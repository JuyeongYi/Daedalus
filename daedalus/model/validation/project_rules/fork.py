# daedalus/model/validation/project_rules/fork.py
"""fork 스킬의 몸 에이전트 규칙 (사용자 확정 2026-09-13).

CC는 fork 스킬의 `agent`를 정확 일치로 찾고, 없으면 **조용히 general-purpose로
실행한다**(실측, CC 2.1.268). 그래서 몸을 못 찾는 경우는 경고가 아니라 에러다.

외부 플러그인 에이전트가 실제로 그 플러그인에 있는지는 보지 않는다 — 카탈로그는
파일시스템이고 검증기는 파일시스템을 읽지 않는다. 사용 선언 여부까지만 판정한다.
"""
from __future__ import annotations

from daedalus.model.validation.severity import ValidationError


def fork_body_agent(skill, project):
    """fork 스킬이 몸으로 쓰는 **프로젝트** 에이전트 (내장·외부·없음이면 None)."""
    name = getattr(skill.config, "agent", "")
    return next((a for a in project.agents if a.name == name), None)


class _ForkRules:
    """fork 스킬 규칙 모음 (_ProjectRules 믹스인)."""

    @staticmethod
    def _check_fork_agents(project) -> list[ValidationError]:
        """fork_agent_placed / fork_agent_missing / fork_agent_undeclared_plugin (에러),
        fork_model_overrides_agent / fork_agent_isolation_ignored (경고)."""
        from daedalus.model.plugin.config import BUILTIN_FORK_AGENTS
        from daedalus.model.plugin.enums import AgentIsolation, ModelType
        from daedalus.model.plugin.skill import ForkSkill

        placed_ids = {
            id(getattr(s, "skill_ref", None))
            for s in getattr(getattr(project, "graph", None), "states", None) or []
        }
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
            body = fork_body_agent(skill, project)
            if body is None:
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

            if id(body) in placed_ids:
                add(skill, rule="fork_agent_placed", message=(
                    f"fork 스킬 '{skill.name}'의 몸 에이전트 '{body.name}'이(가) 캔버스에 "
                    f"배치돼 있습니다 — 워크플로 단계와 fork 몸을 겸하면 캔버스에 보이지 "
                    f"않는 연결이 생깁니다. 배치를 지우거나 다른 에이전트를 고르세요."
                ))
            skill_cfg, body_cfg = skill.config, body.config
            model_clash = (
                skill_cfg.model is not ModelType.INHERIT
                and body_cfg.model is not ModelType.INHERIT
                and skill_cfg.model != body_cfg.model
            )
            effort_clash = (
                skill_cfg.effort is not None
                and body_cfg.effort is not None
                and skill_cfg.effort != body_cfg.effort
            )
            if model_clash or effort_clash:
                which = " / ".join(
                    w for w, on in (("model", model_clash), ("effort", effort_clash)) if on
                )
                add(skill, rule="fork_model_overrides_agent", message=(
                    f"fork 스킬 '{skill.name}'과 몸 에이전트 '{body.name}'의 {which}가 "
                    f"다릅니다 — fork에서는 스킬 값이 이기고 에이전트 값은 무시됩니다. "
                    f"에이전트 값을 쓰려면 스킬 쪽을 비우세요."
                ))
            if body_cfg.isolation is not AgentIsolation.NONE:
                add(skill, rule="fork_agent_isolation_ignored", message=(
                    f"fork 스킬 '{skill.name}'의 몸 에이전트 '{body.name}'에 isolation"
                    f"({body_cfg.isolation.value})이 있지만 fork 실행에는 적용되지 않습니다."
                ))
        return errors
