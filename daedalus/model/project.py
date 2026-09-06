from __future__ import annotations

from dataclasses import dataclass, field

from daedalus.model.fsm.blackboard import Blackboard
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.hook import HookDef
from daedalus.model.plugin.skill import Skill
from daedalus.model.plugin.tool import Tool
from daedalus.model.plugin.workspace_doc import WorkspaceDoc


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
    description: str = ""      # 플러그인 설명 — plugin.json description (빈 값이면 키 생략)
    version: str = "0.1.0"     # 플러그인 버전 — plugin.json version (semver 문자열)
    skills: list[Skill] = field(default_factory=list)
    agents: list[AgentDefinition] = field(default_factory=list)
    reference_placements: list[ReferencePlacement] = field(default_factory=list)
    # 도구 선반 — BuiltinTool/MCPTool/UserDefinedTool의 단일 진실 (결정 Z: shelf).
    # FSM 전략의 ToolEvaluation/ToolExecution.tool은 여기 Tool.name을 이름으로 참조한다.
    tool_shelf: list[Tool] = field(default_factory=list)
    # 훅 라이브러리 — HookDef의 단일 진실 (tool_shelf와 동일 shelf 패턴).
    # ComponentConfig.hooks의 키는 여기 HookDef.name을 이름으로 참조한다.
    hook_library: list[HookDef] = field(default_factory=list)
    # WP-WD — 작업 폴더 문서. LOCAL 빌드에서만 배출된다(마켓플레이스 플러그인은
    # 작업 폴더에 쓸 수 없다). claude_md는 `.claude/CLAUDE.md`의 이 플러그인 구역
    # 이고 **최대 하나**라 리스트가 아니다 — 불변식을 검증이 아니라 구조로 지킨다.
    # rules는 `.claude/rules/<name>.md`로, 파일 하나가 문서 하나다.
    claude_md: WorkspaceDoc | None = None
    rules: list[WorkspaceDoc] = field(default_factory=list)
    # 최상위 블랙보드 — schemas.json의 소스 (DynamicClass 정의의 단일 진실).
    # 에이전트/스킬 FSM의 blackboard.parent가 이 객체를 가리키도록 생성 경로에서 배선한다.
    blackboard: Blackboard = field(default_factory=Blackboard)
    # 프로젝트 워크플로 그래프 — 캔버스의 노드/전이가 정식 FSM 상태로 들어가는 백킹 머신.
    # EntryPoint(start) + 배치된 스킬/에이전트 placement(SimpleState with skill_ref) + 전이.
    # 직렬화/컴파일/검증의 단일 진실. graph.blackboard.parent는 __post_init__에서 배선.
    graph: StateMachine = field(default_factory=_make_project_graph)
    # 그래프 노드 위치 — 키는 state.id (AgentDefinition.graph_layout과 동일 규약, 이름 변경 안전).
    graph_layout: dict[str, list[float]] = field(default_factory=dict)
    # WP-ER — 전이 엣지의 경유점(waypoint) 좌표. 키는 Transition.id(안정 식별자,
    # graph_layout의 state.id 규약과 동일), 값은 [x, y] 목록(소스→타깃 순서).
    # 웨이포인트는 뷰 관심사이므로 fsm 모델(Transition)에는 넣지 않는다.
    edge_layout: dict[str, list[list[float]]] = field(default_factory=dict)
    # WP-RS Part B — 세션 시작 시 진행 상태(state/__progress__.json) 자동 주입 SessionStart
    # 훅을 컴파일 시점에 합성 배출할지 여부. 기본 True. hook_library를 오염시키지
    # 않는다(compiler/emit.py의 compile_hooks_json이 컴파일 시점에 합성).
    # 구버전 프로젝트 파일(키 부재)은 True로 취급(deserialize_project).
    emit_progress_hook: bool = True
    # WP-TG — 빌드 타깃: 마켓플레이스 플러그인(기본) / 로컬 플러그인(.claude/ 반입형).
    # 프로젝트 생성 시 선택하고 프로젝트 속성에서 변경 가능. 구버전 프로젝트 파일
    # (키 부재)은 MARKETPLACE로 취급(deserialize_project) — 하위 호환 게이트.
    build_target: BuildTarget = BuildTarget.MARKETPLACE
    # WP-MW — MCP 서버 정의: 이름 → CC `.mcp.json` 서버 객체(JSON dict 그대로,
    # 예: {"type": "http", "url": "http://127.0.0.1:8787/mcp"}). 컴포넌트들은
    # 서버를 **이름**으로만 참조하는 원칙 그대로이고, 정의는 설치 배선에만 쓰인다 —
    # LOCAL 빌드는 컴파일이 곧 설치라(WP-MW) 컴파일이 대상 작업 폴더의 .mcp.json과
    # .claude/settings.local.json에 직접 병합한다(별도 설치 스크립트 없음).
    # 구버전 파일(키 부재)은 빈 dict.
    mcp_server_defs: dict[str, dict] = field(default_factory=dict)

    # 작업 폴더 settings.json 설정 (WP-WS) — LOCAL 빌드가 대상 작업 폴더의
    # .claude/settings.local.json에 베이크하는 설정 dict(JSON 호환). 편집은
    # QClaudeCodeSettingEditorWidget(external/ 서브모듈, 스키마 구동) 다이얼로그.
    # **hooks 키는 여기 두지 않는다** — 훅은 Daedalus의 hook_library가 정본이라
    # 편집 다이얼로그가 훅 카테고리를 제외하고, 저장·베이크 양쪽이 방어적으로
    # 걷어낸다(진실이 둘이면 병합 순서에 따라 다른 산출이 나온다).
    # MARKETPLACE에서는 배출되지 않는다(workspace_doc과 같은 제약 — 경고 규칙
    # workspace_settings_in_marketplace_build). 구버전 파일(키 부재)은 빈 dict.
    workspace_settings: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # 블랙보드 스코핑 — 프로젝트 그래프 FSM의 blackboard를 최상위 블랙보드의
        # 자식으로 연결한다 (생성 경로의 책임). deserialize_project도 동일 배선을 한다.
        if self.graph.blackboard.parent is None:
            self.graph.blackboard.parent = self.blackboard


