# tests/compiler/test_work_resume.py
"""WP-RS: 작업 재개(플러그인 FSM 진행 상태 저장) — 컴파일러 배출 3종 + SessionStart 훅.

단위 단독 진실: state/__progress__.json 규약(docs/plans/2026-08-02-wp-rs-work-resume.md).
저장 단위는 플러그인 FSM(프로젝트 그래프)의 위치 — 스킬 내부 FSM 상태는 다루지 않는다.
"""
from __future__ import annotations

import json

from daedalus.compiler.emit import compile_agent, compile_hooks_json, compile_skill
from daedalus.compiler.project_compiler import compile_project
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.hook import HookDef, HookEvent
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project

from tests.compiler.builders import (
    make_agent,
    make_declarative,
    make_procedural,
    make_transfer,
)


def _placed_pair():
    """a → b 전이가 있는 project.graph — a는 outgoing 존재(비-터미널) 배치."""
    a = make_procedural(name="a")
    b = make_procedural(name="b")
    project = PluginProject(name="p", skills=[a, b])
    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    project.graph.states += [sa, sb]
    project.graph.transitions.append(
        Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    )
    return project, a, b


def _placed_terminal():
    """outgoing 전이가 없는 단독 배치(터미널)."""
    c = make_procedural(name="c")
    project = PluginProject(name="p", skills=[c])
    sc = SimpleState(name="c", skill_ref=c)
    project.graph.states += [sc]
    return project, c


# ── 1) 배치 스킬: 프리앰블 + 다음 단계 갱신 규칙 + 터미널 완료 단락 ──


def test_placed_skill_has_resume_preamble_with_name():
    project, a, _ = _placed_pair()
    text = compile_skill(a, project=project)
    assert "## 작업 재개" in text
    assert "이 스킬(`a`)" in text
    assert "state/__progress__.json" in text


def test_resume_preamble_before_body():
    project, a, _ = _placed_pair()
    text = compile_skill(a, project=project)
    fm_end = text.index("\n---\n") + len("\n---\n")
    preamble_idx = text.index("## 작업 재개")
    body_idx = text.index("Do the work.")
    assert fm_end <= preamble_idx < body_idx


def test_placed_skill_next_steps_has_progress_update_rule():
    project, a, _ = _placed_pair()
    text = compile_skill(a, project=project)
    assert "## 다음 단계" in text
    assert "`completed`에 추가하고" in text
    assert "## 작업 완료" not in text
    # 갱신 규칙은 "다음 단계" 단락 뒤쪽에 위치한다.
    assert text.index("## 다음 단계") < text.index("`completed`에 추가하고")


def test_terminal_placement_gets_completion_section_instead_of_next_steps():
    project, c = _placed_terminal()
    text = compile_skill(c, project=project)
    assert "## 작업 재개" in text  # 배치된 ProceduralSkill이므로 프리앰블은 여전히 있음
    assert "## 작업 완료" in text
    assert "## 다음 단계" not in text
    assert '`current`를 `"done"`으로' in text


# ── 2) 미배치 스킬 / 에이전트 .md / 로컬 스킬: 단락 부재 ──


def test_unplaced_skill_no_resume_sections():
    a = make_procedural(name="a")
    project = PluginProject(name="p", skills=[a])  # 그래프에 배치 안 함
    text = compile_skill(a, project=project)
    assert "## 작업 재개" not in text
    assert "## 작업 완료" not in text


def test_no_project_no_resume_sections():
    a = make_procedural(name="a")
    text = compile_skill(a)  # project 없음
    assert "## 작업 재개" not in text
    assert "## 작업 완료" not in text


def test_agent_md_has_no_resume_sections_even_if_placed():
    agent = make_agent("worker")
    project = PluginProject(name="p", agents=[agent])
    sa = SimpleState(name="worker", skill_ref=agent)
    project.graph.states += [sa]
    text = compile_agent(agent, project=project)
    assert "## 작업 재개" not in text
    assert "## 작업 완료" not in text


def test_local_skill_no_resume_sections():
    """로컬 스킬(에이전트 소유)은 프로젝트 그래프 placement 대상이 아니다."""
    local = make_procedural(name="local-proc")
    project, a, _ = _placed_pair()
    text = compile_skill(local, local=True, project=project)
    assert "## 작업 재개" not in text
    assert "## 작업 완료" not in text


# ── 3) TransferSkill: 전이 중 note ──


