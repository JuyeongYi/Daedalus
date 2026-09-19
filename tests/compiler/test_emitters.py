# tests/compiler/test_emitters.py
"""`ComponentEmitter` + 절 적용 표의 **시끄러운 실패** 계약 (REFACTOR_SPEC §2-g·§4-b).

표 구동으로 바뀐 산출의 위험은 "표에서 조용히 빠진 한 행"이다 — 종류가 늘었는데
emitter가 없거나, 절 튜플에 절을 넣었는데 provider를 잊으면, 종전 if 사다리라면
문법 오류가 났을 자리가 **아무 말 없는 누락**이 된다(👻). 그래서 조회 실패는
전부 이유와 선택지를 말하는 `ValueError`이고, 여기서 그것을 고정한다.

종류 ↔ emitter의 **집합 등식**은 `tests/test_kind_registry_parity.py`가 본다
(레지스트리가 그 등식의 한쪽이라 그쪽에 모아 둔다).
"""
from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from daedalus.compiler.emit.emitters import (
    EMITTERS,
    ComponentEmitter,
    EmittedFile,
    compile_skill,
    emitter_for,
)
from daedalus.compiler.emit.section_plan import (
    SECTION_PLANS,
    SECTION_PROVIDERS,
    SectionId,
    plan_for_kind,
    provider_for,
)
from daedalus.compiler.units.paths import output_path
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.kinds import KIND_REGISTRY
from daedalus.model.plugin.roles import Bucket, OutputLocation, PlacementRole
from daedalus.model.project import PluginProject
from tests.compiler.builders import (
    make_agent,
    make_procedural,
    make_reference,
    make_transfer,
)


# ── 조회 실패는 이유와 선택지를 말한다 ────────────────────────────────

def test_emitter_for_unknown_kind_lists_the_registered_kinds():
    with pytest.raises(ValueError) as exc:
        emitter_for(object())
    message = str(exc.value)
    assert "emitter" in message
    for kind in EMITTERS:
        assert kind in message


def test_plan_for_unknown_kind_lists_the_registered_kinds():
    with pytest.raises(ValueError) as exc:
        plan_for_kind("no-such-kind")
    message = str(exc.value)
    for kind in SECTION_PLANS:
        assert kind in message


def test_provider_for_unregistered_section_fails_loudly():
    """provider를 지우면 산출에서 단락이 사라지는 게 아니라 컴파일이 멈춘다."""

    class _Ghost(str):
        pass

    with pytest.raises(ValueError) as exc:
        provider_for(_Ghost("ghost-section"))
    assert "ghost-section" in str(exc.value)


def test_output_path_refuses_a_kind_without_an_output_file():
    with pytest.raises(ValueError):
        output_path(OutputLocation.NONE, "x", PurePosixPath("."))


# ── 표의 완결성 ───────────────────────────────────────────────────────

def test_every_declared_section_has_a_provider():
    """절 튜플에 있는데 provider가 없는 절은 없다."""
    declared = {sid for plan in SECTION_PLANS.values() for sid in plan.sections}
    assert declared <= set(SECTION_PROVIDERS), sorted(declared - set(SECTION_PROVIDERS))


def test_every_provider_is_used_by_some_kind():
    """어느 종류도 쓰지 않는 provider는 죽은 코드다 — 표가 늘어나기만 하는 것을 막는다."""
    declared = {sid for plan in SECTION_PLANS.values() for sid in plan.sections}
    assert set(SECTION_PROVIDERS) == declared, sorted(set(SECTION_PROVIDERS) - declared)


def test_section_ids_are_exactly_the_provider_keys():
    """`SectionId` 멤버는 전부 실제로 쓰인다(퇴역 멤버가 표에 남지 않는다)."""
    assert set(SectionId) == set(SECTION_PROVIDERS)


@pytest.mark.parametrize("kind", sorted(SECTION_PLANS))
def test_section_tuple_has_no_duplicates(kind):
    """같은 절을 두 번 내면 산출에 헤딩이 두 개 나간다 — 순서 표의 조용한 오타."""
    sections = SECTION_PLANS[kind].sections
    assert len(sections) == len(set(sections)), sections


# ── emitter 계약 ─────────────────────────────────────────────────────

