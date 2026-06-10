# tests/view/editors/test_skill_editor.py
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QFrame, QScrollArea, QWidget

from daedalus.model.fsm.section import Section


def _make_procedural():
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.plugin.skill import ProceduralSkill
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    return ProceduralSkill(fsm=fsm, name="TestSkill", description="테스트")


def _make_declarative():
    from daedalus.model.plugin.skill import DeclarativeSkill
    return DeclarativeSkill(name="Knowledge", description="배경지식")


def _make_agent():
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.plugin.agent import AgentDefinition
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    return AgentDefinition(fsm=fsm, name="TestAgent", description="에이전트")


def test_frontmatter_panel_procedural(qapp):
    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    comp = _make_procedural()
    panel = _FrontmatterPanel(comp)
    assert isinstance(panel, QScrollArea)


def test_frontmatter_panel_declarative(qapp):
    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    comp = _make_declarative()
    panel = _FrontmatterPanel(comp)
    assert isinstance(panel, QScrollArea)


def test_frontmatter_panel_agent(qapp):
    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    comp = _make_agent()
    panel = _FrontmatterPanel(comp)
    assert isinstance(panel, QScrollArea)


def test_transfer_on_panel_procedural(qapp):
    from daedalus.view.editors.skill_editor import _TransferOnPanel
    from daedalus.model.fsm.section import EventDef
    events = [EventDef("done"), EventDef("error", color="#cc3333")]
    panel = _TransferOnPanel(events)
    assert isinstance(panel, QWidget)


def test_event_card_renders(qapp):
    from daedalus.view.editors.skill_editor import _EventCard
    from daedalus.model.fsm.section import EventDef
    e = EventDef("done", color="#4488ff")
    card = _EventCard(e, can_delete=False)
    assert isinstance(card, QFrame)


