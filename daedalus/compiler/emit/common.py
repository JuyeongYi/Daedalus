# daedalus/compiler/emit/common.py
"""emit 패키지 공용 헬퍼 (WP-RF-3a — emit.py 분해, 이동만·동작 불변).

여러 산출 모듈(frontmatter/sections/skill/agent/hooks/manifest)이 함께 쓰는
최소 단위: enum 값 추출, config 선언 기본값 조회, 본문 블록/블록 결합,
빌드 타깃 판정, 프로젝트 그래프 placement 판정, **산출 파일 보유 판정**.

마지막 하나(`emits_output_file`)는 emit 밖의 `compiler/units/`도 부른다 —
"누가 산출 파일을 갖는가"의 실체가 계획(plan)과 포인터 판정(guides) 두 벌이면
고아 가이드 파일이나 가리킬 파일이 없는 포인터가 조용히 생긴다(원칙 1).
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


# ─────────────────────────── 산출 파일 보유 판정 ───────────────────────────


def emits_output_file(component) -> bool:
    """이 컴포넌트가 자기 산출 파일(`skills/<이름>/SKILL.md` 또는
    `agents/<이름>.md`)을 갖는가 — **한 줄 파사드**(WP-2c).

    판정의 실체는 컴포넌트 자신의 `emits_output()`이다(`OUTPUT_LOCATION` 선언 ×
    `is_active()`). 여기 남아 있는 것은 컴파일러 어휘의 이름 하나뿐이다 —
    `units.components.ComponentUnit`의 제외 규칙과 `guides`의 포인터 판정이 같은 함수를
    부르는 것이 원래의 목적이었고, 이제는 같은 **메서드**를 부른다.

    종전 사다리가 열거하던 제외 대상(참조 용도·비활성 랩핑 스킬)은
    `WrappedSkill.emits_output()` 오버라이드가 답한다 — 새 종류는 여기를 고치지
    않고 `OUTPUT_LOCATION` 한 줄로 합류한다.
    """
    return component.emits_output()


def emitted_components(project) -> list:
    """산출 파일을 갖는 컴포넌트 — 선언 순서(스킬 → 에이전트)."""
    skills = getattr(project, "skills", None) or []
    agents = getattr(project, "agents", None) or []
    return [c for c in [*skills, *agents] if emits_output_file(c)]


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


# ─────────────────────────── 위임 대상 에이전트 이름 ───────────────────────────


def agent_invocation_name(component, project) -> str:
    """이 컴포넌트의 본문을 실행하는 서브에이전트를 **CC가 찾는 이름** (WP-2c).

    "누구에게 위임하는가"는 컴포넌트가 답하고(`delegated_agent_name()` — fork
    스킬은 `config.agent`, 랩핑 스킬은 자기 이름의 러너), "그 이름을 CC가 어떻게
    부르는가"는 빌드 타깃이 답한다. 둘을 한 함수로 묶어 두면 위임 대상을 갖는
    종류가 늘 때마다 이름 해소 규칙이 복제된다.

    프로젝트 에이전트만 타깃별로 바뀐다 — 마켓 빌드는 `플러그인:이름`, LOCAL은
    `이름`. 내장(`general-purpose`)·외부 에이전트는 저장된 문자열 그대로다
    (정확 일치라 틀리면 조용히 general-purpose로 돈다).

    위임 대상이 없는 종류는 `general-purpose`로 답한다 — 종전
    `resolve_fork_agent_name`의 `or "general-purpose"` 폴백과 같다.
    """
    agent = component.delegated_agent_name() or "general-purpose"
    if project is None:
        return agent
    if not any(a.name == agent for a in getattr(project, "agents", None) or []):
        return agent
    if _is_local_build(project):
        return agent
    return f"{getattr(project, 'name', '')}:{agent}"


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
