# daedalus/view/editors/skill_editor.py
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.fsm.section import EventDef, Section
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill, ReferenceSkill, TransferSkill
from daedalus.model.plugin.enums import (
    AgentColor,
    AgentField,
    AgentIsolation,
    EffortLevel,
    MemoryScope,
    ModelType,
    PermissionMode,
    SkillContext,
    SkillField,
    SkillShell,
)


# ---------------------------------------------------------------------------
# 모듈 수준 상수: SkillField | AgentField → config/component 속성명 매핑
# 로드(load) 경로와 저장(write-back) 경로가 같은 테이블을 공유한다.
# ---------------------------------------------------------------------------
_FIELD_ATTR_MAP: dict[SkillField | AgentField, str] = {
    SkillField.ARGUMENT_HINT: "argument_hint",
    SkillField.MODEL: "model",
    SkillField.EFFORT: "effort",
    SkillField.ALLOWED_TOOLS: "allowed_tools",
    SkillField.CONTEXT: "context",
    SkillField.AGENT: "agent",
    SkillField.SHELL: "shell",
    SkillField.PATHS: "paths",
    SkillField.HOOKS: "hooks",
    SkillField.DISABLE_MODEL: "disable_model_invocation",
    SkillField.USER_INVOCABLE: "user_invocable",
    # AgentField 항목
    AgentField.MODEL: "model",
    AgentField.EFFORT: "effort",
    AgentField.TOOLS: "tools",
    AgentField.DISALLOWED_TOOLS: "disallowed_tools",
    AgentField.PERMISSION_MODE: "permission_mode",
    AgentField.SKILLS: "skills",
    AgentField.MEMORY: "memory",
    AgentField.COLOR: "color",
    AgentField.HOOKS: "hooks",
    AgentField.MAX_TURNS: "max_turns",
    AgentField.BACKGROUND: "background",
    AgentField.ISOLATION: "isolation",
    AgentField.MCP_SERVERS: "mcp_servers",
}

# SkillField | AgentField → 역변환에 사용할 Enum 타입 (str → Enum)
_FIELD_ENUM_MAP: dict[SkillField | AgentField, type] = {
    SkillField.MODEL: ModelType,
    SkillField.EFFORT: EffortLevel,
    SkillField.CONTEXT: SkillContext,
    SkillField.SHELL: SkillShell,
    # AgentField 항목
    AgentField.MODEL: ModelType,
    AgentField.EFFORT: EffortLevel,
    AgentField.PERMISSION_MODE: PermissionMode,
    AgentField.MEMORY: MemoryScope,
    AgentField.ISOLATION: AgentIsolation,
    AgentField.COLOR: AgentColor,
}

# list[str] 타입인 필드 집합 — 선언 기본값(default)이 MISSING일 때 클리어 폴백을 []로 결정.
# 두 필드 모두 TagInput 편집이므로 write-back 값은 항상 list로 들어온다.
# 클리어 자체는 _declared_default가 dataclass 선언 기본값으로 처리하므로
# PATHS(default None)는 자연히 None으로 정규화된다.
# 주의: HOOKS는 dict[str, Any] 필드이므로 여기에 포함하지 않는다.
_LIST_FIELDS: set[SkillField | AgentField] = {
    SkillField.ALLOWED_TOOLS,
    SkillField.PATHS,
    AgentField.TOOLS,
    AgentField.DISALLOWED_TOOLS,
    AgentField.SKILLS,
    AgentField.MCP_SERVERS,
}


_COLOR_PRESETS = [
    "#4488ff", "#cc3333", "#cc8800", "#44aa44",
    "#aa44cc", "#ccaa00", "#44aacc", "#888888",
]


