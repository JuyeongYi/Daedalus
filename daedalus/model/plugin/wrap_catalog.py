# daedalus/model/plugin/wrap_catalog.py
"""외부 마켓플레이스 카탈로그 (WP-WR 2단계, D2) — 등록된 **마켓플레이스 폴더**에서
외부 플러그인·스킬을 발견한다.

**파일시스템을 아는 모듈이다**(hook_store와 같은 지위) — 검증기·컴파일러는 이
모듈을 임포트하지 않는다(그쪽은 파일시스템 무접근 순수성을 유지하고, 실존 검사가
필요해지면 호출자가 결과를 주입한다). Qt 무관 순수 stdlib.

마켓플레이스 폴더 등록의 단일 진실은 ``~/.daedalus/external_marketplaces.json``:

    [{"path": "C:/Users/me/.claude/plugins/marketplaces/my-mkt", "marketplace": "my-mkt"},
     {"path": "D:/plugins/standalone", "marketplace": ""}]

- 마켓플레이스 폴더 하나는 "그 밑을 훑으면 플러그인들이 나오는 폴더"다 —
  마켓플레이스 저장소, ``~/.claude/plugins`` 계열 폴더, 플러그인 디렉토리
  자체 전부 가능하다.
- 마켓플레이스 이름 해소 순서: 등록 시 명시한 ``marketplace`` >
  폴더 자신의 ``.claude-plugin/marketplace.json``의 ``name`` > 빈 문자열(bare).
  이름이 있으면 플러그인 id가 ``플러그인@마켓``으로 나와 LOCAL enabledPlugins
  배선까지 자동이고, 없으면 bare(``플러그인``)라 마켓 빌드 dependencies만
  가능하다(컴파일이 경고로 짚는다).
- **여기는 발견(전역)만이다** — 실제로 어느 외부 플러그인을 쓰는지는
  프로젝트 모델(``PluginProject.external_plugins``)이 저장한다(사용자 확정 —
  사용 선언은 프로젝트 단위).
- 깨진 JSON·읽기 실패는 stderr 경고 후 스킵한다(전역 훅 규약 — 파일 하나
  때문에 카탈로그 전체가 죽으면 안 된다).
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

MARKETPLACES_FILENAME = "external_marketplaces.json"

#: 플러그인 탐색 최대 깊이 (마켓플레이스 폴더 자신 = 0). 마켓 저장소는 보통
#: ``<폴더>/plugins/<플러그인>`` 정도라 4면 충분하고, 무제한 재귀는 홈 폴더를
#: 등록하는 실수 한 번에 UI를 멈춘다.
_MAX_SCAN_DEPTH = 4

#: 탐색에서 건너뛰는 디렉토리 이름 (숨김 폴더는 ``.claude-plugin`` 확인용으로만
#: 들여다보고 재귀하지 않는다).
_SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv"})


@dataclass
class MarketplaceFolder:
    """등록된 외부 마켓플레이스 폴더."""

    path: str
    marketplace: str = ""


@dataclass
class CataloguedSkill:
    """발견된 외부 스킬."""

    name: str
    description: str
    source: str  # "플러그인[@마켓]:스킬" — WrappedSkillConfig.source에 그대로 쓴다


@dataclass
class CataloguedPlugin:
    """발견된 외부 플러그인."""

    name: str
    path: str
    marketplace: str = ""
    description: str = ""
    skills: list[CataloguedSkill] = field(default_factory=list)
    #: 로컬에 실물이 받아져 있는가 (사용자 보고 2026-09-07).
    #:
    #: 마켓플레이스는 `marketplace.json`에 플러그인을 **선언**만 하고 실물은
    #: 설치할 때 받아온다(실측: 공식 마켓은 291개 선언, 로컬 실물 40개).
    #: 예전에는 실물이 있는 것만 훑어 "마켓에는 있는데 카탈로그에 안 뜨는"
    #: 플러그인이 252개였다.
    #:
    #: `False`면 **이름·설명만 안다** — 스킬 목록은 파일이 없어 알 수 없으므로
    #: `skills`가 비어 있고, 따라서 랩핑(WrappedSkill)은 설치 후에만 된다.
    #: 반면 **사용 선언(external_plugins)은 지금 할 수 있다** — plugin_id만
    #: 있으면 빌드가 dependencies/enabledPlugins를 내고, 설치는 CC가 한다.
    installed: bool = True
    #: 미설치 플러그인의 marketplace.json 선언 `source` (설치된 것은 None).
    #: 실물을 받아오려면 이것이 재료다 — `plugin_cache`가 이 선언으로 저장소를
    #: 얕게 클론해 두고 `_scan_skills`가 그대로 스킬을 읽는다.
    source_spec: object | None = None
    #: 이 플러그인이 동봉 `.mcp.json`(또는 plugin.json `mcpServers`)으로
    #: 제공하는 MCP 서버 이름들 (이름순). 플러그인이 활성화되면 CC가 함께
    #: 로드하므로 — 에이전트 `mcp_servers` 필드 후보가 되고, LOCAL 컴파일의
    #: `missing_mcp_server_def` 판정에서 제외된다(이 프로젝트가 배선할 것이
    #: 없다). 개별 도구 목록은 지원하지 않는다(사용자 확정 — tools 후보에는
    #: 넣지 않는다).
    mcp_servers: list[str] = field(default_factory=list)

    @property
    def plugin_id(self) -> str:
        """설치 식별자 ``이름[@마켓]`` — external_plugins·dependencies·
        enabledPlugins가 쓰는 형식."""
        return f"{self.name}@{self.marketplace}" if self.marketplace else self.name


# ─────────────────────────── 마켓플레이스 폴더 등록 파일 ───────────────────────────


def marketplaces_file(home_dir: Path | None = None) -> Path:
    """등록 파일 경로. 테스트는 이 함수를 몽키패치해 홈을 격리한다."""
    base = home_dir if home_dir is not None else Path.home()
    return base / ".daedalus" / MARKETPLACES_FILENAME


def load_marketplaces() -> list[MarketplaceFolder]:
    """등록된 마켓플레이스 폴더 목록. 파일이 없거나 깨져 있으면 빈 목록(stderr 경고)."""
    path = marketplaces_file()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[daedalus] 마켓플레이스 등록 파일을 읽지 못했습니다 ({path}): {exc}",
              file=sys.stderr)
        return []
    folders: list[MarketplaceFolder] = []
    for entry in data if isinstance(data, list) else []:
        if not isinstance(entry, dict) or not str(entry.get("path", "")).strip():
            continue
        folders.append(MarketplaceFolder(
            path=str(entry["path"]),
            marketplace=str(entry.get("marketplace", "") or ""),
        ))
    return folders


def save_marketplaces(folders: list[MarketplaceFolder]) -> None:
    path = marketplaces_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [{"path": f.path, "marketplace": f.marketplace} for f in folders]
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _norm(p: str) -> str:
    """경로 동일성 판정용 정규화 (등록 중복 방지)."""
    return os.path.normcase(os.path.normpath(str(p)))


def add_marketplace(path: str, marketplace: str = "") -> list[MarketplaceFolder]:
    """마켓플레이스 폴더를 등록한다(경로 기준 중복이면 이름만 갱신). 갱신된 목록 반환."""
    folders = load_marketplaces()
    for f in folders:
        if _norm(f.path) == _norm(path):
            f.marketplace = marketplace
            break
    else:
        folders.append(MarketplaceFolder(path=str(path), marketplace=marketplace))
    save_marketplaces(folders)
    return folders


def remove_marketplace(path: str) -> bool:
    """마켓플레이스 폴더 등록을 지운다. 있었으면 True."""
    folders = load_marketplaces()
    kept = [f for f in folders if _norm(f.path) != _norm(path)]
    if len(kept) == len(folders):
        return False
    save_marketplaces(kept)
    return True


# ─────────────────────────── 발견 ───────────────────────────


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[daedalus] 마켓플레이스 카탈로그 파일을 읽지 못했습니다 ({path}): {exc}",
              file=sys.stderr)
        return None
    return data if isinstance(data, dict) else None


def _frontmatter_fields(md_path: Path) -> dict[str, str]:
    """SKILL.md 맨 앞 프론트매터의 단순 ``key: value`` 필드만 뽑는다.

    풀 YAML 파서가 아니다 — name/description 표시용이라 한 줄 스칼라만 다루고,
    그 외(멀티라인·리스트)는 조용히 건너뛴다. 파일이 없거나 프론트매터가 없으면
    빈 dict.
    """
    try:
        text = md_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep and key.strip() and not key.startswith((" ", "\t")):
            out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _read_marketplace_manifest(folder_dir: Path) -> dict | None:
    """폴더가 마켓플레이스 저장소면 그 매니페스트(``marketplace.json``)."""
    path = folder_dir / ".claude-plugin" / "marketplace.json"
    return _read_json(path) if path.is_file() else None


def _marketplace_name(folder_dir: Path) -> str:
    """폴더가 마켓플레이스 저장소면 그 이름 (``.claude-plugin/marketplace.json``)."""
    mkt = _read_marketplace_manifest(folder_dir)
    return str(mkt.get("name", "") or "") if mkt else ""


def _declared_plugins(manifest: dict | None) -> list[tuple[str, str, object | None]]:
    """마켓플레이스가 **선언**한 플러그인 — [(이름, 설명, source)] (선언 순서).

    실물이 로컬에 없어도 여기에는 있다 — 마켓은 목록을 선언하고 실물은 설치할
    때 받아오기 때문이다. 항목의 `source`는 마켓 저장소 안 상대 경로일 수도,
    외부 git 저장소 참조일 수도 있다 — **설치를 위해 해석하지는 않는다**(그건
    CC 몫이다). 다만 스킬 이름만이라도 원격에서 받아오려면 재료가 되므로
    그대로 실어 보낸다.
    """
    if not manifest:
        return []
    out: list[tuple[str, str, object | None]] = []
    for item in manifest.get("plugins") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "") or "").strip()
        if name:
            out.append((
                name,
                str(item.get("description", "") or ""),
                item.get("source"),
            ))
    return out


def _scan_skills(plugin_dir: Path, plugin_id: str) -> list[CataloguedSkill]:
    skills_dir = plugin_dir / "skills"
    if not skills_dir.is_dir():
        return []
    out: list[CataloguedSkill] = []
    for child in sorted(skills_dir.iterdir(), key=lambda p: p.name):
        md = child / "SKILL.md"
        if not child.is_dir() or not md.is_file():
            continue
        fm = _frontmatter_fields(md)
        # 이름의 단일 진실은 디렉토리명이다 — CC가 스킬을 디렉토리명으로
        # 설치하고, 프론트매터 name과 어긋난 경우 디렉토리 쪽이 인보크 대상이다.
        name = child.name
        out.append(CataloguedSkill(
            name=name,
            description=fm.get("description", ""),
            source=f"{plugin_id}:{name}",
        ))
    return out


def _scan_mcp_servers(plugin_dir: Path, manifest: dict) -> list[str]:
    """플러그인이 제공하는 MCP 서버 이름 — 동봉 `.mcp.json`의 mcpServers 키
    ∪ plugin.json의 `mcpServers` 키 (이름순 정렬)."""
    names: set[str] = set()
    mcp_json = plugin_dir / ".mcp.json"
    if mcp_json.is_file():
        data = _read_json(mcp_json) or {}
        servers = data.get("mcpServers")
        if isinstance(servers, dict):
            names.update(str(k) for k in servers)
    manifest_servers = manifest.get("mcpServers")
    if isinstance(manifest_servers, dict):
        names.update(str(k) for k in manifest_servers)
    return sorted(names)


def discover_plugins(folder: MarketplaceFolder) -> list[CataloguedPlugin]:
    """마켓플레이스 폴더 하나에서 플러그인(``.claude-plugin/plugin.json`` 보유
    디렉토리)을 찾아 스킬 목록과 함께 돌려준다 (플러그인 이름순 정렬 — 결정적)."""
    folder_dir = Path(folder.path)
    if not folder_dir.is_dir():
        return []
    manifest = _read_marketplace_manifest(folder_dir)
    marketplace = folder.marketplace or (
        str(manifest.get("name", "") or "") if manifest else ""
    )

    plugins: list[CataloguedPlugin] = []
    seen: set[str] = set()

    def visit(directory: Path, depth: int) -> None:
        manifest_path = directory / ".claude-plugin" / "plugin.json"
        if manifest_path.is_file():
            manifest = _read_json(manifest_path) or {}
            name = str(manifest.get("name", "") or directory.name)
            if name not in seen:
                seen.add(name)
                plugin_id = f"{name}@{marketplace}" if marketplace else name
                plugins.append(CataloguedPlugin(
                    name=name,
                    path=str(directory),
                    marketplace=marketplace,
                    description=str(manifest.get("description", "") or ""),
                    skills=_scan_skills(directory, plugin_id),
                    mcp_servers=_scan_mcp_servers(directory, manifest),
                ))
            return  # 플러그인 안에 또 플러그인은 없다 — 하위 재귀 중단
        if depth >= _MAX_SCAN_DEPTH:
            return
        try:
            children = sorted(directory.iterdir(), key=lambda p: p.name)
        except OSError:
            return
        for child in children:
            if not child.is_dir():
                continue
            if child.name in _SKIP_DIRS or child.name.startswith("."):
                continue
            visit(child, depth + 1)

    visit(folder_dir, 0)

    # 마켓이 **선언**했지만 로컬에 실물이 없는 플러그인 — 이름·설명만 싣는다
    # (스킬은 파일이 없어 알 수 없다). 사용 선언은 이것만으로 충분하다.
    for name, description, source_spec in _declared_plugins(manifest):
        if name in seen:
            continue
        seen.add(name)
        plugins.append(CataloguedPlugin(
            name=name,
            path="",  # 로컬 경로가 없다
            marketplace=marketplace,
            description=description,
            skills=[],
            installed=False,
            source_spec=source_spec,
        ))

    plugins.sort(key=lambda p: p.name)
    return plugins


def scan_catalog(
    folders: list[MarketplaceFolder] | None = None,
) -> list[tuple[MarketplaceFolder, list[CataloguedPlugin]]]:
    """전체 카탈로그: 등록 순서대로 (마켓플레이스 폴더, 발견된 플러그인들) 쌍 목록."""
    if folders is None:
        folders = load_marketplaces()
    return [(folder, discover_plugins(folder)) for folder in folders]


def resolve_skill_file(source: str) -> Path | None:
    """랩핑 source(`플러그인[@마켓]:스킬`) → 카탈로그에서 원본 SKILL.md 경로.

    등록된 마켓플레이스 폴더에서 plugin_id 정확 일치로 찾는다. 못 찾으면
    None — 폴더 미등록이거나 소스가 다른 머신의 것이다(에러가 아니라 안내
    대상). wrapped 에디터의 "원본 열기" 버튼이 쓴다.
    """
    plugin_id, _, skill_name = source.partition(":")
    plugin_id, skill_name = plugin_id.strip(), skill_name.strip()
    if not plugin_id or not skill_name:
        return None
    for _folder, plugins in scan_catalog():
        for plugin in plugins:
            if plugin.plugin_id != plugin_id:
                continue
            md = Path(plugin.path) / "skills" / skill_name / "SKILL.md"
            if md.is_file():
                return md
    return None


def used_plugin_mcp_servers(project) -> list[str]:
    """사용 선언된 외부 플러그인이 제공하는 MCP 서버 이름 합집합 (이름순).

    소비처 두 곳: ① 에이전트 `mcp_servers` 필드의 자동완성 후보
    (app.set_project가 provider로 등록), ② LOCAL 컴파일 주입
    (`compile_project(provided_server_names=)` — 이 서버들은 플러그인
    활성화가 가져오므로 `missing_mcp_server_def` 대상이 아니다). 컴파일러는
    파일시스템을 읽지 않으므로 호출 환경이 이 함수를 불러 주입한다
    (resolved_hooks와 같은 경계).
    """
    declared = {
        str(p).strip()
        for p in getattr(project, "external_plugins", None) or []
        if str(p).strip()
    }
    if not declared:
        return []
    names: set[str] = set()
    for _folder, plugins in scan_catalog():
        for plugin in plugins:
            if plugin.plugin_id in declared:
                names.update(plugin.mcp_servers)
    return sorted(names)
