# daedalus/view/editors/delegation_editor.py
"""위임 정의(DelegationDef) kind별 편집기.

더블클릭 → DelegationEditor 탭(MainWindow) 또는 다이얼로그(AgentEditor 사이드바).
편집 결과는 모델에 직접 기록 + notify (undo 커맨드화 범위 외 — 기존 스킬 에디터 폼 정책과 동일).
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.plugin.delegation import (
    AgoraDispatchDef,
    CompositionMode,
    DelegationDef,
    DispatchMode,
    DynamicWorkflowDef,
    PhaseSpec,
    TeamSpawnDef,
    TeammateSpec,
    WaitMode,
)
from daedalus.model.project import PluginProject


# 위임 kind → 표시 타이틀 — 생성 다이얼로그(app.py/agent_editor)와 창 제목의
# 단일 진실. 새 kind 추가 시 여기 한 곳만 갱신한다.
DELEGATION_KIND_TITLES: dict[str, str] = {
    "team_spawn": "👥 팀 Spawn (TeamSpawnDef)",
    "dynamic_workflow": "🔀 Dynamic Workflow (DynamicWorkflowDef)",
    "agora_dispatch": "🛰 Agora Dispatch (AgoraDispatchDef)",
}


# ──────────────────────────────────────────────────────────────────────────────
# 공통 헬퍼: 에이전트 이름 목록
# ──────────────────────────────────────────────────────────────────────────────

def _agent_names(project: PluginProject | None) -> list[str]:
    if project is None:
        return []
    return [a.name for a in project.agents]


def _agent_by_name(project: PluginProject | None, name: str):
    if project is None or not name:
        return None
    for a in project.agents:
        if a.name == name:
            return a
    return None


# ──────────────────────────────────────────────────────────────────────────────
# 공통 상단 위젯: wait_mode + composition + guidance
# ──────────────────────────────────────────────────────────────────────────────

class _CommonHeader(QWidget):
    """모든 kind 공통: wait_mode 콤보 + composition 콤보 + guidance 텍스트."""

    def __init__(
        self,
        deleg: DelegationDef,
        on_changed: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._deleg = deleg
        self._loading = False
        self._ext_on_changed = on_changed

        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 8)

        # wait_mode
        self._wait_combo = QComboBox()
        self._wait_combo.addItem("WAIT (결과 대기)", WaitMode.WAIT)
        self._wait_combo.addItem("FIRE_AND_FORGET (즉시 진행)", WaitMode.FIRE_AND_FORGET)
        form.addRow("완료 모드:", self._wait_combo)

        # composition
        self._comp_combo = QComboBox()
        self._comp_combo.addItem("EXPLICIT (명세 그대로)", CompositionMode.EXPLICIT)
        self._comp_combo.addItem("GUIDED (Claude가 스스로 결정)", CompositionMode.GUIDED)
        form.addRow("구성 모드:", self._comp_combo)

        # guidance
        guidance_lbl = QLabel("유도 보충 지침 (GUIDED):")
        self._guidance_edit = QTextEdit()
        self._guidance_edit.setMaximumHeight(60)
        self._guidance_edit.setPlaceholderText("GUIDED 모드일 때 Claude에게 전달할 보충 지침 (선택)")
        form.addRow(guidance_lbl, self._guidance_edit)

        self._load()
        self._wait_combo.currentIndexChanged.connect(self._on_changed)
        self._comp_combo.currentIndexChanged.connect(self._on_composition_changed)
        self._guidance_edit.textChanged.connect(self._on_changed)

    def _load(self) -> None:
        self._loading = True
        # wait_mode
        for i in range(self._wait_combo.count()):
            if self._wait_combo.itemData(i) is self._deleg.wait_mode:
                self._wait_combo.setCurrentIndex(i)
                break
        # composition
        for i in range(self._comp_combo.count()):
            if self._comp_combo.itemData(i) is self._deleg.composition:
                self._comp_combo.setCurrentIndex(i)
                break
        self._guidance_edit.setPlainText(self._deleg.guidance)
        self._update_guidance_enabled()
        self._loading = False

    def _update_guidance_enabled(self) -> None:
        guided = self._comp_combo.currentData() is CompositionMode.GUIDED
        self._guidance_edit.setEnabled(guided)

    def _on_composition_changed(self) -> None:
        self._update_guidance_enabled()
        self._on_changed()

    def _on_changed(self) -> None:
        if self._loading:
            return
        self._deleg.wait_mode = self._wait_combo.currentData()
        self._deleg.composition = self._comp_combo.currentData()
        self._deleg.guidance = self._guidance_edit.toPlainText()
        if self._ext_on_changed is not None:
            self._ext_on_changed()

    def is_guided(self) -> bool:
        return self._comp_combo.currentData() is CompositionMode.GUIDED


# ──────────────────────────────────────────────────────────────────────────────
# TeamSpawn 편집기 본체
# ──────────────────────────────────────────────────────────────────────────────

class _TeammateRow(QWidget):
    """팀원 1행: 에이전트 콤보 + count 스핀 + role_note 라인에딧 + 삭제 버튼."""

    def __init__(
        self,
        spec: TeammateSpec,
        agent_names: list[str],
        on_delete: Callable[[], None],
        on_changed: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._spec = spec
        self._on_changed = on_changed

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)

        self._agent_combo = QComboBox()
        self._agent_combo.addItem("(선택 없음)", None)
        for name in agent_names:
            self._agent_combo.addItem(f"🤖 {name}", name)
        lay.addWidget(self._agent_combo, 2)

        self._count_spin = QSpinBox()
        self._count_spin.setRange(1, 32)
        self._count_spin.setValue(spec.count)
        self._count_spin.setFixedWidth(60)
        lay.addWidget(self._count_spin)

        self._role_edit = QLineEdit()
        self._role_edit.setPlaceholderText("역할 메모")
        self._role_edit.setText(spec.role_note)
        lay.addWidget(self._role_edit, 3)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(24, 24)
        del_btn.clicked.connect(on_delete)
        lay.addWidget(del_btn)

        # 현재 agent_ref 복원
        if spec.agent_ref is not None:
            agent_name = getattr(spec.agent_ref, "name", None)
            idx = self._agent_combo.findData(agent_name)
            if idx >= 0:
                self._agent_combo.setCurrentIndex(idx)

        self._agent_combo.currentIndexChanged.connect(self._on_agent_changed)
        self._count_spin.valueChanged.connect(self._on_count_changed)
        self._role_edit.textChanged.connect(self._on_role_changed)

    def _on_agent_changed(self) -> None:
        # agent_ref 기록은 상위 _TeamSpawnBody._on_agent_ref_changed가
        # 콤보 데이터(이름)→객체 해소로 수행 — 여기서는 변경 통지만 한다.
        self._on_changed()

    def _on_count_changed(self) -> None:
        self._spec.count = self._count_spin.value()
        self._on_changed()

    def _on_role_changed(self) -> None:
        self._spec.role_note = self._role_edit.text()
        self._on_changed()

    def selected_agent_name(self) -> str | None:
        return self._agent_combo.currentData()


class _TeamSpawnBody(QWidget):
    def __init__(
        self,
        deleg: TeamSpawnDef,
        project: PluginProject | None,
        on_changed: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._deleg = deleg
        self._project = project
        self._on_changed = on_changed
        self._rows: list[_TeammateRow] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel("팀원 목록:")
        root.addWidget(self._label)

        self._rows_widget = QWidget()
        self._rows_lay = QVBoxLayout(self._rows_widget)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        self._rows_lay.setSpacing(2)
        root.addWidget(self._rows_widget)

        add_btn = QPushButton("+ 팀원 추가")
        add_btn.clicked.connect(self._add_teammate)
        root.addWidget(add_btn)

        self._load()

    def _load(self) -> None:
        for spec in self._deleg.teammates:
            self._add_row(spec)

    def _update_label(self, guided: bool) -> None:
        if guided:
            self._label.setText("구성 힌트 (선택) — GUIDED 모드: 아래 팀원 목록은 고정 명단이 아닌 힌트로 적용됩니다.")
        else:
            self._label.setText("팀원 목록:")

    def _add_teammate(self) -> None:
        from daedalus.model.plugin.agent import AgentDefinition
        # 임시 agent_ref: None으로 시작 — 사용자가 콤보에서 선택 후 저장
        spec = TeammateSpec(agent_ref=None, count=1, role_note="")  # type: ignore[arg-type]
        self._deleg.teammates.append(spec)
        self._add_row(spec)
        self._on_changed()

    def _add_row(self, spec: TeammateSpec) -> None:
        def _delete(spec=spec) -> None:
            self._deleg.teammates.remove(spec)
            # 행 찾아 제거
            for row in list(self._rows):
                if row._spec is spec:
                    self._rows.remove(row)
                    self._rows_lay.removeWidget(row)
                    row.deleteLater()
                    break
            self._on_changed()

        row = _TeammateRow(
            spec,
            agent_names=_agent_names(self._project),
            on_delete=_delete,
            on_changed=self._on_agent_ref_changed,
        )
        self._rows.append(row)
        self._rows_lay.addWidget(row)

    def _on_agent_ref_changed(self) -> None:
        # agent_ref 동기화: 각 행의 선택된 이름 → 실제 AgentDefinition
        for row in self._rows:
            name = row.selected_agent_name()
            ref = _agent_by_name(self._project, name) if name else None
            row._spec.agent_ref = ref  # type: ignore[assignment]
        self._on_changed()

    def on_composition_changed(self, guided: bool) -> None:
        self._update_label(guided)


# ──────────────────────────────────────────────────────────────────────────────
# DynamicWorkflow 편집기 본체
# ──────────────────────────────────────────────────────────────────────────────

class _PhaseRow(QWidget):
    """워크플로 단계 1행: title 라인 + detail 텍스트 + agent 콤보 + 삭제."""

    def __init__(
        self,
        spec: PhaseSpec,
        agent_names: list[str],
        on_delete: Callable[[], None],
        on_changed: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._spec = spec
        self._on_changed = on_changed

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)

        top = QHBoxLayout()
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("단계 제목")
        self._title_edit.setText(spec.title)
        top.addWidget(self._title_edit, 3)

        self._agent_combo = QComboBox()
        self._agent_combo.addItem("(없음)", None)
        for name in agent_names:
            self._agent_combo.addItem(f"🤖 {name}", name)
        top.addWidget(self._agent_combo, 2)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(24, 24)
        del_btn.clicked.connect(on_delete)
        top.addWidget(del_btn)
        lay.addLayout(top)

        self._detail_edit = QLineEdit()
        self._detail_edit.setPlaceholderText("단계 상세 설명 (선택)")
        self._detail_edit.setText(spec.detail)
        lay.addWidget(self._detail_edit)

        # agent_ref 복원
        if spec.agent_ref is not None:
            agent_name = getattr(spec.agent_ref, "name", None)
            idx = self._agent_combo.findData(agent_name)
            if idx >= 0:
                self._agent_combo.setCurrentIndex(idx)

        self._title_edit.textChanged.connect(self._on_title_changed)
        self._detail_edit.textChanged.connect(self._on_detail_changed)
        self._agent_combo.currentIndexChanged.connect(lambda: on_changed())

    def _on_title_changed(self) -> None:
        self._spec.title = self._title_edit.text()
        self._on_changed()

    def _on_detail_changed(self) -> None:
        self._spec.detail = self._detail_edit.text()
        self._on_changed()

    def selected_agent_name(self) -> str | None:
        return self._agent_combo.currentData()


class _DynamicWorkflowBody(QWidget):
    def __init__(
        self,
        deleg: DynamicWorkflowDef,
        project: PluginProject | None,
        on_changed: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._deleg = deleg
        self._project = project
        self._on_changed = on_changed
        self._rows: list[_PhaseRow] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        self._objective_edit = QTextEdit()
        self._objective_edit.setMaximumHeight(60)
        self._objective_edit.setPlaceholderText("워크플로가 달성할 목표")
        self._objective_edit.setPlainText(deleg.objective)
        self._objective_label = QLabel("목표 (objective):")
        form.addRow(self._objective_label, self._objective_edit)
        root.addLayout(form)

        self._phases_label = QLabel("단계 목록:")
        root.addWidget(self._phases_label)

        self._rows_widget = QWidget()
        self._rows_lay = QVBoxLayout(self._rows_widget)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        self._rows_lay.setSpacing(2)
        root.addWidget(self._rows_widget)

        add_btn = QPushButton("+ 단계 추가")
        add_btn.clicked.connect(self._add_phase)
        root.addWidget(add_btn)

        self._objective_edit.textChanged.connect(self._on_objective_changed)
        self._load()

    def _load(self) -> None:
        for spec in self._deleg.phases:
            self._add_row(spec)

    def _on_objective_changed(self) -> None:
        self._deleg.objective = self._objective_edit.toPlainText()
        self._on_changed()

    def _add_phase(self) -> None:
        spec = PhaseSpec(title="")
        self._deleg.phases.append(spec)
        self._add_row(spec)
        self._on_changed()

    def _add_row(self, spec: PhaseSpec) -> None:
        def _delete(spec=spec) -> None:
            self._deleg.phases.remove(spec)
            for row in list(self._rows):
                if row._spec is spec:
                    self._rows.remove(row)
                    self._rows_lay.removeWidget(row)
                    row.deleteLater()
                    break
            self._on_changed()

        row = _PhaseRow(
            spec,
            agent_names=_agent_names(self._project),
            on_delete=_delete,
            on_changed=self._on_phase_agent_changed,
        )
        self._rows.append(row)
        self._rows_lay.addWidget(row)

    def _on_phase_agent_changed(self) -> None:
        for row in self._rows:
            name = row.selected_agent_name()
            ref = _agent_by_name(self._project, name) if name else None
            row._spec.agent_ref = ref  # type: ignore[assignment]
        self._on_changed()

    def on_composition_changed(self, guided: bool) -> None:
        hint = " — GUIDED 모드: 아래 내용은 힌트로 적용됩니다." if guided else ":"
        self._objective_label.setText(f"목표 (objective){hint}")
        self._phases_label.setText(f"단계 목록{hint}")


# ──────────────────────────────────────────────────────────────────────────────
# AgoraDispatch 편집기 본체
# ──────────────────────────────────────────────────────────────────────────────

class _AgoraDispatchBody(QWidget):
    def __init__(
        self,
        deleg: AgoraDispatchDef,
        project: PluginProject | None,
        on_changed: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._deleg = deleg
        self._on_changed = on_changed
        self._loading = False

        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)

        self._mode_combo = QComboBox()
        self._mode_combo.addItem("dispatch (단일 대상)", DispatchMode.DISPATCH)
        self._mode_combo.addItem("broadcast (전원 fan-out)", DispatchMode.BROADCAST)
        form.addRow("전송 모드:", self._mode_combo)

        self._target_edit = QLineEdit()
        self._target_edit.setPlaceholderText("대상 instance_id (자유 입력)")
        form.addRow("대상 (target):", self._target_edit)

        self._msgtype_edit = QLineEdit()
        self._msgtype_edit.setPlaceholderText("payload msgtype (필수)")
        form.addRow("메시지 타입 (msgtype):", self._msgtype_edit)

        self._payload_note_edit = QTextEdit()
        self._payload_note_edit.setMaximumHeight(80)
        self._payload_note_edit.setPlaceholderText("페이로드 구성 지침 (선택)")
        form.addRow("페이로드 지침:", self._payload_note_edit)

        # composition 안내 라벨
        info = QLabel(
            "composition 모드는 payload 구성에만 적용됩니다.\n"
            "(msgtype/target은 GUIDED에서도 명시 필수 — 스키마 정체성은 위임 불가)"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #888; font-size: 10px;")
        form.addRow(info)

        self._load()

        self._mode_combo.currentIndexChanged.connect(self._on_changed_slot)
        self._target_edit.textChanged.connect(self._on_changed_slot)
        self._msgtype_edit.textChanged.connect(self._on_changed_slot)
        self._payload_note_edit.textChanged.connect(self._on_changed_slot)

    def _load(self) -> None:
        self._loading = True
        for i in range(self._mode_combo.count()):
            if self._mode_combo.itemData(i) is self._deleg.mode:
                self._mode_combo.setCurrentIndex(i)
                break
        self._target_edit.setText(self._deleg.target)
        self._msgtype_edit.setText(self._deleg.msgtype)
        self._payload_note_edit.setPlainText(self._deleg.payload_note)
        self._loading = False

    def _on_changed_slot(self) -> None:
        if self._loading:
            return
        self._deleg.mode = self._mode_combo.currentData()
        self._deleg.target = self._target_edit.text()
        self._deleg.msgtype = self._msgtype_edit.text()
        self._deleg.payload_note = self._payload_note_edit.toPlainText()
        self._on_changed()

    def on_composition_changed(self, guided: bool) -> None:
        pass  # AgoraDispatch는 payload 쪽에만 적용 — 라벨 변경 불필요


# ──────────────────────────────────────────────────────────────────────────────
# 통합 편집기: DelegationEditor
# ──────────────────────────────────────────────────────────────────────────────

class DelegationEditor(QDialog):
    """위임 정의 kind별 폼 편집기.

    MainWindow에서는 탭 위젯으로, AgentEditor에서는 다이얼로그로 사용한다.
    on_notify_fn이 제공된 경우 모델 변경 시마다 호출된다.
    """

    def __init__(
        self,
        deleg: DelegationDef,
        on_notify_fn: Callable[[], None] | None = None,
        project: PluginProject | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._deleg = deleg
        self._on_notify_fn = on_notify_fn
        self._project = project

        self.setWindowTitle(
            f"{DELEGATION_KIND_TITLES.get(deleg.kind, 'Delegation')} — {deleg.name}"
        )
        self.resize(520, 600)

        root = QVBoxLayout(self)

        # deprecated 안내
        deprecation_notice = QLabel(
            "⚠ 위임 노드는 deprecated — 스킬 본문에 위임 지시를 직접 서술하는 방식을 권장합니다."
        )
        deprecation_notice.setWordWrap(True)
        deprecation_notice.setStyleSheet("color: #cc9944; font-size: 10px;")
        root.addWidget(deprecation_notice)

        # 이름
        name_lay = QHBoxLayout()
        name_lay.addWidget(QLabel("이름:"))
        self._name_edit = QLineEdit(deleg.name)
        self._name_edit.textChanged.connect(self._on_name_changed)
        name_lay.addWidget(self._name_edit)
        root.addLayout(name_lay)

        # 공통 헤더 (wait_mode / composition / guidance)
        self._header = _CommonHeader(deleg, on_changed=self._on_model_changed)
        root.addWidget(self._header)

        # kind별 본체
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body_widget = QWidget()
        body_lay = QVBoxLayout(body_widget)
        body_lay.setContentsMargins(4, 4, 4, 4)

        self._body: _TeamSpawnBody | _DynamicWorkflowBody | _AgoraDispatchBody | None = None
        if isinstance(deleg, TeamSpawnDef):
            self._body = _TeamSpawnBody(deleg, project, self._on_model_changed)
        elif isinstance(deleg, DynamicWorkflowDef):
            self._body = _DynamicWorkflowBody(deleg, project, self._on_model_changed)
        elif isinstance(deleg, AgoraDispatchDef):
            self._body = _AgoraDispatchBody(deleg, project, self._on_model_changed)

        if self._body is not None:
            body_lay.addWidget(self._body)
        body_lay.addStretch()
        scroll.setWidget(body_widget)
        root.addWidget(scroll, 1)

        # 다이얼로그 모드 버튼
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        root.addWidget(buttons)

        # composition 변경 시 본체 라벨 갱신 연동
        self._header._comp_combo.currentIndexChanged.connect(self._on_header_composition_changed)
        self._update_body_label()

    def _on_name_changed(self, text: str) -> None:
        self._deleg.name = text.strip() or self._deleg.name
        self._on_model_changed()

    def _on_model_changed(self) -> None:
        if self._on_notify_fn is not None:
            self._on_notify_fn()

    def _on_header_composition_changed(self) -> None:
        self._update_body_label()

    def _update_body_label(self) -> None:
        if self._body is not None and hasattr(self._body, "on_composition_changed"):
            self._body.on_composition_changed(self._header.is_guided())
