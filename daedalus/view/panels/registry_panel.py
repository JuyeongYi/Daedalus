# daedalus/view/panels/registry_panel.py
from __future__ import annotations

from dataclasses import dataclass

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

from daedalus.model.plugin.kinds import (
    config_kinds_in,
    spec_by_config_kind,
    spec_for,
)
from daedalus.model.plugin.roles import BodySource, Bucket
from daedalus.model.project import PluginProject
from daedalus.view.kind_ui import KindUI, ui_by_config_kind, ui_for
from daedalus.view.panels.external_registry import (
    ExternalSkillsSection,
    UnregisteredAgentsList,
)

_ROLE_COMPONENT = Qt.ItemDataRole.UserRole + 1
_ROLE_PLACED = Qt.ItemDataRole.UserRole + 2
_COLOR_PLACED = QColor("#445544")
_COLOR_NO_PLACE = QColor("#666644")

#: 섹션이 담는 config `kind` 어휘. **선언 순서**가 곧 탭 순서다(결정성) — 새 종류는
#: 모델 레지스트리 한 줄 + `KIND_UI` 한 행이면 팔레트에 나타난다(V1~V4 소멸).
_SECTION_KINDS: tuple[str, ...] = (
    config_kinds_in(Bucket.SKILLS) + config_kinds_in(Bucket.AGENTS)
)


@dataclass(frozen=True)
class _SectionSpec:
    """탭 하나가 담는 것 — 종류 **여럿**일 수 있다 (WP-C).

    `KindUI.section_group`이 같은 종류는 한 탭을 나눠 쓴다(🔌 EXTERNAL AGENTS =
    그래프 노드 역할 + fork 기반 역할). 라벨·색·탭 라벨은 **선언 순서상 첫
    멤버**의 행에서 오므로 표가 하나 늘지 않는다.
    """

    key: str
    """섹션 키 — 그룹이 없으면 config kind 그대로, 있으면 그룹 키."""
    config_kinds: tuple[str, ...]
    ui: KindUI
    """첫 멤버의 뷰 행 — 라벨·색·탭 라벨의 출처."""

    @property
    def external_only(self) -> bool:
        """담는 종류가 전부 **외부 정본**인가 — 그러면 빈 이름으로 만들 수 없다.

        정본이 저쪽 플러그인 파일이므로 "+"는 이름을 묻는 대신 카탈로그 창을
        연다(WP-C). 종류 선언(`BODY_SOURCE`)이 답하므로 목록을 손으로 적지 않는다.
        """
        return all(
            spec_by_config_kind(k).body_source is BodySource.EXTERNAL
            for k in self.config_kinds
        )

    @property
    def shows_catalog_agents(self) -> bool:
        """카탈로그의 **미등록 에이전트**를 함께 보여 주는 섹션인가."""
        return self.external_only and all(
            spec_by_config_kind(k).bucket is Bucket.AGENTS
            for k in self.config_kinds
        )


def _section_specs() -> tuple[_SectionSpec, ...]:
    """`_SECTION_KINDS` → 탭 목록. 그룹이 같은 종류는 한 섹션으로 접힌다."""
    order: list[str] = []
    members: dict[str, list[str]] = {}
    lead: dict[str, str] = {}
    for config_kind in _SECTION_KINDS:
        group = ui_by_config_kind(config_kind).section_group or config_kind
        if group not in members:
            order.append(group)
            members[group] = []
            lead[group] = config_kind
        members[group].append(config_kind)
    return tuple(
        _SectionSpec(
            key=group,
            config_kinds=tuple(members[group]),
            ui=ui_by_config_kind(lead[group]),
        )
        for group in order
    )



