"""외부 플러그인 서브에이전트를 워크플로 노드로 — `ExternalAgent` (WP-9).

이 종류가 증명하려는 것은 리팩토링의 **수용 시험**이다(REFACTOR_SPEC §7-a):
새 종류 하나를 더하는 데 필요한 편집이 종류 등록 다섯 파일 + 새 필드 어휘로
끝나는가. 그래서 여기서는 기능뿐 아니라 **아무도 고치지 않은 계층이 자동으로
옳게 답하는지**를 확인한다 — 직렬화·계획·검증·MCP 어휘는 이 종류를 모른 채
능력 선언만 보고 움직여야 한다.

세 조합이 이 종류의 정체다:
- 그래프 노드다(`PLACEMENT=STATE`) — 포트가 있고 위임 대상이다.
- 산출 파일이 없다(`OUTPUT_LOCATION=NONE`) — emitter도 미리보기도 없다.
- 본문 정본이 외부다(`BODY_SOURCE=EXTERNAL`) — 본문 쓰기가 거절된다.
종전 `isinstance(agent, AgentDefinition)` 하나로는 표현할 수 없던 조합이다.
"""
from __future__ import annotations

import pytest

from daedalus.compiler import compile_project
from daedalus.compiler.emit.emitters import EMITTERS, emitter_for
from daedalus.compiler.preview import can_preview, preview_component
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import ExternalAgent
from daedalus.model.plugin.config import (
    ExternalAgentConfig,
    ProceduralSkillConfig,
)
from daedalus.model.plugin.enums import ModelType
from daedalus.model.plugin.kinds import KIND_REGISTRY, spec_by_kind
from daedalus.model.plugin.placement import (
    is_canvas_placeable,
    is_state_placeable,
)
from daedalus.model.plugin.roles import BodySource, Bucket, OutputLocation
from daedalus.model.plugin.skill import ProceduralSkill, has_external_body
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project
from daedalus.model.validation import Validator

_SOURCE = "review-pack:critic"


def _external(name: str = "critic", source: str = _SOURCE, **cfg) -> ExternalAgent:
    return ExternalAgent(
        name=name,
        description=f"{name} from an installed plugin.",
        config=ExternalAgentConfig(source=source, **cfg),
        transfer_on=[
            EventDef(name="approved", description="the reviewer signed off"),
            EventDef(name="changes", description="the reviewer wants changes"),
        ],
    )


def _caller(name: str = "draft") -> ProceduralSkill:
    entry = EntryPoint(name="s")
    return ProceduralSkill(
        fsm=StateMachine(name=f"{name}_fsm", states=[entry], initial_state=entry),
        name=name, description=f"{name} skill.", config=ProceduralSkillConfig(),
        transfer_on=[EventDef(name="done")],
        call_agents=[EventDef(name="review", description="hand it to the reviewer")],
    )


def _project(*, declared: bool = True, agent: ExternalAgent | None = None):
    """호출 스킬 → 외부 에이전트 한 갈래를 가진 최소 프로젝트."""
    agent = agent if agent is not None else _external()
    skill = _caller()
    project = PluginProject(
        name="p", skills=[skill], agents=[agent],
        external_plugins=["review-pack"] if declared else [],
    )
    node_skill = SimpleState(name=skill.name, skill_ref=skill)
    node_agent = SimpleState(name=agent.name, skill_ref=agent)
    project.graph.states += [node_skill, node_agent]
    project.graph.transitions.append(Transition(
        source=node_skill, target=node_agent,
        trigger=CompletionEvent(name="review"),
    ))
    return project, skill, agent


