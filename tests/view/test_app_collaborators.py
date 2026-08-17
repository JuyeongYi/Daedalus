"""app.py 분해 — 협력 객체 배선 고정 (WP-RF-3e).

MainWindow는 골격만 갖고, 세션 입출력·컴파일·실행·검증은 협력 객체가 맡는다.
여기서 고정하는 것은 두 가지다:

1. **위임 표면** — 테스트·MCP 도구가 `window._save_to_path(...)`처럼 윈도우의
   내부 메서드를 직접 부른다. 협력 객체로 옮기면서 이 이름들이 사라지면
   호출부가 조용히 깨진다.
2. **상태의 단일 진실** — 협력 객체가 `_current_path` 같은 값을 자기 필드로
   복제하면 두 곳이 어긋나는 순간 "저장했는데 다른 파일이 열린다"가 된다.
"""
from __future__ import annotations

import pytest

from daedalus.model.project import PluginProject
from daedalus.view.app import MainWindow
from daedalus.view.compile_actions import CompileActions
from daedalus.view.launch_actions import LaunchActions
from daedalus.view.session_io import SessionIO, recent_label
from daedalus.view.validation_actions import ValidationActions


@pytest.fixture
def window(qapp):
    win = MainWindow()
    win.set_project(PluginProject(name="p"))
    yield win
    win.close()


# --- 배선 ---

@pytest.mark.parametrize(
    ("attr", "cls"),
    [
        ("_session_io", SessionIO),
        ("_compile_actions", CompileActions),
        ("_launch_actions", LaunchActions),
        ("_validation_actions", ValidationActions),
    ],
)
def test_collaborators_are_bound_to_window(window, attr, cls):
    collaborator = getattr(window, attr)
    assert isinstance(collaborator, cls)
    assert collaborator._w is window


def test_collaborators_are_not_mixins():
    """Mixin 금지 — MainWindow는 QMainWindow만 상속한다."""
    from PySide6.QtWidgets import QMainWindow

    assert MainWindow.__bases__ == (QMainWindow,)


# --- 위임 표면 (기존 호출부 보존) ---

_DELEGATED = [
    # 세션 입출력
    "_sync_files_root", "_update_title", "_save_to_path", "_carry_files_dir",
    "_save_project", "_save_project_as", "project_has_content", "_new_project",
    "_prompt_build_target", "_edit_project_properties", "_open_project_dialog",
    "_open_file_dialog", "_export_package_dialog", "_import_package_dialog",
    "_remember_recent", "_rebuild_recent_menu", "_recent_label", "_open_recent",
    "_clear_recent", "open_path",
    # 컴파일
    "_compile_project_dialog", "_known_server_defs",
    # MCP / 실행
    "start_mcp_service", "_show_mcp_info", "_launch_claude_code",
    "_ensure_daedalus_mcp_json",
    # 검증
    "_run_validation", "_show_validation_dock", "_find_validation_dock",
    "_on_validation_item_activated", "_focus_in_project_canvas",
    "_focus_in_agent_tab",
]


@pytest.mark.parametrize("name", _DELEGATED)
def test_window_keeps_delegating_method(name):
    assert callable(getattr(MainWindow, name, None)), name


def test_recent_label_is_the_module_function():
    """`MainWindow._recent_label(...)`은 인스턴스 없이 클래스에서 직접 호출된다."""
    assert MainWindow._recent_label is recent_label


# --- 상태의 단일 진실 ---

def test_current_path_lives_on_window_only(window, tmp_path):
    """저장 경로는 window의 것 하나뿐 — 협력 객체가 복제본을 들고 있지 않다."""
    assert window._save_to_path(str(tmp_path)) is True
    assert window._current_path is not None
    assert window._current_path.startswith(str(tmp_path))
    # SessionIO는 window를 볼 뿐 자기 필드에 경로를 담지 않는다
    assert vars(window._session_io) == {"_w": window}


def test_collaborators_hold_only_the_window_reference(window):
    for attr in ("_compile_actions", "_launch_actions", "_validation_actions"):
        assert vars(getattr(window, attr)) == {"_w": window}


def test_mcp_service_handle_is_read_from_window(window):
    """서비스 핸들도 window가 단일 진실 — 협력 객체가 그것을 읽는다."""
    class _FakeService:
        url = "http://127.0.0.1:9999/mcp"

    window._mcp_service = _FakeService()
    assert window._known_server_defs()["daedalus"]["url"] == "http://127.0.0.1:9999/mcp"
