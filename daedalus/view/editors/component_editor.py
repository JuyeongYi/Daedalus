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
from daedalus.view.editors.variable_loader import get_build_target, variables_for

_ComponentType = (
    ProceduralSkill | DeclarativeSkill | TransferSkill | ReferenceSkill
    | AgentDefinition
)

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

        # 변수 팝업 컨텍스트 — 스킬은 풀 지원, 에이전트 .md는 루트 변수만
        # 인식한다(사용자 확정 매트릭스, variable_loader.variables_for).
        var_context = "agent" if isinstance(component, AgentDefinition) else "skill"

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

        # --- 중앙: 본문(SectionContentPanel) — wrapped는 원본 패널로 대체 ---
        # WP-WR(사용자 확정): 랩핑 스킬은 본문 편집이 **아예 불가능**하다 —
        # 정본은 config.source의 외부 스킬이고 컴파일이 인보크 지시를 생성한다.
        # 비활성 편집기를 보여 주는 대신 원본 경로 + "원본 열기" 버튼만 둔다
        # (프론트매터·연결선 정의는 좌/우 패널이 그대로 담당).
        from daedalus.model.plugin.skill import WrappedSkill as _Wrapped

        self._content_panel: SectionContentPanel | None = None
        self._wrapped_panel: _WrappedSourcePanel | None = None
        if isinstance(component, _Wrapped):
            self._wrapped_panel = _WrappedSourcePanel(component)
            self._wrapped_panel.setMinimumWidth(_CENTER_MIN_W)
            root_splitter.addWidget(self._wrapped_panel)
        else:
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
        # (작업 폴더 문서 탭이 같은 함수를 부른다). variables_fn이라 열 때마다
        # 컨텍스트·빌드 타깃 필터를 다시 적용한다. wrapped는 본문 편집기가
        # 없으므로 팝업도 없다.
        self._var_popup = None
        if self._content_panel is not None:
            self._var_popup = make_variable_popup(
                self._content_panel,
                variables_fn=lambda: variables_for(var_context, get_build_target()),
            )

    def _on_variable_insert(self) -> None:
        if self._content_panel is not None and self._var_popup is not None:
            toggle_variable_popup(self._content_panel, self._var_popup)

    def _on_content_changed(self) -> None:
        # 본문 키스트로크 — content 채널로 보내 무거운 structure 리스너(캔버스
        # _rebuild, 레지스트리 재구성)가 키 입력마다 돌지 않게 한다.
        self._on_model_changed(scope="content")

    def _on_model_changed(self, scope: str = "structure") -> None:
        from daedalus.view.viewmodel.project_vm import call_notify
        if self._wrapped_panel is not None:
            # 프론트매터에서 source를 고치면 원본 패널 표시가 따라간다.
            self._wrapped_panel.refresh()
        self.changed.emit()
        call_notify(self._on_notify_fn, scope)  # type: ignore[arg-type]


class _WrappedSourcePanel(QWidget):
    """랩핑 스킬의 중앙 패널 (WP-WR, 사용자 확정) — 본문 편집기 대신 원본
    경로 표시 + "원본 열기" 버튼만.

    본문의 정본은 source가 가리키는 외부 스킬이고 인보크 지시는 빌드가
    생성한다 — 여기서 편집할 본문이라는 것 자체가 없다. 원본 해석은
    `wrap_catalog.resolve_skill_file`(등록된 마켓플레이스 폴더 기준)이다.
    """

    def __init__(self, component, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._component = component

        from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QVBoxLayout

        lay = QVBoxLayout(self)
        lay.addStretch()
        lay.addWidget(QLabel("본문 정본 (외부 스킬) — 인보크 지시는 빌드가 생성"))
        self._w_source = QLineEdit()
        self._w_source.setReadOnly(True)
        lay.addWidget(self._w_source)
        # 용도 표시 (WP-WR) — 최초 배치가 고정하고 여기서 바꿀 수 없다
        # (한 스킬 두 용도 금지, 사용자 확정 2026-09-07).
        self._w_usage = QLabel("")
        lay.addWidget(self._w_usage)
        self._btn_open = QPushButton("원본 열기")
        self._btn_open.setToolTip(
            "등록된 마켓플레이스 폴더에서 원본 SKILL.md를 찾아 연다"
        )
        self._btn_open.clicked.connect(self.open_source)
        lay.addWidget(self._btn_open)
        self._w_status = QLabel("")
        self._w_status.setWordWrap(True)
        lay.addWidget(self._w_status)
        lay.addStretch()

        self.refresh()

    def _source(self) -> str:
        return getattr(getattr(self._component, "config", None), "source", "") or ""

    def refresh(self) -> None:
        source = self._source()
        if self._w_source.text() != source:
            self._w_source.setText(source)
        usage = getattr(getattr(self._component, "config", None), "usage", "") or ""
        usage_text = {
            "state": "용도: 워크플로 단계 (State) — 최초 배치로 고정됨",
            "reference": "용도: 참조 (Reference — 산출 파일 없음) — 최초 배치로 고정됨",
        }.get(usage, "용도: 미정 — 최초 배치 시 State/Reference를 선택하면 고정됩니다")
        if self._w_usage.text() != usage_text:
            self._w_usage.setText(usage_text)
        if not source:
            self._w_status.setText(
                "source가 비어 있습니다 — 좌측 프론트매터에서 "
                "`플러그인[@마켓]:스킬`을 지정하세요."
            )
        elif self._w_status.text():
            self._w_status.setText("")

    def open_source(self) -> bool:
        """원본 SKILL.md를 OS 기본 프로그램으로 연다. 찾으면 True."""
        from daedalus.model.plugin.wrap_catalog import resolve_skill_file

        md = resolve_skill_file(self._source())
        if md is None:
            self._w_status.setText(
                "원본을 찾지 못했습니다 — 도구 → 외부 플러그인 카탈로그에서 "
                "이 플러그인이 있는 마켓플레이스 폴더를 등록했는지 확인하세요."
            )
            return False
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(md)))
        return True
