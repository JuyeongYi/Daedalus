# daedalus/compiler/emit/agent.py
"""에이전트 .md 조립의 **공개 진입점** — `compile_agent`.

단락 빌더는 `agent_sections.py`로 내려갔다(WP-6, 이동만). 이 모듈은 그 이름을
전부 **재-export**하므로 기존 임포트 경로는 무수정으로 동작한다
(`tests/compiler/test_emit_facade.py`가 고정한다).
"""
from __future__ import annotations

from daedalus.compiler.emit.agent_sections import (  # noqa: F401 — 재-export 파사드
    _agent_delegation_section,
    _agent_hook_groups,
    _agent_mcp_server_names,
    _agent_outputs_section,
    _agent_skills_list,
    _call_contract_section,
    _describe_agent_fsm,
    _emit_agent_field,
    _exits_section,
    _fork_base_contract_section,
    _frontmatter_lines_agent,
    _local_settings_frontmatter_lines,
    _settings_note_agent,
)
from daedalus.compiler.emit.common import _body_block, _join_blocks
from daedalus.compiler.emit.frontmatter import _frontmatter_block
from daedalus.compiler.emit.guides import _insert_guide_pointer
from daedalus.compiler.emit.sections import _blackboard_section, _tool_shelf_section
from daedalus.model.plugin.agent import Agent
from daedalus.model.plugin.hook import HookDef
from daedalus.model.plugin.roles import PlacementRole



def compile_agent(
    agent: Agent, project=None,
    resolved_hooks: dict[str, HookDef] | None = None,
) -> str:
    """에이전트 → agent .md 텍스트 (LF, BOM 없음, 결정적).

    **그래프 유도 단락은 워크플로 에이전트에만 낸다.** fork 에이전트에는 fsm도
    포트도 배치도 없으므로, 가드 없이 부르면 없는 필드를 역참조해 AttributeError로
    죽는다. 판정은 하나(`is_workflow`)다.
    """
    # "그래프 유도 단락을 내는가" = **그래프 노드로 놓이는 에이전트인가**.
    # fork 에이전트는 PLACEMENT=NONE이라 fsm도 포트도 배치도 없다.
    is_workflow = type(agent).PLACEMENT is PlacementRole.STATE
    fm_lines = _frontmatter_lines_agent(agent, project)
    # LOCAL 빌드에서만 hooks/mcpServers가 프론트매터로 나간다 (WP-LA)
    fm_lines.extend(_local_settings_frontmatter_lines(agent, project, resolved_hooks))
    blocks: list[str] = [_frontmatter_block(fm_lines)]

    # 본문(body)
    body_block = _body_block(agent.body)
    if body_block is not None:
        blocks.append(body_block)

    # 호출 계약(WP-CT) — 두 역할이 다른 단락이다: 워크플로 에이전트는 그래프
    # 도착 경로, fork 에이전트는 자기를 실행 기반으로 쓰는 fork 스킬 목록.
    if is_workflow:
        blocks.extend(_call_contract_section(agent, project))
        # 이 에이전트가 부르는 다른 에이전트 (2026-09-12 — CC 중첩 스폰)
        blocks.extend(_agent_delegation_section(agent, project))
    else:
        blocks.extend(_fork_base_contract_section(agent, project))

    # 요구 환경(SETTINGS 언급) — LOCAL 빌드는 프론트매터가 대신하므로 생략된다
    blocks.extend(_settings_note_agent(agent, project))

    if is_workflow:
        # 내부 워크플로 — legacy FSM에 실질 상태가 있을 때만 (WP-AF)
        blocks.extend(_describe_agent_fsm(agent))

        # 출구 — 출력 포트(transfer_on). 호출자 그래프가 이 이름으로 분기한다.
        # fork 에이전트에는 아예 없다(포트가 없다) — 보고 첫 줄은 fork 스킬의
        # `EXIT: … / NEXT: …` 양식이 정하므로 두 지시가 부딪힐 자리가 없어졌다
        # (WP-FK2: 종류가 갈리기 전에는 `_is_fork_agent_only` 휴리스틱이 이 일을
        # 했다 — project=None이면 보호가 되지 않던 판정이다).
        blocks.extend(_agent_outputs_section(agent))

    if project is not None:
        # 링크된 참조 용도 랩핑 스킬은 본문 consult 지시가 아니라 skills
        # 프론트매터로 주입된다(_agent_skills_list 3단계, WP-WR).
        blocks.extend(_tool_shelf_section(project))
        blocks.extend(_blackboard_section(project, agent))

    _insert_guide_pointer(blocks, agent, project)
    return _join_blocks(blocks)

