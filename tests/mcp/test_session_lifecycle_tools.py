"""새 프로젝트·패키지 가져오기·생성+배치 (G11·G12·G14+S1·G15).

MCP 패리티 원칙 — GUI에서 되는 것은 MCP로도 돼야 한다. 여기 고정하는 계약:

- `new_project`는 Ctrl+N 통합 다이얼로그와 **동형**이고(출발점 + 빌드 타깃,
  고른 타깃이 템플릿 저장 타깃을 이긴다) `open_project`와 **같은 저장 게이트**를
  지난다 — 저장할 수 없으면 만들지 않는다(미저장 소실 사고의 그 게이트).
- `create_skill`/`create_agent`의 x/y는 생성+배치를 **1 undo 단위**로 묶는다.
- `set_transition(create_transfer=...)`도 생성+할당이 1 undo 단위다.
"""
from __future__ import annotations

import json

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.model.serialize import serialize_project


def _project(name: str = "p") -> PluginProject:
    s1 = SimpleState(name="Start")
    fsm = StateMachine(name="f", initial_state=s1, states=[s1], final_states=[s1])
    return PluginProject(
        name=name, skills=[ProceduralSkill(fsm=fsm, name="init", description="초기화")]
    )


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


@pytest.fixture
def empty_tools(qapp):
    """빈 프로젝트가 열린 창 — 잃을 것이 없어 저장 게이트를 그냥 지난다."""
    from daedalus.mcp.tools import DaedalusTools
    from daedalus.view.app import MainWindow

    win = MainWindow()
    win.set_project(PluginProject(name="empty"))
    yield DaedalusTools(win)
    win.close()


# --- G11: new_project ---


def test_new_project_empty_requires_saving_current(tools):
    """내용이 있는데 저장 경로가 없으면 만들지 않는다 — open_project와 같은 게이트."""
    with pytest.raises(ValueError, match="save_current_as"):
        tools.new_project()
    # 현재 프로젝트가 그대로 살아 있다
    assert tools._project.name == "p"


def test_new_project_saves_current_first(tools, tmp_path):
    dest = tmp_path / "old"
    result = tools.new_project(save_current_as=str(dest))
    assert result["saved_before"] == str(dest / ".daedalus.json")
    assert (dest / ".daedalus.json").is_file()
    assert tools._project.name == "new-plugin"


def test_new_project_can_discard(tools):
    result = tools.new_project(save_current=False)
    assert result["discarded_unsaved"] is True
    assert result["saved_before"] is None
    assert tools._project.name == "new-plugin"


def test_new_project_from_empty_project_needs_no_save(empty_tools):
    result = empty_tools.new_project(build_target="local")
    assert result["build_target"] == "local"
    assert empty_tools._project.build_target is BuildTarget.LOCAL


def test_new_project_rejects_unknown_build_target(empty_tools):
    with pytest.raises(ValueError, match="빌드 타깃"):
        empty_tools.new_project(build_target="nope")


def test_new_project_unknown_template_rejected_before_saving(tools, tmp_path):
    """알 수 없는 id로 헛저장을 시키지 않는다(열 수 없는 경로 거절과 같은 순서)."""
    dest = tmp_path / "old"
    with pytest.raises(ValueError, match="알 수 없는 템플릿"):
        tools.new_project(template_id="nope", save_current_as=str(dest))
    assert not dest.exists()


def test_new_project_from_template_and_target_wins(empty_tools):
    """생성 시 고른 타깃이 템플릿에 저장된 타깃을 이긴다."""
    result = empty_tools.new_project(
        template_id="implementation-review", build_target="local"
    )
    project = empty_tools._project
    assert result["template"] == "implementation-review"
    assert project.build_target is BuildTarget.LOCAL
    assert project.agents  # 템플릿 내용이 실제로 들어왔다


def test_new_project_from_template_is_dirty(empty_tools, window=None):
    """템플릿은 잃을 내용이 있고 저장 경로는 없다 — 미저장으로 표시한다."""
    empty_tools.new_project(template_id="single-skill-reference")
    assert empty_tools._window._dirty is True


def test_list_project_templates_includes_builtins(empty_tools):
    ids = [t["id"] for t in empty_tools.list_project_templates()["templates"]]
    assert "implementation-review" in ids
    assert all(t["builtin"] for t in empty_tools.list_project_templates()["templates"])


def test_new_project_carries_folder_template_files(empty_tools, tmp_path, monkeypatch):
    """폴더형 템플릿의 files/는 **첫 저장 때** 딸려 온다(GUI와 같은 예약 경로)."""
    from daedalus.model import templates

    root = tmp_path / "templates"
    seed = root / "my-seed"
    seed.mkdir(parents=True)
    (seed / ".daedalus.json").write_text(
        json.dumps(serialize_project(_project("seeded")), ensure_ascii=False),
        encoding="utf-8",
    )
    (seed / "files").mkdir()
    (seed / "files" / "build.ps1").write_text("echo hi", encoding="utf-8")
    monkeypatch.setattr(templates, "user_templates_dir", lambda home_dir=None: root)

    empty_tools.new_project(template_id="my-seed")
    dest = tmp_path / "proj"
    empty_tools.save_project(str(dest))
    assert (dest / "files" / "build.ps1").is_file()


