# tests/model/plugin/test_serialize_symmetry.py
"""설정 직렬화 **대칭** 고정 — 필드를 더하고 선언을 잊으면 여기서 걸린다.

REFACTOR_SPEC §2-c 대칭 테스트 / §8 `test_serialize_symmetry` 행. WP-4의 게이트다.

**무엇을 막는가 (M8 👻).** 종전 `_ser_config`는 종류별 `isinstance` 사다리였다.
설정 클래스에 필드를 하나 더하고 그 가지를 손대지 않으면 필드는 저장되지 않고,
로드하면 기본값으로 **조용히 되돌아온다** — 사용자는 저장 버튼을 눌렀고, 값은
사라졌고, 아무도 말해 주지 않았다. 선언(`SERIALIZED_FIELDS`)이 `fields()`와
집합으로 같아야 한다는 이 단언이 그 구멍을 구조적으로 막는다.

집합 비교인 이유: **순서는 다를 수 있다**. `AgentConfig`는 저장 키 순서가
`… memory, color, background, isolation`인데 dataclass 필드 순서는
`… memory, background, isolation, color`다(2026-09-17 실측). 순서까지 같기를
요구하면 오늘의 JSON 바이트를 표현할 수 없다 — 키 순서는 골든
(`tests/model/test_golden_project_json.py`)이 지킨다.
"""
from __future__ import annotations

import dataclasses

import pytest

from daedalus.model.plugin.config import ComponentConfig
from daedalus.model.plugin.kinds import KIND_REGISTRY
from daedalus.model.plugin.serial_fields import FieldSpec

#: 구체 설정 클래스 9종 — 레지스트리에서 파생한다(손으로 세면 새 종류를 놓친다).
CONFIG_CLASSES = tuple(spec.config_cls for spec in KIND_REGISTRY.values())


def _ids(classes):
    return [c.__name__ for c in classes]


def test_registry_covers_every_concrete_config():
    """파생 목록이 비어 있거나 중복이면 이 파일의 모든 단언이 무의미해진다."""
    assert len(CONFIG_CLASSES) == len(KIND_REGISTRY) == 9
    assert len(set(CONFIG_CLASSES)) == 9


@pytest.mark.parametrize("cls", CONFIG_CLASSES, ids=_ids(CONFIG_CLASSES))
def test_serialized_fields_match_dataclass_fields(cls):
    """`fields(cls)` 이름 집합 == `SERIALIZED_FIELDS` 이름 집합."""
    declared = {f.name for f in dataclasses.fields(cls)}
    serialized = {spec.name for spec in cls.SERIALIZED_FIELDS}
    missing = sorted(declared - serialized)
    extra = sorted(serialized - declared)
    assert not missing, (
        f"{cls.__name__}: 필드 {missing}가 SERIALIZED_FIELDS에 없다 — "
        f"저장되지 않고 로드 시 기본값으로 되돌아간다(M8)."
    )
    assert not extra, (
        f"{cls.__name__}: SERIALIZED_FIELDS의 {extra}는 dataclass 필드가 아니다 — "
        f"`to_dict`가 AttributeError로 터진다."
    )


@pytest.mark.parametrize("cls", CONFIG_CLASSES, ids=_ids(CONFIG_CLASSES))
def test_serialized_fields_have_no_duplicates(cls):
    """같은 이름을 두 번 선언하면 뒤엣것이 앞엣것을 덮어 키 순서가 흔들린다."""
    names = [spec.name for spec in cls.SERIALIZED_FIELDS]
    assert len(names) == len(set(names)), f"{cls.__name__}: 중복 선언 {names}"


@pytest.mark.parametrize("cls", CONFIG_CLASSES, ids=_ids(CONFIG_CLASSES))
def test_serialized_fields_are_field_specs(cls):
    """선언은 전부 `FieldSpec`이다 — 문자열만 적으면 코덱이 사라진다."""
    for spec in cls.SERIALIZED_FIELDS:
        assert isinstance(spec, FieldSpec), f"{cls.__name__}: {spec!r}"


@pytest.mark.parametrize("cls", CONFIG_CLASSES, ids=_ids(CONFIG_CLASSES))
def test_default_config_round_trips(cls):
    """기본값 설정의 왕복 항등 — `to_dict` → `from_dict` → 같은 값."""
    config = cls()
    again = cls.from_dict(config.to_dict())
    assert again == config
    assert again.to_dict() == config.to_dict()


@pytest.mark.parametrize("cls", CONFIG_CLASSES, ids=_ids(CONFIG_CLASSES))
def test_to_dict_keys_are_kind_plus_declaration_order(cls):
    """dict 키 = `kind` + 선언 순서. 키 순서가 곧 저장 파일의 바이트다."""
    expected = ["kind"] + [spec.name for spec in cls.SERIALIZED_FIELDS]
    assert list(cls().to_dict()) == expected


@pytest.mark.parametrize("cls", CONFIG_CLASSES, ids=_ids(CONFIG_CLASSES))
def test_kind_tag_is_the_config_kind(cls):
    """다형성 태그는 `KIND`다 — 이것이 어긋나면 로드가 다른 클래스를 고른다."""
    assert cls().to_dict()["kind"] == cls.KIND


def test_abstract_bases_declare_their_own_tuple_not_an_accumulator():
    """상속으로 **누적**하지 않는다 — 각 클래스가 명시 튜플을 선언한다.

    누적이면 선언 순서가 상속 그래프에 숨고, `AgentConfig`의 `color`가
    `background`보다 앞에 나가는 오늘의 키 순서를 표현할 수 없다.
    """
    from daedalus.model.plugin.config import AgentConfig, SkillConfig

    base = [spec.name for spec in ComponentConfig.SERIALIZED_FIELDS]
    assert base == ["model", "effort", "hooks"]
    assert [spec.name for spec in SkillConfig.SERIALIZED_FIELDS][: len(base)] == base
    tail = [spec.name for spec in AgentConfig.SERIALIZED_FIELDS][-3:]
    assert tail == ["color", "background", "isolation"]


def test_model_missing_key_loads_as_none_not_the_declared_default():
    """`model` 키 부재는 **None**이다 — 선언 기본값(INHERIT)이 아니다.

    오늘의 결함이고(backlog D10) 고치는 것은 저장 파일 해석을 바꾸는 별도
    결정이라, WP-4는 이 부재 의미론을 **보존**한다. 누군가 `missing=None`을
    지우면 여기서 걸리고 사람이 판단한다.
    """
    from daedalus.model.plugin.config import ProceduralSkillConfig

    assert ProceduralSkillConfig.from_dict({}).model is None
    assert ProceduralSkillConfig().model is not None


def test_unknown_keys_in_the_saved_dict_are_ignored():
    """퇴역한 키가 남아 있어도 흡수하지 않는다(원칙 7) — 조용히 무시한다."""
    from daedalus.model.plugin.config import ForkAgentConfig

    config = ForkAgentConfig.from_dict(
        {"kind": "fork_agent", "background": True, "isolation": "worktree"}
    )
    assert not hasattr(config, "background")
    assert not hasattr(config, "isolation")
