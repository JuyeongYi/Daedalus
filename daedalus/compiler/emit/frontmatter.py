# daedalus/compiler/emit/frontmatter.py
"""프론트매터 렌더 — YAML 스칼라/리스트/블록 표기 + 스킬 프론트매터 줄 생성.

에이전트 프론트매터 조립은 agent.py에 있다(스킬과 매트릭스·키 규약이 다르다).
여기 있는 YAML 표기 헬퍼(`_yaml_scalar`/`_yaml_block_lines`)가 양쪽의 단일 진실.
"""
from __future__ import annotations

import json
import re
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
from daedalus.model.plugin.field_matrix import FieldRule, matrix_for
from daedalus.model.plugin.skill import Skill

# YAML이 boolean/null로 오파싱할 수 있는 예약 스칼라 (YAML 1.1 포함 보수적 집합).
# 문자열 값이 이와 (대소문자 무시) 일치하면 따옴표로 보호한다.
_YAML_RESERVED: frozenset[str] = frozenset({
    "true", "false", "null", "~", "yes", "no", "on", "off", "",
})


# 문자열이 plain으로 쓰이면 YAML이 숫자로 읽는 형태 (정수·실수·지수·16/8진·inf/nan).
_YAML_NUMBER_RE = re.compile(
    r"[-+]?(\d[\d_]*(\.\d*)?|\.\d+)([eE][-+]?\d+)?"
    r"|0x[0-9a-fA-F_]+|0o[0-7_]+|[-+]?\.(inf|Inf|INF)|\.(nan|NaN|NAN)"
)
# plain 스칼라의 첫 글자로 올 수 없는 YAML 지시자.
_YAML_LEADING = frozenset("#-[]{}*&!|>@%`\"',?:")


def _yaml_needs_quotes(s: str, *, flow: bool) -> bool:
    """plain으로 쓰면 뜻이 바뀌거나 파싱이 깨지는가.

    예전 판정은 `": "`와 일부 선두 문자만 봤다 — 설명의 ` #`는 주석으로 잘리고,
    줄바꿈·앞 따옴표·끝 `:`는 파싱 에러, `123`은 숫자가 됐다(2026-09-13 점검, PyYAML 실측).
    """
    if not s or s.lower() in _YAML_RESERVED:
        return True
    if s != s.strip() or any(c in s for c in "\n\r\t"):
        return True
    if s[0] in _YAML_LEADING:
        return True
    if ": " in s or s.endswith(":") or " #" in s:
        return True
    if _YAML_NUMBER_RE.fullmatch(s):
        return True
    # flow 리스트 안에서는 구분자·괄호가 구조로 읽힌다(`Bash(git add, git commit)` 분할).
    return flow and any(c in s for c in ",[]{}")


def _yaml_scalar(v: Any, *, flow: bool = False) -> str:
    """프론트매터 스칼라 값을 YAML 표기로. bool은 true/false, 나머지는 문자열.

    따옴표가 필요할 때만 JSON 문자열로 감싼다 — JSON 문자열은 그대로 올바른 YAML
    큰따옴표 스칼라다(`\\n`·`\\"`·`\\\\` 이스케이프). 필요 없으면 plain 그대로라
    기존 산출은 바뀌지 않는다.
    """
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if _yaml_needs_quotes(s, flow=flow):
        return json.dumps(s, ensure_ascii=False)
    return s


def _yaml_list(values: list[Any]) -> str:
    """flow-style YAML 리스트: [a, b, c]."""
    items = ", ".join(_yaml_scalar(_enum_value(v), flow=True) for v in values)
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
    skill: Skill,
    bb_tools: list[str] | tuple[str, ...] = (),
) -> list[str]:
    """스킬 프론트매터 키-값 줄 목록 (--- 구분선 제외).

    name/description은 항상 출력(REQUIRED). when_to_use는 description에 합류하므로
    여기서는 직출하지 않는다. 나머지는 매트릭스 emit==FRONTMATTER + visibility 규칙.

    ``bb_tools``(WP-BM): 이 스킬의 블랙보드 접근 선언에서 유도된 MCP 도구 이름.
    ``allowed-tools``에 **합류**한다 — 스킬의 그 키는 *권한 부여*라 다른 도구를
    막지 않으므로, 더하는 것이 곧 "이 스킬은 블랙보드를 만질 수 있다"이다.
    유도는 호출자(emitter)가 한다: 이 모듈은 YAML 표기만 안다.
    """
    # 표를 고르는 규칙의 실체는 model의 `matrix_for` 하나다(config.kind가 키).
    matrix = matrix_for(skill)
    config = skill.config
    lines: list[str] = []

    for sfield in SkillField:
        rule = matrix.get(sfield)
        if rule is None:
            # 그 kind에 없는 필드(선언형에 SHELL이 없는 식). 매트릭스가
            # 정의의 단일 진실이므로 부재 = 비적용이다.
            continue
        if rule.emit is not FieldEmit.FRONTMATTER:
            continue
        # hooks는 settings.json 모양의 3단 블록이라 한 줄 키-값으로 낼 수 없다 —
        # compile_skill이 훅 라이브러리를 보고 블록으로 붙인다(2026-09-13).
        if sfield is SkillField.HOOKS:
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
        if sfield is SkillField.ALLOWED_TOOLS and bb_tools:
            declared = list(getattr(config, "allowed_tools", None) or [])
            merged = declared + [t for t in bb_tools if t not in declared]
            lines.append(_format_kv(key, merged))
            continue

        emitted = _emit_skill_field(sfield, rule, config, key)
        if emitted is not None:
            lines.append(emitted)
    return lines


def _emit_skill_field(
    sfield: SkillField,
    rule: FieldRule,
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
    `when_to_use` 필드를 갖는 것은 스킬뿐이지만, 기저 `PluginComponent`가 빈
    문자열을 클래스 속성으로 선언하므로(WP-2a 형상 기본값) 에이전트도 그냥
    읽는다 — getattr 가드가 없어도 값이 같다.
    """
    desc = (component.description or "").strip()
    when = (component.when_to_use or "").strip()
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
