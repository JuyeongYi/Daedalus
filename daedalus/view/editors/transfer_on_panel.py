# daedalus/view/editors/transfer_on_panel.py
"""출력 포트(transfer_on / call_agents) 편집 패널 — 이벤트 카드 목록.

구 ``skill_editor.py``(1,172줄)에서 이동했다(WP-RF 관례 — 이동만·동작 불변).
``skill_editor`` 모듈은 재-export 파사드로 남아 기존 임포트 경로가 그대로 동작한다.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.fsm.section import EventDef


_COLOR_PRESETS = [
    "#4488ff", "#cc3333", "#cc8800", "#44aa44",
    "#aa44cc", "#ccaa00", "#44aacc", "#888888",
]


class _ColorPickerPopup(QFrame):
    """8색 프리셋 팔레트 팝업 (모달 아님)."""

    color_selected = Signal(str)

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

    delete_requested = Signal(object)   # EventDef
    changed = Signal()

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


class _TransferOnPanel(QScrollArea):
    """TransferOn / AgentCall 이벤트 카드 목록 (스크롤 지원)."""

    transfer_on_changed = Signal()

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
                    # deleteLater만으로는 이벤트 루프가 돌기 전까지 자식으로 남아
                    # findChildren류 순회가 죽은 카드를 잡는다 — hide 후 부모를
                    # 분리한다(TagInput._rebuild / body_editor.set_entries 관례).
                    w.hide()
                    w.setParent(None)
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
