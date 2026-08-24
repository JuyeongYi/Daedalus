"""ValidationError.is_warning / WARNING_RULES 완전성 테스트 (WP-J)."""
from __future__ import annotations

import importlib
import inspect
import pkgutil
import re

import pytest

import daedalus.model.validation as validation_module
from daedalus.model.validation import ValidationError, WARNING_RULES


# 에러로 분류되어야 하는 규칙 목록
_ERROR_RULES = frozenset({
    "initial_state_in_states",
    "final_states_in_states",
    "no_nested_agent",
    "no_agent_to_agent",
    "no_duplicate_skill_ref",
    "transfer_on_not_empty",
    "transition_endpoint_not_in_states",
    "duplicate_component_name",
    "duplicate_tool_name",
    "duplicate_hook_name",
    "transition_type_consistency",
    "choice_completeness",
})

# 경고로 분류되어야 하는 규칙 목록 (WARNING_RULES와 동일)
_WARN_RULES = frozenset({
    "missing_required_input",
    "pseudo_state_hooks",
    "completion_event_on_composite",
    "duplicate_state_name",
    "unreachable_state",
    "invalid_data_map_source",
    "trigger_unknown_event",
    "invalid_blackboard_field_type",
    "choice_completeness_missing_else",
    "parallel_join_count",
    "dangling_string_reference",
    "invalid_component_name",
    "dangling_tool_ref",
    "empty_tool_definition",
    "dangling_hook_ref",
    "empty_hook_command",
    "hook_matcher_without_tool_event",
    "dangling_blackboard_ref",
    "orphan_blackboard_field",
    "dangling_file_ref",  # WP-FR — 아래 _EXTERNALLY_EMITTED_RULES 참조
    "mcp_agent_in_marketplace_build",  # WP-TG
    "plugin_root_in_local_build",  # WP-TG
    "unsupported_agent_field_in_marketplace_build",  # WP-LA
    "hook_matcher_matches_nothing",  # WP-HS
    "missing_mcp_server_def",  # WP-MW — 아래 _EXTERNALLY_EMITTED_RULES 참조
    "unmergeable_settings_json",  # WP-MW
    "dangling_skill_file_ref",  # WP-SF — 아래 _EXTERNALLY_EMITTED_RULES 참조
    "unknown_skill_files_dir",  # WP-SF
    "skill_dir_token_in_agent",  # WP-SF
    "mid_chain_user_invocable",  # A3
})

# validation 패키지 밖(컴파일러 등)에서 emit되지만 WARNING_RULES에는 등록된 규칙 —
# is_warning 판정 일관성을 위해 등록하되, _emitted_rules_from_source() 소스
# introspection 대상에서는 제외한다(검증기는 파일시스템 무접근 순수성을
# 유지하므로 이 rule 문자열이 validation 패키지 안에 나타나지 않는다).
_EXTERNALLY_EMITTED_RULES = frozenset({
    "dangling_file_ref",  # daedalus/compiler/project_compiler.py 소관 (WP-FR)
    "missing_mcp_server_def",  # daedalus/compiler/project_compiler.py 소관 (WP-MW)
    "unmergeable_settings_json",  # daedalus/compiler/project_compiler.py 소관 (WP-MW)
    "dangling_skill_file_ref",  # daedalus/compiler/project_compiler.py 소관 (WP-SF)
    "unknown_skill_files_dir",  # daedalus/compiler/project_compiler.py 소관 (WP-SF)
})


def _validation_submodule_names() -> list[str]:
    """validation 패키지 하위 모듈의 **전체 점 표기 이름**을 재귀 열거한다.

    ``iter_modules``가 아니라 ``walk_packages``인 이유: 전자는 패키지 바로 아래
    최상위 모듈만 열거한다(비재귀). 지금은 평면 3모듈이라 결과가 같지만, 이후
    규칙을 ``validation/project/hooks.py`` 같은 하위 *패키지*로 한 겹 더 나누면
    그 모듈의 ``rule=`` 리터럴이 introspect 대상에서 빠져 등급 미분류가 조용히
    통과한다. 분해가 더 진행돼도 커버리지가 따라가도록 재귀로 훑는다.
    """
    return [
        info.name
        for info in pkgutil.walk_packages(
            validation_module.__path__, prefix=f"{validation_module.__name__}."
        )
    ]


