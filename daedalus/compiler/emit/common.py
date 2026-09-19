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
from daedalus.model.plugin.roles import OutputLocation


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


# ─────────────────────── 외부 스킬 소스 참조 (WP-WR) ───────────────────────
#
# 순수 문자열 파싱이라 여기(리프)에 둔다 — 종전에는 `wrapped.py`에 있었고
# `sections.linked_background_skills`가 **함수 안에서** 그것을 임포트해
# `sections ↔ wrapped` 순환을 만들었다(WP-6에서 해소, `wrapped.py`가 재-export).


def parse_wrapped_source(source: str) -> tuple[str, str]:
    """WP-WR source 참조 `plugin[@marketplace]:skill` → (plugin_id, skill_name).

    형식이 어긋나면 ("", "") — 검증 경고(`external_source_missing`)가 짚고
    emit은 지시 단락을 생략한다(빈 참조로 산출을 오염시키지 않는다).
    """
    if ":" not in (source or ""):
        return "", ""
    plugin_id, _, skill_name = source.partition(":")
    plugin_id, skill_name = plugin_id.strip(), skill_name.strip()
    if not plugin_id or not skill_name:
        return "", ""
    return plugin_id, skill_name


def external_skill_name(source: str) -> str:
    """source → CC 명령 이름 `플러그인:스킬` (마켓 표기 제거). 형식 불일치면 "".

    크로스 플러그인 스킬 지목의 공식 표기는 `/플러그인:스킬`이고 플러그인 이름에
    마켓 표기가 붙지 않는다(공식 문서 확인 2026-09-06 — @마켓은 설치 식별자라
    dependencies/enabledPlugins 전용이다). 에이전트 `skills` 프론트매터도 같은
    이름으로 해석된다(모듈 docstring의 실측).
    """
    plugin_id, skill_name = parse_wrapped_source(source)
    if not skill_name:
        return ""
    return f"{plugin_id.partition('@')[0]}:{skill_name}"


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


# ───────────────────── 그래프 노드에게 위임할 때 쓰는 이름 ─────────────────────


def delegation_target_name(component) -> str | None:
    """그래프에서 **이 노드에게 위임**할 때 CC가 찾는 이름 (WP-9).

    정본이 외부인 노드(외부 플러그인 서브에이전트)는 `플러그인[@마켓]:이름`
    원문이 곧 그 이름이다 — 우리 산출에는 그 이름의 파일이 없고, CC는 설치된
    플러그인에서 정확 일치로 찾는다. 그 밖에는 컴포넌트 이름 그대로다.

    **원문이 비었거나 형식이 깨졌으면 `None`**이다(WP-9 리뷰 반영). 종전에는
    `source or name`이라 노드 이름(`critic`)이나 플러그인 id(`review-pack`)가
    그대로 위임 지시에 실렸는데, 둘 다 CC가 찾을 수 없는 이름이라 산출이 **없는
    에이전트를 지목**했다 — 컴파일은 경고(`external_source_missing`)만 내고
    성공하므로 그 거짓말이 그대로 나간다. 이름이 없으면 지어내지 않는다(원칙 5);
    무엇을 대신 말할지는 부르는 자리가 정한다(`delegate_to_phrase` /
    `delegation_source_label`).

    `agent_invocation_name`과 묻는 것이 다르다: 그쪽은 "이 컴포넌트의 **본문**을
    누가 실행하는가"(fork 스킬의 `agent` 필드)이고, 여기는 "이 **노드 자신**을
    어떻게 부르는가"다. 한 함수로 묶으면 워크플로 에이전트가
    `general-purpose`로 답한다(위임 대상이 없는 종류의 폴백).
    """
    source = component.external_source
    if source is None:
        return component.name
    _plugin_id, ref_name = parse_wrapped_source(source)
    return source if ref_name else None


#: 외부 플러그인 서브에이전트에게 위임할 때 호출자 산출에 붙는 단서 (WP-9).
#:
#: 이 에이전트는 **우리 플러그인이 만든 파일이 아니다** — 워크플로도 블랙보드도
#: 진행 기록 규약도 모른다. 그래서 ① 필요한 맥락을 전부 프롬프트에 담고
#: ② 결과 기록은 호출자가 직접 하며 ③ 어느 갈래로 이어질지도 호출자가 보고를
#: 읽고 고른다. 이 문장이 없으면 부르는 쪽이 "출력 포트 이름으로 끝내라"를
#: 그대로 지시하고, 외부 에이전트는 그 규약을 모른 채 다르게 답한다.
EXTERNAL_DELEGATION_NOTE = (
    "external plugin agent — it knows neither this workflow nor the blackboard: "
    "put everything it needs in the prompt, record the result yourself, and pick "
    "the branch below from its report"
)


def external_delegation_suffix(component) -> str:
    """위임 지시 뒤에 붙는 외부 에이전트 단서 — 해당 없으면 빈 문자열."""
    if type(component).OUTPUT_LOCATION is not OutputLocation.NONE:
        return ""
    return f" ({EXTERNAL_DELEGATION_NOTE})"


#: 부를 이름이 없는 위임 지시 자리에 나가는 문구 (WP-9 리뷰 반영).
#:
#: 없는 이름을 적어 두면 CC는 그 서브에이전트를 못 찾고 조용히 범용으로 돌거나
#: 실패한다 — 어느 쪽이든 왜 그랬는지 알 수 없다. 그래서 산출은 이름 대신
#: **무엇이 비었고 어디를 고쳐야 하는지**를 말하고, 추측하지 말라고 못 박는다.
_UNNAMED_DELEGATION = (
    "cannot delegate — the external plugin agent on node `{node}` has no usable "
    "`source` (`plugin[@marketplace]:name`), so there is no agent name to call: "
    "say so in your report and stop here instead of guessing an agent"
)


def delegate_to_phrase(component, *, note: bool = True) -> str:
    """"이 노드에게 위임하라" 지시 문구 — 이름을 **지어내지 않는다** (WP-9).

    위임 지시를 내는 세 자리("## Next Steps"·"## Delegation"·FSM 절차 래더)가
    공유한다. 같은 노드를 표면마다 다르게 부르면 원칙 1 위반이고, 그중 한 자리만
    깨진 source를 걸러도 나머지가 없는 이름을 내보낸다.

    `note=False`는 단서(`EXTERNAL_DELEGATION_NOTE`)를 붙이지 않는 자리다 —
    legacy 내부 FSM 절차 래더(`emit/sections._describe_node_action`)는 종전부터
    단서 없이 한 줄만 냈고, 붙이면 구버전 프로젝트의 산출 바이트가 바뀐다.
    """
    name = delegation_target_name(component)
    if name is None:
        return _UNNAMED_DELEGATION.format(node=component.name)
    phrase = f"delegate to agent `{name}`"
    if note:
        phrase += external_delegation_suffix(component)
    return phrase


def delegation_source_label(component) -> str:
    """"어디에서 돌아왔는가"를 말하는 서술형 표지 — 진입 맥락 전용 (WP-9).

    지시가 아니라 서술이라 고치라는 말을 담지 않는다. 다만 부를 이름이 없을 때
    노드 이름을 ``agent `critic```으로 내보내면 진입 맥락도 없는 에이전트를
    지목하므로, 그때는 **노드를 가리키는 말**로 바꾼다.
    """
    name = delegation_target_name(component)
    if name is None:
        return f"the external plugin agent on node `{component.name}`"
    return f"agent `{name}`"


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