# --- G12: import_package ---


def test_import_package_round_trip(tools, tmp_path):
    from daedalus.mcp.tools import DaedalusTools

    source = tmp_path / "src"
    tools.save_project(str(source))
    archive = tmp_path / "bundle.ddpj"
    tools.export_package(str(archive))

    dest = tmp_path / "unpacked"
    result = tools.import_package(str(archive), str(dest))
    assert result["dest"] == str(dest)
    assert result["opened"] == str(dest / ".daedalus.json")
    assert isinstance(tools, DaedalusTools)
    assert tools._project.name == "p"


def test_import_package_rejects_missing_archive(tools, tmp_path):
    with pytest.raises(ValueError, match="패키지 파일이 없습니다"):
        tools.import_package(str(tmp_path / "nope.ddpj"), str(tmp_path / "out"))


def test_import_package_rejects_nonempty_dest(tools, tmp_path):
    source = tmp_path / "src"
    tools.save_project(str(source))
    archive = tmp_path / "bundle.ddpj"
    tools.export_package(str(archive))

    dest = tmp_path / "busy"
    dest.mkdir()
    (dest / "keep.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="가져오지 못했습니다"):
        tools.import_package(str(archive), str(dest))
    assert (dest / "keep.txt").is_file()


# --- G14 + S1: 생성 + 배치 1 undo ---


def test_create_skill_with_coords_places_in_one_undo(tools):
    result = tools.create_skill("plan", x=120, y=40)
    assert result["placed"] is True
    assert tools._vm.get_state_vm("plan") is not None

    tools.undo()
    assert tools._vm.get_state_vm("plan") is None
    assert all(s.name != "plan" for s in tools._project.skills)


def test_create_skill_without_coords_only_creates(tools):
    result = tools.create_skill("plan")
    assert result["placed"] is False
    assert tools._vm.get_state_vm("plan") is None


def test_create_reference_with_coords_makes_reference_node(tools):
    tools.create_skill("guide", kind="reference", x=10, y=10)
    assert [r.model.name for r in tools._vm.reference_vms] == ["guide"]


def test_create_skill_rejects_coords_for_unplaceable_kind(tools):
    with pytest.raises(ValueError, match="배치되지 않습니다"):
        tools.create_skill("bg", kind="declarative", x=1, y=2)


def test_create_skill_rejects_half_coords(tools):
    with pytest.raises(ValueError, match="함께"):
        tools.create_skill("plan", x=1)


def test_create_agent_with_coords_places_and_keeps_default_port(tools):
    """팩토리 단일 진실(S1) — 어느 경로로 만들어도 기본 포트 done을 갖는다."""
    tools.create_agent("worker", x=300, y=0)
    agent = tools._find_component("worker")
    assert [e.name for e in agent.transfer_on] == ["done"]
    assert tools._vm.get_state_vm("worker") is not None


def test_create_agent_without_coords_matches_canvas_factory(tools):
    tools.create_agent("worker")
    agent = tools._find_component("worker")
    assert [e.name for e in agent.transfer_on] == ["done"]


def test_create_skill_keeps_rejecting_unknown_kind(tools):
    with pytest.raises(ValueError, match="알 수 없는 스킬 종류"):
        tools.create_skill("x", kind="nope")


# --- G15: transfer 생성 + 할당 1 undo ---


@pytest.fixture
def linked(tools):
    tools.create_skill("next")
    tools.place_component("init", 0, 0)
    tools.place_component("next", 200, 0)
    tools.connect_states("init", "next")
    return tools


def test_create_transfer_creates_and_assigns_in_one_undo(linked):
    result = linked.set_transition("init", "next", create_transfer="handoff")
    assert result["created_transfer"] == "handoff"
    tvm = linked._find_transition_vm("init", "next")
    assert tvm.model.skill_ref.name == "handoff"

    linked.undo()
    assert tvm.model.skill_ref is None
    assert all(s.name != "handoff" for s in linked._project.skills)


def test_create_transfer_rejects_duplicate_name(linked):
    with pytest.raises(ValueError, match="이미 있습니다"):
        linked.set_transition("init", "next", create_transfer="init")


def test_create_transfer_and_transfer_are_exclusive(linked):
    linked.create_skill("existing", kind="transfer")
    with pytest.raises(ValueError, match="함께 줄 수 없습니다"):
        linked.set_transition(
            "init", "next", transfer="existing", create_transfer="handoff"
        )


def test_create_transfer_combines_with_trigger(linked):
    linked.set_transfer_on("init", [{"name": "ok"}])
    linked.set_transition("init", "next", trigger="ok", create_transfer="handoff")
    tvm = linked._find_transition_vm("init", "next")
    assert tvm.model.trigger.name == "ok"
    assert tvm.model.skill_ref.name == "handoff"

    linked.undo()  # 하나의 MacroCommand로 묶여 있다
    assert tvm.model.trigger is None
    assert tvm.model.skill_ref is None