# ---------------------------------------------------------------------------
# 컴포넌트 관리 — 순수 모델 함수 (Qt 무관, 단위 테스트 가능)
# ---------------------------------------------------------------------------


def rename_component(
    project: PluginProject,
    component: object,
    new_name: str,
) -> None:
    """컴포넌트 이름을 변경하고 관련 문자열 참조를 일괄 갱신한다.

    갱신 대상:
    - component.name 자체
    - ProceduralSkillConfig.agent (에이전트 이름 참조)
    - AgentConfig.skills (스킬 이름 리스트)
    - ReferencePlacement.skill_name (project + 각 agent의 reference_placements)

    ComponentConfig.hooks 키는 hook_library의 HookDef.name 참조로 컴포넌트 이름과
    무관하므로 건드리지 않는다.

    각 참조는 **참조 대상 타입별로 분리**해 갱신한다 — 동명-다른타입 컴포넌트
    (예: 스킬 "x"와 에이전트 "x")가 공존해도 무관 참조를 오갱신하지 않는다:
    - ProceduralSkillConfig.agent는 에이전트 이름 참조 → component가 에이전트일 때만
    - AgentConfig.skills는 스킬 이름 참조 → component가 스킬일 때만
    - ReferencePlacement.skill_name은 스킬 이름 참조 → component가 스킬일 때만
    """
    from daedalus.model.plugin.config import AgentConfig, ProceduralSkillConfig

    old_name: str = getattr(component, "name", "")
    if old_name == new_name:
        return

    is_agent = isinstance(component, AgentDefinition)
    is_skill = isinstance(component, Skill)

    # 1) 이름 자체 변경
    component.name = new_name  # type: ignore[union-attr]

    # 2) ProceduralSkillConfig.agent 갱신 — 에이전트 이름 참조
    if is_agent:
        for skill in project.skills:
            cfg = getattr(skill, "config", None)
            if isinstance(cfg, ProceduralSkillConfig) and cfg.agent == old_name:
                cfg.agent = new_name

    # 3) AgentConfig.skills 갱신 — 스킬 이름 참조
    if is_skill:
        for agent in project.agents:
            cfg = getattr(agent, "config", None)
            if isinstance(cfg, AgentConfig) and isinstance(cfg.skills, list):
                cfg.skills = [new_name if s == old_name else s for s in cfg.skills]

    # 4) ReferencePlacement.skill_name 갱신 — 스킬 이름 참조 (project + 각 agent)
    if is_skill:
        for rp in project.reference_placements:
            if rp.skill_name == old_name:
                rp.skill_name = new_name

        for agent in project.agents:
            for rp in getattr(agent, "reference_placements", []):
                if rp.skill_name == old_name:
                    rp.skill_name = new_name