def _agent_caller_project(agent: ExternalAgent, model=ModelType.INHERIT):
    """**에이전트**가 외부 에이전트를 부르는 프로젝트.

    중첩 체인 규칙(`_agent_call_edges`)의 호출자는 서브에이전트에서 도는
    노드뿐이다 — 메인 스레드에서 도는 절차형 스킬이 부르는 것은 중첩이
    아니라서, 스킬을 호출자로 두면 이 규칙들을 **한 번도 태우지 못한다**.
    """
    from daedalus.model.plugin.agent import AgentDefinition
    from daedalus.model.plugin.config import AgentConfig

    entry = EntryPoint(name="s")
    caller = AgentDefinition(
        fsm=StateMachine(name="lead_fsm", states=[entry], initial_state=entry),
        name="lead", description="lead agent.", config=AgentConfig(model=model),
        transfer_on=[EventDef(name="done")],
        call_agents=[EventDef(name="review")],
    )
    project = PluginProject(
        name="p", agents=[caller, agent], external_plugins=["review-pack"],
    )
    node_caller = SimpleState(name=caller.name, skill_ref=caller)
    node_agent = SimpleState(name=agent.name, skill_ref=agent)
    project.graph.states += [node_caller, node_agent]
    project.graph.transitions.append(Transition(
        source=node_caller, target=node_agent,
        trigger=CompletionEvent(name="review"),
    ))
    return project, caller


def _rules(project) -> dict[str, bool]:
    """규칙 이름 → 경고인가."""
    return {e.rule: e.is_warning for e in Validator.validate_project(project)}


# ── 능력 선언 ────────────────────────────────────────────────────────────

def test_declarations_are_the_three_way_split():
    """그래프 노드 · 산출 없음 · 외부 본문 — 세 선언이 따로 답한다."""
    assert ExternalAgent.KIND == "external_agent"
    assert ExternalAgent.CONFIG_CLS is ExternalAgentConfig
    assert ExternalAgent.BUCKET is Bucket.AGENTS
    assert ExternalAgent.OUTPUT_LOCATION is OutputLocation.NONE
    assert ExternalAgent.BODY_SOURCE is BodySource.EXTERNAL
    assert ExternalAgent.REQUIRES_OUTPUT_PORTS
    # Agent에서 물려받는 것 — 이쪽으로 가는 전이는 위임이다.
    assert ExternalAgent.DELEGATION_TARGET
    assert not ExternalAgent.HAS_INTERNAL_FSM
    assert not ExternalAgent.IS_FORK_BASE


def test_it_is_a_canvas_node_with_ports():
    agent = _external()
    assert is_state_placeable(agent) and is_canvas_placeable(agent)
    assert [e.name for e in agent.output_ports()] == ["approved", "changes"]
    assert agent.call_ports() == []
    assert has_external_body(agent)


def test_known_outgoing_events_cover_both_port_kinds():
    """출력 포트 + 호출 포트 — 호출 포트에서 뽑은 전이가 오탐이 되면 안 된다."""
    agent = _external()
    agent.call_agents = [EventDef(name="escalate")]
    assert agent.known_outgoing_events() == frozenset(
        {"approved", "changes", "escalate"}
    )


def test_new_is_born_with_a_port():
    """포트 0개로 태어나면 배치 즉시 `transfer_on_not_empty`가 뜬다."""
    fresh = ExternalAgent.new("critic", "d")
    assert [e.name for e in fresh.output_ports()] == ["done"]
    # 저장 파일에 키가 없을 때는 **발명하지 않는다** — 둘은 다른 질문이다.
    assert ExternalAgent(name="x", description="d").transfer_on == []


def test_external_source_is_empty_string_not_none_when_unset():
    """빈 값에 `None`을 돌려주면 형식 검사가 통째로 건너뛴다(원칙 5)."""
    assert _external(source="").external_source == ""
    assert _external().external_source == _SOURCE
    assert _external().external_plugin_refs() == ["review-pack"]
    # 형식이 깨진 source는 `external_source_missing` 소관이라 참조로 세지 않는다.
    assert _external(source="review-pack").external_plugin_refs() == []


# ── 아무도 고치지 않은 계층 ───────────────────────────────────────────────

