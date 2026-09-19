"""외부 플러그인 등록 액션 (WP-C) — 레지스트리 🔌/🧷 탭과 MCP의 **공통 실체**.

여기서 고정하는 것: ① 등록은 미선언 플러그인의 사용 선언까지 **1 undo 단위**로
한다 ② 이름은 마이그레이션과 같은 규칙으로 짓고 충돌하면 플러그인 이름을 붙인다
③ 같은 정본을 두 번(또는 다른 역할로) 등록하면 **거절**한다(역할 고정, 사용자
확정 2026-09-19) ④ `skills` 칸이 없는 종류에는 스킬 참조를 붙일 수 없다.
"""
from __future__ import annotations

import pytest

from daedalus.model.project import PluginProject

_SOURCE = "hookify@mkt:doctor"


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    win = MainWindow()
    win.set_project(PluginProject(name="p"))
    yield win
    win.close()


def _register(window, source=_SOURCE, kind="external_fork_agent", **kw):
    from daedalus.view.actions.external_registration import (
        register_external_agent,
    )

    return register_external_agent(window, source, kind, **kw)


# ── 등록 + 자동 사용 선언 ────────────────────────────────────────────────

def test_registration_declares_the_plugin_in_the_same_undo_step(window):
    component = _register(window)
    project = window._project
    assert component.config.source == _SOURCE
    assert component.name == "doctor"
    assert project.external_plugins == ["hookify@mkt"]
    window._project_vm.command_stack.undo()
    assert project.agents == []
    assert project.external_plugins == []


def test_already_declared_plugin_is_not_declared_twice(window):
    """선언은 `plugin_ids_match`로 본다 — bare 선언에 마켓 정본을 등록해도
    중복 선언을 만들지 않는다(같은 플러그인이다)."""
    window._project.external_plugins.append("hookify")
    _register(window)
    assert window._project.external_plugins == ["hookify"]


def test_broken_source_declares_nothing_but_still_registers(window):
    """콜론이 없는 정본은 선언할 플러그인을 알 수 없다 — 지어내지 않는다.

    (검증의 `external_source_missing`이 고칠 자리를 말한다.)
    """
    component = _register(window, source="hookify")
    assert component.config.source == "hookify"
    assert window._project.external_plugins == []


# ── 이름 ─────────────────────────────────────────────────────────────────

def test_name_collision_falls_back_to_the_plugin_prefixed_name(window):
    _register(window, source="other@mkt:doctor", kind="external_agent")
    second = _register(window)
    assert [a.name for a in window._project.agents] == [
        "doctor", "hookify-doctor",
    ]
    assert second.name == "hookify-doctor"


def test_colons_in_the_ref_name_become_dashes(window):
    """하위 폴더 에이전트(`review:security`)도 이름 규약을 지킨다."""
    component = _register(window, source="hookify@mkt:review:security")
    assert component.name == "review-security"


def test_an_explicit_name_wins(window):
    assert _register(window, name="my-critic").name == "my-critic"


# ── 역할 고정 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "second_kind", ["external_agent", "external_fork_agent"]
)
def test_the_same_source_cannot_be_registered_twice(window, second_kind):
    _register(window, kind="external_agent")
    with pytest.raises(ValueError) as excinfo:
        _register(window, kind=second_kind)
    message = str(excinfo.value)
    assert "doctor" in message and "역할" in message
    assert len(window._project.agents) == 1


def test_the_role_conflict_check_ignores_marketplace_notation(window):
    _register(window, source="hookify:doctor", kind="external_agent")
    with pytest.raises(ValueError, match="이미"):
        _register(window, source="hookify@mkt:doctor")


def test_a_kind_without_an_external_source_is_refused(window):
    with pytest.raises(ValueError) as excinfo:
        _register(window, kind="fork_agent")
    assert "external_agent" in str(excinfo.value)
    assert window._project.agents == []


def test_an_empty_source_is_refused(window):
    with pytest.raises(ValueError, match="비어"):
        _register(window, source="  ")


# ── 🧷 스킬 참조 붙이기 ─────────────────────────────────────────────────

def _fork_agent(window, name="worker"):
    from daedalus.view.actions.creation import make_component

    agent = make_component(window, "fork_agent", name)
    window._register_component(agent)
    return agent


def test_adding_a_skill_ref_is_undoable(window):
    from daedalus.view.actions.external_registration import add_skill_ref_to_agent

    agent = _fork_agent(window)
    assert add_skill_ref_to_agent(window, agent, "hookify:review") is True
    assert agent.config.skills == ["hookify:review"]
    window._project_vm.command_stack.undo()
    assert agent.config.skills == []


def test_adding_the_same_ref_twice_stacks_no_command(window):
    from daedalus.view.actions.external_registration import add_skill_ref_to_agent

    agent = _fork_agent(window)
    add_skill_ref_to_agent(window, agent, "hookify:review")
    depth = len(window._project_vm.command_stack._undo_stack)
    assert add_skill_ref_to_agent(window, agent, "hookify:review") is False
    assert len(window._project_vm.command_stack._undo_stack) == depth


def test_external_source_agents_have_no_skills_slot(window):
    from daedalus.view.actions.external_registration import add_skill_ref_to_agent

    external = _register(window)
    with pytest.raises(ValueError, match="skills"):
        add_skill_ref_to_agent(window, external, "hookify:review")
