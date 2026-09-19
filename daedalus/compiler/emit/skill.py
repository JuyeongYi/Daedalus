# daedalus/compiler/emit/skill.py
"""SKILL.md 조립의 **공개 진입점** — `compile_skill` (WP-6 이후 파사드).

텍스트 조립의 실체는 두 곳으로 갈렸다:

- 단락 빌더 → `skill_sections.py` (다음 단계·작업 재개·진입 맥락·진행 기록 잔여)
- 절 순서와 조립 → `section_plan.py` + `emitters.py`

이 모듈은 그 이름들을 **같은 객체로** 재-export하는 파사드다 —
`from daedalus.compiler.emit.skill import compile_skill` 같은 기존 임포트 경로가
무수정으로 동작한다(`tests/compiler/test_emit_facade.py`가 고정한다).
"""
from __future__ import annotations

from daedalus.compiler.emit.emitters import compile_skill  # noqa: F401 — 재-export 파사드
from daedalus.compiler.emit.skill_sections import (  # noqa: F401 — 재-export 파사드
    _ASYNC_FORK_BRANCH_SUFFIX,
    _async_fork_handoff_note,
    _async_fork_targets,
    _entry_context_section,
    _entry_incoming_transitions,
    _entry_item_line,
    _entry_source_ref_name,
    _invoke_phrase,
    _next_step_condition,
    _next_step_invoke_line,
    _next_steps_section,
    _progress_cli,
    _progress_terminal_section,
    _progress_update_note,
    _resume_preamble_section,
    _transfer_prefix,
    _transfer_progress_note,
)
from daedalus.compiler.emit.wrapped import (  # noqa: F401 — 기존 임포트 경로 보존
    parse_wrapped_source,
)
