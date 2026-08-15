"""폴더가 곧 프로젝트 — GUI/MCP 결선 (WP-PK).

`_current_path`는 여전히 **안쪽 파일**을 가리킨다. 그래야 `parent`로 계산하는
곳(FilePanel 루트·컴파일 files_dir·MCP 접속 정보)이 한 줄도 안 바뀐다. 이
파일이 고정하는 것은 "사용자에게 보이는 단위만 폴더로 바뀌었다"는 계약이다.
"""
from __future__ import annotations

import json

import pytest

from daedalus.model import package
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.model.serialize import serialize_project


def _project(name: str = "p") -> PluginProject:
    s1 = SimpleState(name="Start")
    fsm = StateMachine(name="f", initial_state=s1, states=[s1], final_states=[s1])
    return PluginProject(
        name=name, skills=[ProceduralSkill(fsm=fsm, name="init", description="초기화")]
    )


@pytest.fixture(autouse=True)
def isolated_recent(tmp_path, monkeypatch):
    from daedalus.view import recent

    monkeypatch.setattr(recent, "RECENT_PATH", tmp_path / "recent.json")


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    win = MainWindow()
    win.set_project(_project())
    yield win
    win.close()


# --- 저장: 폴더를 주면 안에 정본 파일이 생긴다 ---


def test_saving_to_folder_creates_canonical_file(window, tmp_path):
    folder = tmp_path / "my-plugin"
    folder.mkdir()

    assert window._save_to_path(str(folder)) is True

    assert (folder / package.PROJECT_FILENAME).is_file()
    assert window._current_path == str(folder / package.PROJECT_FILENAME)


def test_saving_creates_missing_folder(window, tmp_path):
    folder = tmp_path / "fresh" / "nested"
    assert window._save_to_path(str(folder)) is True
    assert (folder / package.PROJECT_FILENAME).is_file()


def test_files_root_still_resolves_from_current_path(window, tmp_path):
    """`parent` 계산이 그대로 동작해야 한다 — 그것이 이 설계의 요점이다."""
    folder = tmp_path / "my-plugin"
    (folder / "files").mkdir(parents=True)
    window._save_to_path(str(folder))
    assert window._file_panel.files_root() == str(folder / "files")


def test_title_shows_folder_name(window, tmp_path):
    """새 형식 파일 이름은 전부 `.daedalus.json`이라 그대로 보이면 쓸모없다."""
    folder = tmp_path / "my-plugin"
    folder.mkdir()
    window._save_to_path(str(folder))
    assert "my-plugin" in window.windowTitle()


def test_ctrl_s_keeps_legacy_filename(window, tmp_path):
    """열려 있던 형식을 저장이 말없이 갈아치우면 안 된다."""
    legacy = tmp_path / "old.daedalus.json"
    window._save_to_path(str(legacy))
    window._save_project()
    assert window._current_path == str(legacy)
    assert not (tmp_path / package.PROJECT_FILENAME).exists()


# --- Save As가 files/를 데려간다 ---


def test_save_as_carries_files_dir(window, tmp_path):
    source = tmp_path / "here"
    (source / "files").mkdir(parents=True)
    (source / "files" / "tpl.md").write_text("템플릿", encoding="utf-8")
    window._save_to_path(str(source))

    dest = tmp_path / "there"
    window._save_to_path(str(dest))

    assert (dest / "files" / "tpl.md").read_text(encoding="utf-8") == "템플릿"


def test_save_as_does_not_clobber_existing_files_dir(window, tmp_path):
    source = tmp_path / "here"
    (source / "files").mkdir(parents=True)
    (source / "files" / "mine.md").write_text("내 것", encoding="utf-8")
    window._save_to_path(str(source))

    dest = tmp_path / "there"
    (dest / "files").mkdir(parents=True)
    (dest / "files" / "theirs.md").write_text("남의 것", encoding="utf-8")
    window._save_to_path(str(dest))

    assert (dest / "files" / "theirs.md").exists()
    assert not (dest / "files" / "mine.md").exists()


def test_resaving_same_folder_does_not_recurse(window, tmp_path):
    folder = tmp_path / "here"
    (folder / "files").mkdir(parents=True)
    (folder / "files" / "a.txt").write_text("A", encoding="utf-8")
    window._save_to_path(str(folder))
    window._save_to_path(str(folder))
    assert not (folder / "files" / "files").exists()


# --- 열기: 폴더도, 구버전 파일도 ---


