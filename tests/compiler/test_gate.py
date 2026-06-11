# tests/compiler/test_gate.py
"""컴파일 게이트 — 에러는 거부, 경고만은 통과."""
from __future__ import annotations

from daedalus.compiler import compile_project
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.project import PluginProject

from tests.compiler.builders import make_agora_dispatch, make_delegation_skill, make_procedural


def test_error_project_rejected_no_files(tmp_path):
    # initial_state가 states에 없으면 initial_state_in_states 에러
    real = SimpleState(name="real")
    orphan = SimpleState(name="orphan")
    bad_fsm = StateMachine(name="bad", initial_state=orphan, states=[real])
    skill = make_procedural(name="bad-skill", fsm=bad_fsm)
    project = PluginProject(name="p", skills=[skill])

    result = compile_project(project, tmp_path)
    assert not result.ok
    assert result.errors
    assert result.written == []
    # 출력 폴더에 파일이 없어야
    assert not list(tmp_path.rglob("*.md"))
    assert result.skipped


def test_warning_only_project_compiles_and_includes_warnings(tmp_path):
    # AgoraDispatch with msgtype empty → empty_delegation 경고. msgtype 채워 다른 경고만 유도.
    # 간단히: 정상 procedural 스킬 1개 + 경고 유발 위임 노드(미등록 delegation)
    from daedalus.model.plugin.delegation import AgoraDispatchDef

    deleg = AgoraDispatchDef(name="orphan-send", description="d", msgtype="")  # msgtype 빈값 = 경고
    skill = make_delegation_skill(deleg, name="warn-skill")
    project = PluginProject(name="p", skills=[skill], delegations=[deleg])

    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    assert result.warnings  # empty_delegation 경고 동봉
    assert result.written
    assert (tmp_path / "skills" / "warn-skill" / "SKILL.md").exists()


def test_clean_project_no_warnings(tmp_path):
    skill = make_procedural(name="clean-skill")
    project = PluginProject(name="p", skills=[skill])
    result = compile_project(project, tmp_path)
    assert result.ok
    assert result.warnings == []
    assert (tmp_path / "skills" / "clean-skill" / "SKILL.md").exists()


# ─────────────────────── 게이트 강화: 산출 경로 충돌 ───────────────────────


def test_local_skill_path_collision_rejected(tmp_path):
    """(agent 'a--b', skill 'c')와 (agent 'a', skill 'b--c')는 동일 디렉토리
    'a--b--c'를 산출한다 — 조용한 덮어쓰기 대신 컴파일 거부 + 충돌 보고."""
    from tests.compiler.builders import make_agent

    agent1 = make_agent("a--b")
    agent1.skills = [make_procedural(name="c")]
    agent2 = make_agent("a")
    agent2.skills = [make_procedural(name="b--c")]
    project = PluginProject(name="p", agents=[agent1, agent2])

    result = compile_project(project, tmp_path)
    assert not result.ok
    assert result.written == []
    assert not list(tmp_path.rglob("*.md"))

    conflicts = [e for e in result.errors if e.rule == "compile_output_path_conflict"]
    assert conflicts, [e.rule for e in result.errors]
    msg = conflicts[0].message
    # 충돌 경로 + 원인 컴포넌트 둘 다 보고
    assert "a--b--c" in msg
    assert "a--b" in msg and "b--c" in msg
    # 게이트 에러는 에러 등급이어야 한다 (경고로 새면 안 됨)
    assert all(not e.is_warning for e in conflicts)


def test_duplicate_global_skill_path_rejected(tmp_path):
    """동명 전역 스킬 2개 → skills/<name>/ 경로 충돌로도 거부된다
    (duplicate_component_name 에러와 독립적으로 경로 수준에서 차단)."""
    project = PluginProject(
        name="p",
        skills=[make_procedural(name="same"), make_procedural(name="same")],
    )
    result = compile_project(project, tmp_path)
    assert not result.ok
    assert result.written == []
    rules = {e.rule for e in result.errors}
    assert "compile_output_path_conflict" in rules


# ─────────────────────── 게이트 강화: 이름 규약 에러 승격 ───────────────────────