def test_skill_editor_procedural_smoke(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    comp = _make_procedural()
    editor = SkillEditor(comp)
    assert isinstance(editor, QWidget)


def test_skill_editor_declarative_smoke(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    comp = _make_declarative()
    editor = SkillEditor(comp)
    assert isinstance(editor, QWidget)


def test_skill_editor_agent_smoke(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    comp = _make_agent()
    editor = SkillEditor(comp)
    assert isinstance(editor, QWidget)


def test_skill_editor_changed_signal_exists(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    comp = _make_procedural()
    editor = SkillEditor(comp)
    assert hasattr(editor, "skill_changed")


def test_skill_editor_has_splitter(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    from PyQt6.QtWidgets import QSplitter
    comp = _make_procedural()
    editor = SkillEditor(comp)
    splitter = editor.findChild(QSplitter)
    assert splitter is not None


def test_skill_editor_has_breadcrumb(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    from daedalus.view.editors.body_editor import BreadcrumbNav
    comp = _make_procedural()
    comp.sections = [Section("S1"), Section("S2")]
    editor = SkillEditor(comp)
    nav = editor.findChild(BreadcrumbNav)
    assert nav is not None


def test_skill_editor_has_section_tree(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    from daedalus.view.editors.body_editor import SectionTree
    comp = _make_procedural()
    editor = SkillEditor(comp)
    tree = editor.findChild(SectionTree)
    assert tree is not None


def test_frontmatter_panel_transfer(qapp):
    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.plugin.skill import TransferSkill
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    comp = TransferSkill(fsm=fsm, name="Validate", description="검증")
    panel = _FrontmatterPanel(comp)
    assert isinstance(panel, QScrollArea)


def test_skill_editor_transfer_smoke(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.plugin.skill import TransferSkill
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    comp = TransferSkill(fsm=fsm, name="Validate", description="검증")
    editor = SkillEditor(comp)  # must not raise
    from PyQt6.QtWidgets import QWidget
    assert isinstance(editor, QWidget)


def test_node_item_port_color_from_event_def(qapp):
    """EventDef.color가 StateNodeItem 포트 색상에 반영되는지 확인."""
    from PyQt6.QtGui import QColor
    from daedalus.model.fsm.section import EventDef
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.plugin.skill import ProceduralSkill
    from daedalus.view.viewmodel.state_vm import StateViewModel
    from daedalus.view.canvas.node_item import StateNodeItem

    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    skill = ProceduralSkill(
        fsm=fsm, name="ColorSkill", description="d",
        transfer_on=[EventDef("done", color="#aa44cc"), EventDef("error", color="#cc3333")],
    )
    state = SimpleState(name="node", skill_ref=skill)
    vm = StateViewModel(model=state)
    item = StateNodeItem(vm)

    defs = item._event_defs()
    assert len(defs) == 2
    assert defs[0].color == "#aa44cc"
    assert defs[1].color == "#cc3333"
    assert QColor(defs[0].color).isValid()
    assert QColor(defs[1].color).isValid()
    assert item._output_events() == ["done", "error"]


def test_node_item_entry_point_style(qapp):
    from daedalus.view.canvas.node_item import _TYPE_STYLE
    assert "entry_point" in _TYPE_STYLE


def test_node_item_exit_point_style(qapp):
    from daedalus.view.canvas.node_item import _TYPE_STYLE
    assert "exit_point" in _TYPE_STYLE


def test_entry_point_no_input_port(qapp):
    from PyQt6.QtCore import QPointF
    from daedalus.model.fsm.pseudo import EntryPoint
    from daedalus.view.viewmodel.state_vm import StateViewModel
    from daedalus.view.canvas.node_item import StateNodeItem
    vm = StateViewModel(model=EntryPoint(name="entry"))
    item = StateNodeItem(vm)
    assert item._is_entry_point()
    assert not item.is_input_port(QPointF(0.0, 30.0))


def test_exit_point_no_output_port(qapp):
    from PyQt6.QtCore import QPointF
    from daedalus.model.fsm.pseudo import ExitPoint
    from daedalus.view.viewmodel.state_vm import StateViewModel
    from daedalus.view.canvas.node_item import StateNodeItem
    vm = StateViewModel(model=ExitPoint(name="exit"))
    item = StateNodeItem(vm)
    assert item._is_exit_point()
    assert item._get_output_port_event(QPointF(160.0, 50.0)) is None


# ---------------------------------------------------------------------------
# Write-back + load bug tests (감사 1-2)
# ---------------------------------------------------------------------------

def test_when_to_use_loads_into_panel(qapp):
    """when_to_use가 패널에 로드된다 (감사 1-2 로드 버그)."""
    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    from daedalus.model.plugin.enums import SkillField
    from PyQt6.QtWidgets import QTextEdit, QLineEdit
    comp = _make_procedural()
    comp.when_to_use = "복잡한 작업에 사용하세요"
    panel = _FrontmatterPanel(comp)

    widget = panel._field_widgets.get(SkillField.WHEN_TO_USE)
    assert widget is not None, "when_to_use 위젯이 _field_widgets에 없음"
    if isinstance(widget, QTextEdit):
        text = widget.toPlainText()
    else:
        text = widget.text()
    assert text == "복잡한 작업에 사용하세요", f"when_to_use 로드 실패: {text!r}"


def test_combo_field_writes_back_to_config(qapp):
    """model 콤보 변경이 config.model에 반영된다."""
    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    from daedalus.model.plugin.enums import SkillField, ModelType
    from PyQt6.QtWidgets import QComboBox
    comp = _make_procedural()
    panel = _FrontmatterPanel(comp)

    widget = panel._field_widgets.get(SkillField.MODEL)
    assert widget is not None and isinstance(widget, QComboBox), "model 콤보 위젯 없음"
    widget.setCurrentText("opus")

    assert comp.config.model == ModelType.OPUS, (
        f"config.model이 업데이트되지 않음: {comp.config.model!r}"
    )


def test_checkbox_field_writes_back(qapp):
    """bool 필드(disable_model_invocation) 토글이 config에 반영된다."""
    from daedalus.view.editors.skill_editor import _FrontmatterPanel, _OptionalRow
    from daedalus.model.plugin.enums import SkillField
    from PyQt6.QtWidgets import QCheckBox
    comp = _make_procedural()
    panel = _FrontmatterPanel(comp)

    widget = panel._field_widgets.get(SkillField.DISABLE_MODEL)
    assert widget is not None and isinstance(widget, QCheckBox), "disable_model 체크박스 없음"

    # _OptionalRow 안에 있으면 먼저 활성화
    parent = widget.parent()
    if isinstance(parent, _OptionalRow):
        parent.set_checked(True)

    widget.setChecked(True)
    assert comp.config.disable_model_invocation is True, (
        f"disable_model_invocation이 True로 반영되지 않음: {comp.config.disable_model_invocation!r}"
    )


def test_tag_field_writes_back(qapp):
    """list 필드(allowed_tools) 변경이 config에 반영된다."""
    from daedalus.view.editors.skill_editor import _FrontmatterPanel, _OptionalRow
    from daedalus.model.plugin.enums import SkillField
    from daedalus.view.widgets.tag_input import TagInput
    comp = _make_procedural()
    panel = _FrontmatterPanel(comp)

    widget = panel._field_widgets.get(SkillField.ALLOWED_TOOLS)
    assert widget is not None and isinstance(widget, TagInput), "allowed_tools TagInput 없음"

    # _OptionalRow 안에 있으면 활성화
    parent = widget.parent()
    if isinstance(parent, _OptionalRow):
        parent.set_checked(True)

    widget.add_tag("Bash")
    assert "Bash" in comp.config.allowed_tools, (
        f"allowed_tools에 'Bash' 없음: {comp.config.allowed_tools!r}"
    )


def test_optional_row_uncheck_clears_value(qapp):
    """_OptionalRow 해제 시 config 값이 None/[]로 클리어된다."""
    from daedalus.view.editors.skill_editor import _FrontmatterPanel, _OptionalRow
    from daedalus.model.plugin.enums import SkillField
    comp = _make_procedural()
    comp.config.effort = __import__("daedalus.model.plugin.enums", fromlist=["EffortLevel"]).EffortLevel.HIGH
    panel = _FrontmatterPanel(comp)

    # effort는 OPTIONAL — _OptionalRow로 감싸져 있어야 함
    effort_widget = panel._field_widgets.get(SkillField.EFFORT)
    assert effort_widget is not None, "effort 위젯 없음"

    # _OptionalRow 컨테이너 찾기
    parent = effort_widget.parent()
    assert isinstance(parent, _OptionalRow), "effort 위젯이 _OptionalRow 안에 없음"

    # 체크 해제
    parent.set_checked(False)
    assert comp.config.effort is None, (
        f"effort가 None으로 클리어되지 않음: {comp.config.effort!r}"
    )


def test_user_invocable_uncheck_restores_declared_default(qapp):
    """non-Optional 필드(user_invocable: bool = True)는 행 해제 시 None이 아닌
    dataclass 선언 기본값으로 리셋된다 (Issue 1)."""
    from daedalus.view.editors.skill_editor import _FrontmatterPanel, _OptionalRow
    from daedalus.model.plugin.enums import SkillField
    comp = _make_procedural()
    assert comp.config.user_invocable is True  # 선언 기본값
    panel = _FrontmatterPanel(comp)

    widget = panel._field_widgets.get(SkillField.USER_INVOCABLE)
    assert widget is not None, "user_invocable 위젯 없음"
    parent = widget.parent()
    assert isinstance(parent, _OptionalRow), "user_invocable이 _OptionalRow 안에 없음"

    parent.set_checked(False)
    assert comp.config.user_invocable is True, (
        f"user_invocable이 선언 기본값(True)으로 리셋되지 않음: "
        f"{comp.config.user_invocable!r}"
    )


def test_optional_recheck_restores_widget_value(qapp):
    """행 해제 → 재체크 시 위젯 표시값이 config에 복원된다 (Issue 2)."""
    from daedalus.view.editors.skill_editor import _FrontmatterPanel, _OptionalRow
    from daedalus.model.plugin.enums import EffortLevel, SkillField
    comp = _make_procedural()
    comp.config.effort = EffortLevel.HIGH
    panel = _FrontmatterPanel(comp)

    widget = panel._field_widgets[SkillField.EFFORT]
    parent = widget.parent()
    assert isinstance(parent, _OptionalRow)
    assert widget.currentText() == "high"  # 로드 확인

    # 해제: 선언 기본값(None)으로 클리어, 위젯은 여전히 "high" 표시
    parent.set_checked(False)
    assert comp.config.effort is None
    assert widget.currentText() == "high"

    # 재체크: 위젯 표시값이 모델에 복원되어야 함
    parent.set_checked(True)
    assert comp.config.effort == EffortLevel.HIGH, (
        f"재체크 시 위젯 값이 복원되지 않음: {comp.config.effort!r}"
    )


def test_paths_writes_back_as_list(qapp):
    """PATHS(TagInput) 입력이 list[str]로 config.paths에 기록된다 (결함 1 + WP-E TagInput 전환).

    TagInput은 칩 단위라 공백을 포함한 경로도 단일 항목으로 표현 가능하다 —
    이전 QLineEdit + 공백 split의 표현 한계를 해소한다.
    """
    from daedalus.view.editors.skill_editor import _FrontmatterPanel, _OptionalRow
    from daedalus.model.plugin.enums import SkillField
    from daedalus.view.widgets.tag_input import TagInput
    comp = _make_procedural()
    panel = _FrontmatterPanel(comp)

    widget = panel._field_widgets.get(SkillField.PATHS)
    assert widget is not None and isinstance(widget, TagInput), "paths TagInput 없음"

    parent = widget.parent()
    if isinstance(parent, _OptionalRow):
        parent.set_checked(True)

    widget.add_tag("docs/a.md")
    widget.add_tag("docs/b.md")
    assert comp.config.paths == ["docs/a.md", "docs/b.md"], (
        f"paths가 list로 기록되지 않음: {comp.config.paths!r}"
    )

    # 공백 포함 경로도 단일 항목으로 보존된다
    widget.add_tag("My Documents/c.md")
    assert "My Documents/c.md" in comp.config.paths, (
        f"공백 포함 경로가 보존되지 않음: {comp.config.paths!r}"
    )

    # 전부 제거하면 빈 리스트로
    widget.remove_tag("docs/a.md")
    widget.remove_tag("docs/b.md")
    widget.remove_tag("My Documents/c.md")
    assert comp.config.paths == [], f"빈 입력이 []가 아님: {comp.config.paths!r}"


def test_hooks_load_into_picker_and_toggle_keeps_dict(qapp, tmp_path, monkeypatch):
    """hooks dict가 PresetPicker에 로드되고, 토글 후에도 dict 타입이 유지된다 (결함 2)."""
    from daedalus.model.plugin.enums import SkillField
    from daedalus.view.widgets.preset_picker import PresetPicker

    # HookPresetPicker는 cwd 기준 .claude/hooks/*.json을 스캔
    hooks_dir = tmp_path / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "lint.json").write_text("{}", encoding="utf-8")
    (hooks_dir / "fmt.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    comp = _make_procedural()
    comp.config.hooks = {"lint": {"cmd": "ruff"}}
    panel = _FrontmatterPanel(comp)

    picker = panel._field_widgets.get(SkillField.HOOKS)
    assert picker is not None and isinstance(picker, PresetPicker), "hooks PresetPicker 없음"

    # (b-1) 로드: hooks dict의 키가 picker에 선택 상태로 반영
    assert picker.get_selected() == ["lint"], (
        f"hooks 로드 실패: {picker.get_selected()!r}"
    )

    # (b-2) 토글: dict 타입 유지 + 기존 본문 보존
    picker._checkboxes["fmt"].setChecked(True)
    assert isinstance(comp.config.hooks, dict), (
        f"hooks가 dict가 아님: {type(comp.config.hooks)!r}"
    )
    assert set(comp.config.hooks.keys()) == {"lint", "fmt"}, (
        f"hooks 키 불일치: {comp.config.hooks!r}"
    )
    assert comp.config.hooks["lint"] == {"cmd": "ruff"}, (
        f"기존 hook 본문이 보존되지 않음: {comp.config.hooks['lint']!r}"
    )


def test_hooks_optional_uncheck_clears_to_none(qapp, tmp_path, monkeypatch):
    """hooks _OptionalRow 해제 시 []가 아닌 None으로 클리어된다 (dict 필드)."""
    from daedalus.model.plugin.enums import SkillField
    from daedalus.view.editors.skill_editor import _OptionalRow

    hooks_dir = tmp_path / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "lint.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    comp = _make_procedural()
    comp.config.hooks = {"lint": {}}
    panel = _FrontmatterPanel(comp)

    picker = panel._field_widgets[SkillField.HOOKS]
    parent = picker.parent()
    assert isinstance(parent, _OptionalRow)
    parent.set_checked(False)
    assert comp.config.hooks is None, (
        f"hooks가 None으로 클리어되지 않음: {comp.config.hooks!r}"
    )


def test_writeback_survives_panel_rebuild(qapp):
    """write-back된 값이 패널 재생성 후에도 다시 로드된다 (왕복)."""
    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    from daedalus.model.plugin.enums import SkillField, ModelType
    from PyQt6.QtWidgets import QComboBox
    comp = _make_procedural()
    panel = _FrontmatterPanel(comp)

    # 1) write-back: model → haiku
    widget = panel._field_widgets[SkillField.MODEL]
    assert isinstance(widget, QComboBox)
    widget.setCurrentText("haiku")
    assert comp.config.model == ModelType.HAIKU

    # 2) 패널 재생성
    panel2 = _FrontmatterPanel(comp)
    widget2 = panel2._field_widgets[SkillField.MODEL]
    assert isinstance(widget2, QComboBox)
    assert widget2.currentText() == "haiku", (
        f"재생성 후 model 로드 실패: {widget2.currentText()!r}"
    )