def test_transfer_skill_has_progress_note():
    edge = make_transfer("edge-skill")
    text = compile_skill(edge)
    assert "state/__progress__.json" in text
    assert "전이 맥락을 기록하라" in text


def test_local_transfer_skill_no_progress_note():
    edge = make_transfer("edge-skill")
    text = compile_skill(edge, local=True)
    assert "전이 맥락을 기록하라" not in text


def test_transfer_skill_note_after_body():
    edge = make_transfer("edge-skill")
    text = compile_skill(edge)
    body_idx = text.index("Run on edge.")
    note_idx = text.index("전이 맥락을 기록하라")
    assert body_idx < note_idx


# ── 4) hooks.json: SessionStart 합성 ──


def test_hooks_json_default_emits_session_start():
    project, a, _ = _placed_pair()
    text = compile_hooks_json(project)
    assert text is not None
    obj = json.loads(text)
    assert "SessionStart" in obj["hooks"]
    entry = obj["hooks"]["SessionStart"][0]["hooks"][0]
    assert entry["type"] == "command"
    assert "state/__progress__.json" in entry["command"]


def test_hooks_json_none_when_emit_progress_hook_false():
    project, a, _ = _placed_pair()
    project.emit_progress_hook = False
    assert compile_hooks_json(project) is None


def test_hooks_json_none_when_no_placements():
    project = PluginProject(name="p", skills=[make_procedural(name="a")])
    # project.graph는 EntryPoint만 있는 기본 빈 그래프 — placement 없음.
    assert compile_hooks_json(project) is None


def test_hooks_json_coexists_with_user_session_start_hook():
    user_hook = HookDef(
        name="greet", description="인사", event=HookEvent.SESSION_START,
        command="echo hi",
    )
    agent = make_agent("worker")
    agent.config.hooks = {"greet": {}}
    project, a, _ = _placed_pair()
    project.agents = [agent]
    project.hook_library = [user_hook]

    text = compile_hooks_json(project)
    obj = json.loads(text)
    groups = obj["hooks"]["SessionStart"]
    commands = [g["hooks"][0]["command"] for g in groups]
    assert "echo hi" in commands
    assert any("state/__progress__.json" in c for c in commands)
    # 사용자 훅이 먼저, 합성 진행 훅이 뒤에 이어붙는다.
    assert commands.index("echo hi") < next(
        i for i, c in enumerate(commands) if "state/__progress__.json" in c
    )


def test_compile_project_writes_session_start_hook(tmp_path):
    project, a, _ = _placed_pair()
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    hooks_path = tmp_path / "hooks" / "hooks.json"
    assert hooks_path.exists()
    obj = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert "SessionStart" in obj["hooks"]


# ── 5) 직렬화: emit_progress_hook 왕복 ──


def test_serialize_roundtrip_emit_progress_hook_false():
    project, _, _ = _placed_pair()
    project.emit_progress_hook = False
    data = serialize_project(project)
    assert data["emit_progress_hook"] is False
    restored = deserialize_project(data)
    assert restored.emit_progress_hook is False


def test_serialize_roundtrip_emit_progress_hook_true():
    project, _, _ = _placed_pair()
    assert project.emit_progress_hook is True
    data = serialize_project(project)
    assert data["emit_progress_hook"] is True
    restored = deserialize_project(data)
    assert restored.emit_progress_hook is True


def test_deserialize_legacy_file_without_key_defaults_true():
    project, _, _ = _placed_pair()
    data = serialize_project(project)
    del data["emit_progress_hook"]  # 구버전 파일 시뮬레이션 — 키 부재
    restored = deserialize_project(data)
    assert restored.emit_progress_hook is True


# ── 6) 결정성 ──


def test_compile_project_deterministic_with_progress_features(tmp_path):
    project, _, _ = _placed_pair()
    out1 = tmp_path / "a"
    out2 = tmp_path / "b"
    compile_project(project, out1)
    compile_project(project, out2)

    for rel in ["skills/a/SKILL.md", "skills/b/SKILL.md", "hooks/hooks.json"]:
        raw1 = (out1 / rel).read_bytes()
        raw2 = (out2 / rel).read_bytes()
        assert raw1 == raw2, f"{rel} 바이트 비결정적"


def test_compile_skill_deterministic_across_calls():
    project, a, _ = _placed_pair()
    text1 = compile_skill(a, project=project)
    text2 = compile_skill(a, project=project)
    assert text1 == text2
