"""컴포넌트 **능력 표면** 계약 (REFACTOR_SPEC §2-b/§2-c, WP-2a).

능력 표면은 "이 객체가 무슨 클래스인가"를 묻던 자리를 "무엇을 할 수 있는가"를
객체가 스스로 답하는 선언·메서드로 바꾼다. 이 파일이 지키는 것은 셋이다:

1. **선언이 전수인가** — 구체 9종이 §2-b의 ClassVar를 빠짐없이 갖는가.
   빠뜨리면 그 종류만 조용히 기저 기본값으로 동작한다(👻).
2. **선언이 필드를 오염시키지 않았는가** — `fields()`에 ClassVar 이름이 하나도
   없고 `WorkflowComponent`에는 메서드가 없다(§10 R2·R5). 이 둘이 깨지면
   dataclass 필드 순서·MRO가 조용히 바뀐다.
3. **능력이 오늘의 판정과 같은 답을 내는가** — `emits_output()` ↔
   `emit/common.emits_output_file`, `effective_placement()` ↔
   `is_reference_usage`/`placement.*` 처럼, 호출자를 치환할 WP-2b~2d가
   **동작 불변**임을 여기서 미리 고정한다.

`new()`/`creation_defaults()`는 `view/actions/creation.make_component`의 kind별
람다 9개와 **필드 단위로** 같은 물건을 만드는지 본다 — 그래야 WP-3에서 그 표를
지워도 만들어지는 컴포넌트가 달라지지 않는다.
"""
from __future__ import annotations

import dataclasses

import pytest

from daedalus.compiler.emit.common import emits_output_file
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.plugin.agent import Agent, AgentDefinition, ForkAgent
from daedalus.model.plugin.base import PluginComponent, WorkflowComponent
from daedalus.model.plugin.config import (
    AgentConfig,
    AgentConfigBase,
    AsyncForkSkillConfig,
    ComponentConfig,
    DeclarativeSkillConfig,
    ForkAgentConfig,
    ForkSkillConfig,
    ProceduralSkillConfig,
    ReferenceSkillConfig,
    SkillConfig,
    StepSkillConfig,
    SyncForkSkillConfig,
    TransferSkillConfig,
    WrappedSkillConfig,
)
from daedalus.model.plugin.placement import is_canvas_placeable, is_state_placeable
from daedalus.model.plugin.roles import (
    BodySource,
    Bucket,
    OutputLocation,
    PlacementRole,
)
from daedalus.model.plugin.skill import (
    AsyncForkSkill,
    DeclarativeSkill,
    ForkSkill,
    ProceduralSkill,
    ReferenceSkill,
    Skill,
    StepSkill,
    SyncForkSkill,
    TransferSkill,
    WrappedSkill,
    has_external_body,
    is_reference_usage,
)
from daedalus.view.component_actions import ComponentActions
from daedalus.view.actions.creation import make_component

#: §2-b가 정한 종류 선언 13개. 구체 클래스는 **전부** 해석 가능해야 한다.
CLASSVAR_NAMES: tuple[str, ...] = (
    "KIND", "CONFIG_CLS", "BUCKET", "PLACEMENT", "OUTPUT_LOCATION", "BODY_SOURCE",
    "CONVERT_FAMILY", "DELEGATION_TARGET", "RUNS_IN_SUBAGENT", "REPORTS_OUT_OF_BAND",
    "IS_FORK_BASE", "REQUIRES_OUTPUT_PORTS", "HAS_INTERNAL_FSM",
)

_S, _A = Bucket.SKILLS, Bucket.AGENTS
_SKILL_DIR = OutputLocation.SKILL_DIR
_AGENT_FILE = OutputLocation.AGENT_FILE