@pytest.mark.parametrize("kind", sorted(EMITTERS))
def test_emitter_declares_its_kind_and_plan_kind(kind):
    emitter = EMITTERS[kind]
    assert isinstance(emitter, ComponentEmitter)
    assert emitter.kind == kind
    assert emitter.plan_kind
    assert emitter.label_fmt.format(name="x")
    # 절 선언은 표에서 온다 — emitter가 사본을 들고 있으면 둘이 어긋난다.
    assert emitter.sections is SECTION_PLANS[kind].sections


def test_outputs_declare_the_location_the_component_kind_says():
    skill = make_procedural()
    agent = make_agent()
    (skill_file,) = emitter_for(skill).outputs(skill)
    (agent_file,) = emitter_for(agent).outputs(agent)
    assert skill_file == EmittedFile(
        location=OutputLocation.SKILL_DIR,
        name=skill.name,
        label=f"스킬 '{skill.name}'",
        plan_kind=skill_file.plan_kind,
    )
    assert agent_file.location is OutputLocation.AGENT_FILE
    assert type(skill).BUCKET is Bucket.SKILLS


def test_render_is_deterministic():
    """같은 모델 → 같은 텍스트 (원칙 6). 두 번 불러 달라지면 숨은 상태가 있다."""
    skill = make_procedural()
    emitter = emitter_for(skill)
    assert emitter.render(skill) == emitter.render(skill)


# ── 진행 사슬에 끼는 종류 (`tracks_progress`) ─────────────────────────

def _legacy_project_with(skill) -> PluginProject:
    """**전이·참조 스킬이 상태 노드에 박힌** 손편집/구버전 `.ddpj` 형상.

    GUI는 이런 배치를 만들지 않지만 역직렬화는 막지 않는다 —
    `serialize/deser_fsm.py`의 `skill_ref` 해소는 id 조회뿐이고
    placement 역할을 검사하지 않는다. 그래서 저장 파일에 이 형상이 있으면
    그대로 로드돼 컴파일된다.
    """
    project = PluginProject(name="legacy")
    project.skills.append(skill)
    odd = SimpleState(name="odd")
    odd.skill_ref = skill
    tail = SimpleState(name="tail")
    project.graph.states.extend([odd, tail])
    project.graph.transitions.append(Transition(source=odd, target=tail))
    return project


def test_transfer_skill_never_claims_the_progress_current_pointer():
    """전이 스킬은 상태 노드에 박혀 있어도 `--current`를 지시하지 않는다.

    같은 파일의 '## Progress Record'가 "`current`는 건드리지 말라"고 말하므로
    (`docs/design/compiler.md` 정책 6-a-④), 진행 갱신 지시가 함께 나가면 산출이
    자기 자신과 모순된다. 종전 조립 분기의 `PLACEMENT not in (EDGE, REFERENCE)`
    게이트가 이것을 막았고, 지금은 절 표의 `tracks_progress=False`가 막는다.
    """
    skill = make_transfer()
    text = compile_skill(skill, project=_legacy_project_with(skill))
    assert "--current" not in text
    # 전이 스킬이 내는 진행 지시는 '## Progress Record'의 메모 한 줄뿐이다.
    assert "## Progress Record" in text
    assert "--note" in text


def test_reference_skill_never_gets_a_terminal_finishing_section():
    """참조 스킬은 자기 placement가 없어 '작업 완료'의 주체가 아니다."""
    skill = make_reference()
    project = _legacy_project_with(skill)
    project.graph.transitions.clear()  # 터미널 배치 형상
    text = compile_skill(skill, project=project)
    assert "## Finishing Up" not in text
    assert "--current" not in text


@pytest.mark.parametrize("kind", sorted(SECTION_PLANS))
def test_only_edge_and_reference_kinds_opt_out_of_progress(kind):
    """선언이 종류의 배치 역할과 어긋나지 않는다 (표의 조용한 오타 방지)."""
    component_cls = KIND_REGISTRY[kind].component_cls
    expected = component_cls.PLACEMENT not in (
        PlacementRole.EDGE, PlacementRole.REFERENCE,
    )
    assert SECTION_PLANS[kind].tracks_progress is expected
