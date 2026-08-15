"""프로젝트 패키지 — 폴더가 곧 프로젝트, `.ddpj`는 그것을 묶은 것 (WP-PK).

순수 stdlib 계층만 본다(Qt 무관). GUI/MCP 결선은 tests/view/test_project_folder.py.
"""
from __future__ import annotations

import zipfile

import pytest

from daedalus.model import package
from daedalus.model.package import PackageError


def _make_project_dir(root, name="proj", legacy: str = "") -> str:
    d = root / name
    (d / "files" / "sub").mkdir(parents=True)
    filename = legacy or package.PROJECT_FILENAME
    (d / filename).write_text('{"format": 1}', encoding="utf-8")
    (d / "files" / "a.txt").write_text("A", encoding="utf-8")
    (d / "files" / "sub" / "b.txt").write_text("B", encoding="utf-8")
    return str(d)


# --- 경로 해석 ---


def test_folder_resolves_to_canonical_file(tmp_path):
    assert package.resolve_project_file(tmp_path).name == package.PROJECT_FILENAME


def test_file_resolves_to_itself(tmp_path):
    f = tmp_path / "x.daedalus.json"
    f.write_text("{}", encoding="utf-8")
    assert package.resolve_project_file(f) == f


def test_nonexistent_folder_resolves_to_canonical_file(tmp_path):
    """새 폴더에 저장하는 것이 정상 경로다 — `is_dir()`로는 판정할 수 없다."""
    target = package.resolve_project_file(tmp_path / "brand-new")
    assert target == tmp_path / "brand-new" / package.PROJECT_FILENAME


def test_nonexistent_json_path_resolves_to_itself(tmp_path):
    target = tmp_path / "spec.daedalus.json"
    assert package.resolve_project_file(target) == target


def test_saving_over_legacy_file_keeps_its_name(tmp_path):
    """구버전 파일에 덮어쓰는 저장이 형식을 갈아치우면 안 된다."""
    legacy = tmp_path / "old.daedalus.json"
    legacy.write_text("{}", encoding="utf-8")
    assert package.resolve_project_file(legacy).name == "old.daedalus.json"