#: 구체 9종의 선언 **전수**. 값을 바꾸면 여기서 먼저 걸린다 — 표를 고치지 않고
#: 클래스만 고치는(또는 그 반대의) 편집이 조용히 지나가지 않게 한다.
EXPECTED_DECLARATIONS: dict[type, dict[str, object]] = {
    ProceduralSkill: {
        "KIND": "procedural_skill", "CONFIG_CLS": ProceduralSkillConfig,
        "BUCKET": _S, "PLACEMENT": PlacementRole.STATE,
        "OUTPUT_LOCATION": _SKILL_DIR, "BODY_SOURCE": BodySource.OWNED,
        "CONVERT_FAMILY": "step", "DELEGATION_TARGET": False,
        "RUNS_IN_SUBAGENT": False, "REPORTS_OUT_OF_BAND": False,
        "IS_FORK_BASE": False, "REQUIRES_OUTPUT_PORTS": True,
        "HAS_INTERNAL_FSM": False,
    },
    SyncForkSkill: {
        "KIND": "sync_fork_skill", "CONFIG_CLS": SyncForkSkillConfig,
        "BUCKET": _S, "PLACEMENT": PlacementRole.STATE,
        "OUTPUT_LOCATION": _SKILL_DIR, "BODY_SOURCE": BodySource.OWNED,
        "CONVERT_FAMILY": "step", "DELEGATION_TARGET": False,
        "RUNS_IN_SUBAGENT": True, "REPORTS_OUT_OF_BAND": False,
        "IS_FORK_BASE": False, "REQUIRES_OUTPUT_PORTS": True,
        "HAS_INTERNAL_FSM": False,
    },
    AsyncForkSkill: {
        "KIND": "async_fork_skill", "CONFIG_CLS": AsyncForkSkillConfig,
        "BUCKET": _S, "PLACEMENT": PlacementRole.STATE,
        "OUTPUT_LOCATION": _SKILL_DIR, "BODY_SOURCE": BodySource.OWNED,
        "CONVERT_FAMILY": "step", "DELEGATION_TARGET": False,
        "RUNS_IN_SUBAGENT": True, "REPORTS_OUT_OF_BAND": True,
        "IS_FORK_BASE": False, "REQUIRES_OUTPUT_PORTS": True,
        "HAS_INTERNAL_FSM": False,
    },
    DeclarativeSkill: {
        "KIND": "declarative_skill", "CONFIG_CLS": DeclarativeSkillConfig,
        "BUCKET": _S, "PLACEMENT": PlacementRole.NONE,
        "OUTPUT_LOCATION": _SKILL_DIR, "BODY_SOURCE": BodySource.OWNED,
        "CONVERT_FAMILY": None, "DELEGATION_TARGET": False,
        "RUNS_IN_SUBAGENT": False, "REPORTS_OUT_OF_BAND": False,
        "IS_FORK_BASE": False, "REQUIRES_OUTPUT_PORTS": False,
        "HAS_INTERNAL_FSM": False,
    },
    TransferSkill: {
        "KIND": "transfer_skill", "CONFIG_CLS": TransferSkillConfig,
        "BUCKET": _S, "PLACEMENT": PlacementRole.EDGE,
        "OUTPUT_LOCATION": _SKILL_DIR, "BODY_SOURCE": BodySource.OWNED,
        "CONVERT_FAMILY": None, "DELEGATION_TARGET": False,
        "RUNS_IN_SUBAGENT": False, "REPORTS_OUT_OF_BAND": False,
        "IS_FORK_BASE": False, "REQUIRES_OUTPUT_PORTS": False,
        "HAS_INTERNAL_FSM": False,
    },
    ReferenceSkill: {
        "KIND": "reference_skill", "CONFIG_CLS": ReferenceSkillConfig,
        "BUCKET": _S, "PLACEMENT": PlacementRole.REFERENCE,
        "OUTPUT_LOCATION": _SKILL_DIR, "BODY_SOURCE": BodySource.OWNED,
        "CONVERT_FAMILY": None, "DELEGATION_TARGET": False,
        "RUNS_IN_SUBAGENT": False, "REPORTS_OUT_OF_BAND": False,
        "IS_FORK_BASE": False, "REQUIRES_OUTPUT_PORTS": False,
        "HAS_INTERNAL_FSM": False,
    },
    WrappedSkill: {
        "KIND": "wrapped_skill", "CONFIG_CLS": WrappedSkillConfig,
        "BUCKET": _S, "PLACEMENT": PlacementRole.STATE,
        "OUTPUT_LOCATION": _SKILL_DIR, "BODY_SOURCE": BodySource.EXTERNAL,
        "CONVERT_FAMILY": None, "DELEGATION_TARGET": False,
        "RUNS_IN_SUBAGENT": True, "REPORTS_OUT_OF_BAND": False,
        "IS_FORK_BASE": False, "REQUIRES_OUTPUT_PORTS": False,
        "HAS_INTERNAL_FSM": False,
    },
    AgentDefinition: {
        "KIND": "agent", "CONFIG_CLS": AgentConfig,
        "BUCKET": _A, "PLACEMENT": PlacementRole.STATE,
        "OUTPUT_LOCATION": _AGENT_FILE, "BODY_SOURCE": BodySource.OWNED,
        "CONVERT_FAMILY": None, "DELEGATION_TARGET": True,
        "RUNS_IN_SUBAGENT": True, "REPORTS_OUT_OF_BAND": False,
        "IS_FORK_BASE": False, "REQUIRES_OUTPUT_PORTS": True,
        "HAS_INTERNAL_FSM": True,
    },
    ForkAgent: {
        "KIND": "fork_agent", "CONFIG_CLS": ForkAgentConfig,
        "BUCKET": _A, "PLACEMENT": PlacementRole.NONE,
        "OUTPUT_LOCATION": _AGENT_FILE, "BODY_SOURCE": BodySource.OWNED,
        "CONVERT_FAMILY": None, "DELEGATION_TARGET": True,
        "RUNS_IN_SUBAGENT": True, "REPORTS_OUT_OF_BAND": False,
        "IS_FORK_BASE": True, "REQUIRES_OUTPUT_PORTS": False,
        "HAS_INTERNAL_FSM": False,
    },
}