class _OptionalRow(QWidget):
    """체크박스 ON/OFF로 선택적 프론트매터 필드를 표시/비활성화."""

    toggled = pyqtSignal(bool)

    def __init__(
        self,
        label: str,
        widget: QWidget,
        initially_enabled: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(3)

        self._cb = QCheckBox()
        self._cb.setChecked(initially_enabled)
        layout.addWidget(self._cb)

        lbl = QLabel(label)
        layout.addWidget(lbl)

        self._widget = widget
        layout.addWidget(widget, 1)

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._cb.toggled.connect(self._update_state)
        self._update_state(initially_enabled)

    def _update_state(self, checked: bool) -> None:
        self._widget.setEnabled(checked)
        self._opacity.setOpacity(1.0 if checked else 0.4)
        self.toggled.emit(checked)

    def is_checked(self) -> bool:
        return self._cb.isChecked()

    def set_checked(self, checked: bool) -> None:
        self._cb.setChecked(checked)


class _FrontmatterPanel(QScrollArea):
    """좌측 패널 — SKILL_FIELD_MATRIX 기반 프론트매터 편집."""

    changed = pyqtSignal()
    # 텍스트 키스트로크 전용 채널 — description / when_to_use 타이핑.
    # 무거운 structure 리스너를 우회하기 위해 별도 시그널로 분리한다.
    content_changed = pyqtSignal()
    # 이름 변경 시 발화 — (component, old_name, new_name). 중복 방지 및 참조 갱신용.
    renamed = pyqtSignal(object, str, str)

    def __init__(
        self,
        component: ProceduralSkill | DeclarativeSkill | TransferSkill | ReferenceSkill | AgentDefinition,
        skill_kind: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._component = component
        self._field_widgets: dict[SkillField | AgentField, QWidget] = {}
        self._loading = False  # 로드 중 write-back 핸들러 억제용 가드

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(3)

        lay.addWidget(QLabel("Frontmatter"))

        # name (필수, 항상 표시)
        lay.addWidget(QLabel("name *"))
        self._w_name = QLineEdit(component.name)
        self._w_name.editingFinished.connect(self._save_name)
        lay.addWidget(self._w_name)

        # description (필수, 항상 표시)
        lay.addWidget(QLabel("description *"))
        self._w_desc = QTextEdit()
        self._w_desc.setPlainText(component.description)
        self._w_desc.setFixedHeight(44)
        self._w_desc.textChanged.connect(self._save_desc)
        lay.addWidget(self._w_desc)

        # SKILL_FIELD_MATRIX / AGENT_FIELD_MATRIX 기반 필드 생성
        # 위젯 클래스는 view 측 FIELD_WIDGETS / AGENT_FIELD_WIDGETS에서 조회한다(model→view 의존 역전).
        from daedalus.model.plugin.field_matrix import AGENT_FIELD_MATRIX, SKILL_FIELD_MATRIX
        from daedalus.model.plugin.enums import FieldEmit, FieldVisibility
        from daedalus.view.editors.field_widgets import AGENT_FIELD_WIDGETS, FIELD_WIDGETS

        kind = skill_kind or self._detect_kind(component)
        config = getattr(component, "config", None)

        is_agent = kind == "agent"
        if is_agent:
            rules = AGENT_FIELD_MATRIX  # type: ignore[assignment]
            widget_map = AGENT_FIELD_WIDGETS  # type: ignore[assignment]
        else:
            rules = SKILL_FIELD_MATRIX.get(kind, {})  # type: ignore[assignment]
            widget_map = FIELD_WIDGETS  # type: ignore[assignment]

        self._loading = True
        try:
            skip = {SkillField.NAME, SkillField.DESCRIPTION}
            if is_agent:
                skip = {AgentField.NAME, AgentField.DESCRIPTION}  # type: ignore[assignment]

            # 에이전트는 emit 그룹 순서(FRONTMATTER → INVOCATION → SETTINGS)로
            # 정렬해 렌더링한다. 매트릭스 선언 순서에 의존하면 그룹 라벨과
            # 필드가 어긋날 수 있다 (예: SETTINGS 필드가 Invocation 라벨 아래 표시).
            items = list(rules.items())
            if is_agent:
                group_order = {
                    FieldEmit.FRONTMATTER: 0,
                    FieldEmit.BODY: 0,
                    FieldEmit.INVOCATION: 1,
                    FieldEmit.SETTINGS: 2,
                }
                items.sort(key=lambda kv: group_order[kv[1].emit])  # stable — 그룹 내 선언 순서 유지
            current_group: FieldEmit | None = None

            for fld, rule in items:
                if fld in skip:
                    continue
                if rule.visibility == FieldVisibility.FIXED:
                    continue
                if fld not in widget_map:
                    continue

                # emit 그룹 전환 시 구분 라벨 (에이전트 전용)
                if (
                    is_agent
                    and rule.emit in (FieldEmit.INVOCATION, FieldEmit.SETTINGS)
                    and rule.emit is not current_group
                ):
                    title = "Invocation" if rule.emit is FieldEmit.INVOCATION else "Settings"
                    lay.addWidget(QLabel(f"— {title} —"))
                    current_group = rule.emit

                widget = widget_map[fld]()
                self._apply_value(widget, config, component, fld, rule)
                self._field_widgets[fld] = widget
                self._connect_widget_signal(fld, widget)

                if rule.visibility == FieldVisibility.REQUIRED:
                    from PyQt6.QtWidgets import QComboBox as _QCB
                    if isinstance(widget, _QCB):
                        row = QHBoxLayout()
                        row.addWidget(QLabel(fld.value))
                        row.addWidget(widget, 1)
                        lay.addLayout(row)
                    else:
                        lay.addWidget(QLabel(fld.value))
                        lay.addWidget(widget)
                elif rule.visibility == FieldVisibility.OPTIONAL:
                    current = self._get_current(config, component, fld)
                    enabled = current is not None and current != "" and current != [] and current is not False
                    opt_row = _OptionalRow(fld.value, widget, initially_enabled=enabled)
                    # _OptionalRow 해제 시 config/component 값 클리어
                    opt_row.toggled.connect(
                        lambda checked, f=fld: self._on_optional_toggled(f, checked)
                    )
                    lay.addWidget(opt_row)
        finally:
            self._loading = False

        lay.addStretch()
        self.setWidget(inner)

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_kind(component: object) -> str:
        config = getattr(component, "config", None)
        if config is not None and hasattr(config, "kind"):
            return config.kind
        return "procedural"

    @staticmethod
    def _get_current(config: object, component: object, fld: SkillField | AgentField) -> object:
        """현재 값을 config 또는 component에서 읽어 반환한다."""
        if fld == SkillField.WHEN_TO_USE:
            return getattr(component, "when_to_use", None)
        attr = _FIELD_ATTR_MAP.get(fld)
        if attr and config is not None:
            return getattr(config, attr, None)
        return None

    @staticmethod
    def _apply_value(widget, config, component, fld: SkillField | AgentField, rule) -> None:
        """현재 값(config / component)을 위젯에 채운다."""
        from PyQt6.QtWidgets import QComboBox, QCheckBox, QLineEdit, QSpinBox, QTextEdit
        from daedalus.view.widgets.tag_input import TagInput
        from daedalus.view.widgets.preset_picker import PresetPicker
        current = _FrontmatterPanel._get_current(config, component, fld)

        if isinstance(widget, QSpinBox):
            # QSpinBox 기본 상한이 99라 max_turns가 잘릴 수 있다.
            # CC의 실제 상한은 컴파일러 WP에서 확정 — 잠정 1~1000.
            widget.setRange(1, 1000)
            widget.setValue(int(current) if current is not None else 1)
        elif isinstance(widget, QComboBox):
            val = None
            if current is not None:
                val = current.value if hasattr(current, "value") else str(current)
            elif rule.default_value is not None:
                # default_value는 enum(ModelType.INHERIT 등) 또는 스칼라.
                dv = rule.default_value
                val = dv.value if hasattr(dv, "value") else str(dv)
            if val is not None:
                idx = widget.findText(val)
                if idx >= 0:
                    widget.setCurrentIndex(idx)
        elif isinstance(widget, QCheckBox):
            widget.setChecked(bool(current) if current is not None else False)
        elif isinstance(widget, TagInput):
            if isinstance(current, list):
                widget.set_tags(current)
        elif isinstance(widget, PresetPicker):
            # hooks: dict[str, Any] — 키 집합 ↔ 선택된 프리셋 이름 목록
            if isinstance(current, dict):
                widget.set_selected(list(current.keys()))
        elif isinstance(widget, QTextEdit):
            if current is not None:
                widget.setPlainText(str(current))
            widget.setFixedHeight(44)
        elif isinstance(widget, QLineEdit):
            if isinstance(current, list):
                widget.setText(" ".join(current) if current else "")
            elif current is not None:
                widget.setText(str(current))

    @staticmethod
    def _read_widget_value(fld: SkillField | AgentField, widget: QWidget) -> object:
        """위젯의 현재 표시값을 추출한다 (시그널 연결과 재체크 복원이 공유)."""
        from PyQt6.QtWidgets import QComboBox, QCheckBox, QLineEdit, QSpinBox, QTextEdit
        from daedalus.view.widgets.tag_input import TagInput
        from daedalus.view.widgets.preset_picker import PresetPicker

        if isinstance(widget, QSpinBox):
            return widget.value()
        if isinstance(widget, QComboBox):
            return widget.currentText()
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, TagInput):
            return widget.get_tags()
        if isinstance(widget, PresetPicker):
            return widget.get_selected()
        if isinstance(widget, QTextEdit):
            return widget.toPlainText()
        if isinstance(widget, QLineEdit):
            return widget.text()
        return None

    def _connect_widget_signal(self, fld: SkillField | AgentField, widget: QWidget) -> None:
        """위젯 타입에 맞는 시그널을 공용 핸들러에 연결한다."""
        from PyQt6.QtWidgets import QComboBox, QCheckBox, QLineEdit, QSpinBox, QTextEdit
        from daedalus.view.widgets.tag_input import TagInput
        from daedalus.view.widgets.preset_picker import PresetPicker

        def handler(*_args, f=fld, w=widget) -> None:
            self._write_field(f, self._read_widget_value(f, w))

        if isinstance(widget, QSpinBox):
            widget.valueChanged.connect(handler)
        elif isinstance(widget, QComboBox):
            widget.currentTextChanged.connect(handler)
        elif isinstance(widget, QCheckBox):
            widget.toggled.connect(handler)
        elif isinstance(widget, TagInput):
            widget.tags_changed.connect(handler)
        elif isinstance(widget, PresetPicker):
            widget.selection_changed.connect(handler)
        elif isinstance(widget, QTextEdit):
            widget.textChanged.connect(handler)
        elif isinstance(widget, QLineEdit):
            widget.editingFinished.connect(handler)

    def _write_field(self, fld: SkillField | AgentField, value: object) -> None:
        """write-back: 위젯 값을 config 또는 component에 기록하고 changed를 emit한다."""
        if self._loading:
            return

        config = getattr(self._component, "config", None)

        if fld == SkillField.WHEN_TO_USE:
            self._component.when_to_use = value  # type: ignore[attr-defined]
            # when_to_use는 텍스트 키스트로크 — content 채널로.
            self.content_changed.emit()
            return

        attr = _FIELD_ATTR_MAP.get(fld)
        if attr is None or config is None:
            return

        # Enum 역변환
        enum_type = _FIELD_ENUM_MAP.get(fld)
        if enum_type is not None and isinstance(value, str):
            try:
                value = enum_type(value)
            except ValueError:
                return  # 알 수 없는 값은 무시

        # hooks: dict[str, Any] 필드 — PresetPicker의 이름 목록을 dict로 변환,
        # 이미 존재하는 키의 본문은 보존
        if fld in (SkillField.HOOKS, AgentField.HOOKS) and isinstance(value, list):
            existing = getattr(config, attr, None)
            existing = existing if isinstance(existing, dict) else {}
            value = {name: existing.get(name, {}) for name in value}

        setattr(config, attr, value)
        self.changed.emit()

    @staticmethod
    def _declared_default(obj: object, attr: str, fld: SkillField | AgentField) -> object:
        """dataclass 선언 기본값(default / default_factory)을 조회한다.

        non-Optional 필드(context, shell, user_invocable 등)에 None을 기록해
        타입 계약을 깨지 않도록, 클리어 값은 선언 기본값으로 결정한다.
        default가 MISSING이면 기존 규칙(None / list 필드는 [])으로 폴백.
        """
        import dataclasses

        if dataclasses.is_dataclass(obj):
            for f in dataclasses.fields(obj):
                if f.name != attr:
                    continue
                if f.default is not dataclasses.MISSING:
                    return f.default
                if f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
                    return f.default_factory()  # type: ignore[misc]
                break
        return [] if fld in _LIST_FIELDS else None

    def _on_optional_toggled(self, fld: SkillField | AgentField, checked: bool) -> None:
        """_OptionalRow 토글 처리.

        - 해제: config/component 값을 dataclass 선언 기본값으로 리셋
        - 재체크: 위젯에 남아있는 표시값을 모델에 복원 (silent divergence 방지)
        """
        if self._loading:
            return

        if checked:
            widget = self._field_widgets.get(fld)
            if widget is not None:
                self._write_field(fld, self._read_widget_value(fld, widget))
            return

        config = getattr(self._component, "config", None)

        if fld == SkillField.WHEN_TO_USE:
            self._component.when_to_use = self._declared_default(  # type: ignore[attr-defined]
                self._component, "when_to_use", fld
            )
            self.changed.emit()
            return

        attr = _FIELD_ATTR_MAP.get(fld)
        if attr is None or config is None:
            return

        setattr(config, attr, self._declared_default(config, attr, fld))
        self.changed.emit()

    def _save_name(self) -> None:
        old_name = self._component.name
        new_name = self._w_name.text().strip()
        if not new_name:
            # 빈 이름 — 원복
            self._w_name.setText(old_name)
            return
        if new_name == old_name:
            return
        # 이름 변경 — renamed 시그널로 중복 검사/참조 갱신을 상위에 위임
        self.renamed.emit(self._component, old_name, new_name)
        # renamed 핸들러가 변경을 거부했으면 컴포넌트 이름이 old_name으로 유지됨.
        # 위젯을 항상 컴포넌트 실제 이름과 동기화한다.
        self._w_name.setText(self._component.name)
        self.changed.emit()

    def _save_desc(self) -> None:
        self._component.description = self._w_desc.toPlainText().strip()
        # description은 텍스트 키스트로크 — content 채널로.
        self.content_changed.emit()


class _ColorPickerPopup(QFrame):
    """8색 프리셋 팔레트 팝업 (모달 아님)."""

    color_selected = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: #1a1a2e; border: 1px solid #3a4a6a; border-radius: 5px; }"
        )
        self.setWindowFlags(Qt.WindowType.Popup)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        for hex_color in _COLOR_PRESETS:
            btn = QPushButton()
            btn.setFixedSize(18, 18)
            btn.setStyleSheet(
                f"background: {hex_color}; border: 2px solid #333; border-radius: 9px;"
            )
            btn.clicked.connect(lambda _checked, c=hex_color: self._emit(c))
            lay.addWidget(btn)

    def _emit(self, color: str) -> None:
        self.color_selected.emit(color)
        self.hide()


