"""프로젝트 열기/저장 (open_project / save_project / list_recent_projects).

MCP로 다른 프로젝트를 열려면 앱을 재시작해야 했다. 그런데 여는 순간 편집 중인
내용이 사라지므로, 저장을 **여는 절차 안에** 넣는다 — 저장할 수 없으면 열지
않는다. 그것이 이 파일이 고정하는 계약이다.
"""
from __future__ import annotations

import json

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.model.serialize import serialize_project


def _project(name: str = "p") -> PluginProject:
    s1 = SimpleState(name="Start")
    fsm = StateMachine(name="f", initial_state=s1, states=[s1], final_states=[s1])
    return PluginProject(
        name=name, skills=[ProceduralSkill(fsm=fsm, name="init", description="초기화")]
    )


def _write_project(path, project: PluginProject) -> str:
    path.write_text(
        json.dumps(serialize_project(project), ensure_ascii=False), encoding="utf-8"
    )
    return str(path)


@pytest.fixture(autouse=True)
def isolated_recent(tmp_path, monkeypatch):
    """최근 목록은 홈 디렉토리를 건드리므로 격리한다."""
    from daedalus.view import recent

    monkeypatch.setattr(recent, "RECENT_PATH", tmp_path / "recent.json")


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    win = MainWindow()
    win.set_project(_project())
    yield win
    win.close()


@pytest.fixture
def tools(window):
    from daedalus.mcp.tools import DaedalusTools

    return DaedalusTools(window)


# --- save_project ---


def test_saves_to_given_path(tools, window, tmp_path):
    target = tmp_path / "out.daedalus.json"
    out = tools.save_project(str(target))
    assert target.exists()
    assert out["saved_path"] == str(target)
    assert window._current_path == str(target)


def test_saves_to_current_path_when_omitted(tools, window, tmp_path):
    target = tmp_path / "out.daedalus.json"
    tools.save_project(str(target))
    tools.set_component_description("init", "바뀐 설명")
    tools.save_project()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert any(s["description"] == "바뀐 설명" for s in data["skills"])


def test_save_without_path_on_unsaved_project_is_rejected(tools):
    with pytest.raises(ValueError, match="저장 경로"):
        tools.save_project()


# --- open_project: 저장이 절차 안에 있다 ---


def test_saves_current_before_opening(tools, window, tmp_path):
    here = tmp_path / "here.daedalus.json"
    tools.save_project(str(here))
    tools.set_component_description("init", "저장 안 한 변경")

    other = _write_project(tmp_path / "other.daedalus.json", _project("other"))
    out = tools.open_project(other)

    assert out["opened"] == other
    assert out["saved_before_open"] == str(here)
    # 열기 전 변경이 디스크에 남아 있다
    data = json.loads(here.read_text(encoding="utf-8"))
    assert any(s["description"] == "저장 안 한 변경" for s in data["skills"])


def test_opened_project_replaces_session(tools, window, tmp_path):
    tools.save_project(str(tmp_path / "here.daedalus.json"))
    other = _write_project(tmp_path / "other.daedalus.json", _project("other"))
    tools.open_project(other)

    assert window._project.name == "other"
    assert tools.get_project()["name"] == "other"
    assert window._current_path == other


def test_unsaved_project_without_path_refuses_to_open(tools, window, tmp_path):
    """저장할 곳을 모르면 열지 않는다 — 열었다면 내용이 사라졌을 것이다."""
    other = _write_project(tmp_path / "other.daedalus.json", _project("other"))
    with pytest.raises(ValueError, match="save_current_as"):
        tools.open_project(other)
    assert window._project.name == "p"  # 그대로 남아 있다


def test_save_current_as_gives_the_missing_path(tools, window, tmp_path):
    rescue = tmp_path / "rescue.daedalus.json"
    other = _write_project(tmp_path / "other.daedalus.json", _project("other"))

    out = tools.open_project(other, save_current_as=str(rescue))

    assert rescue.exists()
    assert out["saved_before_open"] == str(rescue)
    assert window._project.name == "other"


def test_discard_is_explicit(tools, window, tmp_path):
    other = _write_project(tmp_path / "other.daedalus.json", _project("other"))
    out = tools.open_project(other, save_current=False)
    assert out["discarded_unsaved"] is True
    assert out["saved_before_open"] is None
    assert window._project.name == "other"


def test_empty_project_opens_without_saving(tools, window, tmp_path):
    """잃을 것이 없으면 저장을 요구하지 않는다."""
    window.set_project(PluginProject(name="empty"))
    other = _write_project(tmp_path / "other.daedalus.json", _project("other"))

    out = tools.open_project(other)

    assert out["saved_before_open"] is None
    assert out["discarded_unsaved"] is False
    assert window._project.name == "other"


def test_missing_file_is_rejected_before_touching_session(tools, window, tmp_path):
    with pytest.raises(ValueError, match="없습니다"):
        tools.open_project(str(tmp_path / "nope.json"))
    assert window._project.name == "p"


def test_broken_file_leaves_no_project_half_loaded(tools, window, tmp_path):
    broken = tmp_path / "broken.daedalus.json"
    broken.write_text("{ not json", encoding="utf-8")
    tools.save_project(str(tmp_path / "here.daedalus.json"))

    with pytest.raises(RuntimeError, match="열지 못했습니다"):
        tools.open_project(str(broken))
    assert window._project.name == "p"


def test_save_failure_blocks_the_open(tools, window, tmp_path, monkeypatch):
    """저장이 실패했는데 열면 그 순간 변경이 사라진다 — 열지 않는다."""
    tools.save_project(str(tmp_path / "here.daedalus.json"))
    other = _write_project(tmp_path / "other.daedalus.json", _project("other"))
    monkeypatch.setattr(type(window), "_save_to_path", lambda self, path: False)

    with pytest.raises(RuntimeError, match="저장하지 못해"):
        tools.open_project(other)
    assert window._project.name == "p"


# --- list_recent_projects ---


def test_recent_lists_saved_paths(tools, window, tmp_path):
    first = tmp_path / "first.daedalus.json"
    tools.save_project(str(first))
    out = tools.list_recent_projects()
    assert out["current"] == str(first)
    assert str(first) in [entry["path"] for entry in out["recent"]]
    # 격리가 실제로 걸렸는지 — 안 걸렸다면 사용자의 홈 목록을 오염시킨 것이다
    assert (tmp_path / "recent.json").exists()


def test_recent_survives_open(tools, tmp_path):
    tools.save_project(str(tmp_path / "here.daedalus.json"))
    other = _write_project(tmp_path / "other.daedalus.json", _project("other"))
    tools.open_project(other)

    paths = [entry["path"] for entry in tools.list_recent_projects()["recent"]]
    assert other in paths


# --- 도구 노출 ---


def test_tools_are_exposed():
    from daedalus.mcp.service import TOOL_NAMES

    for name in ("open_project", "save_project", "list_recent_projects"):
        assert name in TOOL_NAMES
