"""종류 → 프론트매터 표 어댑터 + 종류 전환 뒤의 폼 (WP-FK2 D).

세 가지를 고정한다:
1. 표를 고르는 규칙의 **실체는 모델**이다 — 뷰의 `kind_matrix`는 위젯 표만
   덧붙이는 어댑터라, 어느 종류든 컴파일러·MCP와 같은 표를 본다.
2. 알 수 없는 종류는 **이유를 말하는 실패**다(조용한 빈 폼 금지 — 그 회귀가
   실제로 있었다).
3. 종류를 바꾸면 열린 편집 탭의 폼이 재생성되고, 스테일 위젯의 뒤늦은
   write-back은 **유령 속성을 만들지 않는다**.
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import AgentDefinition, ForkAgent
from daedalus.model.plugin.enums import AgentField, SkillField
from daedalus.model.plugin.field_matrix import matrix_for as model_matrix_for
from daedalus.model.plugin.skill import ProceduralSkill, SyncForkSkill
from daedalus.model.project import PluginProject
from daedalus.view.editors.kind_matrix import matrix_for


def _fsm(name: str) -> StateMachine:
    s = SimpleState(name="s")
    return StateMachine(name=f"{name}_fsm", states=[s], initial_state=s)


def _procedural(name: str = "step") -> ProceduralSkill:
    return ProceduralSkill(fsm=_fsm(name), name=name, description="d")


def _sync_fork(name: str = "scout") -> SyncForkSkill:
    return SyncForkSkill(fsm=_fsm(name), name=name, description="d")


def _agent(name: str = "worker") -> AgentDefinition:
    return AgentDefinition(fsm=_fsm(name), name=name, description="d")


# --- 어댑터 ---


@pytest.mark.parametrize(
    "factory", [_procedural, _sync_fork, _agent, lambda: ForkAgent(name="helper", description="d")]
)
def test_rules_are_the_model_matrix(qapp, factory):
    """뷰가 자기 표를 따로 들지 않는다 — 모델의 표 그대로다."""
    component = factory()
    rules, _widgets, _is_agent = matrix_for(component)
    assert rules == model_matrix_for(component)


def test_agent_flag_and_widget_map_follow_the_kind(qapp):
    from daedalus.view.editors.field_widgets import AGENT_FIELD_WIDGETS, FIELD_WIDGETS

    rules, widgets, is_agent = matrix_for(ForkAgent(name="helper", description="d"))
    assert is_agent is True
    assert widgets is AGENT_FIELD_WIDGETS
    # fork 에이전트 표에는 두 행이 없다(스킬이 background를 정하고, isolation은
    # fork 실행에 적용되지 않는다).
    assert AgentField.BACKGROUND not in rules
    assert AgentField.ISOLATION not in rules

    rules, widgets, is_agent = matrix_for(_sync_fork())
    assert is_agent is False
    assert widgets is FIELD_WIDGETS
    assert SkillField.AGENT in rules


def test_unknown_kind_says_why(qapp):
    """조용한 빈 폼이 아니라 이유를 말하는 실패."""

    class _Config:
        kind = "nonsense"

    class _Thing:
        name = "x"
        config = _Config()

    with pytest.raises(ValueError, match="nonsense"):
        matrix_for(_Thing())


# --- 종류 전환 뒤의 폼 ---


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    win = MainWindow()
    win.set_project(PluginProject(name="p", skills=[_procedural("init")]))
    yield win
    win.close()


def _skill(window, name: str = "init"):
    return next(s for s in window._project.skills if s.name == name)


def _editor_of_open_tab(window, component):
    return getattr(window._tabs.widget(window._open_tabs[component.id]), "_editor")


def test_converting_rebuilds_the_open_frontmatter_form(window):
    """전환은 열린 탭의 폼을 재생성한다 — "탭을 닫았다 여세요"가 아니다."""
    from daedalus.view.actions.fork_skill import convert_skill_kind

    skill = _skill(window)
    window._open_component(skill)
    editor = _editor_of_open_tab(window, skill)
    before = editor._fm
    body_before = editor._content_panel
    assert SkillField.AGENT not in before._field_widgets

    convert_skill_kind(window, skill, "sync_fork")

    after = editor._fm
    assert after is not before
    # fork 종류의 표가 그려졌다 — agent 행이 생기고 allowed_tools는 사라진다.
    assert SkillField.AGENT in after._field_widgets
    assert SkillField.ALLOWED_TOOLS not in after._field_widgets
    # 탭도 본문도 그대로다 — 편집 중인 문서·커서를 날리지 않는다.
    assert window._open_tabs[skill.id] == window._tabs.indexOf(
        window._tabs.widget(window._open_tabs[skill.id])
    )
    assert editor._content_panel is body_before


def test_rebuilt_form_still_reports_renames(window):
    """새 폼이 renamed를 못 내면 참조 갱신이 조용히 끊긴다."""
    from daedalus.view.actions.fork_skill import convert_skill_kind

    skill = _skill(window)
    window._open_component(skill)
    convert_skill_kind(window, skill, "sync_fork")

    fm = _editor_of_open_tab(window, skill)._fm
    fm._w_name.setText("renamed")
    fm._save_name()
    assert skill.name == "renamed"
    assert [s.name for s in window._project.skills] == ["renamed"]


def test_converting_with_no_open_tab_is_safe(window):
    from daedalus.view.actions.fork_skill import convert_skill_kind

    skill = _skill(window)
    assert convert_skill_kind(window, skill, "async_fork")["changed"] is True
    assert skill.id not in window._open_tabs


def test_stale_widget_write_back_creates_no_ghost_attribute(window):
    """전환 전에 만든 폼이 뒤늦게 써도 없는 필드를 만들지 않는다.

    유령 속성이 생기면 "config에 없으면 자동 비수정"을 기대는 설계(MCP
    `set_component_field`의 hasattr 게이트, FIXED 필드 비노출)가 무력해지고,
    저장 한 번에 조용히 사라진다(원칙 5).
    """
    from daedalus.view.actions.fork_skill import convert_skill_kind
    from daedalus.view.editors.skill_editor import _FrontmatterPanel

    skill = _skill(window)
    convert_skill_kind(window, skill, "sync_fork")
    stale = _FrontmatterPanel(skill, project_vm=window._project_vm)

    convert_skill_kind(window, skill, "procedural")
    stale._write_field(SkillField.AGENT, "Explore")

    assert not hasattr(skill.config, "agent")


def test_stale_optional_clear_creates_no_ghost_attribute(window):
    """OPTIONAL 행 해제(기본값 리셋) 경로도 같은 가드를 지난다."""
    from daedalus.view.actions.fork_skill import convert_skill_kind
    from daedalus.view.editors.skill_editor import _FrontmatterPanel

    skill = _skill(window)
    convert_skill_kind(window, skill, "sync_fork")
    stale = _FrontmatterPanel(skill, project_vm=window._project_vm)

    convert_skill_kind(window, skill, "procedural")
    stale._on_optional_toggled(SkillField.AGENT, False)

    assert not hasattr(skill.config, "agent")


# --- 전환 undo (2026-09-18 리뷰) ---


def _fm_fields(window, component) -> set:
    return set(_editor_of_open_tab(window, component)._fm._field_widgets)


def test_undoing_a_conversion_rebuilds_the_form_too(window):
    """되돌리면 폼도 되돌아온다 — 버튼이 "Ctrl+Z로 되돌림"이라고 말한다.

    재동기를 액션 함수에 두면 전환에만 걸리고 undo에는 걸리지 않아, 되돌린
    뒤에도 전환 후의 표로 그려진 폼이 남는다. 그 폼의 write-back은 스테일
    가드가 조용히 버리므로 "편집이 먹지 않는 탭"이 된다(원칙 5).
    """
    from daedalus.view.actions.fork_skill import convert_skill_kind

    skill = _skill(window)
    window._open_component(skill)
    before = _fm_fields(window, skill)
    assert SkillField.ALLOWED_TOOLS in before and SkillField.AGENT not in before

    convert_skill_kind(window, skill, "sync_fork")
    assert SkillField.AGENT in _fm_fields(window, skill)

    window._project_vm.command_stack.undo()

    assert skill.config.kind == "procedural"
    # 폼이 다시 모델의 표를 말한다 — 위젯이 그려진 필드 집합이 표의 부분집합이고
    # 전환 전과 같다.
    assert _fm_fields(window, skill) == before
    assert set(model_matrix_for(skill)) >= _fm_fields(window, skill)


def test_undone_form_writes_back_again(window):
    """되돌린 뒤의 폼은 **쓸 수 있다** — 가드가 삼키던 자리다."""
    from daedalus.view.actions.fork_skill import convert_skill_kind

    skill = _skill(window)
    window._open_component(skill)
    convert_skill_kind(window, skill, "sync_fork")
    window._project_vm.command_stack.undo()

    fm = _editor_of_open_tab(window, skill)._fm
    fm._write_field(SkillField.ALLOWED_TOOLS, ["Read"])
    assert skill.config.allowed_tools == ["Read"]


def test_undoing_a_conversion_resyncs_the_registry(window):
    """레지스트리도 같은 커맨드로 돌아온다 — 화면 하나만 되돌아가면 안 된다."""
    from daedalus.view.actions.fork_skill import convert_skill_kind

    skill = _skill(window)
    panel = window._registry_panel
    convert_skill_kind(window, skill, "sync_fork")
    assert panel._sections["sync_fork"]._list.count() == 1
    assert panel._sections["procedural"]._list.count() == 0

    window._project_vm.command_stack.undo()

    assert panel._sections["sync_fork"]._list.count() == 0
    assert panel._sections["procedural"]._list.count() == 1


def test_redo_puts_the_form_back_on_the_new_kind(window):
    from daedalus.view.actions.fork_skill import convert_skill_kind

    skill = _skill(window)
    window._open_component(skill)
    convert_skill_kind(window, skill, "async_fork")
    window._project_vm.command_stack.undo()
    window._project_vm.command_stack.redo()

    assert skill.config.kind == "async_fork"
    assert SkillField.AGENT in _fm_fields(window, skill)


# --- 가드는 두 부재를 가른다 ---


def test_matrix_config_mismatch_says_why(window, monkeypatch):
    """표에는 있는데 config에 없는 필드 = 모델 버그 → 이유를 말하고 죽는다.

    스테일 위젯(이 종류의 표에 **없는** 필드)과 같은 취급을 하면, 표가 선언한
    편집 가능 행이 조용히 먹통이 된다(원칙 5).
    """
    from daedalus.model.plugin.enums import FieldVisibility
    from daedalus.model.plugin.field_matrix import SKILL_FIELD_MATRIX, FieldRule
    from daedalus.view.editors.skill_editor import _FrontmatterPanel

    skill = _skill(window)
    panel = _FrontmatterPanel(skill, project_vm=window._project_vm)
    monkeypatch.setitem(
        SKILL_FIELD_MATRIX["procedural"],
        SkillField.AGENT,
        FieldRule(FieldVisibility.OPTIONAL),
    )

    with pytest.raises(AttributeError, match="agent"):
        panel._write_field(SkillField.AGENT, "Explore")
    assert not hasattr(skill.config, "agent")
