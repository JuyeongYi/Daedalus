# tests/data/golden/render.py
"""골든 스냅샷의 **계산** 쪽 — 테스트와 재생성기가 공유하는 유일한 산출 경로.

여기가 한 곳이라 "테스트가 보는 것"과 "regen이 쓰는 것"이 어긋날 수 없다
(원칙 1). 저장 형식을 읽고 쓰는 쪽은 :mod:`tests.data.golden.store`,
재생성 진입점은 :mod:`tests.data.golden.regen`다.

**결정성 규약**
  - 경로는 전부 out_dir 기준 상대 POSIX 문자열로 정규화한다(Windows ↔ POSIX).
  - dict는 키 정렬로 저장하고, **순서가 계약인 목록**(plan·written·
    copied_files·findings·skipped)은 정렬하지 않는다 — 그 순서가 골든이다.
  - 텍스트가 없는 파사드(`compile_hooks_json` → None 등)는 해시 대신
    :data:`NO_OUTPUT` 표지를 남긴다. "없음"과 "빈 문자열"이 구분돼야 한다.
"""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from daedalus.compiler.emit import (
    compile_agent,
    compile_hook_scripts,
    compile_hooks_json,
    compile_plugin_manifest,
    compile_schemas_json,
    compile_skill,
)
from daedalus.compiler.emit.guides import GUIDE_KINDS, compile_guide
from daedalus.compiler.emit.wrapped import compile_wrapped_runner
from daedalus.compiler.project_compiler import compile_project
from daedalus.compiler.units import CompileContext, Planner
from daedalus.compiler.workspace import render_rule
from daedalus.model.plugin.skill import WrappedSkill
from daedalus.model.serialize import deserialize_project, serialize_project

from tests.data.golden.corpus import DOGFOOD_JSON, iter_cases

#: 파사드가 "이 프로젝트에는 산출이 없다"고 답했을 때의 표지 (해시 자리).
NO_OUTPUT = "none"


def _digest(text: str | None) -> str:
    if text is None:
        return NO_OUTPUT
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


# ─────────────────────────── 공개 파사드 렌더 ───────────────────────────

def facade_hashes() -> dict[str, str]:
    """REFACTOR_SPEC §8이 지명한 공개 파사드 9종의 산출 텍스트 해시.

    지명 목록과 실제 이름의 대응(전부 실존을 확인했다):
    ``compile_skill`` · ``compile_agent`` · ``compile_wrapped_runner``
    (``compiler.emit.wrapped``) · ``compile_hooks_json`` ·
    ``compile_hook_scripts`` · ``compile_schemas_json`` ·
    ``compile_plugin_manifest`` · ``compile_guide``
    (``compiler.emit.guides``) · ``render_rule`` (``compiler.workspace``).
    """
    out: dict[str, str] = {}
    for corpus, target, project, _kwargs in iter_cases():
        prefix = f"{corpus}/{target}"
        for skill in project.skills:
            out[f"{prefix}/compile_skill/{skill.name}"] = _digest(
                compile_skill(skill, project=project)
            )
            if isinstance(skill, WrappedSkill):
                out[f"{prefix}/compile_wrapped_runner/{skill.name}"] = _digest(
                    compile_wrapped_runner(skill)
                )
        for agent in project.agents:
            out[f"{prefix}/compile_agent/{agent.name}"] = _digest(
                compile_agent(agent, project)
            )
        out[f"{prefix}/compile_hooks_json"] = _digest(compile_hooks_json(project))
        for filename, body in compile_hook_scripts(project):
            out[f"{prefix}/compile_hook_scripts/{filename}"] = _digest(body)
        out[f"{prefix}/compile_schemas_json"] = _digest(compile_schemas_json(project))
        out[f"{prefix}/compile_plugin_manifest"] = _digest(
            compile_plugin_manifest(project)
        )
        for kind in GUIDE_KINDS:
            out[f"{prefix}/compile_guide/{kind}"] = _digest(compile_guide(project, kind))
        for doc in project.rules:
            out[f"{prefix}/render_rule/{doc.name}"] = _digest(render_rule(doc))
    return out


# ─────────────────── compile_project — 산출 파일 · 계획 순서 ───────────────────

def _compile_case(project, kwargs: dict, out_root: Path):
    """계획은 **전체 단위**로 뽑는다 — 파사드(`_plan_outputs`)로는 `out_dir`·
    `files_dir`가 없어 `files_tree`/LOCAL 병합 행이 보이지 않는다(§4-c).
    `compile_project`가 실제로 도는 계획과 같은 것을 스냅샷해야 순서가 계약이다.
    """
    ctx = CompileContext.build(
        project, out_dir=out_root,
        files_dir=kwargs.get("files_dir"),
        skill_files_dir=kwargs.get("skill_files_dir"),
        resolved_hooks=kwargs.get("resolved_hooks"),
        settings_filename=kwargs.get("settings_filename", "settings.json"),
        dry_run=True,
    )
    plan, _gate_errors, _plan_warnings = Planner().plan(ctx)
    result = compile_project(project, out_root, **kwargs)
    return plan, result


def project_hashes_and_plans() -> tuple[dict[str, str], dict[str, dict]]:
    """한 번의 컴파일로 ① 산출 파일 해시 ② 계획·순서 스냅샷을 함께 만든다.

    둘을 따로 돌리면 같은 프로젝트를 두 번 컴파일하게 되고, 그 둘이 어긋나도
    아무도 모른다.
    """
    hashes: dict[str, str] = {}
    plans: dict[str, dict] = {}
    for corpus, target, project, kwargs in iter_cases():
        key = f"{corpus}-{target}"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan, result = _compile_case(project, kwargs, root)
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    hashes[f"{corpus}/{target}/{_rel(path, root)}"] = _digest_bytes(
                        path.read_bytes()
                    )
            plans[key] = {
                # `exclusive`까지 싣는다 — 경로 충돌 게이트·`skipped` 보고의
                # 대상 집합이 곧 이 플래그이고, 그것이 바뀌면 MCP compile_check
                # 응답 형상이 바뀐다(WP-5).
                "plan": [
                    [item.rel_path.as_posix(), item.kind, item.label, item.exclusive]
                    for item in plan
                ],
                "written": [_rel(p, root) for p in result.written],
                "copied_files": [_rel(p, root) for p in result.copied_files],
                "findings": [
                    [error.rule, error.source]
                    for error in list(result.errors) + list(result.warnings)
                ],
                "skipped": [list(entry) for entry in result.skipped],
            }
    return hashes, plans


def facade_and_project_hashes() -> tuple[dict[str, str], dict[str, str], dict[str, dict]]:
    facades = facade_hashes()
    projects, plans = project_hashes_and_plans()
    return facades, projects, plans


# ─────────────────────────── 프로젝트 JSON 골든 ───────────────────────────

def dogfood_project_json() -> str:
    """동결 사본을 로드 → 저장한 텍스트 (앱의 저장 경로와 같은 인자).

    `view/session_io.py`가 쓰는 형식과 같다: ensure_ascii=False, indent=2.
    구버전 포맷이라 로드 시 `_migrate_v1`/fork-split 마이그레이션이 돌고,
    그 결과가 이 스냅샷이다 — 마이그레이션 결과가 바뀌면 여기서 걸린다.
    """
    import json

    data = json.loads(DOGFOOD_JSON.read_text(encoding="utf-8"))
    project = deserialize_project(data)
    return json.dumps(serialize_project(project), ensure_ascii=False, indent=2) + "\n"
