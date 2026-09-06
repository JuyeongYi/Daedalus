# daedalus/model/plugin/plugin_cache.py
"""미설치 플러그인의 실물 캐시 (WP-WR) — `~/.daedalus/cache/plugin/`.

마켓플레이스는 플러그인을 `marketplace.json`에 **선언**만 하고 실물은 설치할
때 받아온다(실측: 공식 마켓 291개 선언 / 로컬 실물 40개). 그래서 받기 전에는
스킬 목록도 설명도 알 수 없고, 랩핑(WrappedSkill)이 막힌다.

**얕은 클론으로 실물을 캐시에 받아 둔다**(사용자 확정). 파일 하나씩 원격에서
긁는 대신 저장소를 한 번 받으면:

- 스킬 이름과 **설명(SKILL.md 프론트매터)까지** 로컬에서 읽는다 — 그것도
  `wrap_catalog._scan_skills`를 **그대로 재사용**해서. 같은 스킬을 어디서
  읽었느냐에 따라 목록이 달라질 여지가 없다.
- GitHub API 요청 한도(익명 IP당 시간당 60회)와 무관하고, **GitHub이 아닌
  호스트(GitLab 등)도 된다** — git이 아는 URL이면 전부.

**언제 인터넷에 나가는가 — 사용자가 그 플러그인을 지목했을 때만이다.**
카탈로그를 열거나 새로고침하는 것만으로는 절대 받지 않는다(291개를 일괄
클론하면 디스크도 시간도 감당할 수 없다). 캐시 폴더 이름에 ref(커밋 SHA 우선)를
넣으므로 같은 버전은 다시 받지 않고, 버전이 바뀌면 새 폴더로 받는다.

Qt 무관 순수 stdlib(+ `git` 실행 파일). 검증기·컴파일러는 이 모듈을 임포트하지
않는다 — 그쪽은 네트워크·파일시스템 무접근이다.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

#: clone/fetch 타임아웃(초) — 사용자가 버튼을 누르고 기다리는 시간이다.
_TIMEOUT = 120.0

#: `owner/repo` 형태의 GitHub 축약 표기 검사용.
_REPO_RE = re.compile(r"^[^/\s]+/[^/\s]+$")


class PluginCacheError(RuntimeError):
    """실물을 받지 못했다 — git 부재·네트워크·잘못된 source."""


@dataclass(frozen=True)
class GitSource:
    """클론 대상 — 저장소와 그 안의 플러그인 경로."""

    url: str
    path: str = ""   # 저장소 안 플러그인 디렉토리 (빈 값이면 루트)
    ref: str = ""    # 커밋 SHA 우선, 없으면 태그·브랜치

    @property
    def cache_key(self) -> str:
        """캐시 폴더 이름 — 경로로 쓸 수 있게 안전한 문자만 남긴다."""
        raw = f"{self.url}__{self.path}__{self.ref or 'HEAD'}"
        return re.sub(r"[^A-Za-z0-9._-]+", "_", raw)[:120]


def parse_git_source(spec: object) -> GitSource | None:
    """marketplace.json 선언의 `source` → GitSource (클론 불가면 None).

    실측한 형태들:
    - `{"source": "git-subdir", "url": "https://github.com/o/r.git",
        "path": "plugins/x", "ref": "v1.5.5", "sha": "30287f5e…"}`
    - `{"source": "github", "repo": "owner/repo", "ref": …, "path": …}`
    - `"./external_plugins/asana"` — 마켓 폴더 안 상대 경로. 원격이 아니다
      (그런 플러그인은 이미 실물이 있어 카탈로그가 로컬에서 읽는다).

    `sha`가 있으면 `ref`보다 우선한다 — 태그는 옮겨 달릴 수 있고 SHA는 불변이라
    캐시 키로 안전하다.
    """
    if not isinstance(spec, dict):
        return None
    path = str(spec.get("path", "") or "")
    ref = str(spec.get("sha") or spec.get("ref") or "")

    url = str(spec.get("url", "") or "").strip()
    if not url:
        repo = str(spec.get("repo", "") or "").strip()
        if _REPO_RE.match(repo):
            url = f"https://github.com/{repo}.git"
    if not url:
        return None
    return GitSource(url=url, path=path, ref=ref)


def cache_dir(home_dir: Path | None = None) -> Path:
    """플러그인 실물 캐시 폴더. 테스트는 이 함수를 몽키패치해 홈을 격리한다."""
    base = home_dir if home_dir is not None else Path.home()
    return base / ".daedalus" / "cache" / "plugin"


def _run_git(args: list[str], cwd: Path | None = None) -> None:
    """git 한 번 실행. 실패는 PluginCacheError로 올린다."""
    try:
        subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            check=True,
            capture_output=True,
            timeout=_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise PluginCacheError(
            "git을 찾지 못했습니다 — 플러그인 실물을 받으려면 git이 설치돼 "
            "있어야 합니다."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise PluginCacheError(f"시간이 초과됐습니다({int(_TIMEOUT)}초).") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        tail = detail[-1] if detail else f"git 종료 코드 {exc.returncode}"
        raise PluginCacheError(f"받지 못했습니다 — {tail}") from exc


def _shallow_clone(source: GitSource, dest: Path) -> None:
    """지정한 ref 하나만 얕게 받는다.

    `git clone --branch`는 태그·브랜치만 받으므로 **커밋 SHA를 지정할 수
    없다**(선언에는 SHA가 흔하다). init + fetch 조합이면 SHA·태그·브랜치가
    모두 통한다.
    """
    dest.mkdir(parents=True, exist_ok=True)
    _run_git(["init", "--quiet"], cwd=dest)
    _run_git(["remote", "add", "origin", source.url], cwd=dest)
    target = source.ref or "HEAD"
    _run_git(["fetch", "--depth", "1", "--quiet", "origin", target], cwd=dest)
    _run_git(["checkout", "--quiet", "FETCH_HEAD"], cwd=dest)


def ensure_cached(
    spec: object, refresh: bool = False,
) -> Path | None:
    """플러그인 실물을 캐시에 확보하고 그 **플러그인 디렉토리**를 돌려준다.

    이미 받아 둔 같은 ref면 인터넷에 나가지 않는다. 클론할 수 없는 source
    (마켓 폴더 안 상대 경로 등)는 `None`.

    실패하면 받다 만 폴더를 지운다 — 남겨 두면 다음 호출이 그것을 "이미 받은
    것"으로 보고 빈 디렉토리를 스캔한다.
    """
    source = parse_git_source(spec)
    if source is None:
        return None

    root = cache_dir() / source.cache_key
    plugin_dir = root / source.path.strip("/") if source.path.strip("/") else root
    if root.exists() and not refresh:
        return plugin_dir if plugin_dir.is_dir() else None
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)

    try:
        _shallow_clone(source, root)
    except PluginCacheError:
        shutil.rmtree(root, ignore_errors=True)
        raise
    if not plugin_dir.is_dir():
        raise PluginCacheError(
            f"받았지만 저장소 안에 '{source.path}' 경로가 없습니다 — 선언의 "
            "path가 저장소 구조와 다릅니다."
        )
    return plugin_dir


def cached_skills(plugin_id: str, spec: object, refresh: bool = False):
    """캐시된 실물에서 스킬 목록을 읽는다 — `CataloguedSkill` 목록.

    스캔은 `wrap_catalog._scan_skills`를 그대로 쓴다(같은 규약·같은 결과):
    이름은 디렉토리명, 설명은 SKILL.md 프론트매터. 클론할 수 없는 source면
    `None`(호출자가 "설치 후 확인"으로 안내한다).
    """
    from daedalus.model.plugin.wrap_catalog import _scan_skills

    plugin_dir = ensure_cached(spec, refresh=refresh)
    if plugin_dir is None:
        return None
    return _scan_skills(plugin_dir, plugin_id)


def clear_cache() -> int:
    """받아 둔 실물을 모두 지운다 — 지운 폴더 수. (디스크 정리용)"""
    root = cache_dir()
    if not root.is_dir():
        return 0
    count = 0
    for child in root.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
            count += 1
    return count
