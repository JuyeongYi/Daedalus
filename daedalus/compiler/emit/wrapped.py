# daedalus/compiler/emit/wrapped.py
"""랩핑 스킬(WP-WR) 산출 — **외부 플러그인 스킬은 서브에이전트에서만 쓴다**.

사용자 확정(2026-09-12): 외부 플러그인 스킬을 메인 컨텍스트에서 직접 인보크하게
두면, 우리 워크플로를 모르는 그 스킬의 지시(다른 스킬로 넘어가라, 계획부터
세워라 …)가 워크플로 한가운데로 새어 들어온다. 그래서 state 용도 랩핑 스킬은
산출이 **둘**이다:

- ``skills/<랩퍼>/SKILL.md`` — 워크플로 단계 그대로(재개·진입 맥락·다음 단계·
  진행 기록). 절차 단락은 "에이전트 `<랩퍼>`에게 위임하라"이고 **외부 스킬을
  직접 인보크하지 말라**고 못 박는다.
- ``agents/<랩퍼>.md`` — 실행 서브에이전트. 프론트매터 ``skills``에 외부 스킬
  (``플러그인:스킬``)을 실어 **시작 시 주입(preload)**한다. 출구(transfer_on)를
  보고 첫 줄에 적게 해 호출자가 다음 단계를 고른다.

실행 에이전트 이름이 랩퍼 이름과 같은 이유: 스킬·에이전트는 이미 한 이름 공간
(`duplicate_component_name`)이라 충돌이 구조적으로 불가능하고, CC에서는 스킬과
에이전트가 서로 다른 도구라 겹치지 않는다. 접미사를 붙이면 사용자 에이전트와
부딪칠 새 경우가 생긴다.

**외부 스킬 이름 해석은 실측했다**(CC 2.1.268 바이너리): 에이전트 ``skills``의
각 이름은 ① 정확한 이름 → ② 에이전트의 플러그인 접두 + 이름 → ③ ``:이름`` 접미
일치 순으로 찾는다. 플러그인 스킬의 명령 이름이 ``플러그인:스킬``이라 ①에서
맞는다. 못 찾거나 ``disable-model-invocation: true``인 스킬은 디버그 로그 경고만
남기고 건너뛰므로, 본문에 "주입되지 않았으면 Skill 도구로 인보크하라" 폴백을 둔다.

모델·effort는 **실행 에이전트 쪽으로 옮긴다** — 일을 하는 컨텍스트가 거기다.
SKILL.md에 남기면 위임만 하는 메인 스레드의 모델이 바뀐다.
"""
from __future__ import annotations

from daedalus.compiler.emit.common import _MISSING, _config_default
from daedalus.compiler.emit.frontmatter import (
    _format_kv,
    _frontmatter_block,
    _yaml_scalar,
)
from daedalus.model.plugin.enums import AgentField, ModelType
from daedalus.model.plugin.roles import BodySource, Bucket, PlacementRole
from daedalus.model.plugin.skill import WrappedSkill


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


def needs_runner_agent(component: object) -> bool:
    """이 컴포넌트가 실행 서브에이전트 산출을 갖는가 — 산출 계획과 절차 단락이
    같은 판정을 쓴다(한쪽만 바뀌면 "위임하라는데 에이전트가 없다"가 된다).

    state 용도 + 활성 + source 형식이 맞는 랩핑 스킬만. 참조 용도는 산출 파일이
    없고(링크된 에이전트의 skills 프론트매터로 주입된다), source가 비면 위임할
    대상이 없다(`external_source_missing`이 짚는다).

    술어는 능력 선언이다(WP-2c): **본문 정본이 외부인 스킬**(`BODY_SOURCE`)이
    **상태 노드로 놓이고**(`effective_placement()`) **켜져 있을 때**
    (`is_active()`) 러너가 필요하다. 컴포넌트가 아닌 값(빈 노드의 `skill_ref`
    등)이 섞여 들어오므로 선언 조회는 `getattr` 폴백으로 관용한다 — 종전
    `isinstance` 사다리와 같은 계약이다.
    """
    if getattr(component, "BUCKET", None) is not Bucket.SKILLS:
        return False
    if getattr(component, "BODY_SOURCE", None) is not BodySource.EXTERNAL:
        return False
    return (
        component.effective_placement() is PlacementRole.STATE
        and component.is_active()
        and bool(external_skill_name(component.external_source or ""))
    )


