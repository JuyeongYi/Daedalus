from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4

from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.base import PluginComponent


class WaitMode(Enum):
    """위임 완료 대기 모드."""
    WAIT = "wait"                  # 위임 결과를 받은 뒤 전이
    FIRE_AND_FORGET = "forget"     # 위임 직후 즉시 진행


class DispatchMode(Enum):
    """AgentAgora 메시지 전송 모드."""
    DISPATCH = "dispatch"          # 단일 대상 (target 지정, 빈 값이면 schema-routed)
    BROADCAST = "broadcast"        # 자기 제외 전원 fan-out


@dataclass
class TeammateSpec:
    """팀원 한 명 — 프로젝트 내 에이전트 객체 참조."""
    agent_ref: AgentDefinition
    count: int = 1
    role_note: str = ""


@dataclass
class PhaseSpec:
    """워크플로 단계 하나."""
    title: str
    detail: str = ""
    agent_ref: AgentDefinition | None = None


@dataclass
class DelegationDef(PluginComponent, ABC):
    """CC 실행 단위에 일을 위임하는 노드의 공통 베이스.

    kind는 PluginComponent의 추상 프로퍼티로 남아 직접 인스턴스화가 막힌다.
    """
    wait_mode: WaitMode = WaitMode.WAIT
    # 안정 식별자 — 값 동등성 비교에서는 제외(compare=False).
    id: str = field(default_factory=lambda: uuid4().hex, compare=False, kw_only=True)


@dataclass
class TeamSpawnDef(DelegationDef):
    """AGENT_TEAM spawn — TeamCreate + 팀원 Agent spawn."""
    teammates: list[TeammateSpec] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return "team_spawn"


@dataclass
class DynamicWorkflowDef(DelegationDef):
    """Workflow 도구로 멀티에이전트 오케스트레이션을 작성·실행."""
    objective: str = ""
    phases: list[PhaseSpec] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return "dynamic_workflow"


@dataclass
class AgoraDispatchDef(DelegationDef):
    """AgentAgora 송신 — agora.dispatch / agora.broadcast."""
    mode: DispatchMode = DispatchMode.DISPATCH
    target: str = ""               # 대상 instance_id 자유 입력 (런타임 외부 존재)
    msgtype: str = ""              # payload msgtype 자유 입력
    payload_note: str = ""         # 페이로드 구성 지침

    @property
    def kind(self) -> str:
        return "agora_dispatch"
