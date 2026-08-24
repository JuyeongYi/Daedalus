"""진입 의미론 두 필드의 tri-state — 직렬화·컴파일·검증 (A8).

`None` = 미지정(프론트매터 키 생략 → CC 기본값 위임) / `True`·`False` = 명시 지정.
순수 bool이면 "기본값을 쓴다"와 "기본값과 같은 값을 못 박았다"가 구분되지 않아
프리셋 "일반 상태로"를 표현할 수 없다.
"""
from __future__ import annotations

from daedalus.compiler.emit import compile_skill
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project
from daedalus.model.validation import Validator


def _proc(name: str = "worker") -> ProceduralSkill:
    s = SimpleState(name="start")
    fsm = StateMachine(name="f", initial_state=s, states=[s], final_states=[s])
    return ProceduralSkill(fsm=fsm, name=name, description="d")


def _frontmatter(text: str) -> dict[str, str]:
    body = text.split("---", 2)[1]
    out: dict[str, str] = {}
    for line in body.strip().split("\n"):
        if ": " in line:
            key, value = line.split(": ", 1)
            out[key.strip()] = value.strip()
    return out


# --- 컴파일 ---


def test_unspecified_omits_both_keys():
    """미지정 = 키 자체가 없다 — CC 기본값에 위임한다."""
    skill = _proc()
    fm = _frontmatter(compile_skill(skill))
    assert "user-invocable" not in fm
    assert "disable-model-invocation" not in fm


def test_explicit_true_is_emitted():
    """`user-invocable: true`가 나가는 것은 정상이다 — 사용자가 진입점으로 못 박았다."""
    skill = _proc()
    skill.config.user_invocable = True
    assert _frontmatter(compile_skill(skill))["user-invocable"] == "true"


def test_explicit_false_is_emitted():
    skill = _proc()
    skill.config.user_invocable = False
    skill.config.disable_model_invocation = False
    fm = _frontmatter(compile_skill(skill))
    assert fm["user-invocable"] == "false"
    assert fm["disable-model-invocation"] == "false"


def test_declarative_follows_the_same_rule():
    skill = DeclarativeSkill(name="k", description="d")
    assert "user-invocable" not in _frontmatter(compile_skill(skill))
    skill.config.user_invocable = True
    assert _frontmatter(compile_skill(skill))["user-invocable"] == "true"


def test_fixed_kinds_are_unaffected():
    """FIXED 종류는 config를 읽지 않고 fixed_value를 강제한다 — 무영향."""
    from daedalus.model.plugin.skill import ReferenceSkill

    fm = _frontmatter(compile_skill(ReferenceSkill(name="r", description="d")))
    assert fm["user-invocable"] == "false"


# --- 직렬화 왕복 ---


def _roundtrip(project: PluginProject) -> PluginProject:
    return deserialize_project(serialize_project(project))


def test_none_roundtrips_as_none():
    project = PluginProject(name="p", skills=[_proc()])
    loaded = _roundtrip(project)
    assert loaded.skills[0].config.user_invocable is None
    assert loaded.skills[0].config.disable_model_invocation is None


def test_true_and_false_roundtrip_explicitly():
    """저장된 true/false는 그대로 왕복한다 — 스크럽 금지(명시 지정한 값이다)."""
    skill = _proc()
    skill.config.user_invocable = True
    skill.config.disable_model_invocation = False
    loaded = _roundtrip(PluginProject(name="p", skills=[skill]))
    assert loaded.skills[0].config.user_invocable is True
    assert loaded.skills[0].config.disable_model_invocation is False


def test_missing_key_becomes_none():
    """구버전 파일에 키가 없으면 미지정으로 읽는다."""
    project = PluginProject(name="p", skills=[_proc()])
    data = serialize_project(project)
    data["skills"][0]["config"].pop("user_invocable")
    data["skills"][0]["config"].pop("disable_model_invocation")
    loaded = deserialize_project(data)
    assert loaded.skills[0].config.user_invocable is None
    assert loaded.skills[0].config.disable_model_invocation is None


def test_stored_true_is_not_scrubbed_to_none():
    """구버전 파일이 저장한 true는 명시 지정으로 살아남는다."""
    project = PluginProject(name="p", skills=[_proc()])
    data = serialize_project(project)
    data["skills"][0]["config"]["user_invocable"] = True
    loaded = deserialize_project(data)
    assert loaded.skills[0].config.user_invocable is True


# --- 검증 (A3 규칙의 tri-state 적응) ---


def _chain(first_ui, second_ui) -> PluginProject:
    a, b = _proc("alpha"), _proc("beta")
    a.config.user_invocable = first_ui
    b.config.user_invocable = second_ui
    project = PluginProject(name="p", skills=[a, b])
    na = SimpleState(name="alpha", skill_ref=a)
    nb = SimpleState(name="beta", skill_ref=b)
    project.graph.states.extend([na, nb])
    project.graph.transitions.append(Transition(source=na, target=nb))
    return project


def _mid_chain(project) -> list:
    return [
        e for e in Validator.validate_project(project)
        if e.rule == "mid_chain_user_invocable"
    ]


def test_none_is_warned_with_note():
    """미지정의 실효값은 CC 기본 true다 — 경고 대상이고, 미지정임을 병기한다."""
    errors = _mid_chain(_chain(None, None))
    assert [e.source for e in errors] == ["beta"]
    assert "미지정" in errors[0].message


def test_explicit_true_is_warned():
    errors = _mid_chain(_chain(None, True))
    assert [e.source for e in errors] == ["beta"]
    assert "미지정" not in errors[0].message


def test_explicit_false_passes():
    """명시 False만 통과한다."""
    assert _mid_chain(_chain(None, False)) == []
