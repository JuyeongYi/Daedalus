"""WP-F: view 저장→열기 왕복 검증."""
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.view.app import MainWindow


def _make_project() -> PluginProject:
    s = SimpleState(name="start")
    fsm = StateMachine(name="f", initial_state=s, states=[s], final_states=[s])
    proc = ProceduralSkill(fsm=fsm, name="my_proc", description="d")
    decl = DeclarativeSkill(name="my_decl", description="d")

    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    afsm = StateMachine(name="af", initial_state=entry, states=[entry, done],
                        final_states=[done])
    agent = AgentDefinition(fsm=afsm, name="my_agent", description="d")
    return PluginProject(name="P", skills=[proc, decl], agents=[agent])


def test_save_then_open_roundtrip_tree(qapp, tmp_path):
    """저장→열기 왕복 후 같은 스킬/에이전트 구성이 로드된다."""
    window = MainWindow()
    window.set_project(_make_project())

    path = str(tmp_path / "proj.daedalus.json")
    window._save_to_path(path)

    # 새 윈도우에서 열기
    window2 = MainWindow()
    window2.open_path(path)

    assert window2._project is not None
    skill_names = {s.name for s in window2._project.skills}
    agent_names = {a.name for a in window2._project.agents}
    assert skill_names == {"my_proc", "my_decl"}
    assert agent_names == {"my_agent"}
    assert window2._current_path == path

    window.close()
    window2.close()


def test_open_clears_existing_tabs(qapp, tmp_path):
    """열기 시 기존 에디터 탭이 정리된다 (Project FSM 탭만 남음)."""
    window = MainWindow()
    project = _make_project()
    window.set_project(project)

    path = str(tmp_path / "proj.daedalus.json")
    window._save_to_path(path)

    # 에디터 탭 하나 열기
    window._open_component(project.agents[0])
    assert window._tabs.count() == 2

    window.open_path(path)
    assert window._tabs.count() == 1  # Project FSM 탭만 남음
    assert window._open_tabs == {}

    window.close()
