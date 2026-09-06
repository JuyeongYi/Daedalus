"""A6 검증 규칙 — skill_only_variable_in_body.

(orphan_hook은 2026-09-07 퇴역 — 플러그인 훅은 전역이라 부착 없이도 배출된다.)
"""
from __future__ import annotations

from daedalus.model.plugin.hook import CommandHook, HookDef, HookEvent
from daedalus.model.plugin.workspace_doc import WorkspaceDoc
from daedalus.model.project import PluginProject
from daedalus.model.validation import Validator

from tests.compiler.builders import make_agent, make_procedural


def _rules(project, rule: str) -> list[str]:
    return [e.rule for e in Validator.validate_project(project) if e.rule == rule]


def _hook(name: str = "fmt") -> HookDef:
    return HookDef(
        name=name, description="", event=HookEvent.POST_TOOL_USE,
        handlers=[CommandHook(script="fmt")],
    )


# --- skill_only_variable_in_body -------------------------------------------


def _agent_project(body: str) -> PluginProject:
    agent = make_agent()
    agent.body = body
    return PluginProject(name="p", agents=[agent])


def test_arguments_in_agent_body_is_flagged():
    project = _agent_project("Use $ARGUMENTS as the target path.")
    assert _rules(project, "skill_only_variable_in_body") == [
        "skill_only_variable_in_body"
    ]


def test_indexed_arguments_is_flagged_by_the_same_token():
    """`$ARGUMENTS[0]`은 `$ARGUMENTS` 부분 문자열이라 한 번만 경고한다."""
    project = _agent_project("First arg: $ARGUMENTS[0]")
    assert _rules(project, "skill_only_variable_in_body") == [
        "skill_only_variable_in_body"
    ]


def test_session_id_in_agent_body_is_flagged():
    project = _agent_project("Log to ${CLAUDE_SESSION_ID}.log")
    assert _rules(project, "skill_only_variable_in_body") == [
        "skill_only_variable_in_body"
    ]


def test_skill_dir_in_agent_is_left_to_the_dedicated_rule():
    """중복 경고 금지 — 에이전트의 ${CLAUDE_SKILL_DIR}는 기존 규칙만 짚는다."""
    project = _agent_project("Read ${CLAUDE_SKILL_DIR}/data.json")
    rules = [e.rule for e in Validator.validate_project(project)]
    assert rules.count("skill_dir_token_in_agent") == 1
    assert "skill_only_variable_in_body" not in rules


def test_code_span_mention_is_not_flagged():
    project = _agent_project("스킬 본문에서는 `$ARGUMENTS`가 치환된다.")
    assert _rules(project, "skill_only_variable_in_body") == []


def test_fenced_mention_is_not_flagged():
    project = _agent_project("```md\n$ARGUMENTS\n${CLAUDE_SESSION_ID}\n```\n")
    assert _rules(project, "skill_only_variable_in_body") == []


def test_skill_body_is_not_flagged():
    """스킬 본문에서는 정상 치환되므로 대상이 아니다."""
    skill = make_procedural(body="Target: $ARGUMENTS\nDir: ${CLAUDE_SKILL_DIR}/x")
    project = PluginProject(name="p", skills=[skill])
    assert _rules(project, "skill_only_variable_in_body") == []


def test_claude_md_body_is_flagged_including_skill_dir():
    """작업 폴더 문서는 기존 규칙의 대상이 아니므로 세 토큰 모두 검사한다."""
    project = PluginProject(
        name="p",
        claude_md=WorkspaceDoc(name="p", body="Run with ${CLAUDE_SKILL_DIR}/run.sh"),
    )
    assert _rules(project, "skill_only_variable_in_body") == [
        "skill_only_variable_in_body"
    ]


def test_rule_doc_body_is_flagged():
    project = PluginProject(
        name="p",
        rules=[WorkspaceDoc(name="style", body="Args: $ARGUMENTS")],
    )
    errs = [
        e for e in Validator.validate_project(project)
        if e.rule == "skill_only_variable_in_body"
    ]
    assert len(errs) == 1
    assert "style" in errs[0].source
    assert errs[0].is_warning


def test_multiple_tokens_report_each():
    project = _agent_project("$ARGUMENTS and ${CLAUDE_SESSION_ID}")
    assert _rules(project, "skill_only_variable_in_body") == [
        "skill_only_variable_in_body"
    ] * 2
