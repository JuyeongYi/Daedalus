from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.view.commands.exit_point_commands import (
    AddExitPointCmd,
    DeleteExitPointCmd,
    RenameExitPointCmd,
    ChangeExitPointColorCmd,
)


def _make_agent_fsm():
    entry = EntryPoint(name="entry")
    exit_done = ExitPoint(name="done")
    return StateMachine(
        name="f", states=[entry, exit_done],
        initial_state=entry, final_states=[exit_done],
    )


def test_add_exit_point():
    fsm = _make_agent_fsm()
    new_ep = ExitPoint(name="error", color="#cc3333")
    cmd = AddExitPointCmd(fsm, new_ep)
    cmd.execute()
    assert new_ep in fsm.states
    assert new_ep in fsm.final_states
    cmd.undo()
    assert new_ep not in fsm.states
    assert new_ep not in fsm.final_states


def test_delete_exit_point():
    fsm = _make_agent_fsm()
    ep = fsm.states[1]  # ExitPoint("done")
    cmd = DeleteExitPointCmd(fsm, ep)
    cmd.execute()
    assert ep not in fsm.states
    assert ep not in fsm.final_states
    cmd.undo()
    assert ep in fsm.states
    assert ep in fsm.final_states


def test_rename_exit_point():
    fsm = _make_agent_fsm()
    ep = fsm.states[1]
    cmd = RenameExitPointCmd(ep, "done", "success")
    cmd.execute()
    assert ep.name == "success"
    cmd.undo()
    assert ep.name == "done"


def test_change_exit_point_color():
    fsm = _make_agent_fsm()
    ep = fsm.states[1]
    assert isinstance(ep, ExitPoint)
    cmd = ChangeExitPointColorCmd(ep, "#4488ff", "#cc3333")
    cmd.execute()
    assert ep.color == "#cc3333"
    cmd.undo()
    assert ep.color == "#4488ff"
