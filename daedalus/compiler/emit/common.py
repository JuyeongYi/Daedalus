# daedalus/compiler/emit/common.py
"""emit 패키지 공용 헬퍼 (WP-RF-3a — emit.py 분해, 이동만·동작 불변).

여러 산출 모듈(frontmatter/sections/skill/agent/hooks/manifest)이 함께 쓰는
최소 단위: enum 값 추출, config 선언 기본값 조회, 본문 블록/블록 결합,
빌드 타깃 판정, 프로젝트 그래프 placement 판정.
"""
from __future__ import annotations

from dataclasses import MISSING as _DC_MISSING
from dataclasses import fields as dc_fields
from enum import Enum
from typing import Any

from daedalus.model.plugin.config import ComponentConfig


def _enum_value(v: Any) -> Any:
    """enum이면 .value, 아니면 그대로."""
    return v.value if isinstance(v, Enum) else v


def _config_default(config: ComponentConfig | None, attr: str) -> Any:
    """config 클래스의 선언 기본값(단일 진실)을 반환. 없으면 sentinel."""
    if config is None:
        return _MISSING
    for f in dc_fields(type(config)):
        if f.name == attr:
            if f.default is not _DC_MISSING:
                return f.default
            if f.default_factory is not _DC_MISSING:  # type: ignore[misc]
                return f.default_factory()  # type: ignore[misc]
    return _MISSING


class _Missing:
    pass


_MISSING = _Missing()


# ─────────────────────────── 본문(body) ───────────────────────────


def _body_block(body: str) -> str | None:
    """component.body를 본문 블록 하나로. 공백뿐이면 None(블록 생략).

    앞뒤 개행만 정리한다(내부 서식은 사용자 마크다운 그대로 보존).
    """
    stripped = (body or "").strip("\n")
    if not stripped.strip():
        return None
    return stripped


# ─────────────────────────── 빌드 타깃 판정 ───────────────────────────


def _build_target(project):
    """프로젝트 빌드 타깃. project 미지정이면 MARKETPLACE 취급(하위 호환)."""
    from daedalus.model.plugin.enums import BuildTarget

    if project is None:
        return BuildTarget.MARKETPLACE
    return getattr(project, "build_target", None) or BuildTarget.MARKETPLACE


def _is_local_build(project) -> bool:
    """프로젝트 빌드 타깃이 LOCAL인가. project 미지정이면 MARKETPLACE 취급(하위 호환)."""
    from daedalus.model.plugin.enums import BuildTarget

    return _build_target(project) is BuildTarget.LOCAL


# ─────────────────────────── 프로젝트 그래프 placement ───────────────────────────


def _graph_placements(component, project) -> list:
    """component가 project.graph에 SimpleState로 배치된 노드 목록(identity 비교).

    "다음 단계" 단락(버그 2)과 WP-RS 작업 재개 단락이 공유하는 placement 판정
    로직의 단일 진실.
    """
    graph = getattr(project, "graph", None)
    if graph is None:
        return []
    return [
        s for s in graph.states
        if getattr(s, "skill_ref", None) is component
    ]


def _graph_placements_any(project) -> bool:
    """프로젝트 그래프에 EntryPoint 외 노드(placement)가 하나라도 있으면 True.

    판정의 단일 진실은 Validator._graph_has_placements — 복붙 드리프트 방지를
    위해 위임한다 (리뷰 지적 ⑦).
    """
    graph = getattr(project, "graph", None)
    if graph is None:
        return False
    from daedalus.model.validation import Validator
    return Validator._graph_has_placements(graph)


# ─────────────────────────── 블록 결합 ───────────────────────────


def _join_blocks(blocks: list[str]) -> str:
    """블록 목록을 빈 줄 하나로 구분해 결합하고 끝에 개행 1개. LF 고정."""
    text = "\n\n".join(b for b in blocks if b is not None and b != "")
    # CRLF 잔존 방지
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text