CONCRETE_COMPONENTS: tuple[type, ...] = tuple(EXPECTED_DECLARATIONS)

ABSTRACT_COMPONENTS: tuple[type, ...] = (
    PluginComponent, Skill, StepSkill, ForkSkill, Agent,
)
CONCRETE_CONFIGS: tuple[type, ...] = (
    ProceduralSkillConfig, SyncForkSkillConfig, AsyncForkSkillConfig,
    WrappedSkillConfig, DeclarativeSkillConfig, TransferSkillConfig,
    ReferenceSkillConfig, AgentConfig, ForkAgentConfig,
)
ABSTRACT_CONFIGS: tuple[type, ...] = (
    ComponentConfig, SkillConfig, StepSkillConfig, ForkSkillConfig, AgentConfigBase,
)

#: config kind ↔ 컴포넌트 클래스 (make_component의 어휘는 **config** kind다).
CONFIG_KIND_TO_CLASS: dict[str, type] = {
    "procedural": ProceduralSkill,
    "sync_fork": SyncForkSkill,
    "async_fork": AsyncForkSkill,
    "declarative": DeclarativeSkill,
    "transfer": TransferSkill,
    "reference": ReferenceSkill,
    "wrapped": WrappedSkill,
    "agent": AgentDefinition,
    "fork_agent": ForkAgent,
}


class _StubWindow:
    """`make_component`가 요구하는 FSM 팩토리 두 개만 가진 창 대역.

    팩토리를 손으로 재현하지 않고 **실제 `ComponentActions`의 것**을 빌려 쓴다
    (두 벌이 되면 이 테스트가 지키려는 등가성 자체가 흐려진다).
    """

    _make_fsm = ComponentActions.make_fsm
    _make_agent_fsm = ComponentActions.make_agent_fsm


def _fsm(name: str = "m") -> StateMachine:
    return _StubWindow()._make_fsm(name)  # type: ignore[return-value]


def _instance(cls: type):
    """구체 9종의 최소 인스턴스 — `new()`가 아니라 생성자로 만든다."""
    kwargs: dict[str, object] = {"name": cls.KIND, "description": "d"}
    if any(f.name == "fsm" for f in dataclasses.fields(cls)):
        kwargs["fsm"] = _fsm()
    return cls(**kwargs)


# ── 1. 선언이 전수인가 ──────────────────────────────────────────────────

@pytest.mark.parametrize("cls", CONCRETE_COMPONENTS, ids=lambda c: c.__name__)
@pytest.mark.parametrize("name", CLASSVAR_NAMES)
def test_every_concrete_class_declares_every_capability(cls, name):
    """구체 9종 × 선언 13개 = 117칸이 전부 채워져 있다(상속 포함)."""
    assert hasattr(cls, name), f"{cls.__name__}에 {name} 선언이 없다"
    assert getattr(cls, name) == EXPECTED_DECLARATIONS[cls][name]


