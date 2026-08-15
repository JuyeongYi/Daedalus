"""프로젝트 패키지 — 폴더가 곧 프로젝트, `.ddpj`는 그것을 묶은 것 (WP-PK).

이미 절반은 그랬다. `files/`가 저장 파일 옆에 있고 `_sync_files_root`가
`parent`로 루트를 잡으니 **프로젝트의 단위는 사실상 폴더**였다. 다만 강제되지
않아 같은 폴더의 `.daedalus.json` 둘이 `files/`를 말없이 공유하는 구멍이 있었다.
폴더 = 프로젝트로 못 박으면 그 구멍은 정의상 사라진다.

`_current_path`는 여전히 **안쪽 파일**을 가리킨다 — 사용자에게 보이는 단위만
폴더로 바뀌고 저장 대상은 파일 그대로다. 덕분에 `Path(_current_path).parent`로
계산하는 곳(FilePanel 루트·컴파일 files_dir·MCP 접속 정보)이 한 줄도 안 바뀌고,
구버전 `<이름>.daedalus.json`도 같은 코드 경로를 탄다.

Qt 무관 순수 stdlib — 압축은 **결정적**이다(항목 정렬 + 고정 타임스탬프).
"""
from __future__ import annotations

import os
import zipfile
from pathlib import Path

#: 프로젝트 폴더 안의 정본 파일 이름. 폴더 하나에 프로젝트 하나임을 이 이름이 보장한다.
PROJECT_FILENAME = ".daedalus.json"

#: 구버전 저장 형식 — 폴더 안에 임의 이름으로 놓인 프로젝트 파일.
LEGACY_SUFFIX = ".daedalus.json"

#: 패키지(zip) 확장자.
ARCHIVE_SUFFIX = ".ddpj"

#: 압축 항목의 고정 타임스탬프 — 같은 내용이면 같은 바이트가 나오게 한다.
_FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)


class PackageError(Exception):
    """패키지를 읽거나 쓸 수 없을 때."""


def is_archive(path: str | os.PathLike[str]) -> bool:
    return str(path).lower().endswith(ARCHIVE_SUFFIX)


def is_legacy_file(path: str | os.PathLike[str]) -> bool:
    """구버전 파일인가 — 폴더 안 정본(`.daedalus.json`)이 아닌 `<이름>.daedalus.json`."""
    name = os.path.basename(str(path))
    return name != PROJECT_FILENAME and name.endswith(LEGACY_SUFFIX)


def resolve_project_file(path: str | os.PathLike[str]) -> Path:
    """**저장 대상** 파일 경로. 폴더를 주면 그 안의 정본 파일이 된다.

    이미 파일이면 그대로 — 구버전 파일에 덮어쓰는 저장이 형식을 갈아치우지
    않는다(사용자가 폴더를 골라 저장할 때만 새 형식으로 옮겨간다).

    **아직 없는 경로**는 `is_dir()`로 판정할 수 없다. 새 폴더에 저장하는 것이
    정상 경로이므로(폴더가 곧 프로젝트다) 확장자로 가른다 — `.json`으로 끝나면
    파일, 아니면 폴더. 이 판정이 없으면 "새 폴더에 저장"이 확장자 없는 파일
    하나를 만들고 끝난다.
    """
    p = Path(path)
    if p.is_dir():
        return p / PROJECT_FILENAME
    if p.exists() or p.suffix.lower() == ".json":
        return p
    return p / PROJECT_FILENAME


def find_project_file(path: str | os.PathLike[str]) -> Path:
    """**열 대상** 파일 경로. 폴더를 주면 그 안에서 프로젝트 파일을 찾는다.

    정본(`.daedalus.json`)이 우선이고, 없으면 구버전 `<이름>.daedalus.json`
    하나를 받아들인다 — 그래야 기존 프로젝트 폴더도 폴더째 열린다. 구버전
    파일이 여럿이면 무엇을 여는지 정할 수 없으므로 거절한다(조용히 하나를
    고르면 나머지를 편집하고 있다고 착각하게 된다).
    """
    p = Path(path)
    if not p.is_dir():
        if not p.exists():
            raise PackageError(f"경로가 없습니다: {p}")
        return p

    canonical = p / PROJECT_FILENAME
    if canonical.is_file():
        return canonical

    legacy = sorted(
        f for f in p.iterdir() if f.is_file() and is_legacy_file(f)
    )
    if len(legacy) == 1:
        return legacy[0]
    if len(legacy) > 1:
        names = ", ".join(f.name for f in legacy)
        raise PackageError(
            f"프로젝트 파일이 여럿입니다({names}). 열 파일을 직접 지정하세요."
        )
    raise PackageError(f"프로젝트 파일이 없습니다: {p / PROJECT_FILENAME}")


def project_dir(path: str | os.PathLike[str]) -> Path:
    """프로젝트 폴더 — 저장 파일이 든 디렉토리. `files/`의 부모이기도 하다."""
    p = Path(path)
    return p if p.is_dir() else p.parent


