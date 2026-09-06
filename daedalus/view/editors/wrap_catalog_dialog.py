# daedalus/view/editors/wrap_catalog_dialog.py
"""랩핑 스킬 카탈로그 창 (WP-WR 2단계, D2) — 등록된 플러그인 루트의 랩핑 가능
스킬을 **플러그인별 트리**로 보이고, 선택한 스킬을 WrappedSkill로 만든다.

발견·루트 등록의 실체는 `model/plugin/wrap_catalog`다 — 이 창은 트리 렌더 +
생성 호출부일 뿐이고, MCP `list_wrappable_skills`/`add_plugin_root`가 같은
모듈을 부른다(패리티 — 표면마다 다른 카탈로그를 보면 안 된다).

생성은 `actions/creation.make_component(window, "wrapped", ...)` + 등록 전
config.source 대입 + `window._register_component`(CreateComponentCmd)다 —
등록 전에 소스를 채우므로 undo 한 번에 컴포넌트가 통째로 사라지고 redo로
소스까지 그대로 돌아온다(중간 상태 없음).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

import daedalus.model.plugin.wrap_catalog as wrap_catalog

_ROLE_KIND = Qt.ItemDataRole.UserRole + 1      # "root" | "plugin" | "skill"
_ROLE_SOURCE = Qt.ItemDataRole.UserRole + 2    # skill 행: source 문자열
_ROLE_ROOT_PATH = Qt.ItemDataRole.UserRole + 3  # root 행: 등록 경로

_COLOR_WRAPPED = QColor("#448844")


def project_wrapped_sources(project) -> set[str]:
    """프로젝트가 이미 랩핑한 source 집합 (트리의 ✔ 표시 판정)."""
    out: set[str] = set()
    for skill in getattr(project, "skills", None) or []:
        if getattr(skill, "kind", "") == "wrapped_skill":
            source = getattr(getattr(skill, "config", None), "source", "") or ""
            if source:
                out.add(source)
    return out


def unique_component_name(project, base: str) -> str:
    """스킬·에이전트 이름과 겹치지 않는 이름 (겹치면 -2, -3 … 접미)."""
    taken = {c.name for c in list(getattr(project, "skills", None) or [])
             + list(getattr(project, "agents", None) or [])}
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


class WrapCatalogDialog(QDialog):
    """루트 → 플러그인 → 스킬 트리 + 루트 등록/제거 + 랩핑 스킬 생성."""

    def __init__(self, window, parent=None) -> None:
        super().__init__(parent or window)
        self._window = window
        self.setWindowTitle("랩핑 스킬 카탈로그")
        self.resize(560, 480)

        lay = QVBoxLayout(self)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["플러그인 / 스킬", "설명"])
        self._tree.setColumnWidth(0, 260)
        self._tree.itemDoubleClicked.connect(lambda *_: self.create_wrapped_from_selection())
        lay.addWidget(self._tree)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        lay.addWidget(self._status)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("루트 추가...")
        add_btn.setToolTip(
            "플러그인들이 들어 있는 폴더를 등록한다 — 마켓플레이스 저장소, "
            "~/.claude/plugins 계열 폴더, 플러그인 폴더 자체 전부 가능"
        )
        add_btn.clicked.connect(self.add_root_dialog)
        btn_row.addWidget(add_btn)

        remove_btn = QPushButton("루트 제거")
        remove_btn.clicked.connect(self.remove_selected_root)
        btn_row.addWidget(remove_btn)

        refresh_btn = QPushButton("새로고침")
        refresh_btn.clicked.connect(self.refresh)
        btn_row.addWidget(refresh_btn)

        btn_row.addStretch()

        create_btn = QPushButton("랩핑 스킬 생성")
        create_btn.setToolTip("선택한 스킬을 감싸는 WrappedSkill을 만든다 (더블클릭도 동일)")
        create_btn.clicked.connect(self.create_wrapped_from_selection)
        btn_row.addWidget(create_btn)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

        self.refresh()

    # ─────────────────────────── 트리 ───────────────────────────

    def refresh(self) -> None:
        self._tree.clear()
        wrapped = project_wrapped_sources(getattr(self._window, "_project", None))
        catalog = wrap_catalog.scan_catalog()
        if not catalog:
            self._status.setText(
                "등록된 플러그인 루트가 없습니다 — [루트 추가...]로 플러그인이 "
                "들어 있는 폴더를 등록하세요."
            )
            return
        total = 0
        for root, plugins in catalog:
            label = root.marketplace or root.path
            root_item = QTreeWidgetItem([f"📁 {label}", "" if plugins else "(플러그인 없음)"])
            root_item.setToolTip(0, root.path)
            root_item.setData(0, _ROLE_KIND, "root")
            root_item.setData(0, _ROLE_ROOT_PATH, root.path)
            self._tree.addTopLevelItem(root_item)
            for plugin in plugins:
                plugin_item = QTreeWidgetItem([f"🧩 {plugin.name}", plugin.description])
                plugin_item.setToolTip(0, plugin.path)
                plugin_item.setData(0, _ROLE_KIND, "plugin")
                root_item.addChild(plugin_item)
                for skill in plugin.skills:
                    total += 1
                    already = skill.source in wrapped
                    text = f"{skill.name} ✔" if already else skill.name
                    skill_item = QTreeWidgetItem([text, skill.description])
                    skill_item.setToolTip(0, skill.source)
                    skill_item.setData(0, _ROLE_KIND, "skill")
                    skill_item.setData(0, _ROLE_SOURCE, skill.source)
                    if already:
                        skill_item.setForeground(0, _COLOR_WRAPPED)
                        skill_item.setToolTip(
                            0, f"{skill.source} — 이미 이 프로젝트에서 랩핑됨"
                        )
                    plugin_item.addChild(skill_item)
                plugin_item.setExpanded(True)
            root_item.setExpanded(True)
        self._status.setText(f"랩핑 가능한 스킬 {total}개. ✔ = 이미 랩핑됨.")
        if total == 0:
            self._status.setText(
                "등록된 루트에서 스킬을 찾지 못했습니다 — 루트 아래에 "
                ".claude-plugin/plugin.json과 skills/<이름>/SKILL.md 구조가 "
                "있는지 확인하세요."
            )

    # ─────────────────────────── 루트 등록 ───────────────────────────

    def add_root_dialog(self) -> None:
        """폴더 선택 + 마켓플레이스 이름(선택) 입력 후 등록."""
        directory = QFileDialog.getExistingDirectory(self, "플러그인 루트 선택")
        if not directory:
            return
        marketplace, ok = QInputDialog.getText(
            self, "마켓플레이스 이름",
            "이 루트의 마켓플레이스 이름 (비우면 자동 감지/bare):",
        )
        if not ok:
            return
        self.add_root(directory, marketplace.strip())

    def add_root(self, path: str, marketplace: str = "") -> None:
        """등록의 실체 — 테스트·프로그램 경로가 다이얼로그 없이 부른다."""
        wrap_catalog.add_plugin_root(path, marketplace)
        self.refresh()

    def remove_selected_root(self) -> None:
        item = self._tree.currentItem()
        while item is not None and item.data(0, _ROLE_KIND) != "root":
            item = item.parent()
        if item is None:
            self._status.setText("제거할 루트 행을 먼저 선택하세요.")
            return
        wrap_catalog.remove_plugin_root(item.data(0, _ROLE_ROOT_PATH))
        self.refresh()

    # ─────────────────────────── 생성 ───────────────────────────

    def create_wrapped_from_selection(self) -> object | None:
        """선택한 스킬 행 → WrappedSkill 생성 (CreateComponentCmd — undo 가능)."""
        item = self._tree.currentItem()
        if item is None or item.data(0, _ROLE_KIND) != "skill":
            self._status.setText("랩핑할 스킬 행을 먼저 선택하세요.")
            return None
        source = item.data(0, _ROLE_SOURCE)
        return self.create_wrapped(source)

    def create_wrapped(self, source: str) -> object | None:
        """source 문자열로 WrappedSkill을 만들어 프로젝트에 등록한다."""
        from daedalus.view.actions.creation import make_component

        window = self._window
        project = getattr(window, "_project", None)
        if project is None:
            self._status.setText("열린 프로젝트가 없습니다.")
            return None
        _, _, skill_name = source.partition(":")
        name = unique_component_name(project, skill_name or "wrapped-skill")
        component = make_component(window, "wrapped", name)
        if component is None:  # pragma: no cover — kind는 고정 문자열
            return None
        # 등록 **전에** 소스를 채운다 — CreateComponentCmd가 완성된 객체를 넣고
        # 빼므로 undo/redo에 소스 없는 중간 상태가 존재하지 않는다.
        component.config.source = source
        window._register_component(component)
        self._status.setText(f"'{name}' 생성됨 — source: {source}")
        self.refresh()
        return component
