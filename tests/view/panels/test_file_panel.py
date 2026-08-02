# tests/view/panels/test_file_panel.py
"""FilePanel — files/ 트리 뷰 + 안내/새로고침 (WP-FR Part A).

가시성 검증은 `isVisible()` 대신 `isHidden()`을 쓴다 — 테스트에서 위젯을 실제로
`.show()`하지 않으므로(최상위 창에 실체화되지 않음) `isVisible()`은 항상 False를
반환한다. `isHidden()`은 조상 실체화 여부와 무관하게 우리가 호출한
`setVisible()`의 명시적 플래그를 그대로 반영한다.
"""
from __future__ import annotations

from daedalus.view.panels.file_panel import FilePanel


def test_no_project_dir_shows_unsaved_guidance(qapp):
    """프로젝트 미저장(project_dir 미설정) — 안내 라벨만 보이고 버튼/트리는 숨김."""
    panel = FilePanel()
    assert not panel._info_label.isHidden()
    assert "저장" in panel._info_label.text()
    assert panel._create_btn.isHidden()
    assert panel._tree.isHidden()
    assert panel.files_root() is None


def test_project_dir_without_files_folder_shows_create_button(tmp_path):
    """project_dir는 있지만 files/ 폴더가 없으면 안내+생성 버튼, 트리는 숨김."""
    panel = FilePanel()
    panel.set_project_dir(tmp_path)
    assert not panel._info_label.isHidden()
    assert "없습니다" in panel._info_label.text()
    assert not panel._create_btn.isHidden()
    assert panel._tree.isHidden()
    assert panel.files_root() is None


def test_create_files_folder_button_creates_dir_and_shows_tree(tmp_path):
    panel = FilePanel()
    panel.set_project_dir(tmp_path)
    panel._create_files_folder()

    files_dir = tmp_path / "files"
    assert files_dir.is_dir()
    assert panel.files_root() == str(files_dir)
    assert not panel._tree.isHidden()
    assert panel._info_label.isHidden()
    assert panel._create_btn.isHidden()


def test_existing_files_folder_binds_tree_root_on_set(tmp_path):
    """이미 존재하는 files/ 폴더 — set_project_dir 시 바로 트리에 바인딩."""
    files_dir = tmp_path / "files"
    (files_dir / "A").mkdir(parents=True)
    (files_dir / "A" / "c.txt").write_text("x", encoding="utf-8")

    panel = FilePanel()
    panel.set_project_dir(tmp_path)

    assert panel.files_root() == str(files_dir)
    assert not panel._tree.isHidden()
    model = panel._tree.model()
    assert model is not None
    root_index = panel._tree.rootIndex()
    # QFileSystemModel은 경로를 '/' 구분자로 정규화해 반환한다 — Path로 비교.
    from pathlib import Path
    assert Path(model.filePath(root_index)) == files_dir
    # 표시 열은 이름(0)만 — 나머지(크기/유형/수정일)는 숨김
    assert not panel._tree.isColumnHidden(0)
    for col in range(1, model.columnCount()):
        assert panel._tree.isColumnHidden(col)


def test_set_project_dir_none_clears_root_and_model(tmp_path):
    """프로젝트가 닫히면(project_dir=None) 안내로 되돌아가고 모델을 해제한다."""
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    panel = FilePanel()
    panel.set_project_dir(tmp_path)
    assert panel.files_root() is not None

    panel.set_project_dir(None)
    assert panel.files_root() is None
    assert panel._tree.model() is None
    assert not panel._info_label.isHidden()
    assert panel._create_btn.isHidden()  # project_dir 자체가 없음


def test_refresh_rebinds_after_external_folder_creation(tmp_path):
    """files/ 폴더가 프로젝트 설정 이후 외부에서 생성되면 refresh()로 반영된다."""
    panel = FilePanel()
    panel.set_project_dir(tmp_path)
    assert panel.files_root() is None

    (tmp_path / "files").mkdir()
    panel.refresh()
    assert panel.files_root() == str(tmp_path / "files")
    assert not panel._tree.isHidden()


def test_drag_enabled_for_drag_source(tmp_path):
    """트리는 드래그 소스로 동작해야 한다(QFileSystemModel 기본 file URL mime)."""
    panel = FilePanel()
    assert panel._tree.dragEnabled()
