"""컴포넌트 생성/이름변경/삭제 커맨드 (WP-CE 1차 + A2).

여기까지 커맨드화된 편집은 캔버스 구조뿐이었다 — 스킬·에이전트를 만들고 이름을
바꾸는 것은 모델에 직접 쓰고 있어서 Ctrl+Z가 듣지 않았고, MCP 표면에도 올릴 수
없었다(AI 편집만 되돌릴 수 없는 비대칭이 생긴다).

**삭제(A2)는 수제 스냅샷이 아니라 기존 커맨드 조립이다.** ``remove_component``가
정리하는 범위(그래프 placement + 연결 전이, 참조 배치, skill_ref None화, 목록
제거)를 통째로 스냅샷 뜨는 대신, **캔버스 정리는 이미 정확한 기존 커맨드로**
(``DeleteRefCmd``/``DeleteTransitionCmd``/``DeleteStateCmd``) 조립하고 **모델
전용 잔여분만** ``_DetachComponentCmd``가 맡는다. 조립 순서 덕에 잔여분이
작아진다 — 캔버스 커맨드가 placement를 먼저 떼어내므로 ``remove_component``가
그 단계를 지나칠 때 할 일이 남아 있지 않다.

기존 커맨드 재사용이 스냅샷 복원보다 나은 실질적 이유는 **뷰모델 identity가
보존된다**는 것이다: undo가 같은 ``StateViewModel``/``TransitionViewModel``
객체를 되돌려 놓으므로 노드 좌표·엣지 경유점이 layout dict를 거치지 않고 그대로
살아난다(모델을 다시 읽어 VM을 재구성하면 그 왕복에서 잃는다).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from daedalus.view.commands.base import Command, MacroCommand

if TYPE_CHECKING:
    from daedalus.model.project import PluginProject
    from daedalus.view.viewmodel.project_vm import ProjectViewModel


def _bucket(project: PluginProject, component: object) -> list:
    """컴포넌트가 들어갈 프로젝트 리스트를 고른다."""
    from daedalus.model.plugin.agent import AgentDefinition

    if isinstance(component, AgentDefinition):
        return project.agents
    return project.skills


class CreateComponentCmd(Command):
    """스킬/에이전트를 프로젝트에 등록한다."""

    def __init__(self, project: PluginProject, component: object) -> None:
        self._project = project
        self._component = component

    @property
    def description(self) -> str:
        kind = getattr(self._component, "kind", type(self._component).__name__)
        return f"{kind} '{getattr(self._component, 'name', '?')}' 생성"

    @property
    def script_repr(self) -> str:
        kind = getattr(self._component, "kind", "component")
        return f'create_component("{getattr(self._component, "name", "?")}", kind="{kind}")'

    def execute(self) -> None:
        bucket = _bucket(self._project, self._component)
        if not any(c is self._component for c in bucket):
            bucket.append(self._component)
        # 블랙보드 스코핑 배선 — 생성 경로의 책임(app._register_component와 동일).
        fsm = getattr(self._component, "fsm", None)
        if fsm is not None and fsm.blackboard.parent is None:
            fsm.blackboard.parent = self._project.blackboard

    def undo(self) -> None:
        bucket = _bucket(self._project, self._component)
        for i, existing in enumerate(bucket):
            if existing is self._component:
                del bucket[i]
                break


class RenameComponentCmd(Command):
    """컴포넌트 이름 변경 — 문자열 참조 3종까지 함께 되돌린다.

    ``rename_component``가 참조 갱신을 전담하므로, undo도 같은 함수를 옛 이름으로
    한 번 더 부르면 참조가 대칭으로 되돌아온다.
    """

    def __init__(
        self, project: PluginProject, component: object, old_name: str, new_name: str
    ) -> None:
        self._project = project
        self._component = component
        self._old_name = old_name
        self._new_name = new_name

    @property
    def description(self) -> str:
        return f"컴포넌트 이름 변경: '{self._old_name}' → '{self._new_name}'"

    @property
    def script_repr(self) -> str:
        return f'rename_component("{self._old_name}", "{self._new_name}")'

    def execute(self) -> None:
        from daedalus.model.project import rename_component

        rename_component(self._project, self._component, self._new_name)

    def undo(self) -> None:
        from daedalus.model.project import rename_component

        rename_component(self._project, self._component, self._old_name)


# ---------------------------------------------------------------------------
# 삭제 (A2)
# ---------------------------------------------------------------------------


class _DetachComponentCmd(Command):
    """``remove_component``의 **모델 전용 잔여분**을 되돌릴 수 있게 감싼다.

    캔버스 커맨드가 placement와 참조 노드를 먼저 떼어낸 뒤에 실행되므로, 여기서
    ``remove_component``가 실제로 하는 일은 ① skills/agents 목록에서 제거
    ② 남은 reference_placements 정리 ③ 다른 FSM의 skill_ref → None 셋뿐이다.

    되돌릴 상태는 execute **직전**에 직접 뜬다(``remove_component``의 반환값은
    사람이 읽는 로그 문자열이라 복원 정보가 없다). 매 execute마다 다시 뜨는데,
    undo가 앞 상태를 정확히 복원하므로 redo가 같은 스냅샷을 다시 잡는다.

    **config.skills / ProceduralSkillConfig.agent의 이름 참조는 건드리지 않는다** —
    ``remove_component``도 건드리지 않기 때문이다(남은 참조는
    ``dangling_string_reference`` 경고가 짚는다). 여기서 임의로 지우면 삭제를
    되돌려도 참조가 돌아오지 않는 비대칭이 생긴다.
    """

    def __init__(self, project: PluginProject, component: object) -> None:
        self._project = project
        self._component = component
        self._bucket_index: int = -1
        self._ref_placements: list[tuple[list, list]] = []
        self._nullified: list[object] = []

    @property
    def description(self) -> str:
        kind = getattr(self._component, "kind", type(self._component).__name__)
        return f"{kind} '{getattr(self._component, 'name', '?')}' 모델 정리"

    @property
    def script_repr(self) -> str:
        return f'# 모델 정리: {getattr(self._component, "name", "?")}'

    def _ref_placement_lists(self) -> list[list]:
        lists = [self._project.reference_placements]
        for agent in self._project.agents:
            placements = getattr(agent, "reference_placements", None)
            if isinstance(placements, list):
                lists.append(placements)
        return lists

    def _skill_ref_holders(self) -> list[object]:
        """skill_ref가 이 컴포넌트를 가리키는 SimpleState/Transition 전부.

        ``remove_component``의 4단계와 **같은 범위**(project.skills/agents의 FSM,
        CompositeState/Region 재귀 — 골격은 ``model/fsm/walk.py`` 단일 진실)를
        훑는다. 프로젝트 그래프는 여기 없다 — 그쪽 placement는 캔버스 커맨드가
        통째로 떼어내며 skill_ref를 유지한다.
        """
        from daedalus.model.fsm.state import SimpleState
        from daedalus.model.fsm.walk import iter_states, iter_transitions

        found: list[object] = []

        def _scan(sm) -> None:
            if sm is None:
                return
            for state in iter_states(sm):
                if isinstance(state, SimpleState) and state.skill_ref is self._component:
                    found.append(state)
            for trans in iter_transitions(sm):
                if trans.skill_ref is self._component:
                    found.append(trans)

        for owner in list(self._project.skills) + list(self._project.agents):
            _scan(getattr(owner, "fsm", None))
        return found

    def execute(self) -> None:
        from daedalus.model.plugin.agent import AgentDefinition
        from daedalus.model.project import remove_component

        bucket = (
            self._project.agents
            if isinstance(self._component, AgentDefinition)
            else self._project.skills
        )
        self._bucket_index = next(
            (i for i, item in enumerate(bucket) if item is self._component), -1
        )
        self._ref_placements = [
            (lst, list(lst)) for lst in self._ref_placement_lists()
        ]
        self._nullified = self._skill_ref_holders()

        remove_component(self._project, self._component)

    def undo(self) -> None:
        from daedalus.model.plugin.agent import AgentDefinition

        bucket = (
            self._project.agents
            if isinstance(self._component, AgentDefinition)
            else self._project.skills
        )
        if not any(item is self._component for item in bucket):
            if 0 <= self._bucket_index <= len(bucket):
                bucket.insert(self._bucket_index, self._component)
            else:
                bucket.append(self._component)
        # 리스트 객체 identity를 유지한 채 내용을 되돌린다 — 새 리스트를 대입하면
        # 이 리스트를 들고 있는 다른 코드(에이전트 dataclass 필드 등)가 어긋난다.
        for lst, saved in self._ref_placements:
            lst[:] = saved
        for holder in self._nullified:
            holder.skill_ref = self._component  # type: ignore[attr-defined]


def _canvas_cleanup_commands(
    project: PluginProject, project_vm: ProjectViewModel, component: object
) -> list[Command]:
    """이 컴포넌트가 캔버스에서 차지하는 것들을 떼어내는 기존 커맨드 목록.

    순서가 곧 정확성이다 — 참조 링크/노드 → 전이 → 상태. 전이를 먼저 지워야
    상태 삭제 후에 출발지/도착지 없는 전이가 남지 않는다.
    """
    from daedalus.view.canvas.sync import sync_refs_to_model
    from daedalus.view.commands.reference_commands import DeleteRefCmd
    from daedalus.view.commands.state_commands import DeleteStateCmd
    from daedalus.view.commands.transition_commands import DeleteTransitionCmd

    def _sync_refs() -> None:
        sync_refs_to_model(project_vm, project.reference_placements)

    commands: list[Command] = []

    # 1) 참조 노드 — 같은 ReferenceSkill이 여러 번 놓일 수 있으므로 전부.
    #    DeleteRefCmd가 연결 링크까지 함께 처리하고 모델 동기화도 한다.
    for rvm in [r for r in project_vm.reference_vms if r.model is component]:
        commands.append(DeleteRefCmd(project_vm, rvm, sync_fn=_sync_refs))

    # 2) placement 노드 — 모델 그래프가 기준이고 VM은 그것의 투영이다.
    #    VM이 없는 placement(캔버스를 로드하지 않은 경로)는 그 자리에서
    #    만들어 준다 — 없다고 건너뛰면 그 노드만 삭제되지 않고 남는다.
    from daedalus.model.fsm.state import SimpleState
    from daedalus.view.viewmodel.state_vm import StateViewModel

    vm_by_state = {id(vm.model): vm for vm in project_vm.state_vms}
    placement_vms: list[StateViewModel] = []
    for state in project.graph.states:
        if not (isinstance(state, SimpleState) and state.skill_ref is component):
            continue
        vm = vm_by_state.get(id(state))
        if vm is None:
            saved = project.graph_layout.get(state.id) or [0.0, 0.0]
            vm = StateViewModel(model=state, x=saved[0], y=saved[1])
        placement_vms.append(vm)

    removed_ids = {id(vm.model) for vm in placement_vms}
    if removed_ids:
        vm_by_transition = {id(tvm.model): tvm for tvm in project_vm.transition_vms}
        for trans in project.graph.transitions:
            if id(trans.source) not in removed_ids and id(trans.target) not in removed_ids:
                continue
            tvm = vm_by_transition.get(id(trans))
            if tvm is None:
                continue  # VM 없는 전이 — 아래 remove_component 잔여분이 처리한다
            commands.append(DeleteTransitionCmd(project_vm, tvm, fsm=project.graph))

    for vm in placement_vms:
        commands.append(DeleteStateCmd(project_vm, vm, fsm=project.graph))

    return commands


class RemoveComponentCmd(MacroCommand):
    """컴포넌트 삭제 — 1 undo 단위 (A2).

    GUI 레지스트리 삭제와 MCP ``delete_component``가 **같은 커맨드**를 쓴다.
    조작 경로에 따라 되돌릴 수 있고 없고가 갈리면 협업 도구로 실격이다.

    자식 목록은 생성 시점의 모델을 보고 만든다 — undo가 그 시점 상태를 정확히
    복원하므로 redo는 같은 자식을 그대로 다시 실행하면 된다.
    """

    def __init__(
        self, project: PluginProject, project_vm: ProjectViewModel, component: object
    ) -> None:
        self._component = component
        kind = getattr(component, "kind", type(component).__name__)
        name = getattr(component, "name", "?")
        children = _canvas_cleanup_commands(project, project_vm, component)
        children.append(_DetachComponentCmd(project, component))
        super().__init__(children, f"{kind} '{name}' 삭제")

    @property
    def script_repr(self) -> str:
        return f'delete_component("{getattr(self._component, "name", "?")}")'