def test_opens_folder(window, tmp_path):
    folder = tmp_path / "other"
    folder.mkdir()
    (folder / package.PROJECT_FILENAME).write_text(
        json.dumps(serialize_project(_project("other"))), encoding="utf-8"
    )

    assert window.open_path(str(folder)) is True
    assert window._project.name == "other"
    assert window._current_path == str(folder / package.PROJECT_FILENAME)


def test_opens_legacy_folder(window, tmp_path):
    """기존 프로젝트 폴더도 폴더째 열린다 — 변환 없이."""
    folder = tmp_path / "legacy"
    folder.mkdir()
    (folder / "old.daedalus.json").write_text(
        json.dumps(serialize_project(_project("legacy"))), encoding="utf-8"
    )

    assert window.open_path(str(folder)) is True
    assert window._project.name == "legacy"
    assert window._current_path == str(folder / "old.daedalus.json")


def test_opens_legacy_file_directly(window, tmp_path):
    legacy = tmp_path / "old.daedalus.json"
    legacy.write_text(
        json.dumps(serialize_project(_project("legacy"))), encoding="utf-8"
    )
    assert window.open_path(str(legacy)) is True
    assert window._project.name == "legacy"


def test_opening_folder_without_project_fails_cleanly(window, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert window.open_path(str(empty)) is False
    assert window._project.name == "p"  # 그대로


def test_recent_label_uses_folder_name(window):
    from daedalus.view.app import MainWindow

    label = MainWindow._recent_label(1, f"/a/my-plugin/{package.PROJECT_FILENAME}")
    assert "my-plugin" in label
    assert package.PROJECT_FILENAME not in label


def test_recent_label_keeps_legacy_filename(window):
    from daedalus.view.app import MainWindow

    label = MainWindow._recent_label(1, "/a/dir/old.daedalus.json")
    assert "old.daedalus.json" in label


# --- MCP ---


@pytest.fixture
def tools(window):
    from daedalus.mcp.tools import DaedalusTools

    return DaedalusTools(window)


def test_mcp_saves_to_folder(tools, window, tmp_path):
    folder = tmp_path / "mine"
    out = tools.save_project(str(folder))
    assert out["saved_path"] == str(folder / package.PROJECT_FILENAME)


def test_mcp_opens_folder(tools, window, tmp_path):
    tools.save_project(str(tmp_path / "here"))
    other = tmp_path / "other"
    other.mkdir()
    (other / package.PROJECT_FILENAME).write_text(
        json.dumps(serialize_project(_project("other"))), encoding="utf-8"
    )

    out = tools.open_project(str(other))
    assert out["name"] == "other"


def test_mcp_rejects_folder_without_project_before_saving(tools, window, tmp_path):
    """열 수 없는 경로면 저장도 하지 않는다 — 헛저장은 혼란만 남긴다."""
    tools.save_project(str(tmp_path / "here"))
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="프로젝트 파일이 없습니다"):
        tools.open_project(str(empty))
    assert window._project.name == "p"


def test_mcp_export_packages_the_folder(tools, window, tmp_path):
    folder = tmp_path / "mine"
    (folder / "files").mkdir(parents=True)
    (folder / "files" / "tpl.md").write_text("템플릿", encoding="utf-8")
    tools.save_project(str(folder))

    out = tools.export_package()

    archive = tmp_path / "mine.ddpj"
    assert out["archive"] == str(archive)
    assert archive.is_file()

    restored = tmp_path / "restored"
    package.unpack(archive, restored)
    assert (restored / "files" / "tpl.md").read_text(encoding="utf-8") == "템플릿"


def test_mcp_export_saves_first(tools, window, tmp_path):
    """메모리에만 있는 편집을 빼놓고 묶으면 받는 쪽은 그것이 최신인 줄 안다."""
    folder = tmp_path / "mine"
    tools.save_project(str(folder))
    tools.set_component_description("init", "묶기 직전 변경")

    tools.export_package()

    restored = tmp_path / "restored"
    package.unpack(tmp_path / "mine.ddpj", restored)
    data = json.loads(
        (restored / package.PROJECT_FILENAME).read_text(encoding="utf-8")
    )
    assert any(s["description"] == "묶기 직전 변경" for s in data["skills"])


def test_mcp_export_requires_a_saved_project(tools):
    with pytest.raises(ValueError, match="save_project"):
        tools.export_package()


def test_export_package_is_exposed():
    from daedalus.mcp.service import TOOL_NAMES

    assert "export_package" in TOOL_NAMES
