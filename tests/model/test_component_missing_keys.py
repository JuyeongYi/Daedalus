# tests/model/test_component_missing_keys.py
"""**부재 의미론** 고정 — 키가 없는 저장 파일이 무엇으로 로드되는가.

REFACTOR_SPEC §2-d / §8 `test_component_missing_keys` 행. WP-4가 컴포넌트
역직렬화를 표 구동 엔진(`COMPONENT_MISSING`)으로 바꿀 때의 게이트다.

**왜 JSON 골든만으로는 부족한가.** 골든은 *키가 있는* 파일만 지킨다. 오늘
`deser_plugin.py`는 `d.get("transfer_on", [])`로 **빈 목록**을 쓰는데
`StepSkill`/`WrappedSkill`의 dataclass 기본값은 `[EventDef("done")]`이다 —
선언형 엔진이 "키가 없으면 dataclass 기본값"으로만 떨어지면 키 없는 파일에
출력 포트 `done`이 **발명**되고, `transfer_on_not_empty` 검증이 에러에서
조용한 통과로 뒤집힌다(원칙 5 위반). 그 차이를 직접 잡는다.

에이전트 쪽(`AgentDefinition.transfer_on`)은 dataclass 기본값이 이미 빈
목록이라 같은 함정이 없지만, 두 버킷이 **같은 답**을 낸다는 사실도 함께 고정한다.
"""
from __future__ import annotations

import pytest

from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import (
    AsyncForkSkill,
    ProceduralSkill,
    SyncForkSkill,
    WrappedSkill,
)
from daedalus.model.serialize.deser import _Registry
from daedalus.model.serialize.deser_plugin import _deser_agent, _deser_skill

_EMPTY_FSM = {
    "id": "fsm0",
    "name": "m",
    "states": [{"kind": "simple", "id": "s0", "name": "work"}],
    "initial_state": "s0",
    "final_states": [],
    "transitions": [],
}

_STEP_KINDS = {
    "procedural_skill": ProceduralSkill,
    "sync_fork_skill": SyncForkSkill,
    "async_fork_skill": AsyncForkSkill,
    "wrapped_skill": WrappedSkill,
}


def _skill_dict(kind: str) -> dict:
    """`transfer_on`/`call_agents` 키가 **없는** 스킬 dict (구버전 파일 모사)."""
    return {
        "kind": kind, "id": "sk0", "name": "s", "description": "d",
        "when_to_use": "w", "body": "", "fsm": _EMPTY_FSM,
    }


@pytest.mark.parametrize("kind", sorted(_STEP_KINDS))
def test_step_skill_without_transfer_on_loads_empty(kind):
    """키 부재 → `transfer_on == []` (dataclass 기본값 `[done]`이 **아니다**)."""
    skill = _deser_skill(_skill_dict(kind), _Registry())
    assert type(skill) is _STEP_KINDS[kind]
    assert skill.transfer_on == [], (
        f"{kind}: 키 없는 파일에 출력 포트가 발명됐다 — "
        f"부재값은 빈 목록이어야 한다(REFACTOR_SPEC §2-d COMPONENT_MISSING)."
    )
    assert skill.call_agents == []


@pytest.mark.parametrize("kind", sorted(_STEP_KINDS))
def test_dataclass_default_differs_from_absent_value(kind):
    """부재값과 dataclass 기본값이 **다르다**는 사실 자체를 고정한다.

    이 단언이 깨지는 경우는 둘이다: ① dataclass 기본값이 빈 목록으로 바뀌었다
    (그러면 이 테스트의 존재 이유가 사라지므로 함께 정리한다) ② 누군가
    부재 의미론을 기본값 쪽으로 맞췄다(회귀). 어느 쪽인지 사람이 보게 한다.
    """
    cls = _STEP_KINDS[kind]
    field = next(f for f in cls.__dataclass_fields__.values() if f.name == "transfer_on")
    default = field.default_factory()
    assert [e.name for e in default] == ["done"], (
        f"{kind}.transfer_on의 dataclass 기본값이 바뀌었다: {default}"
    )


def test_transfer_skill_has_no_ports_at_all():
    """전이 스킬은 포트 개념이 없다 — 키를 넣어도 필드가 생기지 않는다."""
    data = _skill_dict("transfer_skill")
    data["transfer_on"] = [{"name": "done"}]
    skill = _deser_skill(data, _Registry())
    assert not hasattr(skill, "transfer_on")


def test_declarative_and_reference_skills_load_without_fsm():
    """FSM·포트 키가 없는 종류도 키 부재를 조용히 견딘다."""
    for kind in ("declarative_skill", "reference_skill"):
        data = {"kind": kind, "id": "sk0", "name": "s", "description": "d"}
        skill = _deser_skill(data, _Registry())
        assert skill.kind == kind
        assert skill.body == ""
        assert not hasattr(skill, "transfer_on")


def test_agent_without_transfer_on_loads_empty():
    """에이전트도 같은 답 — 키 부재는 빈 목록이다(두 버킷의 답이 같다)."""
    agent = _deser_agent(
        {"kind": "agent", "id": "ag0", "name": "a", "description": "d",
         "fsm": _EMPTY_FSM},
        _Registry(),
    )
    assert type(agent) is AgentDefinition
    assert agent.transfer_on == []
    assert agent.call_agents == []
