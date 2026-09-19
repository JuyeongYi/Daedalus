# daedalus/compiler/plan.py
"""산출 계획 파사드 — 계획 수립의 **기존 진입점**을 지킨다 (WP-5).

계획의 실체는 `compiler/units/`로 옮겼다(이동만, 동작 불변): 산출 종류 하나가
`CompileUnit` 하나이고, 선언 순서 있는 `units.registry.UNITS`가 계획 순서를
소유한다. 이 모듈은 그 앞의 **이름 파사드**다 —

  - `_plan_outputs(project, skill_files_dir=None, resolved_hooks=None)` —
    종전 시그니처. 내부에서 `CompileContext`를 만들어 `Planner`에 넘긴다.
    `out_dir`/`files_dir`가 없으므로 공용 files/ 트리 행(`files_tree`)은
    오르지 않는다 — 전체 계획을 보려면 `Planner().plan(CompileContext.build(...))`.
  - `_PlannedOutput` — `units.base.PlannedOutput`의 **같은 객체** 별칭.
  - 경로·이름 규약 헬퍼 6종 — `units/paths.py`의 같은 객체를 재-export한다.

`project_compiler`가 여기 이름을 다시 재-export하므로 기존 임포트 경로
(`from daedalus.compiler.project_compiler import SKILL_FILES_DIRNAME` 등)는
무수정으로 동작한다(`tests/compiler/test_plan_facade.py`가 **복제가 아니라
같은 객체**임을 고정한다 — 계획과 쓰기가 같은 판정을 봐야 한다).
"""
from __future__ import annotations

from pathlib import Path

from daedalus.compiler.units.base import PlannedOutput
from daedalus.compiler.units.context import CompileContext
from daedalus.compiler.units.paths import (  # noqa: F401 — 재-export 파사드
    SKILL_FILES_DIRNAME,
    _hook_script_name_conflicts,
    _is_link_like,
    _iter_tree_files,
    _OUTPUT_NAME_RE,
    _skill_dir_name,
)
from daedalus.compiler.units.registry import PLANNER
from daedalus.model.validation import ValidationError

#: 종전 이름 — 같은 클래스다(복제 금지).
_PlannedOutput = PlannedOutput


def _plan_outputs(
    project, skill_files_dir: Path | None = None, resolved_hooks=None,
) -> tuple[list[_PlannedOutput], list[ValidationError], list[ValidationError]]:
    """종전 진입점 — 대상 폴더 없이(dry-run) 계획만 세운다.

    skill_files_dir(WP-SF, 선택): 스킬별 동봉 파일 트리. 하위 폴더 이름이 스킬
    산출 디렉토리명과 일치하면 그 파일들이 SKILL.md 옆으로 가는 복사 계획으로
    합류한다 — 계획 집합에 넣기 때문에 SKILL.md를 덮는 파일이 있으면 기존
    `compile_output_path_conflict` 게이트가 잡는다. 일치하는 스킬이 없는 하위
    폴더는 `unknown_skill_files_dir` 경고(세 번째 반환값).
    """
    ctx = CompileContext.build(
        project, skill_files_dir=skill_files_dir, resolved_hooks=resolved_hooks,
        dry_run=True,
    )
    return PLANNER.plan(ctx)
