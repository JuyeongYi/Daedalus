# daedalus/view/actions/fork_skill.py
"""fork 스킬 — fork 에이전트 후보 + 절차형 ↔ 동기/비동기 fork 전환.

편집기 피커·캔버스 우클릭·MCP(`create_skill`/`set_component_field`/`convert_skill`)가
전부 이 함수들을 부른다 — 표면마다 후보나 전환 규칙이 다르면 안 된다.
"""
from __future__ import annotations

import copy
import dataclasses
from typing import Any

from daedalus.model.plugin.kinds import convert_family_kinds, spec_by_config_kind
from daedalus.model.plugin.skill import StepSkill

#: 전환할 수 있는 종류 — **전환 가족 선언에서 파생**한다(WP-3). 같은 가족의
#: 종류는 필드 레이아웃이 같아 컴포넌트 정체성을 유지한 채 `__class__`만 바꿀
#: 수 있다. 목록을 손으로 적어 두면 가족에 종류를 더할 때 여기를 빠뜨리고,
#: 빠뜨린 종류는 전환 메뉴에서 **조용히** 사라진다.
KINDS: tuple[str, ...] = convert_family_kinds(StepSkill.CONVERT_FAMILY)


def fork_agent_choices(project) -> list[tuple[str, str]]:
    """fork 스킬이 고를 수 있는 에이전트 [(값, 설명)] — 순서: 내장 → 외부 → 프로젝트.

    세 종류뿐이다(사용자 확정): 내장, 사용 선언한 외부 플러그인의 에이전트,
    프로젝트의 **fork 에이전트**. 워크플로 에이전트는 후보가 아니다 — 종류가
    다르다(예전에는 "배치되지 않은 워크플로 에이전트"였는데, 그 판정은 배치를
    지우면 조용히 겸직이 생겼다).
    """
    from daedalus.model.plugin.config import BUILTIN_FORK_AGENTS

    rows = [(name, "내장 에이전트") for name in BUILTIN_FORK_AGENTS]
    if project is None:
        return rows
    from daedalus.model.plugin.wrap_catalog import used_plugin_agents

    for agent in used_plugin_agents(project):
        note = "외부 플러그인 에이전트"
        if agent.description:
            note += f" — {agent.description}"
        rows.append((agent.agent_type, note))
    # fork 스킬의 실행 기반이 될 수 있는가 — 종류가 아니라 선언이 답한다
    # (WP-2d Q27: `IS_FORK_BASE`).
    for agent in sorted(project.agents, key=lambda a: a.name):
        if agent.IS_FORK_BASE:
            rows.append((agent.name, "프로젝트 fork 에이전트"))
    return rows


def validate_fork_agent(project, value: str) -> None:
    """고를 수 없는 값이면 이유와 선택지를 담아 ValueError."""
    values = [v for v, _ in fork_agent_choices(project)]
    if value in values:
        return
    if any(a.name == value for a in getattr(project, "agents", None) or []):
        raise ValueError(
            f"'{value}'은(는) 워크플로 에이전트라 fork 에이전트가 될 수 없습니다 — "
            f"워크플로 에이전트는 캔버스 노드이고 fork 에이전트는 fork 스킬의 실행 "
            f"기반입니다. fork 에이전트 종류로 새로 만들거나 다른 에이전트를 고르세요."
        )
    raise ValueError(
        f"'{value}'은(는) 고를 수 있는 에이전트가 아닙니다(정확 일치 — 대소문자 "
        f"포함). 사용 가능: {', '.join(values)}"
    )


def skill_kind_of(component) -> str | None:
    """전환 대상 종류 — 전환 가족에 속하지 않으면 None. `config.kind`가 단일 진실.

    "서로 전환 가능한가"는 컴포넌트가 `CONVERT_FAMILY`로 선언한다(WP-2d Q17) —
    클래스를 열거하면 같은 가족에 종류를 더할 때 여기를 빠뜨리고, 빠뜨리면
    전환 메뉴에서 조용히 사라진다.

    비교값은 **선언에서 읽는다** — 문자열을 베껴 두면 가족 이름을 바꿀 때
    여기만 남아 모든 단계 스킬이 "전환 불가"가 되고 메뉴가 조용히 사라진다.
    컴포넌트가 아닌 값(`None` — 빈 노드의 skill_ref 등)은 예외가 아니라
    "전환 대상이 아니다"로 답한다(`placement_role_of`와 같은 관용 계약).
    """
    if getattr(component, "CONVERT_FAMILY", None) != StepSkill.CONVERT_FAMILY:
        return None
    return component.config.kind if component.config.kind in KINDS else None


