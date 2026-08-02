# daedalus/view/widgets/tag_input.py
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class _TagChip(QWidget):
    """개별 태그 칩 — 이름 + x 버튼."""

    remove_requested = Signal(str)

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._name = name
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(2)
        lay.addWidget(QLabel(name))
        btn = QPushButton("x")
        btn.setFixedSize(16, 16)
        btn.clicked.connect(lambda: self.remove_requested.emit(self._name))
        lay.addWidget(btn)

    @property
    def name(self) -> str:
        return self._name


class TagInput(QWidget):
    """태그 입력 위젯 — list[str] 편집. Enter로 추가, x로 제거."""

    tags_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tags: list[str] = []
        self._candidates: list[str] = []
        self._completer: QCompleter | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        self._input = QLineEdit()
        self._input.setPlaceholderText("입력 후 Enter")
        self._input.returnPressed.connect(self._on_enter)
        lay.addWidget(self._input)

        self._chips_widget = QWidget()
        self._chips_layout = QVBoxLayout(self._chips_widget)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(2)
        self._chips_layout.addStretch()
        lay.addWidget(self._chips_widget)

    def set_candidates(self, candidates: list[str]) -> None:
        """자동완성 후보 목록을 부착한다 (부분 일치, 대소문자 무시).

        카탈로그/프로젝트 변화에 맞춰 재호출되면 이전 QCompleter를 교체한다.
        """
        self._candidates = list(candidates)
        completer = QCompleter(self._candidates, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._input.setCompleter(completer)
        self._completer = completer

    def get_candidates(self) -> list[str]:
        return list(self._candidates)

    def get_tags(self) -> list[str]:
        return list(self._tags)

    def set_tags(self, tags: list[str]) -> None:
        self._tags = list(tags)
        self._rebuild()

    def add_tag(self, tag: str) -> None:
        tag = tag.strip()
        if not tag or tag in self._tags:
            return
        self._tags.append(tag)
        self._rebuild()
        self.tags_changed.emit()

    def remove_tag(self, tag: str) -> None:
        if tag in self._tags:
            self._tags.remove(tag)
            self._rebuild()
            self.tags_changed.emit()

    def _on_enter(self) -> None:
        text = self._input.text().strip()
        if text:
            self.add_tag(text)
            self._input.clear()

    def _rebuild(self) -> None:
        while self._chips_layout.count() > 1:
            child = self._chips_layout.takeAt(0)
            if child is not None:
                w = child.widget()
                if w is not None:
                    w.deleteLater()
        for tag in self._tags:
            chip = _TagChip(tag)
            chip.remove_requested.connect(self.remove_tag)
            self._chips_layout.insertWidget(self._chips_layout.count() - 1, chip)


# 동적 도구/에이전트 후보 제공자 — app.py가 프로젝트 로드 시 설정한다(WP-TM).
# ALLOWED_TOOLS/TOOLS/DISALLOWED_TOOLS 필드의 TagInput이 생성 시점에 이 제공자를
# 조회해 카탈로그+빌트인+에이전트 후보를 채운다. None이면 빈 목록(자동완성 없음).
_TOOL_CANDIDATE_PROVIDER: Callable[[], list[str]] | None = None


def set_tool_candidate_provider(provider: Callable[[], list[str]] | None) -> None:
    """ALLOWED_TOOLS/TOOLS/DISALLOWED_TOOLS TagInput이 표시할 후보 제공자를 등록한다."""
    global _TOOL_CANDIDATE_PROVIDER
    _TOOL_CANDIDATE_PROVIDER = provider


def get_tool_candidates() -> list[str]:
    """등록된 동적 제공자에서 도구/에이전트 후보 목록을 가져온다 (없으면 빈 목록)."""
    if _TOOL_CANDIDATE_PROVIDER is not None:
        return list(_TOOL_CANDIDATE_PROVIDER())
    return []
