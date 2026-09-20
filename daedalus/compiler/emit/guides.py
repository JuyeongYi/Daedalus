# daedalus/compiler/emit/guides.py
"""공통 안내 파일 (WP-FK2 C3) — `guides/<플러그인>/workflow.md`·`blackboard.md`.

**왜 빼내는가.** 워크플로 개념·진행 기록 규약·재개 규칙·블랙보드 CLI 사용법은
스킬마다 글자 하나 다르지 않은 같은 문장이었다. 배치된 스킬이 열이면 같은 산문이
열 번 산출되고, 그 토큰은 걸릴 때마다 실린다(A12 — 반복은 곧 사용료). 그래서
공통 문장은 파일 둘로 모으고, 각 컴포넌트 산출에는 **포인터 1줄**만 남긴다.

**경로 자리표시자가 사라졌다(WP-BM).** 블랙보드 조작이 CLI에서 MCP 도구로 바뀌면서
가이드가 말해야 할 것이 "경로를 낀 셸 명령"에서 **도구 이름**이 됐다. 도구 이름에는
경로가 없으므로 치환 변수 문제도 없다 — 종전의 `<SCHEMAS>` 자리표시자와 "너를 보낸
파일에 적힌 `--schemas` 경로를 쓰라"는 우회가 통째로 필요 없어졌다. 가이드는 도구
이름을 **그대로** 적고, 포인터 줄은 서버와 도구 접두를 한 줄로 알려 준다
(`Blackboard tools:`). 도구 이름은 빌드 타깃이 가르지만(`blackboard_tools.
bb_tool_prefix`) 가이드 자체가 플러그인마다 산출되므로 리터럴로 적어도 어긋나지
않는다.

산출 위치는 두 빌드 타깃 공통으로 루트 직하 `guides/<플러그인>/`이다 — 플러그인
이름으로 네임스페이스를 가르는 것은 `schemas/<플러그인>.json`과 같은 이유(WP-NS)고,
`files/` 밖에 두는 것은 공용 files/ 트리 복사와 섞이지 않게 하기 위해서다.
"""
from __future__ import annotations

from daedalus.compiler import plan_kinds
from daedalus.compiler.emit.blackboard_names import (
    TOOL_NAMES,
    bb_server_name,
    bb_tool,
    bb_tool_glob,
)
from daedalus.compiler.emit.common import _join_blocks, emitted_components
from daedalus.compiler.emit.pointer_rules import (  # noqa: F401 — 재-export 파사드
    _blackboard_classes,
    _blackboard_guide_available,
    _workflow_guide_available,
    blackboard_pointer_wanted,
    workflow_pointer_kind,
)
from daedalus.model.plugin.variables import ROOT_TOKEN

#: 산출 계획 kind — 가이드가 둘이므로 kind도 둘이다(`PlannedOutput`에 구분 필드를
#: 새로 만들지 않는다. kind가 곧 그 행을 쓸 단위의 id다). 문자열의 소유자는
#: `compiler/plan_kinds.py` 하나이고 여기서는 **재-export**한다(WP-5) — 종전
#: 임포트 경로(`from ...emit.guides import WORKFLOW_GUIDE_KIND`)는 무수정이다.
WORKFLOW_GUIDE_KIND = plan_kinds.GUIDE_WORKFLOW
BLACKBOARD_GUIDE_KIND = plan_kinds.GUIDE_BLACKBOARD
GUIDE_KINDS: tuple[str, ...] = plan_kinds.GUIDE_KINDS

GUIDES_DIRNAME = "guides"

#: 도구가 보이지 않을 때의 지침 (WP-BM). 종전에는 "CLI가 없으면 손으로 고쳐라"
#: 였지만, 손편집이야말로 이 도구들이 막으려던 것이다 — 진행 파일은 플러그인끼리
#: 공유하는 파일이라 한 번의 통째 덮어쓰기가 남의 기록을 지우고, 상태 파일은
#: 스키마 검증 없이 쓰면 다음 단계에서 깨진다. 그래서 **고치지 말고 말하라**.
_TOOLS_MISSING_FALLBACK = (
    "If those tools are not available, the plugin's blackboard MCP server is not "
    "running. Say so and stop — do not edit the state files or the progress file "
    "by hand: they are validated on write and shared with every other Daedalus "
    "plugin installed here, so a hand edit can silently destroy another plugin's "
    "record."
)


