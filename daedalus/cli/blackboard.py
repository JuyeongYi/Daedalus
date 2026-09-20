# daedalus/cli/blackboard.py
"""블랙보드 CLI (``daedalus-bb``) — 얇은 argparse 진입점 (WP-BM 단계 1).

판정·검증·쓰기의 실체는 전부 :mod:`daedalus.cli.core`(와 진행 파일의
:mod:`daedalus.cli.progress`)에 있다. 이 모듈이 하는 일은 셋뿐이다:
인자 파싱 → 코어 호출 → **출력 채널 배분**.

소비자가 LLM이므로 **stdout에 나가는 것은 JSON뿐**이고, 진단·안내는 stderr로
나간다. 성공 경로는 stdout에 JSON 한 덩이를 낸다. 오류 경로(exit 2/3, init·write의
exit 1)는 stdout에 **아무것도 쓰지 않는다** — ``validate``만 예외로, 검증에
실패해도 ``{"ok": false, "violations": [...]}``를 stdout에 낸다. 즉 stdout을
무조건 ``json.loads``에 먹이지 말고 exit code로 먼저 갈라야 한다.

exit code: 0 성공 / 1 검증 실패·쓰기 미반영 / 2 사용법·스키마·IO 오류 /
3 대상 상태 파일 없음. 코어의 오류 kind와 1:1이다(`core.KIND_TO_EXIT`).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from daedalus.cli import progress as progress_mod
from daedalus.cli.core import (  # noqa: F401 — 재-export 파사드 (종전 임포트 경로 유지)
    DEFAULT_STATE_ROOT,
    EXIT_INVALID,
    EXIT_NO_FILE,
    EXIT_OK,
    EXIT_USAGE,
    PROGRESS_CLASS,
    PROGRESS_FILENAME,
    BlackboardError,
    _WRITE_MAX_ATTEMPTS,
    class_schema,
    coerce_array,
    coerce_scalar,
    field_schema,
    initial_object,
    load_schemas,
    plugin_name,
    read_raw,
    read_state,
    resolve_state_dir,
    state_path,
    validate_object,
    write_state,
    write_state_checked,
)

#: 종전 이름. 코어의 오류 하나가 CLI 오류이기도 하다(exit code는 `.code`).
CliError = BlackboardError


# ─────────────────────────── 출력 ───────────────────────────


def _emit(value: Any) -> None:
    """stdout에 JSON 한 덩이 — 기계 소비자(LLM)를 위한 유일한 출력 채널."""
    sys.stdout.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _note(message: str) -> None:
    sys.stderr.write(message + "\n")


def _report_violations(violations: list[str]) -> None:
    _note("검증 실패:")
    for line in violations:
        _note(f"  - {line}")


# ─────────────────────────── 인자 ───────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="daedalus-bb",
        description="Daedalus 블랙보드 상태 파일(state/) 읽기·쓰기·검증 CLI.",
    )
    parser.add_argument(
        "--state-dir",
        default=None,
        metavar="DIR",
        help=(
            f"상태 파일 폴더 "
            f"(기본: {DEFAULT_STATE_ROOT}/<--schemas 파일 이름>)"
        ),
    )
    # 필수다. 기본값을 두면 빠뜨렸을 때 "그 파일이 없다"고만 답해 **무엇이 빠졌는지**
    # 말해 주지 않는다 (WP-NS/D10).
    parser.add_argument(
        "--schemas",
        required=True,
        metavar="PATH",
        help="블랙보드 스키마 파일 (필수) — 예: schemas/<플러그인>.json",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>", required=True)

    read_p = sub.add_parser("read", help="상태 파일 전체 또는 필드 값 출력")
    read_p.add_argument("cls", metavar="Class")
    read_p.add_argument("--field", metavar="NAME", default=None)

    init_p = sub.add_parser("init", help="스키마 기반 초기 객체 생성")
    init_p.add_argument("cls", metavar="Class")
    init_p.add_argument("--force", action="store_true", help="이미 있어도 재생성")

    write_p = sub.add_parser("write", help="읽기-수정-쓰기 (검증 통과 시에만 기록)")
    write_p.add_argument("cls", metavar="Class")
    write_p.add_argument(
        "--set", dest="sets", action="append", default=[], metavar="FIELD=VALUE"
    )
    write_p.add_argument(
        "--append", dest="appends", action="append", default=[], metavar="FIELD=VALUE"
    )
    write_p.add_argument(
        "--remove", dest="removes", action="append", default=[], metavar="FIELD=VALUE"
    )

    validate_p = sub.add_parser("validate", help="상태 파일 검증 (생략 시 전 클래스)")
    validate_p.add_argument("classes", nargs="*", metavar="Class")

    sub.add_parser("list", help="스키마의 클래스·필드 목록")

    progress_p = sub.add_parser("progress", help="진행 상태 파일 읽기·갱신")
    progress_sub = progress_p.add_subparsers(
        dest="progress_command", metavar="<subcommand>", required=True
    )
    progress_sub.add_parser("read", help="이 플러그인의 진행 항목 출력")
    progress_set = progress_sub.add_parser("set", help="이 플러그인의 진행 항목 갱신")
    progress_set.add_argument("--current", metavar="SKILL", default=None)
    progress_set.add_argument(
        "--completed", action="append", default=[], metavar="SKILL"
    )
    progress_set.add_argument("--note", metavar="TEXT", default=None)
    progress_set.add_argument("--prev", metavar="SKILL", default=None)
    return parser


def _split_assignment(raw: str, option: str) -> tuple[str, str]:
    if "=" not in raw:
        raise CliError(
            "usage", f"{option} 값은 FIELD=VALUE 형식이어야 한다: {raw!r}"
        )
    name, _, value = raw.partition("=")
    name = name.strip()
    if not name:
        raise CliError("usage", f"{option} 값의 필드 이름이 비었다: {raw!r}")
    return name, value


def _assignments(raws: list[str], option: str, *, accumulate: bool) -> dict[str, Any]:
    """``FIELD=VALUE`` 목록 → 코어가 받는 맵.

    ``--set``은 같은 필드가 반복되면 마지막이 이긴다(대입이다). ``--append``/
    ``--remove``는 원소 연산이라 반복이 **누적**된다 — 값이 리스트면 코어가
    원소 여럿으로 읽는다.
    """
    out: dict[str, Any] = {}
    for raw in raws:
        name, value = _split_assignment(raw, option)
        if not accumulate:
            out[name] = value
            continue
        bucket = out.setdefault(name, [])
        bucket.append(value)
    return out


# ─────────────────────────── 디스패치 ───────────────────────────


def _dispatch(args: argparse.Namespace) -> int:
    schemas_path = Path(args.schemas)
    state_dir = resolve_state_dir(args.state_dir, schemas_path)

    if args.command == "progress":
        plugin = plugin_name(schemas_path)
        if args.progress_command == "read":
            _emit(progress_mod.read_entry(state_dir, plugin))
            return EXIT_OK
        progress_mod.set_entry(
            state_dir,
            plugin,
            current=args.current,
            completed=list(args.completed),
            note=args.note,
            prev=args.prev,
            on_note=_note,
        )
        return EXIT_OK

    from daedalus.cli import core

    schemas = core.load_schemas(schemas_path)

    if args.command == "list":
        _emit(core.list_classes(schemas, state_dir, schemas_path))
        return EXIT_OK
    if args.command == "read":
        _emit(core.read_value(schemas, state_dir, args.cls, args.field))
        return EXIT_OK
    if args.command == "init":
        _emit(core.init_class(schemas, state_dir, args.cls, args.force, on_note=_note))
        return EXIT_OK
    if args.command == "write":
        obj = core.write_class(
            schemas,
            state_dir,
            args.cls,
            sets=_assignments(args.sets, "--set", accumulate=False),
            appends=_assignments(args.appends, "--append", accumulate=True),
            removes=_assignments(args.removes, "--remove", accumulate=True),
            on_note=_note,
        )
        _emit(obj)
        return EXIT_OK
    if args.command == "validate":
        result = core.validate_classes(
            schemas, state_dir, args.classes, on_note=_note
        )
        if result["violations"]:
            _report_violations(result["violations"])
        _emit(result)
        return core.validate_code(result, bool(args.classes))
    raise CliError("usage", f"알 수 없는 명령: {args.command}")  # pragma: no cover


def _force_utf8_streams() -> None:
    """stdout/stderr를 UTF-8로 고정한다.

    Windows에서 파이프로 넘길 때 Python은 로케일 인코딩(cp949 등)을 쓰는데,
    이 CLI의 출력을 읽는 쪽(CC/LLM)은 UTF-8로 읽는다 — 그대로 두면 한국어
    진단 메시지가 깨진 바이트로 전달된다. 테스트의 capsys처럼 reconfigure를
    갖지 않는 스트림도 있으므로 조용히 넘어간다.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):  # pragma: no cover - 환경 의존
            pass


def main(argv: list[str] | None = None) -> int:
    """``daedalus-bb`` 진입점 — 반환값이 그대로 exit code."""
    _force_utf8_streams()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse의 --help(0) / 사용법 오류(2)
        return int(exc.code or 0)
    try:
        return _dispatch(args)
    except BlackboardError as exc:
        if exc.detail:
            _report_violations(exc.detail)
        _note(exc.message)
        return exc.code
    except OSError as exc:
        _note(f"입출력 오류: {exc}")
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
