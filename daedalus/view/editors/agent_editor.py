# daedalus/view/editors/agent_editor.py
"""AgentDefinition 편집기 — 본문 + 포트, 스킬 편집기와 같은 레벨 (WP-AF).

내부 FSM(그래프 탭, EntryPoint/ExitPoint, 로컬 스킬)은 퇴역했다. Daedalus의
FSM은 런타임 엔진이 없어 내부 FSM이 사주는 것은 에이전트 .md 안의 번호 목록
텍스트뿐이었고, 같은 지시는 본문 산문이 동일한 효력을 낸다 — 형식화 비용
(그래프 탭·별도 CommandStack·로컬 스킬 기계장치)에 걸맞은 대가가 없었다
(사용자 확정 설계. 도그푸딩에서 손실·버그 대부분이 이 표면에서 났고, 실사용
세션은 에이전트를 내부 FSM 없이 본문만으로 만들었다).

살아남은 한 조각은 **출력 포트**다 — 프로젝트 그래프가 에이전트의 결과로
분기하므로(ExitPoint 이름이 전이 trigger였다), 이는 스킬의 transfer_on과 같은
개념이라 같은 필드·같은 편집 패널로 이관했다. v1 파일의 내부 FSM은 로드 시
ExitPoint → transfer_on 마이그레이션으로 흡수된다(serialize._migrate_v1).
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.project import PluginProject


class _CallersPanel(QWidget):
    """이 에이전트를 부르는 경로 목록 — 읽기 전용 (A9-4).

    캔버스 우클릭 "호출자 목록"과 **같은 유도 함수**(`agent_links.callers_of`)를
    쓴다. 화면과 컴파일 산출("## 호출 계약")이 다른 목록을 말하면 안 된다.
    """

    def __init__(self, agent: AgentDefinition, project, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QLabel, QListWidget

        self._agent = agent
        self._project = project

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(QLabel("← 호출자 (그래프에서 유도, 읽기 전용)"))
        self._list = QListWidget()
        lay.addWidget(self._list, 1)
        self._empty_label = QLabel(
            "이 에이전트를 부르는 노드가 없습니다 — 호출자 스킬에 에이전트 호출 "
            "포트를 만들고 캔버스에서 이어 주세요."
        )
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet("color: #888888;")
        lay.addWidget(self._empty_label)
        self.refresh()

    def refresh(self) -> None:
        from PySide6.QtWidgets import QListWidgetItem

        from daedalus.view.actions.agent_links import callers_of

        self._list.clear()
        refs = callers_of(self._agent, self._project)
        for ref in refs:
            item = QListWidgetItem(ref.label)
            if ref.description:
                item.setToolTip(ref.description)
            self._list.addItem(item)
        self._list.setVisible(bool(refs))
        self._empty_label.setVisible(not refs)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        # 캔버스에서 전이를 이은 뒤 탭으로 돌아오면 반영돼야 한다.
        self.refresh()
        super().showEvent(event)


class AgentEditor(QWidget):
    """AgentDefinition 편집기 — ComponentEditor + 출력 포트 패널·호출자 목록."""

    agent_changed = Signal()

    def __init__(
        self,
        agent: AgentDefinition,
        on_notify_fn: Callable[[], None] | None = None,
        project: PluginProject | None = None,
        parent: QWidget | None = None,
        project_vm=None,
    ) -> None:
        super().__init__(parent)
        self._agent = agent
        self._on_notify_fn = on_notify_fn
        self._project = project

        from daedalus.view.editors.component_editor import ComponentEditor
        from daedalus.view.editors.skill_editor import _TransferOnPanel

        # 출력 포트 — 프로젝트 그래프가 이 이름으로 분기한다 (스킬과 동일 패턴).
        self._transfer_on_panel = _TransferOnPanel(
            self._agent.transfer_on, title="→ 출력 포트",
        )
        self._transfer_on_panel.transfer_on_changed.connect(self._on_model_changed)

        # 호출자 목록 (A9-4) — **읽기 전용**이다. 누가 이 에이전트를 부르는지는
        # 모델에 적혀 있지 않고 프로젝트 그래프에서 유도할 뿐이라(WP-CT), 여기서
        # 편집하게 하면 같은 사실의 소스가 둘이 된다. 편집은 호출자 쪽 call_agents
        # 포트와 캔버스 전이에서 한다.
        self._callers_panel = _CallersPanel(self._agent, self._project)

        # WP-IP — 입력 경로 패널은 퇴역했다(출력 포트만 남는다).
        self._component_editor = ComponentEditor(
            self._agent,
            right_widgets=[self._transfer_on_panel, self._callers_panel],
            on_notify_fn=self._on_model_changed,
            # 빌드 타깃이 지원하지 않는 필드를 잠그기 위해 전달 (WP-EL)
            build_target=getattr(self._project, "build_target", None),
            project_vm=project_vm,
        )

        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.addWidget(self._component_editor)

    def _on_model_changed(self) -> None:
        self.agent_changed.emit()
        if self._on_notify_fn is not None:
            self._on_notify_fn()