def project_state_machines(project: PluginProject) -> list[StateMachine]:
    """프로젝트가 소유한 최상위 FSM 전부 — 그래프 + 각 스킬/에이전트 FSM.

    ``validation.project_rules.scan.project_machines``와 달리 라벨 없이 머신만
    주고 **프로젝트 그래프를 포함**한다(상태 reads/writes는 배치 노드에도 붙는다).
    """
    machines: list[StateMachine] = [project.graph]
    for skill in project.skills:
        fsm = getattr(skill, "fsm", None)
        if fsm is not None:
            machines.append(fsm)
    for agent in project.agents:
        fsm = getattr(agent, "fsm", None)
        if fsm is not None:
            machines.append(fsm)
    return machines


def _rename_access_path(path: str, old_name: str, new_name: str) -> str:
    """`"Class"` / `"Class.field"` 참조 하나의 클래스 부분만 갈아끼운다."""
    if path == old_name:
        return new_name
    if path.startswith(old_name + "."):
        return new_name + path[len(old_name) :]
    return path


def blackboard_rename_ref_updates(
    project: PluginProject, old_name: str, new_name: str
) -> list[tuple[object, str, list[str]]]:
    """블랙보드 클래스 개명 시 갱신될 상태 reads/writes를 **계산만** 한다.

    ``(state, "reads"|"writes", 새 리스트)`` 목록을 돌려주고 모델은 건드리지
    않는다 — GUI는 그대로 대입하고, MCP는 같은 값으로 ``SetAttrCmd``를 만들어
    undo 가능한 1 단위로 묶는다(적용 방식이 표면마다 다르되 **무엇을 갱신할지는
    한 곳에서 정해진다**).

    개명이 참조를 따라가는 것은 ``rename_component``의 관례와 같다 — 대상이
    그대로 있는데 참조만 끊기면 그 편집이 조용히 고장을 만든다. 반대로 **삭제는
    참조를 건드리지 않는다**(``remove_component``/``delete_hook``과 동일):
    undo로 클래스가 돌아왔는데 참조는 돌아오지 않는 비대칭을 만들지 않기 위해서다.

    실제로 바뀌는 항목만 담는다 — 값이 같은 SetAttrCmd를 쌓으면 Ctrl+Z가 빈
    단계를 센다.
    """
    from daedalus.model.fsm.walk import iter_states

    if not old_name or old_name == new_name:
        return []

    updates: list[tuple[object, str, list[str]]] = []
    for machine in project_state_machines(project):
        for state in iter_states(machine):
            for attr in ("reads", "writes"):
                current = list(getattr(state, attr, []) or [])
                renamed = [_rename_access_path(p, old_name, new_name) for p in current]
                if renamed != current:
                    updates.append((state, attr, renamed))
    return updates


def blackboard_class_referrers(project: PluginProject, name: str) -> list[str]:
    """`"name"` / `"name.field"`를 reads/writes로 참조하는 상태 이름 목록(정렬·중복 제거).

    삭제가 참조를 지우지 않으므로(위 참조), 호출자가 `still_referenced_by`로
    보고해 사용자가 정리할 수 있게 한다 — 남은 참조는 `dangling_blackboard_ref`
    경고가 이어서 짚는다.
    """
    from daedalus.model.fsm.walk import iter_states

    found: set[str] = set()
    for machine in project_state_machines(project):
        for state in iter_states(machine):
            paths = [
                *(getattr(state, "reads", []) or []),
                *(getattr(state, "writes", []) or []),
            ]
            if any(p == name or p.startswith(name + ".") for p in paths):
                found.add(getattr(state, "name", "?"))
    return sorted(found)