@pytest.mark.parametrize("cls", ABSTRACT_COMPONENTS, ids=lambda c: c.__name__)
def test_abstract_bases_do_not_answer_kind_questions(cls):
    """추상 기저에서 `KIND`/`CONFIG_CLS`를 읽으면 **AttributeError**다.

    기본값을 주면 추상을 종류처럼 쓴 코드가 조용히 통과한다(원칙 5).
    """
    for name in ("KIND", "CONFIG_CLS"):
        with pytest.raises(AttributeError):
            getattr(cls, name)


@pytest.mark.parametrize("cls", CONCRETE_COMPONENTS, ids=lambda c: c.__name__)
def test_kind_property_is_a_facade_over_the_declaration(cls):
    """`c.kind` == `KIND`, `c.config.kind` == config의 `KIND` — 선언이 정본이다."""
    comp = _instance(cls)
    assert comp.kind == cls.KIND
    assert comp.config.kind == cls.CONFIG_CLS.KIND
    assert type(comp.config) is cls.CONFIG_CLS


@pytest.mark.parametrize("cls", ABSTRACT_CONFIGS, ids=lambda c: c.__name__)
def test_abstract_configs_do_not_answer_kind(cls):
    with pytest.raises(AttributeError):
        getattr(cls, "KIND")


# ── 2. 선언이 필드를 오염시키지 않았는가 (§10 R2·R5) ─────────────────────

@pytest.mark.parametrize(
    "cls",
    CONCRETE_COMPONENTS + ABSTRACT_COMPONENTS + CONCRETE_CONFIGS + ABSTRACT_CONFIGS,
    ids=lambda c: c.__name__,
)
def test_classvars_never_became_dataclass_fields(cls):
    """`from __future__ import annotations` 아래서 `ClassVar`를 이름으로 임포트하지
    않으면 dataclass가 문자열 주석을 **필드로** 오해한다 — 그 사고의 게이트다.
    """
    names = {f.name for f in dataclasses.fields(cls)}
    leaked = names & (set(CLASSVAR_NAMES) | {"USAGE_REFERENCE"})
    assert not leaked, f"{cls.__name__}의 ClassVar가 필드가 됐다: {sorted(leaked)}"


def test_workflow_mixin_has_no_methods():
    """`WorkflowComponent`는 **필드 홀더**다 — 메서드를 두면 MRO에서 가려진다.

    `StepSkill(Skill, WorkflowComponent)`의 MRO는
    `StepSkill → Skill → PluginComponent → WorkflowComponent`라
    믹스인의 `state_machines()`보다 `PluginComponent`의 기본 구현이 **먼저**
    잡힌다. 실패가 아니라 **조용한 무시**라서 테스트로 막는다(§10 R2).
    """
    offenders = [
        name
        for name, value in vars(WorkflowComponent).items()
        if not name.startswith("__") and callable(value)
    ]
    assert not offenders, (
        "WorkflowComponent에 메서드를 두지 않는다 — 구체/중간 클래스에서 "
        f"오버라이드하라: {offenders}"
    )
    assert [f.name for f in dataclasses.fields(WorkflowComponent)] == ["fsm"]


def test_mro_puts_plugin_component_defaults_before_the_mixin():
    """위 규약이 지키는 **사실 자체**를 못 박는다 — MRO가 바뀌면 여기서 걸린다."""
    mro = StepSkill.__mro__
    assert mro.index(PluginComponent) < mro.index(WorkflowComponent)


# ── 3. 능력이 오늘의 판정과 같은 답을 내는가 ─────────────────────────────

def _wrapped(usage: str = "state", enabled: bool = True, source: str = "alpha:beta"):
    skill = WrappedSkill(fsm=_fsm(), name="w", description="d")
    skill.config.usage = usage
    skill.config.enabled = enabled
    skill.config.source = source
    return skill


def _capability_corpus() -> list[object]:
    return [
        *[_instance(cls) for cls in CONCRETE_COMPONENTS],
        _wrapped(usage="reference"),
        _wrapped(usage="", enabled=False),
        _wrapped(usage="reference", enabled=False),
    ]


