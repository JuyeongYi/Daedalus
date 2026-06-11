import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """PyQt6 테스트용 QApplication 싱글턴."""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _reset_hook_name_provider():
    """모듈 전역 훅 이름 제공자가 테스트 간에 누수되지 않도록 강제 해제.

    개별 테스트의 try/finally 수동 규약에 의존하지 않는 안전망.
    """
    yield
    from daedalus.view.widgets.preset_picker import set_hook_name_provider
    set_hook_name_provider(None)
