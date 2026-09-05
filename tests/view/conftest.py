import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """PySide6 테스트용 QApplication 싱글턴."""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _reset_hook_name_provider():
    """모듈 전역 제공자(훅 이름·도구 후보·블랙보드 후보)가 테스트 간에 누수되지
    않도록 강제 해제. 개별 테스트의 try/finally 수동 규약에 의존하지 않는 안전망
    — 전역이 프로젝트 객체를 붙잡아 두는 것도 막는다.
    """
    yield
    from daedalus.view.widgets.tag_input import (
        set_blackboard_candidate_provider,
        set_hook_name_provider,
        set_tool_candidate_provider,
    )
    set_hook_name_provider(None)
    set_tool_candidate_provider(None)
    set_blackboard_candidate_provider(None)
    from daedalus.view.widgets.markdown_editor import set_files_root_provider
    set_files_root_provider(None)