def _plugin(project) -> str:
    return getattr(project, "name", "") or "plugin"


def guide_rel_path(project, kind: str) -> str:
    """가이드 kind → 산출 루트 기준 POSIX 상대 경로."""
    base = "workflow.md" if kind == WORKFLOW_GUIDE_KIND else "blackboard.md"
    return f"{GUIDES_DIRNAME}/{_plugin(project)}/{base}"


def _guide_ref(project, kind: str) -> str:
    """컴포넌트 본문이 가리키는 참조 — 타깃 중립 토큰이 붙는다(컴포넌트에서 확장)."""
    return f"{ROOT_TOKEN}/{guide_rel_path(project, kind)}"


def workflow_guide_referenced(project) -> bool:
    """워크플로 가이드를 가리키는 포인터가 하나라도 나가는가 (고아 파일 방지).

    대상 집합은 `emitted_components` — 계획(`_plan_outputs`)이 파일을 내는 집합과
    **같은 함수**다(원칙 1).
    """
    return any(
        workflow_pointer_kind(c, project) for c in emitted_components(project)
    )


def blackboard_guide_referenced(project) -> bool:
    return any(
        blackboard_pointer_wanted(c, project) for c in emitted_components(project)
    )


def guide_pointer_line(component, project) -> str | None:
    """프론트매터 직후에 들어갈 포인터 블록. 대상이 아니면 None.

    포인터를 받는 컴포넌트에는 **어느 도구를 쓰는지** 한 줄이 따라붙는다
    (`Blackboard tools:`). 종전의 `State CLI:` 줄이 조건부였던 이유 — 가이드의
    `<SCHEMAS>` 자리표시자를 채울 실제 경로가 산출 어딘가에 남아야 한다는 것 —
    은 WP-BM으로 사라졌다(도구 이름에는 경로가 없다). 대신 서버 이름을 남긴다:
    도구가 보이지 않을 때 **무엇이 안 떠 있는지** 말할 수 있어야 한다.
    """
    wf = workflow_pointer_kind(component, project)
    bb = blackboard_pointer_wanted(component, project)
    if not wf and not bb:
        return None
    wf_ref = _guide_ref(project, WORKFLOW_GUIDE_KIND)
    bb_ref = _guide_ref(project, BLACKBOARD_GUIDE_KIND)
    bb_clause = f"`{bb_ref}` (shared state and its tools)"
    wf_clause = f"`{wf_ref}` (how this workflow runs, progress record, reports)"

    if wf == "main":
        line = "Before you start, read " + (
            f"{wf_clause} and {bb_clause}." if bb else f"{wf_clause}."
        )
    elif wf == "fork":
        line = (
            f'Read `{wf_ref}` section "Fork reports" for the report format. '
            f"Updating the progress record and the resume rules in that guide "
            f"belong to the main conversation, not to you."
        )
        if bb:
            line += f" Also read {bb_clause}."
    else:
        line = f"Before you start, read {bb_clause}."

    line += (
        f"\nBlackboard tools: `{bb_tool_glob(project)}` "
        f"(MCP server `{bb_server_name(project)}`) — the guide lists them."
    )
    return line


# ─────────────────────────── workflow.md ───────────────────────────


