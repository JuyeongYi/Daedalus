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
    RUNNER_PAYLOAD,
    ComponentEmitter,
    EmittedFile,
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
from daedalus.model.plugin.roles import Bucket, OutputLocation
from tests.compiler.builders import make_agent, make_procedural


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
    assert RUNNER_PAYLOAD not in (skill_file.payload, agent_file.payload)


def test_render_is_deterministic():
    """같은 모델 → 같은 텍스트 (원칙 6). 두 번 불러 달라지면 숨은 상태가 있다."""
    skill = make_procedural()
    emitter = emitter_for(skill)
    assert emitter.render(skill) == emitter.render(skill)
