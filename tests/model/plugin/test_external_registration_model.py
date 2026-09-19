"""등록 표면이 묻는 **모델 판정** (WP-C) — 셋 다 실체가 하나여야 한다.

- `registered_external_component` / `unregistered_plugin_agents`:
  "이 외부 에이전트를 이미 등록했는가". 레지스트리 🔌 탭 하단 목록,
  등록 액션의 역할 고정 거절, MCP `registered_as`가 같은 답을 말해야 한다.
- `skill_ref_users`: "이 외부 스킬 참조를 누가 쓰는가". 🧷 탭의 ✔,
  MCP `used_by`, 카탈로그 창의 ✔이 같은 답을 말해야 한다.
- `plugin.names`: 외부 정본 → 컴포넌트 이름. 마이그레이션과 등록이 같은 이름을
  지어야 한다(경로에 따라 다른 이름으로 태어나면 안 된다).

파일시스템을 읽는 것은 `scan_catalog` 하나이므로 그 결과를 **주입**해 테스트가
폴더 등록에 매이지 않게 한다(유도 함수의 `catalog` 인자 — GUI가 캐시를 넘기는
것과 같은 경로다).
"""
from __future__ import annotations

import pytest

from daedalus.model.plugin.wrap_catalog import (
    CataloguedAgent,
    CataloguedPlugin,
    MarketplaceFolder,
    registered_external_component,
    skill_ref_users,
    unregistered_plugin_agents,
    used_plugin_agents,
)
from daedalus.model.project import PluginProject


def _catalog(*agent_names: str, plugin="hookify", marketplace="mkt"):
    plugin_obj = CataloguedPlugin(
        name=plugin,
        path="/nowhere",
        marketplace=marketplace,
        agents=[
            CataloguedAgent(
                name=n, description=f"{n} does things.",
                agent_type=f"{plugin}:{n}",
            )
            for n in agent_names
        ],
    )
    return [(MarketplaceFolder(path="/nowhere", marketplace=marketplace),
             [plugin_obj])]


def _project_with(kind: str, name: str, source: str) -> PluginProject:
    from daedalus.model.plugin.kinds import spec_by_config_kind

    project = PluginProject(name="p")
    project.external_plugins.append("hookify@mkt")
    component = spec_by_config_kind(kind).component_cls.new(
        name, "", fsm_factory=lambda _n: None, source=source,
    )
    project.agents.append(component)
    return project


# ── 등록 판정 ────────────────────────────────────────────────────────────

def test_unregistered_list_drops_what_is_already_registered():
    project = _project_with("external_agent", "doctor", "hookify@mkt:doctor")
    catalog = _catalog("doctor", "auditor")
    assert [a.agent_type for a in used_plugin_agents(project, catalog)] == [
        "hookify:auditor", "hookify:doctor",
    ]
    assert [
        a.agent_type for a in unregistered_plugin_agents(project, catalog)
    ] == ["hookify:auditor"]


def test_registration_match_ignores_marketplace_notation():
    """``hookify:x``와 ``hookify@mkt:x``를 **다르게 세지 않는다**.

    카탈로그는 `agent_type`을 bare로 내고(CC가 찾는 이름) 사용자가 손으로 적은
    `source`는 마켓을 달고 있을 수 있다. 원문 정확 일치로 세면 이미 등록한
    에이전트가 미등록 목록에 또 나온다.
    """
    project = _project_with("external_fork_agent", "doctor", "hookify@mkt:doctor")
    found = registered_external_component(project, "hookify:doctor")
    assert found is not None and found.name == "doctor"
    assert unregistered_plugin_agents(project, _catalog("doctor")) == []


def test_registration_match_needs_the_same_ref_name():
    project = _project_with("external_agent", "doctor", "hookify:doctor")
    assert registered_external_component(project, "hookify:auditor") is None
    assert registered_external_component(project, "") is None


def test_two_markets_with_the_same_plugin_name_are_different_targets():
    project = _project_with("external_agent", "doctor", "hookify@mkt1:doctor")
    assert registered_external_component(project, "hookify@mkt2:doctor") is None


# ── 스킬 참조 사용처 ─────────────────────────────────────────────────────

def test_skill_ref_users_normalizes_and_sorts():
    from daedalus.model.plugin.kinds import spec_by_config_kind

    project = PluginProject(name="p")
    for name, refs in (
        ("zulu", ["hookify:review"]),
        ("alpha", ["hookify@mkt:review", "local-skill"]),
    ):
        agent = spec_by_config_kind("fork_agent").component_cls.new(
            name, "", fsm_factory=lambda _n: None,
        )
        agent.config.skills = refs
        project.agents.append(agent)
    # `@마켓`이 붙은 참조도 **같은 스킬**을 쓰는 것으로 센다(그 표기 자체는
    # `external_skill_ref_marketplace` 경고가 짚는다). 프로젝트 스킬 이름은
    # 외부 참조가 아니라 키에 들지 않는다.
    assert skill_ref_users(project) == {"hookify:review": ["alpha", "zulu"]}


def test_skill_ref_users_is_empty_without_external_refs():
    assert skill_ref_users(PluginProject(name="p")) == {}


# ── 이름 짓기 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hookify:Hook_Doctor", "hookify-hook-doctor"),
        ("  Review Pack  ", "review-pack"),
        ("--a--b--", "a-b"),
    ],
)
def test_component_name_slug_matches_the_name_convention(text, expected):
    from daedalus.model.plugin.names import component_name_slug

    assert component_name_slug(text) == expected


def test_external_ref_name_candidates_prefer_the_bare_ref_name():
    from daedalus.model.plugin.names import external_ref_name_candidates

    assert external_ref_name_candidates("hookify@mkt:Hook_Doctor") == (
        "hook-doctor", "hookify-hook-doctor",
    )
    # 콜론이 없으면 후보는 하나다(형식이 깨진 정본 — 지어내지 않는다).
    assert external_ref_name_candidates("hookify") == ("hookify",)


def test_free_component_name_falls_back_to_a_suffix():
    from daedalus.model.plugin.names import free_component_name

    assert free_component_name({"a"}, "a", "b") == "b"
    assert free_component_name({"a", "b"}, "a", "b") == "a-2"
    assert free_component_name({"a", "b", "a-2"}, "a", "b") == "a-3"
