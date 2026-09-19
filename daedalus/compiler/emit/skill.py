# daedalus/compiler/emit/skill.py
"""SKILL.md 조립의 **공개 진입점** — `compile_skill`.

단락 빌더(다음 단계·작업 재개·진입 맥락·진행 기록 잔여)는 `skill_sections.py`로
내려갔다(WP-6, 이동만). 이 모듈은 그 이름들을 전부 **재-export**하므로
`from daedalus.compiler.emit.skill import _next_steps_section` 같은 기존 임포트
경로는 무수정으로 동작한다 — 파사드 완전성은 `tests/compiler/test_emit_facade.py`가
고정한다.

방향: `skill_sections`(아래) → `skill`(위). 조립 표(`section_plan`)가 빌더를
아래에서 임포트하고, `compile_skill`이 그 위의 emitter를 부르기 때문이다
(`tests/compiler/test_emit_import_acyclic.py`).
"""
from __future__ import annotations

from daedalus.compiler.emit.common import (
    _body_block,
    _graph_placements,
    _graph_placements_any,
    _join_blocks,
)
from daedalus.compiler.emit.fork import fork_frontmatter_lines, fork_report_section
from daedalus.compiler.emit.frontmatter import (
    _frontmatter_block,
    _frontmatter_lines_skill,
)
from daedalus.compiler.emit.guides import _insert_guide_pointer
from daedalus.compiler.emit.sections import (
    _background_references_section,
    _blackboard_section,
    _describe_fsm,
    _mcp_requirement_section_skill,
    _tool_shelf_section,
)
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
from daedalus.compiler.emit.wrapped import (  # noqa: F401 — parse_wrapped_source 재노출(기존 임포트 경로)
    _wrapped_procedure_section,
    _wrapped_requirements_section,
    parse_wrapped_source,
)
from daedalus.model.plugin.placement import is_edge_placeable
from daedalus.model.plugin.roles import BodySource, Bucket, PlacementRole
from daedalus.model.plugin.skill import Skill


# ─────────────────────────── 공개: compile_skill ───────────────────────────


def _skill_kind_key(skill: Skill) -> str:
    """Skill 인스턴스 → SKILL_FIELD_MATRIX 키 — **`config.kind`가 단일 진실**이다.

    isinstance 사슬로 문자열을 다시 만들면 클래스와 config가 어긋난 날 두 사실이
    나온다. 표에 없는 kind면 `matrix_for`가 이유를 말하는 ValueError를 낸다.
    """
    from daedalus.model.plugin.field_matrix import matrix_for

    matrix_for(skill)  # 표가 없으면 여기서 이유를 말하고 멈춘다
    return str(skill.config.kind)