@pytest.mark.parametrize("comp", _capability_corpus(), ids=lambda c: repr(c.kind))
def test_capability_answers_match_todays_predicates(comp):
    """치환 대상 판정 6개가 능력 메서드와 **같은 답**을 낸다 (WP-2b~2d 동작 불변)."""
    assert comp.emits_output() is emits_output_file(comp)
    assert (
        comp.effective_placement() is PlacementRole.REFERENCE
    ) is is_reference_usage(comp)
    # `is_disabled_wrapped` 파사드는 WP-2c에서 마지막 호출자가 사라져 삭제됐다 —
    # 이제 능력 메서드를 **원 필드**에 직접 맞춰 본다(파사드끼리의 동어반복이
    # 아니라 실제 상태를 건다).
    assert comp.is_active() is bool(getattr(comp.config, "enabled", True))
    assert (type(comp).BODY_SOURCE is BodySource.EXTERNAL) is has_external_body(comp)
    assert (comp.effective_placement() is PlacementRole.STATE) is is_state_placeable(
        comp
    )
    assert (
        comp.effective_placement() in (PlacementRole.STATE, PlacementRole.REFERENCE)
    ) is is_canvas_placeable(comp)


def test_reference_skill_is_a_reference_placement_by_declaration():
    """참조 스킬은 **선언으로** 참조 노드다 — `is_reference_usage`의 첫 분기."""
    ref = ReferenceSkill(name="r", description="d")
    assert ref.effective_placement() is PlacementRole.REFERENCE
    assert is_reference_usage(ref)


@pytest.mark.parametrize("cls", CONCRETE_COMPONENTS, ids=lambda c: c.__name__)
def test_shape_queries_match_the_fields_that_exist(cls):
    """형상 조회는 **그 필드를 가진 클래스에서만** 비지 않는다."""
    comp = _instance(cls)
    has_fsm = any(f.name == "fsm" for f in dataclasses.fields(cls))
    assert bool(comp.state_machines()) is has_fsm
    if has_fsm:
        assert comp.state_machines() == [comp.fsm]
    assert comp.output_ports() == list(getattr(comp, "transfer_on", []))
    assert comp.call_ports() == list(getattr(comp, "call_agents", []))
    # 복사본이어야 한다 — 돌려준 목록을 고쳐도 모델이 바뀌면 안 된다.
    ports = comp.output_ports()
    ports.clear()
    assert comp.output_ports() == list(getattr(comp, "transfer_on", []))


def test_output_ports_are_the_only_port_surface():
    """포트 조회는 `output_ports()` 하나다 — 옛 `output_events`/
    `output_event_defs` 파사드는 WP-2d에서 소비자가 사라져 삭제했다."""
    from daedalus.model.fsm.section import EventDef

    sk = ProceduralSkill(fsm=_fsm(), name="p", description="d")
    sk.transfer_on = [EventDef("ok"), EventDef("fail")]
    assert [e.name for e in sk.output_ports()] == ["ok", "fail"]

    ag = AgentDefinition(fsm=_fsm(), name="a", description="d")
    ag.transfer_on = [EventDef("done")]
    assert ag.output_ports() == [EventDef("done")]
    assert ag.output_ports() is not ag.transfer_on

    tr = TransferSkill(fsm=_fsm(), name="t", description="d")
    assert tr.output_ports() == []
    for name in ("output_events", "output_event_defs"):
        assert not hasattr(sk, name) and not hasattr(ag, name)


def test_known_outgoing_events_keeps_the_agent_skill_asymmetry():
    """스킬은 호출 포트를 합법 집합에 넣고 에이전트는 넣지 않는다(오늘 그대로).

    `machine_rules`의 trigger_unknown_event가 오늘 그렇게 동작한다 — 넓히면
    경고가 사라지는 **동작 변경**이라 backlog(D9)다.
    """
    from daedalus.model.fsm.section import EventDef

    sk = ProceduralSkill(fsm=_fsm(), name="p", description="d")
    sk.call_agents = [EventDef("ask")]
    assert sk.known_outgoing_events() == frozenset({"done", "ask"})

    ag = AgentDefinition(fsm=_fsm(), name="a", description="d")
    ag.transfer_on = [EventDef("done")]
    ag.call_agents = [EventDef("ask")]
    assert ag.known_outgoing_events() == frozenset({"done"})

    # 집합을 정의하지 않는 종류는 None이다(검증 스킵) — 빈 집합과 다르다.
    assert DeclarativeSkill(name="d", description="").known_outgoing_events() is None
    assert TransferSkill(
        fsm=_fsm(), name="t", description=""
    ).known_outgoing_events() is None


