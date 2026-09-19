"""외부 fork 에이전트의 MCP 표면 (WP-EX/WP-A) — 패리티 원칙 2.

GUI에서 할 수 있는 등록·지목·조회는 MCP로도 되어야 한다. 새 종류가 생겼을 때
**어휘는 레지스트리 파생이라 자동**이지만, 그 종류만의 생성 인자(`source`)와
거절 규칙은 여기서 못 박는다 — 조용히 무시되면 사용자는 값을 넣고도 아무 일도
일어나지 않는 것을 나중에야 안다(원칙 5).
"""
from __future__ import annotations

import pytest

from daedalus.model.project import PluginProject

_SOURCE = "review-pack@mkt:critic"


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


# ── 생성 ─────────────────────────────────────────────────────────────────

def test_create_agent_accepts_the_new_kind_and_seeds_the_source(tools):
    out = tools.create_agent(
        "critic", kind="external_fork_agent", source=_SOURCE,
    )
    assert out == {
        "created": "critic", "kind": "external_fork_agent",
        "placed": False, "source": _SOURCE,
    }
    agent = tools._project.agents[0]
    assert agent.kind == "external_fork_agent"
    assert agent.config.source == _SOURCE
    # 등록은 편집이다 — 한 번의 undo로 되돌아간다.
    tools.undo()
    assert tools._project.agents == []


def test_create_agent_source_also_works_for_the_node_role(tools):
    out = tools.create_agent("reviewer", kind="external_agent", source=_SOURCE)
    assert out["source"] == _SOURCE
    assert tools._project.agents[0].config.source == _SOURCE


@pytest.mark.parametrize("kind", ["agent", "fork_agent"])
def test_source_is_rejected_for_kinds_that_cannot_hold_it(tools, kind):
    """받아 놓고 버리지 않는다 — 어느 종류가 이 인자를 받는지까지 말한다."""
    with pytest.raises(ValueError) as excinfo:
        tools.create_agent("x", kind=kind, source=_SOURCE)
    message = str(excinfo.value)
    assert "source" in message
    assert "external_agent" in message and "external_fork_agent" in message
    assert tools._project.agents == []


def test_the_fork_base_role_is_not_placeable(tools):
    """배치되지 않는 종류에 좌표를 주면 거절한다(그래프 노드 역할과 갈리는 자리)."""
    with pytest.raises(ValueError, match="배치되지 않습니다"):
        tools.create_agent(
            "critic", kind="external_fork_agent", source=_SOURCE, x=1.0, y=2.0,
        )


# ── 지목 ─────────────────────────────────────────────────────────────────

def test_fork_skill_can_target_a_registered_external_fork_agent(tools):
    tools.create_agent("critic", kind="external_fork_agent", source=_SOURCE)
    out = tools.create_skill("scout", kind="sync_fork", fork_agent="critic")
    assert out["fork_agent"] == "critic"

    tools.create_skill("audit", kind="async_fork")
    tools.set_component_field("audit", "agent", "critic")
    assert tools._project.skills[1].config.agent == "critic"


def test_a_raw_plugin_reference_is_rejected_with_the_registration_path(tools):
    """등록하지 않은 `플러그인:이름` 원문은 거절하고 **등록하는 법**을 말한다."""
    with pytest.raises(ValueError) as excinfo:
        tools.create_skill("scout", kind="sync_fork", fork_agent=_SOURCE)
    assert "external_fork_agent" in str(excinfo.value)
    assert tools._project.skills == []


# ── 조회 ─────────────────────────────────────────────────────────────────

def test_get_component_reports_who_forks_into_it(tools):
    """`used_by_fork_skills`는 `IS_FORK_BASE` 선언에서 파생된다 — 자동 합류."""
    tools.create_agent("critic", kind="external_fork_agent", source=_SOURCE)
    tools.create_skill("scout", kind="sync_fork", fork_agent="critic")
    info = tools.get_component("critic")
    assert info["kind"] == "external_fork_agent"
    assert info["used_by_fork_skills"] == ["scout"]
    assert info["config"]["source"] == _SOURCE


def test_the_only_settable_field_is_source(tools):
    """매트릭스 파생 — 산출 파일이 없는 종류는 프론트매터 필드를 갖지 않는다.

    `name`/`description`은 전용 도구(`rename_component`/
    `set_component_description`)가 맡으므로 이 목록에 오르지 않는다 —
    남는 것은 우리가 소유하는 값 하나뿐이다.
    """
    tools.create_agent("critic", kind="external_fork_agent", source=_SOURCE)
    fields = {f["field"] for f in tools.list_component_fields("critic")["fields"]}
    assert fields == {"source"}


def test_ports_are_refused_for_the_fork_base_role(tools):
    """출력 포트·호출 포트는 **단일 배치되는 노드**만 갖는다(같은 술어)."""
    tools.create_agent("critic", kind="external_fork_agent", source=_SOURCE)
    with pytest.raises(ValueError, match="출력 포트"):
        tools.set_transfer_on("critic", [{"name": "done"}])
    with pytest.raises(ValueError, match="호출 포트"):
        tools.add_agent_call("critic", "ask")


def test_body_writes_are_rejected(tools):
    """본문 정본은 그 플러그인의 파일이다 — GUI 잠금과 같은 선언을 본다."""
    tools.create_agent("critic", kind="external_fork_agent", source=_SOURCE)
    with pytest.raises(ValueError):
        tools.set_component_body("critic", "# nope")