class _EventCard(QFrame):
    """TransferOn 패널의 이벤트 한 항목 카드."""

    delete_requested = pyqtSignal(object)   # EventDef
    changed = pyqtSignal()

    def __init__(
        self,
        event_def: EventDef,
        siblings: list[EventDef] | None = None,
        can_delete: bool = True,
        multiline_desc: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._event = event_def
        self._siblings = siblings or []
        self._multiline = multiline_desc
        self._popup = _ColorPickerPopup(parent=self)
        self._popup.color_selected.connect(self._on_color_picked)

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._update_border()

        # 색상 버튼 (공통)
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(14, 14)
        self._color_btn.setStyleSheet(
            f"background: {event_def.color}; border: 2px solid #335; border-radius: 7px;"
        )
        self._color_btn.clicked.connect(self._show_color_popup)

        # 이름 (공통)
        self._w_name = QLineEdit(event_def.name)
        self._w_name.setFixedWidth(100)
        self._w_name.editingFinished.connect(self._on_name_changed)

        # 삭제 버튼 (공통)
        self._del_btn = QPushButton("✕")
        self._del_btn.setFixedSize(20, 20)
        self._del_btn.setEnabled(can_delete)
        self._del_btn.clicked.connect(lambda: self.delete_requested.emit(self._event))

        if multiline_desc:
            lay = QVBoxLayout(self)
            lay.setContentsMargins(8, 8, 8, 8)
            lay.setSpacing(6)
            top = QHBoxLayout()
            top.addWidget(self._color_btn)
            top.addWidget(self._w_name)
            top.addWidget(QLabel("🤖"))
            top.addStretch()
            top.addWidget(self._del_btn)
            lay.addLayout(top)
            self._w_desc_multi = QTextEdit()
            self._w_desc_multi.setPlainText(event_def.description)
            self._w_desc_multi.setPlaceholderText("에이전트에 전달할 내용을 작성하세요...")
            self._w_desc_multi.setMinimumHeight(60)
            self._w_desc_multi.textChanged.connect(self._on_desc_multi_changed)
            lay.addWidget(self._w_desc_multi)
        else:
            lay = QHBoxLayout(self)
            lay.setContentsMargins(8, 8, 8, 8)
            lay.setSpacing(8)
            lay.addWidget(self._color_btn)
            col = QVBoxLayout()
            col.setSpacing(3)
            name_row = QHBoxLayout()
            name_row.addWidget(self._w_name)
            name_row.addWidget(QLabel("이벤트 이름"))
            name_row.addStretch()
            col.addLayout(name_row)
            self._w_desc = QLineEdit(event_def.description)
            self._w_desc.setPlaceholderText("간략한 설명 (선택)")
            self._w_desc.editingFinished.connect(self._on_desc_changed)
            col.addWidget(self._w_desc)
            lay.addLayout(col, 1)
            lay.addWidget(self._del_btn)

    def _update_border(self) -> None:
        c = QColor(self._event.color)
        border = c.name()
        bg = c.darker(300).name()
        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 5px; }}"
        )

    def _show_color_popup(self) -> None:
        pos = self._color_btn.mapToGlobal(self._color_btn.rect().bottomLeft())
        self._popup.move(pos)
        self._popup.show()

    def _on_color_picked(self, color: str) -> None:
        self._event.color = color
        self._color_btn.setStyleSheet(
            f"background: {color}; border: 2px solid #335; border-radius: 7px;"
        )
        self._update_border()
        self.changed.emit()

    def _on_name_changed(self) -> None:
        new_name = self._w_name.text().strip()
        if not new_name:
            self._w_name.setText(self._event.name)
            return
        # 같은 리스트 내 이름 중복 방지
        if any(e.name == new_name and e is not self._event for e in self._siblings):
            self._w_name.setText(self._event.name)
            return
        self._event.name = new_name
        self.changed.emit()

    def _on_desc_changed(self) -> None:
        self._event.description = self._w_desc.text()
        self.changed.emit()

    def _on_desc_multi_changed(self) -> None:
        self._event.description = self._w_desc_multi.toPlainText()
        self.changed.emit()


