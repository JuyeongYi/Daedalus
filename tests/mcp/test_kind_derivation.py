"""MCP 종류·필드 어휘가 **레지스트리와 매트릭스에서 파생**되는지 (WP-8 P3~P5).

카탈로그 P3·P4·P5는 전부 👻이었다 — 빠뜨려도 테스트도 컴파일도 실패하지 않는
손수 목록이다: 생성 인자(`fork_agent`/`source`/`usage`)가 유효한 kind 목록,
`set_component_field`가 받는 필드의 문자열 사다리, `place_component`의 비배치
kind를 열거한 거절 문구. 여기서는 그 셋이 **선언에서 나온다**는 것과, 레지스트리
행이 사라지면 조용히 넘어가지 않고 **이름을 말하며 실패**한다는 것을 고정한다.
"""
from __future__ import annotations

import pytest

from daedalus.model.project import PluginProject


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    win = MainWindow()
    win.set_project(PluginProject(name="p"))
    yield win
    win.close()


@pytest.fixture
def tools(window):
    from daedalus.mcp.tools import DaedalusTools

    return DaedalusTools(window)


# --- P3: 생성 인자는 config 필드에서 파생 ---------------------------------


def test_fork_agent_rejection_lists_the_kinds_whose_config_has_agent(tools):
    """거절은 이유와 **선택지**를 말한다 — 목록은 config 클래스에서 나온다."""
    with pytest.raises(ValueError) as excinfo:
        tools.create_skill("x", kind="procedural", fork_agent="Explore")
    message = str(excinfo.value)
    assert "agent" in message
    # 순서가 아니라 **집합**을 본다(선언 순서가 바뀌어도 계약은 같다, R12).
    assert {"sync_fork", "async_fork"} <= set(
        part.strip() for part in message.split("사용 가능:")[-1].split(",")
    )


def test_fork_agent_is_reported_for_every_kind_whose_config_has_it(tools):
    """응답의 `fork_agent`도 파생이다 — fork 2종을 이름으로 열거하지 않는다."""
    import dataclasses

    from daedalus.model.plugin.kinds import KIND_REGISTRY
    from daedalus.model.plugin.roles import Bucket

    expected = {
        spec.config_kind
        for spec in KIND_REGISTRY.values()
        if spec.bucket is Bucket.SKILLS
        and any(f.name == "agent" for f in dataclasses.fields(spec.config_cls))
    }
    reported = set()
    for kind in ("procedural", "sync_fork", "async_fork", "declarative"):
        out = tools.create_skill(f"s-{kind}", kind=kind)
        if "fork_agent" in out:
            reported.add(kind)
    assert reported == expected


# --- 레지스트리 부재는 시끄럽다 (F9) --------------------------------------


@pytest.fixture
def registry_without_procedural(monkeypatch):
    from daedalus.model.plugin import kinds as kinds_mod

    thinned = {
        k: v for k, v in kinds_mod.KIND_REGISTRY.items() if k != "procedural_skill"
    }
    monkeypatch.setattr(kinds_mod, "KIND_REGISTRY", thinned)
    monkeypatch.setattr(
        kinds_mod,
        "CONFIG_KIND_INDEX",
        {s.config_kind: s for s in thinned.values()},
    )
    return thinned


def test_create_skill_fails_loudly_for_a_removed_kind(
    tools, window, registry_without_procedural
):
    """레지스트리 행이 사라지면 **이름을 말하며** 실패한다 — 조용한 생성 실패 금지."""
    with pytest.raises(ValueError, match="procedural"):
        tools.create_skill("ghost", kind="procedural")
    assert window._project.skills == []


def test_create_skill_with_coordinates_fails_before_creating(
    tools, window, registry_without_procedural
):
    """좌표 경로도 같은 레지스트리를 탄다 — 배치 판정이 먼저 거절한다."""
    with pytest.raises(ValueError, match="procedural"):
        tools.create_skill("ghost", kind="procedural", x=1, y=2)
    assert window._project.skills == []


def test_create_agent_fails_loudly_for_a_removed_kind(tools, window, monkeypatch):
    from daedalus.model.plugin import kinds as kinds_mod

    thinned = {k: v for k, v in kinds_mod.KIND_REGISTRY.items() if k != "agent"}
    monkeypatch.setattr(kinds_mod, "KIND_REGISTRY", thinned)
    monkeypatch.setattr(
        kinds_mod,
        "CONFIG_KIND_INDEX",
        {s.config_kind: s for s in thinned.values()},
    )
    with pytest.raises(ValueError, match="agent"):
        tools.create_agent("ghost")
    assert window._project.agents == []


# --- P4: setter 허용 = 매트릭스 비-FIXED 행 -------------------------------


def test_fixed_field_is_refused_with_its_fixed_value(tools):
    """종류가 고정하는 필드는 조용한 no-op이 아니라 **거절**이다(원칙 5)."""
    tools.create_skill("scout", kind="sync_fork")
    with pytest.raises(ValueError) as excinfo:
        tools.set_component_field("scout", "context", "fork")
    message = str(excinfo.value)
    assert "context" in message and "고정" in message


