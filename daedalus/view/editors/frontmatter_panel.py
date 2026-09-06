# daedalus/view/editors/frontmatter_panel.py
"""프론트매터 편집 패널 — SKILL_FIELD_MATRIX / AGENT_FIELD_MATRIX 기반 좌측 폼.

구 ``skill_editor.py``(1,172줄)에서 이동했다(WP-RF 관례 — 이동만·동작 불변).
``skill_editor`` 모듈은 재-export 파사드로 남아 기존 임포트 경로가 그대로 동작한다.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QWidget,
)

from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill, ReferenceSkill, TransferSkill
from daedalus.model.plugin.enums import (
    AgentColor,
    AgentField,
    AgentIsolation,
    EffortLevel,
    MemoryScope,
    ModelType,
    PermissionMode,
    SkillContext,
    SkillField,
    SkillShell,
)
from daedalus.view.widgets.tag_input import TagInput


# ---------------------------------------------------------------------------
# 모듈 수준 상수: SkillField | AgentField → config/component 속성명 매핑
# 로드(load) 경로와 저장(write-back) 경로가 같은 테이블을 공유한다.
# ---------------------------------------------------------------------------
_FIELD_ATTR_MAP: dict[SkillField | AgentField, str] = {
    SkillField.SOURCE: "source",  # WP-WR
    SkillField.ARGUMENT_HINT: "argument_hint",
    SkillField.MODEL: "model",
    SkillField.EFFORT: "effort",
    SkillField.ALLOWED_TOOLS: "allowed_tools",
    SkillField.CONTEXT: "context",
    SkillField.AGENT: "agent",
    SkillField.SHELL: "shell",
    SkillField.PATHS: "paths",
    SkillField.HOOKS: "hooks",
    SkillField.DISABLE_MODEL: "disable_model_invocation",
    SkillField.USER_INVOCABLE: "user_invocable",
    # AgentField 항목
    AgentField.MODEL: "model",
    AgentField.EFFORT: "effort",
    AgentField.TOOLS: "tools",
    AgentField.DISALLOWED_TOOLS: "disallowed_tools",
    AgentField.PERMISSION_MODE: "permission_mode",
    AgentField.SKILLS: "skills",
    AgentField.MEMORY: "memory",
    AgentField.COLOR: "color",
    AgentField.HOOKS: "hooks",
    AgentField.MAX_TURNS: "max_turns",
    AgentField.BACKGROUND: "background",
    AgentField.ISOLATION: "isolation",
    AgentField.MCP_SERVERS: "mcp_servers",
}

# SkillField | AgentField → 역변환에 사용할 Enum 타입 (str → Enum)
_FIELD_ENUM_MAP: dict[SkillField | AgentField, type] = {
    SkillField.MODEL: ModelType,
    SkillField.EFFORT: EffortLevel,
    SkillField.CONTEXT: SkillContext,
    SkillField.SHELL: SkillShell,
    # AgentField 항목
    AgentField.MODEL: ModelType,
    AgentField.EFFORT: EffortLevel,
    AgentField.PERMISSION_MODE: PermissionMode,
    AgentField.MEMORY: MemoryScope,
    AgentField.ISOLATION: AgentIsolation,
    AgentField.COLOR: AgentColor,
}

# list[str] 타입인 필드 집합 — 선언 기본값(default)이 MISSING일 때 클리어 폴백을 []로 결정.
# 두 필드 모두 TagInput 편집이므로 write-back 값은 항상 list로 들어온다.
# 클리어 자체는 _declared_default가 dataclass 선언 기본값으로 처리하므로
# PATHS(default None)는 자연히 None으로 정규화된다.
# 주의: HOOKS는 dict[str, Any] 필드이므로 여기에 포함하지 않는다.
_LIST_FIELDS: set[SkillField | AgentField] = {
    SkillField.ALLOWED_TOOLS,
    SkillField.PATHS,
    AgentField.TOOLS,
    AgentField.DISALLOWED_TOOLS,
    AgentField.SKILLS,
    AgentField.MCP_SERVERS,
}

# 도구/에이전트 카탈로그 자동완성을 받는 필드 집합 (WP-TM Part B).
# PATHS/SKILLS/MCP_SERVERS는 도구 권한 문자열이 아니므로 제외.
_TOOL_CANDIDATE_FIELDS: set[SkillField | AgentField] = {
    SkillField.ALLOWED_TOOLS,
    AgentField.TOOLS,
    AgentField.DISALLOWED_TOOLS,
}


# 프론트매터 그리드의 열 — 모든 행이 이 세 열을 공유한다.
_COL_CHECK, _COL_LABEL, _COL_WIDGET = 0, 1, 2
_COL_COUNT = 3

_DIM_OPACITY = 0.4


# ---------------------------------------------------------------------------
# 위젯 어댑터 표 — 위젯 타입 하나당 (읽기, 쓰기, 변경 시그널 이름) 한 줄.
#
# 값 로드(_apply_value) · 값 읽기(_read_widget_value) · 시그널 연결
# (_connect_widget_signal)이 **같은 isinstance 사슬을 세 벌** 복제하고 있었다.
# 위젯 타입이 하나 늘면 세 곳을 함께 고쳐야 하고, 한 곳을 빠뜨리면 "값은
# 채워지는데 편집이 저장되지 않는" 식의 반쪽 고장이 조용히 생긴다.
#
# **순회 순서는 분해 전 elif 사슬의 순서를 그대로 유지한다** — isinstance는
# 서브클래스에도 참이므로 순서가 곧 우선순위다(표의 줄을 옮기면 동작이 바뀐다).
# ---------------------------------------------------------------------------

def _write_spin_box(widget: QSpinBox, current: object, rule) -> None:
    # QSpinBox 기본 상한이 99라 max_turns가 잘릴 수 있다.
    # CC의 실제 상한은 컴파일러 WP에서 확정 — 잠정 1~1000.
    widget.setRange(1, 1000)
    widget.setValue(int(current) if current is not None else 1)


def _write_combo_box(widget: QComboBox, current: object, rule) -> None:
    val = None
    if current is not None:
        val = current.value if hasattr(current, "value") else str(current)
    elif rule.default_value is not None:
        # default_value는 enum(ModelType.INHERIT 등) 또는 스칼라.
        dv = rule.default_value
        val = dv.value if hasattr(dv, "value") else str(dv)
    if val is not None:
        idx = widget.findText(val)
        if idx >= 0:
            widget.setCurrentIndex(idx)


def _write_check_box(widget: QCheckBox, current: object, rule) -> None:
    widget.setChecked(bool(current) if current is not None else False)


def _write_tag_input(widget: TagInput, current: object, rule) -> None:
    if isinstance(current, list):
        widget.set_tags(current)
    elif isinstance(current, dict):
        # hooks: dict[str, Any] — 키 집합을 태그 목록으로 (WP-SF hooks TagInput 전환)
        widget.set_tags(list(current.keys()))


def _write_text_edit(widget: QTextEdit, current: object, rule) -> None:
    if current is not None:
        widget.setPlainText(str(current))
    widget.setFixedHeight(44)


def _write_line_edit(widget: QLineEdit, current: object, rule) -> None:
    if isinstance(current, list):
        widget.setText(" ".join(current) if current else "")
    elif current is not None:
        widget.setText(str(current))


# (위젯 타입, 표시값 읽기, 현재값 쓰기, 변경 시그널 이름)
_WIDGET_ADAPTERS: tuple[tuple[type, object, object, str], ...] = (
    (QSpinBox, lambda w: w.value(), _write_spin_box, "valueChanged"),
    (QComboBox, lambda w: w.currentText(), _write_combo_box, "currentTextChanged"),
    (QCheckBox, lambda w: w.isChecked(), _write_check_box, "toggled"),
    (TagInput, lambda w: w.get_tags(), _write_tag_input, "tags_changed"),
    (QTextEdit, lambda w: w.toPlainText(), _write_text_edit, "textChanged"),
    (QLineEdit, lambda w: w.text(), _write_line_edit, "editingFinished"),
)


def _adapter_for(widget: QWidget):
    """위젯에 맞는 어댑터 한 줄. 표에 없는 타입이면 None."""
    for entry in _WIDGET_ADAPTERS:
        if isinstance(widget, entry[0]):
            return entry
    return None


class _OptionalRow(QWidget):
    """체크박스 ON/OFF로 선택적 프론트매터 필드를 표시/비활성화.

    **이 위젯 자체는 행의 세 번째 칸(값 위젯을 담는 칸)이다.** 체크박스와
    라벨은 같은 부모 그리드의 0·1열에 따로 놓인다(`place_in`) — 행마다 독립
    레이아웃을 쓰면 열 폭이 공유되지 않아 라벨 길이만큼 값 위젯의 시작
    x좌표가 어긋나 계단처럼 보였다(사용자 보고: hooks / mcp_servers 행).

    값 위젯의 부모는 여전히 이 객체다 — 호출부와 테스트가 `widget.parent()`로
    행을 찾아 올라가 토글·잠금을 확인한다.
    """

    toggled = Signal(bool)

    def __init__(
        self,
        label: str,
        widget: QWidget,
        initially_enabled: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(0)

        self._widget = widget
        layout.addWidget(widget, 1)

        # 0·1열 셀 — 부모가 place_in으로 그리드에 가져간다. 여기서 만드는 이유는
        # 토글·잠금이 세 칸을 함께 다뤄야 하기 때문이다(소유는 이 객체가 한다).
        self._cb = QCheckBox()
        self._cb.setChecked(initially_enabled)
        self._label = QLabel(label)
        self._label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        # QGraphicsEffect는 위젯 하나에만 붙으므로 흐릴 칸마다 하나씩 둔다.
        # 체크박스는 흐리지 않는다 — 다시 켜려면 눌러야 하는 컨트롤이다.
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._label_opacity = QGraphicsOpacityEffect(self._label)
        self._label.setGraphicsEffect(self._label_opacity)

        self._cb.toggled.connect(self._update_state)
        self._update_state(initially_enabled)

    def place_in(self, grid, row: int) -> None:
        """세 칸을 그리드 한 행에 배치한다 — 열 폭은 모든 행이 공유한다."""
        grid.addWidget(self._cb, row, _COL_CHECK)
        grid.addWidget(self._label, row, _COL_LABEL)
        grid.addWidget(self, row, _COL_WIDGET)

    def set_locked(self, reason: str) -> None:
        """행 전체를 잠근다 (WP-EL).

        체크박스까지 꺼야 한다 — 값 위젯만 잠그면 "켤 수는 있는데 아무 일도
        안 일어나는" 상태가 된다.
        """
        for cell in (self, self._cb, self._label):
            cell.setEnabled(False)
            cell.setToolTip(reason)

    def _update_state(self, checked: bool) -> None:
        self._widget.setEnabled(checked)
        opacity = 1.0 if checked else _DIM_OPACITY
        self._opacity.setOpacity(opacity)
        self._label_opacity.setOpacity(opacity)
        self.toggled.emit(checked)

    def is_checked(self) -> bool:
        return self._cb.isChecked()

    def set_checked(self, checked: bool) -> None:
        self._cb.setChecked(checked)


class _FrontmatterPanel(QScrollArea):
    """좌측 패널 — SKILL_FIELD_MATRIX 기반 프론트매터 편집."""

    changed = Signal()
    # 텍스트 키스트로크 전용 채널 — description / when_to_use 타이핑.
    # 무거운 structure 리스너를 우회하기 위해 별도 시그널로 분리한다.
    content_changed = Signal()
    # 이름 변경 시 발화 — (component, old_name, new_name). 중복 방지 및 참조 갱신용.
    renamed = Signal(object, str, str)

    def __init__(
        self,
        component: ProceduralSkill | DeclarativeSkill | TransferSkill | ReferenceSkill | AgentDefinition,
        skill_kind: str | None = None,
        parent: QWidget | None = None,
        build_target=None,
        project_vm=None,
    ) -> None:
        super().__init__(parent)
        self._component = component
        # 커맨드 스택 — 진입점 프리셋(A8)처럼 undo 가능해야 하는 편집에 쓴다.
        # None이면 그 UI를 만들지 않는다(에디터 단독 생성 경로 호환).
        self._project_vm = project_vm
        # 빌드 타깃에 따라 CC가 무시하는 필드를 잠근다 (WP-EL). None이면
        # 마켓플레이스로 취급 — 기존 호출부·테스트 호환.
        from daedalus.model.plugin.enums import BuildTarget

        self._build_target = build_target or BuildTarget.MARKETPLACE
        self._field_widgets: dict[SkillField | AgentField, QWidget] = {}
        self._loading = False  # 로드 중 write-back 핸들러 억제용 가드

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # 모든 필드 행이 **하나의 그리드**를 공유한다 — 행마다 독립 레이아웃을
        # 쓰면 라벨 길이가 그대로 값 위젯의 시작 x좌표 차이가 되어 행들이
        # 계단처럼 어긋난다(사용자 보고). 열: 0=체크박스 / 1=라벨 / 2=값 위젯.
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(3)
        grid.setColumnStretch(_COL_WIDGET, 1)
        self._grid = grid
        self._grid_row = 0

        self._add_span_row(QLabel("Frontmatter"))

        # name (필수, 항상 표시)
        self._w_name = QLineEdit(component.name)
        self._w_name.editingFinished.connect(self._save_name)
        self._add_field_row("name *", self._w_name)

        # description (필수, 항상 표시)
        self._w_desc = QTextEdit()
        self._w_desc.setPlainText(component.description)
        self._w_desc.setFixedHeight(44)
        self._w_desc.textChanged.connect(self._save_desc)
        self._add_field_row("description *", self._w_desc)

        # 진입점 프리셋 (A8) — 캔버스 노드 우클릭과 **같은 함수**를 부른다.
        self._entry_preset_combo: QComboBox | None = None
        self._build_entry_preset_row(component)

        # 미리보기 / 관련 경고 (A9-1, A9-3) — 역시 캔버스 메뉴와 같은 함수.
        self._build_component_action_row()

        # SKILL_FIELD_MATRIX / AGENT_FIELD_MATRIX 기반 필드 생성
        # 위젯 클래스는 view 측 FIELD_WIDGETS / AGENT_FIELD_WIDGETS에서 조회한다(model→view 의존 역전).
        from daedalus.model.plugin.field_matrix import AGENT_FIELD_MATRIX, SKILL_FIELD_MATRIX
        from daedalus.model.plugin.enums import FieldEmit, FieldVisibility
        from daedalus.view.editors.field_widgets import AGENT_FIELD_WIDGETS, FIELD_WIDGETS

        kind = skill_kind or self._detect_kind(component)
        config = getattr(component, "config", None)

        is_agent = kind == "agent"
        if is_agent:
            rules = AGENT_FIELD_MATRIX  # type: ignore[assignment]
            widget_map = AGENT_FIELD_WIDGETS  # type: ignore[assignment]
        else:
            rules = SKILL_FIELD_MATRIX.get(kind, {})  # type: ignore[assignment]
            widget_map = FIELD_WIDGETS  # type: ignore[assignment]

        self._loading = True
        try:
            skip = {SkillField.NAME, SkillField.DESCRIPTION}
            if is_agent:
                skip = {AgentField.NAME, AgentField.DESCRIPTION}  # type: ignore[assignment]

            # 에이전트는 emit 그룹 순서(FRONTMATTER → INVOCATION → SETTINGS)로
            # 정렬해 렌더링한다. 매트릭스 선언 순서에 의존하면 그룹 라벨과
            # 필드가 어긋날 수 있다 (예: SETTINGS 필드가 Invocation 라벨 아래 표시).
            items = list(rules.items())
            if is_agent:
                group_order = {
                    FieldEmit.FRONTMATTER: 0,
                    FieldEmit.BODY: 0,
                    FieldEmit.INVOCATION: 1,
                    FieldEmit.SETTINGS: 2,
                }
                items.sort(key=lambda kv: group_order[kv[1].emit])  # stable — 그룹 내 선언 순서 유지
            current_group: FieldEmit | None = None

            for fld, rule in items:
                if fld in skip:
                    continue
                if rule.visibility == FieldVisibility.FIXED:
                    continue
                if fld not in widget_map:
                    continue

                # emit 그룹 전환 시 구분 라벨 (에이전트 전용)
                if (
                    is_agent
                    and rule.emit in (FieldEmit.INVOCATION, FieldEmit.SETTINGS)
                    and rule.emit is not current_group
                ):
                    title = "Invocation" if rule.emit is FieldEmit.INVOCATION else "Settings"
                    self._add_span_row(QLabel(f"— {title} —"))
                    current_group = rule.emit

                widget = widget_map[fld]()
                container: QWidget | None = None
                self._apply_value(widget, config, component, fld, rule)
                self._wire_tool_candidates(fld, widget)
                self._field_widgets[fld] = widget
                self._connect_widget_signal(fld, widget)

                if rule.visibility == FieldVisibility.REQUIRED:
                    # 체크박스 열은 비운다 — 라벨·위젯 열은 OPTIONAL 행과 공유한다.
                    self._add_field_row(fld.value, widget)
                elif rule.visibility == FieldVisibility.OPTIONAL:
                    current = self._get_current(config, component, fld)
                    enabled = self._is_field_set(config, component, fld, current)
                    opt_row = _OptionalRow(fld.value, widget, initially_enabled=enabled)
                    # _OptionalRow 해제 시 config/component 값 클리어
                    opt_row.toggled.connect(
                        lambda checked, f=fld: self._on_optional_toggled(f, checked)
                    )
                    self._add_optional_row(opt_row)
                    # 잠금은 행 전체에 걸어야 한다 — 위젯만 잠그면 체크박스가
                    # 살아 있어 "켤 수는 있는데 아무 일도 안 일어나는" 상태가 된다
                    container = opt_row

                if is_agent:
                    self._apply_build_target_lock(fld, container or widget)
        finally:
            self._loading = False

        grid.setRowStretch(self._grid_row, 1)
        self.setWidget(inner)

    # ------------------------------------------------------------------
    # 그리드 배치 — 행 종류가 달라도 같은 열을 쓴다
    # ------------------------------------------------------------------

    def _add_span_row(self, widget: QWidget) -> None:
        """헤더·그룹 구분 라벨처럼 열 구분이 없는 항목 — 행 전체를 스팬한다."""
        self._grid.addWidget(widget, self._grid_row, 0, 1, _COL_COUNT)
        self._grid_row += 1

    def _add_span_layout(self, layout) -> None:
        """버튼 행 등 레이아웃 형태의 스팬 항목."""
        self._grid.addLayout(layout, self._grid_row, 0, 1, _COL_COUNT)
        self._grid_row += 1

    def _add_field_row(self, label: str, widget: QWidget) -> None:
        """라벨|위젯 한 행 — 체크박스 열은 빈 칸으로 남는다."""
        lbl = QLabel(label)
        lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._grid.addWidget(lbl, self._grid_row, _COL_LABEL)
        self._grid.addWidget(widget, self._grid_row, _COL_WIDGET)
        self._grid_row += 1

    def _add_optional_row(self, row: _OptionalRow) -> None:
        """체크박스|라벨|위젯 한 행 — 세 칸을 같은 열에 놓는다."""
        row.place_in(self._grid, self._grid_row)
        self._grid_row += 1

    def _apply_build_target_lock(self, fld, widget: QWidget) -> None:
        """빌드 타깃이 지원하지 않는 에이전트 필드를 잠근다 (WP-EL).

        CC는 플러그인 서브에이전트의 hooks/mcpServers/permissionMode를 보안상
        무시한다. 편집을 그대로 두면 "설정했는데 아무 일도 일어나지 않는" 상태가
        된다 — 설계자가 건 제약이 조용히 사라지는 것이므로, 아예 만질 수 없게
        하고 이유를 툴팁으로 알린다.
        """
        from daedalus.model.plugin.field_matrix import agent_field_supported

        if agent_field_supported(fld, self._build_target):
            return
        reason = (
            f"마켓플레이스 플러그인에서는 '{fld.frontmatter_key}'가 무시됩니다"
            f" (CC 보안 정책). 프로젝트 속성에서 빌드 타깃을 '프로젝트 설치'로"
            f" 바꾸면 사용할 수 있습니다."
        )
        if isinstance(widget, _OptionalRow):
            # 세 칸이 그리드에 흩어져 있으므로 행이 스스로 전부 잠근다.
            widget.set_locked(reason)
            return
        widget.setEnabled(False)
        widget.setToolTip(reason)

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_kind(component: object) -> str:
        config = getattr(component, "config", None)
        if config is not None and hasattr(config, "kind"):
            return config.kind
        return "procedural"

    @staticmethod
    def _get_current(config: object, component: object, fld: SkillField | AgentField) -> object:
        """현재 값을 config 또는 component에서 읽어 반환한다."""
        if fld == SkillField.WHEN_TO_USE:
            return getattr(component, "when_to_use", None)
        attr = _FIELD_ATTR_MAP.get(fld)
        if attr and config is not None:
            return getattr(config, attr, None)
        return None

    @staticmethod
    def _apply_value(widget, config, component, fld: SkillField | AgentField, rule) -> None:
        """현재 값(config / component)을 위젯에 채운다."""
        current = _FrontmatterPanel._get_current(config, component, fld)
        adapter = _adapter_for(widget)
        if adapter is not None:
            adapter[2](widget, current, rule)

    @staticmethod
    def _wire_tool_candidates(fld: SkillField | AgentField, widget: QWidget) -> None:
        """ALLOWED_TOOLS/TOOLS/DISALLOWED_TOOLS TagInput에 동적 후보를 부착한다.

        후보는 app.py가 프로젝트 로드 시 등록한 제공자(카탈로그+빌트인+
        Agent(이름))에서 조회한다 — 생성 시점 스냅샷.

        HOOKS TagInput에는 hook_library 이름을 부착한다(같은 provider 패턴).
        """
        from daedalus.view.widgets.tag_input import get_tool_candidates
        if fld in _TOOL_CANDIDATE_FIELDS and isinstance(widget, TagInput):
            widget.set_candidates(get_tool_candidates())
        elif fld in (SkillField.HOOKS, AgentField.HOOKS) and isinstance(widget, TagInput):
            # hook_library 이름을 자동완성 후보로 — provider 함수를 호출해야
            # 모듈 변수 캡처 문제(임포트 시점 None)를 피한다.
            from daedalus.view.widgets.tag_input import get_hook_names
            names = get_hook_names()
            if names:
                widget.set_candidates(names)
        elif fld is AgentField.MCP_SERVERS and isinstance(widget, TagInput):
            # 사용 선언된 외부 플러그인이 제공하는 서버 + 프로젝트
            # mcp_server_defs 이름 (WP-WR — app.set_project가 provider 등록).
            # tools 후보에는 넣지 않는다(개별 도구 목록 미지원 — 사용자 확정).
            from daedalus.view.widgets.tag_input import get_mcp_server_candidates
            servers = get_mcp_server_candidates()
            if servers:
                widget.set_candidates(servers)

    @staticmethod
    def _read_widget_value(fld: SkillField | AgentField, widget: QWidget) -> object:
        """위젯의 현재 표시값을 추출한다 (시그널 연결과 재체크 복원이 공유)."""
        adapter = _adapter_for(widget)
        return adapter[1](widget) if adapter is not None else None

    def _connect_widget_signal(self, fld: SkillField | AgentField, widget: QWidget) -> None:
        """위젯 타입에 맞는 시그널을 공용 핸들러에 연결한다."""

        def handler(*_args, f=fld, w=widget) -> None:
            self._write_field(f, self._read_widget_value(f, w))

        adapter = _adapter_for(widget)
        if adapter is not None:
            getattr(widget, adapter[3]).connect(handler)

    def _write_field(self, fld: SkillField | AgentField, value: object) -> None:
        """write-back: 위젯 값을 config 또는 component에 기록하고 changed를 emit한다."""
        if self._loading:
            return

        config = getattr(self._component, "config", None)

        if fld == SkillField.WHEN_TO_USE:
            self._component.when_to_use = value  # type: ignore[attr-defined]
            # when_to_use는 텍스트 키스트로크 — content 채널로.
            self.content_changed.emit()
            return

        attr = _FIELD_ATTR_MAP.get(fld)
        if attr is None or config is None:
            return

        # Enum 역변환
        enum_type = _FIELD_ENUM_MAP.get(fld)
        if enum_type is not None and isinstance(value, str):
            try:
                value = enum_type(value)
            except ValueError:
                return  # 알 수 없는 값은 무시

        # hooks: dict[str, Any] 필드 — TagInput의 이름 목록을 dict로 변환,
        # 이미 존재하는 키의 본문은 보존
        if fld in (SkillField.HOOKS, AgentField.HOOKS) and isinstance(value, list):
            existing = getattr(config, attr, None)
            existing = existing if isinstance(existing, dict) else {}
            value = {name: existing.get(name, {}) for name in value}

        setattr(config, attr, value)
        self.changed.emit()

    def _build_component_action_row(self) -> None:
        """"미리보기" / "관련 경고" 버튼 행 (A9-1, A9-3).

        캔버스 우클릭 메뉴와 **같은 함수**를 부른다 — 여기서 산출을 따로
        만들거나 검증을 따로 돌리면 두 표면이 다른 답을 내게 된다.
        """
        row = QHBoxLayout()
        preview = QPushButton("미리보기")
        preview.setToolTip("이 컴포넌트가 어떤 파일로 나가는지 — 파일은 쓰지 않는다")
        preview.clicked.connect(self._show_preview)
        row.addWidget(preview)

        warn = QPushButton("관련 경고")
        warn.setToolTip("이 컴포넌트에 관한 검증 결과만 검증 패널에 표시한다")
        warn.clicked.connect(self._show_findings)
        row.addWidget(warn)
        row.addStretch()
        self._add_span_layout(row)
        self._preview_btn = preview
        self._findings_btn = warn

    def _main_window(self):
        """이 패널이 놓인 최상위 창 — 프로젝트/검증 패널에 닿는 통로."""
        return self.window()

    def _show_preview(self) -> None:
        from daedalus.view.actions.preview import show_preview_dialog

        window = self._main_window()
        project = getattr(window, "_project", None)
        resolved = window.resolved_hooks() if hasattr(window, "resolved_hooks") else None
        show_preview_dialog(
            window, self._component, project=project, resolved_hooks=resolved,
        )

    def _show_findings(self) -> None:
        window = self._main_window()
        if hasattr(window, "show_component_findings"):
            window.show_component_findings(self._component)

    def _build_entry_preset_row(self, component) -> None:
        """진입 의미론 프리셋 콤보 (A8).

        `user_invocable`/`disable_model_invocation` 개별 체크 행은 그대로 남는다 —
        이 콤보는 그 둘을 **뜻으로 고르는 지름길**이고, 캔버스 노드 우클릭 메뉴와
        `view/actions/entrypoint.apply_entry_preset` 하나를 공유한다.

        `project_vm`이 없으면(에디터를 단독으로 띄우는 테스트 등) 콤보를 만들지
        않는다 — 적용이 커맨드 스택을 거쳐야 하는데 스택이 없기 때문이다.
        """
        from daedalus.view.actions.entrypoint import ENTRY_PRESETS, supports_entry_presets

        if self._project_vm is None or not supports_entry_presets(component):
            return

        combo = QComboBox()
        combo.addItem("(직접 지정)", None)
        for spec in ENTRY_PRESETS:
            combo.addItem(spec.label, spec.preset)
            combo.setItemData(
                combo.count() - 1, spec.description, Qt.ItemDataRole.ToolTipRole
            )
        combo.setCurrentIndex(self._entry_preset_index(component))
        combo.currentIndexChanged.connect(self._on_entry_preset_chosen)
        self._add_field_row("진입 설정", combo)
        self._entry_preset_combo = combo

    def _entry_preset_index(self, component) -> int:
        """현재 값에 맞는 콤보 인덱스. 어느 프리셋도 아니면 0("(직접 지정)")."""
        from daedalus.view.actions.entrypoint import ENTRY_PRESETS, current_entry_preset

        current = current_entry_preset(component)
        for i, spec in enumerate(ENTRY_PRESETS, start=1):
            if spec.preset is current:
                return i
        return 0

    def _on_entry_preset_chosen(self, _index: int) -> None:
        from daedalus.view.actions.entrypoint import apply_entry_preset

        combo = self._entry_preset_combo
        if self._loading or combo is None or self._project_vm is None:
            return
        preset = combo.currentData()
        if preset is None:
            return
        if apply_entry_preset(self._project_vm, self._component, preset):
            # 개별 체크 행이 새 값을 보이도록 패널을 다시 그린다 — 프리셋과
            # 개별 행이 다른 값을 말하면 어느 쪽이 진실인지 알 수 없다.
            self.changed.emit()
            self._reload_entry_fields()

    def _reload_entry_fields(self) -> None:
        """프리셋 적용 후 두 필드의 위젯/체크 상태를 모델과 다시 맞춘다."""
        config = getattr(self._component, "config", None)
        if config is None:
            return
        self._loading = True
        try:
            for fld, attr in (
                (SkillField.USER_INVOCABLE, "user_invocable"),
                (SkillField.DISABLE_MODEL, "disable_model_invocation"),
            ):
                widget = self._field_widgets.get(fld)
                if widget is None:
                    continue
                value = getattr(config, attr, None)
                if isinstance(widget, QCheckBox):
                    widget.setChecked(bool(value))
                row = widget.parent()
                if isinstance(row, _OptionalRow):
                    row.set_checked(value is not None)
        finally:
            self._loading = False

    @classmethod
    def _is_field_set(
        cls, config: object, component: object, fld: SkillField | AgentField, current: object
    ) -> bool:
        """OPTIONAL 행의 체크 상태 — 이 값이 "지정된" 것인가.

        기본 판정은 "빈 값이 아님"이다. **tri-state 필드(A8 — 선언 기본값이 None인
        bool)에서는 명시 `False`도 지정**이므로 예외로 살린다 — 그렇지 않으면
        `user_invocable=False`(순수 상태로)를 지정한 스킬이 미지정처럼 보이고,
        패널을 다시 그리는 것만으로 체크가 풀린 것처럼 읽힌다.

        `background: bool = False`처럼 선언 기본값이 `False`인 필드는 종전대로
        미지정 취급이다(선언 기본값과 같은 값은 지정이 아니다).
        """
        if current is None or current == "" or current == []:
            return False
        if current is False:
            attr = _FIELD_ATTR_MAP.get(fld)
            owner = config if config is not None else component
            if attr is None or owner is None:
                return False
            return cls._declared_default(owner, attr, fld) is None
        return True

    @staticmethod
    def _declared_default(obj: object, attr: str, fld: SkillField | AgentField) -> object:
        """dataclass 선언 기본값(default / default_factory)을 조회한다.

        non-Optional 필드(context, shell, user_invocable 등)에 None을 기록해
        타입 계약을 깨지 않도록, 클리어 값은 선언 기본값으로 결정한다.
        default가 MISSING이면 기존 규칙(None / list 필드는 [])으로 폴백.
        """
        import dataclasses

        if dataclasses.is_dataclass(obj):
            for f in dataclasses.fields(obj):
                if f.name != attr:
                    continue
                if f.default is not dataclasses.MISSING:
                    return f.default
                if f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
                    return f.default_factory()  # type: ignore[misc]
                break
        return [] if fld in _LIST_FIELDS else None

    def _on_optional_toggled(self, fld: SkillField | AgentField, checked: bool) -> None:
        """_OptionalRow 토글 처리.

        - 해제: config/component 값을 dataclass 선언 기본값으로 리셋
        - 재체크: 위젯에 남아있는 표시값을 모델에 복원 (silent divergence 방지)
        """
        if self._loading:
            return

        if checked:
            widget = self._field_widgets.get(fld)
            if widget is not None:
                self._write_field(fld, self._read_widget_value(fld, widget))
            return

        config = getattr(self._component, "config", None)

        if fld == SkillField.WHEN_TO_USE:
            self._component.when_to_use = self._declared_default(  # type: ignore[attr-defined]
                self._component, "when_to_use", fld
            )
            self.changed.emit()
            return

        attr = _FIELD_ATTR_MAP.get(fld)
        if attr is None or config is None:
            return

        setattr(config, attr, self._declared_default(config, attr, fld))
        self.changed.emit()

    def _save_name(self) -> None:
        old_name = self._component.name
        new_name = self._w_name.text().strip()
        if not new_name:
            # 빈 이름 — 원복
            self._w_name.setText(old_name)
            return
        if new_name == old_name:
            return
        # 이름 변경 — renamed 시그널로 중복 검사/참조 갱신을 상위에 위임
        self.renamed.emit(self._component, old_name, new_name)
        # renamed 핸들러가 변경을 거부했으면 컴포넌트 이름이 old_name으로 유지됨.
        # 위젯을 항상 컴포넌트 실제 이름과 동기화한다.
        self._w_name.setText(self._component.name)
        self.changed.emit()

    def _save_desc(self) -> None:
        self._component.description = self._w_desc.toPlainText().strip()
        # description은 텍스트 키스트로크 — content 채널로.
        self.content_changed.emit()
