import pytest


@pytest.fixture(autouse=True)
def _isolate_recent_projects(tmp_path, monkeypatch):
    """최근 프로젝트 목록(WP-RP)이 사용자 홈을 오염시키지 않도록 격리한다.

    MainWindow를 만드는 테스트가 수백 개라, 저장·열기 경로가 실제
    ``~/.daedalus/recent.json``에 tmp 경로를 쌓게 두면 사용자의 메뉴가
    테스트 잔해로 채워진다.
    """
    from daedalus.view import recent

    monkeypatch.setattr(recent, "RECENT_PATH", tmp_path / "recent.json")
