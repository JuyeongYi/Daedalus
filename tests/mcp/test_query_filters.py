"""조회 필터·신호 (Q5·Q6).

- `validate_project(severity=, component=)`: 컴포넌트 하나를 손보는 중에 전체
  결과를 받아 눈으로 골라내던 낭비를 끊는다. 컴포넌트 판정은 캔버스 우클릭
  "관련 경고 보기"와 **같은 실체**(`view/actions/warnings.findings_for`)라
  그래프 placement 노드가 subject인 규칙도 잡힌다.
- `get_project`의 `workspace_docs`: 작업 폴더 문서(WP-WD)가 있다는 **신호**만.
  신호가 없으면 그 표면의 존재 자체를 몰라 조용히 잊힌다.
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject


def _skill(name: str) -> ProceduralSkill:
    s = SimpleState(name="Start")
    fsm = StateMachine(name=f"{name}_fsm", initial_state=s, states=[s], final_states=[s])
    return ProceduralSkill(fsm=fsm, name=name, description="설명")


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    project = PluginProject(name="p", skills=[_skill("init"), _skill("wrap")])
    win = MainWindow()
    win.set_project(project)
    yield win
    win.close()


@pytest.fixture
def tools(window):
    from daedalus.mcp.tools import DaedalusTools

    return DaedalusTools(window)


# --- Q5: validate_project 필터 ---


def test_validate_unfiltered_reports_totals(tools):
    result = tools.validate_project()
    assert result["filtered"] is False
    assert result["error_count"] == result["total_error_count"]
    assert result["warning_count"] == result["total_warning_count"]


def test_validate_severity_filter(tools):
    tools.create_skill("Bad Name")  # invalid_component_name 경고
    warnings_only = tools.validate_project(severity="warning")
    assert warnings_only["filtered"] is True
    assert warnings_only["issues"]
    assert all(i["severity"] == "warning" for i in warnings_only["issues"])

    errors_only = tools.validate_project(severity="error")
    assert all(i["severity"] == "error" for i in errors_only["issues"])


def test_validate_severity_keeps_project_totals(tools):
    tools.create_skill("Bad Name")
    result = tools.validate_project(severity="error")
    assert result["total_warning_count"] >= 1
    assert result["warning_count"] == 0


def test_validate_rejects_unknown_severity(tools):
    with pytest.raises(ValueError, match="severity"):
        tools.validate_project(severity="nope")


def test_validate_component_filter_narrows(tools):
    tools.create_skill("Bad Name")
    result = tools.validate_project(component="Bad Name")
    assert result["filtered"] is True
    assert result["issues"]
    assert all("Bad Name" in i["message"] for i in result["issues"])

    other = tools.validate_project(component="init")
    assert not any("Bad Name" in i["message"] for i in other["issues"])


def test_validate_component_filter_sees_placement_findings(tools):
    """placement 노드가 subject인 규칙(mid_chain_user_invocable)도 잡힌다."""
    tools.place_component("init", 0, 0)
    tools.place_component("wrap", 200, 0)
    tools.connect_states("init", "wrap")
    tools.set_entry_preset("wrap", "entry")  # 중간 노드인데 user-invocable

    result = tools.validate_project(component="wrap")
    assert "mid_chain_user_invocable" in {i["rule"] for i in result["issues"]}


def test_validate_component_and_severity_combine(tools):
    tools.place_component("init", 0, 0)
    tools.place_component("wrap", 200, 0)
    tools.connect_states("init", "wrap")
    tools.set_entry_preset("wrap", "entry")

    result = tools.validate_project(component="wrap", severity="error")
    assert result["issues"] == []
    assert result["total_warning_count"] >= 1


def test_validate_component_rejects_unknown_name(tools):
    with pytest.raises(ValueError, match="찾을 수 없습니다"):
        tools.validate_project(component="nope")


# --- Q6: workspace_docs 신호 ---


def test_workspace_docs_signal_empty_by_default(tools):
    meta = tools.get_project(sections=["meta"])
    assert meta["workspace_docs"] == {"claude_md": False, "rules": 0}


def test_workspace_docs_signal_counts_rules(tools):
    tools.create_rule("style")
    tools.create_rule("naming")
    meta = tools.get_project(sections=["meta"])
    assert meta["workspace_docs"]["rules"] == 2


def test_workspace_docs_signal_ignores_empty_claude_md(tools):
    tools.set_claude_md("")
    assert tools.get_project(sections=["meta"])["workspace_docs"]["claude_md"] is False
    tools.set_claude_md("# 규칙\n\n본문")
    assert tools.get_project(sections=["meta"])["workspace_docs"]["claude_md"] is True


def test_workspace_docs_signal_present_in_full_project(tools):
    assert "workspace_docs" in tools.get_project()
