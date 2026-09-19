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

# (NO_PLACE_KINDS 퇴역 — WP-7 ②/WP-8. "캔버스에 아무 노드로도 놓이지 않는
#  종류"의 음성 목록을 문자열로 들고 있던 상수다. 뷰 경로와 MCP
#  `create_skill(x, y)`가 모두 배치 역할 선언(`KindSpec.placement`)을 직접
#  읽게 되면서 소비자가 0이 됐다 — 같은 사실을 두 곳에서 말하지 않는다.)

# (CREATABLE_KINDS는 "여기에 만들기" 빈 캔버스 메뉴(A9-9)와 함께 퇴역 —
#  이름을 정확히 타이핑해야 해서 쓰기 어려웠다(사용자 확정). 생성 표면은
#  레지스트리 "+" / 카탈로그 선언 후 드래그 / MCP create_skill이다.)


def make_component(
    window, kind: str, name: str, description: str = "", agent: str | None = None,
    source: str | None = None,
):
    """모델 객체만 만든다(프로젝트에 넣지 않는다). 미지 종류는 ``None``.

    **종류별 팩토리는 없다** (WP-3). 예전에는 여기 config kind → 람다 9개짜리
    표가 있었고, 새 종류를 만들면 그 표를 고쳐야 한다는 사실을 아무도 알려 주지
    않았다 — 빠뜨리면 레지스트리 "+"와 MCP `create_skill`에서 조용히 사라졌다.
    지금은 종류 레지스트리가 클래스를 고르고, **무엇으로 태어나는지는 그 종류
    자신이 안다**(`PluginComponent.new`/`creation_defaults`).

    FSM 팩토리는 창의 `_make_fsm`/`_make_agent_fsm`을 쓴다 — 레지스트리 생성
    경로가 쓰는 것과 같은 팩토리여야 만들어진 물건이 같다. 어느 쪽을 쓸지는
    버킷 선언이 답한다.

    `agent`·`source`는 **종류별 생성 인자**다(fork 스킬의 실행 기반 / 외부 정본
    참조) — 그 종류가 쓸 수 없는 인자는 여기 오기 전에 호출자가 거절한다.

    `description`은 MCP `create_skill`/`create_agent`가 생성과 동시에 설명을
    받기 때문에 있다(S1 — 그쪽이 자체 팩토리 dict를 들고 있던 것을 여기로
    환원했다). GUI 경로는 이름만 주고 설명은 편집기에서 채운다.

    미지 종류에 `None`을 돌려주는 것은 종전 계약이다 — 거절 문구는 호출자가
    소유한다(MCP `create_skill`은 고를 수 있는 종류를 함께 말한다).
    """
    from daedalus.model.plugin.kinds import CONFIG_KIND_INDEX
    from daedalus.model.plugin.roles import Bucket

    spec = CONFIG_KIND_INDEX.get(kind)
    if spec is None:
        return None
    fsm_factory = (
        window._make_agent_fsm if spec.bucket is Bucket.AGENTS else window._make_fsm
    )
    return spec.component_cls.new(
        name, description, fsm_factory=fsm_factory, agent=agent, source=source
    )


def placement_cmds(scene, window, component, x: float, y: float) -> list:
    """이 컴포넌트를 (x, y)에 놓는 커맨드들 — 놓이지 않는 종류면 빈 목록.

    생성 경로가 여럿이어도(레지스트리 · 캔버스 · MCP · 🔌 탭 등록) **배치의
    실체는 여기 하나**다. 참조로 배치되는 컴포넌트는 상태 노드가 아니라
    **참조 노드**로 놓인다(캔버스 드롭과 같은 커맨드·같은 판정
    `placement.is_reference_placed`).
    """
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.plugin.placement import (
        is_canvas_placeable,
        is_reference_placed,
    )
    from daedalus.view.canvas.sync import sync_refs_to_model
    from daedalus.view.commands.reference_commands import CreateRefCmd
    from daedalus.view.commands.state_commands import CreateStateCmd
    from daedalus.view.viewmodel.state_vm import ReferenceViewModel, StateViewModel

    project = window._project
    if project is None or not is_canvas_placeable(component):
        return []
    project_vm = scene._project_vm
    if is_reference_placed(component):
        rvm = ReferenceViewModel(model=component, x=x, y=y)
        return [CreateRefCmd(
            project_vm, rvm,
            sync_fn=lambda: sync_refs_to_model(
                project_vm, project.reference_placements
            ),
        )]
    state = SimpleState(name=component.name, skill_ref=component)
    vm = StateViewModel(model=state, x=x, y=y)
    return [CreateStateCmd(project_vm, vm, fsm=project.graph)]


def create_and_place(
    scene, window, kind: str, name: str, x: float, y: float, description: str = "",
    agent: str | None = None, source: str | None = None,
) -> object | None:
    """컴포넌트를 만들고 (배치 대상이면) 그 좌표에 놓는다 — 1 undo 단위.

    어느 노드로도 놓이지 않는 종류는 만들기만 한다.

    캔버스 "여기에 만들기" 메뉴가 퇴역한 뒤로도 이 경로는 살아 있다 — MCP
    `create_skill(x, y)`가 좌표를 주면 여기로 온다.
    """
    from daedalus.view.commands.base import Command, MacroCommand
    from daedalus.view.commands.component_commands import CreateComponentCmd

    project = window._project
    if project is None:
        return None
    component = make_component(
        window, kind, name, description, agent=agent, source=source
    )
    if component is None:
        return None

    children: list[Command] = [CreateComponentCmd(project, component)]
    children.extend(placement_cmds(scene, window, component, x, y))
    scene._project_vm.execute(
        MacroCommand(children, f"{kind} '{name}' 생성 + 배치")
    )
    return component
