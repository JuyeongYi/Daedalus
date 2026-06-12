from __future__ import annotations

from dataclasses import dataclass, field

from daedalus.model.fsm.blackboard import Blackboard
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.delegation import DelegationDef
from daedalus.model.plugin.hook import HookDef
from daedalus.model.plugin.skill import Skill
from daedalus.model.plugin.tool import Tool


def _make_project_graph() -> StateMachine:
    """프로젝트 그래프(워크플로 백킹 머신) 기본값.

    EntryPoint(name="start")를 시작 상태로 갖는 빈 머신. EntryPoint는 캔버스에
    '워크플로 시작점' 마커로 렌더링되고, 사용자가 EntryPoint → 첫 스킬로 전이를
    그어 시작점을 선언한다. blackboard.parent 배선은 PluginProject.__post_init__
    및 deserialize_project가 담당한다 (생성 경로의 책임).
    """
    entry = EntryPoint(name="start")
    return StateMachine(
        name="project_graph",
        initial_state=entry,
        states=[entry],
    )


@dataclass
class ReferencePlacement:
    """캔버스 위의 참조 노드 하나. 여러 상태가 공유 가능."""

    skill_name: str
    x: float = 0.0
    y: float = 0.0
    connected_states: list[str] = field(default_factory=list)


@dataclass
class PluginProject:
    name: str
    skills: list[Skill] = field(default_factory=list)
    agents: list[AgentDefinition] = field(default_factory=list)
    reference_placements: list[ReferencePlacement] = field(default_factory=list)
    delegations: list[DelegationDef] = field(default_factory=list)
    # 도구 선반 — BuiltinTool/MCPTool/UserDefinedTool의 단일 진실 (결정 Z: shelf).
    # FSM 전략의 ToolEvaluation/ToolExecution.tool은 여기 Tool.name을 이름으로 참조한다.
    tool_shelf: list[Tool] = field(default_factory=list)
    # 훅 라이브러리 — HookDef의 단일 진실 (tool_shelf와 동일 shelf 패턴).
    # ComponentConfig.hooks의 키는 여기 HookDef.name을 이름으로 참조한다.
    hook_library: list[HookDef] = field(default_factory=list)
    # 최상위 블랙보드 — schemas.json의 소스 (DynamicClass 정의의 단일 진실).
    # 에이전트/스킬 FSM의 blackboard.parent가 이 객체를 가리키도록 생성 경로에서 배선한다.
    blackboard: Blackboard = field(default_factory=Blackboard)
    # 프로젝트 워크플로 그래프 — 캔버스의 노드/전이가 정식 FSM 상태로 들어가는 백킹 머신.
    # EntryPoint(start) + 배치된 스킬/에이전트 placement(SimpleState with skill_ref) + 전이.
    # 직렬화/컴파일/검증의 단일 진실. graph.blackboard.parent는 __post_init__에서 배선.
    graph: StateMachine = field(default_factory=_make_project_graph)
    # 그래프 노드 위치 — 키는 state.id (AgentDefinition.graph_layout과 동일 규약, 이름 변경 안전).
    graph_layout: dict[str, list[float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # 블랙보드 스코핑 — 프로젝트 그래프 FSM의 blackboard를 최상위 블랙보드의
        # 자식으로 연결한다 (생성 경로의 책임). deserialize_project도 동일 배선을 한다.
        if self.graph.blackboard.parent is None:
            self.graph.blackboard.parent = self.blackboard
