# tests/view/actions/test_fork_skill_kind.py
"""`skill_kind_of` — 전환 가족 판정의 계약 (WP-2d Q17).

전환 메뉴(캔버스 우클릭 "종류 전환"·편집기 종류 전환 줄)·MCP `convert_skill`이
전부 이 함수를 부른다. 조용히 None을 돌려주면 메뉴가 통째로 사라지므로,
판정의 두 축을 고정한다: ① 비교값은 선언(`StepSkill.CONVERT_FAMILY`)에서
읽는가 ② 컴포넌트가 아닌 값에 예외 대신 "대상 아님"으로 답하는가.
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.config import ProceduralSkillConfig
from daedalus.model.plugin.skill import (
    DeclarativeSkill,
    ProceduralSkill,
    StepSkill,
)
from daedalus.view.actions.fork_skill import skill_kind_of


def _fsm() -> StateMachine:
    s = SimpleState(name="s")
    return StateMachine(name="m", states=[s], initial_state=s)


def test_step_skill_reports_its_config_kind():
    skill = ProceduralSkill(
        fsm=_fsm(), name="n", description="d", config=ProceduralSkillConfig(),
    )
    assert skill_kind_of(skill) == "procedural"


def test_family_value_is_read_from_the_declaration(monkeypatch):
    """가족 이름을 바꿔도 판정이 따라온다 — 문자열을 베껴 두면 여기서 깨진다."""
    monkeypatch.setattr(StepSkill, "CONVERT_FAMILY", "renamed-family")
    skill = ProceduralSkill(
        fsm=_fsm(), name="n", description="d", config=ProceduralSkillConfig(),
    )
    assert skill_kind_of(skill) == "procedural"


def test_non_step_skill_is_not_convertible():
    assert skill_kind_of(DeclarativeSkill(name="n", description="d")) is None


@pytest.mark.parametrize("value", [None, "procedural", 7])
def test_non_component_values_answer_not_convertible(value):
    """빈 노드의 `skill_ref`(None)·kind 문자열이 섞여 들어도 예외가 아니다."""
    assert skill_kind_of(value) is None
