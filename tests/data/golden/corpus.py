# tests/data/golden/corpus.py
"""골든 코퍼스 — 리팩토링 안전망이 렌더하는 두 벌의 프로젝트 (WP-0).

두 벌인 이유(REFACTOR_SPEC §8): 실사용 프로젝트 하나만으로는 산출 경로가
0줄로 남는 종류가 있다 — dogfood(`project/daedalus_cc_plugin/`)의 랩핑 스킬
9개는 **전부 usage=reference**라 `compile_wrapped_runner`·state 용도 랩핑
스킬이 한 번도 돌지 않고, async fork 스킬도 없다.

① **dogfood** — 실사용 프로젝트의 **동결 사본**(`dogfood.daedalus.json`).
   살아 있는 작업 사본(`project/daedalus_cc_plugin/.daedalus.json`)은 **읽지
   않는다**: 사용자가 편집하면 골든이 무작위로 깨진다. 사본은 이 폴더에
   커밋돼 있고 갱신은 명시적인 재생성(regen)으로만 한다.

   **출처(2026-09-19)**: 이 사본은 그 시점의 **아직 커밋되지 않은 작업 사본**
   에서 떴다(HEAD의 `project/daedalus_cc_plugin/.daedalus.json`이 아니다 —
   당시 작업 사본은 HEAD 대비 +1570/-317줄이었고, 종류·훅 커버리지가 더 넓어
   안전망으로 쓸모가 많다). 그래서 이 파일의 내용은 리포 안 다른 어디에도
   없다. 나중에 `--refresh-dogfood`를 돌렸을 때 나오는 큰 diff를 직렬화
   회귀로 오해하지 말 것 — 사용자가 그 작업 사본을 커밋하면 그때 다시 떠서
   출처를 git 이력으로 되돌리면 된다.

② **synthetic** — 여기서 조립하는 합성 프로젝트. 9종 전부 ×
   (배치/미배치) × (블랙보드 유/무) × 랩핑 스킬 3상태(state/reference/
   enabled=False) × async fork × fork 에이전트 × **훅을 가진 ReferenceSkill**
   (D6 수정이 산출을 바꾸는 자리 — 골든 diff로 보이게 한다).

**결정성 규약.** dataclass의 `id`는 uuid4 기본값이라 실행마다 다르다. 산출
텍스트에는 나가지 않지만, 한 번이라도 새면 골든이 무작위로 깨진다 — 그래서
조립이 끝난 프로젝트를 `_stamp_ids`가 선언 순서대로 훑어 결정적 id로 덮는다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterator

from daedalus.model.fsm.blackboard import Blackboard, DynamicClass, DynamicField
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.variable import FieldType
from daedalus.model.plugin.agent import AgentDefinition, ForkAgent
from daedalus.model.plugin.config import (
    AgentConfig,
    AsyncForkSkillConfig,
    DeclarativeSkillConfig,
    ForkAgentConfig,
    ProceduralSkillConfig,
    ReferenceSkillConfig,
    SyncForkSkillConfig,
    TransferSkillConfig,
    WrappedSkillConfig,
)
from daedalus.model.plugin.enums import (
    AgentColor,
    BuildTarget,
    EffortLevel,
    ModelType,
    PermissionMode,
)
from daedalus.model.plugin.hook import CommandHook, HookDef, HookEvent
from daedalus.model.plugin.skill import (
    AsyncForkSkill,
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    SyncForkSkill,
    TransferSkill,
    WrappedSkill,
)
from daedalus.model.plugin.workspace_doc import WorkspaceDoc
from daedalus.model.project import PluginProject, ReferencePlacement
from daedalus.model.serialize import deserialize_project

GOLDEN_DIR = Path(__file__).resolve().parent

#: 동결 사본. 살아 있는 `project/daedalus_cc_plugin/.daedalus.json`이 아니다.
DOGFOOD_JSON = GOLDEN_DIR / "dogfood.daedalus.json"

#: 복사 계획(`files_tree`/`skill_file`)을 태우는 ASCII 전용 트리.
TREES_DIR = GOLDEN_DIR / "trees"
FILES_DIR = TREES_DIR / "files"
SKILL_FILES_DIR = TREES_DIR / "skill-files"


# ─────────────────────────── 결정적 id 스탬프 ───────────────────────────

def _iter_machine_objects(machine: StateMachine | None) -> Iterator[object]:
    if machine is None:
        return
    yield machine
    for state in machine.states:
        yield state
        for region in getattr(state, "regions", []) or []:
            yield region
            for sub in getattr(region, "states", []) or []:
                yield sub
    for transition in machine.transitions:
        yield transition


def _iter_stampable(project: PluginProject) -> Iterator[object]:
    """선언 순서 = 스탬프 순서. 이 순서가 바뀌면 id도 바뀐다(의도)."""
    for component in list(project.skills) + list(project.agents):
        yield component
        yield from _iter_machine_objects(getattr(component, "fsm", None))
    yield from _iter_machine_objects(project.graph)
    for hook in project.hook_library:
        yield hook
    for tool in project.tool_shelf:
        yield tool
    if project.claude_md is not None:
        yield project.claude_md
    for rule in project.rules:
        yield rule


def _stamp_ids(project: PluginProject, prefix: str) -> PluginProject:
    """uuid4 기본값을 결정적 id로 덮는다 — 골든이 실행마다 흔들리지 않게."""
    for index, obj in enumerate(_iter_stampable(project)):
        if hasattr(obj, "id"):
            obj.id = f"{prefix}{index:016x}"
    return project


# ─────────────────────────── 합성 코퍼스 ───────────────────────────

_PLUGIN_SOURCE = "ext-pack:outer-skill"


def _blackboard() -> Blackboard:
    return Blackboard(class_definitions=[
        DynamicClass(
            name="TaskState",
            description="the unit of work in flight",
            fields=[
                DynamicField(name="step", field_type=FieldType.INT, required=True),
                DynamicField(name="note", field_type=FieldType.STRING),
            ],
        ),
        DynamicClass(
            name="ReviewFindings",
            description="what the reviewer found",
            fields=[DynamicField(name="blocking", field_type=FieldType.BOOL)],
        ),
    ])


def _skill_fsm(name: str) -> StateMachine:
    first = SimpleState(name="analyze")
    second = SimpleState(name="report")
    machine = StateMachine(
        name=f"{name}_fsm", initial_state=first, states=[first, second],
        final_states=[second],
    )
    machine.transitions.append(
        Transition(source=first, target=second, trigger=CompletionEvent(name="done"))
    )
    return machine


def _agent_fsm(name: str) -> StateMachine:
    entry = EntryPoint(name="entry")
    work = SimpleState(name="work")
    done = ExitPoint(name="done")
    machine = StateMachine(
        name=f"{name}_fsm", initial_state=entry, states=[entry, work, done],
        final_states=[done],
    )
    machine.transitions.append(Transition(source=entry, target=work))
    machine.transitions.append(
        Transition(source=work, target=done, trigger=CompletionEvent(name="done"))
    )
    return machine


def _hook_library() -> list[HookDef]:
    """훅 라이브러리 4종. 마지막 `ref-only`는 **D6 관측점**이다.

    `emitted_hooks`는 라이브러리 소유 훅을 `enabled` 스위치로 거르므로
    `enabled=False`인 훅은 전역 배출 경로로 들어오지 않는다. 그래서 이 훅의
    스크립트가 산출되는 유일한 길은 `hooks_needing_scripts`의 **스킬 루프**뿐이고,
    오늘은 그 루프의 `is_reference_usage` 게이트가 참조 용도 스킬을 건너뛴다.
    D6(게이트 제거)이 들어오면 `ref-only.sh`가 새로 나타나 골든 해시가 움직인다 —
    `enabled=True`인 훅(guard-bash 등)만 참조하면 그 변화가 통째로 가려진다.
    """
    return [
        HookDef(
            name="guard-bash", description="Bash 호출 감시",
            event=HookEvent.PRE_TOOL_USE, matcher="Bash",
            handlers=[CommandHook(script="echo guard")],
        ),
        HookDef(
            name="fmt-on-edit", description="편집 후 포맷",
            event=HookEvent.POST_TOOL_USE, matcher="Edit|Write",
            handlers=[CommandHook(script="echo format", timeout=30)],
        ),
        HookDef(
            name="notify-stop", description="종료 알림",
            event=HookEvent.STOP,
            handlers=[CommandHook(script="echo stop")],
        ),
        HookDef(
            name="ref-only", description="참조 용도 스킬만 참조하는 훅",
            event=HookEvent.STOP,
            handlers=[CommandHook(script="echo ref")],
            enabled=False,
        ),
    ]


def _components() -> dict[str, object]:
    """9종 전수 + 랩핑 스킬 3상태. 이름은 산출 이름 규약을 통과한다."""
    return {
        "procedural": ProceduralSkill(
            fsm=_skill_fsm("placed-procedural"),
            name="placed-procedural",
            description="Runs the first workflow step",
            when_to_use="the workflow starts",
            config=ProceduralSkillConfig(
                model=ModelType.SONNET, effort=EffortLevel.MEDIUM,
                allowed_tools=["Read", "Write"], argument_hint="<target>",
            ),
            body=(
                "# Instructions\n\nRead <${ROOT}/files/docs/reference.md> and the "
                "bundled ${CLAUDE_SKILL_DIR}/readme.txt, then do the work.\n"
            ),
            transfer_on=[EventDef("done", description="finished the step")],
            call_agents=[EventDef("ask-worker", description="needs the worker agent")],
        ),
        "sync_fork": SyncForkSkill(
            fsm=_skill_fsm("sync-fork"),
            name="sync-fork",
            description="Delegates a bounded task and waits",
            when_to_use="a sub-task must finish before continuing",
            config=SyncForkSkillConfig(model=ModelType.INHERIT, agent="fork-base"),
            body="# Instructions\n\nDelegate and wait for the report.\n",
            transfer_on=[EventDef("ok"), EventDef("failed")],
        ),
        "async_fork": AsyncForkSkill(
            fsm=_skill_fsm("async-fork"),
            name="async-fork",
            description="Delegates a long task and moves on",
            when_to_use="the sub-task may take a while",
            config=AsyncForkSkillConfig(model=ModelType.HAIKU, agent="general-purpose"),
            body="# Instructions\n\nStart the background job.\n",
            transfer_on=[EventDef("started")],
        ),
        "declarative": DeclarativeSkill(
            name="knowledge",
            description="Background knowledge for the plugin",
            when_to_use="reasoning about the domain",
            body="# Knowledge\n\nFacts live here.\n",
            config=DeclarativeSkillConfig(user_invocable=True),
        ),
        "transfer": TransferSkill(
            fsm=_skill_fsm("edge-helper"),
            name="edge-helper",
            description="Runs while crossing an edge",
            when_to_use="a transition needs preparation",
            body="# Instructions\n\nPrepare the handover.\n",
            config=TransferSkillConfig(),
        ),
        # §8 골든 행 — 훅을 가진 ReferenceSkill. D6(emit/hooks.py의 두 루프
        # 통합)이 산출을 바꾸는 자리라 골든 diff로 드러나야 한다.
        # `ref-only`(enabled=False)가 그 관측점이다 — `_hook_library` docstring 참조.
        "reference": ReferenceSkill(
            name="ref-with-hooks",
            description="Reference document that also declares hooks",
            when_to_use="looking up the contract",
            body="# Contract\n\nReference body.\n",
            config=ReferenceSkillConfig(hooks={"guard-bash": {}, "ref-only": {}}),
        ),
        "wrapped_state": WrappedSkill(
            fsm=_skill_fsm("wrapped-state"),
            name="wrapped-state",
            description="Wraps an external skill as a workflow step",
            when_to_use="the external procedure is the step",
            config=WrappedSkillConfig(source=_PLUGIN_SOURCE, usage="state", enabled=True),
            transfer_on=[EventDef("done")],
        ),
        "wrapped_reference": WrappedSkill(
            fsm=_skill_fsm("wrapped-reference"),
            name="wrapped-reference",
            description="Wraps an external skill as a reference node",
            when_to_use="the external document is consulted",
            config=WrappedSkillConfig(
                source=_PLUGIN_SOURCE, usage="reference", enabled=True,
            ),
            transfer_on=[EventDef("done")],
        ),
        "wrapped_disabled": WrappedSkill(
            fsm=_skill_fsm("wrapped-off"),
            name="wrapped-off",
            description="Wrapped skill that is switched off",
            when_to_use="never — it is disabled",
            config=WrappedSkillConfig(
                source="ext-pack:retired-skill", usage="state", enabled=False,
            ),
            transfer_on=[EventDef("done")],
        ),
        "agent": AgentDefinition(
            fsm=_agent_fsm("worker"),
            name="worker",
            description="Workflow agent node",
            config=AgentConfig(
                model=ModelType.SONNET, tools=["Read", "Grep"],
                permission_mode=PermissionMode.ACCEPT_EDITS,
                skills=["knowledge"], mcp_servers=["golden-server"],
                color=AgentColor.BLUE, hooks={"fmt-on-edit": {}},
            ),
            body="# instruction\n\nDo the agent work.\n",
            transfer_on=[EventDef("done", color="#cc6666")],
            call_agents=[EventDef("escalate")],
        ),
        "fork_agent": ForkAgent(
            name="fork-base",
            description="Execution base for the sync fork skill",
            config=ForkAgentConfig(model=ModelType.OPUS, color=AgentColor.GREEN),
            body="# instruction\n\nRun the delegated task.\n",
        ),
    }


def _place(project: PluginProject, parts: dict[str, object], *, blackboard: bool) -> None:
    """그래프 배치 — 상태 노드 · 전이 엣지 스킬 · 참조 노드."""
    graph = project.graph
    start = graph.initial_state
    reads = ["TaskState"] if blackboard else []
    writes = ["ReviewFindings"] if blackboard else []

    node_procedural = SimpleState(
        name="placed-procedural", skill_ref=parts["procedural"],
        reads=reads, writes=writes,
    )
    node_sync = SimpleState(name="sync-fork", skill_ref=parts["sync_fork"])
    node_async = SimpleState(name="async-fork", skill_ref=parts["async_fork"])
    node_agent = SimpleState(name="worker", skill_ref=parts["agent"])
    node_wrapped = SimpleState(name="wrapped-state", skill_ref=parts["wrapped_state"])
    node_know = SimpleState(name="knowledge", skill_ref=parts["declarative"])
    graph.states += [
        node_procedural, node_sync, node_async, node_agent, node_wrapped, node_know,
    ]

    graph.transitions.append(Transition(source=start, target=node_procedural))
    graph.transitions.append(Transition(
        source=node_procedural, target=node_sync,
        trigger=CompletionEvent(name="done"), skill_ref=parts["transfer"],
    ))
    graph.transitions.append(Transition(
        source=node_sync, target=node_async, trigger=CompletionEvent(name="ok"),
    ))
    graph.transitions.append(Transition(
        source=node_sync, target=node_agent, trigger=CompletionEvent(name="failed"),
    ))
    graph.transitions.append(Transition(
        source=node_async, target=node_wrapped, trigger=CompletionEvent(name="started"),
    ))
    graph.transitions.append(Transition(
        source=node_procedural, target=node_agent,
        trigger=CompletionEvent(name="ask-worker"),
    ))

    project.reference_placements = [
        ReferencePlacement(
            skill_name="ref-with-hooks", x=10.0, y=20.0,
            connected_states=["placed-procedural", "worker"],
        ),
        ReferencePlacement(
            skill_name="wrapped-reference", x=30.0, y=40.0,
            connected_states=["placed-procedural"],
        ),
    ]


def build_synthetic(*, placed: bool, blackboard: bool) -> PluginProject:
    """합성 코퍼스 1벌. build_target은 호출자가 고른다(두 타깃 모두 렌더)."""
    parts = _components()
    project = PluginProject(
        name="golden",
        description="Synthetic golden corpus covering every component kind",
        version="1.2.3",
        skills=[
            parts["procedural"], parts["sync_fork"], parts["async_fork"],
            parts["declarative"], parts["transfer"], parts["reference"],
            parts["wrapped_state"], parts["wrapped_reference"], parts["wrapped_disabled"],
        ],
        agents=[parts["agent"], parts["fork_agent"]],
        hook_library=_hook_library(),
        blackboard=_blackboard() if blackboard else Blackboard(),
        claude_md=WorkspaceDoc(
            name="Golden", body="Workspace note for the golden corpus.\n",
        ),
        rules=[WorkspaceDoc(
            name="golden-rule",
            body="Always check the golden snapshot.\n",
            paths=["src/**/*.py"],
        )],
        mcp_server_defs={"golden-server": {"type": "http", "url": "http://127.0.0.1:9/mcp"}},
        # "ext-pack"은 랩핑 스킬 source의 플러그인 id와 정확히 일치해 배선이
        # 나가고, "spare-pack@golden-market"은 선언만 되어 있어
        # unused_external_plugin 경고를 태운다(경고 순서도 골든이다).
        external_plugins=["ext-pack", "spare-pack@golden-market"],
        workspace_settings={"cleanupPeriodDays": 7},
        build_target=BuildTarget.MARKETPLACE,
    )
    if placed:
        _place(project, parts, blackboard=blackboard)
    suffix = f"{'p' if placed else 'u'}{'b' if blackboard else 'n'}"
    return _stamp_ids(project, f"golden{suffix}")


def build_gate_failure() -> PluginProject:
    """게이트 실패 코퍼스 — `skipped` 목록을 스냅샷하기 위한 최소 프로젝트.

    이름 규약 위반(`Bad Name`) + 산출 경로 충돌(같은 이름의 스킬 둘)을 한꺼번에
    태운다. `compile_project`는 파일을 하나도 쓰지 않고 계획 전체를 skipped로
    보고해야 한다.
    """
    def _proc(name: str) -> ProceduralSkill:
        return ProceduralSkill(
            fsm=_skill_fsm(name), name=name, description="d", when_to_use="w",
            config=ProceduralSkillConfig(), body="# Instructions\n\nWork.\n",
            transfer_on=[EventDef("done")],
        )

    project = PluginProject(
        name="golden",
        skills=[_proc("Bad Name"), _proc("dupe"), _proc("dupe")],
        agents=[AgentDefinition(
            fsm=_agent_fsm("aide"), name="aide", description="d",
            config=AgentConfig(), body="# instruction\n\nWork.\n",
            transfer_on=[EventDef("done")],
        )],
        build_target=BuildTarget.MARKETPLACE,
    )
    return _stamp_ids(project, "goldengate")


# ─────────────────────────── dogfood 코퍼스 ───────────────────────────

def load_dogfood() -> PluginProject:
    """동결 사본을 읽어 프로젝트로 만든다 (살아 있는 작업 사본은 읽지 않는다)."""
    data = json.loads(DOGFOOD_JSON.read_text(encoding="utf-8"))
    return deserialize_project(data)


# ─────────────────────────── 코퍼스 목록 ───────────────────────────

#: (이름, 팩토리, compile_project 추가 인자). **순서가 골든 키 순서**다.
CORPORA: tuple[tuple[str, Callable[[], PluginProject], dict], ...] = (
    # dogfood는 트리 인자를 주지 않는다 — 실사용 폴더의 skill-files/에는
    # 사람이 흘린 비ASCII 스크래치 파일만 있어, 복사 골든에 넣으면 플랫폼별
    # 유니코드 정규화에 따라 해시가 흔들린다. 복사 경로(files_tree/skill_file)는
    # ASCII 전용 trees/를 쓰는 합성 코퍼스가 전담한다.
    ("dogfood", load_dogfood, {}),
    ("synthetic-placed-bb", lambda: build_synthetic(placed=True, blackboard=True),
     {"files_dir": FILES_DIR, "skill_files_dir": SKILL_FILES_DIR}),
    ("synthetic-placed-nobb", lambda: build_synthetic(placed=True, blackboard=False),
     {"files_dir": FILES_DIR, "skill_files_dir": SKILL_FILES_DIR}),
    ("synthetic-unplaced-bb", lambda: build_synthetic(placed=False, blackboard=True),
     {"files_dir": FILES_DIR, "skill_files_dir": SKILL_FILES_DIR}),
    ("synthetic-unplaced-nobb", lambda: build_synthetic(placed=False, blackboard=False),
     {"files_dir": FILES_DIR, "skill_files_dir": SKILL_FILES_DIR}),
    ("gate-failure", build_gate_failure, {}),
)

#: 두 빌드 타깃 모두 렌더한다 (MARKETPLACE ↔ LOCAL은 산출 구조가 다르다).
TARGETS: tuple[tuple[str, BuildTarget], ...] = (
    ("marketplace", BuildTarget.MARKETPLACE),
    ("local", BuildTarget.LOCAL),
)


def iter_cases() -> Iterator[tuple[str, str, PluginProject, dict]]:
    """(코퍼스 이름, 타깃 이름, 프로젝트, compile 인자) — 선언 순서 그대로."""
    for corpus_name, factory, kwargs in CORPORA:
        for target_name, target in TARGETS:
            project = factory()
            project.build_target = target
            yield corpus_name, target_name, project, dict(kwargs)
