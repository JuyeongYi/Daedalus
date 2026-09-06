# tests/model/test_save_user_template.py
"""현재 프로젝트를 사용자 템플릿으로 저장 (Save As Template).

두 경로가 함께 있어야 한다 — 내장(패키지 동봉)은 재설치 때 갈리고, 여기 저장한
사용자 템플릿은 `~/.daedalus/templates/`에 남는다. 홈 격리는 conftest의
_isolate_user_templates가 한다.
"""
from __future__ import annotations

import json

import pytest

from daedalus.model import templates
from daedalus.model.package import PROJECT_FILENAME
from daedalus.model.project import PluginProject
from daedalus.model.templates import (
    TemplateError,
    delete_user_template,
    list_templates,
    load_template,
    save_user_template,
)


def _project(name: str = "my-plugin") -> PluginProject:
    return PluginProject(name=name, description="내 시드")


# ─────────────────────────── 저장 형식 ───────────────────────────


def test_saves_single_json_when_no_side_files():
    path = save_user_template(_project(), "my-seed")
    assert path.name == "my-seed.json"
    # 파일은 **프로젝트 저장 파일 그 자체**다 — 로드가 같은 역직렬화기를 탄다
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["name"] == "my-plugin"
    assert data["format"] == 2


def test_saved_template_appears_in_catalogue_and_loads():
    save_user_template(_project(), "my-seed")
    entry = next(t for t in list_templates() if t.id == "my-seed")
    # 표시 문구는 프로젝트의 name/description 그대로
    assert (entry.title, entry.summary) == ("my-plugin", "내 시드")
    assert entry.file is not None  # 사용자 템플릿

    loaded = load_template("my-seed")
    assert loaded.name == "my-plugin"


def test_folder_form_when_project_has_side_files(tmp_path):
    """동봉 파일이 있으면 폴더형 — 그래야 첫 저장 때 딸려 간다."""
    source = tmp_path / "proj"
    (source / "files" / "A").mkdir(parents=True)
    (source / "files" / "A" / "c.txt").write_text("x", encoding="utf-8")
    (source / "skill-files" / "s1").mkdir(parents=True)
    (source / "skill-files" / "s1" / "note.md").write_text("y", encoding="utf-8")

    path = save_user_template(_project(), "with-files", source_dir=source)
    assert path.name == PROJECT_FILENAME
    root = path.parent
    assert root.name == "with-files"
    assert (root / "files" / "A" / "c.txt").read_text(encoding="utf-8") == "x"
    assert (root / "skill-files" / "s1" / "note.md").read_text(encoding="utf-8") == "y"

    entry = next(t for t in list_templates() if t.id == "with-files")
    assert entry.source_dir == root  # 첫 저장 때 동반 복사의 원천


def test_empty_side_dirs_stay_single_json(tmp_path):
    """빈 files/는 폴더형으로 만들 이유가 없다."""
    source = tmp_path / "proj"
    (source / "files").mkdir(parents=True)
    path = save_user_template(_project(), "empty-side", source_dir=source)
    assert path.name == "empty-side.json"


# ─────────────────────────── id 규약 ───────────────────────────


@pytest.mark.parametrize("bad", ["My Seed", "seed/../x", "-seed", "", "seed.json"])
def test_rejects_unsafe_ids(bad):
    """파일 이름이 되므로 경로 문자를 받지 않는다 — 조용히 슬러그로 바꾸지도
    않는다(지은 이름과 목록에 뜨는 이름이 달라진다)."""
    with pytest.raises(TemplateError, match="쓸 수 없습니다"):
        save_user_template(_project(), bad)


# ─────────────────────────── 덮어쓰기 ───────────────────────────


def test_existing_id_requires_overwrite():
    save_user_template(_project(), "my-seed")
    with pytest.raises(TemplateError, match="이미 있습니다"):
        save_user_template(_project("other"), "my-seed")

    save_user_template(_project("other"), "my-seed", overwrite=True)
    assert load_template("my-seed").name == "other"


def test_overwrite_switches_form_and_cleans_up(tmp_path):
    """폴더형 → 파일형(그 반대도) 전환 시 옛 형태가 남지 않는다."""
    source = tmp_path / "proj"
    (source / "files").mkdir(parents=True)
    (source / "files" / "c.txt").write_text("x", encoding="utf-8")

    folder_path = save_user_template(_project(), "seed", source_dir=source)
    assert folder_path.parent.is_dir()

    # 동봉 파일 없이 다시 저장 → 파일형이 되고 폴더는 사라진다
    file_path = save_user_template(_project(), "seed", overwrite=True)
    assert file_path.name == "seed.json"
    assert not (templates.user_templates_dir() / "seed").exists()
    assert [t.id for t in list_templates() if t.id == "seed"] == ["seed"]


def test_user_template_shadows_builtin():
    """동명 id면 사용자 것이 이긴다 — 내장은 목록에서 가려진다."""
    save_user_template(_project("mine"), "research-pipeline")
    entries = [t for t in list_templates() if t.id == "research-pipeline"]
    assert len(entries) == 1
    assert entries[0].title == "mine"


# ─────────────────────────── 삭제 ───────────────────────────


def test_delete_user_template_removes_both_forms(tmp_path):
    source = tmp_path / "proj"
    (source / "files").mkdir(parents=True)
    (source / "files" / "c.txt").write_text("x", encoding="utf-8")
    save_user_template(_project(), "folder-seed", source_dir=source)
    save_user_template(_project(), "file-seed")

    assert delete_user_template("folder-seed") is True
    assert delete_user_template("file-seed") is True
    assert delete_user_template("never") is False
    assert [t.id for t in list_templates() if t.id.endswith("-seed")] == []


def test_delete_restores_shadowed_builtin():
    """사용자 사본을 지우면 가려졌던 내장이 다시 드러난다."""
    save_user_template(_project("mine"), "research-pipeline")
    delete_user_template("research-pipeline")
    entry = next(t for t in list_templates() if t.id == "research-pipeline")
    assert entry.file is None  # 내장으로 복귀
