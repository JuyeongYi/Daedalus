# daedalus/model/plugin/wrap_catalog.py
"""랩핑 소스 카탈로그 (WP-WR 2단계, D2) — 등록된 플러그인 루트에서 랩핑 가능한
스킬을 발견한다.

**파일시스템을 아는 모듈이다**(hook_store와 같은 지위) — 검증기·컴파일러는 이
모듈을 임포트하지 않는다(그쪽은 파일시스템 무접근 순수성을 유지하고, 실존 검사가
필요해지면 호출자가 결과를 주입한다). Qt 무관 순수 stdlib.

루트 등록의 단일 진실은 ``~/.daedalus/plugin_roots.json``:

    [{"path": "C:/Users/me/.claude/plugins/marketplaces/my-mkt", "marketplace": "my-mkt"},
     {"path": "D:/plugins/standalone", "marketplace": ""}]

- 루트 하나는 "그 밑을 훑으면 플러그인들이 나오는 폴더"다 — 마켓플레이스 저장소,
  ``~/.claude/plugins`` 계열 폴더, 플러그인 디렉토리 자체 전부 가능하다.
- 마켓플레이스 이름 해소 순서: 등록 시 명시한 ``marketplace`` >
  루트 자신의 ``.claude-plugin/marketplace.json``의 ``name`` > 빈 문자열(bare).
  이름이 있으면 소스가 ``플러그인@마켓:스킬``로 나와 LOCAL enabledPlugins
  배선까지 자동이고, 없으면 bare(``플러그인:스킬``)라 마켓 빌드 dependencies만
  가능하다(컴파일이 ``wrapped_source_no_marketplace``로 짚는다).
- 깨진 JSON·읽기 실패는 stderr 경고 후 스킵한다(전역 훅 규약 — 파일 하나
  때문에 카탈로그 전체가 죽으면 안 된다).
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOTS_FILENAME = "plugin_roots.json"

#: 플러그인 탐색 최대 깊이 (루트 자신 = 0). 마켓 저장소는 보통
#: ``<루트>/plugins/<플러그인>`` 정도라 4면 충분하고, 무제한 재귀는 홈 폴더를
#: 루트로 등록하는 실수 한 번에 UI를 멈춘다.
_MAX_SCAN_DEPTH = 4

#: 탐색에서 건너뛰는 디렉토리 이름 (숨김 폴더는 ``.claude-plugin`` 확인용으로만
#: 들여다보고 재귀하지 않는다).
_SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv"})


@dataclass
class PluginRoot:
    """등록된 탐색 루트."""

    path: str
    marketplace: str = ""


@dataclass
class CataloguedSkill:
    """발견된 랩핑 가능 스킬."""

    name: str
    description: str
    source: str  # "플러그인[@마켓]:스킬" — WrappedSkillConfig.source에 그대로 쓴다


@dataclass
class CataloguedPlugin:
    """발견된 플러그인."""

    name: str
    path: str
    marketplace: str = ""
    description: str = ""
    skills: list[CataloguedSkill] = field(default_factory=list)


# ─────────────────────────── 루트 등록 파일 ───────────────────────────


def plugin_roots_file(home_dir: Path | None = None) -> Path:
    """루트 등록 파일 경로. 테스트는 이 함수를 몽키패치해 홈을 격리한다."""
    base = home_dir if home_dir is not None else Path.home()
    return base / ".daedalus" / ROOTS_FILENAME


def load_plugin_roots() -> list[PluginRoot]:
    """등록된 루트 목록. 파일이 없거나 깨져 있으면 빈 목록(stderr 경고)."""
    path = plugin_roots_file()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[daedalus] 플러그인 루트 파일을 읽지 못했습니다 ({path}): {exc}",
              file=sys.stderr)
        return []
    roots: list[PluginRoot] = []
    for entry in data if isinstance(data, list) else []:
        if not isinstance(entry, dict) or not str(entry.get("path", "")).strip():
            continue
        roots.append(PluginRoot(
            path=str(entry["path"]),
            marketplace=str(entry.get("marketplace", "") or ""),
        ))
    return roots


def save_plugin_roots(roots: list[PluginRoot]) -> None:
    path = plugin_roots_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [{"path": r.path, "marketplace": r.marketplace} for r in roots]
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _norm(p: str) -> str:
    """경로 동일성 판정용 정규화 (등록 중복 방지)."""
    return os.path.normcase(os.path.normpath(str(p)))


def add_plugin_root(path: str, marketplace: str = "") -> list[PluginRoot]:
    """루트를 등록한다(경로 기준 중복이면 marketplace만 갱신). 갱신된 목록 반환."""
    roots = load_plugin_roots()
    for r in roots:
        if _norm(r.path) == _norm(path):
            r.marketplace = marketplace
            break
    else:
        roots.append(PluginRoot(path=str(path), marketplace=marketplace))
    save_plugin_roots(roots)
    return roots


def remove_plugin_root(path: str) -> bool:
    """루트 등록을 지운다. 있었으면 True."""
    roots = load_plugin_roots()
    kept = [r for r in roots if _norm(r.path) != _norm(path)]
    if len(kept) == len(roots):
        return False
    save_plugin_roots(kept)
    return True


# ─────────────────────────── 발견 ───────────────────────────


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[daedalus] 플러그인 카탈로그 파일을 읽지 못했습니다 ({path}): {exc}",
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


def _marketplace_name(root_dir: Path) -> str:
    """루트가 마켓플레이스 저장소면 그 이름 (``.claude-plugin/marketplace.json``)."""
    mkt = _read_json(root_dir / ".claude-plugin" / "marketplace.json") \
        if (root_dir / ".claude-plugin" / "marketplace.json").is_file() else None
    return str(mkt.get("name", "") or "") if mkt else ""


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


def discover_plugins(root: PluginRoot) -> list[CataloguedPlugin]:
    """루트 하나에서 플러그인(``.claude-plugin/plugin.json`` 보유 디렉토리)을
    찾아 스킬 목록과 함께 돌려준다 (플러그인 이름순 정렬 — 결정적)."""
    root_dir = Path(root.path)
    if not root_dir.is_dir():
        return []
    marketplace = root.marketplace or _marketplace_name(root_dir)

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

    visit(root_dir, 0)
    plugins.sort(key=lambda p: p.name)
    return plugins


def scan_catalog(
    roots: list[PluginRoot] | None = None,
) -> list[tuple[PluginRoot, list[CataloguedPlugin]]]:
    """전체 카탈로그: 등록 순서대로 (루트, 발견된 플러그인들) 쌍 목록."""
    if roots is None:
        roots = load_plugin_roots()
    return [(root, discover_plugins(root)) for root in roots]
