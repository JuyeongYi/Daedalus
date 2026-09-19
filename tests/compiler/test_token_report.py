# tests/compiler/test_token_report.py
"""토큰 비용 리포트 (A5-lite) — 추정 휴리스틱 + CompileResult 동봉 + 산출 불변.

핵심 계약 3가지:
  1. 리포트는 **표시 전용**이다 — 산출 파일 텍스트가 바이트 단위로 불변이어야 한다.
  2. 임계 초과는 **검증 규칙이 아니다** — WARNING_RULES에 들어가지 않고
     CompileResult.warnings/errors도 늘리지 않는다.
  3. 외부 토크나이저에 의존하지 않는다(순수 stdlib).
"""
from __future__ import annotations

from pathlib import Path

from daedalus.compiler import compile_project
from daedalus.compiler.token_report import (
    DEFAULT_FILE_TOKEN_THRESHOLD,
    TokenKind,
    TokenReport,
    estimate_tokens,
)
from daedalus.model.project import PluginProject
from daedalus.model.validation import WARNING_RULES

from .builders import make_agent, make_procedural


# ─────────────────────────── 추정 휴리스틱 ───────────────────────────


def test_estimate_empty_is_zero():
    assert estimate_tokens("") == 0


def test_estimate_ascii_is_about_quarter_of_chars():
    text = "a" * 400
    assert estimate_tokens(text) == 100


def test_estimate_non_ascii_costs_more_per_char():
    """한글은 같은 글자 수라도 토큰이 더 많이 든다 — 한 구간으로 뭉치면 과소평가."""
    assert estimate_tokens("가" * 300) > estimate_tokens("a" * 300)


def test_estimate_is_monotonic_in_length():
    short = estimate_tokens("hello world")
    long = estimate_tokens("hello world" * 10)
    assert 0 < short < long


# ─────────────────────────── TokenReport ───────────────────────────


def test_report_totals_and_no_notice_under_threshold():
    report = TokenReport()
    report.add("skills/a/SKILL.md", "skill", "a" * 40, token_kind=TokenKind.CONTEXT)
    report.add("agents/b.md", "agent", "b" * 80, token_kind=TokenKind.CONTEXT)
    assert report.total_chars == 120
    assert report.total_tokens == 10 + 20
    assert report.over_threshold() == []
    assert report.notice() is None
    assert "30" in report.summary()


def test_report_notice_only_for_context_kinds():
    """설정 파일(schemas/hooks)은 대화 컨텍스트에 실리지 않으므로 임계로 재지 않는다."""
    big = "a" * (DEFAULT_FILE_TOKEN_THRESHOLD * 4 + 400)
    report = TokenReport()
    report.add(
        "schemas/p.json", "schemas_json", big, token_kind=TokenKind.TOTAL_ONLY,
    )
    assert report.notice() is None
    assert report.total_tokens > DEFAULT_FILE_TOKEN_THRESHOLD

    report.add("skills/fat/SKILL.md", "skill", big, token_kind=TokenKind.CONTEXT)
    notice = report.notice()
    assert notice is not None
    assert "skills/fat/SKILL.md" in notice
    assert [e.path for e in report.over_threshold()] == ["skills/fat/SKILL.md"]


def test_report_entry_shape():
    """항목은 값만 들고, 임계 판정은 리포트가 한다 — 진실이 둘이면 안 된다."""
    report = TokenReport()
    entry = report.add(
        "skills/a/SKILL.md", "skill", "hello", token_kind=TokenKind.CONTEXT,
    )
    assert (entry.path, entry.kind, entry.chars) == ("skills/a/SKILL.md", "skill", 5)
    assert report.threshold == DEFAULT_FILE_TOKEN_THRESHOLD
    assert not hasattr(entry, "over_threshold")


# ─────────────────────── compile_project 동봉 ───────────────────────


def _project() -> PluginProject:
    return PluginProject(
        name="p", skills=[make_procedural("demo-skill")], agents=[make_agent("worker")],
    )


