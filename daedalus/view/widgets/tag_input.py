# daedalus/view/widgets/tag_input.py
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCompleter,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def _make_completer(candidates: list[str], parent: QWidget) -> QCompleter:
    """TagInput 계열이 공유하는 자동완성 구성 (부분 일치, 대소문자 무시).

    UnfilteredPopupCompletion — 빈 입력에서도 전체 목록이 뜬다
    (사용자 요청: "아무것도 안 입력하면 아무것도 안 뜬다").
    타이핑하면 MatchContains로 좁혀진다.
    """
    completer = QCompleter(candidates, parent)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    completer.setFilterMode(Qt.MatchFlag.MatchContains)
    completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
    completer.setMaxVisibleItems(15)
    return completer


class _TagChip(QWidget):
    """개별 태그 칩 — 제자리 편집 가능한 QLineEdit + x 버튼.

    QLabel이었을 때는 오타 하나 고치려면 지우고 다시 타이핑해야 했다
    (사용자 보고 — 긴 도구 패턴·glob에서 특히 아프다). 편집 확정은
    ``edit_committed(old, new)``로 알리기만 하고 유효성 판단(빈 값·중복)은
    TagInput이 한다 — 칩은 자기 형제 태그를 모른다.
    """

    remove_requested = Signal(str)
    edit_committed = Signal(str, str)  # (old, new) — new가 old와 다를 때만

    def __init__(
        self,
        name: str,
        candidates: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._name = name
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(2)
        self._edit = QLineEdit(name)
        if candidates:
            self._edit.setCompleter(_make_completer(candidates, self))
        # editingFinished는 Enter와 포커스 아웃 양쪽에서 온다(연달아 두 번 올 수
        # 있다). 커밋 후 _name을 갱신하고 되돌림 시 텍스트를 _name으로 복원하므로,
        # 두 번째 발화는 "텍스트 == _name"이라 자연히 no-op이 된다.
        self._edit.editingFinished.connect(self._on_editing_finished)
        lay.addWidget(self._edit)
        btn = QPushButton("x")
        btn.setFixedSize(16, 16)
        btn.clicked.connect(lambda: self.remove_requested.emit(self._name))
        lay.addWidget(btn)

    @property
    def name(self) -> str:
        return self._name

    def _on_editing_finished(self) -> None:
        new = self._edit.text().strip()
        if new == self._name:
            return
        self.edit_committed.emit(self._name, new)

    def accept_edit(self, new: str) -> None:
        """TagInput이 편집을 승인했다 — 이후 x 버튼·재편집이 새 이름 기준."""
        self._name = new
        self._edit.setText(new)

    def revert_edit(self) -> None:
        """빈 값·중복 편집을 되돌린다 (삭제는 x 버튼의 몫)."""
        self._edit.setText(self._name)


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

        카탈로그/프로젝트 변화에 맞춰 재호출되면 이전 QCompleter를 교체하고,
        기존 칩들도 재구성해 같은 후보를 물린다 (칩 편집도 자동완성을 받는다).
        """
        self._candidates = list(candidates)
        completer = _make_completer(self._candidates, self)
        self._input.setCompleter(completer)
        self._completer = completer
        self._rebuild()

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

    def _on_chip_edited(self, chip: _TagChip, old: str, new: str) -> None:
        """칩 제자리 편집의 유효성 판정 — 빈 값·중복은 되돌린다.

        빈 값을 삭제로 해석하지 않는 이유: 삭제는 x 버튼이라는 명시 경로가
        따로 있고, 포커스 아웃으로도 커밋되는 편집에서 지우다 만 값이
        조용히 태그를 없애면 사고다.
        """
        if not new or new in self._tags:
            chip.revert_edit()
            return
        try:
            idx = self._tags.index(old)
        except ValueError:
            chip.revert_edit()
            return
        self._tags[idx] = new
        chip.accept_edit(new)
        self.tags_changed.emit()

    def _rebuild(self) -> None:
        while self._chips_layout.count() > 1:
            child = self._chips_layout.takeAt(0)
            if child is not None:
                w = child.widget()
                if w is not None:
                    # hide 후 부모 분리 — deleteLater만 하면 이벤트 루프가 돌기
                    # 전까지 자식으로 남아 findChildren류 순회가 죽은 칩을 잡는다.
                    # hide를 먼저 해야 최상위 창 깜빡임이 없다(hook_panel 관례).
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
        for tag in self._tags:
            chip = _TagChip(tag, candidates=self._candidates)
            chip.remove_requested.connect(self.remove_tag)
            chip.edit_committed.connect(
                lambda old, new, c=chip: self._on_chip_edited(c, old, new)
            )
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


# 상태 접근 선언(reads/writes) TagInput의 후보 제공자 — app.py가 프로젝트 로드 시
# 설정한다(WP-BB). 프로젝트 블랙보드의 "클래스" + "클래스.필드" 전체를 반환한다.
# 호출 시점 스냅샷(생성 시 1회 조회) — 블랙보드 변경 시 실시간 갱신은 하지 않는다
# (get_tool_candidates와 동일한 정책).
_BLACKBOARD_CANDIDATE_PROVIDER: Callable[[], list[str]] | None = None


def set_blackboard_candidate_provider(provider: Callable[[], list[str]] | None) -> None:
    """reads/writes TagInput이 표시할 블랙보드 클래스/필드 후보 제공자를 등록한다."""
    global _BLACKBOARD_CANDIDATE_PROVIDER
    _BLACKBOARD_CANDIDATE_PROVIDER = provider


def get_blackboard_candidates() -> list[str]:
    """등록된 동적 제공자에서 블랙보드 클래스/필드 후보 목록을 가져온다 (없으면 빈 목록)."""
    if _BLACKBOARD_CANDIDATE_PROVIDER is not None:
        return list(_BLACKBOARD_CANDIDATE_PROVIDER())
    return []


# HOOKS TagInput의 훅 이름 후보 제공자 — app.py가 프로젝트 로드 시 등록한다
# (전역 훅 포함, A1). 위 둘과 완전히 같은 패턴이고 소비처도 같다(skill_editor의
# `_wire_tool_candidates`). 원래 preset_picker.py에 있었는데, 그 모듈이 소유하던
# 체크리스트 위젯이 TagInput으로 대체되면서 남은 것이 이 제공자뿐이라 후보를
# 쓰는 위젯 옆으로 옮겼다.
_HOOK_NAME_PROVIDER: Callable[[], list[str]] | None = None


def set_hook_name_provider(provider: Callable[[], list[str]] | None) -> None:
    """HOOKS TagInput이 표시할 훅 이름 목록 제공자를 등록한다."""
    global _HOOK_NAME_PROVIDER
    _HOOK_NAME_PROVIDER = provider


def get_hook_names() -> list[str]:
    """등록된 제공자에서 현재 훅 이름 목록을 가져온다 (없으면 빈 목록)."""
    if _HOOK_NAME_PROVIDER is not None:
        return list(_HOOK_NAME_PROVIDER())
    return []


# MCP 서버 이름 후보 (WP-WR) — 에이전트 MCP_SERVERS TagInput용. 사용 선언된
# 외부 플러그인이 동봉 .mcp.json으로 제공하는 서버 + 프로젝트 mcp_server_defs
# 이름을 app.set_project가 등록한다. tools 후보에는 넣지 않는다(개별 도구
# 목록 미지원 — 사용자 확정). 위 provider들과 같은 패턴·같은 스냅샷 규약.
_MCP_SERVER_PROVIDER: Callable[[], list[str]] | None = None


def set_mcp_server_candidate_provider(
    provider: Callable[[], list[str]] | None,
) -> None:
    """MCP_SERVERS TagInput이 표시할 서버 이름 목록 제공자를 등록한다."""
    global _MCP_SERVER_PROVIDER
    _MCP_SERVER_PROVIDER = provider


def get_mcp_server_candidates() -> list[str]:
    """등록된 제공자에서 현재 MCP 서버 이름 목록을 가져온다 (없으면 빈 목록)."""
    if _MCP_SERVER_PROVIDER is not None:
        return list(_MCP_SERVER_PROVIDER())
    return []