def _validation_sources() -> str:
    """validation 패키지 **전 모듈**의 소스를 합친다 (WP-RF-3d 분해 대응).

    분해 전에는 단일 모듈이라 ``inspect.getsource(validation_module)`` 하나로
    충분했다. 패키지가 된 지금 파사드(``__init__``)만 보면 규칙 검사 본문이
    통째로 빠지므로, 하위 모듈을 재귀 열거해 함께 읽는다 — 앞으로 구획이 더
    갈려도 이 테스트가 따라간다.
    """
    texts = [inspect.getsource(validation_module)]
    for name in _validation_submodule_names():
        try:
            texts.append(inspect.getsource(importlib.import_module(name)))
        except OSError:
            # 빈 모듈(하위 패키지의 빈 ``__init__.py`` 등)은 linecache가 소스를
            # 못 내주고 OSError를 던진다. 규칙 리터럴이 있을 수 없는 파일이므로
            # 건너뛴다 — 여기서 터지면 아래 분류 테스트가 진짜 이유를 못 말한다.
            continue
    return "\n".join(texts)


def _emitted_rules_from_source() -> frozenset[str]:
    """validation 패키지 소스에서 실제 emit되는 rule= 리터럴을 introspect."""
    return frozenset(re.findall(r'rule="([a-z0-9_]+)"', _validation_sources()))


def test_warning_rules_completeness():
    """WARNING_RULES가 경고 규칙 집합과 동일하다."""
    assert WARNING_RULES == _WARN_RULES


def test_validation_sources_cover_rule_modules():
    """소스 introspection이 규칙 본문이 있는 하위 모듈까지 읽는지 고정.

    파사드(``__init__``)만 읽으면 규칙이 하나도 안 잡히므로, 아래 분류 테스트가
    전부 통과해 버린다 — 모듈 이동/개명으로 커버리지가 조용히 사라지는 것을 막는다.
    """
    text = _validation_sources()
    names = _validation_submodule_names()
    assert f"{validation_module.__name__}.machine_rules" in names
    assert 'rule="unreachable_state"' in text  # 머신 수준 규칙 본문
    assert 'rule="duplicate_component_name"' in text  # 프로젝트 수준 규칙 본문


def test_every_emitted_rule_is_classified():
    """validation 패키지가 emit하는 모든 rule이 에러/경고 어느 한쪽에 분류되어 있다.

    소스 introspection — 새 규칙 추가 시 이 테스트가 깨져 분류 누락을 강제 검출한다.
    (하드코딩 재진술이 아니라 실제 emit 지점 기준.)
    """
    emitted = _emitted_rules_from_source()
    assert emitted, "validation 패키지에서 rule= 리터럴을 찾지 못했다 — 패턴 확인 필요"
    classified = _ERROR_RULES | _WARN_RULES
    unclassified = emitted - classified
    assert not unclassified, (
        f"분류되지 않은 규칙: {sorted(unclassified)} — "
        f"WARNING_RULES(validation/severity.py) 및 본 테스트의 "
        f"_ERROR_RULES/_WARN_RULES에 등급을 지정하라"
    )
    # 역방향: 분류표에 있으나 더 이상 emit되지 않는 유령 규칙도 검출
    # (컴파일러 등 validation 패키지 밖에서 emit되는 규칙은 제외 — 위 참조)
    ghost = classified - emitted - _EXTERNALLY_EMITTED_RULES
    assert not ghost, f"emit되지 않는 유령 규칙: {sorted(ghost)}"


def test_error_and_warning_rules_are_disjoint():
    """에러 규칙과 경고 규칙이 겹치지 않는다 (invalid_component_name 제외)."""
    overlap = _ERROR_RULES & WARNING_RULES
    assert not overlap, f"에러/경고 규칙 중복: {overlap}"


@pytest.mark.parametrize("rule", sorted(_ERROR_RULES))
def test_error_rule_is_not_warning(rule: str):
    """에러 등급 규칙은 is_warning이 False다."""
    err = ValidationError(rule=rule, message="test msg", source="s")
    assert not err.is_warning, f"규칙 '{rule}'은 에러여야 한다"


@pytest.mark.parametrize("rule", sorted(_WARN_RULES - {"invalid_component_name"}))
def test_warning_rule_is_warning(rule: str):
    """경고 등급 규칙은 is_warning이 True다."""
    err = ValidationError(rule=rule, message="test msg", source="s")
    assert err.is_warning, f"규칙 '{rule}'은 경고여야 한다"


def test_invalid_component_name_empty_is_error():
    """invalid_component_name + '비어 있습니다' 메시지 → 에러."""
    err = ValidationError(
        rule="invalid_component_name",
        message="컴포넌트 이름이 비어 있습니다.",
        source="",
    )
    assert not err.is_warning


def test_invalid_component_name_mismatch_is_warning():
    """invalid_component_name + 일반 불일치 메시지 → 경고."""
    err = ValidationError(
        rule="invalid_component_name",
        message="컴포넌트 이름 'MySkill'이 명명 규약에 맞지 않습니다.",
        source="MySkill",
    )
    assert err.is_warning
