# daedalus/view/panels/external_registry.py
"""레지스트리 도크의 **카탈로그 표면** 두 조각 (WP-C).

`registry_panel`의 섹션은 "프로젝트에 있는 컴포넌트"를 그린다. 여기 둘은 그
반대편 — **아직 프로젝트 것이 아닌 카탈로그 항목**을 그리고, 우클릭으로
프로젝트에 들여오는 자리다.

- `UnregisteredAgentsList`: 🔌 탭 하단. 사용 선언한 플러그인의 에이전트 중
  아직 컴포넌트로 등록되지 않은 것(`wrap_catalog.unregistered_plugin_agents`).
- `ExternalSkillsSection`: 🧷 탭 전체. 외부 플러그인 스킬 참조 목록과 그것을
  `skills:`에 가진 에이전트(`wrap_catalog.used_plugin_skill_refs` /
  `skill_ref_users`).

**판정은 전부 모델에 묻는다** — 여기서 세거나 거르지 않는다(원칙 1). 등록·추가의
실체도 `view/actions/external_registration`이고 이 위젯은 시그널만 쏜다.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.plugin.kinds import spec_by_config_kind
from daedalus.view.kind_ui import ui_by_config_kind

#: 아직 프로젝트 것이 아닌 항목의 글자색 — 등록된 컴포넌트와 한눈에 갈린다.
_COLOR_CATALOG = QColor("#7a6a78")
_ROLE_VALUE = Qt.ItemDataRole.UserRole + 11


def register_role_noun(config_kind: str) -> str:
    """이 종류로 등록하면 **무엇이 되는가** — 종류 선언이 답한다(표를 두지 않는다).

    fork 실행 기반이면 "fork 에이전트", 아니면 캔버스에 놓이는 "그래프 노드"다.
    """
    return "fork 에이전트" if spec_by_config_kind(config_kind).is_fork_base else "그래프 노드"


def _plain_list() -> QListWidget:
    """드래그하지 않는 목록 — 카탈로그 항목은 아직 컴포넌트가 아니라 놓을 수 없다."""
    widget = QListWidget()
    widget.setDragEnabled(False)
    widget.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
    widget.setMinimumHeight(30)
    widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    return widget


def _catalog_item(text: str, value: str, tooltip: str) -> QListWidgetItem:
    item = QListWidgetItem(text)
    item.setData(_ROLE_VALUE, value)
    item.setToolTip(tooltip)
    item.setForeground(_COLOR_CATALOG)
    font = item.font()
    font.setItalic(True)
    item.setFont(font)
    return item


class UnregisteredAgentsList(QWidget):
    """🔌 탭 하단 — 사용 선언한 플러그인의 **미등록** 에이전트.

    등록 역할은 이 섹션이 담는 종류들에서 그대로 나온다(`kinds` 인자) — 메뉴
    항목을 손으로 적으면 새 역할이 조용히 빠진다.
    """

    register_requested = Signal(str, str)  # agent_type, config_kind

    def __init__(self, kinds: tuple[str, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._kinds = kinds
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self._header = QLabel("카탈로그 — 미등록")
        self._header.setToolTip(
            "사용 선언한 외부 플러그인이 동봉한 에이전트 중 아직 이 프로젝트에 "
            "등록하지 않은 것입니다. 우클릭해서 역할을 골라 등록하세요."
        )
        lay.addWidget(self._header)
        self._list = _plain_list()
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        lay.addWidget(self._list)

    def set_agents(self, agents: list) -> None:
        """`CataloguedAgent` 목록을 다시 그린다 (모델이 이미 걸러 준 것)."""
        self._list.clear()
        self._header.setText(f"카탈로그 — 미등록 ({len(agents)})")
        for agent in agents:
            self._list.addItem(_catalog_item(
                f"🔌 {agent.agent_type}",
                agent.agent_type,
                agent.description or agent.agent_type,
            ))

    def _on_context_menu(self, pos: QPoint) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        agent_type = item.data(_ROLE_VALUE)
        menu = QMenu(self)
        for config_kind in self._kinds:
            ui = ui_by_config_kind(config_kind)
            action = menu.addAction(
                f"{ui.icon} {register_role_noun(config_kind)}로 등록"
            )
            if action is not None:
                action.triggered.connect(
                    lambda _checked=False, k=config_kind: (
                        self.register_requested.emit(agent_type, k)
                    )
                )
        menu.exec(self._list.mapToGlobal(pos))


class ExternalSkillsSection(QWidget):
    """🧷 EXTERNAL SKILLS 탭 — 외부 플러그인 스킬 참조 목록.

    컴포넌트 종류가 아니라 **카탈로그 항목**의 섹션이다(프로젝트에는 이 스킬의
    컴포넌트가 없다 — 쓰는 방법은 fork 에이전트 `skills:` 참조 하나뿐이다, WP-B).
    """

    add_requested = Signal()  # "+" → 외부 플러그인 카탈로그 창
    attach_requested = Signal(str, object)  # skill_ref, agent

    #: 탭 툴팁 + 섹션 제목 (`_RegistrySection.label_text`와 같은 자리).
    label_text = "🧷 EXTERNAL SKILLS"
    tab_label = "🧷"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._agents: list = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(2)
        hdr.addWidget(QLabel(self.label_text))
        hdr.addStretch()
        btn = QPushButton("+")
        btn.setFixedSize(20, 20)
        btn.setToolTip("외부 플러그인 카탈로그를 엽니다 — 거기서 사용 선언을 합니다.")
        btn.clicked.connect(self.add_requested)
        hdr.addWidget(btn)
        lay.addLayout(hdr)

        self._list = _plain_list()
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        lay.addWidget(self._list)

    def set_rows(
        self, refs: list[str], users: dict[str, list[str]], agents: list
    ) -> None:
        """참조 목록 + 사용 중인 에이전트 이름(모델 판정)을 다시 그린다."""
        self._agents = list(agents)
        self._list.clear()
        for ref in refs:
            names = users.get(ref, [])
            suffix = f"  ✔ {', '.join(names)}" if names else ""
            item = _catalog_item(
                f"🧷 {ref}{suffix}",
                ref,
                (
                    f"{ref} — 쓰는 에이전트: {', '.join(names)}"
                    if names
                    else f"{ref} — 아직 아무 에이전트도 쓰지 않습니다."
                ),
            )
            self._list.addItem(item)

    def _on_context_menu(self, pos: QPoint) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        ref = item.data(_ROLE_VALUE)
        menu = QMenu(self)
        submenu = menu.addMenu("fork 에이전트 skills에 추가")
        if submenu is None:  # pragma: no cover - Qt가 None을 주는 일은 없다
            return
        self._fill_agent_submenu(submenu, ref)
        menu.exec(self._list.mapToGlobal(pos))

    def _fill_agent_submenu(self, submenu: QMenu, ref: str) -> None:
        """`skills` 칸을 가진 에이전트를 **역할별로 나눠** 담는다.

        fork 에이전트가 먼저다(이 참조의 본래 용도 — 서브에이전트 프리로드).
        워크플로 에이전트도 `skills`를 가지므로 함께 내되 구역을 나눈다.
        `skills` 칸이 없는 종류(외부 정본 — 산출 파일이 없다)는 아예 없다.
        """
        from daedalus.model.plugin.field_matrix import AgentField
        from daedalus.model.plugin.kinds import spec_for

        candidates = [
            a for a in self._agents
            if AgentField.SKILLS in spec_for(a).field_matrix
        ]
        if not candidates:
            action = submenu.addAction("(skills를 가진 에이전트가 없습니다)")
            if action is not None:
                action.setEnabled(False)
            return
        groups = (
            ("fork 에이전트", [a for a in candidates if a.IS_FORK_BASE]),
            ("워크플로 에이전트", [a for a in candidates if not a.IS_FORK_BASE]),
        )
        for title, agents in groups:
            if not agents:
                continue
            submenu.addSection(title)
            for agent in sorted(agents, key=lambda a: a.name):
                from daedalus.view.kind_ui import ui_for

                already = ref in (getattr(agent.config, "skills", None) or [])
                action = submenu.addAction(
                    f"{ui_for(agent).icon} {agent.name}"
                    + ("  ✔" if already else "")
                )
                if action is None:  # pragma: no cover
                    continue
                action.setEnabled(not already)
                if already:
                    action.setToolTip("이미 이 참조를 가지고 있습니다.")
                action.triggered.connect(
                    lambda _checked=False, a=agent: (
                        self.attach_requested.emit(ref, a)
                    )
                )
