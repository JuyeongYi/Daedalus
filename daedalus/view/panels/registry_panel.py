# daedalus/view/panels/registry_panel.py
from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QDrag
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.plugin.kinds import config_kinds_in, spec_for
from daedalus.model.plugin.roles import Bucket
from daedalus.model.plugin.skill import WrappedSkill
from daedalus.model.project import PluginProject
from daedalus.view.kind_ui import ui_by_config_kind, ui_for

_ROLE_COMPONENT = Qt.ItemDataRole.UserRole + 1
_ROLE_PLACED = Qt.ItemDataRole.UserRole + 2
#: 후보 행(WP-WR — 아직 컴포넌트가 아닌 외부 스킬)의 드래그 mime 텍스트.
#: 있으면 컴포넌트 이름 대신 이 텍스트로 드래그한다.
_ROLE_DRAG_TEXT = Qt.ItemDataRole.UserRole + 3

_COLOR_PLACED = QColor("#445544")
_COLOR_NO_PLACE = QColor("#666644")
_COLOR_CANDIDATE = QColor("#7f8f9f")

#: 섹션 키 = config `kind` 어휘. **선언 순서**가 곧 탭 순서다(결정성) — 새 종류는
#: 모델 레지스트리 한 줄 + `KIND_UI` 한 행이면 팔레트에 나타난다(V1~V4 소멸).
_SECTION_KINDS: tuple[str, ...] = (
    config_kinds_in(Bucket.SKILLS) + config_kinds_in(Bucket.AGENTS)
)

#: 후보 행(WP-WR)이 들어갈 섹션 — WP-10에서 이 경로 전체가 사라진다.
_WRAPPED_SECTION = WrappedSkill.CONFIG_CLS.KIND


class _DraggableList(QListWidget):
    """배치된 항목은 드래그 불가인 목록 위젯."""

    def startDrag(self, supported_actions: Qt.DropAction) -> None:
        item = self.currentItem()
        if item is None or item.data(_ROLE_PLACED):
            return
        # 후보 행(WP-WR)은 컴포넌트가 없고 "wrapped-source:<source>" mime으로
        # 끈다 — 캔버스 드롭이 그 시점에 WrappedSkill을 생성·배치한다.
        drag_text = item.data(_ROLE_DRAG_TEXT)
        if drag_text is None:
            component = item.data(_ROLE_COMPONENT)
            if component is None:
                return
            drag_text = component.name
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(drag_text)
        drag.setMimeData(mime)
        _run_drag = getattr(drag, "exec")
        _run_drag(Qt.DropAction.CopyAction)