def test_registry_row_is_derived_from_the_class():
    spec = spec_by_kind("external_agent")
    assert spec is KIND_REGISTRY["external_agent"]
    assert spec.component_cls is ExternalAgent
    assert spec.config_cls is ExternalAgentConfig
    assert spec.config_kind == "external_agent"
    assert spec.output_location is OutputLocation.NONE


def test_round_trips_through_the_serialization_engine():
    """직렬화 엔진은 이 종류를 모른다 — 키는 `dataclasses.fields`가 정한다."""
    project, _skill, agent = _project()
    agent.call_agents = [EventDef(name="escalate")]
    data = serialize_project(project)
    (raw,) = data["agents"]
    assert raw["kind"] == "external_agent"
    # 내부 FSM이 없으므로 `fsm` 키가 나가지 않는다(퇴역 개념의 잔재 금지).
    assert "fsm" not in raw
    assert raw["config"] == {
        "kind": "external_agent", "model": "inherit", "effort": None,
        "hooks": None, "source": _SOURCE,
    }

    back = deserialize_project(data)
    (loaded,) = back.agents
    assert isinstance(loaded, ExternalAgent)
    assert loaded.external_source == _SOURCE
    assert [e.name for e in loaded.output_ports()] == ["approved", "changes"]
    assert [e.name for e in loaded.call_ports()] == ["escalate"]


def test_mcp_create_vocabulary_includes_it():
    from daedalus.mcp.tools.props import PropsTools

    assert "external_agent" in PropsTools._AGENT_KINDS


# ── 컴파일: 산출 0개 ─────────────────────────────────────────────────────

def test_it_has_no_emitter_and_no_preview():
    """미리보기 거절은 **사용자의 말**로 한다 — emitter 등록은 우리 사정이다.

    GUI는 `can_preview`로 메뉴를 흐리지만 MCP `compile_preview`에는 흐릴 메뉴가
    없다 — 게이트가 `preview_component` 안에 없으면 그 표면만 "emitter가 없다"는
    내부 사정을 이유로 말한다(원칙 2·5, WP-9 리뷰).
    """
    agent = _external()
    assert "external_agent" not in EMITTERS
    assert not agent.emits_output()
    assert not can_preview(agent)
    with pytest.raises(ValueError, match="external_agent"):
        emitter_for(agent)
    with pytest.raises(ValueError) as exc:
        preview_component(agent)
    message = str(exc.value)
    assert "external_agent" in message
    assert "산출 파일이 없어" in message and "부르는 쪽" in message
    assert "emitter" not in message


def test_compile_produces_no_file_for_it(tmp_path):
    project, _skill, _agent = _project()
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    assert not (tmp_path / "agents" / "critic.md").exists()
    written = {p.name for p in result.written}
    assert "critic.md" not in written


def test_caller_names_it_by_source_and_says_it_knows_nothing(tmp_path):
    """호출자 산출이 **`플러그인:이름`**으로 부르고 외부라는 사실을 말한다."""
    from daedalus.compiler.emit import compile_skill

    project, skill, _agent = _project()
    text = compile_skill(skill, project=project)
    assert f"delegate to agent `{_SOURCE}`" in text
    assert "knows neither this workflow nor the blackboard" in text
    # 노드 이름으로 부르면 CC가 그 서브에이전트를 찾지 못한다.
    assert "delegate to agent `critic`" not in text


