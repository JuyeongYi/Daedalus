# daedalus/compiler/emit/fork.py
"""fork 스킬 산출 (사용자 확정 2026-09-13).

CC의 `context: fork` 스킬은 SKILL.md 본문을 작업 지시로 삼아 `agent` 서브에이전트를
띄운다(실측, CC 2.1.268). 그래서 절차형과 달리:

- `agent:`는 CC가 찾는 이름으로 낸다 — 프로젝트 에이전트는 마켓 빌드에서
  `플러그인:이름`, LOCAL에서 `이름`. 내장·외부 에이전트는 저장된 문자열 그대로
  (정확 일치라 틀리면 조용히 general-purpose로 돈다).
- `background`는 종류가 정한다(사용자 확정 2026-09-17): 동기 fork는 `false`,
  비동기 fork는 `true`. 매트릭스의 FIXED 값이라 배치 여부와 무관하게 **항상**
  배출된다 — 키가 없으면 CC 기본값(백그라운드)으로 돌아 산출이 침묵한다.
- 서브에이전트는 다음 스킬을 부르지도, 진행 기록을 쓰지도 않는다. **보고가
  지시가 된다** — 첫 줄 `EXIT: … / NEXT: …`, 끝에 메인이 실행할 진행 기록 명령.
"""
from __future__ import annotations

from daedalus.compiler.emit.common import _is_local_build
from daedalus.compiler.emit.frontmatter import _format_kv

# 판정의 실체는 모델에 있다(뷰·MCP·컴파일러가 같은 목록을 말해야 한다) —
# 여기는 종전 임포트 경로를 살리는 재-export다.
from daedalus.model.plugin.placement import fork_skills_using  # noqa: F401


def resolve_fork_agent_name(skill, project) -> str:
    """fork 스킬 `agent:`에 적을 이름 — 프로젝트 에이전트만 타깃별로 바꾼다."""
    agent = getattr(skill.config, "agent", "") or "general-purpose"
    if project is None:
        return agent
    if not any(a.name == agent for a in getattr(project, "agents", None) or []):
        return agent
    if _is_local_build(project):
        return agent
    return f"{getattr(project, 'name', '')}:{agent}"


def fork_frontmatter_lines(lines: list[str], skill, project) -> list[str]:
    """매트릭스가 만든 프론트매터 줄에 fork 전용 값을 반영한다.

    하는 일은 `agent:` 이름 해소 하나다 — `context`·`background`는 매트릭스가
    FIXED로 낸다(값의 단일 진실이 표에 있다).
    """
    resolved = _format_kv("agent", resolve_fork_agent_name(skill, project))
    return [resolved if line.startswith("agent:") else line for line in lines]


def fork_report_section(cli: str, branch_lines: str, *, terminal: bool) -> list[str]:
    """배치된 fork 스킬의 "## Report" — Next Steps·진행 기록 규칙을 대신한다.

    cli: `daedalus-bb … progress` 접두. branch_lines: Next Steps와 같은 갈래 목록
    (없으면 ""). terminal: 나가는 전이가 없는 마지막 단계인가.
    """
    intro = (
        "You run in a forked subagent. Do not start the next step and do not "
        "update `state/__progress__.json` — the main conversation does both, "
        "driven by your report."
    )
    if terminal:
        return [
            "## Report",
            intro + "\n\n"
            "This skill is the last step of the workflow. Start your report with "
            "the line `EXIT: done / NEXT: (end)`, and end it with:\n"
            f'- Main conversation: run `{cli} set --completed <this skill> '
            '--current done --note "<result summary>"`.',
        ]
    blocks = ["## Report", intro]
    if branch_lines:
        blocks.append("Pick the branch that matches the outcome:\n" + branch_lines)
    blocks.append(
        "Start your report with one line in the form `EXIT: <branch> / NEXT: "
        "/<skill>` (for a branch that delegates, `NEXT: agent <name>`). End it "
        "with the progress command for the main conversation, filled in:\n"
        f"- Main conversation: run `{cli} set --completed <this skill> "
        '--current <next target> --prev <this skill> --note "<branch> — '
        '<one-line handoff>"`, then continue with NEXT.'
    )
    return blocks
