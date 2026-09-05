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


@pytest.fixture(autouse=True)
def _isolate_global_hooks(tmp_path, monkeypatch):
    """전역 훅 폴더(A1)를 사용자 홈에서 떼어낸다.

    `~/.daedalus/hooks/`를 그대로 읽으면 개발자가 거기 둔 훅에 따라 검증·컴파일
    결과가 달라져 테스트가 그 사람의 머신에서만 통과하거나 실패한다. 기본값은
    **빈 폴더**(존재하지 않음)이고, 전역 훅을 다루는 테스트가 여기에 파일을 깐다.
    """
    from daedalus.model.plugin import hook_store

    monkeypatch.setattr(
        hook_store, "global_hooks_dir",
        lambda home_dir=None: (
            (home_dir if home_dir is not None else tmp_path / "home")
            / ".daedalus" / hook_store.GLOBAL_HOOKS_DIRNAME
        ),
    )


@pytest.fixture(autouse=True)
def _isolate_user_templates(tmp_path, monkeypatch):
    """사용자 템플릿 폴더(~/.daedalus/templates/)를 홈에서 떼어낸다.

    실제 홈을 읽으면 개발자가 등록해 둔 템플릿이 카탈로그 개수·내용 단언을
    그 사람의 머신에서만 깨뜨린다(전역 훅 격리와 같은 이유). 기본값은 빈
    폴더(존재하지 않음)이고, 사용자 템플릿을 다루는 테스트가 여기에 파일을 깐다.
    """
    from daedalus.model import templates

    monkeypatch.setattr(
        templates, "user_templates_dir",
        lambda home_dir=None: (
            (home_dir if home_dir is not None else tmp_path / "home")
            / ".daedalus" / "templates"
        ),
    )


@pytest.fixture(autouse=True)
def _auto_discard_unsaved_changes(monkeypatch):
    """`window.close()`의 미저장 변경 확인(A7)이 테스트를 모달로 멈추지 않게 한다.

    수십 개 테스트가 편집 직후 `window.close()`를 부르는데, 그 경로가
    QMessageBox를 띄우면 헤드리스 실행이 그대로 멈춘다. 여기서는 항상
    "버리고 진행"으로 답한다 — A7 도입 이전의 동작과 같다.

    확인 로직 자체를 검증하는 테스트는 모듈 임포트 시점에 잡아 둔 원본 함수를
    직접 호출하거나(이 패치는 임포트 뒤에 걸린다) 이 속성을 다시 덮어쓴다.
    """
    from daedalus.view.app import MainWindow

    monkeypatch.setattr(
        MainWindow, "confirm_discard_changes", lambda self: True, raising=True
    )
