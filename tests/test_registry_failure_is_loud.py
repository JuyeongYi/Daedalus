# tests/test_registry_failure_is_loud.py
"""레지스트리 부재는 **시끄럽다** (REFACTOR_SPEC §8, WP-3).

표를 하나로 모으면 새 위험이 생긴다: 그 한 표에서 빠진 종류는 **모든** 계층에서
동시에 사라진다. 사라지는 방식이 조용하면(빈 폼·None 반환·건너뜀) 어디가 잘못
됐는지 아무도 말해 주지 않는다 — 그게 이 리팩토링이 없애려는 바로 그 실패
양식이다(👻, 원칙 5).

그래서 항목 하나를 monkeypatch로 지우고 **예외가 나는지**, 그리고 그 메시지에
**빠진 종류 이름이 실려 있는지**를 본다. 이름이 없으면 사용자는 "알 수 없는
종류"라는 말만 보고 어느 종류인지 모른다.

`EMITTERS`(WP-6)와 `KIND_UI`(WP-7)도 같은 방식으로 지켜진다.
"""
from __future__ import annotations

import pytest

from daedalus.model.plugin import kinds as kinds_mod
from daedalus.model.plugin.kinds import (
    bucket_of,
    spec_by_config_kind,
    spec_by_kind,
)
from daedalus.model.plugin.roles import Bucket
from daedalus.model.plugin.skill import ProceduralSkill

_VICTIM_KIND = "procedural_skill"
_VICTIM_CONFIG_KIND = "procedural"


@pytest.fixture
def registry_without_procedural(monkeypatch):
    """`procedural_skill` 행만 빠진 레지스트리 — 다른 행은 그대로다."""
    thinned = {k: v for k, v in kinds_mod.KIND_REGISTRY.items() if k != _VICTIM_KIND}
    monkeypatch.setattr(kinds_mod, "KIND_REGISTRY", thinned)
    monkeypatch.setattr(
        kinds_mod,
        "CONFIG_KIND_INDEX",
        {s.config_kind: s for s in thinned.values()},
    )
    return thinned


def test_kind_lookup_names_the_missing_kind(registry_without_procedural):
    with pytest.raises(ValueError, match=_VICTIM_KIND):
        spec_by_kind(_VICTIM_KIND, bucket=Bucket.SKILLS, subject="스킬 'x'")


def test_kind_lookup_says_which_item_and_what_is_available(
    registry_without_procedural,
):
    """거절은 **이유 + 선택지**다 — 어느 항목인지와 고를 수 있는 값을 함께 말한다."""
    with pytest.raises(ValueError) as excinfo:
        spec_by_kind(_VICTIM_KIND, bucket=Bucket.SKILLS, subject="스킬 'alpha'")
    message = str(excinfo.value)
    assert "스킬 'alpha'" in message
    assert "사용 가능" in message and "transfer_skill" in message


def test_config_kind_lookup_names_the_missing_kind(registry_without_procedural):
    with pytest.raises(ValueError, match=_VICTIM_CONFIG_KIND):
        spec_by_config_kind(_VICTIM_CONFIG_KIND)


def test_bucket_lookup_fails_loudly_for_a_removed_kind(registry_without_procedural):
    """버킷 판정도 레지스트리를 탄다 — 빠진 종류가 `skills`로 조용히 떨어지지 않는다."""

    class _Project:
        skills: list = []
        agents: list = []

    skill = ProceduralSkill.__new__(ProceduralSkill)
    with pytest.raises(ValueError, match=_VICTIM_KIND):
        bucket_of(_Project(), skill)


def test_bucket_lookup_refuses_non_components():
    """컴포넌트가 아닌 값은 `TypeError`다 — 관용하면 목록이 조용히 오염된다."""

    class _Project:
        skills: list = []
        agents: list = []

    with pytest.raises(TypeError, match="컴포넌트"):
        bucket_of(_Project(), object())


def test_wrong_bucket_is_refused_even_when_the_kind_exists():
    """스킬 목록에 적힌 `"agent"`는 **에이전트를 만들지 않는다**.

    버킷을 안 보면 손편집된 파일 하나가 스킬 자리에 에이전트를 앉히고, 그
    어긋남은 저장·산출까지 조용히 따라간다.
    """
    with pytest.raises(ValueError, match="agent"):
        spec_by_kind("agent", bucket=Bucket.SKILLS, subject="스킬 'x'")


# ── 뷰 표면 (WP-7) ───────────────────────────────────────────────────────

@pytest.fixture
def kind_ui_without_procedural(monkeypatch):
    """`procedural_skill`의 **뷰 행**만 빠진 표 — 다른 행은 그대로다."""
    from daedalus.view import kind_ui as kind_ui_mod

    thinned = {
        k: v for k, v in kind_ui_mod.KIND_UI.items() if k != _VICTIM_KIND
    }
    monkeypatch.setattr(kind_ui_mod, "KIND_UI", thinned)
    return thinned


def test_palette_build_names_the_kind_without_a_ui_row(
    qapp, kind_ui_without_procedural
):
    """UI 행이 빠지면 팔레트 구축이 **그 종류 이름을 찍고** 죽는다.

    예전에는 아이콘 없는 행·회색 기본 노드로 **조용히** 그려졌다 — 어느 종류가
    빠졌는지 화면만 봐서는 알 수 없었다(👻, 원칙 5).
    """
    from daedalus.view.panels.registry_panel import RegistryPanel

    with pytest.raises(ValueError, match=_VICTIM_KIND):
        RegistryPanel()


def test_component_lookup_names_the_kind_without_a_ui_row(
    qapp, kind_ui_without_procedural
):
    """인스턴스 조회도 같은 거절이다 — 캔버스 노드·편집 탭이 함께 부른다."""
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.fsm.state import SimpleState
    from daedalus.view.kind_ui import ui_for

    state = SimpleState(name="s")
    skill = ProceduralSkill(
        fsm=StateMachine(name="f", states=[state], initial_state=state),
        name="x", description="d",
    )
    with pytest.raises(ValueError, match=_VICTIM_KIND):
        ui_for(skill)