def test_delete_and_delegation_hooks():
    assert ProceduralSkill(fsm=_fsm(), name="p", description="").can_delete() == (
        True, None
    )
    blocked, reason = _wrapped().can_delete()
    # 사유는 **절**이다 — 판정("삭제할 수 없습니다")과 대안 안내는 호출자가
    # 소유한다. 모델이 완결 문장을 돌려주면 두 계층이 같은 말을 이어 붙인다.
    assert blocked is False and reason == "랩핑 스킬이기 때문입니다"
    assert "삭제할 수 없" not in reason and "비활성화" not in reason

    fork = SyncForkSkill(fsm=_fsm(), name="f", description="")
    fork.config.agent = "worker"
    assert fork.delegated_agent_name() == "worker"
    assert _wrapped().delegated_agent_name() == "w"
    assert ProceduralSkill(fsm=_fsm(), name="p", description="").delegated_agent_name() is None


def test_external_reference_hooks_match_the_wiring_rule():
    """`external_plugin_refs()`는 오늘 `naming._check_external_plugins`의 제외 규칙과 같다."""
    assert _wrapped(source="alpha@mkt:beta").external_plugin_refs() == ["alpha@mkt"]
    assert _wrapped(source="alpha:beta", enabled=False).external_plugin_refs() == []
    assert _wrapped(source="").external_plugin_refs() == []
    assert _wrapped(source="alpha:").external_plugin_refs() == []
    assert _wrapped(source="alpha:beta").external_source == "alpha:beta"
    assert ProceduralSkill(fsm=_fsm(), name="p", description="").external_source is None
    assert ProceduralSkill(
        fsm=_fsm(), name="p", description=""
    ).external_plugin_refs() == []


def test_hook_refs_preserve_insertion_order():
    """정렬하지 않는다 — `dangling_hook_ref` 경고의 "첫 등장 순서"가 계약이다."""
    sk = ProceduralSkill(fsm=_fsm(), name="p", description="")
    sk.config.hooks = {"zeta": {}, "alpha": {}}
    assert sk.hook_refs() == ["zeta", "alpha"]
    sk.config.hooks = None
    assert sk.hook_refs() == []


def test_hook_refs_tolerates_corrupted_hooks_value():
    """dict가 아닌 `hooks`는 "참조 없음" — 깨진 사용자 파일에 터지지 않는다.

    역직렬화는 `hooks`를 날것으로 싣기 때문에 손상된 `.daedalus.json`이 목록·
    문자열을 들고 들어올 수 있다. 여기서 AttributeError가 나면 검증 패널과
    MCP `compile_check`가 통째로 죽는다(원칙 5).
    """
    sk = ProceduralSkill(fsm=_fsm(), name="p", description="")
    for broken in (["oops"], "oops", 7, object()):
        sk.config.hooks = broken  # type: ignore[assignment]
        assert sk.hook_refs() == [], f"깨진 hooks 값 {broken!r}에서 참조가 새어 나왔다"


# ── 4. config의 이름 참조 계약 (Q14) ─────────────────────────────────────

def test_config_name_refs_are_namespaced():
    """네임스페이스를 보지 않으면 동명-다른타입 참조를 오갱신한다."""
    fork = SyncForkSkillConfig(agent="worker")
    assert fork.name_refs(Bucket.AGENTS) == ["worker"]
    assert fork.name_refs(Bucket.SKILLS) == []
    fork.rename_ref(Bucket.SKILLS, "worker", "other")
    assert fork.agent == "worker"          # 스킬 네임스페이스는 건드리지 않는다
    fork.rename_ref(Bucket.AGENTS, "worker", "other")
    assert fork.agent == "other"

    agent_cfg = AgentConfig(skills=["a", "b"])
    assert agent_cfg.name_refs(Bucket.SKILLS) == ["a", "b"]
    assert agent_cfg.name_refs(Bucket.AGENTS) == []
    agent_cfg.rename_ref(Bucket.AGENTS, "a", "z")
    assert agent_cfg.skills == ["a", "b"]
    agent_cfg.rename_ref(Bucket.SKILLS, "a", "z")
    assert agent_cfg.skills == ["z", "b"]
    assert agent_cfg.name_refs(Bucket.SKILLS) is not agent_cfg.skills