def compile_skill(
    skill: Skill,
    *,
    project=None,
    resolved_hooks=None,
) -> str:
    """단일 스킬 → SKILL.md 텍스트 (LF, BOM 없음, 결정적).

    project가 주어지면 tool_shelf 참조 단락을 덧붙인다(ProceduralSkill에 한함).
    """
    kind_key = _skill_kind_key(skill)
    fm_lines = _frontmatter_lines_skill(skill, kind_key)
    # fork 스킬 = **본문이 우리 것이면서 서브에이전트에서 도는 스킬**. 종류를
    # 열거하지 않는다 — 랩핑 스킬도 서브에이전트에서 돌지만 본문의 정본이
    # 외부라(`BODY_SOURCE`) fork 산출 규약(보고가 지시가 된다)을 받지 않는다.
    is_fork = (
        skill.BUCKET is Bucket.SKILLS
        and skill.RUNS_IN_SUBAGENT
        and skill.BODY_SOURCE is BodySource.OWNED
    )
    if is_fork:
        fm_lines = fork_frontmatter_lines(fm_lines, skill, project)
    # 스킬 훅 — 스킬이 활성인 동안만 걸린다(2026-09-13 실측: 플러그인 스킬도 동작).
    # settings.json과 같은 3단 구조라 한 줄 키-값이 아니라 블록으로 낸다.
    from daedalus.compiler.emit.frontmatter import _yaml_block_lines
    from daedalus.compiler.emit.hooks import component_hook_groups

    hook_groups = component_hook_groups(skill, project, resolved_hooks)
    if hook_groups:
        fm_lines.append("hooks:")
        fm_lines.extend(_yaml_block_lines(hook_groups, 2))

    blocks: list[str] = [_frontmatter_block(fm_lines)]

    # 작업 재개 프리앰블(WP-RS) — 프론트매터 직후, 본문 앞. 프로젝트 그래프에
    # 배치된 Procedural/Declarative 스킬에 배출(미배치는 없음).
    # Declarative 포함 이유: 배치되면 "다음 단계"를 받는데 갱신 규칙이 빠지면
    # 그 노드에서 진행 사슬이 끊긴다 (리뷰 지적 ①).
    progress_placements: list = []
    # 진행 사슬에 끼는 것은 **그래프 노드로 놓이는 종류**다(C10 — 종전의 배치
    # 클래스 튜플). 엣지 스킬(전이)·참조 노드 스킬은 자기 placement가 없어
    # 재개 프리앰블·진입 맥락의 대상이 아니다.
    if project is not None and type(skill).PLACEMENT not in (
        PlacementRole.EDGE,
        PlacementRole.REFERENCE,
    ):
        progress_placements = _graph_placements(skill, project)
    if progress_placements:
        # fork 서브에이전트는 사용자에게 확인하거나 진행 기록을 쓸 수 없다 —
        # 재개 판단은 부르는 메인 몫이다.
        if not is_fork:
            blocks.extend(_resume_preamble_section(project, skill.name))
        # 진입 맥락(WP-IC) — 작업 재개 프리앰블 뒤·본문 앞. incoming 전이가
        # 없으면 _entry_context_section이 빈 리스트를 반환(단락 생략).
        blocks.extend(_entry_context_section(skill, project))

    # 본문(body)
    body_block = _body_block(skill.body)
    if body_block is not None:
        blocks.append(body_block)

    # TransferSkill: 전이 도중 중단 대비 note (본문 끝).
    # 진행 파일을 만드는 배치 스킬이 하나도 없는 프로젝트에서는 고아 지시가
    # 되므로 placement 존재를 게이트로 건다 (리뷰 지적 ②).
    if (
        is_edge_placeable(skill)
        and project is not None
        and _graph_placements_any(project)
    ):
        blocks.append("## Progress Record")
        blocks.append(_transfer_progress_note(project))

    # WrappedSkill (WP-WR) — 절차는 실행 서브에이전트 위임 지시(emit/wrapped.py —
    # 외부 스킬은 메인 컨텍스트에서 직접 인보크하지 않는다). FSM 절차·tool_shelf는
    # 없다(본문의 정본이 소스라 여기서 만들 절차가 없다). 블랙보드 단락은
    # placement reads/writes 기반이라 유지.
    if skill.BODY_SOURCE is BodySource.EXTERNAL:
        blocks.extend(_wrapped_procedure_section(skill))
        if project is not None:
            blocks.extend(_blackboard_section(project, skill))

    # 단계 스킬(절차형·fork 2종) = 상태 노드로 놓이면서 본문이 우리 것인 스킬 —
    # FSM 절차 + tool_shelf. 랩핑 스킬은 본문 정본이 외부라 만들 절차가 없고,
    # 전이/참조/선언형은 상태 노드가 아니다.
    if (
        type(skill).PLACEMENT is PlacementRole.STATE
        and skill.BODY_SOURCE is BodySource.OWNED
    ):
        blocks.extend(_describe_fsm(skill.fsm, skill))
        if project is not None:
            blocks.extend(_tool_shelf_section(project))
            blocks.extend(_blackboard_section(project, skill))

    # 배치 노드에 링크된 참조 용도 랩핑 스킬 → consult 지시 (WP-WR).
    # 참조 용도는 산출 파일이 없어 이 단락이 유일한 흔적이다.
    if project is not None:
        blocks.extend(_background_references_section(skill, project))

    # 요구 환경(MCP 서버 자동 언급) — allowed_tools의 mcp__ 접두에서 추출.
    # project 유무와 무관(스킬 자체 config만 참조), "다음 단계" 단락 앞.
    # WrappedSkill은 소스 플러그인 의존까지 합쳐 전용 단락으로(헤딩 중복 방지).
    if skill.BODY_SOURCE is BodySource.EXTERNAL:
        blocks.extend(_wrapped_requirements_section(skill))
    else:
        blocks.extend(_mcp_requirement_section_skill(skill))

    # 프로젝트 그래프 기반 "다음 단계" (버그 2).
    # WP-RS: 배치 스킬이면 다음 단계 단락 끝에 진행 상태 갱신 규칙을 합류시키고,
    # outgoing이 없는 터미널 배치면 "다음 단계" 대신 "작업 완료"를 배출한다.
    # 터미널 판정은 "다음 단계 문구 생성 실패"가 아니라 **placement의 실제
    # outgoing 전이 부재**다 — 타깃이 빈 상태(skill_ref=None)뿐이라 문구가 안
    # 나와도 중간 스킬은 터미널이 아니다 (리뷰 차단 지적).
    if project is not None:
        next_blocks = _next_steps_section(skill, project)
        has_outgoing = any(
            t.source is p
            for p in progress_placements
            for t in getattr(project.graph, "transitions", [])
        )
        if is_fork and progress_placements:
            # 갈래 목록은 Next Steps와 같은 것을 쓰되, 실행 지시가 아니라 보고 양식이다.
            blocks.extend(fork_report_section(
                _progress_cli(project),
                next_blocks[-1] if next_blocks else "",
                terminal=not has_outgoing,
                background=skill.REPORTS_OUT_OF_BAND,
                skill_name=skill.name,
            ))
        elif next_blocks:
            if progress_placements:
                next_blocks = list(next_blocks)
                note = _progress_update_note(project)
                # 비동기 fork로 넘기는 갈래가 있으면 `current` 소유 규약을 덧붙인다
                # (오케스트레이터 확정 2026-09-18 — fork 쪽 선행 조건과 짝을 이룬다).
                bg_targets = _async_fork_targets(skill, project)
                if bg_targets:
                    note += "\n" + _async_fork_handoff_note(
                        _progress_cli(project), bg_targets,
                    )
                next_blocks[-1] = next_blocks[-1] + "\n\n" + note
            blocks.extend(next_blocks)
        elif progress_placements and not has_outgoing:
            blocks.extend(_progress_terminal_section(project))

    _insert_guide_pointer(blocks, skill, project)
    return _join_blocks(blocks)
