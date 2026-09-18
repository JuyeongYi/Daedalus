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
    def _check_external_sources(project) -> list[ValidationError]:
        """외부 정본 참조의 형식 검사 (WP-WR, 일반화 WP-2b) — `plugin[@marketplace]:name`.

        대상은 "본문·정의의 정본이 외부에 있다"고 **스스로 말하는** 컴포넌트
        전부다(`external_source is not None` — Q34). 종류를 묻지 않으므로
        외부 정본을 갖는 새 종류는 선언 한 줄로 이 검사를 받는다.

        빈 값·형식 불일치는 경고다(`external_source_missing`) — 편집 중일 수
        있다. 실존(카탈로그 해소) 검사는 파일시스템 소관이라 여기 없다.
        """
        errors: list[ValidationError] = []
        for comp in [*getattr(project, "skills", []), *getattr(project, "agents", [])]:
            source = comp.external_source
            if source is None:
                continue
            plugin_id, _, ref_name = source.partition(":")
            if not plugin_id.strip() or not ref_name.strip():
                errors.append(ValidationError(
                    rule="external_source_missing",
                    message=(
                        f"'{comp.name}'의 source가 비었거나 형식이 "
                        f"어긋납니다({source!r}) — `플러그인[@마켓]:이름` 형식으로 "
                        f"지정하세요. 컴파일 산출의 인보크 지시가 생략됩니다."
                    ),
                    source=comp.name,
                    subject=comp,
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
        from daedalus.model.plugin.roles import BodySource, PlacementRole

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
            # 용도 스위치를 가진 종류는 오늘 랩핑 스킬 하나뿐이다 — 능력 선언에
            # 그 사실을 표현하는 칸이 없어 본문 정본으로 좁힌다.
            if type(skill).BODY_SOURCE is not BodySource.EXTERNAL:  # WRAPPED-ONLY
                continue
            as_state = id(skill) in state_placed
            as_ref = skill.name in ref_placed
            as_reference_usage = skill.effective_placement() is PlacementRole.REFERENCE
            if as_reference_usage and as_state:
                errors.append(ValidationError(
                    rule="wrapped_usage_conflict",
                    message=(
                        f"랩핑 스킬 '{skill.name}'은 용도가 reference로 고정됐는데 "
                        f"그래프에 워크플로 단계로 배치돼 있습니다 — 참조 용도는 "
                        f"산출 파일이 없어 그 단계가 빈 참조가 됩니다."
                    ),
                    source=skill.name, subject=skill,
                ))
            elif not as_reference_usage and as_ref:
                usage = skill.config.usage or ""  # WRAPPED-ONLY (문구 전용)
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
            if not skill.is_active() and (as_state or as_ref):
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
        """외부 플러그인 사용 선언 ↔ 컴포넌트 참조 정합 (WP-WR, 사용자 확정).

        배선(dependencies/enabledPlugins)의 단일 진실은
        ``project.external_plugins`` 선언이다 — 그래서 어긋남은 두 방향 다
        경고다: ① 선언했는데 어떤 컴포넌트도 그 플러그인을 참조하지 않음
        (unused_external_plugin — 쓰기로 해놓고 안 쓴 경우), ② 컴포넌트가
        미선언 플러그인을 가리킴(undeclared_external_plugin — 선언이 없으면
        빌드 배선이 나가지 않아 런타임에 그것을 찾지 못한다).

        **종류를 묻지 않는다**(WP-2b): "내가 배선을 요구하는 플러그인 설치
        id는 무엇인가"는 컴포넌트가 답한다(`external_plugin_refs()` — Q15).
        그 안에 두 가지 제외가 이미 들어 있다 — 꺼 둔 컴포넌트는 참조로 치지
        않고(산출에 안 나가므로 배선이 필요 없고 쓰는 것도 아니다), 형식이
        깨진 source는 `external_source_missing` 소관이라 빈 목록을 답한다.

        매칭은 설치 식별자 정확 일치다(``alpha@mkt`` != ``alpha`` — 마켓이
        다르면 다른 설치 대상이다).
        """
        declared = {
            str(p).strip()
            for p in getattr(project, "external_plugins", None) or []
            if str(p).strip()
        }
        referenced: set[str] = set()
        errors: list[ValidationError] = []
        for comp in [*getattr(project, "skills", []), *getattr(project, "agents", [])]:
            for plugin_id in comp.external_plugin_refs():
                referenced.add(plugin_id)
                if plugin_id not in declared:
                    errors.append(ValidationError(
                        rule="undeclared_external_plugin",
                        message=(
                            f"'{comp.name}'이(가) 사용 선언되지 않은 플러그인 "
                            f"'{plugin_id}'를 가리킵니다 — external_plugins에 없으면 "
                            f"빌드가 dependencies/enabledPlugins를 배선하지 않아 "
                            f"런타임에 그것을 찾지 못합니다. 카탈로그 창에서 "
                            f"플러그인을 체크하거나 set_external_plugins로 선언하세요."
                        ),
                        source=comp.name,
                        subject=comp,
                    ))
        for plugin_id in sorted(declared - referenced):
            errors.append(ValidationError(
                rule="unused_external_plugin",
                message=(
                    f"외부 플러그인 '{plugin_id}'를 사용하기로 선언했지만 어떤 "
                    f"컴포넌트도 참조하지 않습니다 — 빌드 배선(dependencies/"
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
        """dangling_string_reference — AgentConfigBase.skills /
        reference_placements.skill_name의 문자열 참조 실존 검사.

        fork 스킬의 `agent`는 여기서 보지 않는다 — 내장·외부 에이전트도 가리킬 수
        있어 프로젝트 이름만으로 판정할 수 없다(`fork_agent_missing`이 맡는다).

        "이 설정이 **스킬 이름**을 가리키는가"는 설정 자신이 답한다
        (`config.name_refs(Bucket.SKILLS)` — Q14). 네임스페이스를 인수로 받는
        덕에 동명-다른타입(스킬 "x"와 에이전트 "x")을 섞지 않는다."""
        from daedalus.model.plugin.roles import Bucket

        errors: list[ValidationError] = []

        # 전역 이름 맵
        global_skill_names = {s.name for s in project.skills}

        # config의 스킬 이름 참조 검사 — 에이전트 두 종류 모두.
        for agent in project.agents:
            for skill_name in agent.config.name_refs(Bucket.SKILLS):
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