class _ContractCard(QFrame):
    """계약 섹션 카드 — 타이틀 잠금, 내용 편집 가능."""

    changed = pyqtSignal()

    def __init__(self, section: Section, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._section = section
        self.setFrameShape(QFrame.Shape.StyledPanel)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self._title_lbl = QLabel(f"🔒 {section.title}")
        lay.addWidget(self._title_lbl)

        self._w_content = QTextEdit()
        self._w_content.setPlainText(section.content)
        self._w_content.setPlaceholderText("이 호출에서 기대하는 입력을 작성하세요...")
        self._w_content.setMinimumHeight(60)
        self._w_content.textChanged.connect(self._on_content_changed)
        lay.addWidget(self._w_content)

    @property
    def section(self) -> Section:
        return self._section

    def sync_title(self) -> None:
        """모델 제목을 라벨에 반영 (in-place 갱신 — 위젯 재생성 회피)."""
        self._title_lbl.setText(f"🔒 {self._section.title}")

    def _on_content_changed(self) -> None:
        self._section.content = self._w_content.toPlainText()
        self.changed.emit()


class _ContractPanel(QScrollArea):
    """잠금 계약 섹션 패널 — 인라인 편집 카드 목록 (스크롤 지원)."""

    contract_changed = pyqtSignal()

    def __init__(
        self,
        label: str,
        contracts: list[Section],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._contracts = contracts
        self._label = label
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._inner = QWidget()
        self._lay = QVBoxLayout(self._inner)
        self._lay.setContentsMargins(12, 12, 12, 12)
        self._lay.setSpacing(8)
        self._cards: list[_ContractCard] = []
        self.setWidget(self._inner)
        self._rebuild()

    def refresh(self) -> None:
        """모델과 카드를 동기화한다.

        카드 수/순서/대상 Section이 동일하면 위젯을 재생성하지 않고
        제목만 in-place 갱신한다 — 편집 중인 QTextEdit가 deleteLater되어
        타이핑이 끊기는 버그(_ContractCard 실사용 버그)를 막는다.
        구조가 달라졌을 때만 전체 재구성한다.
        """
        if self._cards_match_model():
            for card in self._cards:
                card.sync_title()
            return
        self._rebuild()

    def _cards_match_model(self) -> bool:
        """현재 카드 목록이 모델 contracts와 identity 기준으로 1:1 대응하는지."""
        if len(self._cards) != len(self._contracts):
            return False
        return all(
            card.section is sec
            for card, sec in zip(self._cards, self._contracts)
        )

    def _rebuild(self) -> None:
        self._cards = []
        while self._lay.count():
            child = self._lay.takeAt(0)
            if child is not None:
                w = child.widget()
                if w is not None:
                    w.deleteLater()
        if not self._contracts:
            placeholder = QLabel("연결된 호출이 없습니다")
            self._lay.addWidget(placeholder)
            self._lay.addStretch()
            return
        lbl = QLabel(self._label)
        self._lay.addWidget(lbl)
        for sec in self._contracts:
            card = _ContractCard(sec)
            card.changed.connect(self.contract_changed)
            self._lay.addWidget(card)
            self._cards.append(card)
        self._lay.addStretch()


class _TransferOnPanel(QScrollArea):
    """TransferOn / AgentCall 이벤트 카드 목록 (스크롤 지원)."""

    transfer_on_changed = pyqtSignal()

    def __init__(
        self,
        transfer_on: list[EventDef],
        title: str = "⇄ Transfer On",
        default_color: str = "#4488ff",
        multiline_desc: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._transfer_on = transfer_on
        self._default_color = default_color
        self._multiline = multiline_desc
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        hdr_row = QHBoxLayout()
        btn_add = QPushButton("＋")
        btn_add.setFixedWidth(28)
        btn_add.clicked.connect(self._on_add_event)
        hdr_row.addWidget(btn_add)
        hdr_row.addWidget(QLabel(title))
        hdr_row.addStretch()
        lay.addLayout(hdr_row)

        self._cards_widget = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(6)
        lay.addWidget(self._cards_widget)

        lay.addStretch()
        self.setWidget(inner)
        self._rebuild_cards()

    def _rebuild_cards(self) -> None:
        while self._cards_layout.count():
            child = self._cards_layout.takeAt(0)
            if child is not None:
                w = child.widget()
                if w is not None:
                    w.deleteLater()
        for event_def in self._transfer_on:
            card = _EventCard(event_def, siblings=self._transfer_on, can_delete=True, multiline_desc=self._multiline)
            card.changed.connect(self.transfer_on_changed)
            card.delete_requested.connect(self._on_delete_event)
            self._cards_layout.addWidget(card)

    def _on_add_event(self) -> None:
        existing = {e.name for e in self._transfer_on}
        base = "new_event"
        name = base
        counter = 2
        while name in existing:
            name = f"{base}_{counter}"
            counter += 1
        self._transfer_on.append(EventDef(name, color=self._default_color))
        self._rebuild_cards()
        self.transfer_on_changed.emit()

    def _on_delete_event(self, event_def: EventDef) -> None:
        self._transfer_on.remove(event_def)
        self._rebuild_cards()
        self.transfer_on_changed.emit()


class SkillEditor(QWidget):
    """스킬/에이전트 편집기 — ComponentEditor + 타입별 우측 패널."""

    skill_changed = pyqtSignal()

    def __init__(
        self,
        component: ProceduralSkill | DeclarativeSkill | TransferSkill | ReferenceSkill | AgentDefinition,
        on_notify_fn: Callable[[], None] | None = None,
        show_call_agents: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        from daedalus.view.editors.component_editor import ComponentEditor

        right_widgets: list[QWidget] = []
        if isinstance(component, ProceduralSkill):
            right_widgets.append(_TransferOnPanel(component.transfer_on, title="⇄ Transfer On"))
            if show_call_agents:
                right_widgets.append(
                    _TransferOnPanel(component.call_agents, title="🤖 Agent Call", default_color="#8a4a4a", multiline_desc=True)
                )

        # Determine skill_kind for field matrix
        if isinstance(component, ProceduralSkill):
            kind = "local_procedural" if not show_call_agents else "procedural"
        elif isinstance(component, TransferSkill):
            kind = "local_transfer" if not show_call_agents else "transfer"
        elif isinstance(component, DeclarativeSkill):
            kind = "declarative"
        elif isinstance(component, ReferenceSkill):
            kind = "reference"
        else:
            kind = None

        self._editor = ComponentEditor(
            component,
            right_widgets=right_widgets,
            on_notify_fn=self._on_notify,
            skill_kind=kind,
        )

        self._on_notify_fn = on_notify_fn

        # right_widgets의 changed 시그널 연결
        for w in right_widgets:
            if hasattr(w, "transfer_on_changed"):
                w.transfer_on_changed.connect(self._editor._on_model_changed)

        self._editor.changed.connect(self.skill_changed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._editor)

    def _on_notify(self) -> None:
        self.skill_changed.emit()
        if self._on_notify_fn is not None:
            self._on_notify_fn()
