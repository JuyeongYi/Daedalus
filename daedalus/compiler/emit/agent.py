# daedalus/compiler/emit/agent.py
"""에이전트 .md 조립의 **공개 진입점** — `compile_agent` (WP-6 이후 파사드).

단락 빌더는 `agent_sections.py`, 절 순서와 조립은 `section_plan.py` +
`emitters.py`다. 이 모듈은 그 이름들을 **같은 객체로** 재-export한다
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
from daedalus.compiler.emit.emitters import compile_agent  # noqa: F401 — 재-export 파사드