def test_a_broken_source_names_no_agent_at_all(tmp_path):
    """부를 이름이 없으면 **이름을 지어내지 않는다** (WP-9 리뷰 — 정정).

    종전에는 `source or name`이라 빈 source면 노드 이름(`critic`), 콜론 없는
    source면 플러그인 id(`review-pack`)가 위임 지시에 그대로 실렸다. 둘 다 CC가
    찾을 수 없는 이름인데 `external_source_missing`은 **경고**라 컴파일이
    성공하므로, 없는 에이전트를 지목하는 산출이 그대로 나갔다(원칙 5).
    """
    from daedalus.compiler.emit import compile_agent, compile_skill

    for broken in ("", "   ", "review-pack", "review-pack:"):
        project, skill, _agent = _project(agent=_external(source=broken))
        text = compile_skill(skill, project=project)
        assert "cannot delegate" in text
        assert "has no usable `source`" in text
        assert "on node `critic`" in text
        # 없는 이름을 어느 형태로도 적지 않는다.
        assert "delegate to agent `" not in text

        agent_project, caller = _agent_caller_project(_external(source=broken))
        agent_text = compile_agent(caller, agent_project)
        assert "cannot delegate" in agent_text
        assert "delegate to agent `" not in agent_text

    # 그래도 컴파일은 성공한다(경고 1건) — 편집 중일 수 있다.
    project, _skill, _agent = _project(agent=_external(source=""))
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    assert "external_source_missing" in {e.rule for e in result.warnings}


def test_entry_context_of_a_broken_source_points_at_the_node():
    """진입 맥락은 지시가 아니라 서술이라 문구가 다르다 — 그래도 이름은 없다."""
    from daedalus.compiler.emit import compile_skill

    agent = _external(source="")
    project, skill, _agent = _project(agent=agent)
    after = _caller("wrapup")
    project.skills.append(after)
    node_after = SimpleState(name=after.name, skill_ref=after)
    project.graph.states.append(node_after)
    node_agent = next(
        s for s in project.graph.states
        if getattr(s, "skill_ref", None) is agent
    )
    project.graph.transitions.append(Transition(
        source=node_agent, target=node_after,
        trigger=CompletionEvent(name="approved"),
    ))
    text = compile_skill(after, project=project)
    assert "entered after the external plugin agent on node `critic` returned" in text
    assert "entered after agent `critic`" not in text


def test_agent_delegation_section_carries_the_same_name_and_note():
    """에이전트 쪽 "## Delegation"도 같은 이름·같은 단서를 쓴다 (원칙 1).

    스킬의 "## Next Steps"와 에이전트의 "## Delegation"이 다른 이름을 말하면
    같은 노드가 표면마다 다르게 불린다 — 판정의 실체는
    `emit/common.delegation_target_name` 하나다.
    """
    from daedalus.compiler.emit import compile_agent

    agent = _external()
    project, caller = _agent_caller_project(agent)
    text = compile_agent(caller, project)
    assert f"delegate to agent `{_SOURCE}`" in text
    assert "knows neither this workflow nor the blackboard" in text
    assert "delegate to agent `critic`" not in text


def test_its_name_is_not_subject_to_the_output_name_gate(tmp_path):
    """산출 파일이 없으면 CC 파일명 규약을 따를 이유가 없다 (§2-g 부수 효과).

    이름은 외부 플러그인의 것이라 우리가 고를 수 없다 — 게이트를 걸면 남의
    작명 때문에 컴파일이 통째로 막힌다.
    """
    project, _skill, agent = _project()
    agent.name = "Critic Reviewer"  # 공백 + 대문자 — 남의 작명이다
    result = compile_project(project, tmp_path)
    named = [
        e for e in result.errors if e.rule == "compile_invalid_component_name"
    ]
    assert not named


# ── 검증 ─────────────────────────────────────────────────────────────────

def test_empty_source_is_caught_by_the_generalized_rule():
    """`_check_external_sources`는 종류를 묻지 않는다 — 선언 한 줄로 합류한다."""
    project, _skill, _agent = _project(agent=_external(source=""))
    assert _rules(project).get("external_source_missing") is True


def test_undeclared_plugin_is_reported():
    project, _skill, _agent = _project(declared=False)
    assert _rules(project).get("undeclared_external_plugin") is True
    project.external_plugins = ["review-pack"]
    assert "undeclared_external_plugin" not in _rules(project)


def test_empty_ports_are_an_error():
    agent = _external()
    agent.transfer_on = []
    project, _skill, _agent = _project(agent=agent)
    assert _rules(project).get("transfer_on_not_empty") is False


