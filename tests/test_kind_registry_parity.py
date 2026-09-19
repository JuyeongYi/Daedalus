# tests/test_kind_registry_parity.py
"""종류 레지스트리 **패리티** (REFACTOR_SPEC §8, WP-3).

`daedalus/model/plugin/kinds.py`가 "종류가 몇 가지인가"의 단일 등록 지점이 된 뒤,
각 계층이 들고 있던 표들은 전부 **파생**이어야 한다. 파생이 아니라 베껴 쓴 표가
하나라도 남으면 새 종류가 그 표에서만 조용히 빠지고, 그 부재는 예외가 아니라
"팔레트에 안 보임"·"MCP가 거절함"·"파일에서 안 읽힘"으로 나타난다(👻).

그래서 여기서는 **집합 등식**만 쓴다 — 한쪽을 고치고 다른 쪽을 잊으면 실패한다.
`KIND_UI`(WP-7)·`EMITTERS`(WP-6) 부분은 그 표들이 생길 때 이 파일에 합류한다.

생성 등가 게이트(`make_component` ↔ `new()`)도 여기로 옮겨 왔다 —
`view/actions/creation`의 종류별 람다 9개를 레지스트리 파생으로 바꾸는 것이
WP-3이고, **바꾸기 전후로 같은 물건이 만들어진다**는 것을 이 파일이 지킨다.
"""
from __future__ import annotations

import dataclasses

import pytest

from daedalus.mcp.tools.props import PropsTools
from daedalus.model.plugin.field_matrix import (
    AGENT_FIELD_MATRIX,
    SKILL_FIELD_MATRIX,
)
from daedalus.model.plugin.kinds import (
    COMPONENT_CLASSES,
    CONFIG_KIND_INDEX,
    KIND_REGISTRY,
    config_kinds_in,
    kinds_in,
    spec_by_config_kind,
    spec_for,
)
from daedalus.model.plugin.enums import FieldEmit
from daedalus.model.plugin.roles import Bucket, OutputLocation
from daedalus.view.actions.creation import make_component

# 창 대역은 **한 벌만** 둔다 — FSM 팩토리가 두 벌이 되면 "같은 물건인가"를 묻는
# 이 파일의 등가 게이트 자체가 흐려진다.
from tests.model.plugin.test_capability_surface import _StubWindow

_BUCKETS = (Bucket.SKILLS, Bucket.AGENTS)


# ── 1. 등록 지점 ↔ 레지스트리 ────────────────────────────────────────────

def test_registry_rows_are_exactly_the_registered_classes():
    """행의 순서까지 선언 순서다 — 팔레트 탭·MCP 문구가 그 순서를 쓴다."""
    assert tuple(s.component_cls for s in KIND_REGISTRY.values()) == COMPONENT_CLASSES


def test_component_kind_and_config_kind_are_a_bijection():
    """두 어휘는 **짝**이다 — 한 config 종류를 두 컴포넌트가 나눠 쓰면 역색인이 거짓말한다."""
    assert len(CONFIG_KIND_INDEX) == len(KIND_REGISTRY)
    assert {s.config_kind for s in KIND_REGISTRY.values()} == set(CONFIG_KIND_INDEX)


@pytest.mark.parametrize("bucket", _BUCKETS, ids=lambda b: b.value)
def test_bucket_partition_is_total(bucket):
    """모든 행은 정확히 한 버킷에 속한다(합집합 = 전체, 교집합 = 공집합)."""
    others = [b for b in _BUCKETS if b is not bucket]
    mine = set(kinds_in(bucket))
    assert mine and not mine & {k for b in others for k in kinds_in(b)}
    assert mine | {k for b in others for k in kinds_in(b)} == set(KIND_REGISTRY)


# ── 2. 프론트매터 매트릭스 ───────────────────────────────────────────────

@pytest.mark.parametrize(
    ("bucket", "table"),
    [(Bucket.SKILLS, SKILL_FIELD_MATRIX), (Bucket.AGENTS, AGENT_FIELD_MATRIX)],
    ids=lambda x: getattr(x, "value", "table"),
)
def test_matrix_keys_are_exactly_the_registered_config_kinds(bucket, table):
    """표에만 있는 종류(죽은 행)도, 종류에만 있는 표 없음(빈 폼)도 없다."""
    assert set(config_kinds_in(bucket)) == set(table)


