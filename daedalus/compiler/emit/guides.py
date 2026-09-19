# daedalus/compiler/emit/guides.py
"""공통 안내 파일 (WP-FK2 C3) — `guides/<플러그인>/workflow.md`·`blackboard.md`.

**왜 빼내는가.** 워크플로 개념·진행 기록 규약·재개 규칙·블랙보드 CLI 사용법은
스킬마다 글자 하나 다르지 않은 같은 문장이었다. 배치된 스킬이 열이면 같은 산문이
열 번 산출되고, 그 토큰은 걸릴 때마다 실린다(A12 — 반복은 곧 사용료). 그래서
공통 문장은 파일 둘로 모으고, 각 컴포넌트 산출에는 **포인터 1줄**만 남긴다.

**치환 변수를 쓰지 않는다.** CC의 `${CLAUDE_PLUGIN_ROOT}`/`${CLAUDE_PROJECT_DIR}`
치환은 **스킬·에이전트 content**에서만 일어난다(공식 plugins-reference 치환 표
확인 2026-09-17). 가이드는 모델이 Read 도구로 읽는 평범한 파일이라 토큰이 그대로
리터럴로 보이고, 같은 문서가 "Bash로 실행하는 명령의 환경에도 없다"고 못 박는다.
그래서 가이드 본문의 경로 자리에는 `<SCHEMAS>` 자리표시자를 쓰고, "너를 보낸
스킬/에이전트 파일에 적힌 `--schemas <경로>`를 그대로 쓰라"고 말한다. 대신
**포인터를 받은 컴포넌트 산출에는 확장되는 실제 경로를 가진 명령이 최소 1줄
남는다** — 진행 명령이 없는 컴포넌트(에이전트·fork 에이전트·미배치 스킬)에는
포인터 줄에 `State CLI:` 한 줄을 덧붙여 그것을 보장한다. 이 보장은 **가이드
종류와 무관하다**: 워크플로 가이드도 블랙보드 가이드와 똑같이 "너를 보낸 파일에
적힌 `--schemas` 경로를 쓰라"고 말하므로, 블랙보드 클래스가 없는 프로젝트의
배치 에이전트(워크플로 포인터만 받는다)에도 경로가 남아야 가이드가 거짓을
말하지 않는다(원칙 5).

산출 위치는 두 빌드 타깃 공통으로 루트 직하 `guides/<플러그인>/`이다 — 플러그인
이름으로 네임스페이스를 가르는 것은 `schemas/<플러그인>.json`과 같은 이유(WP-NS)고,
`files/` 밖에 두는 것은 공용 files/ 트리 복사와 섞이지 않게 하기 위해서다.
"""
from __future__ import annotations

from daedalus.compiler import plan_kinds
from daedalus.compiler.emit.common import (
    _graph_placements,
    _graph_placements_any,
    _join_blocks,
    emitted_components,
)
from daedalus.model.plugin.placement import is_edge_placeable, is_reference_placed
from daedalus.model.plugin.roles import BodySource, Bucket, PlacementRole
from daedalus.model.plugin.variables import ROOT_TOKEN

#: 산출 계획 kind — 가이드가 둘이므로 kind도 둘이다(`PlannedOutput`에 구분 필드를
#: 새로 만들지 않는다. kind가 곧 그 행을 쓸 단위의 id다). 문자열의 소유자는
#: `compiler/plan_kinds.py` 하나이고 여기서는 **재-export**한다(WP-5) — 종전
#: 임포트 경로(`from ...emit.guides import WORKFLOW_GUIDE_KIND`)는 무수정이다.
WORKFLOW_GUIDE_KIND = plan_kinds.GUIDE_WORKFLOW
BLACKBOARD_GUIDE_KIND = plan_kinds.GUIDE_BLACKBOARD
GUIDE_KINDS: tuple[str, ...] = plan_kinds.GUIDE_KINDS

GUIDES_DIRNAME = "guides"

#: 가이드 본문에서 `--schemas` 경로가 들어갈 자리. 실제 경로는 포인터를 낸
#: 컴포넌트 파일에 적혀 있다(모듈 docstring 참조).
SCHEMAS_PLACEHOLDER = "<SCHEMAS>"

