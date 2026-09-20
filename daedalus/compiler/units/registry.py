# daedalus/compiler/units/registry.py
"""컴파일 단위 등록과 계획 수립 (WP-5).

`UNITS`는 **선언 순서 있는 튜플**이고 계획 순서 = 쓰기 순서다 — 종전
`_plan_outputs`의 문단 등장 순서를 그대로 옮겼다. 순서를 바꾸면 산출 파일의
내용은 같아도 `written`/`copied_files`/경고의 순서가 달라진다
(`tests/compiler/test_plan_order_golden.py`가 고정한다).

새 산출을 더하는 사람은 단위 하나를 쓰고 이 튜플에 한 줄 넣는다. 드라이버·
게이트·토큰 리포트는 고치지 않는다 — 그것이 이 표의 값이다.
"""
from __future__ import annotations

from daedalus.compiler.units.base import CompileUnit, PlannedOutput
from daedalus.compiler.units.components import ComponentUnit
from daedalus.compiler.units.context import CompileContext
from daedalus.compiler.units.docs import (
    GUIDE_UNITS,
    ManifestUnit,
    McpJsonUnit,
    SchemasUnit,
    WorkspaceRuleUnit,
)
from daedalus.compiler.units.gate import Gate
from daedalus.compiler.units.hooks import HooksUnit
from daedalus.compiler.units.install import ClaudeMdUnit, LocalWiringUnit
from daedalus.compiler.units.trees import FilesTreeUnit, SkillFilesUnit
from daedalus.model.plugin.roles import Bucket
from daedalus.model.validation import ValidationError

#: 계획 순서 = 쓰기 순서. **순서가 계약이다.**
UNITS: tuple[CompileUnit, ...] = (
    ComponentUnit(Bucket.SKILLS),
    ComponentUnit(Bucket.AGENTS),
    SkillFilesUnit(),
    HooksUnit(),
    WorkspaceRuleUnit(),
    *GUIDE_UNITS,
    SchemasUnit(),
    ManifestUnit(),
    McpJsonUnit(),
    FilesTreeUnit(),
    LocalWiringUnit(),
    ClaudeMdUnit(),
)


def _index(units: tuple[CompileUnit, ...]) -> dict[str, CompileUnit]:
    out: dict[str, CompileUnit] = {}
    for unit in units:
        for unit_id in unit.unit_ids():
            if unit_id in out:
                raise ValueError(
                    f"산출 계획 kind '{unit_id}'를 두 단위가 주장합니다: "
                    f"{type(out[unit_id]).__name__} ↔ {type(unit).__name__}"
                )
            out[unit_id] = unit
    return out


#: 계획 행의 kind → 그 행을 쓸 단위.
UNIT_BY_ID: dict[str, CompileUnit] = _index(UNITS)


def unit_for(planned: PlannedOutput) -> CompileUnit:
    """계획 행을 쓸 단위 — 없으면 시끄럽게 실패한다 (원칙 5)."""
    unit = UNIT_BY_ID.get(planned.kind)
    if unit is None:
        raise ValueError(
            f"알 수 없는 산출 계획 kind: {planned.kind!r} — "
            f"등록: {', '.join(sorted(UNIT_BY_ID))}"
        )
    return unit


class Planner:
    """단위를 선언 순서로 돌려 계획을 세우고 게이트를 친다."""

    def __init__(self, units: tuple[CompileUnit, ...] = UNITS) -> None:
        self.units = tuple(units)

    def plan(
        self, ctx: CompileContext,
    ) -> tuple[list[PlannedOutput], list[ValidationError], list[ValidationError]]:
        """파일 쓰기 전에 전체 산출 경로 집합을 계산하고 게이트 에러를 수집한다.

        에러 3종:
          compile_invalid_component_name — 산출 이름 규약 불일치 (게이트에서 에러 승격)
          compile_output_path_conflict   — 동일 산출 경로 중복 (조용한 덮어쓰기 방지)
          duplicate_hook_script          — 서로 다른 훅이 같은 스크립트 파일명으로
                                           슬러그됨 (조용한 드롭 방지, WP-HS)
        """
        gate = Gate()
        # 프로젝트 이름은 **모든 컴포넌트 에러보다 앞**에 온다(문구도 다르다).
        gate.check_project_name(ctx.project)
        plan: list[PlannedOutput] = []
        for unit in self.units:
            plan.extend(unit.plan(ctx, gate))
        self._check_path_conflicts(plan, gate)
        return plan, gate.errors, gate.warnings

    @staticmethod
    def _check_path_conflicts(plan: list[PlannedOutput], gate: Gate) -> None:
        """산출 경로 충돌 검사 — 첫 점유자와 이후 충돌자를 모두 보고.

        `exclusive=False` 행(트리 복사·병합)은 대상이 아니다 — 경로 하나가
        산출 하나라는 전제를 만족하지 않는다.
        """
        seen: dict = {}
        for item in plan:
            if not item.exclusive:
                continue
            first = seen.get(item.rel_path)
            if first is not None:
                gate.fail(ValidationError(
                    rule="compile_output_path_conflict",
                    message=(
                        f"산출 경로 '{item.rel_path}'가 충돌합니다: {first.label} ↔ "
                        f"{item.label}. 그대로 진행하면 뒤의 쓰기가 앞의 산출물을 "
                        f"조용히 덮어씁니다 — 컴포넌트 이름을 조정하세요."
                    ),
                    source=str(item.rel_path),
                    subject=item.subject,
                ))
            else:
                seen[item.rel_path] = item


#: 드라이버가 쓰는 기본 계획기.
PLANNER = Planner()
