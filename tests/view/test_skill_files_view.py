"""스킬별 파일 view 배선 (WP-SF) — 드롭 토큰 + FilePanel 루트 전환."""
from __future__ import annotations

from daedalus.view.widgets.markdown_editor import (
    MarkdownEditor,
    _skill_file_ref_token,
    set_files_root_provider,
    set_skill_files_root_provider,
)


# --- 토큰 계산 ---


def test_skill_file_token_strips_skill_dir_component(tmp_path):
    root = tmp_path / "skill-files"
    target = root / "alpha" / "scripts" / "run.sh"
    target.parent.mkdir(parents=True)
    target.write_text("x", encoding="utf-8")
    token = _skill_file_ref_token(str(target), str(root))
    # 스킬 폴더 이름(alpha)은 토큰에 없다 — 런타임 SKILL_DIR가 그 폴더다
    assert token == "${CLAUDE_SKILL_DIR}/scripts/run.sh"


def test_skill_file_token_wraps_spaces(tmp_path):
    root = tmp_path / "skill-files"
    target = root / "alpha" / "my doc.md"
    target.parent.mkdir(parents=True)
    target.write_text("x", encoding="utf-8")
    assert _skill_file_ref_token(str(target), str(root)) == "<${CLAUDE_SKILL_DIR}/my doc.md>"


def test_loose_file_under_root_yields_no_token(tmp_path):
    """스킬 폴더 미소속 파일 — 소속을 알 수 없어 토큰 없음(기본 드롭으로)."""
    root = tmp_path / "skill-files"
    root.mkdir()
    stray = root / "stray.txt"
    stray.write_text("x", encoding="utf-8")
    assert _skill_file_ref_token(str(stray), str(root)) is None


def test_outside_root_yields_no_token(tmp_path):
    other = tmp_path / "elsewhere.txt"
    other.write_text("x", encoding="utf-8")
    assert _skill_file_ref_token(str(other), str(tmp_path / "skill-files")) is None


# --- provider 합류 (_token_for_path) ---


def test_token_for_path_tries_both_roots(qapp, tmp_path):
    files = tmp_path / "files"
    files.mkdir()
    (files / "common.txt").write_text("x", encoding="utf-8")
    skill_files = tmp_path / "skill-files"
    (skill_files / "alpha").mkdir(parents=True)
    (skill_files / "alpha" / "ref.md").write_text("x", encoding="utf-8")

    set_files_root_provider(lambda: str(files))
    set_skill_files_root_provider(lambda: str(skill_files))
    try:
        assert MarkdownEditor._token_for_path(str(files / "common.txt")) == (
            "${ROOT}/files/common.txt"
        )
        assert MarkdownEditor._token_for_path(
            str(skill_files / "alpha" / "ref.md")
        ) == "${CLAUDE_SKILL_DIR}/ref.md"
        assert MarkdownEditor._token_for_path(str(tmp_path / "outside.txt")) is None
    finally:
        set_files_root_provider(None)
        set_skill_files_root_provider(None)


# --- FilePanel 루트 전환 ---


def test_file_panel_exposes_both_roots(qapp, tmp_path):
    from daedalus.view.panels.file_panel import FilePanel

    (tmp_path / "files").mkdir()
    (tmp_path / "skill-files").mkdir()
    panel = FilePanel()
    panel.set_project_dir(tmp_path)
    assert panel.files_root() == str(tmp_path / "files")
    assert panel.skill_files_root() == str(tmp_path / "skill-files")


def test_file_panel_combo_switches_tree_root(qapp, tmp_path):
    from daedalus.view.panels.file_panel import FilePanel

    (tmp_path / "files").mkdir()
    (tmp_path / "skill-files" / "alpha").mkdir(parents=True)
    panel = FilePanel()
    panel.set_project_dir(tmp_path)
    assert panel._tree.isVisible() or panel._model is not None  # files 루트 바인딩

    panel._root_combo.setCurrentIndex(1)  # 스킬별
    assert panel._model is not None
    from pathlib import Path

    # QFileSystemModel.rootPath()는 구분자를 '/'로 돌려준다 — Path로 정규화 비교
    assert Path(panel._model.rootPath()) == tmp_path / "skill-files"


def test_file_panel_create_button_creates_selected_root(qapp, tmp_path):
    from daedalus.view.panels.file_panel import FilePanel

    panel = FilePanel()
    panel.set_project_dir(tmp_path)
    panel._root_combo.setCurrentIndex(1)  # 스킬별 — 아직 폴더 없음
    panel._create_root_folder()
    assert (tmp_path / "skill-files").is_dir()
    assert not (tmp_path / "files").exists()  # 선택된 루트만 만든다