def test_registry_matrix_view_is_read_only():
    """살아 있는 dict를 들려주면 한 호출자의 수정이 모듈 표를 오염시킨다."""
    spec = spec_by_config_kind("procedural")
    key = next(iter(spec.field_matrix))
    with pytest.raises(TypeError):
        spec.field_matrix[key] = None  # type: ignore[index]


def test_kinds_that_emit_a_file_have_frontmatter_rows():
    """산출이 있으면 프론트매터 행이 있고, 산출이 없으면 배출 행이 없다 — 양방향.

    뒤쪽은 오늘 공집합에 대한 단언이지만(모든 종류가 파일을 낸다) 계약을
    **먼저** 못 박아 둔다: 산출 없는 종류(WP-9 `ExternalAgent`)가 생겼을 때
    프론트매터 행을 물려받으면 편집기가 나가지도 않는 필드를 그린다.
    """
    for kind, spec in KIND_REGISTRY.items():
        emits = {rule.emit for rule in spec.field_matrix.values()}
        if spec.output_location is OutputLocation.NONE:
            assert not emits & {FieldEmit.FRONTMATTER, FieldEmit.BODY}, kind
        else:
            assert FieldEmit.FRONTMATTER in emits, kind


# ── 3. MCP 어휘 ──────────────────────────────────────────────────────────

def test_mcp_create_vocabulary_is_derived_from_the_registry():
    """`create_skill`/`create_agent`가 받는 종류 = 레지스트리의 config 어휘.

    **순서까지** 같다 — 거절 문구의 "사용 가능: …" 목록이 결정적이어야 한다.
    """
    assert PropsTools._SKILL_KINDS == config_kinds_in(Bucket.SKILLS)
    assert PropsTools._AGENT_KINDS == config_kinds_in(Bucket.AGENTS)


# ── 4. 생성 등가 (V7 이관 게이트) ────────────────────────────────────────

def _fsm_factory_for(spec, window: _StubWindow):
    return (
        window._make_agent_fsm if spec.bucket is Bucket.AGENTS else window._make_fsm
    )


def _fsm_shape(machine) -> tuple[str, tuple[str, ...], str]:
    return (
        machine.name,
        tuple(s.name for s in machine.states),
        machine.initial_state.name,
    )


@pytest.mark.parametrize("config_kind", sorted(CONFIG_KIND_INDEX))
@pytest.mark.parametrize("agent", [None, "worker"])
def test_make_component_matches_registry_new_field_by_field(config_kind, agent):
    """레지스트리·MCP·캔버스가 쓰는 팩토리와 `new()`가 **같은 물건**을 만든다.

    WP-3이 `creation.make_component`의 종류별 람다 9개를 레지스트리 파생으로
    바꿔도 만들어지는 컴포넌트가 달라지지 않는다는 게이트다.
    """
    spec = spec_by_config_kind(config_kind)
    cls = spec.component_cls
    window = _StubWindow()
    legacy = make_component(window, config_kind, "thing", "desc", agent=agent)
    fresh = cls.new(
        "thing", "desc", fsm_factory=_fsm_factory_for(spec, window), agent=agent
    )
    assert type(fresh) is type(legacy)
    for f in dataclasses.fields(cls):
        if f.name == "id":
            continue          # 안정 ID는 인스턴스마다 다르다(compare=False)
        left, right = getattr(fresh, f.name), getattr(legacy, f.name)
        if f.name == "fsm":
            assert _fsm_shape(left) == _fsm_shape(right), f.name
        else:
            assert left == right, f.name


@pytest.mark.parametrize(
    "kind",
    [k for k, s in KIND_REGISTRY.items() if s.component_cls.REQUIRES_OUTPUT_PORTS],
)
def test_required_ports_exist_right_after_new(kind):
    """`REQUIRES_OUTPUT_PORTS`인 종류는 태어나자마자 포트를 갖는다.

    없으면 배치 즉시 `transfer_on_not_empty` 에러가 뜬다 — 새 컴포넌트가
    처음부터 빨간 줄을 달고 나오는 것을 막는 것이 `creation_defaults()`다.
    """
    spec = KIND_REGISTRY[kind]
    window = _StubWindow()
    comp = spec.component_cls.new("thing", fsm_factory=_fsm_factory_for(spec, window))
    assert comp.output_ports(), f"{kind}이(가) 포트 0개로 태어난다"
    assert spec_for(comp) is spec
