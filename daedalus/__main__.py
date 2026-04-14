import sys
import traceback

from PyQt6.QtWidgets import QApplication

from daedalus.model.fsm.machine import StateMachine
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

    rules_skill = DeclarativeSkill(name="rules", description="기반 규칙", content="코딩 컨벤션")

    t1 = SimpleState(name="validate")
    transfer_fsm = StateMachine(
        name="validate_fsm", initial_state=t1, states=[t1], final_states=[t1]
    )
    validate_skill = TransferSkill(fsm=transfer_fsm, name="validate", description="전이 시 검증")

    ref_skill = ReferenceSkill(name="coding-conventions", description="코딩 컨벤션 참조")

    w1 = SimpleState(name="Receive")
    w2 = SimpleState(name="Execute")
    worker_fsm = StateMachine(
        name="worker_fsm",
        initial_state=w1,
        states=[w1, w2],
        transitions=[Transition(source=w1, target=w2)],
        final_states=[w2],
    )
    worker = AgentDefinition(fsm=worker_fsm, name="worker", description="작업 에이전트")

    return PluginProject(
        name="MyPlugin",
        skills=[init_skill, cleanup_skill, rules_skill, validate_skill, ref_skill],
        agents=[worker],
    )


def _excepthook(exc_type: type, exc_value: BaseException, exc_tb: object) -> None:
    """PyQt 시그널 핸들러 포함 모든 미처리 예외를 전체 출력."""
    traceback.print_exception(exc_type, exc_value, exc_tb)  # type: ignore[arg-type]


def main() -> None:
    sys.excepthook = _excepthook

    app = QApplication(sys.argv)
    app.setStyleSheet(_DARK_STYLE)

    window = MainWindow()
    window.set_project(_demo_project())
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
