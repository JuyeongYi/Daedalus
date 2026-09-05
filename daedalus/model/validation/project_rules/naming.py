# daedalus/model/validation/project_rules/naming.py
"""이름·문자열 참조 규칙 (이동만 — 동작 불변).

duplicate_component_name / invalid_component_name / dangling_string_reference.
"""
from __future__ import annotations

import re

from daedalus.model.validation.severity import ValidationError

COMPONENT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class _NamingRules:
    """이름 규약·문자열 참조 규칙 모음 (_ProjectRules 믹스인)."""

    _COMPONENT_NAME_RE = COMPONENT_NAME_RE

    @staticmethod
    def _check_duplicate_component_name(project) -> list[ValidationError]:
        """duplicate_component_name — skills/agents 전체에서 동명 컴포넌트 에러."""
        seen: dict[str, object] = {}
        errors: list[ValidationError] = []
        all_components = [
            *project.skills,
            *project.agents,
        ]
        for comp in all_components:
            name = getattr(comp, "name", None)
            if name is None:
                continue
            if name in seen:
                errors.append(ValidationError(
                    rule="duplicate_component_name",
                    message=(
                        f"프로젝트에 이름 '{name}'이 중복됩니다. "
                        f"컴파일 시 디렉토리/파일명 충돌이 발생합니다."
                    ),
                    source=name,
                    subject=comp,
                ))
            else:
                seen[name] = comp
        return errors

    @staticmethod
    def _check_invalid_component_name(project) -> list[ValidationError]:
        """invalid_component_name — 이름이 ^[a-z0-9][a-z0-9-]*$ 불일치 시 경고. 빈 이름은 에러."""
        all_components = [
            *project.skills,
            *project.agents,
        ]
        errors: list[ValidationError] = []
        for comp in all_components:
            name = getattr(comp, "name", None)
            if name is None:
                continue
            if name == "":
                errors.append(ValidationError(
                    rule="invalid_component_name",
                    message="컴포넌트 이름이 비어 있습니다.",
                    source="",
                    subject=comp,
                ))
            elif not COMPONENT_NAME_RE.match(name):
                errors.append(ValidationError(
                    rule="invalid_component_name",
                    message=(
                        f"컴포넌트 이름 '{name}'이 명명 규약 "
                        f"'^[a-z0-9][a-z0-9-]*$'에 맞지 않습니다."
                    ),
                    source=name,
                    subject=comp,
                ))
        return errors

    @staticmethod
    def _check_invalid_project_name(project) -> list[ValidationError]:
        """invalid_component_name — 프로젝트 이름도 컴포넌트와 동일 규약 적용.

        프로젝트 이름은 plugin.json의 name(플러그인 식별자)이 되므로 컴포넌트
        이름과 같은 등급(빈 이름=에러, 규약 불일치=경고)으로 검사한다.
        다른 프로젝트 수준 규칙(duplicate_component_name 등)에는 프로젝트 이름을
        끌어들이지 않는다 — 이름 규약 검사만.
        """
        name = getattr(project, "name", None)
        if name is None:
            return []
        if name == "":
            return [ValidationError(
                rule="invalid_component_name",
                message="프로젝트 이름이 비어 있습니다.",
                source="",
                subject=project,
                path=("project",),
            )]
        if not COMPONENT_NAME_RE.match(name):
            return [ValidationError(
                rule="invalid_component_name",
                message=(
                    f"프로젝트 이름 '{name}'이 명명 규약 "
                    f"'^[a-z0-9][a-z0-9-]*$'에 맞지 않습니다."
                ),
                source=name,
                subject=project,
                path=("project",),
            )]
        return []

    @staticmethod
    def _check_dangling_string_references(project) -> list[ValidationError]:
        """dangling_string_reference — ProceduralSkillConfig.agent / AgentConfig.skills /
        reference_placements.skill_name의 문자열 참조 실존 검사."""
        from daedalus.model.plugin.config import ProceduralSkillConfig, AgentConfig
        from daedalus.model.plugin.skill import ProceduralSkill

        errors: list[ValidationError] = []

        # 전역 이름 맵
        global_skill_names = {s.name for s in project.skills}
        global_agent_names = {a.name for a in project.agents}

        # ProceduralSkillConfig.agent 검사
        for skill in project.skills:
            if not isinstance(skill, ProceduralSkill):
                continue
            cfg = skill.config
            if isinstance(cfg, ProceduralSkillConfig) and cfg.agent:
                if cfg.agent not in global_agent_names:
                    errors.append(ValidationError(
                        rule="dangling_string_reference",
                        message=(
                            f"스킬 '{skill.name}'의 config.agent '{cfg.agent}'가 "
                            f"프로젝트 agents에 없습니다."
                        ),
                        source=skill.name,
                        subject=skill,
                    ))

        # AgentConfig.skills 검사 (전역 스킬 이름)
        for agent in project.agents:
            cfg = agent.config
            if not isinstance(cfg, AgentConfig):
                continue
            for skill_name in cfg.skills:
                if skill_name not in global_skill_names:
                    errors.append(ValidationError(
                        rule="dangling_string_reference",
                        message=(
                            f"에이전트 '{agent.name}'의 config.skills '{skill_name}'이 "
                            f"프로젝트 skills에 없습니다."
                        ),
                        source=agent.name,
                        subject=agent,
                    ))

        # reference_placements.skill_name 검사
        for placement in project.reference_placements:
            if placement.skill_name not in global_skill_names:
                errors.append(ValidationError(
                    rule="dangling_string_reference",
                    message=(
                        f"reference_placement의 skill_name '{placement.skill_name}'이 "
                        f"프로젝트 skills에 없습니다."
                    ),
                    source=placement.skill_name,
                    subject=placement,
                ))

        return errors