def test_compile_result_carries_report_matching_written_files(tmp_path):
    result = compile_project(_project(), tmp_path)
    assert result.ok
    report = result.token_report

    paths = {e.path for e in report.entries}
    written_rel = {
        Path(p).relative_to(tmp_path).as_posix() for p in result.written
    }
    assert paths == written_rel

    # 각 항목의 추정치가 실제 산출 텍스트에서 계산된 값과 같아야 한다.
    for entry in report.entries:
        text = (tmp_path / entry.path).read_text(encoding="utf-8")
        assert entry.chars == len(text)
        assert entry.tokens == estimate_tokens(text)
    assert report.total_tokens == sum(e.tokens for e in report.entries)


def test_report_does_not_change_output_bytes(tmp_path):
    """리포트는 결과 객체·UI 전용 — 산출 텍스트를 건드리지 않는다."""
    a = tmp_path / "a"
    result = compile_project(_project(), a)
    assert result.ok
    before = {
        p.relative_to(a).as_posix(): p.read_bytes() for p in a.rglob("*") if p.is_file()
    }

    b = tmp_path / "b"
    compile_project(_project(), b)
    after = {
        p.relative_to(b).as_posix(): p.read_bytes() for p in b.rglob("*") if p.is_file()
    }
    assert before == after  # 결정적 산출 — 리포트가 끼어도 동일


def test_over_threshold_is_informational_not_a_validation_rule(tmp_path):
    """임계 초과는 경고/에러를 늘리지 않고 컴파일도 막지 않는다."""
    fat = make_procedural("fat-skill", body="word " * (DEFAULT_FILE_TOKEN_THRESHOLD * 2))
    project = PluginProject(name="p", skills=[fat])

    result = compile_project(project, tmp_path)
    assert result.ok
    assert result.written
    notice = result.token_report.notice()
    assert notice is not None
    # 검증 결과에 섞이지 않는다
    assert all(e.rule != "token_budget" for e in result.warnings + result.errors)
    assert not any("토큰" in e.message for e in result.warnings)


def test_token_rules_are_not_registered_as_validation_rules():
    for name in ("token_budget", "token_threshold_exceeded", "over_token_threshold"):
        assert name not in WARNING_RULES


# ─────────────────── 공통 안내 파일 (WP-FK2 C3) ───────────────────


def _guide_project() -> PluginProject:
    """가이드 둘이 모두 계획에 오르는 프로젝트 — 배치된 스킬 + 블랙보드."""
    from daedalus.model.fsm.blackboard import Blackboard, DynamicClass, DynamicField
    from daedalus.model.fsm.event import CompletionEvent
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.transition import Transition
    from daedalus.model.fsm.variable import FieldType

    a, b = make_procedural("a"), make_procedural("b")
    project = PluginProject(
        name="p", skills=[a, b],
        blackboard=Blackboard(class_definitions=[DynamicClass(
            name="Task", description="d",
            fields=[DynamicField(name="step", field_type=FieldType.INT)],
        )]),
    )
    sa, sb = SimpleState(name="a", skill_ref=a), SimpleState(name="b", skill_ref=b)
    project.graph.states += [sa, sb]
    project.graph.transitions.append(
        Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    )
    return project


def test_guide_kinds_are_declared_context_and_guide():
    """가이드도 모델이 Read로 읽는 산문이다 — 임계 판정 대상이고 고지 줄 대상이다.

    종전에는 이 사실이 `token_report.CONTEXT_KINDS`라는 kind 문자열 **사본**에
    적혀 있어, 개명하면 토큰 리포트만 조용히 가이드를 못 알아봤다. 이제 판정은
    산출 계획이 선언한다(WP-5) — 그래서 **계획 행의 선언**을 직접 본다.
    kind 문자열의 소유자가 `compiler/plan_kinds.py` 하나임도 함께 고정한다.
    """
    from daedalus.compiler import plan_kinds
    from daedalus.compiler.emit.guides import GUIDE_KINDS
    from daedalus.compiler.token_report import TokenKind
    from daedalus.compiler.units import CompileContext, Gate
    from daedalus.compiler.units.docs import GUIDE_UNITS

    assert GUIDE_KINDS is plan_kinds.GUIDE_KINDS

    project = _guide_project()
    ctx = CompileContext.build(project, dry_run=True)
    rows = [row for unit in GUIDE_UNITS for row in unit.plan(ctx, Gate())]
    assert [row.kind for row in rows] == list(GUIDE_KINDS)
    for row in rows:
        assert row.token_kind is TokenKind.CONTEXT
        assert row.is_guide is True


