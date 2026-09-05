# daedalus/model/validation/project_rules/blackboard.py
"""블랙보드(blackboard) 규칙 3종 (이동만 — 동작 불변) — WP-BB Part E / WP-BT."""
from __future__ import annotations

from daedalus.model.validation.project_rules.scan import scan_state_access
from daedalus.model.validation.severity import ValidationError


class _BlackboardRules:
    """블랙보드 규칙 모음 (_ProjectRules 믹스인)."""

    _scan_state_access = staticmethod(scan_state_access)

    @staticmethod
    def _check_blackboard_field_types(project) -> list[ValidationError]:
        """invalid_blackboard_field_type — 블랙보드 필드 타입이 허용 집합
        (BLACKBOARD_FIELD_TYPES — 스칼라 원소 타입 4종) 밖이면 경고 (WP-BT).

        구버전 파일의 list/json/any/number 필드를 F7이 짚어 준다 (로드·컴파일은
        계속 동작 — 경고 등급). 컨테이너 형상은 CollectionType이 전담한다.
        """
        from daedalus.model.fsm.blackboard import BLACKBOARD_FIELD_TYPES

        errors: list[ValidationError] = []
        classes = getattr(project.blackboard, "class_definitions", None) or []
        for cls in classes:
            for fld in cls.fields:
                if fld.field_type not in BLACKBOARD_FIELD_TYPES:
                    errors.append(ValidationError(
                        rule="invalid_blackboard_field_type",
                        message=(
                            f"블랙보드 필드 '{cls.name}.{fld.name}'의 타입 "
                            f"'{fld.field_type.value}'은 더 이상 허용되지 않습니다 — "
                            f"스칼라 타입(string/int/float/bool) + 컬렉션 조합을 쓰세요."
                        ),
                        source=f"{cls.name}.{fld.name}",
                        subject=fld,
                    ))
        return errors

    @staticmethod
    def _check_dangling_blackboard_refs(project) -> list[ValidationError]:
        """dangling_blackboard_ref — 상태 reads/writes의 "Class"/"Class.field" 문자열
        참조가 프로젝트 최상위 블랙보드 class_definitions에 실존하는지 검사.

        미존재 → 경고(subject=해당 상태). 빈 문자열은 스킵. 모든 머신(skill.fsm/
        agent.fsm, 재귀)과 프로젝트 그래프의 상태를 검사한다.
        """
        classes = getattr(project.blackboard, "class_definitions", None) or []
        known_classes = {c.name for c in classes}
        known_fields = {f"{c.name}.{fld.name}" for c in classes for fld in c.fields}

        errors: list[ValidationError] = []

        def _make_checker(path: tuple[str, ...]):
            def _visit(state) -> None:
                for ref in list(getattr(state, "reads", None) or []) + list(
                    getattr(state, "writes", None) or []
                ):
                    if not ref:
                        continue
                    valid = ref in known_fields if "." in ref else ref in known_classes
                    if not valid:
                        errors.append(ValidationError(
                            rule="dangling_blackboard_ref",
                            message=(
                                f"상태 '{state.name}'의 블랙보드 참조 '{ref}'이 "
                                f"프로젝트 블랙보드에 없습니다."
                            ),
                            source=state.name,
                            subject=state,
                            path=path,
                        ))
            return _visit

        for skill in project.skills:
            fsm = getattr(skill, "fsm", None)
            if fsm is not None:
                scan_state_access(fsm, _make_checker((f"skill:{skill.name}",)))
        for agent in project.agents:
            scan_state_access(agent.fsm, _make_checker((f"agent:{agent.name}",)))
        graph = getattr(project, "graph", None)
        if graph is not None:
            scan_state_access(graph, _make_checker(("project",)))

        return errors

    @staticmethod
    def _check_orphan_blackboard_fields(project) -> list[ValidationError]:
        """orphan_blackboard_field — 어떤 상태의 reads/writes에도 등장하지 않는
        블랙보드 필드를 경고. 클래스 전체 참조("Class")는 그 클래스의 모든 필드를
        커버한 것으로 간주한다. 프로젝트 전체에 접근 선언이 하나도 없으면 스킵
        (선언 기능 미사용 프로젝트에 경고 폭주 방지)."""
        classes = getattr(project.blackboard, "class_definitions", None) or []
        if not classes:
            return []

        declared: set[str] = set()

        def _collect(state) -> None:
            declared.update(getattr(state, "reads", None) or [])
            declared.update(getattr(state, "writes", None) or [])

        for skill in project.skills:
            fsm = getattr(skill, "fsm", None)
            if fsm is not None:
                scan_state_access(fsm, _collect)
        for agent in project.agents:
            scan_state_access(agent.fsm, _collect)
        graph = getattr(project, "graph", None)
        if graph is not None:
            scan_state_access(graph, _collect)

        if not declared:
            return []  # 접근 선언 기능 자체를 쓰지 않는 프로젝트 — 스킵

        errors: list[ValidationError] = []
        for cls in classes:
            if cls.name in declared:
                continue  # 클래스 전체 참조 — 모든 필드 커버
            for fld in cls.fields:
                field_ref = f"{cls.name}.{fld.name}"
                if field_ref in declared:
                    continue
                errors.append(ValidationError(
                    rule="orphan_blackboard_field",
                    message=(
                        f"블랙보드 필드 '{field_ref}'을 참조하는 상태(reads/writes)가 "
                        f"없습니다."
                    ),
                    source=field_ref,
                    subject=fld,
                ))
        return errors
