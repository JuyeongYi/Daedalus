import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """PyQt6 테스트용 QApplication 싱글턴."""
    app = QApplication.instance() or QApplication([])
    yield app
