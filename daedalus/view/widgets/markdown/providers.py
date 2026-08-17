"""파일 루트 제공자 + 드롭 참조 토큰 계산 (WP-FR / WP-SF).

TagInput의 도구/블랙보드 후보 제공자와 동일한 패턴 — app이 ``_current_path``
변화에 맞춰 등록하고, MarkdownEditor의 드롭 치환이 조회한다. None이면(미저장
프로젝트 등) 드롭 치환이 비활성화되고 기본 동작으로 흐른다.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Callable

# --- files/ 루트 제공자 (WP-FR) ---
_FILES_ROOT_PROVIDER: Callable[[], str | None] | None = None


def set_files_root_provider(provider: Callable[[], str | None] | None) -> None:
    """MarkdownEditor 드롭 치환이 참조할 현재 프로젝트 files/ 루트 제공자를 등록한다."""
    global _FILES_ROOT_PROVIDER
    _FILES_ROOT_PROVIDER = provider


def get_files_root() -> str | None:
    """등록된 제공자에서 현재 files/ 루트 경로를 가져온다 (없으면 None)."""
    if _FILES_ROOT_PROVIDER is not None:
        return _FILES_ROOT_PROVIDER()
    return None


_SKILL_FILES_ROOT_PROVIDER: Callable[[], str | None] | None = None


def set_skill_files_root_provider(provider: Callable[[], str | None] | None) -> None:
    """skill-files/ 루트 제공자를 등록한다 (WP-SF — files 제공자와 동일 패턴)."""
    global _SKILL_FILES_ROOT_PROVIDER
    _SKILL_FILES_ROOT_PROVIDER = provider


def get_skill_files_root() -> str | None:
    """등록된 제공자에서 현재 skill-files/ 루트 경로를 가져온다 (없으면 None)."""
    if _SKILL_FILES_ROOT_PROVIDER is not None:
        return _SKILL_FILES_ROOT_PROVIDER()
    return None


def _file_ref_token(local_path: str, files_root: str) -> str | None:
    """local_path가 files_root 하위 파일이면 참조 토큰을 계산한다. 아니면 None.

    토큰은 타깃 중립 ``${ROOT}/files/<상대경로>``다(WP-RT) — 어느 CC 변수가
    되는지는 컴파일 시점에 빌드 타깃이 정한다. 경로 구분자는 POSIX(``/``)로
    정규화한다.

    경로에 공백이 있으면 마크다운 관례대로 ``<...>``로 감싼다 — 감싸지 않으면
    컴파일러의 참조 스캐너가 공백에서 끊어 자기가 만든 토큰을 dangling으로
    오탐한다(리뷰 지적: Part B/C 자기모순).
    """
    try:
        rel = Path(local_path).resolve().relative_to(Path(files_root).resolve())
    except ValueError:
        return None
    if str(rel) == ".":
        return None  # files_root 자체가 드롭된 경우 — 삽입 대상 아님
    from daedalus.model.plugin.variables import file_ref_token

    posix_rel = PurePosixPath(rel.as_posix())
    token = file_ref_token(str(posix_rel))
    return f"<{token}>" if " " in str(posix_rel) else token


def _skill_file_ref_token(local_path: str, skill_files_root: str) -> str | None:
    """local_path가 skill-files/<스킬>/ 하위 파일이면 참조 토큰을 계산한다 (WP-SF).

    토큰은 ``${CLAUDE_SKILL_DIR}/<스킬 폴더 안 상대경로>`` — 첫 경로 조각(스킬
    폴더 이름)은 토큰에 들어가지 않는다. 런타임에 CC가 이 변수를 그 스킬의
    디렉토리로 치환하기 때문이다. skill-files/ 바로 밑 파일(스킬 폴더 없음)은
    소속을 알 수 없어 None — 기본 드롭으로 흘린다(컴파일도 복사하지 않는다).
    공백 경로의 ``<...>`` 감싸기는 files 토큰과 같은 이유다.
    """
    try:
        rel = Path(local_path).resolve().relative_to(Path(skill_files_root).resolve())
    except ValueError:
        return None
    parts = PurePosixPath(rel.as_posix()).parts
    if len(parts) < 2:
        return None  # 루트 자체 또는 스킬 폴더 미소속 파일
    inner = "/".join(parts[1:])
    token = "${CLAUDE_SKILL_DIR}/" + inner
    return f"<{token}>" if " " in inner else token