def test_model_tier_comparison_skips_it():
    """우리 `config.model`은 어디로도 나가지 않는다 — 티어 비교 대상이 아니다.

    호출자가 haiku, 외부 에이전트가 fable이면 종전 규칙대로라면 에러다. 그
    모델 값은 남의 플러그인 파일이 정하므로 우리가 적어 본 값으로 판정하면
    실체 없는 에러가 된다. 같은 자리에 워크플로 에이전트를 두면 에러가
    **나는** 것으로 규칙이 살아 있음을 함께 확인한다.
    """
    project, _caller = _agent_caller_project(
        _external(model=ModelType.FABLE), model=ModelType.HAIKU
    )
    assert "agent_calls_higher_model" not in _rules(project)

    from daedalus.model.plugin.agent import AgentDefinition
    from daedalus.model.plugin.config import AgentConfig

    entry = EntryPoint(name="s")
    rival = AgentDefinition(
        fsm=StateMachine(name="rival_fsm", states=[entry], initial_state=entry),
        name="critic", description="d",
        config=AgentConfig(model=ModelType.FABLE),
        transfer_on=[EventDef(name="done")],
    )
    old = project.agents[1]
    project.agents[1] = rival
    for state in project.graph.states:
        if getattr(state, "skill_ref", None) is old:
            state.skill_ref = rival
    assert _rules(project).get("agent_calls_higher_model") is False


def test_it_still_counts_toward_the_nesting_depth():
    """모델 비교에서 빠지는 것이지 **호출 체인에서 빠지는 것이 아니다**."""
    from daedalus.model.validation.project_rules.workflow import (
        _agent_call_edges,
    )

    agent = _external()
    project, _caller = _agent_caller_project(agent)
    edges = _agent_call_edges(project)
    assert [callee for _s, _t, _c, callee, _p in edges] == [agent]


# ── 편집 표면 ────────────────────────────────────────────────────────────

def test_body_writes_are_rejected():
    """본문 정본이 외부인 종류는 MCP 본문 쓰기를 거절한다 (D4와 같은 술어)."""
    assert has_external_body(_external())


def test_the_canvas_badge_does_not_call_it_a_wrapped_skill():
    """뱃지 문구·아이콘도 **선언**에서 나온다 (WP-9 리뷰 — 스멜 ⑤).

    술어(`has_external_body`)만 종류 중립이고 문구가 랩핑 스킬로 굳어 있으면,
    외부 플러그인 **에이전트** 노드가 캔버스에서 🔗 "랩핑 스킬"로 불린다.
    """
    pytest.importorskip("PySide6")
    from daedalus.view.canvas.node_badges import badges_for

    (icon, tooltip), = badges_for(_external())
    assert icon == "🔌"
    assert "랩핑 스킬" not in tooltip
    assert "EXTERNAL AGENTS" in tooltip and _SOURCE in tooltip


def test_the_editor_panel_speaks_of_an_agent_not_a_skill():
    """편집기 산문과 "원본 열기" 버튼도 종류를 따라간다 (WP-9 리뷰).

    카탈로그는 플러그인의 `skills/<이름>/SKILL.md`만 해소한다 — 에이전트에
    버튼을 남겨 두면 누를 때마다 "찾지 못했습니다"만 내놓는다(조용한 실패).
    """
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from daedalus.view.editors.component_editor import _WrappedSourcePanel

    QApplication.instance() or QApplication([])
    panel = _WrappedSourcePanel(_external(source=""))
    assert "에이전트" in panel._w_status.text()
    assert "스킬" not in panel._w_status.text()
    assert panel._btn_open.isHidden()


def test_editable_fields_are_name_description_source():
    from daedalus.model.plugin.enums import AgentField, FieldEmit
    from daedalus.model.plugin.field_matrix import matrix_for

    rules = matrix_for(_external())
    assert set(rules) == {
        AgentField.NAME, AgentField.DESCRIPTION, AgentField.SOURCE,
    }
    assert {rule.emit for rule in rules.values()} == {FieldEmit.NONE}
