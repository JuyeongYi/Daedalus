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
개념이라 같은 필드·같은 편집 패널로 이관했다. 구버전 파일의 내부 FSM은 로드
시 ExitPoint → transfer_on 마이그레이션으로 흡수된다(serialize.py).
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.project import PluginProject


class AgentEditor(QWidget):
    """AgentDefinition 편집기 — ComponentEditor + 출력/입력 포트 패널."""

    agent_changed = Signal()

    def __init__(
        self,
        agent: AgentDefinition,
        on_notify_fn: Callable[[], None] | None = None,
        project: PluginProject | None = None,
        parent: QWidget | None = None,
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

        # WP-IP — 입력 경로 패널은 퇴역했다(출력 포트만 남는다).
        self._component_editor = ComponentEditor(
            self._agent,
            right_widgets=[self._transfer_on_panel],
            on_notify_fn=self._on_model_changed,
            # 빌드 타깃이 지원하지 않는 필드를 잠그기 위해 전달 (WP-EL)
            build_target=getattr(self._project, "build_target", None),
        )

        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.addWidget(self._component_editor)

    def _on_model_changed(self) -> None:
        self.agent_changed.emit()
        if self._on_notify_fn is not None:
            self._on_notify_fn()
