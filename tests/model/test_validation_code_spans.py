"""본문 문자열 규칙이 '설명'을 '사용'으로 오인하지 않는가.

규격을 설명하는 문서 스킬은 플러그인 전용 변수 이름을 언급할 수밖에 없다.
그것을 죽은 경로로 짚으면 고칠 수 없는 경고가 영구히 남는다.
"""
from __future__ import annotations

from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.project import PluginProject
from daedalus.model.validation import Validator, _strip_markdown_code

from tests.compiler.builders import make_procedural


def _rules(body: str) -> list[str]:
    skill = make_procedural(body=body)
    project = PluginProject(
        name="p", skills=[skill], build_target=BuildTarget.LOCAL,
    )
    return [
        e.rule for e in Validator.validate_project(project)
        if e.rule == "plugin_root_in_local_build"
    ]


def test_inline_code_mention_is_not_flagged():
    assert _rules("`${CLAUDE_PLUGIN_ROOT}`는 플러그인 스킬에서만 치환된다.") == []


def test_fenced_code_mention_is_not_flagged():
    body = "예시:\n\n```yaml\ncommand: ${CLAUDE_PLUGIN_ROOT}/bin/x\n```\n"
    assert _rules(body) == []


def test_table_row_with_backticks_is_not_flagged():
    body = "| 변수 | 조건 |\n|---|---|\n| `${CLAUDE_PLUGIN_DATA}` | 플러그인 전용 |\n"
    assert _rules(body) == []


def test_bare_usage_is_still_flagged():
    """코드 표시 없이 그냥 쓴 것은 여전히 실사용으로 본다."""
    assert _rules("스크립트는 ${CLAUDE_PLUGIN_ROOT}/bin/run.sh 를 실행한다.") == [
        "plugin_root_in_local_build"
    ]


def test_mixed_mention_and_usage_flags_the_usage():
    body = (
        "`${CLAUDE_PLUGIN_ROOT}`는 플러그인 전용이다.\n\n"
        "실제 경로: ${CLAUDE_PLUGIN_DATA}/cache\n"
    )
    assert _rules(body) == ["plugin_root_in_local_build"]


# --- 헬퍼 자체 ---


def test_strip_removes_inline_code():
    assert _strip_markdown_code("a `b` c") == "a  c"


def test_strip_removes_fence():
    assert _strip_markdown_code("a\n```\nb\n```\nc").strip() == "a\n\nc".strip()


def test_fence_stripped_before_inline():
    """펜스를 먼저 지워야 그 안의 백틱이 인라인 코드로 잘못 짝지어지지 않는다."""
    body = "```\n`x` and ${CLAUDE_PLUGIN_ROOT}\n```\nreal ${CLAUDE_PLUGIN_DATA}"
    out = _strip_markdown_code(body)
    assert "${CLAUDE_PLUGIN_ROOT}" not in out
    assert "${CLAUDE_PLUGIN_DATA}" in out


def test_unclosed_fence_swallows_to_end():
    """닫히지 않은 펜스는 끝까지 코드로 본다 — 열린 펜스 뒤는 코드 블록이다."""
    assert _strip_markdown_code("a\n```\n${CLAUDE_PLUGIN_ROOT}").strip() == "a"
