# daedalus/cli/progress.py
"""``daedalus-bb progress`` — 진행 상태 파일 읽기·갱신 (WP-NS/D13).

`state/__progress__.json`은 플러그인 FSM(프로젝트 그래프)의 진행 위치를 담는
**스키마 밖 규약 파일**이다. 최상위 키가 플러그인 이름이고, 그 아래에 항목이 온다:

    {"my-plugin": {"current": ..., "completed": [...], "note": ..., "prev": ...,
                   "updated": ...}}

**왜 CLI가 전담하는가.** 이 파일은 지금까지 산출된 스킬 본문의 산문 지시로
손편집됐다. 최상위 키가 생기면 "다른 플러그인의 키는 건드리지 말라"는 병합을 LLM이
손으로 해야 하는데, 한 번 놓치면 파일을 통째 덮어써 남의 진행 상태를 지운다 —
파일시스템 충돌을 파일 안으로 옮기는 셈이다. 블랙보드에 CLI를 만든 이유("말로만
시키면 LLM이 JSON을 손으로 만들다 스키마를 어긴다")가 이 파일에는 적용된 적이
없었고, 이 모듈이 그 부채를 갚는다.

`blackboard`의 원자적 쓰기와 낙관적 잠금을 그대로 재사용한다 — 병렬 서브에이전트가
같은 파일을 갱신하는 시나리오가 블랙보드와 똑같이 성립하기 때문이다.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from daedalus.cli.blackboard import (
    _WRITE_MAX_ATTEMPTS,
    EXIT_INVALID,
    EXIT_NO_FILE,
    EXIT_OK,
    EXIT_USAGE,
    PROGRESS_FILENAME,
    CliError,
    _emit,
    _note,
    read_raw,
    write_state,
    write_state_checked,
)

#: 항목의 필드 — 없는 필드는 쓰지 않는다(빈 값으로 채우면 "설정했다"와 구분이 안 된다).
_ENTRY_FIELDS = ("current", "completed", "note", "prev", "updated")


def progress_path(state_dir: Path) -> Path:
    """진행 파일 경로 — `--state-dir`의 **부모**에 놓인다.

    블랙보드는 `state/<플러그인>/`으로 갈라지지만 진행 파일은 `state/` 루트에 하나로
    남기 때문이다(D13). 인자 하나(`--state-dir`)가 두 위치를 모두 결정하므로 서로
    어긋날 수 없다.
    """
    return state_dir.parent / PROGRESS_FILENAME


def load_progress(path: Path) -> tuple[dict[str, Any], str | None]:
    """진행 파일을 읽어 `(내용, 원문)`을 돌려준다. 없으면 `({}, None)`.

    원문을 함께 돌려주는 이유는 낙관적 잠금 때문이다 — 쓰기 직전에 디스크가 그대로인지
    비교해야 한다.

    깨진 JSON과 **구형식 파일은 거부한다.** 기존 런타임 데이터를 마이그레이션하지
    않기로 했지만(D11), 그것이 조용히 덮어써도 된다는 뜻은 아니다.
    """
    raw = read_raw(path)
    if raw is None:
        return {}, None
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise CliError(
            f"진행 파일 JSON 파싱 실패: {path.as_posix()}: {exc}\n"
            f"손으로 고치거나 {PROGRESS_FILENAME}을 지운 뒤 다시 시도하라.",
            EXIT_USAGE,
        ) from exc
    if not isinstance(data, dict):
        raise CliError(
            f"진행 파일 최상위가 JSON 객체가 아니다: {path.as_posix()}", EXIT_USAGE
        )
    # 새 형식은 "플러그인 이름 → 항목 객체"라 모든 값이 객체다. 구형식은 최상위에
    # current/completed가 바로 놓여 값이 문자열·배열이다.
    for key, value in data.items():
        if not isinstance(value, dict):
            raise CliError(
                f"구형식 진행 파일이다: {path.as_posix()} (최상위 '{key}'가 객체가 "
                f"아니다).\n새 형식은 플러그인 이름을 최상위 키로 쓴다 — 이전 진행 "
                f"기록은 이어받지 않으므로 파일을 지우고 다시 시작하라.",
                EXIT_USAGE,
            )
    return data, raw


def _merge_entry(
    entry: dict[str, Any],
    *,
    current: str | None,
    completed: list[str],
    note: str | None,
    prev: str | None,
) -> dict[str, Any]:
    """항목 갱신 — 주어진 값만 바꾸고 `completed`는 중복 없이 누적한다."""
    merged = dict(entry)
    if current is not None:
        merged["current"] = current
    if note is not None:
        merged["note"] = note
    if prev is not None:
        merged["prev"] = prev
    if completed:
        done = list(merged.get("completed") or [])
        for name in completed:
            if name not in done:
                done.append(name)
        merged["completed"] = done
    merged["updated"] = datetime.now().astimezone().isoformat(timespec="seconds")
    return {key: merged[key] for key in _ENTRY_FIELDS if key in merged}


def cmd_read(state_dir: Path, plugin: str) -> int:
    """이 플러그인의 항목만 stdout으로 낸다. 없으면 exit 3.

    남의 항목을 대신 보여주지 않는다 — 파일이 공유될 뿐 항목은 각자의 것이다.
    """
    path = progress_path(state_dir)
    data, _ = load_progress(path)
    entry = data.get(plugin)
    if entry is None:
        raise CliError(
            f"'{plugin}'의 진행 기록이 없다: {path.as_posix()}", EXIT_NO_FILE
        )
    _emit(entry)
    return EXIT_OK


def cmd_set(
    state_dir: Path,
    plugin: str,
    *,
    current: str | None,
    completed: list[str],
    note: str | None,
    prev: str | None,
) -> int:
    """이 플러그인의 항목을 갱신한다 — 다른 최상위 키는 건드리지 않는다.

    읽기-수정-쓰기를 낙관적 잠금으로 감싼다(블랙보드 write와 같은 관례). 충돌은
    "남이 방금 썼다"는 뜻이므로 다시 읽어 적용하면 대개 한 번에 끝난다.
    """
    path = progress_path(state_dir)
    for attempt in range(1, _WRITE_MAX_ATTEMPTS + 1):
        data, raw = load_progress(path)
        data[plugin] = _merge_entry(
            data.get(plugin) or {},
            current=current,
            completed=completed,
            note=note,
            prev=prev,
        )
        if raw is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_state(path, data)
            return EXIT_OK
        if write_state_checked(path, data, raw):
            return EXIT_OK
        _note(
            f"다른 프로세스가 {path.as_posix()}를 먼저 갱신했다 — 다시 읽는다 "
            f"({attempt}/{_WRITE_MAX_ATTEMPTS})."
        )
    raise CliError(
        f"쓰지 않았다 — {path.as_posix()}를 {_WRITE_MAX_ATTEMPTS}번 시도하는 동안 "
        f"매번 다른 프로세스가 먼저 갱신했다.",
        # 블랙보드 write의 재시도 소진(`_cmd_write`)과 **같은 상황·같은 계약**이다:
        # 사용법이 틀린 것이 아니라 "쓰기가 반영되지 않았다"이므로 exit 1이다.
        EXIT_INVALID,
    )