def test_find_prefers_canonical(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    (d / package.PROJECT_FILENAME).write_text("{}", encoding="utf-8")
    (d / "old.daedalus.json").write_text("{}", encoding="utf-8")
    assert package.find_project_file(d).name == package.PROJECT_FILENAME


def test_find_accepts_single_legacy_file(tmp_path):
    """기존 프로젝트 폴더도 폴더째 열려야 한다."""
    d = tmp_path / "p"
    d.mkdir()
    (d / "old.daedalus.json").write_text("{}", encoding="utf-8")
    assert package.find_project_file(d).name == "old.daedalus.json"


def test_find_refuses_ambiguous_legacy(tmp_path):
    """조용히 하나를 고르면 나머지를 편집 중이라 착각하게 된다."""
    d = tmp_path / "p"
    d.mkdir()
    (d / "a.daedalus.json").write_text("{}", encoding="utf-8")
    (d / "b.daedalus.json").write_text("{}", encoding="utf-8")
    with pytest.raises(PackageError, match="여럿"):
        package.find_project_file(d)


def test_find_reports_missing_file(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    with pytest.raises(PackageError, match=package.PROJECT_FILENAME):
        package.find_project_file(d)


def test_project_dir_of_file_is_its_folder(tmp_path):
    f = tmp_path / package.PROJECT_FILENAME
    f.write_text("{}", encoding="utf-8")
    assert package.project_dir(f) == tmp_path


# --- 표시 이름 ---


def test_display_name_of_canonical_is_folder_name(tmp_path):
    """새 형식 파일 이름은 전부 같으므로 폴더 이름이 곧 이름이다."""
    d = tmp_path / "my-plugin"
    d.mkdir()
    assert package.display_name(d / package.PROJECT_FILENAME) == "my-plugin"


def test_display_name_of_legacy_is_file_name(tmp_path):
    assert package.display_name(tmp_path / "old.daedalus.json") == "old.daedalus.json"


def test_default_archive_name_strips_suffixes(tmp_path):
    d = tmp_path / "my-plugin"
    assert package.default_archive_name(d / package.PROJECT_FILENAME) == "my-plugin.ddpj"
    assert package.default_archive_name(tmp_path / "old.daedalus.json") == "old.ddpj"


def test_is_archive():
    assert package.is_archive("a/b.ddpj")
    assert package.is_archive("A/B.DDPJ")
    assert not package.is_archive("a/b.zip")


# --- 압축 ---


def test_pack_includes_files_tree(tmp_path):
    source = _make_project_dir(tmp_path)
    archive = tmp_path / "out.ddpj"
    members = package.pack(source, archive)
    assert package.PROJECT_FILENAME in members
    assert "files/a.txt" in members
    assert "files/sub/b.txt" in members


def test_pack_is_deterministic(tmp_path):
    """같은 내용이면 같은 바이트 — 컴파일러와 같은 값이다."""
    source = _make_project_dir(tmp_path)
    first = tmp_path / "1.ddpj"
    second = tmp_path / "2.ddpj"
    package.pack(source, first)
    package.pack(source, second)
    assert first.read_bytes() == second.read_bytes()


def test_pack_contents_sit_at_archive_root(tmp_path):
    """폴더 이름을 한 겹 더 넣으면 푸는 쪽에서 중첩만 깊어진다."""
    source = _make_project_dir(tmp_path, name="deep")
    archive = tmp_path / "out.ddpj"
    package.pack(source, archive)
    with zipfile.ZipFile(archive) as zf:
        assert not any(n.startswith("deep/") for n in zf.namelist())


def test_pack_refuses_folder_without_project(tmp_path):
    empty = tmp_path / "nothing"
    (empty / "files").mkdir(parents=True)
    with pytest.raises(PackageError, match="프로젝트 파일이 없어"):
        package.pack(empty, tmp_path / "x.ddpj")


def test_pack_accepts_legacy_project(tmp_path):
    source = _make_project_dir(tmp_path, legacy="old.daedalus.json")
    members = package.pack(source, tmp_path / "x.ddpj")
    assert "old.daedalus.json" in members


# --- 해제 ---


def test_unpack_round_trips(tmp_path):
    source = _make_project_dir(tmp_path)
    archive = tmp_path / "out.ddpj"
    package.pack(source, archive)

    dest = tmp_path / "restored"
    opened = package.unpack(archive, dest)

    assert opened == dest / package.PROJECT_FILENAME
    assert (dest / "files" / "sub" / "b.txt").read_text(encoding="utf-8") == "B"


def test_unpack_refuses_nonempty_dest(tmp_path):
    """덮어 풀면 무엇이 남은 것이고 무엇이 온 것인지 구분할 수 없다."""
    source = _make_project_dir(tmp_path)
    archive = tmp_path / "out.ddpj"
    package.pack(source, archive)
    dest = tmp_path / "busy"
    dest.mkdir()
    (dest / "keep.txt").write_text("x", encoding="utf-8")

    with pytest.raises(PackageError, match="비어 있지 않"):
        package.unpack(archive, dest)
    assert (dest / "keep.txt").exists()


def test_unpack_refuses_non_project_zip(tmp_path):
    archive = tmp_path / "plain.ddpj"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "hi")
    with pytest.raises(PackageError, match="프로젝트 패키지가 아닙니다"):
        package.unpack(archive, tmp_path / "dest")


def test_unpack_refuses_broken_zip(tmp_path):
    archive = tmp_path / "broken.ddpj"
    archive.write_bytes(b"not a zip")
    with pytest.raises(PackageError, match="읽을 수 없습니다"):
        package.unpack(archive, tmp_path / "dest")


def test_unpack_blocks_path_traversal(tmp_path):
    """남이 준 파일을 푸는 자리다 — 목적지 밖에 쓰게 두면 안 된다 (zip slip)."""
    archive = tmp_path / "evil.ddpj"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(package.PROJECT_FILENAME, "{}")
        zf.writestr("../escaped.txt", "pwned")

    dest = tmp_path / "dest"
    with pytest.raises(PackageError, match="안전하지 않은"):
        package.unpack(archive, dest)
    assert not (tmp_path / "escaped.txt").exists()


def test_unpack_blocks_absolute_path(tmp_path):
    archive = tmp_path / "evil2.ddpj"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(package.PROJECT_FILENAME, "{}")
        zf.writestr("/etc/passwd", "pwned")

    with pytest.raises(PackageError, match="안전하지 않은"):
        package.unpack(archive, tmp_path / "dest")


def test_unpack_writes_nothing_when_a_member_is_unsafe(tmp_path):
    """검사는 쓰기 **전에** 끝나야 한다 — 절반 푼 폴더가 남으면 안 된다."""
    archive = tmp_path / "evil3.ddpj"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(package.PROJECT_FILENAME, "{}")
        zf.writestr("files/ok.txt", "ok")
        zf.writestr("../escaped.txt", "pwned")

    dest = tmp_path / "dest"
    with pytest.raises(PackageError):
        package.unpack(archive, dest)
    assert not dest.exists() or not any(dest.iterdir())
