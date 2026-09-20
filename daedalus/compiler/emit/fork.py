# daedalus/compiler/emit/fork.py
"""fork 스킬 산출 (사용자 확정 2026-09-13).

CC의 `context: fork` 스킬은 SKILL.md 본문을 작업 지시로 삼아 `agent` 서브에이전트를
띄운다(실측, CC 2.1.268). 그래서 절차형과 달리:

- `agent:`는 CC가 찾는 이름으로 낸다 — 프로젝트 fork 에이전트는 마켓 빌드에서
  `플러그인:이름`, LOCAL에서 `이름`. 등록된 **외부** fork 에이전트는 그 컴포넌트의
  `source` 원문(`플러그인:이름`, 타깃 무관), 내장(`general-purpose` 등)은 저장된
  문자열 그대로(정확 일치라 틀리면 조용히 general-purpose로 돈다). 해소 실체는
  `common.agent_invocation_name` 하나다(WP-EX/WP-A).
- `background`는 종류가 정한다(사용자 확정 2026-09-17): 동기 fork는 `false`,
  비동기 fork는 `true`. 매트릭스의 FIXED 값이라 배치 여부와 무관하게 **항상**
  배출된다 — 키가 없으면 CC 기본값(백그라운드)으로 돌아 산출이 침묵한다.
- 서브에이전트는 다음 스킬을 부르지도, 진행 기록을 쓰지도 않는다. **보고가
  지시가 된다** — 첫 줄 `EXIT: … / NEXT: …`, 끝에 메인이 실행할 진행 기록 명령.
- "## Report" 도입 문구는 종류가 가른다(WP-FK2 C1): 동기는 "메인이 기다린다",
  비동기는 "보통은 알림으로 늦게 닿지만 환경에 따라 인라인으로 돌아온다"까지
  말하고, 진행 명령 앞에 `current` 확인 선행 조건 1줄이 붙는다.
"""
from __future__ import annotations

from daedalus.compiler.emit.common import agent_invocation_name
from daedalus.compiler.emit.frontmatter import _format_kv

# 판정의 실체는 모델에 있다(뷰·MCP·컴파일러가 같은 목록을 말해야 한다) —
# 여기는 종전 임포트 경로를 살리는 재-export다.
from daedalus.model.plugin.placement import fork_skills_using  # noqa: F401


def resolve_fork_agent_name(skill, project) -> str | None:
    """fork 스킬 `agent:`에 적을 이름 — **한 줄 파사드**(WP-2c). 없으면 `None`.

    실체는 `common.agent_invocation_name`이다: "누구에게 위임하는가"는
    컴포넌트가(`delegated_agent_name()`), "그 이름을 CC가 어떻게 부르는가"는
    빌드 타깃(또는 외부 정본 원문)이 답한다. fork 스킬이 위임 대상을 갖는
    유일한 종류가 아니므로 해소 규칙이 fork 전용 모듈에만 있으면 다른 위임
    자리에서 복제된다.
    """
    return agent_invocation_name(skill, project)


def fork_frontmatter_lines(lines: list[str], skill, project) -> list[str]:
    """매트릭스가 만든 프론트매터 줄에 fork 전용 값을 반영한다.

    하는 일은 `agent:` 이름 해소 하나다 — `context`·`background`는 매트릭스가
    FIXED로 낸다(값의 단일 진실이 표에 있다).

    **이름이 없으면 그 줄을 지운다**(WP-EX): 등록된 외부 fork 에이전트의
    source가 비었거나 깨진 경우다. 빈 `agent:`를 내면 CC가 조용히
    general-purpose로 돌고, 이름을 지어내면 산출이 없는 에이전트를 지목한다 —
    둘 다 거짓말이라 지시 자체를 빼고 `external_source_missing` 경고가 고칠
    자리를 말하게 한다(원칙 5).
    """
    name = resolve_fork_agent_name(skill, project)
    if name is None:
        return [line for line in lines if not line.startswith("agent:")]
    resolved = _format_kv("agent", name)
    return [resolved if line.startswith("agent:") else line for line in lines]


#: 동기 fork 도입 — 메인이 보고를 기다린다. 사실이 하나뿐이라 조건절이 없다.
_SYNC_INTRO = (
    "You run in a forked subagent. Do not start the next step and do not "
    "update `state/__progress__.json` — the main conversation does both, "
    "driven by your report."
)

