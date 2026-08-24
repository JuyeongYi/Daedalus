"""A7 — 앱 종료 시 미저장 변경 확인.

MCP/GUI로 편집한 내용이 메모리에만 있는 채 창이 닫혀 유실된 사고가 세 번 났다.
여기서 고정하는 것은 ① 더티 판정이 실제 편집 경로(구조 + 본문 키스트로크)를
빠짐없이 잡는가 ② 저장/로드가 그것을 내리는가 ③ closeEvent가 답에 따라
종료를 막는가다.

`confirm_discard_changes`는 루트 conftest의 autouse 픽스처가 항상 True로
덮어쓰므로(헤드리스에서 모달이 뜨면 전체 스위트가 멈춘다), 원본 함수를 **모듈
임포트 시점**에 잡아 두고 직접 호출한다.
"""
from PySide6.QtWidgets import QMessageBox

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.view.app import MainWindow

# 픽스처가 덮어쓰기 전의 진짜 구현 (모듈 임포트는 픽스처보다 먼저 돈다)
_REAL_CONFIRM = MainWindow.confirm_discard_changes


def _make_project() -> PluginProject:
    s = SimpleState(name="start")
    fsm = StateMachine(name="f", initial_state=s, states=[s], final_states=[s])
    proc = ProceduralSkill(fsm=fsm, name="my-proc", description="d")
    decl = DeclarativeSkill(name="my-decl", description="d")
    return PluginProject(name="p", skills=[proc, decl])


# --- 더티 판정 ---


def test_fresh_window_is_clean(qapp):
    """아무것도 안 한 창은 깨끗하다 — 시작하자마자 확인창이 뜨면 안 된다."""
    window = MainWindow()
    assert window._dirty is False
    window.close()


def test_load_project_clears_dirty(qapp):
    """로드 자체는 미저장 변경이 아니다 (로드 중 notify가 여러 번 돈다)."""
    window = MainWindow()
    window.load_project(_make_project())
    assert window._dirty is False
    window.close()


def test_structure_edit_marks_dirty(qapp):
    """캔버스 구조 편집(structure 채널) → 더티."""
    window = MainWindow()
    window.load_project(_make_project())
    window._project_vm.notify()
    assert window._dirty is True
    window.close()


def test_content_edit_marks_dirty(qapp):
    """본문 키스트로크(content 채널) → 더티.

    content 리스너를 따로 등록하지 않으면 여기가 통째로 새어 나간다
    (`ProjectViewModel.notify("content")`는 content 리스너만 부른다).
    """
    window = MainWindow()
    window.load_project(_make_project())
    window._project_vm.notify(scope="content")
    assert window._dirty is True
    window.close()


def test_body_editing_marks_dirty(qapp):
    """실제 본문 편집 경로(body_documents QTextDocument)로도 더티가 잡힌다.

    채널 단위 notify가 아니라 사용자가 실제로 밟는 경로를 태워야 의미가 있다 —
    `SectionContentPanel`이 어느 채널로 알리는지가 바뀌면 여기가 깨진다.
    """
    from PySide6.QtGui import QTextCursor

    from daedalus.view.editors.skill_editor import SkillEditor

    window = MainWindow()
    project = _make_project()
    window.load_project(project)

    skill = project.skills[0]
    editor = SkillEditor(skill, on_notify_fn=window._project_vm.notify)
    body_panel = editor._editor._content_panel  # SectionContentPanel

    # setPlainText는 undo 스택을 지운다 — 실제 타이핑과 같은 경로를 쓴다.
    cursor = body_panel._w_content.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText("타이핑")

    assert skill.body.endswith("타이핑")
    assert window._dirty is True
    editor.close()
    window.close()


def test_save_clears_dirty(qapp, tmp_path):
    window = MainWindow()
    window.load_project(_make_project())
    window._project_vm.notify()
    assert window._dirty is True

    assert window._save_to_path(str(tmp_path / "proj")) is True
    assert window._dirty is False
    window.close()


def test_title_shows_asterisk_while_dirty(qapp, tmp_path):
    """관례대로 제목에 `*`가 붙고, 저장하면 사라진다."""
    window = MainWindow()
    window.load_project(_make_project())
    window._save_to_path(str(tmp_path / "proj"))
    assert not window.windowTitle().startswith("*")

    window._project_vm.notify()
    assert window.windowTitle().startswith("*")

    window._save_to_path(str(tmp_path / "proj"))
    assert not window.windowTitle().startswith("*")
    window.close()


# --- 종료 확인 다이얼로그 ---


def test_confirm_passes_when_clean(qapp, monkeypatch):
    """깨끗하면 아무것도 묻지 않는다."""
    window = MainWindow()
    window.load_project(_make_project())

    asked = []
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: asked.append(a) or QMessageBox.StandardButton.Cancel
    )
    assert _REAL_CONFIRM(window) is True
    assert asked == []
    window.close()


def test_confirm_cancel_blocks_close(qapp, monkeypatch):
    """취소 → 종료 거부 + 창 유지."""
    window = MainWindow()
    window.load_project(_make_project())
    window._project_vm.notify()

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Cancel
    )
    monkeypatch.setattr(MainWindow, "confirm_discard_changes", _REAL_CONFIRM)

    stopped = []
    monkeypatch.setattr(
        window._launch_actions, "stop_mcp_service", lambda: stopped.append(True)
    )
    assert window.close() is False
    # 닫지 않았으니 MCP 서버도 내리지 않는다
    assert stopped == []
    assert window._dirty is True

    monkeypatch.setattr(MainWindow, "confirm_discard_changes", lambda self: True)
    window.close()


def test_confirm_discard_allows_close(qapp, monkeypatch):
    """저장 안 함 → 그대로 종료."""
    window = MainWindow()
    window.load_project(_make_project())
    window._project_vm.notify()

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Discard
    )
    assert _REAL_CONFIRM(window) is True
    window.close()


def test_confirm_save_writes_then_allows_close(qapp, monkeypatch, tmp_path):
    """저장 후 종료 → 실제로 저장되고 종료가 허용된다."""
    window = MainWindow()
    window.load_project(_make_project())
    window._save_to_path(str(tmp_path / "proj"))
    window._project_vm.notify()
    assert window._dirty is True

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Save
    )
    assert _REAL_CONFIRM(window) is True
    assert window._dirty is False
    window.close()


def test_confirm_save_that_fails_blocks_close(qapp, monkeypatch):
    """저장하겠다고 답했는데 저장이 안 됐으면 종료를 막는다.

    미저장 프로젝트에서 "다른 이름으로 저장" 다이얼로그를 취소한 경우가 이것이다 —
    여기서 그냥 닫으면 이 기능이 막으려던 사고를 그대로 낸다.
    """
    window = MainWindow()
    window.load_project(_make_project())
    window._project_vm.notify()

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Save
    )
    # 경로 미지정 → save_project_as → 폴더 선택 취소
    from daedalus.view import session_io

    monkeypatch.setattr(
        session_io.QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: "")
    )
    assert _REAL_CONFIRM(window) is False
    assert window._dirty is True
    window.close()