def compile_workflow_guide(project) -> str | None:
    """`guides/<플러그인>/workflow.md` 텍스트. 배치 노드가 없으면 None."""
    if not _workflow_guide_available(project):
        return None
    plugin = _plugin(project)
    read_tool = bb_tool(project, "progress_read")
    set_tool = bb_tool(project, "progress_set")
    blocks: list[str] = [
        f"# {plugin} — Workflow Guide",
        (
            f"Every skill and agent of the `{plugin}` plugin that points here shares "
            f"the rules below. Read this once at the start of a step; the file that "
            f"sent you here carries whatever is specific to that step."
        ),
        "## 1. How this workflow runs",
        (
            "- A **skill** is one step of the workflow. Each step ends on exactly "
            "one **output event**; that event is the branch the workflow takes "
            "next, and the step's \"Next Steps\" section lists the branches.\n"
            "- A **guard** on a branch is a condition that has to hold for that "
            "branch to be the one you take.\n"
            "- A **transition skill** is a short step that runs on the edge "
            "itself. When a branch names one, follow it first, then start the "
            "target step.\n"
            "- A branch can **delegate to an agent**. The agent runs in its own "
            "context and reports back; the caller waits, owns what the agent "
            "produced, and picks the next branch from it.\n"
            "- A **fork skill** runs its step in a forked subagent. A synchronous "
            "fork is waited for; a background fork usually reports back later as a "
            "task notification. Neither one starts the next step or writes the "
            "progress record — its report tells the main conversation what to do "
            "(section 5).\n"
            "- A **declarative skill** is knowledge the step needs, not an action, "
            "and a **reference skill** is a document. **Background skills** are "
            "external skills linked to a step for consultation when their subject "
            "comes up."
        ),
        # 금지는 **쓰기**에만 건다. fork 산출에도 "## Entry Context"가 나가고
        # (emit/skill.py), 그 지시("`prev`와 `note`의 갈래를 확인하라")를
        # 이행할 유일한 수단이 2절의 `progress read`다 — 읽기까지 금지하면 한
        # 산출이 서로 모순되는 두 지시를 동시에 낸다(원칙 5).
        (
            "Sections 2-3 are for the main conversation only. If you are running "
            "inside a forked subagent, do not update the progress record and do "
            "not ask the user anything — you may read the record for your entry "
            "context (section 4), and your outcome goes into your report "
            "(section 5) instead of into the record."
        ),
        "## 2. The progress record",
        (
            "`state/__progress__.json` records where this workflow is. Its "
            "top-level key is the plugin name and the entry under it has "
            "`current` (the step the workflow is on), `completed` (steps already "
            "finished), `note` (free text — put the branch you took here), `prev` "
            "(the step the workflow came from) and `updated` (written for you)."
        ),
        (
            f"Read and update it with these two tools — never by editing the file:\n"
            f"- `{read_tool}` — return this plugin's entry. Error kind "
            f"`not_found` means this plugin has no entry yet.\n"
            f"- `{set_tool}` — update it, with `completed` (a list of step names, "
            f"accumulated without duplicates), `current`, `prev` and `note`. Every "
            f"argument is optional and only what you pass changes. Other plugins' "
            f"entries in the same file are left untouched."
        ),
        (
            "Always name the branch (the output event) in `note`: the receiving "
            "step works out which path it came in on from `prev` plus the branch in "
            "`note`, and without the branch it cannot tell two different outcomes "
            "of the same source apart."
        ),
        (
            "When a branch delegates to an agent, make the update **twice** — "
            "`current=<agent name>` just before delegating, then `current="
            "<follow-up skill>` once the agent returns (keep `prev` as the "
            "delegating skill both times)."
        ),
        (
            "A transition skill does not own `current`: it runs on the transition "
            "itself, not at a position in the workflow, so it records only what "
            f'happened during the transition (`{set_tool}` with `note="<what '
            'happened>"`) and leaves `current` as the caller set it.'
        ),
        (
            "When a branch hands off to a background fork, that hand-off is still a "
            "hand-off: give `current` to the fork and say so in `note`, then stop "
            "blocking on it — the fork's report says what to record next."
        ),
        _TOOLS_MISSING_FALLBACK,
        "## 3. Resume rules",
        (
            f"Call `{read_tool}` before starting a step, and act on what it says:\n"
            "- `current` is the skill you were just asked to run → resume it from "
            "where it stopped, using `note` for context.\n"
            "- `current` is a different skill → the workflow is somewhere else. "
            "Stop and confirm with the user before continuing.\n"
            "- `current` is a background fork that is still running → the workflow "
            "is waiting for that fork's report. This is not a case to ask the user "
            "about: say that the fork is still running, leave the progress file "
            "alone, and act on the report when it arrives.\n"
            "- Error kind `not_found` (no entry for this plugin yet) → the skill "
            "you were just asked to run is the starting point. Record it: "
            f'`{set_tool}` with `current="<that skill>"`.'
        ),
        "## 4. Reading the entry context",
        (
            "`prev` names the step the workflow came from and the branch recorded "
            "in `note` says which of that step's outcomes you are handling — when "
            "one source reaches the same step by several branches, the branch name "
            "in `note` is what picks the right one. After returning from an agent "
            "delegation `prev` holds the delegating skill, not the agent. The "
            '"Entry Context" section of a step lists its incoming paths.'
        ),
        "## 5. Fork reports",
        (
            "A fork skill runs in a forked subagent. It never starts the next step "
            "and never writes the progress record — its report is what drives the "
            "main conversation."
        ),
        (
            "Start the report with one line that names the branch taken and what "
            "comes next:\n"
            "- `EXIT: <branch> / NEXT: /<skill>` — the main conversation invokes "
            "that skill next.\n"
            "- `EXIT: <branch> / NEXT: agent <name>` — that branch delegates to "
            "the named agent.\n"
            "- `EXIT: done / NEXT: (end)` — the workflow ends here."
        ),
        (
            "End the report with the progress call the main conversation should "
            "make, already filled in. A background fork states the precondition for "
            "it as well: the main conversation reads the progress record first and "
            "makes the call only while `current` is still that fork."
        ),
    ]
    return _join_blocks(blocks)


