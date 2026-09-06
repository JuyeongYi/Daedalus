"""MCP `compile_check` — 파일을 쓰지 않는 컴파일 예행 (G3).

컴파일러 emit 경고 7종은 `validate_project`에 나오지 않아, MCP로만 저작하면
GUI Ctrl+B를 누르기 전까지 영영 보이지 않았다. 이 도구가 그 갭을 메운다.

게이트: ① 디스크 불변 ② Ctrl+B 컴파일과 **같은 주입**(동봉 파일 루트·전역 훅·
서버 정의)이라 같은 경고가 나올 것.
"""
from __future__ import annotations

import json

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.config import AgentConfig, ProceduralSkillConfig
from daedalus.model.plugin.enums import BuildTarget, ModelType
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.plugin.workspace_doc import WorkspaceDoc
from daedalus.model.project import PluginProject


def _skill(name: str = "alpha", body: str = "# Do\n\nwork") -> ProceduralSkill:
    s = SimpleState(name="s")
    fsm = StateMachine(name=name, initial_state=s, states=[s], final_states=[s])
    return ProceduralSkill(
        fsm=fsm, name=name, description="d", body=body,
        config=ProceduralSkillConfig(model=ModelType.SONNET),
        transfer_on=[EventDef("done")],
    )


def _snapshot(root) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    win = MainWindow()
    yield win
    win.close()


def _tools(window):
    from daedalus.mcp.tools import DaedalusTools

    return DaedalusTools(window)


def test_registered_in_tool_names():
    from daedalus.mcp.service import TOOL_NAMES

    assert "compile_check" in TOOL_NAMES


def test_reports_ok_and_planned_files(window, tmp_path):
    window.set_project(PluginProject(name="p", skills=[_skill()]))
    out = tmp_path / "out"

    result = _tools(window).compile_check(str(out))

    assert result["ok"] is True
    assert result["error_count"] == 0
    assert "skills/alpha/SKILL.md" in result["planned_files"]
    assert ".claude-plugin/plugin.json" in result["planned_files"]
    assert result["out_dir"] == str(out)
    assert result["build_target"] == "marketplace"
    # 파일은 하나도 만들어지지 않는다 — 이것이 이 도구의 전부다.
    assert not out.exists()


def test_out_dir_optional(window, tmp_path):
    window.set_project(PluginProject(name="p", skills=[_skill()]))

    result = _tools(window).compile_check()

    assert result["ok"] is True
    assert result["out_dir"] is None
    assert "skills/alpha/SKILL.md" in result["planned_files"]


def test_surfaces_gate_errors(window, tmp_path):
    window.set_project(PluginProject(name="p", skills=[_skill(name="Bad Name")]))

    result = _tools(window).compile_check(str(tmp_path / "out"))

    assert result["ok"] is False
    rules = {i["rule"] for i in result["issues"]}
    assert "compile_invalid_component_name" in rules
    assert result["planned_files"] == []
    assert result["skipped"]


def test_surfaces_compiler_only_warnings(window, tmp_path):
    """`validate_project`에는 없고 컴파일에만 나오던 경고를 보여준다."""
    project_dir = tmp_path / "proj"
    (project_dir / "files").mkdir(parents=True)
    project = PluginProject(
        name="p", skills=[_skill(body="see ${ROOT}/files/gone.txt")],
    )
    window.set_project(project)
    window._current_path = str(project_dir / ".daedalus.json")

    tools = _tools(window)
    assert "dangling_file_ref" not in {
        i["rule"] for i in tools.validate_project()["issues"]
    }
    result = tools.compile_check(str(tmp_path / "out"))
    assert "dangling_file_ref" in {i["rule"] for i in result["issues"]}


def test_local_merge_is_read_only(window, tmp_path):
    """LOCAL 병합류는 읽기만 — 대상 작업 폴더가 한 바이트도 바뀌지 않는다."""
    work = tmp_path / "work"
    (work / ".claude").mkdir(parents=True)
    (work / ".claude" / "settings.local.json").write_text(
        json.dumps({"env": {"A": "1"}}), encoding="utf-8",
    )
    (work / ".claude" / "CLAUDE.md").write_text("# Team\n\nkeep\n", encoding="utf-8")
    (work / ".mcp.json").write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")

    project = PluginProject(name="p", skills=[_skill()])
    project.build_target = BuildTarget.LOCAL
    project.claude_md = WorkspaceDoc(name="p", body="Follow the plan.")
    window.set_project(project)
    before = _snapshot(work)

    result = _tools(window).compile_check(str(work))

    assert result["ok"] is True
    assert _snapshot(work) == before


def test_missing_mcp_server_def_warning(window, tmp_path):
    from daedalus.model.plugin.agent import AgentDefinition

    agent = AgentDefinition(
        fsm=StateMachine(
            name="a_fsm",
            initial_state=(entry := SimpleState(name="e")),
            states=[entry],
            final_states=[entry],
        ),
        name="worker", description="d",
        config=AgentConfig(model=ModelType.SONNET, tools=["mcp__github__search"]),
        body="do", transfer_on=[EventDef("done")],
    )
    project = PluginProject(name="p", skills=[_skill()], agents=[agent])
    project.build_target = BuildTarget.LOCAL
    window.set_project(project)

    result = _tools(window).compile_check(str(tmp_path / "work"))

    issues = {(i["rule"], i["source"]) for i in result["issues"]}
    assert ("missing_mcp_server_def", "github") in issues


def test_reports_token_summary(window, tmp_path):
    window.set_project(PluginProject(name="p", skills=[_skill()]))

    tokens = _tools(window).compile_check(str(tmp_path / "out"))["tokens"]

    assert tokens["total_tokens"] > 0
    assert tokens["total_chars"] > 0
    assert tokens["over_threshold"] == []
    assert tokens["notice"] is None


def test_compile_inputs_shape(window, tmp_path):
    """동봉 파일 루트는 저장 폴더 기준 — 미저장이면 None(그 스캔 생략)."""
    window.set_project(PluginProject(name="p", skills=[_skill()]))
    assert window.compile_inputs()["files_dir"] is None

    window._current_path = str(tmp_path / "proj" / ".daedalus.json")
    inputs = window.compile_inputs()

    assert inputs["files_dir"] == tmp_path / "proj" / "files"
    assert inputs["skill_files_dir"] == tmp_path / "proj" / "skill-files"
    assert "daedalus" in inputs["extra_server_defs"]
    assert inputs["resolved_hooks"] == window.resolved_hooks()


def test_ctrl_b_and_compile_check_share_inputs(window, tmp_path, monkeypatch):
    """Ctrl+B 컴파일도 같은 `compile_inputs`를 쓴다 — 한쪽만 고치면 결과가 갈린다."""
    window.set_project(PluginProject(name="p", skills=[_skill()]))
    calls: list[str] = []
    real = type(window._compile_actions).compile_inputs
    monkeypatch.setattr(
        type(window._compile_actions), "compile_inputs",
        lambda self: (calls.append("x"), real(self))[1],
    )
    monkeypatch.setattr(
        "daedalus.view.app.QFileDialog.getExistingDirectory",
        lambda *a, **k: str(tmp_path / "out"),
    )

    window._compile_project_dialog()
    _tools(window).compile_check(str(tmp_path / "check"))

    assert len(calls) == 2
