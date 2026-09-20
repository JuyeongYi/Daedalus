# tests/compiler/test_unit_contract.py
"""`CompileUnit` 계약 (REFACTOR_SPEC §8 · WP-5).

산출 종류 하나 = 단위 하나로 옮기면서 **드라이버가 더 이상 보지 않게 된
사실들**을 여기서 고정한다. 골든(산출 바이트·계획 순서)은 "결과가 같은가"를
보지만, 이 파일은 "계약이 살아 있는가"를 본다:

  - 단위 id는 유일하고 **선언 순서가 계획 순서**다.
  - 모든 계획 행이 `mode`/`phase`/`expands_root`/`token_kind`를 **선언**한다
    (드라이버의 kind 튜플로 되돌아가지 않는다).
  - `render()`는 순수하다 — 두 번 불러도 같은 텍스트.
  - `plan()`은 **주입된 경로 밖의 파일을 읽지 않는다**(원칙 4).
  - 파사드 계획(`_plan_outputs`) ⊂ 전체 계획이고 차집합은 `{files_tree}`.
  - `OUTPUT_LOCATION`이 NONE인 컴포넌트는 예외 없이 **건너뛴다** — emitter
    조회보다 앞에 게이트가 있기 때문이다(§2-g).
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from daedalus.compiler import plan_kinds
from daedalus.compiler.plan import _plan_outputs
from daedalus.compiler.token_report import TokenKind
from daedalus.compiler.units import (
    UNIT_BY_ID,
    UNITS,
    CompileContext,
    CopyUnit,
    Gate,
    MergeUnit,
    OutputMode,
    Phase,
    Planner,
    TextUnit,
    unit_for,
)
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.roles import Bucket, OutputLocation
from daedalus.model.project import PluginProject

from tests.compiler.builders import make_agent, make_procedural
from tests.data.golden.corpus import FILES_DIR, SKILL_FILES_DIR, build_synthetic

#: 선언 순서 = 계획 순서 = 쓰기 순서. **순서가 계약이다.**
_EXPECTED_UNIT_IDS: list[tuple[str, ...]] = [
    (plan_kinds.SKILL,),
    (plan_kinds.AGENT,),
    (plan_kinds.SKILL_FILE,),
    (plan_kinds.HOOKS_JSON, plan_kinds.HOOK_SCRIPT),
    (plan_kinds.WORKSPACE_RULE,),
    (plan_kinds.GUIDE_WORKFLOW,),
    (plan_kinds.GUIDE_BLACKBOARD,),
    (plan_kinds.SCHEMAS_JSON,),
    (plan_kinds.PLUGIN_MANIFEST,),
    (plan_kinds.MCP_JSON,),
    (plan_kinds.FILES_TREE,),
    (plan_kinds.LOCAL_WIRING,),
    (plan_kinds.CLAUDE_MD,),
]

#: 복사 산출은 텍스트가 아니라 계상 대상이 아니다. 나머지 행은 구간을 밝힌다.
_EXPECTED_TOKEN_KIND: dict[str, TokenKind] = {
    plan_kinds.SKILL: TokenKind.CONTEXT,
    plan_kinds.AGENT: TokenKind.CONTEXT,
    plan_kinds.WORKSPACE_RULE: TokenKind.CONTEXT,
    plan_kinds.GUIDE_WORKFLOW: TokenKind.CONTEXT,
    plan_kinds.GUIDE_BLACKBOARD: TokenKind.CONTEXT,
    plan_kinds.CLAUDE_MD: TokenKind.CONTEXT,
    plan_kinds.HOOKS_JSON: TokenKind.TOTAL_ONLY,
    plan_kinds.HOOK_SCRIPT: TokenKind.TOTAL_ONLY,
    plan_kinds.SCHEMAS_JSON: TokenKind.TOTAL_ONLY,
    plan_kinds.PLUGIN_MANIFEST: TokenKind.TOTAL_ONLY,
    plan_kinds.MCP_JSON: TokenKind.TOTAL_ONLY,
    plan_kinds.SKILL_FILE: TokenKind.NONE,
    plan_kinds.FILES_TREE: TokenKind.NONE,
    plan_kinds.LOCAL_WIRING: TokenKind.NONE,
}


def _local(project: PluginProject) -> PluginProject:
    project.build_target = BuildTarget.LOCAL
    return project


def _full_ctx(project, **kwargs) -> CompileContext:
    return CompileContext.build(
        project, out_dir=Path("out"), files_dir=FILES_DIR,
        skill_files_dir=SKILL_FILES_DIR, dry_run=True, **kwargs,
    )


def _full_plan(project, **kwargs):
    plan, _errors, _warnings = Planner().plan(_full_ctx(project, **kwargs))
    return plan


# ─────────────────────────── 단위 등록 ───────────────────────────


def test_unit_ids_are_unique_and_in_declaration_order():
    assert [unit.unit_ids() for unit in UNITS] == _EXPECTED_UNIT_IDS
    flat = [uid for unit in UNITS for uid in unit.unit_ids()]
    assert len(flat) == len(set(flat))
    assert set(flat) == set(UNIT_BY_ID)


def test_every_plan_kind_has_a_unit():
    """계획 행의 kind는 전부 등록된 단위가 있다 — 없으면 쓰기가 죽는다."""
    for row in _full_plan(_local(build_synthetic(placed=True, blackboard=True))):
        assert unit_for(row) is UNIT_BY_ID[row.kind]


def test_unknown_plan_kind_fails_loudly():
    """등록 없는 kind는 **이유와 선택지**를 말하며 죽는다 (원칙 5)."""
    row = _full_plan(build_synthetic(placed=False, blackboard=False))[0]
    row.kind = "nonesuch"
    with pytest.raises(ValueError) as excinfo:
        unit_for(row)
    assert "nonesuch" in str(excinfo.value)
    assert plan_kinds.SKILL in str(excinfo.value)


# ─────────────────────────── 계획 행의 선언 ───────────────────────────


@pytest.mark.parametrize("placed", [True, False])
def test_every_planned_row_declares_its_shape(placed):
    """행이 `mode`/`phase`/`expands_root`/`token_kind`를 값으로 들고 다닌다."""
    for row in _full_plan(_local(build_synthetic(placed=placed, blackboard=True))):
        assert isinstance(row.mode, OutputMode)
        assert isinstance(row.phase, Phase)
        assert isinstance(row.expands_root, bool)
        assert isinstance(row.token_kind, TokenKind)
        assert row.token_kind is _EXPECTED_TOKEN_KIND[row.kind], row.kind
        unit = unit_for(row)
        if row.mode is OutputMode.TEXT:
            assert isinstance(unit, TextUnit)
        elif row.mode is OutputMode.MERGE:
            assert isinstance(unit, MergeUnit)
        else:
            assert isinstance(unit, CopyUnit)


def test_merge_rows_are_install_phase_and_not_exclusive():
    """병합 행은 쓰기 루프 뒤(INSTALL)에서 돌고 게이트 대상이 아니다."""
    rows = _full_plan(_local(build_synthetic(placed=True, blackboard=False)))
    merges = [r for r in rows if r.mode is OutputMode.MERGE]
    assert {r.kind for r in merges} == {plan_kinds.LOCAL_WIRING, plan_kinds.CLAUDE_MD}
    for row in merges:
        assert row.phase is Phase.INSTALL
        assert row.exclusive is False
    # 나머지는 전부 WRITE 단계다 — 두 단계 사이에 진단 스캔이 있다.
    assert {r.phase for r in rows if r.mode is not OutputMode.MERGE} == {Phase.WRITE}


def test_text_rows_render_identically_twice():
    """`render()`는 순수하다 — 미리보기와 산출이 같은 텍스트여야 한다."""
    project = _local(build_synthetic(placed=True, blackboard=True))
    ctx = _full_ctx(project)
    for row in _full_plan(project):
        unit = unit_for(row)
        if row.mode is not OutputMode.TEXT:
            continue
        assert unit.render(row, ctx) == unit.render(row, ctx), row.kind


def test_plan_does_not_read_files_outside_the_injected_paths(monkeypatch):
    """계획은 파일 **내용**을 읽지 않는다 — 주입이 유일한 입력이다 (원칙 4)."""
    reads: list[str] = []
    original = Path.read_text

    def spy(self, *args, **kwargs):
        reads.append(str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy)
    _full_plan(_local(build_synthetic(placed=True, blackboard=True)))
    assert reads == []


# ─────────────────────── 파사드 계획 ⊂ 전체 계획 ───────────────────────


def test_facade_plan_is_the_full_plan_minus_files_tree():
    """`_plan_outputs`는 out_dir·files_dir를 모르므로 트리 행만 빠진다."""
    project = _local(build_synthetic(placed=True, blackboard=True))
    facade, _errors, _warnings = _plan_outputs(
        project, skill_files_dir=SKILL_FILES_DIR,
    )
    full = _full_plan(project)
    facade_keys = [(r.rel_path, r.kind) for r in facade]
    full_keys = [(r.rel_path, r.kind) for r in full]
    assert [k for k in full_keys if k not in facade_keys] == [
        (PurePosixPath("files"), plan_kinds.FILES_TREE)
    ]
    assert [k for k in facade_keys if k not in full_keys] == []


# ─────────────── 산출 없는 종류는 조용히, 그러나 완전히 빠진다 ───────────────


class _NoOutputComponent:
    """`OUTPUT_LOCATION`이 NONE인 종류의 대역 (WP-9 `ExternalAgent`의 선행 형상).

    모델 클래스를 새로 만들지 않는다 — `PluginComponent`의 구체 서브클래스를
    테스트에서 정의하면 `test_registry_discovery`가 등록 과잉으로 잡는다.
    계획이 읽는 표면(`emits_output()`·`name`)만 갖춘 대역이면 충분하다.
    """
    KIND = "test_no_output"
    BUCKET = Bucket.AGENTS
    OUTPUT_LOCATION = OutputLocation.NONE

    def __init__(self, name: str) -> None:
        self.name = name

    def emits_output(self) -> bool:
        return type(self).OUTPUT_LOCATION is not OutputLocation.NONE

    def hook_refs(self) -> list[str]:
        return []


def test_component_without_output_is_skipped_and_not_name_gated():
    """산출이 없는 종류는 계획에 오르지 않고 **이름 게이트도 받지 않는다**.

    이름이 외부 플러그인의 것이라 CC 파일명 규약(`^[a-z0-9][a-z0-9-]*$`)을
    따를 이유가 없다 — 게이트가 emitter 조회보다 앞에 있는 이유다(§2-g).
    """
    project = PluginProject(
        name="p", skills=[make_procedural("ok-skill")], agents=[make_agent("aide")],
    )
    project.agents.append(_NoOutputComponent("Not A Valid Name"))

    plan, errors, _warnings = _plan_outputs(project)

    assert [r.component for r in plan if r.kind == plan_kinds.AGENT] == [
        project.agents[0]
    ]
    assert [e.source for e in errors] == []
