# daedalus/model/validation/project_rules/fork.py
"""fork 스킬이 쓰는 에이전트 규칙 (사용자 확정 2026-09-13).

CC는 fork 스킬의 `agent`를 정확 일치로 찾고, 없으면 **조용히 general-purpose로
실행한다**(실측, CC 2.1.268). 그래서 fork 에이전트를 못 찾는 경우는 경고가 아니라 에러다.

fork 에이전트는 별도 종류다(WP-FK2) — 워크플로 에이전트를 fork 에이전트로
지목하면 에러(`fork_agent_wrong_kind`)이고, 아무도 부르지 않는 fork 에이전트는
경고(`unused_fork_agent`)다.

**다른 플러그인의 에이전트도 먼저 컴포넌트로 등록한다**(WP-EX, 사용자 확정
2026-09-19). 그래서 여기에는 `플러그인:이름` 문자열을 따로 보는 분기가 없다 —
등록되지 않은 이름은 등록된 자체 fork 에이전트와 **똑같이** `fork_agent_missing`
이고, 등록된 것의 사용 선언 누락은 `ExternalForkAgent.external_plugin_refs()`를
통해 `undeclared_external_plugin`(경고)이 짚는다. 종전 `fork_agent_undeclared_plugin`
(에러)은 같은 사실을 두 등급으로 말하던 비대칭이라 함께 사라졌다.

외부 플러그인 에이전트가 실제로 그 플러그인에 있는지는 보지 않는다 — 카탈로그는
파일시스템이고 검증기는 파일시스템을 읽지 않는다.
"""
from __future__ import annotations

from daedalus.model.validation.severity import ValidationError


def fork_project_agent(skill, project):
    """fork 스킬이 fork 에이전트로 쓰는 **프로젝트** 에이전트 (내장·외부·없음이면 None).

    "이 스킬이 본문을 누구에게 맡기는가"는 컴포넌트가 답한다
    (`delegated_agent_name()` — Q33). 내장 이름(`general-purpose`)·외부
    플러그인 이름(`플러그인:이름`)은 프로젝트 목록에 없으므로 None이 되고,
    그 경우의 등급은 `_check_fork_agents`가 가른다.
    """
    name = skill.delegated_agent_name() or ""
    return next((a for a in project.agents if a.name == name), None)