def test_report_lists_each_guide_as_its_own_entry(tmp_path):
    """가이드 둘은 kind가 다른 **별도 항목**으로 리포트에 실린다."""
    from daedalus.model.fsm.blackboard import Blackboard, DynamicClass, DynamicField
    from daedalus.model.fsm.event import CompletionEvent
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.transition import Transition
    from daedalus.model.fsm.variable import FieldType

    a, b = make_procedural("a"), make_procedural("b")
    project = PluginProject(
        name="p", skills=[a, b],
        blackboard=Blackboard(class_definitions=[DynamicClass(
            name="Task", description="d",
            fields=[DynamicField(name="step", field_type=FieldType.INT)],
        )]),
    )
    sa, sb = SimpleState(name="a", skill_ref=a), SimpleState(name="b", skill_ref=b)
    project.graph.states += [sa, sb]
    project.graph.transitions.append(
        Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    )

    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    by_path = {e.path: e for e in result.token_report.entries}
    assert by_path["guides/p/workflow.md"].kind == "guide_workflow"
    assert by_path["guides/p/blackboard.md"].kind == "guide_blackboard"
    assert by_path["guides/p/workflow.md"].tokens > 0


def test_notice_adds_a_line_about_the_shared_guides():
    """가이드 토큰은 포인터를 받은 컴포넌트가 실행될 때마다 **추가로** 실린다."""
    big = "a" * (DEFAULT_FILE_TOKEN_THRESHOLD * 4 + 400)
    report = TokenReport()
    report.add("skills/fat/SKILL.md", "skill", big, token_kind=TokenKind.CONTEXT)
    assert "공통 안내 파일" not in report.notice()

    report.add(
        "guides/p/workflow.md", "guide_workflow", "b" * 400,
        token_kind=TokenKind.CONTEXT, is_guide=True,
    )
    notice = report.notice()
    assert "공통 안내 파일 ≈100토큰" in notice
    assert "실행될 때마다 추가로 실립니다" in notice


def test_guides_line_shows_even_when_nothing_is_over_threshold():
    """가이드는 임계(5,000)를 넘을 일이 없다 — 초과 문단에만 붙이면 영영 안 보인다."""
    report = TokenReport()
    report.add("skills/a/SKILL.md", "skill", "a" * 400, token_kind=TokenKind.CONTEXT)
    report.add(
        "guides/p/workflow.md", "guide_workflow", "b" * 400,
        token_kind=TokenKind.CONTEXT, is_guide=True,
    )
    assert report.over_threshold() == []
    notice = report.notice()
    assert notice is not None
    assert notice.startswith("공통 안내 파일 ≈100토큰")
    assert "임계" not in notice


def test_real_compile_reports_the_guides_line(tmp_path):
    """도그푸드 형상 — 임계를 넘는 파일이 없어도 가이드 줄은 나온다."""
    from daedalus.model.fsm.event import CompletionEvent
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.transition import Transition

    a, b = make_procedural("a"), make_procedural("b")
    project = PluginProject(name="p", skills=[a, b])
    sa, sb = SimpleState(name="a", skill_ref=a), SimpleState(name="b", skill_ref=b)
    project.graph.states += [sa, sb]
    project.graph.transitions.append(
        Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    )
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    assert result.token_report.over_threshold() == []
    assert "공통 안내 파일" in (result.token_report.notice() or "")


def test_gate_rejected_compile_has_empty_report(tmp_path):
    """게이트에 막히면 쓴 파일이 없으므로 리포트도 비어 있다."""
    project = PluginProject(name="Bad Name", skills=[make_procedural("demo-skill")])
    result = compile_project(project, tmp_path)
    assert not result.ok
    assert result.token_report.entries == []
    assert result.token_report.total_tokens == 0
