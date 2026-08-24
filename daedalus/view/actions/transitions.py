# daedalus/view/actions/transitions.py
"""전이 트리거 지정 (A9-8).

**지금까지 트리거를 바꾸는 GUI가 없었다.** 전이를 그을 때 어느 포트에서
끌었느냐로 정해지고, 그 뒤에는 MCP `set_transition`으로만 고칠 수 있었다 —
포트 이름을 바꾸거나 갈래를 잘못 물린 뒤에는 전이를 지우고 다시 긋는 수밖에
없었다.

후보는 **출발 노드가 선언한 출력 이벤트**다: 스킬의 `transfer_on` +
`call_agents`. 그것이 곧 캔버스에 그려지는 포트이고, 트리거는 그 포트를
가리키는 이름이다(`trigger_unknown_event` 경고가 어긋남을 짚는 것과 같은 관계).
"""
from __future__ import annotations

from daedalus.model.fsm.event import CompletionEvent


def trigger_choices(transition_vm) -> list[str]:
    """이 전이가 가질 수 있는 트리거 이름 — 출발 노드의 출력 이벤트 (선언 순서).

    `transfer_on` 다음 `call_agents` 순이고 중복은 제거한다. 에이전트가 출발이면
    그 `transfer_on`(출력 포트)이 후보다.
    """
    source = getattr(transition_vm.source_vm.model, "skill_ref", None)
    if source is None:
        return []
    names: list[str] = []
    for attr in ("transfer_on", "call_agents"):
        for event in getattr(source, attr, None) or []:
            name = getattr(event, "name", "")
            if name and name not in names:
                names.append(name)
    return names


def current_trigger(transition_vm) -> str:
    """현재 트리거 이름. 없으면 빈 문자열."""
    return getattr(getattr(transition_vm.model, "trigger", None), "name", "") or ""


def set_trigger(project_vm, transition_vm, name: str) -> bool:
    """전이 트리거를 바꾼다 (undo 가능). 빈 이름 = 트리거 없음.

    `CompletionEvent`를 **새로 만들어** 넣는다 — 기존 이벤트 객체의 name을
    제자리에서 고치면 `SetAttrCmd`의 old/new가 같은 객체를 가리켜 undo가 죽는다
    (attr_commands 모듈 docstring이 못 박은 규약).
    """
    from daedalus.view.commands.attr_commands import SetAttrCmd

    if current_trigger(transition_vm) == (name or ""):
        return False

    new_trigger = CompletionEvent(name=name) if name else None
    src = transition_vm.source_vm.model.name
    tgt = transition_vm.target_vm.model.name
    project_vm.execute(
        SetAttrCmd(
            transition_vm.model, "trigger", new_trigger,
            label=f"전이 '{src}→{tgt}' 트리거 → {name or '(없음)'}",
            script=f'set_transition("{src}", "{tgt}", trigger="{name}")',
        )
    )
    return True