class _ForkRules:
    """fork 스킬 규칙 모음 (_ProjectRules 믹스인)."""

    @staticmethod
    def _check_fork_agents(project) -> list[ValidationError]:
        """fork_agent_wrong_kind / fork_agent_missing (에러),
        fork_model_overrides_agent (경고)."""
        from daedalus.model.plugin.config import BUILTIN_FORK_AGENTS
        from daedalus.model.plugin.enums import ModelType

        errors: list[ValidationError] = []

        # rule은 반드시 키워드 리터럴로 넘긴다 — 등급 분류 테스트가 소스의
        # `rule="…"`을 긁어 누락을 잡는다.
        def add(skill, *, rule: str, message: str) -> None:
            errors.append(ValidationError(
                rule=rule, message=message, source=skill.name, subject=skill,
            ))

        for skill in project.skills:
            # fork 스킬 = 서브에이전트에서 도는 스킬 — 스킬 종류 중 이 선언을
            # 갖는 것은 fork 2종뿐이다(종전 `isinstance(ForkSkill)`과 같은 집합).
            if not type(skill).RUNS_IN_SUBAGENT:
                continue
            name = skill.delegated_agent_name() or ""
            target = fork_project_agent(skill, project)
            if target is None:
                if name in BUILTIN_FORK_AGENTS:
                    continue
                add(skill, rule="fork_agent_missing", message=(
                    f"fork 스킬 '{skill.name}'의 에이전트 '{name}'이(가) 없습니다 — "
                    f"CC는 못 찾은 에이전트를 조용히 general-purpose로 실행합니다. "
                    f"내장({', '.join(BUILTIN_FORK_AGENTS)})이나 프로젝트에 등록한 "
                    f"fork 에이전트(자체 fork 에이전트 · 등록한 외부 fork 에이전트) "
                    f"중에서 고르세요."
                ))
                continue

            # fork 실행 기반이 될 수 있는 종류인가 (Q27 — `IS_FORK_BASE`).
            # 워크플로 에이전트는 선언하지 않으므로 여기 걸린다.
            if not type(target).IS_FORK_BASE:
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
        from daedalus.model.plugin.placement import fork_skills_using

        errors: list[ValidationError] = []
        for agent in getattr(project, "agents", None) or []:
            if not type(agent).IS_FORK_BASE:  # Q27 — 워크플로 에이전트는 대상 아님
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

    @staticmethod
    def _check_fork_blackboard_tools_reachable(project) -> list[ValidationError]:
        """bb_tools_unreachable (경고) — 블랙보드를 쓰는 fork 스킬의 기반이
        **산출 파일이 없는** 에이전트(등록된 외부 fork 에이전트)일 때 (WP-BM).

        블랙보드 도구 권한은 프론트매터가 부여하는데, fork 스킬의 SKILL.md는 그
        서브에이전트의 도구를 늘리지 못한다 — 권한을 실을 수 있는 유일한 파일은
        **fork 에이전트의 .md**다. 그 정본이 남의 플러그인에 있으면 우리가 쓸
        파일이 없다.

        조용히 넘기면 그 fork는 런타임에 블랙보드 도구를 못 보고, 캔버스의
        📖/✏ 선언은 아무 효과도 내지 않는다(원칙 5). 다만 그 에이전트의
        `tools`가 비어 있으면(= 전부 상속) 실제로는 보일 수도 있어 **경고**다.
        """
        from daedalus.model.plugin.roles import OutputLocation

        errors: list[ValidationError] = []
        agents = {a.name: a for a in getattr(project, "agents", None) or []}
        for skill in getattr(project, "skills", None) or []:
            if not type(skill).RUNS_IN_SUBAGENT:
                continue
            if not _declares_blackboard_access(skill, project):
                continue
            base = agents.get(skill.delegated_agent_name() or "")
            if base is None or type(base).OUTPUT_LOCATION is not OutputLocation.NONE:
                continue
            errors.append(ValidationError(
                rule="bb_tools_unreachable",
                message=(
                    f"fork 스킬 '{skill.name}'은 블랙보드를 읽거나 쓰지만, 실행 "
                    f"기반 '{base.name}'은 정본이 다른 플러그인에 있어 산출 파일이 "
                    f"없습니다 — 블랙보드 도구 권한을 실을 자리가 없습니다. 그 "
                    f"에이전트의 도구 목록이 비어 있지 않으면 이 fork는 런타임에 "
                    f"블랙보드 도구를 보지 못합니다. 자체 fork 에이전트를 기반으로 "
                    f"쓰거나, 이 단계의 블랙보드 접근 선언을 지우세요."
                ),
                source=skill.name,
                subject=skill,
            ))
        return errors


def _declares_blackboard_access(skill, project) -> bool:
    """이 스킬이 블랙보드를 읽거나 쓰는가 — 자체 FSM + 그래프 배치의 선언 합집합.

    컴파일러의 `emit/sections._component_access_union`과 **같은 질문**이다.
    검증기는 컴파일러를 임포트할 수 없어(경계 계약) 여기에 모델 표현을 둔다 —
    두 곳이 보는 대상(상태의 `reads`/`writes`)은 같은 필드다.
    """
    from daedalus.model.fsm.walk import iter_states

    def _has(state) -> bool:
        return bool(getattr(state, "reads", None) or getattr(state, "writes", None))

    for sm in skill.state_machines():
        if any(_has(state) for state in iter_states(sm)):
            return True
    graph = getattr(project, "graph", None)
    if graph is None:
        return False
    return any(
        getattr(node, "skill_ref", None) is skill and _has(node)
        for node in getattr(graph, "states", None) or []
    )