def _wrapped_procedure_section(skill) -> list[str]:
    """랩핑 스킬 SKILL.md의 절차 단락 — 실행 서브에이전트 위임 지시."""
    if not needs_runner_agent(skill):
        return []
    ext = external_skill_name(skill.config.source)
    plugin, _, skill_name = ext.partition(":")
    return [
        "## Procedure",
        (
            f"This step runs in a subagent. Delegate it to agent `{skill.name}` — "
            f"it has the external skill `/{ext}` (the skill `{skill_name}` from "
            f"plugin `{plugin}`) preloaded and follows it in its own context. Pass "
            f"along the task and whatever context it needs (arguments, relevant "
            f"files, results of earlier steps). Do not invoke `/{ext}` yourself in "
            f"this context. When the agent reports back, the first line of its "
            f"report names the exit it took — continue with the sections below "
            f"(Next Steps, progress record) using that exit."
        ),
    ]


def _wrapped_requirements_section(skill) -> list[str]:
    """랩핑 스킬의 요구 환경 — 소스 플러그인 설치·활성 + MCP 서버 합류.

    `_mcp_requirement_section_skill`과 헤딩이 겹치지 않도록 여기서 한 단락으로
    합쳐 만든다(같은 사실을 두 번 말하지 않는다).
    """
    from daedalus.compiler.emit.sections import _mcp_servers_from_tools

    plugin_id, _skill_name = parse_wrapped_source(skill.external_source or "")
    lines: list[str] = []
    if plugin_id:
        lines.append(
            f"This skill wraps a skill from plugin `{plugin_id}` — that plugin "
            f"must be installed and enabled (settings `enabledPlugins`)."
        )
    servers = _mcp_servers_from_tools(
        getattr(skill.config, "allowed_tools", None)
    )
    if servers:
        names = ", ".join(f"`{x}`" for x in servers)
        lines.append(
            f"This skill requires these MCP servers to be connected: {names}"
        )
    if not lines:
        return []
    return ["## Requirements", "\n\n".join(lines)]


def _runner_frontmatter_lines(skill: WrappedSkill) -> list[str]:
    config = skill.config
    ext = external_skill_name(config.source)
    description = (
        f"Runs the `{skill.name}` workflow step by following the external skill "
        f"/{ext}. Delegated by the `{skill.name}` skill — not for direct use."
    )
    lines = [
        f"{AgentField.NAME.frontmatter_key}: {_yaml_scalar(skill.name)}",
        f"{AgentField.DESCRIPTION.frontmatter_key}: {_yaml_scalar(description)}",
        _format_kv(AgentField.SKILLS.frontmatter_key, [ext]),
    ]
    model = getattr(config, "model", None)
    if model is not None and model is not ModelType.INHERIT:
        lines.append(_format_kv(AgentField.MODEL.frontmatter_key, model))
    effort = getattr(config, "effort", None)
    default_effort = _config_default(config, "effort")
    if effort is not None and (default_effort is _MISSING or effort != default_effort):
        lines.append(_format_kv(AgentField.EFFORT.frontmatter_key, effort))
    return lines


def compile_wrapped_runner(skill: WrappedSkill) -> str:
    """state 용도 랩핑 스킬 → 실행 서브에이전트 .md 텍스트 (LF, 결정적).

    `needs_runner_agent`가 False인 컴포넌트에는 부르지 않는다(산출 계획이 거른다).
    """
    from daedalus.compiler.emit.agent import _exits_section
    from daedalus.compiler.emit.common import _join_blocks

    ext = external_skill_name(skill.config.source)
    blocks: list[str] = [_frontmatter_block(_runner_frontmatter_lines(skill))]
    blocks.append("## Procedure")
    blocks.append(
        f"Your procedure is the external skill `/{ext}`, preloaded into your "
        f"context. Follow its instructions to carry out the task you were given. "
        f"If its content is not in your context, invoke `/{ext}` with the Skill "
        f"tool before doing anything else."
    )
    blocks.append(
        f"You are running one step of a larger workflow on behalf of the "
        f"`{skill.name}` skill. The caller owns that workflow: do not update "
        f"progress records or start other workflow steps — finish this step and "
        f"report back."
    )
    blocks.extend(_exits_section(skill.transfer_on))
    return _join_blocks(blocks)
