# daedalus/view/editors/component_editor.py
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QSplitter,
    QWidget,
)

from daedalus.model.plugin.agent import Agent
from daedalus.model.plugin.roles import Bucket
from daedalus.model.plugin.skill import Skill
from daedalus.view.editors.body_editor import (
    SectionContentPanel,
    make_variable_popup,
    toggle_variable_popup,
)
from daedalus.view.editors.skill_editor import _FrontmatterPanel
from daedalus.view.editors.variable_loader import get_build_target, variables_for

#: 편집기가 받는 컴포넌트 — 스킬 7종·에이전트 2종 전부(종류별 차이는
#: 프론트매터 표와 우측 패널이 흡수한다).
_ComponentType = Skill | Agent

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
        # 프론트매터 폼 재생성(종류 전환)에 필요한 생성 인자 — 폼만 다시
        # 만들려면 만들 때 쓴 것을 그대로 다시 줘야 한다.
        self._build_target = build_target
        self._project_vm = project_vm

        # 변수 팝업 컨텍스트 — 스킬은 풀 지원, 에이전트 .md는 루트 변수만
        # 인식한다(사용자 확정 매트릭스, variable_loader.variables_for).
        # 맥락을 가르는 것은 종류가 아니라 **산출 버킷**이다(WP-2d Q25) —
        # `component_actions`/MCP `delete_component`와 같은 술어를 쓴다.
        var_context = "agent" if component.BUCKET is Bucket.AGENTS else "skill"

        root_lay = QHBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        root_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._root_splitter = root_splitter

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

        # --- 중앙: 본문(SectionContentPanel) — 정본이 외부면 원본 패널로 대체 ---
        # 본문 정본이 외부인 종류(외부 플러그인 에이전트)는 본문 편집이
        # **아예 불가능**하다 — 정본은 config.source가 가리키는 그 플러그인의
        # 파일이고 우리 산출에는 위임 지시만 나간다. 비활성 편집기를 보여 주는
        # 대신 원본 경로 + "원본 열기" 버튼만 둔다(프론트매터·연결선 정의는
        # 좌/우 패널이 그대로 담당).
        from daedalus.model.plugin.skill import has_external_body

        self._content_panel: SectionContentPanel | None = None
        self._external_panel: _ExternalSourcePanel | None = None
        if has_external_body(component):
            self._external_panel = _ExternalSourcePanel(component)
            self._external_panel.setMinimumWidth(_CENTER_MIN_W)
            root_splitter.addWidget(self._external_panel)
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
        # 컨텍스트·빌드 타깃 필터를 다시 적용한다. 본문 정본이 외부인 종류는
        # 본문 편집기가 없으므로 팝업도 없다.
        self._var_popup = None
        if self._content_panel is not None:
            self._var_popup = make_variable_popup(
                self._content_panel,
                variables_fn=lambda: variables_for(var_context, get_build_target()),
            )

    def rebuild_frontmatter(self) -> _FrontmatterPanel:
        """좌측 프론트매터 폼을 **현재 종류로** 다시 만들고 돌려준다.

        종류 전환(`convert_skill_kind`)은 `__class__`와 config를 통째로 바꾸므로
        전환 전에 그려진 폼은 다른 종류의 표를 보고 있다 — 사라진 필드를 그대로
        편집할 수 있고 새로 생긴 필드는 보이지 않는다.

        **본문·우측 패널은 건드리지 않는다.** 편집기 전체를 재생성하면 편집 중인
        본문 문서와 커서·스크롤이 날아가고, 탭이 목록 끝으로 옮겨진다.
        """
        kind = getattr(getattr(self._component, "config", None), "kind", None)
        new = _FrontmatterPanel(
            self._component, skill_kind=kind, build_target=self._build_target,
            project_vm=self._project_vm,
        )
        new.setMinimumWidth(_LEFT_MIN_W)
        new.changed.connect(self._on_model_changed)
        new.content_changed.connect(lambda: self._on_model_changed(scope="content"))

        sizes = self._root_splitter.sizes()
        old = self._root_splitter.replaceWidget(0, new)
        self._root_splitter.setSizes(sizes)
        if old is not None:
            old.setParent(None)
            old.deleteLater()
        self._fm = new
        return new

    def _on_variable_insert(self) -> None:
        if self._content_panel is not None and self._var_popup is not None:
            toggle_variable_popup(self._content_panel, self._var_popup)

    def _on_content_changed(self) -> None:
        # 본문 키스트로크 — content 채널로 보내 무거운 structure 리스너(캔버스
        # _rebuild, 레지스트리 재구성)가 키 입력마다 돌지 않게 한다.
        self._on_model_changed(scope="content")

    def _on_model_changed(self, scope: str = "structure") -> None:
        from daedalus.view.viewmodel.project_vm import call_notify
        if self._external_panel is not None:
            # 프론트매터에서 source를 고치면 원본 패널 표시가 따라간다.
            self._external_panel.refresh()
        self.changed.emit()
        call_notify(self._on_notify_fn, scope)  # type: ignore[arg-type]


class _ExternalSourcePanel(QWidget):
    """본문 정본이 **외부**인 컴포넌트의 중앙 패널 — 본문 편집기 대신 원본
    경로 표시 + "원본 열기" 버튼.

    본문의 정본은 source가 가리키는 외부 플러그인의 파일이고 위임 지시는
    빌드가 생성한다 — 여기서 편집할 본문이라는 것 자체가 없다. 원본 해석은
    `wrap_catalog.resolve_source_file`(등록된 마켓플레이스 폴더 기준)이다.

    **문구의 명사는 선언에서 나온다**(WP-9 리뷰 반영) — 산문이 한 버킷으로
    굳어 있으면 다른 버킷의 편집기가 **틀린 지시**를 한다(원칙 5).
    """

    def __init__(self, component, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._component = component

        from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QVBoxLayout

        # 정본이 무엇으로 불리는가 — 버킷이 답한다(스킬 산출 vs 에이전트 산출).
        self._noun = "에이전트" if component.BUCKET is Bucket.AGENTS else "스킬"

        lay = QVBoxLayout(self)
        lay.addStretch()
        lay.addWidget(QLabel("본문 정본 (외부) — 위임 지시는 빌드가 생성"))
        self._w_source = QLineEdit()
        self._w_source.setReadOnly(True)
        lay.addWidget(self._w_source)
        self._btn_open = QPushButton("원본 열기")
        self._btn_open.setToolTip(
            "등록된 마켓플레이스 폴더에서 원본 파일을 찾아 연다"
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
        if not source:
            self._w_status.setText(
                f"source가 비어 있습니다 — 좌측 프론트매터에서 외부 "
                f"{self._noun} source를 `플러그인[@마켓]:이름` 형식으로 "
                f"지정하세요."
            )
        elif self._w_status.text():
            self._w_status.setText("")

    def open_source(self) -> bool:
        """원본 파일을 OS 기본 프로그램으로 연다. 찾으면 True."""
        from daedalus.model.plugin.wrap_catalog import resolve_source_file

        md = resolve_source_file(self._component)
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
