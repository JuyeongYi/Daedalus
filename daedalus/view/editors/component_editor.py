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
from daedalus.view.editors.body_editor import (
    SectionContentPanel,
    make_variable_popup,
    toggle_variable_popup,
)
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
        project_vm=None,
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
            project_vm=project_vm,
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
            for i, w in enumerate(rw):
                w.setMinimumHeight(_RIGHT_CHILD_MIN_H)
                right_splitter.addWidget(w)
                # 위젯이 `right_stretch`로 선호 비율을 선언할 수 있다 (WP-SF —
                # 파일 트리는 포트 카드 목록보다 세로 공간이 더 필요하다).
                right_splitter.setStretchFactor(i, getattr(w, "right_stretch", 1))
            # stretch factor는 sizeHint 이후의 **여유 공간**에만 작용한다 —
            # 초기 분할 자체를 비율대로 잡으려면 setSizes가 필요하다
            # (QSplitter가 합계 대비 비율로 정규화한다).
            right_splitter.setSizes(
                [100 * getattr(w, "right_stretch", 1) for w in rw]
            )
            root_splitter.addWidget(right_splitter)

        # stretch 비율: 좌1 중3 우2 (3컬럼) / 좌1 중3 (2컬럼)
        root_splitter.setStretchFactor(0, 1)
        root_splitter.setStretchFactor(1, 3)
        if rw:
            root_splitter.setStretchFactor(2, 2)

        root_lay.addWidget(root_splitter)

        # Variable popup — 생성·위치 계산은 body_editor의 공용 헬퍼가 맡는다
        # (작업 폴더 문서 탭이 같은 함수를 부른다).
        self._var_popup = make_variable_popup(self._content_panel, variables)

    def _on_variable_insert(self) -> None:
        toggle_variable_popup(self._content_panel, self._var_popup)

    def _on_content_changed(self) -> None:
        # 본문 키스트로크 — content 채널로 보내 무거운 structure 리스너(캔버스
        # _rebuild, 레지스트리 재구성)가 키 입력마다 돌지 않게 한다.
        self._on_model_changed(scope="content")

    def _on_model_changed(self, scope: str = "structure") -> None:
        from daedalus.view.viewmodel.project_vm import call_notify
        self.changed.emit()
        call_notify(self._on_notify_fn, scope)  # type: ignore[arg-type]
