# daedalus/view/actions/creation.py
"""컴포넌트 생성 + 캔버스 배치 (A9-9).

레지스트리에서 만들고 → 목록에서 찾아 → 캔버스로 드래그하는 세 걸음을, 놓고
싶은 자리에서 바로 만드는 한 걸음으로 줄인다.

**생성 자체는 레지스트리 경로와 같은 커맨드**(`CreateComponentCmd`)를 쓰고,
배치는 `CreateStateCmd` / 참조 노드 커맨드를 쓴다 — 여기서 새 경로를 발명하면
"어디서 만들었느냐에 따라 다른 물건이 되는" 상태가 된다. 둘을 `MacroCommand`로
묶어 **1 undo 단위**로 만드는 것이 이 모듈이 더하는 유일한 것이다.
"""
from __future__ import annotations

#: 캔버스에 **노드로 배치되지 않는** 종류 (레지스트리의 `no_place`와 같은 규칙).
#: declarative/transfer는 워크플로 노드가 아니다 — 만들기만 하고 배치는 없다.
NO_PLACE_KINDS: frozenset[str] = frozenset({"declarative", "transfer"})

#: 캔버스 "여기에 만들기" 메뉴에 낼 종류와 표시 문구 (표시 순서 = 이 순서).
CREATABLE_KINDS: tuple[tuple[str, str], ...] = (
    ("procedural", "Procedural Skill"),
    ("declarative", "Declarative Skill (배치 없음)"),
    ("reference", "Reference Skill"),
    ("agent", "Agent"),
)


def make_component(window, kind: str, name: str, description: str = ""):
    """모델 객체만 만든다(프로젝트에 넣지 않는다).

    FSM 생성은 창의 `_make_fsm`/`_make_agent_fsm`을 쓴다 — 레지스트리 생성
    경로가 쓰는 것과 같은 팩토리여야 만들어진 물건이 같다.

    `description`은 MCP `create_skill`/`create_agent`가 생성과 동시에 설명을
    받기 때문에 있다(S1 — 그쪽이 자체 팩토리 dict를 들고 있던 것을 여기로
    환원했다). GUI 경로는 이름만 주고 설명은 편집기에서 채운다.
    """
    from daedalus.model.fsm.section import EventDef
    from daedalus.model.plugin.agent import AgentDefinition
    from daedalus.model.plugin.skill import (
        DeclarativeSkill,
        ProceduralSkill,
        ReferenceSkill,
        TransferSkill,
    )

    factories = {
        "procedural": lambda: ProceduralSkill(
            fsm=window._make_fsm(name), name=name, description=description
        ),
        "declarative": lambda: DeclarativeSkill(name=name, description=description),
        "transfer": lambda: TransferSkill(
            fsm=window._make_fsm(name), name=name, description=description
        ),
        "reference": lambda: ReferenceSkill(name=name, description=description),
        "agent": lambda: AgentDefinition(
            fsm=window._make_agent_fsm(name), name=name, description=description,
            transfer_on=[EventDef(name="done")],
        ),
    }
    factory = factories.get(kind)
    return factory() if factory is not None else None


def create_and_place(
    scene, window, kind: str, name: str, x: float, y: float, description: str = ""
) -> object | None:
    """컴포넌트를 만들고 (배치 대상이면) 그 좌표에 놓는다 — 1 undo 단위.

    참조 스킬은 상태 노드가 아니라 **참조 노드**로 놓인다(캔버스 드롭과 같은
    커맨드). `NO_PLACE_KINDS`는 만들기만 한다.
    """
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.plugin.skill import ReferenceSkill
    from daedalus.view.canvas.sync import sync_refs_to_model
    from daedalus.view.commands.base import Command, MacroCommand
    from daedalus.view.commands.component_commands import CreateComponentCmd
    from daedalus.view.commands.reference_commands import CreateRefCmd
    from daedalus.view.commands.state_commands import CreateStateCmd
    from daedalus.view.viewmodel.state_vm import ReferenceViewModel, StateViewModel

    project = window._project
    if project is None:
        return None
    component = make_component(window, kind, name, description)
    if component is None:
        return None

    project_vm = scene._project_vm
    children: list[Command] = [CreateComponentCmd(project, component)]

    if kind not in NO_PLACE_KINDS:
        if isinstance(component, ReferenceSkill):
            rvm = ReferenceViewModel(model=component, x=x, y=y)
            children.append(CreateRefCmd(
                project_vm, rvm,
                sync_fn=lambda: sync_refs_to_model(
                    project_vm, project.reference_placements
                ),
            ))
        else:
            state = SimpleState(name=name, skill_ref=component)
            vm = StateViewModel(model=state, x=x, y=y)
            children.append(CreateStateCmd(project_vm, vm, fsm=project.graph))

    project_vm.execute(
        MacroCommand(children, f"{kind} '{name}' 생성 + 배치")
    )
    return component
