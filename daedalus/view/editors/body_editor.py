"""공용 본문 편집 위젯 — SectionContentPanel(단일 마크다운 body 편집), VariablePopup.

WP-SB: 수동 섹션 트리 편집(SectionTree/BreadcrumbNav)은 마크다운 에디터
(WP-MD1/MD2)로 대체되어 제거됐다 — 본문 구조의 단일 진실은 이제 컴포넌트의
``body: str`` 필드(마크다운 텍스트) 하나다.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from daedalus.view.editors import body_documents
from daedalus.view.widgets.markdown_editor import (
    MarkdownEditor,
    MarkdownToolbar,
    SearchBar,
    TocPanel,
)


class SectionContentPanel(QWidget):
    """컴포넌트 본문(body) 편집 패널 — 마크다운 에디터/프리뷰 + 변수 삽입."""

    variable_insert_requested = Signal()
    content_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._component: object | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # --- 툴바 ---
        toolbar = QWidget()
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(10, 5, 10, 5)
        tb_lay.setSpacing(6)

        tb_lay.addStretch()
        self._btn_variable = QPushButton("{ } 변수 삽입")
        self._btn_variable.clicked.connect(self.variable_insert_requested)
        tb_lay.addWidget(self._btn_variable)

        lay.addWidget(toolbar)

        # --- 서식 툴바 ---
        self._w_content = MarkdownEditor()
        self._w_content.textChanged.connect(self._save_body)
        self._md_toolbar = MarkdownToolbar(self._w_content)
        self._md_toolbar.preview_toggled.connect(self._on_preview_toggled)
        self._md_toolbar.toc_toggled.connect(self._on_toc_toggled)
        lay.addWidget(self._md_toolbar)

        # --- 찾기/바꾸기 바 (기본 숨김) ---
        self._search_bar = SearchBar(self._w_content)
        self._w_content.search_requested.connect(self._search_bar.open)
        lay.addWidget(self._search_bar)

        # --- 본문(에디터/프리뷰 스택) + TOC 사이드바(기본 숨김) ---
        self._w_preview = QTextBrowser()
        self._w_preview.setOpenExternalLinks(False)
        self._w_preview.setStyleSheet(
            "QTextBrowser { background-color: #1e1e32; color: #cccccc; border: none; }",
        )

        self._content_stack = QStackedWidget()
        self._content_stack.addWidget(self._w_content)  # page 0: 편집
        self._content_stack.addWidget(self._w_preview)  # page 1: 프리뷰

        self._toc_panel = TocPanel(self._w_content)
        self._toc_panel.setFixedWidth(180)
        self._toc_panel.hide()

        body_row = QHBoxLayout()
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(0)
        body_row.addWidget(self._content_stack, 1)
        body_row.addWidget(self._toc_panel)
        lay.addLayout(body_row, 1)

    def current_component(self) -> object | None:
        return self._component

    def show_body(self, component: object) -> None:
        """컴포넌트의 본문 문서를 에디터에 붙인다 (WP-BU).

        setPlainText로 내용만 갈아끼우면 그 문서의 undo 이력이 지워져, 다른
        컴포넌트를 잠깐 열었다 돌아오면 본문 되돌리기가 불가능해진다. 대신
        컴포넌트별 QTextDocument를 레지스트리에서 받아 통째로 교체하므로
        본문마다 독립적인 undo 스택이 탭을 옮겨다녀도 유지된다.
        """
        self._component = component
        self._md_toolbar.set_preview_checked(False)
        self._content_stack.setCurrentIndex(0)
        self._search_bar.close_bar()
        doc = body_documents.registry().document_for(component)
        self._w_content.blockSignals(True)
        self._w_content.attach_document(doc)
        self._w_content.blockSignals(False)
        # TOC는 blockSignals로 억제된 textChanged를 못 받으므로 문서 전환 시 직접 갱신한다
        self._toc_panel.refresh()

    def _on_preview_toggled(self, checked: bool) -> None:
        # 변수 삽입도 숨은 문서를 조용히 바꾸는 경로 — 프리뷰 중 잠근다
        self._btn_variable.setEnabled(not checked)
        if checked:
            self._search_bar.close_bar()
            self._w_preview.document().setMarkdown(self._w_content.toPlainText())
            self._content_stack.setCurrentIndex(1)
        else:
            self._content_stack.setCurrentIndex(0)

    def _on_toc_toggled(self, checked: bool) -> None:
        self._toc_panel.setVisible(checked)

    def insert_variable(self, var_name: str) -> None:
        self._w_content.insertPlainText(var_name)

    def _save_body(self) -> None:
        if self._component is not None:
            self._component.body = self._w_content.toPlainText()  # type: ignore[attr-defined]
            self.content_changed.emit()


class VariablePopup(QFrame):
    """변수 선택 팝업 — 클릭 시 variable_selected 시그널 방출."""

    variable_selected = Signal(str)

    def __init__(
        self,
        entries: list,  # list[VariableEntry]
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setFixedWidth(300)
        # 열 때마다 목록을 다시 만드는 제공자 — make_variable_popup이 채우고
        # toggle_variable_popup이 호출한다(없으면 생성 시점 목록 고정).
        self._variables_fn: Callable[[], list] | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(8, 5, 8, 5)
        hdr_lbl = QLabel("변수 선택 — 클릭 시 커서 위치에 삽입")
        hdr_row.addWidget(hdr_lbl)
        hdr_row.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(16, 16)
        close_btn.clicked.connect(self.hide)
        hdr_row.addWidget(close_btn)
        hdr_widget = QWidget()
        hdr_widget.setLayout(hdr_row)
        lay.addWidget(hdr_widget)

        # 행 영역 — set_entries가 통째로 다시 채운다 (컨텍스트·빌드 타깃에 따라
        # 유효한 변수가 달라 팝업을 열 때마다 갱신된다).
        rows_widget = QWidget()
        self._rows_lay = QVBoxLayout(rows_widget)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        self._rows_lay.setSpacing(0)
        lay.addWidget(rows_widget)

        self.set_entries(entries)

    _SOURCE_LABELS = {
        "builtin": ("기본 제공", "#4477aa"),
        "global":  ("글로벌 (~/.daedalus/variables.yaml)", "#4a7a4a"),
        "project": ("프로젝트 (.daedalus/variables.yaml)", "#7a7a4a"),
    }

    def set_entries(self, entries: list) -> None:
        """행 목록을 교체한다 — 헤더는 그대로, 그룹 라벨·버튼만 다시 만든다."""
        while self._rows_lay.count():
            child = self._rows_lay.takeAt(0)
            if child is not None:
                w = child.widget()
                if w is not None:
                    # deleteLater만으로는 이벤트 루프 전까지 자식으로 남아
                    # findChildren류 순회가 죽은 행을 잡는다(TagInput 관례).
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
        current_source: str | None = None
        for entry in entries:
            if entry.source != current_source:
                current_source = entry.source
                label_text, _label_color = self._SOURCE_LABELS.get(
                    entry.source, (entry.source, "#446"),
                )
                self._rows_lay.addWidget(QLabel(label_text))
            row = QPushButton()
            row.setText(f"{entry.name}   {entry.description}")
            row.clicked.connect(lambda _c, n=entry.name: self._emit(n))
            self._rows_lay.addWidget(row)
        self.adjustSize()

    def _emit(self, name: str) -> None:
        self.variable_selected.emit(name)
        self.hide()


# ---------------------------------------------------------------------------
# 변수 삽입 배선 — 팝업 생성과 위치 계산의 단일 진실
#
# `SectionContentPanel`을 쓰는 표면이 둘이다(컴포넌트 편집기, 작업 폴더 문서 탭).
# 배선이 한쪽에만 있으면 같은 버튼이 표면마다 다르게 동작한다 — 실제로 그랬다:
# workspace_editor는 시그널을 연결하지 않아 변수 버튼이 무동작이었다.
# ---------------------------------------------------------------------------


def make_variable_popup(
    panel: SectionContentPanel,
    variables: list | None = None,  # list[VariableEntry]
    variables_fn: Callable[[], list] | None = None,
) -> VariablePopup:
    """패널에 붙는 변수 팝업을 만들고 삽입 경로를 연결한다.

    variables_fn을 주면 **팝업을 열 때마다** 그것으로 목록을 다시 만든다 —
    유효한 변수가 편집 컨텍스트(스킬/에이전트/작업 폴더 문서)와 빌드 타깃에
    따라 다르고(사용자 확정 매트릭스, `variable_loader.variables_for`), 빌드
    타깃은 세션 중에 바뀔 수 있어 생성 시점 고정으로는 스테일해진다.
    둘 다 생략하면 `load_variables()`로 기본+글로벌 변수를 읽는다(무필터).
    """
    if variables is None:
        if variables_fn is not None:
            # 행은 첫 열기에서 채운다 — 생성 시점에 fn을 부르면 그 결과가
            # 곧 스테일이고(빌드 타깃은 나중에 정해질 수 있다) 어차피
            # toggle이 열 때마다 다시 만든다.
            variables = []
        else:
            from daedalus.view.editors.variable_loader import load_variables

            variables = load_variables()
    popup = VariablePopup(variables, parent=panel)
    popup._variables_fn = variables_fn
    popup.variable_selected.connect(panel.insert_variable)
    popup.hide()
    return popup


def toggle_variable_popup(panel: SectionContentPanel, popup: VariablePopup) -> None:
    """변수 팝업을 버튼 바로 아래에 띄운다(이미 떠 있으면 닫는다).

    VariablePopup은 Qt.Popup 플래그의 최상위 창이라 move()가 **전역 좌표**를
    받는다 — 패널 상대 좌표를 넘기면 화면 좌상단 근처에 떠 버린다.
    """
    if popup.isVisible():
        popup.hide()
        return
    fn = getattr(popup, "_variables_fn", None)
    if fn is not None:
        popup.set_entries(fn())
    btn = panel._btn_variable
    popup.move(btn.mapToGlobal(QPoint(0, btn.height())))
    popup.show()
    popup.raise_()
