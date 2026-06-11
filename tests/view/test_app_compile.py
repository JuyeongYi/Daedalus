"""MainWindow 컴파일 액션(Ctrl+B) — 폴더 선택 → compile_project → 상태바/검증패널."""
from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.section import EventDef, Section
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.config import ProceduralSkillConfig
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.view.app import MainWindow


def _make_skill(name: str = "demo-skill", fsm: StateMachine | None = None) -> ProceduralSkill:
    if fsm is None:
        s = SimpleState(name="start")
        fsm = StateMachine(name="m", initial_state=s, states=[s], final_states=[s])
    return ProceduralSkill(
        fsm=fsm,
        name=name,
        description="d",
        config=ProceduralSkillConfig(),
        sections=[Section("Instructions", "do it")],
        transfer_on=[EventDef("done")],
    )


def test_compile_action_writes_files(qapp, tmp_path, monkeypatch):
    window = MainWindow()
    project = PluginProject(name="p", skills=[_make_skill()])
    window.set_project(project)

    monkeypatch.setattr(
        "daedalus.view.app.QFileDialog.getExistingDirectory",
        lambda *a, **k: str(tmp_path),
    )
    window._compile_project_dialog()

    assert (tmp_path / "skills" / "demo-skill" / "SKILL.md").exists()
    assert "컴파일 완료" in window._status_label.text()
    window.close()


def test_compile_action_rejected_on_error(qapp, tmp_path, monkeypatch):
    window = MainWindow()
    # initial_state가 states에 없는 잘못된 FSM → 에러
    real = SimpleState(name="real")
    orphan = SimpleState(name="orphan")
    bad = StateMachine(name="bad", initial_state=orphan, states=[real])
    project = PluginProject(name="p", skills=[_make_skill("bad-skill", fsm=bad)])
    window.set_project(project)

    monkeypatch.setattr(
        "daedalus.view.app.QFileDialog.getExistingDirectory",
        lambda *a, **k: str(tmp_path),
    )
    window._compile_project_dialog()

    assert "거부" in window._status_label.text()
    assert not list(tmp_path.rglob("*.md"))
    window.close()


def test_compile_action_cancel_noop(qapp, monkeypatch):
    window = MainWindow()
    project = PluginProject(name="p", skills=[_make_skill()])
    window.set_project(project)

    monkeypatch.setattr(
        "daedalus.view.app.QFileDialog.getExistingDirectory",
        lambda *a, **k: "",  # 취소
    )
    window._compile_project_dialog()
    # 취소 시 상태바에 컴파일 관련 메시지가 없어야(기본 유지)
    assert "컴파일" not in window._status_label.text()
    window.close()
