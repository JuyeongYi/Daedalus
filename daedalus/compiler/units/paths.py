# daedalus/compiler/units/paths.py
"""산출 경로·이름 규약과 트리 열거 규칙 (WP-5, `plan.py`에서 이동만).

계획과 실제 쓰기가 **같은 규칙**을 봐야 하므로 한 곳에 둔다 — 열거를 따로
구현하면 두 목록이 언젠가 어긋난다. `compiler/plan.py`가 여기 이름을 그대로
재-export하므로 기존 임포트 경로는 무수정으로 동작한다
(`tests/compiler/test_plan_facade.py`가 **같은 객체**임을 고정한다).
"""
from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath

from daedalus.compiler.emit import (
    _collect_referenced_hook_names,
    hook_library,
)
from daedalus.model.plugin.roles import OutputLocation
from daedalus.model.validation import ValidationError

# CC 플러그인 산출물 이름 규약 — Validator._COMPONENT_NAME_RE와 동일 패턴.
# 검증기에서는 경고(편집 중)지만 컴파일 게이트에서는 에러로 승격한다.
_OUTPUT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# 스킬별 동봉 파일 소스 디렉토리명 (WP-SF) — <프로젝트 폴더>/skill-files/<스킬 산출
# 디렉토리명>/… 이 그 스킬의 SKILL.md **옆으로** 복사된다. 공용 files/와 분리한
# 이유: files/는 통째로 <out>/files/로 가는 규칙이라, 섞으면 스킬 파일이 양쪽에
# 이중 산출된다. 참조 토큰은 `${CLAUDE_SKILL_DIR}/<상대경로>` — CC 공식 변수로
# 마켓플레이스/로컬 동일 동작이라 ${ROOT} 같은 타깃 중립화가 필요 없다.
SKILL_FILES_DIRNAME = "skill-files"


def _skill_dir_name(skill_name: str) -> str:
    return skill_name


def output_path(
    location: OutputLocation, name: str, cc_prefix: PurePosixPath,
) -> PurePosixPath:
    """컴포넌트 산출 자리(`OutputLocation`) → 산출 루트 기준 상대 경로.

    모델은 **위치 종류**만 말하고(`SKILL_DIR`/`AGENT_FILE`/`NONE`) `skills/<n>/
    SKILL.md` 같은 CC 플러그인 레이아웃 조립은 컴파일러가 한다 — 레이아웃은 CC의
    규약이지 모델의 어휘가 아니다. `emit/`도 이 함수를 부르지 않는다(`emit`은
    `units`보다 아래층이다): emitter는 `EmittedFile`로 자리와 이름만 말한다.

    `NONE`은 도달 불가다 — 호출자가 `emits_output()`으로 앞에서 거른다.
    """
    if location is OutputLocation.SKILL_DIR:
        return cc_prefix / "skills" / _skill_dir_name(name) / "SKILL.md"
    if location is OutputLocation.AGENT_FILE:
        return cc_prefix / "agents" / f"{name}.md"
    raise ValueError(
        f"산출 파일이 없는 자리입니다: {location!r} — "
        f"`emits_output()`이 거짓인 컴포넌트에는 경로를 묻지 않는다."
    )


def _hook_script_name_conflicts(project, resolved_hooks=None) -> list[ValidationError]:
    """서로 다른 훅이 같은 스크립트 파일명으로 슬러그되면 에러 (duplicate_hook_script).

    훅 이름은 사용자가 자유롭게 쓰지만 파일명은 ``_slug``를 거친다 — '`run tests`'와
    '`run-tests`'는 이름이 다른데 파일명이 `run-tests.sh` 하나로 겹친다.
    ``compile_hook_scripts``는 먼저 선언된 훅을 남기고 뒤의 것을 조용히 버리므로,
    게이트가 없으면 **훅 하나가 아무 말 없이 사라진 산출물**이 나간다.

    산출 경로 충돌(``compile_output_path_conflict``)이 잡지 못하는 이유가 그것이다 —
    드롭이 계획 이전에 일어나 계획에는 경로가 하나만 올라온다. 그래서 계획을 세우기
    전에 라이브러리 쪽에서 판정한다.

    같은 훅 안의 파일명 중복은 대상이 아니다(``script_files``가 번호로 유일화한다).
    """
    library = hook_library(project, resolved_hooks)
    referenced = set(_collect_referenced_hook_names(project))

    owners: dict[str, str] = {}          # 파일명 → 먼저 점유한 훅 이름
    conflicts: dict[str, list[str]] = {}  # 파일명 → 충돌한 훅 이름들(선언 순서)
    for hook in library:
        if hook.name not in referenced:
            continue
        for filename, _body in hook.script_files():
            first = owners.get(filename)
            if first is None:
                owners[filename] = hook.name
            elif first != hook.name:
                conflicts.setdefault(filename, [first]).append(hook.name)

    return [
        ValidationError(
            rule="duplicate_hook_script",
            message=(
                f"훅 스크립트 파일명 '{filename}'이 충돌합니다: "
                f"{', '.join(repr(n) for n in names)}. 훅 이름이 파일명으로 바뀔 때 "
                f"같은 이름이 되어, 그대로 진행하면 먼저 선언된 훅의 스크립트만 "
                f"남고 나머지는 조용히 사라집니다 — 훅 이름을 조정하거나 핸들러에 "
                f"script_name을 지정하세요."
            ),
            source=filename,
            subject=project,
        )
        for filename, names in conflicts.items()
    ]


def _iter_tree_files(root: Path) -> list[Path]:
    """root 트리의 파일을 정렬 순회로 열거한다 (WP-SF — 복사 계획용).

    ``_copy_files_tree``와 같은 규칙: 심볼릭 링크/정션은 디렉토리든 파일이든
    제외한다(따라가면 트리 밖 내용이 산출물로 샌다).
    """
    files: list[Path] = []
    for walk_root, dirnames, filenames in os.walk(root, followlinks=False):
        root_path = Path(walk_root)
        dirnames[:] = sorted(d for d in dirnames if not _is_link_like(root_path / d))
        for filename in sorted(filenames):
            src = root_path / filename
            if not _is_link_like(src):
                files.append(src)
    return files


def _is_link_like(path: Path) -> bool:
    """심볼릭 링크 또는 Windows 정션이면 True — files/ 복사에서 제외 대상."""
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    return bool(isjunction and isjunction(path))
