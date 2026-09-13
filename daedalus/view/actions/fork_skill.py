# daedalus/view/actions/fork_skill.py
"""fork 스킬 — 몸 에이전트 후보 + 절차형 ↔ fork 전환 (사용자 확정 2026-09-13).

편집기 피커·캔버스 우클릭·MCP(`create_skill`/`set_component_field`/`convert_skill`)가
전부 이 함수들을 부른다 — 표면마다 후보나 전환 규칙이 다르면 안 된다.
"""
from __future__ import annotations

import copy
import dataclasses
from typing import Any

#: 전환할 수 있는 종류 — 두 종류는 필드 집합이 같아(fork는 절차형의 하위 클래스)
#: 컴포넌트 정체성을 유지한 채 바꿀 수 있다.
KINDS: tuple[str, ...] = ("procedural", "fork")


def fork_agent_choices(project) -> list[tuple[str, str]]:
    """fork 스킬이 고를 수 있는 에이전트 [(값, 설명)] — 순서: 내장 → 외부 → 프로젝트.

    세 종류뿐이다(사용자 확정): 내장, 사용 선언한 외부 플러그인의 에이전트,
    **캔버스에 배치되지 않은** 프로젝트 에이전트. 배치된 에이전트는 워크플로
    단계라 몸을 겸하면 캔버스에 안 보이는 연결이 생기므로 넣지 않는다.
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
    placed = {
        id(getattr(s, "skill_ref", None))
        for s in getattr(project.graph, "states", None) or []
    }
    for agent in sorted(project.agents, key=lambda a: a.name):
        if id(agent) not in placed:
            rows.append((agent.name, "프로젝트 에이전트 (캔버스 미배치)"))
    return rows


def validate_fork_agent(project, value: str) -> None:
    """고를 수 없는 값이면 이유와 선택지를 담아 ValueError."""
    values = [v for v, _ in fork_agent_choices(project)]
    if value in values:
        return
    if any(a.name == value for a in getattr(project, "agents", None) or []):
        raise ValueError(
            f"프로젝트 에이전트 '{value}'는 캔버스에 배치돼 있어 fork 몸으로 쓸 수 "
            f"없습니다 — 워크플로 단계와 몸을 겸하면 보이지 않는 연결이 생깁니다. "
            f"배치를 지우거나 다른 에이전트를 고르세요."
        )
    raise ValueError(
        f"'{value}'은(는) 고를 수 있는 에이전트가 아닙니다(정확 일치 — 대소문자 "
        f"포함). 사용 가능: {', '.join(values)}"
    )


def skill_kind_of(component) -> str | None:
    """전환 대상 종류 — 절차형/fork가 아니면 None."""
    from daedalus.model.plugin.skill import ForkSkill, ProceduralSkill

    if isinstance(component, ForkSkill):
        return "fork"
    if isinstance(component, ProceduralSkill):
        return "procedural"
    return None


def convert_skill_kind(window, component, target: str) -> dict[str, Any]:
    """절차형 ↔ fork 전환 — 1 undo. 편집기 버튼·캔버스 메뉴·MCP `convert_skill`의 실체.

    이름·본문·설명·포트·전이·배치는 그대로다 — 객체를 새로 만들지 않고 클래스와
    config만 바꾸므로 그래프 참조·본문 문서·열린 탭이 끊기지 않는다. fork로 갈 때
    `allowed_tools`(fork에서 효과 없음)를, 절차형으로 갈 때 `agent`를 버리고
    `dropped`로 보고한다.

    Returns: {"changed", "old", "new", "dropped"}.
    Raises: ValueError — 대상이 절차형/fork가 아니거나 알 수 없는 종류.
    """
    from daedalus.model.plugin.config import ForkSkillConfig, ProceduralSkillConfig
    from daedalus.model.plugin.skill import ForkSkill, ProceduralSkill
    from daedalus.view.commands.attr_commands import SetAttrCmd
    from daedalus.view.commands.base import MacroCommand

    current = skill_kind_of(component)
    if current is None:
        raise ValueError(
            f"'{getattr(component, 'name', '?')}'은(는) 절차형/fork 스킬이 아닙니다 — "
            f"전환은 두 종류 사이에서만 됩니다."
        )
    if target not in KINDS:
        raise ValueError(f"알 수 없는 종류 '{target}'. 사용 가능: {', '.join(KINDS)}")
    if current == target:
        return {"changed": False, "old": current, "new": target, "dropped": {}}

    old_cfg = component.config
    common = {
        f.name: copy.deepcopy(getattr(old_cfg, f.name))
        for f in dataclasses.fields(ProceduralSkillConfig)
        if f.name != "allowed_tools"
    }
    dropped: dict[str, Any] = {}
    if target == "fork":
        new_cls, new_cfg = ForkSkill, ForkSkillConfig(**common)
        if old_cfg.allowed_tools:
            dropped["allowed_tools"] = list(old_cfg.allowed_tools)
    else:
        new_cls, new_cfg = ProceduralSkill, ProceduralSkillConfig(**common)
        dropped["agent"] = old_cfg.agent

    name = component.name
    window._project_vm.execute(MacroCommand([
        SetAttrCmd(component, "config", new_cfg, label=f"'{name}' 설정 교체"),
        SetAttrCmd(component, "__class__", new_cls, label=f"'{name}' 종류 교체"),
    ], f"'{name}' {current} → {target} 전환"))
    panel = getattr(window, "_registry_panel", None)
    if panel is not None and getattr(window, "_project", None) is not None:
        panel.set_project(window._project)
    return {"changed": True, "old": current, "new": target, "dropped": dropped}