#: CLI를 못 쓸 때의 폴백. 없앨 수는 없지만(대안이 없다) 위험한 지점을 못 박는다.
#: 예전에는 스킬마다 반복됐다 — 이제 가이드에 한 번만 나온다.
_PROGRESS_MANUAL_FALLBACK = (
    "If `daedalus-bb` is unavailable, edit `state/__progress__.json` by hand — but "
    "change only this plugin's top-level key and leave every other key untouched; "
    "the file is shared with any other Daedalus plugin installed here."
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


# ─────────────────────────── 게이트 ───────────────────────────


def _blackboard_classes(project) -> list:
    bb = getattr(project, "blackboard", None)
    return list(getattr(bb, "class_definitions", None) or [])


def _workflow_guide_available(project) -> bool:
    """워크플로 가이드가 말할 것이 있는가 — 그래프에 배치 노드가 하나라도 있는가."""
    return project is not None and _graph_placements_any(project)


def _blackboard_guide_available(project) -> bool:
    return project is not None and bool(_blackboard_classes(project))


# ─────────────────────────── 포인터 대상 판정 ───────────────────────────


def workflow_pointer_kind(component, project) -> str:
    """이 컴포넌트가 받는 워크플로 가이드 포인터 종류 — "" | "main" | "fork".

    "main"은 **메인 대화에서 도는 배치 컴포넌트**다(배치된 절차형·선언형·state
    용도 랩핑 스킬·워크플로 에이전트, placement가 있는 프로젝트의 전이 스킬).

    fork 스킬은 "fork"다 — 가이드 2·3절("진행 기록을 이렇게 갱신하라", "current가
    다르면 사용자에게 확인하라")은 fork 자신의 "## Report"("진행 파일을 네가
    갱신하지 말라")와 정면으로 충돌하고, fork 서브에이전트는 사용자에게 되물을
    수도 없다. 그래서 보고 양식만 가리키는 전용 줄을 낸다.

    fork 에이전트·랩핑 실행 에이전트·미배치 스킬은 대상이 아니다("").

    **판정은 전부 능력 선언이다**(WP-2c) — 종류를 열거하지 않으므로 새 종류는
    `PLACEMENT`/`RUNS_IN_SUBAGENT`/`IS_FORK_BASE`를 고르는 것으로 합류한다.
    """
    if not _workflow_guide_available(project):
        return ""
    if is_edge_placeable(component):
        # 엣지 스킬은 그래프 노드가 아니다 — 진행 파일을 만드는 배치 스킬이
        # 하나라도 있으면(위 게이트) 지침이 고아가 아니다.
        return "main"
    if not _graph_placements(component, project):
        return ""
    if is_reference_placed(component):
        # 참조 노드는 스스로 워크플로를 진행시키지 않는다. 참조 용도 랩핑
        # 스킬은 산출 파일도 없지만, D1 이전에 만든 `.ddpj`에는 state 노드로
        # 박혀 있을 수 있어 여기까지 도달한다.
        return ""
    if (
        component.BUCKET is Bucket.SKILLS
        and component.RUNS_IN_SUBAGENT
        and component.BODY_SOURCE is BodySource.OWNED
    ):
        # fork 스킬 — 본문이 우리 것이면서 서브에이전트에서 도는 단계.
        return "fork"
    if component.IS_FORK_BASE:
        # fork 실행 기반(fork 에이전트) — 가이드는 그것을 쓰는 fork 스킬이 받는다.
        return ""
    return "main"


def blackboard_pointer_wanted(component, project) -> bool:
    """이 컴포넌트가 블랙보드 가이드 포인터를 받는가.

    오늘 "## Shared State (Blackboard)"가 배출되는 컴포넌트와 같은 집합이다 —
    단계 스킬(fork 2종 포함)·state 용도 랩핑 스킬·에이전트 두 종류. 클래스 정의가
    하나도 없으면 가이드 자체가 없다.

    술어는 **"그래프 노드로 도는 종류인가"**(선언 `PLACEMENT`) ∪ 에이전트
    전부이고, 거기서 **인스턴스**가 참조 노드로 쓰이는 것만 뺀다 — 선언(종류가
    블랙보드 단락을 갖는가)과 상태(이 인스턴스가 참조로 놓였는가)를 나눠 묻는다.
    """
    if not _blackboard_guide_available(project):
        return False
    if is_reference_placed(component):
        return False
    return (
        component.BUCKET is Bucket.AGENTS
        or type(component).PLACEMENT is PlacementRole.STATE
    )


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


def guide_pointer_line(
    component, project, *, has_schema_command: bool = False,
) -> str | None:
    """프론트매터 직후에 들어갈 포인터 블록. 대상이 아니면 None.

    has_schema_command: 이 컴포넌트 산출에 확장되는 `--schemas` 경로를 가진 명령이
    이미 남아 있는가(배치 스킬의 진행 명령). 없으면 `State CLI:` 한 줄을 덧붙여
    가이드의 `<SCHEMAS>` 자리표시자를 채울 실제 경로를 남긴다 — **어느 가이드를
    가리키든** 그렇다(두 가이드 모두 그 경로를 요구한다). 부분 명령만 종류에
    따라 다르다: 블랙보드 가이드를 받으면 상태 읽기/쓰기, 아니면 진행 기록이
    그 경로를 쓰는 유일한 자리다.
    """
    wf = workflow_pointer_kind(component, project)
    bb = blackboard_pointer_wanted(component, project)
    if not wf and not bb:
        return None
    wf_ref = _guide_ref(project, WORKFLOW_GUIDE_KIND)
    bb_ref = _guide_ref(project, BLACKBOARD_GUIDE_KIND)
    bb_clause = f"`{bb_ref}` (shared state and the daedalus-bb CLI)"
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

    if not has_schema_command:
        # 여기 도달했다면 포인터가 하나 이상 나간다(위 조기 반환). 가이드는 둘 다
        # "너를 보낸 파일에 적힌 `--schemas` 경로를 쓰라"고 하므로 경로는 가이드
        # 종류와 무관하게 남긴다. 부분 명령만 갈린다.
        subcommands = "<read|write|validate>" if bb else "progress <read|set>"
        line += (
            f"\nState CLI: `daedalus-bb --schemas {ROOT_TOKEN}/schemas/"
            f"{_plugin(project)}.json {subcommands} ...` — the guide "
            f"explains the subcommands."
        )
    return line


# ─────────────────────────── workflow.md ───────────────────────────


def compile_workflow_guide(project) -> str | None:
    """`guides/<플러그인>/workflow.md` 텍스트. 배치 노드가 없으면 None."""
    if not _workflow_guide_available(project):
        return None
    plugin = _plugin(project)
    cli = f"daedalus-bb --schemas {SCHEMAS_PLACEHOLDER} progress"
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
            "(the step the workflow came from) and `updated` (written by the CLI)."
        ),
        (
            f"Read and update it with the `daedalus-bb` CLI. Wherever "
            f"`{SCHEMAS_PLACEHOLDER}` appears below, use the `--schemas <path>` "
            f"value written in the skill or agent file that sent you here — that "
            f"file spells the real path out:\n"
            f"- `{cli} read` — print this plugin's entry. Exit code 3 means this "
            f"plugin has no entry yet.\n"
            f"- `{cli} set --completed <skill> --current <skill> --prev <skill> "
            f'--note "<text>"` — update it. Every option is optional and only what '
            f"you pass changes; `--completed` may be repeated."
        ),
        (
            "Always name the branch (the output event) in `note`: the receiving "
            "step works out which path it came in on from `prev` plus the branch in "
            "`note`, and without the branch it cannot tell two different outcomes "
            "of the same source apart."
        ),
        (
            "When a branch delegates to an agent, run the update **twice** — "
            "`--current <agent name>` just before delegating, then `--current "
            "<follow-up skill>` once the agent returns (keep `--prev` as the "
            "delegating skill both times)."
        ),
        (
            "A transition skill does not own `current`: it runs on the transition "
            "itself, not at a position in the workflow, so it records only what "
            f'happened during the transition (`{cli} set --note "<what happened>"`) '
            "and leaves `current` as the caller set it."
        ),
        (
            "When a branch hands off to a background fork, that hand-off is still a "
            "hand-off: give `current` to the fork and say so in `note`, then stop "
            "blocking on it — the fork's report says what to record next."
        ),
        _PROGRESS_MANUAL_FALLBACK,
        "## 3. Resume rules",
        (
            f"Run `{cli} read` before starting a step, and act on what it says:\n"
            "- `current` is the skill you were just asked to run → resume it from "
            "where it stopped, using `note` for context.\n"
            "- `current` is a different skill → the workflow is somewhere else. "
            "Stop and confirm with the user before continuing.\n"
            "- `current` is a background fork that is still running → the workflow "
            "is waiting for that fork's report. This is not a case to ask the user "
            "about: say that the fork is still running, leave the progress file "
            "alone, and act on the report when it arrives.\n"
            "- Exit code 3 (no entry for this plugin yet) → the skill you were just "
            f"asked to run is the starting point. Record it: `{cli} set --current "
            "<that skill>`."
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
            "End the report with the progress command the main conversation should "
            "run, already filled in. A background fork states the precondition for "
            "it as well: the main conversation reads the progress record first and "
            "runs the command only while `current` is still that fork."
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
    cli = f"daedalus-bb --schemas {SCHEMAS_PLACEHOLDER}"
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
        "## The daedalus-bb CLI",
        (
            f"Run `command -v daedalus-bb` to check whether the CLI is available "
            f"(this assumes a POSIX shell; if you cannot tell, assume it is missing "
            f"and edit the files directly per the rules below). If it is available, "
            f"do not edit the state files by hand — read and write them through the "
            f"CLI, which validates against the schema before writing. Wherever "
            f"`{SCHEMAS_PLACEHOLDER}` appears below, use the `--schemas <path>` "
            f"value written in the skill or agent file that sent you here:\n"
            f"- `{cli} read <Class>`\n"
            f"- `{cli} write <Class> --set <field>=<value>`\n"
            f"  (use `--append` / `--remove` for collection fields)\n"
            f"- `{cli} validate`\n"
            f"`--schemas` is required, and it also decides where state goes: the "
            f"CLI derives the state directory from the schema filename, so it "
            f"writes under `{state_dir}/`.\n"
            f"`daedalus-bb` ships with Daedalus — do not install any package to "
            f"obtain it."
        ),
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

#: 판정 질문은 "스키마 경로가 산출 어딘가에 보이는가"가 아니라 **"`--schemas
#: <경로>` 형태의 명령이 남아 있는가"**다. 경로만 보고 판정하면 사용자 body가
#: 그 경로를 언급하기만 해도 `State CLI:` 줄이 조용히 사라지고, 가이드의
#: `<SCHEMAS>` 자리표시자를 채울 명령이 그 파일에 하나도 없게 된다(원칙 5).
#: 컴파일러가 `--schemas <경로>`를 배출하는 자리는 `emit/skill.py`의
#: `_progress_cli`와 이 모듈의 `State CLI:` 줄뿐이라 접두를 좁혀도 참 판정이
#: 줄지 않는다.
_SCHEMAS_REF_PREFIX = f"--schemas {ROOT_TOKEN}/schemas/"


def _insert_guide_pointer(blocks: list[str], component, project) -> None:
    """프론트매터 블록 직후(index 1)에 포인터를 끼운다 — 다른 어떤 단락보다 앞.

    `has_schema_command`는 **조립된 블록에서 직접 판정한다** — 질문 자체가
    "확장되는 `--schemas` 경로가 이 산출에 이미 남아 있는가"이므로, 컴포넌트
    종류로 다시 유도하면 산출과 판정이 언젠가 어긋난다.
    """
    has_schema = any(_SCHEMAS_REF_PREFIX in b for b in blocks if b)
    line = guide_pointer_line(component, project, has_schema_command=has_schema)
    if line:
        blocks.insert(1, line)