class _RegistrySection(QWidget):
    """레이블 + 리스트 + "+" 버튼을 묶은 레지스트리 섹션."""

    add_requested = Signal()
    item_double_clicked = Signal(object)
    delete_requested = Signal(object)  # component
    preview_requested = Signal(object)  # component — 컴파일 미리보기 (A9-1)
    #: 랩핑 스킬 켜고 끄기 (WP-WR) — (component, enabled). 삭제의 대체재라
    #: 랩핑 스킬 행에서는 이것이 '삭제' 자리를 대신한다.
    enabled_toggle_requested = Signal(object, bool)

    def __init__(
        self,
        label: str,
        color: QColor,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._color = color
        self.label_text = label  # RegistryPanel이 탭 툴팁으로 재사용

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(2)
        hdr.addWidget(QLabel(label))
        hdr.addStretch()
        btn = QPushButton("+")
        btn.setFixedSize(20, 20)
        btn.clicked.connect(self.add_requested)
        hdr.addWidget(btn)
        lay.addLayout(hdr)

        self._list = _DraggableList()
        self._list.setDragEnabled(True)
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self._list.setMinimumHeight(30)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.doubleClicked.connect(self._on_double_click)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        lay.addWidget(self._list)

    def clear(self) -> None:
        self._list.clear()

    def add_candidate_item(self, label: str, drag_text: str, tooltip: str) -> None:
        """후보 행 (WP-WR) — 컴포넌트가 아니라 선언된 외부 플러그인의 스킬.

        드래그하면 캔버스 드롭 시점에 WrappedSkill이 생성·배치된다(mime =
        `wrapped-source:<source>`). 더블클릭·컨텍스트 메뉴는 컴포넌트가 없어
        자연히 무동작이다(_ROLE_COMPONENT가 None — 기존 가드 그대로).
        """
        item = QListWidgetItem(label)
        item.setData(_ROLE_DRAG_TEXT, drag_text)
        item.setForeground(_COLOR_CANDIDATE)
        item.setToolTip(tooltip)
        font = item.font()
        font.setItalic(True)
        item.setFont(font)
        self._list.addItem(item)

    def add_item(self, component: object, placed: bool) -> None:
        from daedalus.model.plugin.placement import is_canvas_placeable

        icon = ui_for(component).icon
        name = getattr(component, "name", str(component))
        # 캔버스에 놓이는가는 **항목마다** 묻는다(양성 판정 단일 진실) — 섹션
        # 단위 플래그를 따로 두면 같은 사실의 출처가 둘이 된다(스멜 ②).
        no_place = not is_canvas_placeable(component)

        label = f"{icon} {name}"
        item = QListWidgetItem(label)
        item.setData(_ROLE_COMPONENT, component)
        item.setData(_ROLE_PLACED, placed)

        if no_place:
            item.setForeground(_COLOR_NO_PLACE)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            font = item.font()
            font.setItalic(True)
            item.setFont(font)
        elif placed:
            item.setForeground(_COLOR_PLACED)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            font = item.font()
            font.setItalic(True)
            item.setFont(font)
        else:
            item.setForeground(self._color)
        self._list.addItem(item)

    def _on_double_click(self, index) -> None:
        item = self._list.itemFromIndex(index)
        if item:
            comp = item.data(_ROLE_COMPONENT)
            if comp is not None:
                self.item_double_clicked.emit(comp)

    def _on_context_menu(self, pos: QPoint) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        comp = item.data(_ROLE_COMPONENT)
        if comp is None:
            return
        menu = QMenu(self)
        # 트랜스퍼 스킬은 캔버스 노드가 아니라 엣지에 붙어 placement 우클릭
        # 메뉴가 닿지 않는다(사용자 보고) — 레지스트리가 전 컴포넌트 공통의
        # 미리보기 진입점이다.
        preview_action = menu.addAction("컴파일 미리보기…")
        if preview_action is not None:
            from daedalus.compiler.preview import can_preview

            # 산출 자리가 없는 종류만 비활성 — 참조 용도·비활성 랩핑 스킬은
            # 파일이 나가지 않아도 미리보기 대상이다(compiler/preview.py).
            preview_action.setEnabled(can_preview(comp))
            if not can_preview(comp):
                preview_action.setToolTip(
                    "이 종류는 산출 파일이 없어 미리볼 것이 없습니다."
                )
            preview_action.triggered.connect(lambda: self.preview_requested.emit(comp))
        # 랩핑 스킬은 삭제할 수 없다(WP-WR, 사용자 확정 2026-09-07) — 메뉴에
        # 아예 내지 않고 그 자리에 켜고 끄는 항목을 둔다. 눌러 봐야 거절당하는
        # 항목을 보여 주면 "왜 안 되지"를 매번 다시 겪는다.
        # 종류가 아니라 **뷰 표면 선언**(`has_enable_toggle`)이 어느 쪽
        # 항목인지 답한다 — 활성/비활성은 인스턴스 능력(`is_active`)이 답한다.
        if ui_for(comp).has_enable_toggle:
            enabled = comp.is_active()
            toggle = menu.addAction("비활성화" if enabled else "활성화")
            if toggle is not None:
                toggle.setToolTip(
                    "끄면 빌드 산출과 외부 플러그인 배선에서 빠집니다 — 소스와 "
                    "배치는 그대로라 언제든 되돌릴 수 있습니다."
                )
                toggle.triggered.connect(
                    lambda: self.enabled_toggle_requested.emit(comp, not enabled)
                )
        else:
            delete_action = menu.addAction("삭제")
            if delete_action is not None:
                delete_action.triggered.connect(
                    lambda: self.delete_requested.emit(comp)
                )
        menu.exec(self._list.mapToGlobal(pos))


class RegistryPanel(QWidget):
    """스킬/에이전트 레지스트리 팔레트."""

    component_double_clicked = Signal(object)
    new_component_requested = Signal(str)  # kind: "procedural"|"declarative"|"transfer"|"agent"
    component_delete_requested = Signal(object)  # component
    component_preview_requested = Signal(object)  # component — 컴파일 미리보기
    component_enabled_toggled = Signal(object, bool)  # 랩핑 스킬 켜고 끄기 (WP-WR)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: PluginProject | None = None
        self._placed_ids: set[int] = set()
        # 외부 스킬 후보 캐시 (WP-WR) — 카탈로그 스캔은 파일시스템이라
        # notify마다 돌리면 안 된다. 사용 선언 목록이 바뀔 때만 재스캔한다
        # (마켓 폴더 등록 변화는 다음 선언 변경/프로젝트 로드에 반영 — 허용).
        self._candidates_key: tuple[str, ...] | None = None
        self._candidates: list[tuple[str, str, str, str]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._sections: dict[str, _RegistrySection] = {
            kind: _RegistrySection(
                ui_by_config_kind(kind).section_label,
                ui_by_config_kind(kind).section_color,
            )
            for kind in _SECTION_KINDS
        }
        # 종류별 세로 스택 대신 **탭**으로 담는다 (사용자 확정 — 좌측 열을
        # 컴팩트하게 만들어 파일 독을 아래에 두고 에디터가 공간을 가져간다).
        # 탭 라벨은 짧게, 전체 이름은 툴팁으로.
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        for kind, section in self._sections.items():
            section.add_requested.connect(lambda k=kind: self.new_component_requested.emit(k))
            section.item_double_clicked.connect(self.component_double_clicked)
            section.delete_requested.connect(self.component_delete_requested)
            section.enabled_toggle_requested.connect(self.component_enabled_toggled)
            section.preview_requested.connect(self.component_preview_requested)
            idx = self._tabs.addTab(section, ui_by_config_kind(kind).tab_label)
            self._tabs.setTabToolTip(idx, section.label_text)
        layout.addWidget(self._tabs)

    def set_project(self, project: PluginProject) -> None:
        self._project = project
        self._candidates_key = None  # 프로젝트 전환 — 후보 재스캔
        self._rebuild()

    def _wrapped_candidates(self) -> list[tuple[str, str, str, str]]:
        """사용 선언된 외부 플러그인의 스킬 (스킬명, plugin_id, source, 설명).

        이미 랩핑됐는지는 여기서 거르지 않는다 — 그 판정은 rebuild 시점의
        프로젝트 상태이고(랩퍼 생성·삭제마다 변한다), 캐시는 스캔 결과만 든다.
        """
        project = self._project
        declared = tuple(getattr(project, "external_plugins", None) or [])
        if not declared:
            return []
        if self._candidates_key == declared:
            return self._candidates
        from daedalus.model.plugin import wrap_catalog

        rows: list[tuple[str, str, str, str]] = []
        for _folder, plugins in wrap_catalog.scan_catalog():
            for plugin in plugins:
                if plugin.plugin_id not in declared:
                    continue
                for skill in plugin.skills:
                    rows.append(
                        (skill.name, plugin.plugin_id, skill.source, skill.description)
                    )
        self._candidates_key = declared
        self._candidates = rows
        return rows

    def set_placed_ids(self, placed_ids: set[int]) -> None:
        self._placed_ids = placed_ids
        self._rebuild()

    def _rebuild(self) -> None:
        for section in self._sections.values():
            section.clear()
        if self._project is None:
            return
        # **순서 민감한 isinstance 사다리가 있던 자리다**(V4) — 서브클래스가 먼저
        # 매치돼야 해서 WrappedSkill/AsyncForkSkill을 앞에 두어야 했고, 새 종류는
        # 어느 분기에도 걸리지 않아 **조용히 레지스트리에서 사라졌다**. 이제
        # 종류 선언이 자기 섹션을 답한다(`spec_for(c).config_kind`).
        # 배치 여부는 항목마다 묻는다 — 캔버스에 놓이지 않는 종류는 애초에
        # `_placed_ids`(상태 노드의 skill_ref)에 들어가지 않는다.
        for component in list(self._project.skills) + list(self._project.agents):
            key = spec_for(component).config_kind
            self._sections[key].add_item(
                component, id(component) in self._placed_ids
            )
        # 외부 스킬 후보 (WP-WR) — 사용 선언된 플러그인의 스킬 중 아직 이
        # 프로젝트가 랩핑하지 않은 것. 드래그해 배치하면 그 시점에
        # WrappedSkill이 생성된다(체크만 하면 목록에 자동으로 나타난다 —
        # 사용자 확정 "목록에 그냥 자동으로 명시").
        # "본문 정본이 외부인 스킬의 소스" — 종류가 아니라 능력이 답한다(WP-2c).
        from daedalus.model.plugin.skill import has_external_body

        wrapped_sources = {
            s.external_source or ""
            for s in self._project.skills
            if has_external_body(s)
        }
        from daedalus.view.actions.creation import WRAPPED_SOURCE_MIME_PREFIX

        for name, plugin_id, source, description in self._wrapped_candidates():
            if source in wrapped_sources:
                continue
            self._sections[_WRAPPED_SECTION].add_candidate_item(
                label=f"🔗 {name} ({plugin_id})",
                drag_text=f"{WRAPPED_SOURCE_MIME_PREFIX}{source}",
                tooltip=(
                    f"{source}"
                    + (f" — {description}" if description else "")
                    + "\n캔버스로 드래그하면 WrappedSkill로 생성·배치됩니다."
                ),
            )