def remove_component(
    project: PluginProject,
    component: object,
) -> list[str]:
    """컴포넌트를 프로젝트에서 제거하고 관련 모델을 정리한다.

    정리 내역 문자열 리스트를 반환한다 (확인 다이얼로그 표시용).

    정리 항목:
    - project.skills / agents 에서 제거 (identity 비교)
    - project.graph 에서 해당 skill_ref를 가진 SimpleState + 연결 전이 제거
    - project.graph_layout 에서 해당 state.id 제거
    - project.reference_placements + 각 agent reference_placements에서 skill_name 일치 항목 제거
      (skill_name은 스킬 이름 참조 — component가 스킬일 때만, 동명-다른타입 오삭제 방지)
    - 다른 스킬/에이전트 FSM의 skill_ref(SimpleState/Transition.skill_ref)가 삭제 대상이면 None으로
    """
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.walk import iter_states, iter_transitions

    log: list[str] = []
    comp_name: str = getattr(component, "name", str(component))

    # --- 1) 최상위 목록에서 identity 제거 ---
    def _remove_by_identity(lst: list, label: str) -> bool:
        for i, item in enumerate(lst):
            if item is component:
                lst.pop(i)
                log.append(f"{label} '{comp_name}' 제거됨")
                return True
        return False

    removed = (
        _remove_by_identity(project.skills, "스킬")
        or _remove_by_identity(project.agents, "에이전트")
    )
    if not removed:
        log.append(f"'{comp_name}' — 목록에서 찾을 수 없음")

    # --- 2) project.graph에서 해당 placement 상태 + 전이 제거 ---
    states_to_remove: list = []
    for state in project.graph.states:
        if isinstance(state, SimpleState) and state.skill_ref is component:
            states_to_remove.append(state)

    removed_state_ids: set = {id(s) for s in states_to_remove}
    if states_to_remove:
        # 연결 전이 먼저 제거 (edge_layout 정리 대상 수집)
        transitions_to_remove = [
            t for t in project.graph.transitions
            if id(t.source) in removed_state_ids or id(t.target) in removed_state_ids
        ]
        project.graph.transitions = [
            t for t in project.graph.transitions
            if id(t.source) not in removed_state_ids and id(t.target) not in removed_state_ids
        ]
        project.graph.states = [
            s for s in project.graph.states if id(s) not in removed_state_ids
        ]
        for s in states_to_remove:
            # graph_layout에서 제거
            project.graph_layout.pop(s.id, None)
        for t in transitions_to_remove:
            # edge_layout(웨이포인트)에서 제거 (WP-ER)
            project.edge_layout.pop(t.id, None)
        log.append(f"캔버스 노드 {len(states_to_remove)}개 + 연결 전이 제거됨")

    # --- 3) reference_placements 정리 — skill_name은 스킬 이름 참조이므로
    #     component가 스킬일 때만 (동명 에이전트 삭제 시 오삭제 방지) ---
    if isinstance(component, Skill):
        def _clean_ref_placements(placements: list) -> int:
            before = len(placements)
            to_remove = [rp for rp in placements if rp.skill_name == comp_name]
            for rp in to_remove:
                placements.remove(rp)
            return before - len(placements)

        n_rp = _clean_ref_placements(project.reference_placements)
        for agent in project.agents:
            n_rp += _clean_ref_placements(getattr(agent, "reference_placements", []))
        if n_rp > 0:
            log.append(f"참조 배치 {n_rp}개 제거됨")

    # --- 4) 다른 FSM의 skill_ref → None 으로 ---
    def _nullify_skill_refs_in_machine(sm: StateMachine) -> int:
        # 재귀 골격(sub_machine/Region)은 model/fsm/walk.py가 단일 진실.
        count = 0
        for state in iter_states(sm):
            if isinstance(state, SimpleState) and state.skill_ref is component:
                state.skill_ref = None
                count += 1
        for trans in iter_transitions(sm):
            if trans.skill_ref is component:
                trans.skill_ref = None
                count += 1
        return count

    nullified = 0
    for skill in project.skills:
        fsm = getattr(skill, "fsm", None)
        if fsm is not None:
            nullified += _nullify_skill_refs_in_machine(fsm)
    for agent in project.agents:
        fsm = getattr(agent, "fsm", None)
        if fsm is not None:
            nullified += _nullify_skill_refs_in_machine(fsm)
    if nullified > 0:
        log.append(f"다른 FSM 내 skill_ref {nullified}개 → None")

    return log
