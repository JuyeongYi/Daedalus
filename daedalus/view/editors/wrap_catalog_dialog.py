# daedalus/view/editors/wrap_catalog_dialog.py
"""외부 플러그인 카탈로그 창 (WP-WR, D2) — 등록된 **마켓플레이스 폴더**의 외부
플러그인·스킬을 트리로 보이고, 체크박스로 "이 프로젝트에서 사용"을 선언한다.

- 발견·폴더 등록의 실체는 `model/plugin/wrap_catalog`(전역 —
  `~/.daedalus/external_marketplaces.json`), **사용 선언은 프로젝트 모델**
  (`PluginProject.external_plugins` — 사용자 확정: 프로젝트 단위 저장)이다.
  체크 토글은 SetAttrCmd라 undo되고 저장 파일에 왕복한다.
- **이 창의 동작은 등록과 선언뿐이다**(사용자 확정) — 실제 랩핑(인보크 지시
  산출 + dependencies/enabledPlugins 배선)은 **빌드가** 한다. 외부 스킬을
  워크플로 단계로 놓고 싶을 때만 WrappedSkill을 만드는데, 그 생성은 기존
  경로(레지스트리 🔗 탭·캔버스 "여기에 만들기"·MCP `create_skill(source=)`)
  소관이라 여기에는 생성 버튼이 없다. 스킬 행은 후보 확인용이고 ✔는 이미
  랩핑된 소스 표시다.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
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

_ROLE_KIND = Qt.ItemDataRole.UserRole + 1      # "marketplace" | "plugin" | "skill"
_ROLE_SOURCE = Qt.ItemDataRole.UserRole + 2    # skill 행: source 문자열
_ROLE_FOLDER_PATH = Qt.ItemDataRole.UserRole + 3  # marketplace 행: 등록 경로
_ROLE_PLUGIN_ID = Qt.ItemDataRole.UserRole + 4    # plugin 행: 설치 식별자
#: 미설치 plugin 행: marketplace.json 선언 source(원격 조회 재료). 설치된
#: 플러그인은 None — 스킬이 이미 로컬에 있어 조회할 이유가 없다.
_ROLE_SOURCE_SPEC = Qt.ItemDataRole.UserRole + 5

_COLOR_WRAPPED = QColor("#448844")
_COLOR_MUTED = QColor("#888888")


def project_wrapped_sources(project) -> set[str]:
    """프로젝트가 이미 랩핑한 source 집합 (트리의 ✔ 표시 판정)."""
    out: set[str] = set()
    for skill in getattr(project, "skills", None) or []:
        if getattr(skill, "kind", "") == "wrapped_skill":
            source = getattr(getattr(skill, "config", None), "source", "") or ""
            if source:
                out.add(source)
    return out


class WrapCatalogDialog(QDialog):
    """마켓플레이스 폴더 → 플러그인(체크=사용 선언) → 스킬 트리."""

    def __init__(self, window, parent=None) -> None:
        super().__init__(parent or window)
        self._window = window
        # 원격에서 받아온 스킬 이름(plugin_id → [이름]) — 창이 열려 있는 동안의
        # 표시용이다. 영속 캐시는 remote_skills가 홈에 따로 둔다.
        self._remote_skills: dict[str, list[str]] = {}
        self.setWindowTitle("외부 플러그인 카탈로그")
        self.resize(560, 480)

        lay = QVBoxLayout(self)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["마켓플레이스 / 플러그인 / 스킬", "설명"])
        self._tree.setColumnWidth(0, 280)
        # 플러그인 행 체크박스 = 이 프로젝트에서 사용 선언(external_plugins).
        # refresh가 blockSignals로 트리를 다시 그리므로 사람 토글에서만 온다.
        self._tree.itemChanged.connect(self._on_item_changed)
        lay.addWidget(self._tree)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        lay.addWidget(self._status)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("마켓플레이스 폴더 추가...")
        add_btn.setToolTip(
            "플러그인들이 들어 있는 마켓플레이스 폴더를 등록한다 — 마켓 저장소, "
            "~/.claude/plugins 계열 폴더, 플러그인 폴더 자체 전부 가능"
        )
        add_btn.clicked.connect(self.add_marketplace_dialog)
        btn_row.addWidget(add_btn)

        remove_btn = QPushButton("폴더 제거")
        remove_btn.clicked.connect(self.remove_selected_marketplace)
        btn_row.addWidget(remove_btn)

        refresh_btn = QPushButton("새로고침")
        refresh_btn.clicked.connect(self.refresh)
        btn_row.addWidget(refresh_btn)

        # 미설치 플러그인의 스킬 이름만 원격에서 받아온다(WP-WR) — **버튼을
        # 누를 때만 인터넷 요청이 나간다**. 목록을 여는 것만으로는 절대 나가지
        # 않는다(수백 개를 일괄 조회하면 API 한도에 걸린다).
        self._fetch_btn = QPushButton("스킬 목록 받아오기")
        self._fetch_btn.setToolTip(
            "선택한 **미설치** 플러그인의 스킬 이름을 GitHub에서 조회한다"
            "(클론 없이 디렉토리 목록 한 번). 설명은 설치 후에 보인다."
        )
        self._fetch_btn.clicked.connect(self.fetch_selected_skills)
        btn_row.addWidget(self._fetch_btn)

        btn_row.addStretch()

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

        self.refresh()

    # ─────────────────────────── 트리 ───────────────────────────

    def refresh(self) -> None:
        # 재구성 중의 setCheckState가 itemChanged를 쏘면 편집 루프가 돈다 —
        # 사람 토글만 시그널이 되도록 트리를 조용히 다시 그린다.
        self._tree.blockSignals(True)
        try:
            total, used_count = self._rebuild_tree()
        finally:
            self._tree.blockSignals(False)
        if total is None:
            return
        self._status.setText(
            f"외부 스킬 {total}개. 체크 = 이 프로젝트에서 사용(빌드가 의존성 "
            f"자동 배선, 현재 {used_count}개). ✔ = 이미 랩핑됨."
        )
        if total == 0:
            self._status.setText(
                "등록된 마켓플레이스 폴더에서 스킬을 찾지 못했습니다 — 폴더 "
                "아래에 .claude-plugin/plugin.json과 skills/<이름>/SKILL.md "
                "구조가 있는지 확인하세요."
            )

    def _rebuild_tree(self) -> tuple[int | None, int]:
        """트리 재구성. (스킬 수 | None=폴더 없음, 사용 선언된 플러그인 수)."""
        self._tree.clear()
        project = getattr(self._window, "_project", None)
        wrapped = project_wrapped_sources(project)
        declared = set(getattr(project, "external_plugins", None) or [])
        catalog = wrap_catalog.scan_catalog()
        if not catalog:
            self._status.setText(
                "등록된 마켓플레이스 폴더가 없습니다 — [마켓플레이스 폴더 "
                "추가...]로 플러그인이 들어 있는 폴더를 등록하세요."
            )
            return None, 0
        total = 0
        used_count = 0
        for folder, plugins in catalog:
            label = folder.marketplace or folder.path
            folder_item = QTreeWidgetItem(
                [f"📁 {label}", "" if plugins else "(플러그인 없음)"]
            )
            folder_item.setToolTip(0, folder.path)
            folder_item.setData(0, _ROLE_KIND, "marketplace")
            folder_item.setData(0, _ROLE_FOLDER_PATH, folder.path)
            self._tree.addTopLevelItem(folder_item)
            # 마켓이 선언만 하고 실물은 아직 안 받은 플러그인은 별도 그룹으로
            # 접어 둔다(사용자 보고 2026-09-07 — 공식 마켓은 291개 선언 중 로컬
            # 실물이 40개였다. 한 목록에 쏟으면 설치된 것을 찾을 수 없다).
            # **사용 선언은 여기서도 된다** — 스킬 목록과 랩핑만 설치 후다.
            uninstalled = [p for p in plugins if not p.installed]
            group: QTreeWidgetItem | None = None
            if uninstalled:
                group = QTreeWidgetItem(
                    [f"⋯ 미설치 ({len(uninstalled)})",
                     "이름·설명만 안다 — 체크(사용 선언)는 가능, 스킬은 설치 후"],
                )
                group.setData(0, _ROLE_KIND, "uninstalled-group")
                group.setForeground(0, _COLOR_MUTED)
                folder_item.addChild(group)
            for plugin in plugins:
                used = plugin.plugin_id in declared
                if used:
                    used_count += 1
                parent_item = group if (not plugin.installed and group is not None) else folder_item
                # 아이콘으로 실물 유무를 가른다(사용자 요청) — 🧩 받음 / ❌ 아직
                # 안 받음. 미설치도 체크(사용 선언)는 되므로 색만으로는 약하다.
                icon = "🧩" if plugin.installed else "❌"
                plugin_item = QTreeWidgetItem(
                    [f"{icon} {plugin.name}", plugin.description]
                )
                if not plugin.installed:
                    plugin_item.setForeground(0, _COLOR_MUTED)
                    plugin_item.setToolTip(
                        0,
                        f"{plugin.plugin_id}\n아직 받지 않음 — 사용 선언은 지금 "
                        f"가능하고(빌드가 의존성을 배선), 스킬 목록과 랩핑은 "
                        f"설치 후에 됩니다.",
                    )
                else:
                    plugin_item.setToolTip(0, f"{plugin.plugin_id}\n{plugin.path}")
                plugin_item.setData(0, _ROLE_KIND, "plugin")
                plugin_item.setData(0, _ROLE_PLUGIN_ID, plugin.plugin_id)
                plugin_item.setData(
                    0, _ROLE_SOURCE_SPEC,
                    None if plugin.installed else plugin.source_spec,
                )
                plugin_item.setFlags(
                    plugin_item.flags() | Qt.ItemFlag.ItemIsUserCheckable
                )
                plugin_item.setCheckState(
                    0, Qt.CheckState.Checked if used else Qt.CheckState.Unchecked
                )
                parent_item.addChild(plugin_item)
                if not plugin.installed:
                    for name in self._remote_skills.get(plugin.plugin_id, []):
                        source = f"{plugin.plugin_id}:{name}"
                        total += 1
                        already = source in wrapped
                        remote_item = QTreeWidgetItem(
                            [f"{name} ✔" if already else name, "(설명은 설치 후)"],
                        )
                        remote_item.setToolTip(0, source)
                        remote_item.setData(0, _ROLE_KIND, "skill")
                        remote_item.setData(0, _ROLE_SOURCE, source)
                        if already:
                            remote_item.setForeground(0, _COLOR_WRAPPED)
                        plugin_item.addChild(remote_item)
                    plugin_item.setExpanded(bool(self._remote_skills.get(plugin.plugin_id)))
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
                plugin_item.setExpanded(plugin.installed)
            folder_item.setExpanded(True)
        return total, used_count

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """플러그인 체크 토글 → external_plugins 선언 (SetAttrCmd — undo 가능)."""
        if column != 0 or item.data(0, _ROLE_KIND) != "plugin":
            return
        self.set_plugin_used(
            item.data(0, _ROLE_PLUGIN_ID),
            item.checkState(0) == Qt.CheckState.Checked,
        )
        # itemChanged를 쏜 아이템을 같은 호출 안에서 clear()로 파괴하면 Qt가
        # 시그널 반환 경로에서 그 아이템을 다시 만져 간헐적 access violation이
        # 난다(실측 — 플레이키 크래시). 트리 재구성은 이벤트 루프로 미룬다.
        # 수신 컨텍스트(self)를 주면 다이얼로그가 먼저 닫혀도 죽은 위젯에
        # 발화하지 않는다(WP-WS 0ms 디바운스 수명 함정과 같은 결).
        QTimer.singleShot(0, self, self.refresh)

    def set_plugin_used(self, plugin_id: str, used: bool) -> bool:
        """external_plugins 선언 토글의 실체 — 새 리스트를 SetAttrCmd로 대입
        (제자리 수정이면 undo가 같은 객체를 가리킨다). 변화 없으면 False."""
        from daedalus.view.commands.attr_commands import SetAttrCmd

        project = getattr(self._window, "_project", None)
        if project is None:
            return False
        declared = list(getattr(project, "external_plugins", None) or [])
        if used == (plugin_id in declared):
            return False
        new_list = (
            [*declared, plugin_id] if used
            else [p for p in declared if p != plugin_id]
        )
        self._window._project_vm.execute(SetAttrCmd(
            project,
            "external_plugins",
            new_list,
            label=("외부 플러그인 사용 선언: " if used
                   else "외부 플러그인 사용 해제: ") + plugin_id,
            script=f'set_external_plugins({new_list!r})',
        ))
        return True

    def fetch_selected_skills(self) -> list[str] | None:
        """선택한 미설치 플러그인의 스킬 이름을 원격에서 받아 트리에 채운다.

        **이 메서드가 이 창에서 인터넷 요청이 나가는 유일한 지점이다.**
        받아온 이름은 캐시되고(커밋 SHA 키), 다음 새로고침부터는 요청 없이
        그대로 보인다.
        """
        from daedalus.model.plugin import remote_skills

        item = self._tree.currentItem()
        if item is None or item.data(0, _ROLE_KIND) != "plugin":
            self._status.setText("스킬을 받아올 플러그인 행을 먼저 선택하세요.")
            return None
        plugin_id = item.data(0, _ROLE_PLUGIN_ID)
        spec = item.data(0, _ROLE_SOURCE_SPEC)
        if spec is None:
            self._status.setText(
                f"'{plugin_id}'는 이미 설치돼 있어 스킬이 목록에 보입니다."
            )
            return None
        self._status.setText(f"'{plugin_id}' 스킬 목록을 받아오는 중…")
        try:
            names = remote_skills.skill_names(plugin_id, spec)
        except remote_skills.RemoteSkillsError as exc:
            self._status.setText(f"받아오지 못했습니다 — {exc}")
            return None
        if names is None:
            self._status.setText(
                f"'{plugin_id}'는 GitHub 저장소가 아니어서 원격 조회를 "
                "지원하지 않습니다 — 설치 후 확인하세요."
            )
            return None
        self._remote_skills[plugin_id] = names
        self.refresh()
        self._status.setText(
            f"'{plugin_id}' 스킬 {len(names)}개를 받아왔습니다 — 이름만입니다"
            "(설명은 설치 후). 캔버스로 끌어 워크플로 단계로 감쌀 수 있습니다."
        )
        return names

    # ─────────────────────────── 마켓플레이스 폴더 등록 ───────────────────────────

    def add_marketplace_dialog(self) -> None:
        """폴더 선택 + 마켓플레이스 이름(선택) 입력 후 등록."""
        directory = QFileDialog.getExistingDirectory(self, "마켓플레이스 폴더 선택")
        if not directory:
            return
        marketplace, ok = QInputDialog.getText(
            self, "마켓플레이스 이름",
            "이 폴더의 마켓플레이스 이름 (비우면 자동 감지/bare):",
        )
        if not ok:
            return
        self.add_marketplace(directory, marketplace.strip())

    def add_marketplace(self, path: str, marketplace: str = "") -> None:
        """등록의 실체 — 테스트·프로그램 경로가 다이얼로그 없이 부른다."""
        wrap_catalog.add_marketplace(path, marketplace)
        self.refresh()

    def remove_selected_marketplace(self) -> None:
        item = self._tree.currentItem()
        while item is not None and item.data(0, _ROLE_KIND) != "marketplace":
            item = item.parent()
        if item is None:
            self._status.setText("제거할 마켓플레이스 폴더 행을 먼저 선택하세요.")
            return
        wrap_catalog.remove_marketplace(item.data(0, _ROLE_FOLDER_PATH))
        self.refresh()