@pytest.mark.parametrize("cls", CONCRETE_CONFIGS, ids=lambda c: c.__name__)
def test_only_the_two_referencing_families_override_the_contract(cls):
    """이름 참조를 **가진 config만** 기저 구현을 덮는다 — 나머지는 항상 빈 목록.

    새 config가 이름 참조 필드를 들이면 이 표가 먼저 어긋난다.
    """
    references = issubclass(cls, (ForkSkillConfig, AgentConfigBase))
    for name in ("name_refs", "rename_ref"):
        overridden = getattr(cls, name) is not getattr(ComponentConfig, name)
        assert overridden is references, f"{cls.__name__}.{name}"
    if not references:
        cfg = cls()
        assert cfg.name_refs(Bucket.SKILLS) == []
        assert cfg.name_refs(Bucket.AGENTS) == []


# ── 5. `new()` ↔ `make_component` 등가 (V7 이관 게이트) ──────────────────

def _fsm_factory_for(cls: type, window: _StubWindow):
    return window._make_agent_fsm if cls.BUCKET is _A else window._make_fsm


def _fsm_shape(machine) -> tuple[str, tuple[str, ...], str]:
    return (
        machine.name,
        tuple(s.name for s in machine.states),
        machine.initial_state.name,
    )


@pytest.mark.parametrize("config_kind", sorted(CONFIG_KIND_TO_CLASS))
@pytest.mark.parametrize("agent", [None, "worker"])
def test_new_matches_make_component_field_by_field(config_kind, agent):
    """레지스트리·MCP·캔버스가 쓰는 팩토리와 `new()`가 **같은 물건**을 만든다."""
    cls = CONFIG_KIND_TO_CLASS[config_kind]
    window = _StubWindow()
    legacy = make_component(window, config_kind, "thing", "desc", agent=agent)
    fresh = cls.new(
        "thing", "desc", fsm_factory=_fsm_factory_for(cls, window), agent=agent
    )
    assert type(fresh) is type(legacy)
    for f in dataclasses.fields(cls):
        if f.name == "id":
            continue          # 안정 ID는 인스턴스마다 다르다(compare=False)
        left, right = getattr(fresh, f.name), getattr(legacy, f.name)
        if f.name == "fsm":
            assert _fsm_shape(left) == _fsm_shape(right), f.name
        else:
            assert left == right, f.name


def test_new_refuses_to_guess_a_state_machine():
    """FSM이 required인 종류에 팩토리를 안 주면 **이유를 말하고** 실패한다(원칙 5)."""
    with pytest.raises(ValueError, match="fsm_factory"):
        ProceduralSkill.new("x")
    # FSM이 없는 종류는 팩토리 없이도 만들어진다.
    assert ReferenceSkill.new("x").name == "x"


@pytest.mark.parametrize(
    "cls",
    [c for c in CONCRETE_COMPONENTS if c.REQUIRES_OUTPUT_PORTS],
    ids=lambda c: c.__name__,
)
def test_required_ports_exist_right_after_new(cls):
    """`REQUIRES_OUTPUT_PORTS`인 종류는 태어나자마자 포트를 갖는다.

    없으면 배치 즉시 `transfer_on_not_empty` 에러가 뜬다 — 새 컴포넌트가
    처음부터 빨간 줄을 달고 나오는 것을 막는 것이 `creation_defaults()`다.
    """
    window = _StubWindow()
    comp = cls.new("thing", fsm_factory=_fsm_factory_for(cls, window))
    assert comp.output_ports(), f"{cls.__name__}이 포트 0개로 태어난다"


def test_creation_defaults_do_not_leak_into_deserialisation():
    """생성 시드와 dataclass 기본값은 **다르다** — 파일에 키가 없으면 포트를 만들지 않는다."""
    assert AgentDefinition(fsm=_fsm(), name="a", description="").transfer_on == []
    assert AgentDefinition.creation_defaults(name="a", agent=None)["transfer_on"]
    assert PluginComponent.creation_defaults(name="x", agent=None) == {}
