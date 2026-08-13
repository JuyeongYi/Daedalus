import sys
import traceback

from PySide6.QtWidgets import QApplication

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import ExitPoint
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill, ReferenceSkill, TransferSkill
from daedalus.model.project import PluginProject
from daedalus.view.app import MainWindow

_DARK_STYLE = """
QMainWindow, QWidget { background-color: #1a1a2e; color: #ccc; }
QMenuBar { background-color: #252540; color: #999; }
QMenuBar::item:selected { background-color: #334; }
QMenu { background-color: #252540; color: #ccc; }
QMenu::item:selected { background-color: #334; }
QDockWidget::title { background-color: #252540; color: #888; padding: 4px; }
QTabWidget::pane { border: 1px solid #333; }
QTabBar::tab { background: #252540; color: #666; padding: 6px 14px; }
QTabBar::tab:selected { background: #1a1a2e; color: #ccc; border-top: 2px solid #6674cc; }
QTreeView { background-color: #1e1e32; border: none; }
QListWidget { background-color: #1e1e32; border: none; }
QLineEdit { background-color: #252540; border: 1px solid #444; border-radius: 3px;
            padding: 4px 8px; color: #88aaff; }
QPushButton { background-color: #252540; border: 1px solid #444; border-radius: 3px;
              padding: 4px 8px; color: #ccc; }
QPushButton:checked { background-color: #334; border-color: #6674cc; color: #88aaff; }
QStatusBar { background-color: #252540; color: #555; }
QLabel { color: #ccc; }
"""


def _demo_project() -> PluginProject:
    """개발용 데모 프로젝트."""
    s1 = SimpleState(name="Start")
    s2 = SimpleState(name="Process")
    s3 = SimpleState(name="End")
    init_fsm = StateMachine(
        name="init_fsm",
        initial_state=s1,
        states=[s1, s2, s3],
        transitions=[Transition(source=s1, target=s2), Transition(source=s2, target=s3)],
        final_states=[s3],
    )
    init_skill = ProceduralSkill(fsm=init_fsm, name="init", description="초기화 스킬")

    c1 = SimpleState(name="Cleanup")
    cleanup_fsm = StateMachine(
        name="cleanup_fsm", initial_state=c1, states=[c1], final_states=[c1]
    )
    cleanup_skill = ProceduralSkill(fsm=cleanup_fsm, name="cleanup", description="정리 스킬")

    rules_skill = DeclarativeSkill(
        name="rules",
        description="기반 규칙",
        body="# Instructions\n\n코딩 컨벤션",
    )

    t1 = SimpleState(name="validate")
    transfer_fsm = StateMachine(
        name="validate_fsm", initial_state=t1, states=[t1], final_states=[t1]
    )
    validate_skill = TransferSkill(fsm=transfer_fsm, name="validate", description="전이 시 검증")

    ref_skill = ReferenceSkill(name="coding-conventions", description="코딩 컨벤션 참조")

    w1 = SimpleState(name="Receive")
    w2 = SimpleState(name="Execute")
    w_done = ExitPoint(name="done")  # transfer_on_not_empty 게이트 충족 (Ctrl+B 데모)
    worker_fsm = StateMachine(
        name="worker_fsm",
        initial_state=w1,
        states=[w1, w2, w_done],
        transitions=[Transition(source=w1, target=w2), Transition(source=w2, target=w_done)],
        final_states=[w2],
    )
    worker = AgentDefinition(fsm=worker_fsm, name="worker", description="작업 에이전트")

    project = PluginProject(
        name="my-plugin",
        skills=[init_skill, cleanup_skill, rules_skill, validate_skill, ref_skill],
        agents=[worker],
    )
    # 데모 워크플로 배치 — 빈 캔버스 첫인상 방지 (WP-EP 이후 EntryPoint 마커가
    # 없으므로 placement가 없으면 캔버스가 완전히 비어 보인다)
    p_init = SimpleState(name="init", skill_ref=init_skill)
    p_worker = SimpleState(name="worker", skill_ref=worker)
    p_cleanup = SimpleState(name="cleanup", skill_ref=cleanup_skill)
    project.graph.states.extend([p_init, p_worker, p_cleanup])
    project.graph.transitions.extend([
        Transition(source=p_init, target=p_worker),
        Transition(source=p_worker, target=p_cleanup),
    ])
    return project


def _excepthook(exc_type: type, exc_value: BaseException, exc_tb: object) -> None:
    """Qt 시그널 핸들러 포함 모든 미처리 예외를 전체 출력."""
    traceback.print_exception(exc_type, exc_value, exc_tb)  # type: ignore[arg-type]


def main() -> None:
    sys.excepthook = _excepthook

    app = QApplication(sys.argv)
    app.setStyleSheet(_DARK_STYLE)

    window = MainWindow()
    window.set_project(_demo_project())
    # 앱이 켜지면 CC와 협업할 MCP 서버도 함께 뜬다 (WP-MCP). MainWindow.__init__이
    # 아니라 여기서 시작하는 이유는 테스트가 MainWindow를 다수 생성하기 때문이다.
    window.start_mcp_service()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
