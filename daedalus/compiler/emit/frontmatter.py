# daedalus/compiler/emit/frontmatter.py
"""프론트매터 렌더 — YAML 스칼라/리스트/블록 표기 + 스킬 프론트매터 줄 생성.

에이전트 프론트매터 조립은 agent.py에 있다(스킬과 매트릭스·키 규약이 다르다).
여기 있는 YAML 표기 헬퍼(`_yaml_scalar`/`_yaml_block_lines`)가 양쪽의 단일 진실.
"""
from __future__ import annotations

from typing import Any

from daedalus.compiler.emit.common import _MISSING, _config_default, _enum_value
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.config import ComponentConfig
from daedalus.model.plugin.enums import (
    FieldEmit,
    FieldVisibility,
    ModelType,
    SkillField,
)
from daedalus.model.plugin.field_matrix import SKILL_FIELD_MATRIX, FieldRule
from daedalus.model.plugin.skill import Skill

# YAML이 boolean/null로 오파싱할 수 있는 예약 스칼라 (YAML 1.1 포함 보수적 집합).
# 문자열 값이 이와 (대소문자 무시) 일치하면 따옴표로 보호한다.
_YAML_RESERVED: frozenset[str] = frozenset({
    "true", "false", "null", "~", "yes", "no", "on", "off", "",
})


def _yaml_scalar(v: Any) -> str:
    """프론트매터 스칼라 값을 YAML 표기로. bool은 true/false, 나머지는 문자열."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    # YAML 예약 스칼라(true/null/yes/…)는 따옴표로 보호 — boolean/null 오파싱 방지.
    if s.lower() in _YAML_RESERVED:
        return '"' + s + '"'
    # 콜론/특수문자 포함 시 따옴표 — 보수적으로 콜론+공백, 선두 특수문자만 감싼다.
    if (": " in s) or s.startswith(("#", "-", "[", "{", "*", "&", "!", "|", ">", "@")):
        return '"' + s.replace('"', '\\"') + '"'
    return s


def _yaml_list(values: list[Any]) -> str:
    """flow-style YAML 리스트: [a, b, c]."""
    items = ", ".join(_yaml_scalar(_enum_value(v)) for v in values)
    return f"[{items}]"


def _yaml_block_lines(value: Any, indent: int = 0) -> list[str]:
    """중첩 dict/list를 블록 스타일 YAML 줄 목록으로 (WP-LA).

    flow-style(`_yaml_list`)로는 표현할 수 없는 프론트매터 값 — 에이전트의
    ``hooks``(이벤트 → 그룹 → 훅 3단 중첩) 전용이다. 다루는 값은 dict/list/
    스칼라뿐이고, 스칼라 표기는 `_yaml_scalar`를 그대로 쓴다(단일 진실).
    """
    pad = " " * indent
    lines: list[str] = []
    if isinstance(value, dict):
        for key, val in value.items():
            if isinstance(val, (dict, list)) and val:
                lines.append(f"{pad}{key}:")
                lines.extend(_yaml_block_lines(val, indent + 2))
            else:
                lines.append(f"{pad}{key}: {_yaml_scalar(_enum_value(val))}")
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)) and item:
                sub = _yaml_block_lines(item, indent + 2)
                # 첫 줄만 "- "로 끌어올리고 나머지는 그 들여쓰기를 유지한다
                lines.append(f"{pad}- {sub[0].lstrip()}")
                lines.extend(sub[1:])
            else:
                lines.append(f"{pad}- {_yaml_scalar(_enum_value(item))}")
    else:
        lines.append(f"{pad}{_yaml_scalar(_enum_value(value))}")
    return lines


# ─────────────────────────── 스킬 프론트매터 ───────────────────────────


def _frontmatter_lines_skill(
    skill: Skill, kind_key: str,
) -> list[str]:
    """스킬 프론트매터 키-값 줄 목록 (--- 구분선 제외).

    name/description은 항상 출력(REQUIRED). when_to_use는 description에 합류하므로
    여기서는 직출하지 않는다. 나머지는 매트릭스 emit==FRONTMATTER + visibility 규칙.
    """
    matrix = SKILL_FIELD_MATRIX[kind_key]
    config = getattr(skill, "config", None)
    lines: list[str] = []

    for sfield in SkillField:
        rule = matrix[sfield]
        if rule.emit is not FieldEmit.FRONTMATTER:
            continue
        key = sfield.frontmatter_key
        if key is None:  # WHEN_TO_USE — 본문/description 합류
            continue

        if sfield is SkillField.NAME:
            lines.append(f"{key}: {_yaml_scalar(skill.name)}")
            continue
        if sfield is SkillField.DESCRIPTION:
            lines.append(f"{key}: {_yaml_scalar(_compose_description(skill))}")
            continue

        emitted = _emit_skill_field(sfield, rule, skill, config, key)
        if emitted is not None:
            lines.append(emitted)
    return lines


def _emit_skill_field(
    sfield: SkillField,
    rule: FieldRule,
    skill: Skill,
    config: ComponentConfig | None,
    key: str,
) -> str | None:
    """단일 스킬 프론트매터 필드를 YAML 줄로. 생략 시 None."""
    attr = sfield.value  # SkillField.value == config 속성명

    # FIXED — config 무시, fixed_value 강제
    if rule.visibility is FieldVisibility.FIXED:
        return _format_kv(key, rule.fixed_value)

    # config에서 실제 값 읽기
    value = getattr(config, attr, _MISSING) if config is not None else _MISSING
    if value is _MISSING or value is None:
        return None

    # model == INHERIT 이면 키 생략
    if sfield is SkillField.MODEL and value is ModelType.INHERIT:
        return None

    # 빈 컬렉션은 생략
    if isinstance(value, (list, dict)) and not value:
        return None

    # hooks(dict[str, Any]) — 프론트매터에는 참조 이름 목록만 표기(flow-list).
    # 본문 풀이 단락은 두지 않는다 (이름 참조 규약). 라이브러리 실존은 게이트가 검증.
    if sfield is SkillField.HOOKS and isinstance(value, dict):
        return _format_kv(key, list(value.keys()))

    # REQUIRED 외에는 선언 기본값과 같으면 생략(잡음 제거)
    if rule.visibility is not FieldVisibility.REQUIRED:
        default = _config_default(config, attr)
        if default is not _MISSING and value == default:
            return None

    return _format_kv(key, value)


def _format_kv(key: str, value: Any) -> str:
    """키-값 한 줄. 리스트는 flow-list, enum/스칼라는 스칼라."""
    if isinstance(value, list):
        return f"{key}: {_yaml_list(value)}"
    return f"{key}: {_yaml_scalar(_enum_value(value))}"


def _compose_description(component: Skill | AgentDefinition) -> str:
    """description + when_to_use 합류.

    정책 2: description이 있으면 "<description> Use when <when_to_use>".
    description이 비어 있으면 when_to_use만(있을 때). 둘 다 비면 빈 문자열.
    when_to_use는 Skill에만 있으므로 getattr 가드.
    """
    desc = (component.description or "").strip()
    when = (getattr(component, "when_to_use", "") or "").strip()
    if desc and when:
        sep = " " if desc.endswith((".", "!", "?")) else ". "
        return f"{desc}{sep}Use when {when}"
    if desc:
        return desc
    if when:
        return f"Use when {when}"
    return ""


def _frontmatter_block(lines: list[str]) -> str:
    """--- 로 감싼 프론트매터 블록 문자열."""
    body = "\n".join(lines)
    return f"---\n{body}\n---"
