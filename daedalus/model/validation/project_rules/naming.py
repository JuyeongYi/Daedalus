# daedalus/model/validation/project_rules/naming.py
"""이름·문자열 참조 규칙 (이동만 — 동작 불변).

duplicate_component_name / invalid_component_name / dangling_string_reference.
"""
from __future__ import annotations

import re

from daedalus.model.plugin.skill import is_disabled_wrapped
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
    def _check_wrapped_sources(project) -> list[ValidationError]:
        """랩핑 스킬 source 형식 검사 (WP-WR) — `plugin[@marketplace]:skill`.

        빈 값·형식 불일치는 경고다(wrapped_source_missing) — 편집 중일 수
        있다. 실존(카탈로그 해소) 검사는 파일시스템 소관이라 여기 없다.
        """
        errors: list[ValidationError] = []
        for skill in getattr(project, "skills", []):
            if getattr(skill, "kind", "") != "wrapped_skill":
                continue
            source = getattr(getattr(skill, "config", None), "source", "") or ""
            plugin_id, _, skill_name = source.partition(":")
            if not plugin_id.strip() or not skill_name.strip():
                errors.append(ValidationError(
                    rule="wrapped_source_missing",
                    message=(
                        f"랩핑 스킬 '{skill.name}'의 source가 비었거나 형식이 "
                        f"어긋납니다({source!r}) — `플러그인[@마켓]:스킬` 형식으로 "
                        f"지정하세요. 컴파일 산출의 인보크 지시가 생략됩니다."
                    ),
                    source=skill.name,
                    subject=skill,
                ))
        return errors

    @staticmethod
    def _check_wrapped_usage(project) -> list[ValidationError]:
        """랩핑 스킬 용도 고정 ↔ 배치 정합 (WP-WR, 사용자 확정 2026-09-07).

        용도는 최초 배치가 고정하고 한 스킬 두 용도는 금지다 — 배치 경로가
        구조로 막지만, MCP·구버전 파일 등 모델 직접 경로 대비 경고로 짚는다:
        reference 용도인데 그래프 상태 배치가 있거나, state(또는 미정)
        용도인데 참조 배치가 있으면 어긋남이다.
        """
        errors: list[ValidationError] = []
        ref_placed = {
            rp.skill_name
            for rp in getattr(project, "reference_placements", []) or []
        }
        state_placed = {
            id(getattr(s, "skill_ref", None))
            for s in getattr(project.graph, "states", [])
            if getattr(s, "skill_ref", None) is not None
        }
        for skill in getattr(project, "skills", []):
            if getattr(skill, "kind", "") != "wrapped_skill":
                continue
            usage = getattr(getattr(skill, "config", None), "usage", "") or ""
            as_state = id(skill) in state_placed
            as_ref = skill.name in ref_placed
            if usage == "reference" and as_state:
                errors.append(ValidationError(
                    rule="wrapped_usage_conflict",
                    message=(
                        f"랩핑 스킬 '{skill.name}'은 용도가 reference로 고정됐는데 "
                        f"그래프에 워크플로 단계로 배치돼 있습니다 — 참조 용도는 "
                        f"산출 파일이 없어 그 단계가 빈 참조가 됩니다."
                    ),
                    source=skill.name, subject=skill,
                ))
            elif usage != "reference" and as_ref:
                errors.append(ValidationError(
                    rule="wrapped_usage_conflict",
                    message=(
                        f"랩핑 스킬 '{skill.name}'은 용도가 "
                        f"{'state' if usage == 'state' else '미정'}인데 참조 노드로 "
                        f"배치돼 있습니다 — 한 랩핑 스킬은 한 용도만 가집니다"
                        f"(최초 배치가 고정)."
                    ),
                    source=skill.name, subject=skill,
                ))
            if is_disabled_wrapped(skill) and (as_state or as_ref):
                where = "워크플로 단계" if as_state else "참조 노드"
                errors.append(ValidationError(
                    rule="disabled_wrapped_placed",
                    message=(
                        f"랩핑 스킬 '{skill.name}'은 비활성인데 캔버스에 "
                        f"{where}로 배치돼 있습니다 — 산출에 나가지 않으므로 그 "
                        f"자리는 빈 단계가 됩니다. 다시 활성화하거나 배치를 "
                        f"걷어내세요(랩핑 스킬은 삭제할 수 없습니다)."
                    ),
                    source=skill.name, subject=skill,
                ))
        return errors

    @staticmethod
    def _check_external_plugins(project) -> list[ValidationError]:
        """외부 플러그인 사용 선언 ↔ 랩핑 참조 정합 (WP-WR, 사용자 확정).

        배선(dependencies/enabledPlugins)의 단일 진실은
        ``project.external_plugins`` 선언이다 — 그래서 어긋남은 두 방향 다
        경고다: ① 선언했는데 어떤 랩핑 스킬도 그 플러그인을 참조하지 않음
        (unused_external_plugin — 쓰기로 해놓고 안 쓴 경우), ② 랩핑 스킬이
        미선언 플러그인을 가리킴(undeclared_external_plugin — 선언이 없으면
        빌드 배선이 나가지 않아 런타임에 그 스킬을 찾지 못한다).

        매칭은 설치 식별자 정확 일치다(``alpha@mkt`` ≠ ``alpha`` — 마켓이
        다르면 다른 설치 대상이다). 형식이 깨진 source는
        wrapped_source_missing이 이미 짚으므로 여기서 중복 경고하지 않는다.
        """
        declared = {
            str(p).strip()
            for p in getattr(project, "external_plugins", None) or []
            if str(p).strip()
        }
        referenced: set[str] = set()
        errors: list[ValidationError] = []
        for skill in getattr(project, "skills", []):
            if getattr(skill, "kind", "") != "wrapped_skill":
                continue
            # 비활성 랩퍼는 참조로 치지 않는다 — 산출에 안 나가므로 배선이
            # 필요 없고(undeclared 대상 아님), 그 플러그인을 쓰는 것도 아니다
            # (unused는 사실 그대로다). WP-WR 삭제 대신 비활성화.
            if is_disabled_wrapped(skill):
                continue
            source = getattr(getattr(skill, "config", None), "source", "") or ""
            plugin_id, _, skill_name = source.partition(":")
            plugin_id = plugin_id.strip()
            if not plugin_id or not skill_name.strip():
                continue  # wrapped_source_missing 소관
            referenced.add(plugin_id)
            if plugin_id not in declared:
                errors.append(ValidationError(
                    rule="undeclared_external_plugin",
                    message=(
                        f"랩핑 스킬 '{skill.name}'이 사용 선언되지 않은 플러그인 "
                        f"'{plugin_id}'를 가리킵니다 — external_plugins에 없으면 "
                        f"빌드가 dependencies/enabledPlugins를 배선하지 않아 "
                        f"런타임에 그 스킬을 찾지 못합니다. 카탈로그 창에서 "
                        f"플러그인을 체크하거나 set_external_plugins로 선언하세요."
                    ),
                    source=skill.name,
                    subject=skill,
                ))
        for plugin_id in sorted(declared - referenced):
            errors.append(ValidationError(
                rule="unused_external_plugin",
                message=(
                    f"외부 플러그인 '{plugin_id}'를 사용하기로 선언했지만 어떤 "
                    f"랩핑 스킬도 참조하지 않습니다 — 빌드 배선(dependencies/"
                    f"enabledPlugins)은 그대로 나갑니다. 워크플로 단계로 쓰지 "
                    f"않는 의도적 활성화면 무시해도 됩니다."
                ),
                source=plugin_id,
                subject=project,
            ))
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
