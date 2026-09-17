# daedalus/model/validation/project_rules/fork.py
"""fork 스킬이 쓰는 에이전트 규칙 (사용자 확정 2026-09-13).

CC는 fork 스킬의 `agent`를 정확 일치로 찾고, 없으면 **조용히 general-purpose로
실행한다**(실측, CC 2.1.268). 그래서 fork 에이전트를 못 찾는 경우는 경고가 아니라 에러다.

fork 에이전트는 별도 종류다(WP-FK2) — 워크플로 에이전트를 fork 에이전트로
지목하면 에러(`fork_agent_wrong_kind`)이고, 아무도 부르지 않는 fork 에이전트는
경고(`unused_fork_agent`)다.

외부 플러그인 에이전트가 실제로 그 플러그인에 있는지는 보지 않는다 — 카탈로그는
파일시스템이고 검증기는 파일시스템을 읽지 않는다. 사용 선언 여부까지만 판정한다.
"""
from __future__ import annotations

from daedalus.model.validation.severity import ValidationError


def fork_project_agent(skill, project):
    """fork 스킬이 fork 에이전트로 쓰는 **프로젝트** 에이전트 (내장·외부·없음이면 None)."""
    name = getattr(skill.config, "agent", "")
    return next((a for a in project.agents if a.name == name), None)


class _ForkRules:
    """fork 스킬 규칙 모음 (_ProjectRules 믹스인)."""

    @staticmethod
    def _check_fork_agents(project) -> list[ValidationError]:
        """fork_agent_wrong_kind / fork_agent_missing / fork_agent_undeclared_plugin (에러),
        fork_model_overrides_agent (경고)."""
        from daedalus.model.plugin.agent import AgentDefinition
        from daedalus.model.plugin.config import BUILTIN_FORK_AGENTS
        from daedalus.model.plugin.enums import ModelType
        from daedalus.model.plugin.skill import ForkSkill

        declared = {
            p.partition("@")[0] for p in getattr(project, "external_plugins", None) or []
        }
        errors: list[ValidationError] = []

        # rule은 반드시 키워드 리터럴로 넘긴다 — 등급 분류 테스트가 소스의
        # `rule="…"`을 긁어 누락을 잡는다.
        def add(skill, *, rule: str, message: str) -> None:
            errors.append(ValidationError(
                rule=rule, message=message, source=skill.name, subject=skill,
            ))

        for skill in project.skills:
            if not isinstance(skill, ForkSkill):
                continue
            name = skill.config.agent
            target = fork_project_agent(skill, project)
            if target is None:
                if name in BUILTIN_FORK_AGENTS:
                    continue
                plugin, sep, _agent = name.partition(":")
                if not sep:
                    add(skill, rule="fork_agent_missing", message=(
                        f"fork 스킬 '{skill.name}'의 에이전트 '{name}'이(가) 없습니다 — "
                        f"CC는 못 찾은 에이전트를 조용히 general-purpose로 실행합니다. "
                        f"내장({', '.join(BUILTIN_FORK_AGENTS)}), 사용 선언한 외부 "
                        f"플러그인 에이전트(플러그인:이름), 프로젝트 에이전트 중에서 고르세요."
                    ))
                elif plugin not in declared:
                    add(skill, rule="fork_agent_undeclared_plugin", message=(
                        f"fork 스킬 '{skill.name}'의 에이전트 '{name}'은(는) 사용 선언하지 "
                        f"않은 플러그인 '{plugin}'의 것입니다 — 플러그인이 켜지지 않으면 "
                        f"조용히 general-purpose로 실행됩니다. 외부 플러그인 목록에 선언하세요."
                    ))
                continue

            if isinstance(target, AgentDefinition):
                add(skill, rule="fork_agent_wrong_kind", message=(
                    f"fork 스킬 '{skill.name}'의 에이전트 '{target.name}'은(는) 워크플로 "
                    f"에이전트입니다 — 워크플로 에이전트는 fork 에이전트가 될 수 없습니다. "
                    f"fork 에이전트 종류로 만들거나 다른 에이전트를 고르세요."
                ))
            skill_cfg, target_cfg = skill.config, target.config
            model_clash = (
                skill_cfg.model is not ModelType.INHERIT
                and target_cfg.model is not ModelType.INHERIT
                and skill_cfg.model != target_cfg.model
            )
            effort_clash = (
                skill_cfg.effort is not None
                and target_cfg.effort is not None
                and skill_cfg.effort != target_cfg.effort
            )
            if model_clash or effort_clash:
                which = " / ".join(
                    w for w, on in (("model", model_clash), ("effort", effort_clash)) if on
                )
                add(skill, rule="fork_model_overrides_agent", message=(
                    f"fork 스킬 '{skill.name}'과 fork 에이전트 '{target.name}'의 {which}가 "
                    f"다릅니다 — fork에서는 스킬 값이 이기고 에이전트 값은 무시됩니다. "
                    f"에이전트 값을 쓰려면 스킬 쪽을 비우세요."
                ))
        return errors

    @staticmethod
    def _check_unused_fork_agents(project) -> list[ValidationError]:
        """unused_fork_agent (경고) — 어떤 fork 스킬도 부르지 않는 fork 에이전트.

        산출은 되지만(agents/<이름>.md) 아무도 실행하지 않는다 — 조용히 아무 일도
        일어나지 않는 상태라 알린다(원칙 5). 워크플로 에이전트는 대상이 아니다
        (캔버스 노드로 불린다).
        """
        from daedalus.model.plugin.agent import ForkAgent
        from daedalus.model.plugin.placement import fork_skills_using

        errors: list[ValidationError] = []
        for agent in getattr(project, "agents", None) or []:
            if not isinstance(agent, ForkAgent):
                continue
            if fork_skills_using(agent, project):
                continue
            errors.append(ValidationError(
                rule="unused_fork_agent",
                message=(
                    f"fork 에이전트 '{agent.name}'을(를) 부르는 fork 스킬이 없습니다 — "
                    f"산출은 되지만 아무도 실행하지 않습니다. fork 스킬의 에이전트로 "
                    f"고르거나 지우세요."
                ),
                source=agent.name,
                subject=agent,
                path=(f"agent:{agent.name}",),
            ))
        return errors