class _DraggableList(QListWidget):
    """배치된 항목은 드래그 불가인 목록 위젯."""

    def startDrag(self, supported_actions: Qt.DropAction) -> None:
        item = self.currentItem()
        if item is None or item.data(_ROLE_PLACED):
            return
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

            # 산출 자리가 없는 종류만 비활성(compiler/preview.py).
            preview_action.setEnabled(can_preview(comp))
            if not can_preview(comp):
                preview_action.setToolTip(
                    "이 종류는 산출 파일이 없어 미리볼 것이 없습니다."
                )
            preview_action.triggered.connect(lambda: self.preview_requested.emit(comp))
        delete_action = menu.addAction("삭제")
        if delete_action is not None:
            delete_action.triggered.connect(
                lambda: self.delete_requested.emit(comp)
            )
        menu.exec(self._list.mapToGlobal(pos))


class RegistryPanel(QWidget):
    """스킬/에이전트 레지스트리 팔레트 + 외부 플러그인 등록 표면 (WP-C).

    탭은 세 갈래다: 종류별 컴포넌트 섹션(종류 레지스트리 파생) · 🔌 EXTERNAL
    AGENTS(두 역할을 한 섹션 + 카탈로그의 미등록 에이전트) · 🧷 EXTERNAL
    SKILLS(컴포넌트가 아닌 카탈로그 항목).

    **카탈로그 스캔은 파일시스템을 읽는다** — 그래서 `_rebuild`마다 부르지 않고
    프로젝트가 바뀔 때와 명시 새로고침(`refresh_catalog` — 카탈로그 창이 닫힐
    때)에만 다시 훑고, 결과를 캐시해 유도 함수에 주입한다. 사용 선언
    (`external_plugins`)이 바뀌었을 때는 다시 훑을 필요가 없다 — 선언 필터는
    그릴 때 걸린다.
    """

    component_double_clicked = Signal(object)
    new_component_requested = Signal(str)  # config kind
    component_delete_requested = Signal(object)  # component
    component_preview_requested = Signal(object)  # component — 컴파일 미리보기
    #: 외부 정본 섹션의 "+" — 카탈로그 창을 연다(이름을 물어 만들 수 없다).
    catalog_requested = Signal()
    #: 미등록 외부 에이전트를 등록 (agent_type, config kind).
    external_agent_register_requested = Signal(str, str)
    #: 외부 스킬 참조를 에이전트 skills에 추가 (skill_ref, agent).
    external_skill_attach_requested = Signal(str, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: PluginProject | None = None
        self._placed_ids: set[int] = set()
        self._catalog: list | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._sections: dict[str, _RegistrySection] = {}
        #: config kind → 그것이 사는 섹션 키 (그룹이면 여러 종류가 한 키).
        self._section_of_kind: dict[str, str] = {}
        #: 섹션 키 → 그 탭 하단의 미등록 에이전트 목록(있는 탭만).
        self._catalog_agents: dict[str, UnregisteredAgentsList] = {}

        # 종류별 세로 스택 대신 **탭**으로 담는다 (사용자 확정 — 좌측 열을
        # 컴팩트하게 만들어 파일 독을 아래에 두고 에디터가 공간을 가져간다).
        # 탭 라벨은 짧게, 전체 이름은 툴팁으로.
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        # **모듈 상수로 두지 않는다** — `KIND_UI` 행이 빠진 종류는 팔레트를
        # 만들 때 이름을 찍고 죽어야 한다(`test_registry_failure_is_loud`).
        # 임포트 시점에 접으면 그 거절이 임포트 실패로 번져 이유를 잃는다.
        for spec in _section_specs():
            self._add_kind_tab(spec)
        self._skills_section = ExternalSkillsSection()
        self._skills_section.add_requested.connect(self.catalog_requested)
        self._skills_section.attach_requested.connect(
            self.external_skill_attach_requested
        )
        idx = self._tabs.addTab(
            self._skills_section, self._skills_section.tab_label
        )
        self._tabs.setTabToolTip(idx, self._skills_section.label_text)
        layout.addWidget(self._tabs)

    def _add_kind_tab(self, spec: _SectionSpec) -> None:
        """종류 섹션 하나를 탭으로 만든다 (그룹이면 종류 여럿이 한 탭)."""
        section = _RegistrySection(spec.ui.section_label, spec.ui.section_color)
        self._sections[spec.key] = section
        for config_kind in spec.config_kinds:
            self._section_of_kind[config_kind] = spec.key
        # 외부 정본 섹션의 "+"는 이름을 물어 만들 수 없다 — 정본이 저쪽
        # 플러그인 파일이라 카탈로그에서 고르는 것이 유일한 진입이다.
        if spec.external_only:
            section.add_requested.connect(self.catalog_requested)
        else:
            section.add_requested.connect(
                lambda k=spec.config_kinds[0]: self.new_component_requested.emit(k)
            )
        section.item_double_clicked.connect(self.component_double_clicked)
        section.delete_requested.connect(self.component_delete_requested)
        section.preview_requested.connect(self.component_preview_requested)

        page: QWidget = section
        if spec.shows_catalog_agents:
            page = QWidget()
            lay = QVBoxLayout(page)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(4)
            lay.addWidget(section, 2)
            catalog_list = UnregisteredAgentsList(spec.config_kinds)
            catalog_list.register_requested.connect(
                self.external_agent_register_requested
            )
            self._catalog_agents[spec.key] = catalog_list
            lay.addWidget(catalog_list, 1)
        idx = self._tabs.addTab(page, spec.ui.tab_label)
        self._tabs.setTabToolTip(idx, section.label_text)

    # --- 갱신 ---

    def set_project(self, project: PluginProject) -> None:
        if project is not self._project:
            self._project = project
            self.refresh_catalog()  # _rebuild까지 한다
            return
        self._project = project
        self._rebuild()

    def refresh_catalog(self) -> None:
        """카탈로그를 **다시 훑고** 그린다 — 파일시스템을 읽는 유일한 경로.

        프로젝트를 바꿀 때와 카탈로그 창이 닫힐 때만 부른다. 폴더가 없거나 읽기가
        실패하면 빈 목록이다(카탈로그 모듈의 fail-soft 규약).
        """
        from daedalus.model.plugin import wrap_catalog

        self._catalog = wrap_catalog.scan_catalog()
        self._rebuild()

    def set_placed_ids(self, placed_ids: set[int]) -> None:
        self._placed_ids = placed_ids
        self._rebuild()

    def _rebuild(self) -> None:
        for section in self._sections.values():
            section.clear()
        if self._project is None:
            return
        # **순서 민감한 isinstance 사다리가 있던 자리다**(V4) — 서브클래스가 먼저
        # 매치돼야 해서 AsyncForkSkill을 앞에 두어야 했고, 새 종류는
        # 어느 분기에도 걸리지 않아 **조용히 레지스트리에서 사라졌다**. 이제
        # 종류 선언이 자기 섹션을 답한다(`spec_for(c).config_kind`).
        # 배치 여부는 항목마다 묻는다 — 캔버스에 놓이지 않는 종류는 애초에
        # `_placed_ids`(상태 노드의 skill_ref)에 들어가지 않는다.
        for component in list(self._project.skills) + list(self._project.agents):
            key = self._section_of_kind[spec_for(component).config_kind]
            self._sections[key].add_item(
                component, id(component) in self._placed_ids
            )
        self._rebuild_catalog_surfaces()

    def _rebuild_catalog_surfaces(self) -> None:
        """🔌 하단 미등록 목록 + 🧷 탭 — 판정은 전부 모델 함수가 한다."""
        from daedalus.model.plugin import wrap_catalog

        project = self._project
        catalog = self._catalog
        for widget in self._catalog_agents.values():
            widget.set_agents(
                wrap_catalog.unregistered_plugin_agents(project, catalog)
            )
        self._skills_section.set_rows(
            wrap_catalog.used_plugin_skill_refs(project, catalog),
            wrap_catalog.skill_ref_users(project),
            list(project.agents),
        )
