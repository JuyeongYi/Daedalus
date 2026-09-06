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

# (CREATABLE_KINDS는 "여기에 만들기" 빈 캔버스 메뉴(A9-9)와 함께 퇴역 —
#  이름을 정확히 타이핑해야 해서 쓰기 어려웠다(사용자 확정). 생성 표면은
#  레지스트리 "+" / 카탈로그 선언 후 드래그 / MCP create_skill이다.)


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
        WrappedSkill,
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
        "wrapped": lambda: WrappedSkill(
            fsm=window._make_fsm(name), name=name, description=description
        ),
        "agent": lambda: AgentDefinition(
            fsm=window._make_agent_fsm(name), name=name, description=description,
            transfer_on=[EventDef(name="done")],
        ),
    }
    factory = factories.get(kind)
    return factory() if factory is not None else None


def unique_component_name(project, base: str) -> str:
    """스킬·에이전트 이름과 겹치지 않는 이름 (겹치면 -2, -3 … 접미)."""
    taken = {c.name for c in list(getattr(project, "skills", None) or [])
             + list(getattr(project, "agents", None) or [])}
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


#: 레지스트리 🔗 후보 행이 캔버스로 끄는 드래그 mime 접두 (WP-WR) —
#: `wrapped-source:<source>`. 일반 컴포넌트 드래그(mime=컴포넌트 이름)와
#: 구분하는 단일 진실이고, canvas_view.dropEvent와 registry_panel이 함께 쓴다.
WRAPPED_SOURCE_MIME_PREFIX = "wrapped-source:"


def create_wrapped_skill(
    window, source: str, name: str | None = None, description: str = "",
    x: float | None = None, y: float | None = None,
    usage: str = "state",
):
    """WrappedSkill 생성 + source 대입 + 사용 플러그인 자동 선언 — 1 undo (WP-WR).

    레지스트리 🔗 후보 행의 캔버스 드롭과 MCP `create_skill(kind="wrapped",
    source=)`가 둘 다 이것을 부른다. source의 플러그인부가
    `project.external_plugins`에 없으면 **함께 선언한다**(사용자 확정 —
    사용하기로 한 플러그인은 목록에 자동 명시). 등록 전에 source를 채우므로
    undo/redo에 소스 없는 중간 상태가 없고, 선언 추가·(x/y가 있으면) 캔버스
    배치까지 MacroCommand 한 단위다 — `create_and_place`와 같은 결.

    usage(사용자 확정 2026-09-07): "state"(워크플로 단계 — SimpleState 배치·
    SKILL.md 산출) / "reference"(참조 노드 복수 배치 — 산출 파일 없음, 링크된
    노드에 consult 지시 합류). 생성 시 고정된다 — 한 스킬 두 용도 금지.
    """
    from daedalus.model.fsm.state import SimpleState
    from daedalus.view.canvas.sync import sync_refs_to_model
    from daedalus.view.commands.attr_commands import SetAttrCmd
    from daedalus.view.commands.base import Command, MacroCommand
    from daedalus.view.commands.component_commands import CreateComponentCmd
    from daedalus.view.commands.reference_commands import CreateRefCmd
    from daedalus.view.commands.state_commands import CreateStateCmd
    from daedalus.view.viewmodel.state_vm import ReferenceViewModel, StateViewModel

    if usage not in ("state", "reference"):
        raise ValueError(f"usage는 state 또는 reference여야 합니다 (받은 값: {usage!r}).")
    project = getattr(window, "_project", None)
    if project is None:
        return None
    if name is None:
        _, _, skill_part = source.partition(":")
        name = unique_component_name(project, skill_part.strip() or "wrapped-skill")
    component = make_component(window, "wrapped", name, description)
    if component is None:  # pragma: no cover — kind는 고정 문자열
        return None
    component.config.source = source
    component.config.usage = usage

    project_vm = window._project_vm
    children: list[Command] = [CreateComponentCmd(project, component)]
    plugin_id = source.partition(":")[0].strip()
    declared = list(getattr(project, "external_plugins", None) or [])
    if plugin_id and plugin_id not in declared:
        children.append(SetAttrCmd(
            project,
            "external_plugins",
            [*declared, plugin_id],
            label=f"외부 플러그인 사용 선언: {plugin_id}",
            script=f'external_plugins += "{plugin_id}"',
        ))
    if x is not None and y is not None:
        if usage == "reference":
            rvm = ReferenceViewModel(model=component, x=float(x), y=float(y))
            children.append(CreateRefCmd(
                project_vm, rvm,
                sync_fn=lambda: sync_refs_to_model(
                    project_vm, project.reference_placements
                ),
            ))
        else:
            state = SimpleState(name=name, skill_ref=component)
            vm = StateViewModel(model=state, x=float(x), y=float(y))
            children.append(CreateStateCmd(project_vm, vm, fsm=project.graph))
    project_vm.execute(
        children[0] if len(children) == 1
        else MacroCommand(children, f"wrapped '{name}' 생성 + 플러그인 선언")
    )
    return component


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
