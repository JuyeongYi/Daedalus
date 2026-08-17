"""찾기/바꾸기 바 (WP-MD3) — `MarkdownEditor` 위에 접히는 바."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QWidget,
)

if TYPE_CHECKING:  # pragma: no cover - 타입 힌트 전용
    from daedalus.view.widgets.markdown.editor import MarkdownEditor

_SEARCH_MATCH_BG = QColor("#665522")
_SEARCH_CURRENT_BG = QColor("#a3843a")


class SearchBar(QWidget):
    """찾기/바꾸기 바 — `MarkdownEditor` 위에 접히는 바(기본 숨김).

    포팅 정답지: qmarkdowntextedit의 QPlainTextEditSearchWidget을 단순화
    (정규식/단어 단위/선택 범위 검색 없음 — WP-MD3 Part A 명세 범위).
    검색은 `toPlainText()`에 대한 평문 부분 문자열 매칭이며 `QTextDocument.find`를
    쓰지 않는다 — 매치 목록을 직접 들고 있어야 다음/이전·바꾸기 순서 제어가 쉽다.
    """

    def __init__(self, editor: "MarkdownEditor", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._editor = editor
        self._matches: list[tuple[int, int]] = []
        self._current: int = -1
        # 문서 편집 시 정수 오프셋 매치가 스테일 — dirty 표시 후 다음 조작
        # 진입 시 재수집한다 (스테일 오프셋으로 엉뚱한 구간을 치환하는 결함 방지).
        self._matches_dirty = False
        self._editor.textChanged.connect(self._mark_matches_dirty)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(4)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("찾기")
        lay.addWidget(self._search_edit, 1)

        self._prev_btn = QPushButton("↑")
        self._prev_btn.setFixedWidth(24)
        self._prev_btn.setToolTip("이전 (Shift+Enter)")
        lay.addWidget(self._prev_btn)

        self._next_btn = QPushButton("↓")
        self._next_btn.setFixedWidth(24)
        self._next_btn.setToolTip("다음 (Enter)")
        lay.addWidget(self._next_btn)

        self._case_btn = QPushButton("Aa")
        self._case_btn.setCheckable(True)
        self._case_btn.setFixedWidth(28)
        self._case_btn.setToolTip("대소문자 구분")
        lay.addWidget(self._case_btn)

        self._count_label = QLabel("0/0")
        self._count_label.setStyleSheet("color: #888;")
        self._count_label.setFixedWidth(56)
        lay.addWidget(self._count_label)

        self._replace_edit = QLineEdit()
        self._replace_edit.setPlaceholderText("바꾸기")
        lay.addWidget(self._replace_edit, 1)

        self._replace_btn = QPushButton("바꾸기")
        lay.addWidget(self._replace_btn)

        self._replace_all_btn = QPushButton("모두 바꾸기")
        lay.addWidget(self._replace_all_btn)

        self._close_btn = QPushButton("✕")
        self._close_btn.setFlat(True)
        self._close_btn.setFixedWidth(20)
        self._close_btn.setToolTip("닫기 (Esc)")
        lay.addWidget(self._close_btn)

        self.setStyleSheet(
            "SearchBar { background-color: #252540; }"
            "QLineEdit { background-color: #1e1e32; color: #ccc; "
            "border: 1px solid #3a3a5c; }",
        )

        self._search_edit.textChanged.connect(lambda _t: self._perform_search())
        self._case_btn.toggled.connect(lambda _c: self._perform_search())
        self._next_btn.clicked.connect(self.search_next)
        self._prev_btn.clicked.connect(self.search_prev)
        self._replace_btn.clicked.connect(self.replace_current)
        self._replace_all_btn.clicked.connect(self.replace_all)
        self._close_btn.clicked.connect(self.close_bar)

        self._search_edit.installEventFilter(self)
        self._replace_edit.installEventFilter(self)

        self.hide()

    # --- 표시/숨김 ---

    def open(self, prefill: str = "") -> None:
        """바를 열고 검색창에 포커스한다. prefill이 있으면 검색어로 채운다.

        `setText`가 실제로 값을 바꾸면 `textChanged` → `_perform_search`가 이미
        원래 커서 위치를 앵커로 실행되므로, 그 경우 재호출하지 않는다(재호출하면
        직전 호출이 옮겨 둔 커서를 앵커로 다시 검색해 한 칸 더 건너뛰는 버그가 된다).
        값이 그대로면(빈 prefill 포함, 재오픈 등) 여기서 명시적으로 1회 실행한다.
        """
        if " " in prefill:
            prefill = ""  # 여러 줄 선택(U+2029 문단 구분자) — 프리필 생략
        self.show()
        changed = bool(prefill) and self._search_edit.text() != prefill
        if changed:
            self._search_edit.setText(prefill)
        self._search_edit.selectAll()
        self._search_edit.setFocus()
        if not changed:
            self._perform_search()

    def close_bar(self) -> None:
        """바를 숨기고 하이라이트를 지운 뒤 에디터로 포커스를 돌려준다.

        이미 숨어 있으면 아무것도 하지 않는다 — show_body 등 경유 호출이
        포커스를 훔치지 않게 (리뷰 지적 3).
        """
        if self.isHidden():
            return
        self.hide()
        self._matches = []
        self._current = -1
        self._editor.setExtraSelections([])
        self._editor.setFocus()

    # --- Esc/Enter/Shift+Enter/Up/Down 배선 (검색·바꾸기 입력창 공용) ---

    def eventFilter(self, obj, event):  # noqa: N802 (Qt override)
        if event.type() == QEvent.Type.KeyPress and obj in (
            self._search_edit,
            self._replace_edit,
        ):
            key = event.key()
            mods = event.modifiers()
            if key == Qt.Key.Key_Escape:
                self.close_bar()
                return True
            if key == Qt.Key.Key_Up or (
                key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and mods & Qt.KeyboardModifier.ShiftModifier
            ):
                self.search_prev()
                return True
            if key == Qt.Key.Key_Down or key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.search_next()
                return True
        return super().eventFilter(obj, event)

    # --- 검색 ---

    def _collect_matches(self) -> list[tuple[int, int]]:
        term = self._search_edit.text()
        if term == "":
            return []
        text = self._editor.toPlainText()
        case_sensitive = self._case_btn.isChecked()
        haystack = text if case_sensitive else text.lower()
        needle = term if case_sensitive else term.lower()
        step = len(needle)
        matches: list[tuple[int, int]] = []
        start = 0
        while True:
            idx = haystack.find(needle, start)
            if idx == -1:
                break
            matches.append((idx, idx + step))
            start = idx + step
        return matches

    def _nearest_match_index(self, pos: int) -> int:
        for i, (start, _end) in enumerate(self._matches):
            if start >= pos:
                return i
        return 0

    def _mark_matches_dirty(self) -> None:
        self._matches_dirty = True

    def _ensure_fresh_matches(self) -> bool:
        """편집으로 스테일된 매치를 재수집한다. 재수집했으면 True."""
        if not self._matches_dirty:
            return False
        self._matches_dirty = False
        anchor = self._editor.textCursor().selectionStart()
        self._matches = self._collect_matches()
        self._current = self._nearest_match_index(anchor) if self._matches else -1
        return True

    def _perform_search(self) -> None:
        # 앵커는 선택 "시작" — 선택 끝을 쓰면 프리필된 그 단어를 건너뛰고
        # 다음/첫 일치로 튄다 (리뷰 지적 2).
        anchor = self._editor.textCursor().selectionStart()
        self._matches = self._collect_matches()
        self._matches_dirty = False
        if not self._matches:
            self._current = -1
            self._update_highlights()
            self._update_count_label()
            return
        self._current = self._nearest_match_index(anchor)
        self._select_current()

    def _select_current(self) -> None:
        start, end = self._matches[self._current]
        cursor = self._editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self._editor.setTextCursor(cursor)
        self._editor.ensureCursorVisible()
        self._update_highlights()
        self._update_count_label()

    def search_next(self) -> None:
        refreshed = self._ensure_fresh_matches()
        if not self._matches:
            return
        if not refreshed:
            # 재수집 직후에는 커서 기준 최근접 일치가 이미 current — 건너뛰지 않는다
            self._current = (self._current + 1) % len(self._matches)
        self._select_current()

    def search_prev(self) -> None:
        refreshed = self._ensure_fresh_matches()
        if not self._matches:
            return
        if not refreshed:
            self._current = (self._current - 1) % len(self._matches)
        self._select_current()

    def _update_highlights(self) -> None:
        selections = []
        for i, (start, end) in enumerate(self._matches):
            cursor = QTextCursor(self._editor.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setBackground(_SEARCH_CURRENT_BG if i == self._current else _SEARCH_MATCH_BG)
            selection = QTextEdit.ExtraSelection()
            selection.format = fmt
            selection.cursor = cursor
            selections.append(selection)
        self._editor.setExtraSelections(selections)

    def _update_count_label(self) -> None:
        total = len(self._matches)
        current = self._current + 1 if self._current >= 0 else 0
        self._count_label.setText(f"{current}/{total}")

    # --- 바꾸기 ---

    def replace_current(self) -> None:
        """현재 일치 1건을 치환하고 다음 일치로 이동한다."""
        self._ensure_fresh_matches()
        if not self._matches or self._current < 0:
            return
        start, end = self._matches[self._current]
        replacement = self._replace_edit.text()
        cursor = QTextCursor(self._editor.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.beginEditBlock()
        cursor.insertText(replacement)
        cursor.endEditBlock()
        new_pos = start + len(replacement)

        self._matches = self._collect_matches()
        self._matches_dirty = False
        if self._matches:
            self._current = self._nearest_match_index(new_pos)
            self._select_current()
        else:
            self._current = -1
            result_cursor = self._editor.textCursor()
            result_cursor.setPosition(min(new_pos, len(self._editor.toPlainText())))
            self._editor.setTextCursor(result_cursor)
            self._update_highlights()
            self._update_count_label()

    def replace_all(self) -> None:
        """전체 일치를 1 undo 단위로 치환하고 치환 건수를 일치 수 라벨에 표시한다."""
        self._ensure_fresh_matches()
        if not self._matches:
            return
        count = len(self._matches)
        replacement = self._replace_edit.text()
        edit_cursor = self._editor.textCursor()
        edit_cursor.beginEditBlock()
        for start, end in reversed(self._matches):
            cursor = QTextCursor(self._editor.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(replacement)
        edit_cursor.endEditBlock()

        self._matches = self._collect_matches()
        self._current = -1
        self._update_highlights()
        self._count_label.setText(f"{count}건 바꿈")