#: 비동기 fork 도입 — `background: true`라고 **항상** 비동기로 도는 것이 아니다.
#: 비대화 `claude -p`/Agent SDK, `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, 같은
#: 스킬이 아직 도는 중의 재호출, 스케줄 작업 발화에서는 강제로 인라인 실행된다
#: (공식 문서 2026-09-17 확인). "메인은 기다리지 않는다"고 단정하면 인라인으로
#: 돌아온 경우 메인이 **오지 않을 알림을 기다린다** — 두 경로를 다 말하고 지시는
#: 하나로 준다.
_ASYNC_INTRO = (
    "You run in a forked subagent. The main conversation usually does not wait "
    "for you: your report normally reaches it later as a task notification (in "
    "some environments — non-interactive runs, background tasks disabled, a "
    "re-entrant call — it is delivered inline instead). Either way, do not start "
    "the next step and do not update the progress file yourself."
)


def _async_progress_precondition(read_tool: str, skill_name: str) -> str:
    """비동기 fork 보고의 진행 호출 **앞**에 오는 선행 조건 1줄 — 오케스트레이터 확정 (2026-09-18).

    진행 파일은 플러그인당 항목이 하나라 "지금 도는 비동기 단계"를 적을 자리가
    없다. 그래서 소유권 규약을 3단으로 둔다: ① 호출자가 넘길 때 `current=<이
    fork>`로 소유권을 넘기고(`emit/skill_sections.py` `_async_fork_handoff_note`) ② 보고가
    도착하면 메인이 `current`가 **아직 이 스킬인지** 확인한 뒤에만 갱신하며
    ③ 재개 규칙이 "도는 중인 비동기 fork가 current면 기다리는 중"이라고 말한다.
    이 확인이 없으면 뒤늦게 온 보고가 이미 앞으로 나간 워크플로의 `current`를
    과거로 되돌린다(조용한 실패).
    """
    return (
        f"- Main conversation: call `{read_tool}` first. Only if `current` is still "
        f"`{skill_name}` make the progress call below and continue with NEXT; "
        f"if it moved on, do not touch the progress file — report this result to "
        f"the user and stop."
    )


def fork_report_section(
    set_tool: str, branch_lines: str, *,
    terminal: bool, background: bool, skill_name: str,
    read_tool: str = "",
) -> list[str]:
    """배치된 fork 스킬의 "## Report" — Next Steps·진행 기록 규칙을 대신한다.

    set_tool/read_tool: 진행 기록 MCP 도구 이름(WP-BM). branch_lines: Next Steps와
    같은 갈래 목록(없으면 ""). terminal: 나가는 전이가 없는 마지막 단계인가.
    background: 비동기 fork인가 — 도입 문구와 선행 조건이 갈린다.
    skill_name: 이 스킬의 이름 — 선행 조건이 지목하고, 진행 호출의
    `completed`/`prev` 자리에 그대로 박힌다(한 블록 안에서 이름과
    `<this skill>` 자리표시자를 섞지 않는다 — 통째로 구체적이어야 한다).
    """
    intro = _ASYNC_INTRO if background else _SYNC_INTRO
    pre = (
        _async_progress_precondition(read_tool, skill_name) + "\n"
        if background else ""
    )
    if terminal:
        return [
            "## Report",
            intro + "\n\n"
            "This skill is the last step of the workflow. Start your report with "
            "the line `EXIT: done / NEXT: (end)`, and end it with:\n"
            + pre
            + f'- Main conversation: call `{set_tool}` with '
            f'`completed=["{skill_name}"]`, `current="done"`, '
            '`note="<result summary>"`.',
        ]
    blocks = ["## Report", intro]
    if branch_lines:
        blocks.append("Pick the branch that matches the outcome:\n" + branch_lines)
    blocks.append(
        "Start your report with one line in the form `EXIT: <branch> / NEXT: "
        "/<skill>` (for a branch that delegates, `NEXT: agent <name>`). End it "
        "with the progress call for the main conversation, filled in:\n"
        + pre
        + f'- Main conversation: call `{set_tool}` with '
        f'`completed=["{skill_name}"]`, `current="<next target>"`, '
        f'`prev="{skill_name}"`, `note="<branch> — <one-line handoff>"`, '
        'then continue with NEXT.'
    )
    return blocks
