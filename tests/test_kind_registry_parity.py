# tests/test_kind_registry_parity.py
"""종류 레지스트리 **패리티** (REFACTOR_SPEC §8, WP-3).

`daedalus/model/plugin/kinds.py`가 "종류가 몇 가지인가"의 단일 등록 지점이 된 뒤,
각 계층이 들고 있던 표들은 전부 **파생**이어야 한다. 파생이 아니라 베껴 쓴 표가
하나라도 남으면 새 종류가 그 표에서만 조용히 빠지고, 그 부재는 예외가 아니라
"팔레트에 안 보임"·"MCP가 거절함"·"파일에서 안 읽힘"으로 나타난다(👻).

그래서 여기서는 **집합 등식**만 쓴다 — 한쪽을 고치고 다른 쪽을 잊으면 실패한다.
`EMITTERS`(WP-6)는 §3절에, `KIND_UI`(WP-7)는 §6절에 합류했다.

생성 등가 게이트(`make_component` ↔ `new()`)도 여기로 옮겨 왔다 —
`view/actions/creation`의 종류별 람다 9개를 레지스트리 파생으로 바꾸는 것이
WP-3이고, **바꾸기 전후로 같은 물건이 만들어진다**는 것을 이 파일이 지킨다.
"""
from __future__ import annotations

import dataclasses

import pytest

from daedalus.compiler import plan_kinds
from daedalus.compiler.emit.emitters import EMITTERS
from daedalus.compiler.emit.section_plan import SECTION_PLANS
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
from daedalus.model.plugin.roles import Bucket, OutputLocation, PlacementRole
from daedalus.view.actions.creation import make_component
from daedalus.view.kind_ui import KIND_UI, DIALOG_TITLES, ui_by_config_kind

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


# ── 3. 산출 emitter (WP-6) ───────────────────────────────────────────────

def test_emitters_are_exactly_the_kinds_that_emit_a_file():
    """**양방향**이다 — 산출이 있는 종류마다 emitter가 하나, 없는 종류에는 없다.

    한쪽만 보면 둘 다 조용히 깨진다: emitter를 잊으면 그 종류가 컴파일에서
    `emitter_for` ValueError로 죽고, 산출이 없는 종류(WP-9 `ExternalAgent`)에
    emitter를 남기면 계획에 오르지도 않는 파일을 렌더하는 죽은 코드가 된다.
    """
    expected = {
        kind for kind, spec in KIND_REGISTRY.items()
        if spec.output_location is not OutputLocation.NONE
    }
    assert set(EMITTERS) == expected


def test_section_plans_are_exactly_the_emitter_kinds():
    """emitter와 절 표는 같은 종류 집합을 말한다 — 한쪽만 늘면 조회가 죽는다."""
    assert set(SECTION_PLANS) == set(EMITTERS)


@pytest.mark.parametrize("kind", sorted(EMITTERS))
def test_emitter_plan_kind_matches_the_bucket(kind):
    """스킬은 `skill`, 에이전트는 `agent` 계획 kind로 오른다(러너는 별도 행)."""
    spec = KIND_REGISTRY[kind]
    expected = plan_kinds.SKILL if spec.bucket is Bucket.SKILLS else plan_kinds.AGENT
    assert EMITTERS[kind].plan_kind == expected


# ── 4. MCP 어휘 ──────────────────────────────────────────────────────────

def test_mcp_create_vocabulary_is_derived_from_the_registry():
    """`create_skill`/`create_agent`가 받는 종류 = 레지스트리의 config 어휘.

    **순서까지** 같다 — 거절 문구의 "사용 가능: …" 목록이 결정적이어야 한다.
    """
    assert PropsTools._SKILL_KINDS == config_kinds_in(Bucket.SKILLS)
    assert PropsTools._AGENT_KINDS == config_kinds_in(Bucket.AGENTS)


# ── 5. 생성 등가 (V7 이관 게이트) ────────────────────────────────────────

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


# ── 6. 뷰 표면 (WP-7) ────────────────────────────────────────────────────

def test_kind_ui_rows_are_exactly_the_registered_kinds():
    """**양방향**이다 — UI 행이 없는 종류도, 종류가 없는 UI 행도 없다.

    한쪽만 보면 둘 다 조용히 깨진다: 행을 잊으면 그 종류가 팔레트·캔버스·편집
    탭에서 `ui_for` ValueError로 죽고(예전에는 회색 기본 노드로 **조용히**
    그려졌다), 남은 행은 아무도 그리지 않는 죽은 표가 된다.
    """
    assert set(KIND_UI) == set(KIND_REGISTRY)


def test_kind_ui_order_follows_the_registry():
    """선언 순서 = 팔레트 탭 순서 — 같은 질문에 같은 순서로 답한다(결정성)."""
    assert list(KIND_UI) == list(KIND_REGISTRY)


def test_dialog_titles_cover_every_config_kind():
    """이름 입력 다이얼로그 제목은 config 어휘 전부를 덮는다 (V9)."""
    assert set(DIALOG_TITLES) == set(CONFIG_KIND_INDEX)
    assert all(DIALOG_TITLES.values())


#: 상태 노드로 놓이지 않는데도 캔버스 스타일을 갖는 종류 — **구버전 저장
#: 그래프의 폴백**이다. `declarative`는 예전에 배치 가능했고, 그때 저장된
#: `.daedalus.json`의 배치는 로드 시 그대로 복원된다(배치 **판정**만 막혔다).
#: 새 종류가 이 목록에 드는 것은 규칙 위반이다 — 목록은 줄어들기만 한다.
_LEGACY_STYLED_KINDS: frozenset[str] = frozenset({"declarative_skill"})


@pytest.mark.parametrize("kind", sorted(KIND_REGISTRY))
def test_state_placeable_kinds_have_a_node_style(kind):
    """상태 노드로 놓이는 종류는 캔버스 스타일을 갖는다 — 그리고 그 역도 참이다.

    `node_style`이 없으면 노드가 **빈 상태와 구분되지 않는 회청색**으로
    그려진다(랩핑 스킬이 겪은 실제 회귀). 반대로 놓이지 않는 종류에 스타일을
    남기면 아무도 쓰지 않는 표가 된다 — 예외는 구버전 그래프 폴백뿐이고
    그 목록도 여기서 고정한다.
    """
    spec = KIND_REGISTRY[kind]
    expected = spec.placement is PlacementRole.STATE or kind in _LEGACY_STYLED_KINDS
    assert (KIND_UI[kind].node_style is not None) is expected


@pytest.mark.parametrize("kind", sorted(KIND_REGISTRY))
def test_switch_labels_are_exactly_the_convert_family_kinds(kind):
    """전환 라벨은 전환 가족 선언과 짝이다 — 라벨 없는 가족원은 버튼이 안 생긴다."""
    spec = KIND_REGISTRY[kind]
    ui = KIND_UI[kind]
    assert (ui.switch_label is not None) is (spec.convert_family is not None)
    assert (ui.switch_tooltip is not None) is (spec.convert_family is not None)


def test_registry_sections_use_the_registry_vocabulary():
    """팔레트 섹션 키 = config 어휘(R14) — 손으로 조립한 kind 문자열이 없다."""
    from daedalus.view.panels.registry_panel import _SECTION_KINDS

    assert list(_SECTION_KINDS) == list(
        config_kinds_in(Bucket.SKILLS)
    ) + list(config_kinds_in(Bucket.AGENTS))
    for config_kind in _SECTION_KINDS:
        assert ui_by_config_kind(config_kind) is KIND_UI[
            spec_by_config_kind(config_kind).kind
        ]