def convert_skill_kind(window, component, target: str) -> dict[str, Any]:
    """절차형 ↔ 동기 fork ↔ 비동기 fork 전환 — 1 undo.

    편집기 버튼·캔버스 메뉴·MCP `convert_skill`의 실체다. 이름·본문·설명·포트·
    전이·배치는 그대로다 — 객체를 새로 만들지 않고 클래스와 config만 바꾸므로
    그래프 참조·본문 문서·열린 탭이 끊기지 않는다.

    필드 복사는 **대상 config 클래스 기준**이다: `agent`는 ForkSkillConfig에만
    있으므로 부모(StepSkillConfig) 기준으로 복사하면 sync↔async 전환에서
    `agent`가 조용히 기본값으로 리셋된다(`dropped`에도 안 잡힌다).
    - procedural → fork: `allowed_tools` 드롭(fork에서 효과 없음)
    - fork → procedural: `agent` 드롭(대상에 없는 필드라 자연히 빠진다)
    - sync ↔ async: 드롭 없음(`agent` 보존)

    Returns: {"changed", "old", "new", "dropped"}.
    Raises: ValueError — 대상이 단계 스킬이 아니거나 알 수 없는 종류.
    """
    from daedalus.view.commands.attr_commands import SetAttrCmd
    from daedalus.view.commands.base import MacroCommand
    from daedalus.view.commands.surface_commands import resync_bracket

    current = skill_kind_of(component)
    if current is None:
        raise ValueError(
            f"'{getattr(component, 'name', '?')}'은(는) 절차형/fork 스킬이 아닙니다 — "
            f"전환은 {', '.join(KINDS)} 사이에서만 됩니다."
        )
    if target not in KINDS:
        raise ValueError(f"알 수 없는 종류 '{target}'. 사용 가능: {', '.join(KINDS)}")
    if current == target:
        return {"changed": False, "old": current, "new": target, "dropped": {}}

    # 클래스 이름을 문자열로 보관하고 런타임에 `getattr`로 푸는 옛 표(V11)는
    # 이름 오타가 AttributeError로만 드러났다 — 레지스트리가 **클래스 자체**를 준다.
    target_spec = spec_by_config_kind(target)
    new_cls = target_spec.component_cls
    new_cfg_cls = target_spec.config_cls

    old_cfg = component.config
    # 드롭은 **쌍**이 정한다: procedural → fork 전환에서만 allowed_tools가
    # 빠진다(fork는 서브에이전트가 도구를 정한다). sync ↔ async는 같은
    # 필드 레이아웃이라 드롭이 없다.
    drop = (
        {"allowed_tools"}
        if current == "procedural" and target != "procedural"
        else set()
    )
    common = {
        f.name: copy.deepcopy(getattr(old_cfg, f.name))
        for f in dataclasses.fields(new_cfg_cls)
        if hasattr(old_cfg, f.name) and f.name not in drop
    }
    new_cfg = new_cfg_cls(**common)

    dropped: dict[str, Any] = {}
    carried = {f.name for f in dataclasses.fields(new_cfg_cls)}
    for f in dataclasses.fields(old_cfg):
        if f.name in carried and f.name not in drop:
            continue
        value = getattr(old_cfg, f.name)
        if value:  # 빈 값은 잃을 것이 없다
            dropped[f.name] = list(value) if isinstance(value, list) else value

    name = component.name
    # 열려 있던 편집 탭의 프론트매터 폼과 레지스트리는 **다른 종류의 표**로
    # 그려진 스테일 위젯이다. 재동기를 액션에 두면 undo에는 걸리지 않으므로
    # (되돌려도 전환 후의 폼이 남는다) 매크로 안에 넣는다 — 전환도 undo도
    # 마지막에 확정된 상태를 다시 그린다.
    head, tail = resync_bracket(window, component)
    window._project_vm.execute(MacroCommand([
        head,
        SetAttrCmd(component, "config", new_cfg, label=f"'{name}' 설정 교체"),
        SetAttrCmd(component, "__class__", new_cls, label=f"'{name}' 종류 교체"),
        tail,
    ], f"'{name}' {current} → {target} 전환"))
    return {"changed": True, "old": current, "new": target, "dropped": dropped}