def test_nonconforming_name_rejected_at_gate(tmp_path):
    """공백/대문자 이름은 검증기에서는 경고지만 컴파일 게이트에서는 에러로 거부."""
    for bad_name in ("My Skill", "BadName"):
        out = tmp_path / bad_name.replace(" ", "_")
        project = PluginProject(name="p", skills=[make_procedural(name=bad_name)])
        result = compile_project(project, out)
        assert not result.ok, f"{bad_name!r}이 게이트를 통과함"
        assert result.written == []
        assert not list(out.rglob("*.md"))
        named = [
            e for e in result.errors if e.rule == "compile_invalid_component_name"
        ]
        assert named, [e.rule for e in result.errors]
        assert "컴파일 시에는 이름 규약이 필수" in named[0].message
        assert all(not e.is_warning for e in named)


def test_nonconforming_agent_and_local_skill_name_rejected(tmp_path):
    """에이전트·로컬 스킬 이름도 게이트 규약 검사 대상이다."""
    from tests.compiler.builders import make_agent

    agent = make_agent("Worker Agent")  # 공백+대문자
    agent.skills = [make_procedural(name="Local Skill")]
    project = PluginProject(name="p", agents=[agent])

    result = compile_project(project, tmp_path)
    assert not result.ok
    assert result.written == []
    named = [e for e in result.errors if e.rule == "compile_invalid_component_name"]
    sources = {e.source for e in named}
    assert "Worker Agent" in sources
    assert "Local Skill" in sources


def test_validator_keeps_warning_grade_for_invalid_name():
    """F7 검증기의 invalid_component_name은 경고 등급 그대로 유지된다
    (게이트만 엄격 — 편집 중에는 경고가 맞다)."""
    from daedalus.model.validation import Validator

    project = PluginProject(name="p", skills=[make_procedural(name="My Skill")])
    findings = Validator.validate_project(project)
    named = [f for f in findings if f.rule == "invalid_component_name"]
    assert named
    assert all(f.is_warning for f in named)


def test_clean_project_still_passes_after_gate_hardening(tmp_path):
    """정상 프로젝트(규약 이름 + 충돌 없음)는 강화된 게이트를 그대로 통과한다."""
    from tests.compiler.builders import make_agent

    agent = make_agent("a1")
    agent.skills = [make_procedural(name="local-proc")]
    project = PluginProject(
        name="p", skills=[make_procedural(name="top-skill")], agents=[agent]
    )
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    assert (tmp_path / "skills" / "top-skill" / "SKILL.md").exists()
    assert (tmp_path / "agents" / "a1.md").exists()
    assert (tmp_path / "skills" / "a1--local-proc" / "SKILL.md").exists()


# ─────────────────────── 리뷰 마이너 후속 ───────────────────────


def test_gate_rules_registered_in_compiler_error_rules(tmp_path):
    """게이트가 발급하는 rule은 전부 COMPILER_ERROR_RULES에 등록되어 있고,
    WARNING_RULES와 겹치지 않아야 한다 (등급 의도의 단일 진실)."""
    from daedalus.compiler.project_compiler import COMPILER_ERROR_RULES
    from daedalus.model.validation import WARNING_RULES
    from tests.compiler.builders import make_agent

    assert not (COMPILER_ERROR_RULES & WARNING_RULES)

    # 두 게이트 에러를 동시에 유발하는 프로젝트로 발급 rule ⊆ 등록 집합 고정
    agent1 = make_agent("a--b")
    agent1.skills = [make_procedural(name="c")]
    agent2 = make_agent("a")
    agent2.skills = [make_procedural(name="b--c")]
    project = PluginProject(
        name="p", skills=[make_procedural(name="Bad Name")], agents=[agent1, agent2]
    )
    result = compile_project(project, tmp_path)
    emitted = {e.rule for e in result.errors if e.rule.startswith("compile_")}
    assert emitted == COMPILER_ERROR_RULES, (
        f"발급 {emitted} vs 등록 {COMPILER_ERROR_RULES}"
    )


def test_skipped_includes_local_skills(tmp_path):
    """거부 시 skipped에 에이전트 로컬 스킬도 포함된다."""
    from tests.compiler.builders import make_agent

    agent = make_agent("a1")
    agent.skills = [make_procedural(name="local-proc")]
    project = PluginProject(
        name="p", skills=[make_procedural(name="Bad Name")], agents=[agent]
    )
    result = compile_project(project, tmp_path)
    assert not result.ok
    labels = [label for _, label in result.skipped]
    assert any("local-proc" in lb for lb in labels), labels
    assert any("a1" in lb for lb in labels)
