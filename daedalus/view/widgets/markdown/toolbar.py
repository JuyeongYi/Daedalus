"""서식 툴바 (WP-MD2/WP-MK) — `MarkdownEditor` 공개 API에 배선된 버튼 행."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QWidget

from daedalus.view.widgets.markdown.editor import MarkdownEditor


class MarkdownToolbar(QWidget):
    """서식 툴바 — `MarkdownEditor` 공개 API에 배선된 버튼 행.

    `H1 H2 H3 │ B I S │ <> {} │ • 1. ☑ │ " 🔗 │ ☰ 👁` — ☰(TOC 토글)·👁(프리뷰)는
    문서를 건드리지 않고 각각 `toc_toggled`/`preview_toggled` 시그널만 방출한다
    (TOC 패널 표시/숨김·프리뷰 자체는 `SectionContentPanel` 소관).
    """

    preview_toggled = Signal(bool)
    toc_toggled = Signal(bool)

    _BUTTON_WIDTH = 30

    def __init__(self, editor: MarkdownEditor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._editor = editor
        self._edit_buttons: list[QPushButton] = []  # 프리뷰 중 비활성화 대상

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(2)

        self._add_button(lay, "H1", "제목 1 (Ctrl+1)", lambda: self._apply_heading(1))
        self._add_button(lay, "H2", "제목 2 (Ctrl+2)", lambda: self._apply_heading(2))
        self._add_button(lay, "H3", "제목 3 (Ctrl+3)", lambda: self._apply_heading(3))
        self._add_separator(lay)
        self._add_button(lay, "B", "굵게 (Ctrl+B)", lambda: self._apply_wrap("**", "**"))
        self._add_button(lay, "I", "기울임 (Ctrl+I)", lambda: self._apply_wrap("*", "*"))
        self._add_button(lay, "S", "취소선 (Ctrl+Shift+X)", lambda: self._apply_wrap("~~", "~~"))
        self._add_separator(lay)
        self._add_button(lay, "<>", "인라인 코드 (Ctrl+`)", self._apply_inline_code)
        self._add_button(lay, "{}", "코드 블록 (Ctrl+Shift+C)", self._apply_code_block)
        self._add_separator(lay)
        self._add_button(lay, "•", "불릿 리스트 (Ctrl+Shift+8)", lambda: self._apply_marker("- "))
        self._add_button(lay, "1.", "번호 리스트 (Ctrl+Shift+7)", lambda: self._apply_marker("1. "))
        self._add_button(lay, "☑", "체크리스트 (Ctrl+Shift+9)", lambda: self._apply_marker("- [ ] "))
        self._add_separator(lay)
        self._add_button(lay, "\"", "인용 (Ctrl+Shift+.)", lambda: self._apply_marker("> "))
        self._add_button(lay, "🔗", "링크 (Ctrl+K)", self._apply_link)
        self._add_separator(lay)
        self._btn_toc = self._add_button(
            lay, "☰", "목차 토글", self._on_toc_toggled, checkable=True,
        )
        self._edit_buttons.append(self._btn_toc)  # 프리뷰 중 비활성화 대상에 포함
        self._btn_preview = self._add_button(
            lay, "👁", "미리보기 전환", self._on_preview_toggled, checkable=True,
        )
        lay.addStretch(1)

    def _add_button(
        self,
        lay: QHBoxLayout,
        text: str,
        tooltip: str,
        handler,
        *,
        checkable: bool = False,
    ) -> QPushButton:
        btn = QPushButton(text)
        btn.setFlat(True)
        btn.setFixedWidth(self._BUTTON_WIDTH)
        btn.setToolTip(tooltip)
        btn.setCheckable(checkable)
        if checkable:
            # checkable은 ☰(TOC)/👁(프리뷰) 전용 — 문서를 건드리지 않으므로
            # 호출부가 필요할 때만 개별적으로 _edit_buttons에 편입시킨다
            btn.toggled.connect(handler)
        else:
            btn.clicked.connect(handler)
            self._edit_buttons.append(btn)
        lay.addWidget(btn)
        return btn

    def _add_separator(self, lay: QHBoxLayout) -> None:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        lay.addWidget(sep)

    def _apply_heading(self, level: int) -> None:
        self._editor.set_heading_level(level)
        self._editor.setFocus()

    def _apply_wrap(self, prefix: str, suffix: str) -> None:
        self._editor.toggle_wrap(prefix, suffix)
        self._editor.setFocus()

    def _apply_marker(self, marker: str) -> None:
        self._editor.toggle_line_marker(marker)
        self._editor.setFocus()

    def _apply_inline_code(self) -> None:
        self._editor.toggle_inline_code()
        self._editor.setFocus()

    def _apply_code_block(self) -> None:
        self._editor.toggle_code_block()
        self._editor.setFocus()

    def _apply_link(self) -> None:
        self._editor.insert_link()
        self._editor.setFocus()

    def _on_toc_toggled(self, checked: bool) -> None:
        self.toc_toggled.emit(checked)
        self._editor.setFocus()

    def _on_preview_toggled(self, checked: bool) -> None:
        # 프리뷰 중 편집 버튼이 숨은 문서를 조용히 바꾸지 못하게 잠근다
        for btn in self._edit_buttons:
            btn.setEnabled(not checked)
        self.preview_toggled.emit(checked)
        self._editor.setFocus()

    def set_preview_checked(self, checked: bool) -> None:
        """프리뷰(👁) 버튼 체크 상태를 외부에서 리셋할 때 쓰는 공개 API.

        `checked`가 현재 상태와 다르면 `toggled` 시그널이 발생해 `preview_toggled`도
        함께 방출된다(호출자가 이를 감안해야 함 — `SectionContentPanel.show_body`는
        이 방출로 스택이 편집 모드로 복귀하는 것을 활용한다).
        """
        self._btn_preview.setChecked(checked)
