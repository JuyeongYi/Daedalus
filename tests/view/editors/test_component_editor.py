# tests/view/editors/test_component_editor.py
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QSplitter, QWidget


def _make_procedural():
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.plugin.skill import ProceduralSkill
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    return ProceduralSkill(fsm=fsm, name="TestSkill", description="d")


def _make_declarative():
    from daedalus.model.plugin.skill import DeclarativeSkill
    return DeclarativeSkill(name="K", description="d")


def _make_agent():
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.plugin.agent import AgentDefinition
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    return AgentDefinition(fsm=fsm, name="TestAgent", description="d")


def test_two_column_no_right_widgets(qapp):
    """right_widgets가 없으면 2컬럼(좌측+중앙)만 존재."""
    from daedalus.view.editors.component_editor import ComponentEditor
    comp = _make_declarative()
    editor = ComponentEditor(comp)
    root_splitter = editor.findChild(QSplitter)
    assert root_splitter is not None
    assert root_splitter.count() == 2  # left + center


def test_three_column_with_right_widgets(qapp):
    """right_widgets가 있으면 3컬럼(좌측+중앙+우측)."""
    from daedalus.view.editors.component_editor import ComponentEditor
    comp = _make_procedural()
    from daedalus.view.editors.skill_editor import _TransferOnPanel
    rw = [_TransferOnPanel(comp.transfer_on)]
    editor = ComponentEditor(comp, right_widgets=rw)
    root_splitter = editor.findChild(QSplitter)
    assert root_splitter is not None
    assert root_splitter.count() == 3  # left + center + right


def test_left_has_frontmatter(qapp):
    """좌측에 FrontmatterPanel이 배치된다 (WP-SB: SectionTree 제거)."""
    from daedalus.view.editors.component_editor import ComponentEditor
    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    comp = _make_procedural()
    editor = ComponentEditor(comp)
    fm = editor.findChild(_FrontmatterPanel)
    assert fm is not None


def test_center_has_content_panel(qapp):
    """중앙에 SectionContentPanel(본문 body 편집)이 배치된다 (WP-SB: BreadcrumbNav 제거)."""
    from daedalus.view.editors.component_editor import ComponentEditor
    from daedalus.view.editors.body_editor import SectionContentPanel
    comp = _make_procedural()
    editor = ComponentEditor(comp)
    cp = editor.findChild(SectionContentPanel)
    assert cp is not None
    assert cp.current_component() is comp


def test_changed_signal(qapp):
    """changed 시그널이 존재."""
    from daedalus.view.editors.component_editor import ComponentEditor
    comp = _make_declarative()
    editor = ComponentEditor(comp)
    assert hasattr(editor, "changed")


def test_right_widgets_in_vertical_splitter(qapp):
    """우측 위젯이 수직 스플리터에 배치."""
    from daedalus.view.editors.component_editor import ComponentEditor
    from daedalus.view.editors.skill_editor import _TransferOnPanel
    comp = _make_procedural()
    t1 = _TransferOnPanel(comp.transfer_on)
    t2 = _TransferOnPanel(comp.call_agents, default_color="#8a4a4a", multiline_desc=True)
    editor = ComponentEditor(comp, right_widgets=[t1, t2])
    splitters = editor.findChildren(QSplitter)
    assert len(splitters) >= 2


def test_on_notify_callback(qapp):
    """on_notify_fn이 모델 변경 시 호출."""
    from daedalus.view.editors.component_editor import ComponentEditor
    comp = _make_declarative()
    called = []
    editor = ComponentEditor(comp, on_notify_fn=lambda: called.append(1))
    editor._on_model_changed()
    assert len(called) == 1


def test_variable_popup_opens_at_button_global_pos(qapp):
    """변수 삽입 팝업은 Qt.Popup 최상위 창 — 버튼의 전역 좌표 바로 아래에 떠야 한다.

    회귀: 패널 상대 좌표를 move()에 넘기면 화면 좌상단 근처에 떴다.
    """
    from PySide6.QtCore import QPoint
    from daedalus.view.editors.component_editor import ComponentEditor
    comp = _make_declarative()
    editor = ComponentEditor(comp)
    editor.show()
    editor._on_variable_insert()
    try:
        btn = editor._content_panel._btn_variable
        expected = btn.mapToGlobal(QPoint(0, btn.height()))
        assert editor._var_popup.pos() == expected
        assert editor._var_popup.isVisible()
    finally:
        editor._var_popup.hide()
        editor.close()


# ---------------------------------------------------------------------------
# notify 채널 분리 — 텍스트 키스트로크가 structure 리스너를 깨우지 않는다
# ---------------------------------------------------------------------------

def test_body_typing_routes_to_content_scope(qapp):
    """본문(body) 타이핑 → ProjectViewModel.notify(scope='content')만 호출.

    structure 리스너(캔버스 _rebuild 등)는 키스트로크마다 돌지 않아야 한다.
    """
    from daedalus.view.viewmodel.project_vm import ProjectViewModel
    comp = _make_declarative()

    pvm = ProjectViewModel()
    struct: list[int] = []
    content: list[int] = []
    pvm.add_listener(lambda: struct.append(1))
    pvm.add_listener(lambda: content.append(1), scope="content")

    from daedalus.view.editors.component_editor import ComponentEditor
    editor = ComponentEditor(comp, on_notify_fn=pvm.notify)

    # 본문 타이핑 시뮬레이션
    editor._content_panel._w_content.setPlainText("타이핑 중")

    assert content == [1], "content 리스너가 호출되어야 한다"
    assert struct == [], "structure 리스너는 본문 타이핑에 호출되면 안 된다"


def test_default_scope_routes_to_structure_scope(qapp):
    """기본 scope(구조 변경)는 structure 채널로 라우팅된다. content 리스너 미호출."""
    from daedalus.view.viewmodel.project_vm import ProjectViewModel
    comp = _make_declarative()

    pvm = ProjectViewModel()
    struct: list[int] = []
    content: list[int] = []
    pvm.add_listener(lambda: struct.append(1))
    pvm.add_listener(lambda: content.append(1), scope="content")

    from daedalus.view.editors.component_editor import ComponentEditor
    editor = ComponentEditor(comp, on_notify_fn=pvm.notify)

    editor._on_model_changed()

    assert struct == [1], "structure 리스너가 호출되어야 한다"
    assert content == [], "content 리스너는 구조 변경에 호출되면 안 된다"


def test_description_typing_routes_to_content_scope(qapp):
    """frontmatter description 타이핑 → content 채널."""
    from daedalus.view.viewmodel.project_vm import ProjectViewModel
    comp = _make_declarative()

    pvm = ProjectViewModel()
    struct: list[int] = []
    content: list[int] = []
    pvm.add_listener(lambda: struct.append(1))
    pvm.add_listener(lambda: content.append(1), scope="content")

    from daedalus.view.editors.component_editor import ComponentEditor
    editor = ComponentEditor(comp, on_notify_fn=pvm.notify)

    editor._fm._w_desc.setPlainText("새 설명")  # textChanged → _save_desc → content_changed

    assert content and content[-1] == 1, "description 타이핑은 content 채널로"
    assert struct == [], "description 타이핑이 structure 리스너를 깨워서는 안 된다"
