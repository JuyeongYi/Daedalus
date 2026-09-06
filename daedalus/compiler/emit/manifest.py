# daedalus/compiler/emit/manifest.py
"""plugin.json 매니페스트 + schemas.json(블랙보드) + 경로 변수 확장(WP-RT/WP-TG)."""
from __future__ import annotations

import json
from typing import Any

from daedalus.compiler.emit.common import _build_target


# ─────────────────────────── schemas.json (블랙보드) ───────────────────────────


def _field_to_json_schema(fld) -> dict[str, Any]:
    """DynamicField → JSON Schema 속성. CollectionType으로 array 래핑."""
    from daedalus.model.fsm.blackboard import (
        CollectionType,
        FIELD_TYPE_TO_JSON_SCHEMA,
    )
    scalar = dict(FIELD_TYPE_TO_JSON_SCHEMA.get(fld.field_type, {}))
    if fld.collection is CollectionType.LIST:
        return {"type": "array", "items": scalar}
    if fld.collection is CollectionType.SET:
        return {"type": "array", "items": scalar, "uniqueItems": True}
    return scalar


def _class_to_json_schema(cls) -> dict[str, Any]:
    """DynamicClass → JSON Schema object. required는 필드 required 플래그 기준."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for fld in cls.fields:
        prop = _field_to_json_schema(fld)
        if fld.default is not None:
            prop = {**prop, "default": fld.default}
        properties[fld.name] = prop
        if fld.required:
            required.append(fld.name)
    schema: dict[str, Any] = {"type": "object"}
    if cls.description:
        schema["description"] = cls.description
    schema["properties"] = properties
    if required:
        schema["required"] = required
    return schema


def compile_schemas_json(project) -> str | None:
    """프로젝트 최상위 블랙보드의 class_definitions → schemas.json 텍스트.

    각 DynamicClass를 JSON Schema object로 변환해
    ``{"<클래스명>": <schema>}`` 형태로 묶는다 (선언 순서 = 결정적 키 순서).
    class_definitions가 비어 있으면 None (파일 생성 안 함).

    LF·UTF-8 보장 텍스트(끝 개행 1개). json.loads 왕복 가능.
    """
    bb = getattr(project, "blackboard", None)
    classes = getattr(bb, "class_definitions", None) or []
    if not classes:
        return None
    schemas_obj: dict[str, Any] = {}
    for cls in classes:
        schemas_obj[cls.name] = _class_to_json_schema(cls)
    text = json.dumps(schemas_obj, ensure_ascii=False, indent=2)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


# ─────────────────────────── plugin.json (매니페스트) ───────────────────────────


def compile_plugin_manifest(project) -> str:
    """프로젝트 → .claude-plugin/plugin.json 텍스트 (LF, 결정적, 항상 생성).

    키 순서 고정: name → description(빈 문자열이면 키 생략) → version.
    LF·UTF-8 보장 텍스트(끝 개행 1개). json.loads 왕복 가능.
    """
    manifest: dict[str, Any] = {"name": getattr(project, "name", "")}
    description = getattr(project, "description", "") or ""
    if description:
        manifest["description"] = description
    manifest["version"] = getattr(project, "version", "0.1.0")

    # WP-WR — 랩핑 스킬의 소스 플러그인을 의존성으로 선언한다. 키·형식은
    # SchemaStore claude-code-plugin-manifest.json 스키마 확인(2026-09-06):
    # "dependencies": ["name" | "name@marketplace"] — bare name은 자기
    # 마켓플레이스 기준 해소. 이름순 정렬·중복 제거(결정적).
    deps = sorted({
        source.partition(":")[0].strip()
        for skill in getattr(project, "skills", [])
        if getattr(skill, "kind", "") == "wrapped_skill"
        for source in [getattr(getattr(skill, "config", None), "source", "") or ""]
        if source.partition(":")[0].strip() and source.partition(":")[2].strip()
    })
    if deps:
        manifest["dependencies"] = deps

    text = json.dumps(manifest, ensure_ascii=False, indent=2)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


# ─────────────────────────── 로컬 빌드 (WP-TG) ───────────────────────────


def expand_root_token(text: str, project=None) -> str:
    """산출 텍스트의 ``${ROOT}``를 빌드 타깃에 맞는 CC 변수로 확장한다 (WP-RT).

    본문 정본은 타깃 중립 토큰 하나만 쓰고, 어느 CC 변수가 되는지는 여기서
    정해진다 — 마켓플레이스는 ``${CLAUDE_PLUGIN_ROOT}``, 프로젝트 설치는
    ``${CLAUDE_PROJECT_DIR}``. 매핑의 단일 진실은 model/plugin/variables.py.
    """
    from daedalus.model.plugin.variables import expand_root

    return expand_root(text, _build_target(project))
