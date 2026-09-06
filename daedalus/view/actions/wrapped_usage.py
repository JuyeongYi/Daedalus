# daedalus/view/actions/wrapped_usage.py
"""랩핑 스킬 용도 전환 (WP-WR) — state ↔ reference.

최초 배치가 용도를 고정하지만(한 스킬 두 용도 금지), **나중에 바꾸는 길**은
있어야 한다 — 없으면 삭제·재생성뿐이라 이름·설명·프론트매터·source를 전부
다시 입력해야 하고, 이미 연결된 배선은 되돌릴 수 없다(사용자 보고 2026-09-07).

지켜야 할 불변식은 "**동시에** 두 용도로 쓰이지 않는다"이지 "영원히 못
바꾼다"가 아니다. 그래서 전환은 기존 배치를 모두 걷어낸 뒤에만 성립한다:

- 배치가 없으면 `SetAttrCmd` 하나로 끝난다(undo 가능).
- 배치가 있으면 기본은 **거부**하고 무엇을 지워야 하는지 알려준다. 조용히
  지우면 사용자가 그은 전이가 말없이 사라진다.
- `force=True`면 삭제 커맨드와 전환을 `MacroCommand`로 묶어 **1 undo**로
  만든다. 삭제 조립은 `RemoveComponentCmd`와 **같은 함수**
  (`_canvas_cleanup_commands`)를 쓴다 — 참조 노드·전이·상태의 순서가 곧
  정확성이라 여기서 다시 짜면 언젠가 어긋난다.
"""
from __future__ import annotations

from typing import Any

#: 허용 용도 — WrappedSkillConfig.usage의 값 집합(""=미정은 전환의 출발점).
USAGES: tuple[str, ...] = ("state", "reference")


def placement_counts(project, project_vm, component) -> dict[str, int]:
    """이 컴포넌트가 지금 캔버스에서 차지한 것의 개수.

    states/transitions는 그래프 배치와 그에 닿는 전이, references는 참조 노드
    배치다. 전환 거부 메시지와 결과 보고가 같은 숫자를 말하도록 여기 하나로 센다.
    """
    from daedalus.model.fsm.state import SimpleState

    states = [
        s for s in project.graph.states
        if isinstance(s, SimpleState) and s.skill_ref is component
    ]
    state_ids = {id(s) for s in states}
    transitions = [
        t for t in project.graph.transitions
        if id(t.source) in state_ids or id(t.target) in state_ids
    ]
    name = getattr(component, "name", "")
    references = [
        rp for rp in (getattr(project, "reference_placements", None) or [])
        if rp.skill_name == name
    ]
    return {
        "states": len(states),
        "transitions": len(transitions),
        "references": len(references),
    }


def describe_placements(counts: dict[str, int]) -> str:
    """거부 메시지용 요약 — 0인 항목은 말하지 않는다."""
    parts = []
    if counts["states"]:
        parts.append(f"워크플로 노드 {counts['states']}개")
    if counts["transitions"]:
        parts.append(f"연결 전이 {counts['transitions']}개")
    if counts["references"]:
        parts.append(f"참조 노드 {counts['references']}개")
    return ", ".join(parts)


def change_wrapped_usage(
    window, component, new_usage: str, force: bool = False,
) -> dict[str, Any]:
    """랩핑 스킬의 용도를 바꾼다 — GUI 버튼과 MCP `set_wrapped_usage`의 실체.

    Returns: {"changed", "old", "new", "removed"} — removed는 force로 함께
    걷어낸 배치 개수(없으면 전부 0).
    Raises: ValueError — 대상이 랩핑 스킬이 아니거나, 알 수 없는 용도이거나,
    배치가 남아 있는데 force가 아닐 때.
    """
    from daedalus.model.plugin.skill import WrappedSkill
    from daedalus.view.commands.attr_commands import SetAttrCmd
    from daedalus.view.commands.base import Command, MacroCommand
    from daedalus.view.commands.component_commands import _canvas_cleanup_commands

    if not isinstance(component, WrappedSkill):
        raise ValueError(
            f"'{getattr(component, 'name', '?')}'은 랩핑 스킬이 아닙니다 — "
            "용도(state/reference)는 랩핑 스킬의 개념입니다."
        )
    if new_usage not in USAGES:
        raise ValueError(
            f"알 수 없는 용도 '{new_usage}'. 사용 가능: {', '.join(USAGES)}"
        )

    project = window._project
    project_vm = window._project_vm
    old = getattr(component.config, "usage", "") or ""
    if old == new_usage:
        return {"changed": False, "old": old, "new": new_usage,
                "removed": {"states": 0, "transitions": 0, "references": 0}}

    counts = placement_counts(project, project_vm, component)
    placed = any(counts.values())
    if placed and not force:
        raise ValueError(
            f"'{component.name}'은 이미 캔버스에 놓여 있습니다"
            f"({describe_placements(counts)}) — 용도를 바꾸려면 그 배치를 먼저 "
            f"지우거나, force로 함께 정리하세요(전이까지 사라집니다)."
        )

    children: list[Command] = []
    if placed:
        children.extend(_canvas_cleanup_commands(project, project_vm, component))
    children.append(SetAttrCmd(
        component.config, "usage", new_usage,
        label=f"'{component.name}' 용도 변경: {old or '미정'} → {new_usage}",
        script=f'set_wrapped_usage("{component.name}", "{new_usage}")',
    ))
    project_vm.execute(
        children[0] if len(children) == 1
        else MacroCommand(children, f"'{component.name}' 용도 변경 + 배치 정리")
    )
    return {
        "changed": True, "old": old, "new": new_usage,
        "removed": counts if placed else {"states": 0, "transitions": 0, "references": 0},
    }
