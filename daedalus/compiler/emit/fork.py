# daedalus/compiler/emit/fork.py
"""fork 스킬 산출 (사용자 확정 2026-09-13).

CC의 `context: fork` 스킬은 SKILL.md 본문을 작업 지시로 삼아 `agent` 서브에이전트를
띄운다(실측, CC 2.1.268). 그래서 절차형과 달리:

- `agent:`는 CC가 찾는 이름으로 낸다 — 프로젝트 에이전트는 마켓 빌드에서
  `플러그인:이름`, LOCAL에서 `이름`. 내장·외부 에이전트는 저장된 문자열 그대로
  (정확 일치라 틀리면 조용히 general-purpose로 돈다).
- 배치된 fork는 `background: false` — 기본은 백그라운드라 부른 쪽이 보고를
  기다리지 않는데, 그러면 보고로 분기를 고를 수 없다.
- 서브에이전트는 다음 스킬을 부르지도, 진행 기록을 쓰지도 않는다. **보고가
  지시가 된다** — 첫 줄 `EXIT: … / NEXT: …`, 끝에 메인이 실행할 진행 기록 명령.
"""
from __future__ import annotations

from daedalus.compiler.emit.common import _is_local_build
from daedalus.compiler.emit.frontmatter import _format_kv


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


def fork_skills_using(agent, project) -> list[str]:
    """이 프로젝트 에이전트를 fork 에이전트로 쓰는 fork 스킬 이름 (정렬 — 결정적)."""
    from daedalus.model.plugin.skill import ForkSkill

    return sorted(
        s.name for s in getattr(project, "skills", None) or []
        if isinstance(s, ForkSkill) and s.config.agent == agent.name
    )


def fork_frontmatter_lines(lines: list[str], skill, project, *, placed: bool) -> list[str]:
    """매트릭스가 만든 프론트매터 줄에 fork 전용 값을 반영한다."""
    resolved = _format_kv("agent", resolve_fork_agent_name(skill, project))
    out = [resolved if line.startswith("agent:") else line for line in lines]
    if placed:
        out.append("background: false")
    return out


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