def test_field_on_config_but_not_in_the_matrix_is_refused(tools, window):
    """`allowed_tools`는 fork config에 남아 있지만 fork 매트릭스에는 없다.

    예전에는 `hasattr(config, field)`만 보고 받아 저장했고, 값은 산출에 한 번도
    도달하지 않았다 — fork에서는 에이전트 도구가 이긴다(실측, CC 2.1.268).
    """
    tools.create_skill("scout", kind="sync_fork")
    with pytest.raises(ValueError, match="없습니다"):
        tools.set_component_field("scout", "allowed_tools", ["Read"])
    skill = next(s for s in window._project.skills if s.name == "scout")
    assert skill.config.allowed_tools == []


def test_settable_fields_are_exactly_the_non_fixed_matrix_rows(tools):
    """setter가 실제로 받는 집합 == 매트릭스 비-FIXED 행 − 전용 도구 필드.

    멤버십 두 개만 보면 setter가 FIXED 행을 전부 받아도 통과한다 — 목록을
    **돌려서** 실제 허용 집합을 재고 집합 동등으로 고정한다(원칙 1).
    """
    from daedalus.model.plugin.enums import FieldVisibility
    from daedalus.mcp.tools.fields import _DEDICATED_TOOL_FIELDS

    tools.create_skill("scout", kind="sync_fork")
    rows = tools.list_component_fields("scout")["fields"]
    listed = {
        f["field"] for f in rows if f["visibility"] != FieldVisibility.FIXED.value
    }
    assert "agent" in listed and "allowed_tools" not in listed

    accepted = set()
    for row in rows:
        field = row["field"]
        try:
            # 현재 값을 그대로 다시 넣는다 — 허용 여부만 재고 상태는 바꾸지 않는다.
            tools.set_component_field("scout", field, row["current"])
        except ValueError:
            continue
        accepted.add(field)
    assert accepted == listed - _DEDICATED_TOOL_FIELDS


def test_rejection_offers_only_fields_that_can_actually_be_set(tools):
    """거절이 내놓는 "사용 가능" 선택지는 전부 실제로 설정된다(원칙 5).

    예전에는 `list_component_fields`를 그대로 흘려서 같은 호출이 거절하는
    FIXED 행(`disable_model_invocation` 등)과 전용 도구 필드까지 선택지로
    제시했다 — 이유는 맞고 선택지가 틀린 거절이다.
    """
    tools.create_skill("xfer", kind="transfer")
    with pytest.raises(ValueError) as excinfo:
        tools.set_component_field("xfer", "nope", 1)
    offered = [
        part.strip()
        for part in str(excinfo.value).split("사용 가능:")[-1].split(",")
        if part.strip()
    ]
    assert offered
    current = {
        f["field"]: f["current"] for f in tools.list_component_fields("xfer")["fields"]
    }
    for field in offered:
        tools.set_component_field("xfer", field, current[field])


# --- P5: 배치 거절 문구는 배치 역할에서 파생 -------------------------------


def test_placement_rejection_names_the_role_not_a_hand_written_kind_list(tools):
    from daedalus.mcp.tools.placement_prose import kinds_with_placement
    from daedalus.model.plugin.roles import PlacementRole

    tools.create_agent("helper", kind="fork_agent")
    with pytest.raises(ValueError) as excinfo:
        tools.place_component("helper", x=0, y=0)
    message = str(excinfo.value)
    assert "배치되지 않는 종류" in message
    for kind in kinds_with_placement(PlacementRole.NONE):
        assert kind in message


def test_edge_placement_rejection_says_it_lives_on_a_transition(tools):
    tools.create_skill("xfer", kind="transfer")
    with pytest.raises(ValueError, match="전이"):
        tools.place_component("xfer", x=0, y=0)


def test_every_placement_role_has_prose():
    """역할이 늘면 문구도 따라온다 — 빠진 역할은 KeyError로 시끄럽게 실패한다."""
    from daedalus.mcp.tools.placement_prose import placement_role_prose
    from daedalus.model.plugin.roles import PlacementRole

    for role in PlacementRole:
        assert placement_role_prose(role)


def test_creation_rejection_for_non_canvas_kinds_is_derived(tools):
    """생성+배치 경로도 같은 선언을 읽는다(props ↔ canvas 한 문장)."""
    with pytest.raises(ValueError, match="배치되지 않습니다"):
        tools.create_skill("bg", kind="declarative", x=1, y=2)


# --- `_component_kind` 퇴역 ------------------------------------------------


def test_component_kind_wrapper_is_gone():
    """`str(comp.kind)` 한 줄 래퍼는 퇴역했다 — `kind`는 모든 컴포넌트의 property다."""
    from daedalus.mcp.tools import DaedalusTools

    assert not hasattr(DaedalusTools, "_component_kind")