def display_name(path: str | os.PathLike[str]) -> str:
    """창 제목·최근 목록에 보일 이름.

    새 형식의 파일 이름은 `.daedalus.json` 하나뿐이라 그대로 보이면 어느
    프로젝트인지 알 수 없다 — 폴더 이름이 곧 이름이다. 구버전은 파일 이름.
    """
    p = Path(path)
    if p.name == PROJECT_FILENAME:
        return p.parent.name or str(p.parent)
    return p.name


def default_archive_name(path: str | os.PathLike[str]) -> str:
    """이 프로젝트를 묶을 때 쓸 기본 파일 이름."""
    stem = display_name(path)
    if stem.endswith(LEGACY_SUFFIX):
        stem = stem[: -len(LEGACY_SUFFIX)]
    return f"{stem or 'project'}{ARCHIVE_SUFFIX}"


# ----------------------------------------------------------------------
# 압축 / 해제
# ----------------------------------------------------------------------


def _archive_members(source_dir: Path) -> list[tuple[Path, str]]:
    """(실제 경로, 아카이브 내 이름) 목록 — 이름순 정렬, POSIX 구분자.

    폴더 안 **전부**를 담는다. `.daedalus/catalogue/`(프로젝트 카탈로그)처럼
    눈에 안 띄지만 프로젝트의 일부인 것들이 있어, 골라 담으면 반드시 빠진다.
    """
    members: list[tuple[Path, str]] = []
    for root, dirs, files in os.walk(source_dir):
        dirs.sort()
        for name in sorted(files):
            full = Path(root) / name
            if full.is_symlink():
                continue  # 심볼릭 링크는 따라가지 않는다(컴파일러 files/ 복사와 같은 정책)
            members.append((full, full.relative_to(source_dir).as_posix()))
    members.sort(key=lambda item: item[1])
    return members


def pack(source_dir: str | os.PathLike[str], archive_path: str | os.PathLike[str]) -> list[str]:
    """프로젝트 폴더를 `.ddpj`로 묶고 담긴 항목 이름을 돌려준다.

    폴더 **내용**이 아카이브 루트에 놓인다 — 푸는 쪽이 목적지 폴더를 정하므로
    안에 폴더 이름을 한 겹 더 넣으면 중첩만 깊어진다.
    """
    source = Path(source_dir)
    if not source.is_dir():
        raise PackageError(f"프로젝트 폴더가 아닙니다: {source}")

    members = _archive_members(source)
    if not any(
        name == PROJECT_FILENAME or is_legacy_file(name) for _full, name in members
    ):
        raise PackageError(f"프로젝트 파일이 없어 묶을 수 없습니다: {source}")

    target = Path(archive_path)
    if target.parent and not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for full, name in members:
            info = zipfile.ZipInfo(name, date_time=_FIXED_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, full.read_bytes())
    return [name for _full, name in members]


def _safe_target(dest: Path, name: str) -> Path:
    """아카이브 항목이 목적지 밖으로 나가지 않는지 검사한다 (zip slip).

    남이 준 파일을 푸는 자리다 — `../../.ssh/authorized_keys` 같은 이름을
    그대로 믿으면 목적지 밖에 쓴다.
    """
    parts = name.replace("\\", "/").split("/")
    if os.path.isabs(name) or name.startswith(("/", "\\")) or ".." in parts:
        raise PackageError(f"안전하지 않은 경로가 들어 있습니다: {name}")
    target = (dest / name).resolve()
    root = dest.resolve()
    if root != target and root not in target.parents:
        raise PackageError(f"안전하지 않은 경로가 들어 있습니다: {name}")
    return target


def unpack(archive_path: str | os.PathLike[str], dest_dir: str | os.PathLike[str]) -> Path:
    """`.ddpj`를 목적지 폴더에 풀고 **열어야 할 프로젝트 파일** 경로를 돌려준다.

    목적지는 새로 만들거나 비어 있어야 한다 — 기존 폴더에 덮어 풀면 무엇이
    남은 것이고 무엇이 온 것인지 구분할 수 없다.
    """
    archive = Path(archive_path)
    if not archive.is_file():
        raise PackageError(f"패키지 파일이 없습니다: {archive}")

    dest = Path(dest_dir)
    if dest.exists() and any(dest.iterdir()):
        raise PackageError(f"목적지 폴더가 비어 있지 않습니다: {dest}")

    try:
        with zipfile.ZipFile(archive) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            if not any(n == PROJECT_FILENAME or is_legacy_file(n) for n in names):
                raise PackageError(f"프로젝트 패키지가 아닙니다: {archive}")
            targets = [(n, _safe_target(dest, n)) for n in names]
            dest.mkdir(parents=True, exist_ok=True)
            for name, target in targets:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(name))
    except zipfile.BadZipFile as exc:
        raise PackageError(f"패키지를 읽을 수 없습니다: {exc}") from exc

    return find_project_file(dest)
