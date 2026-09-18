"""컴파일 액션의 토큰 비용 표시 (A5-lite).

상태바에는 **항상** 합계가 붙고, 임계 초과 안내창은 **넘었을 때만** 뜬다 —
매 컴파일마다 창이 뜨면 계기판이 아니라 방해다.
"""
from __future__ import annotations

from daedalus.compiler.project_compiler import compile_project
from daedalus.compiler.token_report import DEFAULT_FILE_TOKEN_THRESHOLD
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.view.app import MainWindow


def _skill(name: str, body: str) -> ProceduralSkill:
    s = SimpleState(name="start")
    fsm = StateMachine(name=name, initial_state=s, states=[s], final_states=[s])
    return ProceduralSkill(
        fsm=fsm, name=name, description="d", body=body,
        transfer_on=[EventDef("done")],
    )


def _run_compile(window, tmp_path, monkeypatch) -> list[str]:
    """컴파일을 돌리고, 뜬 안내창의 본문 목록을 돌려준다."""
    shown: list[str] = []
    monkeypatch.setattr(
        "daedalus.view.app.QFileDialog.getExistingDirectory",
        lambda *a, **k: str(tmp_path),
    )
    monkeypatch.setattr(
        "daedalus.view.compile_actions.QMessageBox.exec",
        lambda self: shown.append(self.text()),
    )
    window._compile_project_dialog()
    return shown


def test_status_bar_shows_token_total(qapp, tmp_path, monkeypatch):
    window = MainWindow()
    window.set_project(PluginProject(name="p", skills=[_skill("demo", "short")]))

    shown = _run_compile(window, tmp_path, monkeypatch)

    assert "컴파일 완료" in window._status_label.text()
    assert "토큰" in window._status_label.text()
    assert shown == []  # 임계 이하 — 창을 띄우지 않는다
    window.close()


def test_guide_notice_line_alone_does_not_open_the_dialog(qapp, tmp_path,
                                                          monkeypatch):
    """가이드가 나가는 형상(배치 노드 2개)에서도 임계 이하면 창이 뜨지 않는다.

    `notice()`는 임계 초과가 없어도 공통 안내 파일 한 줄을 돌려준다 — 모달을
    그 문자열로 고르면 가이드가 생긴 프로젝트는 **매 컴파일마다** 창이 뜬다.
    띄울지는 `over_threshold()`가 정한다(compile_actions.show_token_notice).
    """
    a, b = _skill("a", "short"), _skill("b", "short")
    project = PluginProject(name="p", skills=[a, b])
    sa, sb = SimpleState(name="a", skill_ref=a), SimpleState(name="b", skill_ref=b)
    project.graph.states += [sa, sb]
    project.graph.transitions.append(
        Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    )
    window = MainWindow()
    window.set_project(project)

    shown = _run_compile(window, tmp_path, monkeypatch)

    assert (tmp_path / "guides" / "p" / "workflow.md").exists()
    assert "토큰" in window._status_label.text()
    assert shown == []  # 가이드 줄만으로는 창을 띄우지 않는다
    window.close()

    # 그런데 안내 문자열 자체에는 가이드 줄이 들어 있다 — 즉 위의 `shown == []`은
    # "notice가 비어서"가 아니라 게이트가 임계로 판정해서다.
    report = compile_project(project, tmp_path / "again").token_report
    assert not report.over_threshold()
    assert "공통 안내 파일" in (report.notice() or "")


def test_notice_dialog_when_over_threshold(qapp, tmp_path, monkeypatch):
    window = MainWindow()
    fat = _skill("fat-skill", "word " * (DEFAULT_FILE_TOKEN_THRESHOLD * 2))
    window.set_project(PluginProject(name="p", skills=[fat]))

    shown = _run_compile(window, tmp_path, monkeypatch)

    assert len(shown) == 1
    assert "skills/fat-skill/SKILL.md" in shown[0]
    # 컴파일 자체는 성공한다 — 정보성이지 게이트가 아니다.
    assert (tmp_path / "skills" / "fat-skill" / "SKILL.md").exists()
    assert "거부" not in window._status_label.text()
    window.close()