# ─────────────────────────── blackboard.md ───────────────────────────


def compile_blackboard_guide(project) -> str | None:
    """`guides/<플러그인>/blackboard.md` 텍스트. 클래스 정의가 없으면 None."""
    classes = _blackboard_classes(project)
    if not classes:
        return None
    plugin = _plugin(project)
    state_dir = f"state/{plugin}"
    tool = {name: bb_tool(project, name) for name in TOOL_NAMES}
    lines: list[str] = []
    for cls in classes:
        desc = f" — {cls.description}" if cls.description else ""
        lines.append(f"- `{cls.name}` → `{state_dir}/{cls.name}.json`{desc}")
    blocks: list[str] = [
        f"# {plugin} — Shared State Guide",
        (
            f"Every skill and agent of the `{plugin}` plugin that points here shares "
            f"the rules below. The file that sent you here names which of these "
            f"classes that step reads and writes."
        ),
        (
            "State shared across contexts in this workflow lives as JSON files in "
            f"the `{state_dir}/` directory of the working folder. Each file follows "
            f"the schema defined in the plugin's `schemas/{plugin}.json`."
        ),
        "## State files",
        "\n".join(lines),
        "## Blackboard tools",
        (
            f"Never edit these files by hand. The MCP server "
            f"`{bb_server_name(project)}` owns them and validates every write "
            f"against the schema; it also writes atomically and will not overwrite "
            f"a change another context made while you were working. It ships with "
            f"Daedalus — do not install anything to obtain it. The tools your file "
            f"is allowed to use are listed in its own frontmatter:\n"
            f"- `{tool['list']}` — the classes and their fields.\n"
            f"- `{tool['read']}` — one class (`cls`), or one field of it (`field`).\n"
            f"- `{tool['init']}` — create a class's file from the schema.\n"
            f"- `{tool['write']}` — `set` fields, `append`/`remove` elements of "
            f"collection fields. Returns the object after writing.\n"
            f"- `{tool['validate']}` — check the state files against the schema."
        ),
        (
            "A tool that fails returns `{\"ok\": false, \"error\": {...}}` instead "
            "of a value, and `error.kind` says what happened:\n"
            "- `not_found` — that state file does not exist yet. Create it.\n"
            "- `usage` — the class, the field or the value is wrong. `message` "
            "lists what is available; fix the call.\n"
            "- `rejected` — the write was refused and **the file is unchanged**. "
            "`detail` lists the schema violations, or the write kept colliding "
            "with another context's writes."
        ),
        _TOOLS_MISSING_FALLBACK,
        "## Rules",
        (
            "- Always read a state file before changing it (read, modify, write).\n"
            "- If the file does not exist, create it from the schema.\n"
            "- Always fill every field the schema marks as required."
        ),
    ]
    return _join_blocks(blocks)


def compile_guide(project, kind: str) -> str | None:
    """계획 kind → 가이드 텍스트 (쓰기 루프의 단일 진입)."""
    if kind == WORKFLOW_GUIDE_KIND:
        return compile_workflow_guide(project)
    if kind == BLACKBOARD_GUIDE_KIND:
        return compile_blackboard_guide(project)
    raise ValueError(f"가이드 kind가 아닙니다: {kind!r}")


# ─────────────────────────── 포인터 삽입 ───────────────────────────


def _insert_guide_pointer(blocks: list[str], component, project) -> None:
    """프론트매터 블록 직후(index 1)에 포인터를 끼운다 — 다른 어떤 단락보다 앞.

    조립된 블록을 들여다보지 않는다 — 종전에는 "확장되는 `--schemas` 경로가 이
    산출에 이미 남아 있는가"를 블록 텍스트에서 판정했지만, WP-BM으로 경로가
    사라져 그 질문 자체가 없어졌다.
    """
    line = guide_pointer_line(component, project)
    if line:
        blocks.insert(1, line)
