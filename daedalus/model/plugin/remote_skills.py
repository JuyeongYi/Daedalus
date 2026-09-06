# daedalus/model/plugin/remote_skills.py
"""미설치 플러그인의 스킬 이름 조회 (WP-WR) — 클론 없이 GitHub API로.

마켓플레이스는 플러그인을 `marketplace.json`에 **선언**만 하고 실물은 설치할
때 받아온다(실측: 공식 마켓 291개 선언 / 로컬 실물 40개). 그래서 미설치
플러그인은 이름·설명만 알고 **스킬 목록을 모른다** — 랩핑(WrappedSkill)은
스킬 이름이 있어야 하므로 그때까지 막힌다.

저장소를 통째로 클론하는 대신 **디렉토리 목록 한 번**만 받아온다(사용자 확정):
`skills/` 아래의 하위 디렉토리 이름이 곧 스킬 이름이기 때문이다(카탈로그의
로컬 스캔과 같은 규약 — 이름의 단일 진실은 디렉토리명). 설명은 받지 않는다:
스킬마다 SKILL.md를 또 받아야 해서 요청이 N배가 되고, 랩핑에 필요한 것은
이름뿐이다.

**언제 인터넷에 요청을 보내는가**: 사용자가 그 플러그인을 **지목했을 때만**이다
(사용자 확정). 카탈로그를 열거나 새로고침하는 것만으로는 절대 나가지 않는다 —
291개를 일괄로 받으면 rate limit도, 대기 시간도 감당할 수 없다. 결과는
`~/.daedalus/cache/remote-skills/`에 커밋 SHA(또는 ref)까지 포함한 키로
캐시하므로, 같은 버전을 다시 물으면 요청이 나가지 않는다.

**GitHub만 다룬다.** 다른 호스트(일반 git URL 등)는 API 형식이 제각각이라
`None`을 돌려주고 호출자가 "설치 후 확인"으로 안내한다 — 억지로 추측해
엉뚱한 목록을 보여주는 것보다 모른다고 말하는 편이 낫다. Qt 무관 순수 stdlib.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

#: GitHub API 요청 타임아웃(초) — 사용자가 버튼을 누르고 기다리는 시간이다.
_TIMEOUT = 10.0

#: `https://github.com/OWNER/REPO(.git)` 또는 `git@github.com:OWNER/REPO.git`
_GITHUB_URL_RE = re.compile(
    r"^(?:https?://github\.com/|git@github\.com:)([^/]+)/([^/]+?)(?:\.git)?/?$"
)


class RemoteSkillsError(RuntimeError):
    """원격 조회 실패 — 네트워크·권한·형식."""


@dataclass(frozen=True)
class GithubRef:
    """조회 대상 — 저장소와 그 안의 플러그인 경로."""

    owner: str
    repo: str
    path: str = ""      # 저장소 안 플러그인 디렉토리 (빈 값이면 루트)
    ref: str = ""       # 커밋 SHA 우선, 없으면 태그·브랜치

    @property
    def cache_key(self) -> str:
        parts = [self.owner, self.repo, self.path.strip("/"), self.ref or "HEAD"]
        return "__".join(p.replace("/", "_") or "-" for p in parts)


def parse_github_source(spec: object) -> GithubRef | None:
    """marketplace.json 선언의 `source` → GithubRef (GitHub이 아니면 None).

    실측한 두 형태를 다룬다:
    - `{"source": "git-subdir", "url": "https://github.com/o/r.git",
        "path": "plugins/x", "ref": "v1.5.5", "sha": "30287f5e…"}`
    - `{"source": "github", "repo": "owner/repo", "ref": …, "path": …}`

    `sha`가 있으면 `ref`보다 우선한다 — 태그는 옮겨 달릴 수 있고 SHA는 불변이라
    캐시 키로 안전하다. 문자열 source(마켓 저장소 안 상대 경로)는 원격이 아니라
    None이다(그런 플러그인은 마켓 폴더에 실물이 있다).
    """
    if not isinstance(spec, dict):
        return None
    kind = str(spec.get("source", "") or "")
    path = str(spec.get("path", "") or "")
    ref = str(spec.get("sha") or spec.get("ref") or "")

    repo_field = str(spec.get("repo", "") or "")
    if kind == "github" and "/" in repo_field:
        owner, _, repo = repo_field.partition("/")
        return GithubRef(owner=owner.strip(), repo=repo.strip(), path=path, ref=ref)

    url = str(spec.get("url", "") or "")
    match = _GITHUB_URL_RE.match(url.strip())
    if match:
        return GithubRef(
            owner=match.group(1), repo=match.group(2), path=path, ref=ref,
        )
    return None


def cache_dir(home_dir: Path | None = None) -> Path:
    """조회 결과 캐시 폴더. 테스트는 이 함수를 몽키패치해 홈을 격리한다."""
    base = home_dir if home_dir is not None else Path.home()
    return base / ".daedalus" / "cache" / "remote-skills"


def _api_url(ref: GithubRef) -> str:
    prefix = f"{ref.path.strip('/')}/" if ref.path.strip("/") else ""
    url = f"https://api.github.com/repos/{ref.owner}/{ref.repo}/contents/{prefix}skills"
    return f"{url}?ref={ref.ref}" if ref.ref else url


def _fetch_json(url: str) -> object:
    """GitHub API 한 번 호출. 실패는 RemoteSkillsError로 올린다."""
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            # User-Agent가 없으면 GitHub API가 403으로 막는다.
            "User-Agent": "daedalus-plugin-designer",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RemoteSkillsError(
                "이 플러그인 저장소에 skills/ 디렉토리가 없습니다(스킬을 제공하지 "
                "않거나 경로가 다릅니다)."
            ) from exc
        if exc.code in (403, 429):
            raise RemoteSkillsError(
                "GitHub API 요청 한도에 걸렸습니다 — 잠시 후 다시 시도하세요."
            ) from exc
        raise RemoteSkillsError(f"조회 실패(HTTP {exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RemoteSkillsError(f"인터넷에 연결하지 못했습니다: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RemoteSkillsError("GitHub 응답을 해석하지 못했습니다.") from exc


def fetch_skill_names(ref: GithubRef) -> list[str]:
    """`skills/` 아래 디렉토리 이름 — 곧 스킬 이름 (이름순).

    **인터넷 요청이 여기서 나간다.** 캐시를 쓰려면 `skill_names`를 부르라.
    """
    entries = _fetch_json(_api_url(ref))
    if not isinstance(entries, list):
        raise RemoteSkillsError("GitHub 응답이 디렉토리 목록이 아닙니다.")
    names = [
        str(e.get("name", ""))
        for e in entries
        if isinstance(e, dict) and e.get("type") == "dir" and e.get("name")
    ]
    return sorted(names)


def skill_names(
    plugin_id: str, spec: object, refresh: bool = False,
) -> list[str] | None:
    """미설치 플러그인의 스킬 이름 — 캐시 우선, 없으면 **한 번** 요청.

    GitHub이 아니거나 조회할 수 없으면 `None`(호출자가 "설치 후 확인"으로
    안내한다). 캐시 키에 SHA/ref가 들어가므로 버전이 바뀌면 자동으로 다시
    받는다 — `refresh=True`는 같은 버전을 강제로 다시 받을 때만 쓴다.
    """
    ref = parse_github_source(spec)
    if ref is None:
        return None

    path = cache_dir() / f"{ref.cache_key}.json"
    if not refresh and path.is_file():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cached = None
        if isinstance(cached, dict) and isinstance(cached.get("skills"), list):
            return [str(s) for s in cached["skills"]]

    names = fetch_skill_names(ref)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"plugin_id": plugin_id, "ref": ref.ref, "skills": names},
                ensure_ascii=False, indent=2,
            ) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass  # 캐시 실패는 조회 결과를 버릴 이유가 아니다
    return names
