# daedalus/view/editors/component_editor.py
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QSplitter,
    QWidget,
)

from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import (
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    TransferSkill,
)
from daedalus.view.editors.body_editor import SectionContentPanel, VariablePopup
from daedalus.view.editors.skill_editor import _FrontmatterPanel
from daedalus.view.editors.variable_loader import load_variables

_ComponentType = ProceduralSkill | DeclarativeSkill | TransferSkill | ReferenceSkill | AgentDefinition

_LEFT_MIN_W = 120
_CENTER_MIN_W = 200
_RIGHT_MIN_W = 120
_RIGHT_CHILD_MIN_H = 60


class ComponentEditor(QWidget):
    """재사용 복합 에디터 — 좌(Frontmatter) | 중(본문 body) | 우(옵션)."""

    changed = Signal()

    def __init__(
        self,
        component: _ComponentType,
        right_widgets: list[QWidget] | None = None,
        on_notify_fn: Callable[[], None] | None = None,
        skill_kind: str | None = None,
        parent: QWidget | None = None,
        build_target=None,
    ) -> None:
        super().__init__(parent)
        self._component = component
        self._on_notify_fn = on_notify_fn

        variables = load_variables()

        root_lay = QHBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        root_splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- 좌측: FrontmatterPanel ---
        self._fm = _FrontmatterPanel(
            component, skill_kind=skill_kind, build_target=build_target,
        )
        self._fm.setMinimumWidth(_LEFT_MIN_W)
        self._fm.changed.connect(self._on_model_changed)
        # description / when_to_use 키스트로크 → content 채널
        self._fm.content_changed.connect(lambda: self._on_model_changed(scope="content"))
        root_splitter.addWidget(self._fm)

        # --- 중앙: SectionContentPanel(본문 body) ---
        self._content_panel = SectionContentPanel()
        self._content_panel.setMinimumWidth(_CENTER_MIN_W)
        self._content_panel.variable_insert_requested.connect(self._on_variable_insert)
        self._content_panel.content_changed.connect(self._on_content_changed)
        self._content_panel.show_body(component)
        root_splitter.addWidget(self._content_panel)

        # --- 우측: right_widgets (수직 스플리터, 있을 때만) ---
        rw = right_widgets or []
        if rw:
            right_splitter = QSplitter(Qt.Orientation.Vertical)
            right_splitter.setMinimumWidth(_RIGHT_MIN_W)
            for w in rw:
                w.setMinimumHeight(_RIGHT_CHILD_MIN_H)
                right_splitter.addWidget(w)
            root_splitter.addWidget(right_splitter)

        # stretch 비율: 좌1 중3 우2 (3컬럼) / 좌1 중3 (2컬럼)
        root_splitter.setStretchFactor(0, 1)
        root_splitter.setStretchFactor(1, 3)
        if rw:
            root_splitter.setStretchFactor(2, 2)

        root_lay.addWidget(root_splitter)

        # Variable popup
        self._var_popup = VariablePopup(variables, parent=self._content_panel)
        self._var_popup.variable_selected.connect(self._content_panel.insert_variable)
        self._var_popup.hide()

    def _on_variable_insert(self) -> None:
        if self._var_popup.isVisible():
            self._var_popup.hide()
            return
        from PySide6.QtCore import QPoint
        btn = self._content_panel._btn_variable
        # VariablePopup은 Qt.Popup 플래그의 최상위 창 — move()는 전역 좌표를 받는다.
        # (패널 상대 좌표를 넘기면 화면 좌상단 근처에 떠 버린다.)
        pos = btn.mapToGlobal(QPoint(0, btn.height()))
        self._var_popup.move(pos)
        self._var_popup.show()
        self._var_popup.raise_()

    def _on_content_changed(self) -> None:
        # 본문 키스트로크 — content 채널로 보내 무거운 structure 리스너(캔버스
        # _rebuild, 레지스트리 재구성)가 키 입력마다 돌지 않게 한다.
        self._on_model_changed(scope="content")

    def _on_model_changed(self, scope: str = "structure") -> None:
        from daedalus.view.viewmodel.project_vm import call_notify
        self.changed.emit()
        call_notify(self._on_notify_fn, scope)  # type: ignore[arg-type]
