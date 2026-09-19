# daedalus/compiler/units/context.py
"""컴파일 1회의 **주입된 사실** (WP-5).

원칙 4: 검증기·컴파일러는 파일시스템을 읽지 않는다 — 호출자가 주입한다. 그
주입 인자가 여기 한 덩어리로 모인다. 계획 단위(`CompileUnit.plan`)와 쓰기
(`CompileUnit.emit`)가 **같은 ctx**를 보므로 "계획은 LOCAL로 세우고 쓰기는
MARKETPLACE로"와 같은 어긋남이 구조적으로 불가능하다.

`compile_project`의 인자와 1:1이다 — 새 주입 인자는 여기와 `build()`에 한 줄씩
더하고, 단위는 `ctx.<이름>`으로 읽는다(시그니처가 단위 수만큼 늘지 않는다).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from daedalus.compiler.emit import _is_local_build


@dataclass(frozen=True)
class CompileContext:
    """한 번의 컴파일이 아는 모든 것 — 값 객체(불변)."""

    project: Any
    #: 빌드 타깃이 LOCAL인가 — 산출 위치·설치 배선이 갈리는 유일한 축.
    is_local: bool
    #: 산출 루트 기준 CC 디렉토리 접두 — LOCAL ".claude", MARKETPLACE ".".
    cc_prefix: PurePosixPath
    #: 대상 폴더. None이면 dry-run 중 대상 미지정(계획 경로가 상대 경로가 된다).
    out_root: Path | None
    files_dir: Path | None
    skill_files_dir: Path | None
    resolved_hooks: dict | None
    extra_server_defs: dict[str, dict] | None
    provided_server_names: frozenset[str] | None
    settings_filename: str
    dry_run: bool

    @classmethod
    def build(
        cls, project, *,
        out_dir: Path | str | None = None,
        files_dir: Path | str | None = None,
        skill_files_dir: Path | str | None = None,
        resolved_hooks: dict | None = None,
        extra_server_defs: dict[str, dict] | None = None,
        provided_server_names: set[str] | frozenset[str] | None = None,
        settings_filename: str = "settings.json",
        dry_run: bool = False,
    ) -> "CompileContext":
        """`compile_project` 인자 → 컨텍스트 (정규화는 여기 한 곳)."""
        is_local = _is_local_build(project)
        return cls(
            project=project,
            is_local=is_local,
            # LOCAL은 컴파일이 곧 설치 — 스킬/에이전트가 CC가 실제로 읽는
            # <작업 폴더>/.claude/ 밑으로 바로 나간다. files/·schemas/·
            # hooks/scripts/는 루트 그대로다(본문의 ${CLAUDE_PROJECT_DIR}/…
            # 참조가 그 위치를 가리킨다).
            cc_prefix=PurePosixPath(".claude") if is_local else PurePosixPath("."),
            out_root=Path(out_dir) if out_dir is not None else None,
            files_dir=Path(files_dir) if files_dir is not None else None,
            skill_files_dir=(
                Path(skill_files_dir) if skill_files_dir is not None else None
            ),
            resolved_hooks=resolved_hooks,
            extra_server_defs=extra_server_defs,
            provided_server_names=(
                frozenset(provided_server_names)
                if provided_server_names is not None else None
            ),
            settings_filename=settings_filename,
            dry_run=dry_run,
        )
