"""작업 폴더 문서 배출 — `.claude/rules/*.md` + `.claude/CLAUDE.md` 구역 병합 (WP-WD).

`.claude/CLAUDE.md`는 **사용자·팀의 파일**이라 통째로 쓸 수 없다. 플러그인마다
`<!-- daedalus:<플러그인> open/close -->` 두 줄로 자기 구역을 만들고 그 안만 갈아
끼운다(D9). 덕분에 ① 구역 밖 사용자 내용이 보존되고 ② ddls 플러그인 여럿이 한
파일에 공존하며 ③ 재빌드가 멱등이다.

HTML 주석은 CC가 컨텍스트 주입 전에 제거하므로 표식의 토큰 비용은 0이다.
"""
from __future__ import annotations

import pytest

from daedalus.compiler.project_compiler import compile_project
from daedalus.compiler.workspace import merge_claude_md
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.workspace_doc import WorkspaceDoc
from daedalus.model.project import PluginProject


def _project(name: str = "my-plugin", **kwargs) -> PluginProject:
    project = PluginProject(name=name, **kwargs)
    project.build_target = BuildTarget.LOCAL
    return project


# ─────────────────────── 구역 병합 (순수 함수) ───────────────────────


def test_creates_file_with_markers_when_absent():
    """새로 만들 때도 표식을 남긴다 — 안 남기면 다음 빌드가 남의 파일로 본다."""
    text, warning = merge_claude_md(None, "alpha", title="alpha", body="be careful")
    assert warning is None
    assert "<!-- daedalus:alpha open -->" in text
    assert "<!-- daedalus:alpha close -->" in text
    assert "# alpha" in text
    assert "be careful" in text


def test_replaces_region_in_place():
    existing = (
        "# Team rules\n\nkeep this\n\n"
        "<!-- daedalus:alpha open -->\n# alpha\n\nOLD\n"
        "<!-- daedalus:alpha close -->\n\ntrailing user text\n"
    )
    text, warning = merge_claude_md(existing, "alpha", title="alpha", body="NEW")
    assert warning is None
    assert "OLD" not in text
    assert "NEW" in text
    # 구역 밖은 그대로, 위치도 보존된다.
    assert text.index("keep this") < text.index("NEW") < text.index("trailing user text")


def test_is_idempotent():
    first, _ = merge_claude_md(None, "alpha", title="alpha", body="x")
    second, _ = merge_claude_md(first, "alpha", title="alpha", body="x")
    assert second == first


def test_appends_region_when_file_has_no_region():
    existing = "# Team rules\n\nkeep this\n"
    text, warning = merge_claude_md(existing, "alpha", title="alpha", body="x")
    assert warning is None
    assert text.startswith("# Team rules")
    assert text.index("keep this") < text.index("<!-- daedalus:alpha open -->")


def test_two_plugins_coexist():
    """이 병합 방식이 존재하는 이유 — 고정 파일명이지만 서로 덮지 않는다."""
    first, _ = merge_claude_md(None, "alpha", title="alpha", body="A body")
    both, warning = merge_claude_md(first, "beta", title="beta", body="B body")
    assert warning is None
    assert "A body" in both and "B body" in both
    assert both.count("<!-- daedalus:alpha open -->") == 1
    assert both.count("<!-- daedalus:beta open -->") == 1


def test_other_plugin_region_is_untouched():
    first, _ = merge_claude_md(None, "alpha", title="alpha", body="A1")
    both, _ = merge_claude_md(first, "beta", title="beta", body="B1")
    updated, _ = merge_claude_md(both, "alpha", title="alpha", body="A2")
    assert "A2" in updated and "B1" in updated and "A1" not in updated


def test_empty_body_removes_region():
    existing, _ = merge_claude_md(None, "alpha", title="alpha", body="x")
    text, warning = merge_claude_md(existing, "alpha", title="alpha", body="   ")
    assert warning is None
    assert "<!-- daedalus:alpha open -->" not in text
    assert "x" not in text


def test_empty_body_with_no_region_is_a_no_op():
    """구역이 없고 쓸 내용도 없으면 파일을 건드리지 않는다."""
    text, warning = merge_claude_md("# Team rules\n", "alpha", title="alpha", body="")
    assert text is None and warning is None


def test_body_with_own_h1_is_not_double_titled():
    text, _ = merge_claude_md(
        None, "alpha", title="alpha", body="# My own title\n\nbody"
    )
    assert text.count("# ") == 1
    assert "# My own title" in text


# ─────────────────────── 손상 입력 — 절대 먹지 않는다 ───────────────────────


@pytest.mark.parametrize(
    "existing",
    [
        # close 없음 — 끝을 추측하면 뒤 내용을 통째로 날린다.
        "<!-- daedalus:alpha open -->\nstuff\n\nuser content after\n",
        # open이 둘
        "<!-- daedalus:alpha open -->\na\n<!-- daedalus:alpha close -->\n"
        "<!-- daedalus:alpha open -->\nb\n<!-- daedalus:alpha close -->\n",
        # close가 open보다 앞
        "<!-- daedalus:alpha close -->\nx\n<!-- daedalus:alpha open -->\n",
        # open 없이 close만
        "user text\n<!-- daedalus:alpha close -->\n",
    ],
)
def test_malformed_region_is_refused_without_touching_the_file(existing):
    text, warning = merge_claude_md(existing, "alpha", title="alpha", body="NEW")
    assert text is None, "손상 입력에서는 어떤 내용도 쓰지 않는다"
    assert warning and "alpha" in warning


# ─────────────────────── 컴파일 산출 ───────────────────────


def test_rules_are_written_to_claude_rules(tmp_path):
    project = _project(
        rules=[
            WorkspaceDoc(name="testing", body="run pytest"),
            WorkspaceDoc(name="api-design", body="validate input"),
        ]
    )
    result = compile_project(project, tmp_path)
    assert not result.errors, [e.message for e in result.errors]
    assert (tmp_path / ".claude" / "rules" / "testing.md").read_text(
        encoding="utf-8"
    ) == "run pytest\n"
    assert (tmp_path / ".claude" / "rules" / "api-design.md").is_file()


def test_empty_rule_is_not_written(tmp_path):
    project = _project(rules=[WorkspaceDoc(name="testing", body="  ")])
    compile_project(project, tmp_path)
    assert not (tmp_path / ".claude" / "rules" / "testing.md").exists()


def test_claude_md_region_written(tmp_path):
    project = _project(claude_md=WorkspaceDoc(name="my-plugin", body="always lint"))
    result = compile_project(project, tmp_path)
    assert not result.errors
    text = (tmp_path / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
    assert "<!-- daedalus:my-plugin open -->" in text
    assert "always lint" in text


def test_claude_md_preserves_user_content(tmp_path):
    target = tmp_path / ".claude"
    target.mkdir()
    (target / "CLAUDE.md").write_text("# Ours\n\nhand written\n", encoding="utf-8")
    project = _project(claude_md=WorkspaceDoc(name="my-plugin", body="always lint"))
    compile_project(project, tmp_path)
    text = (target / "CLAUDE.md").read_text(encoding="utf-8")
    assert "hand written" in text and "always lint" in text


def test_malformed_claude_md_warns_and_leaves_file(tmp_path):
    target = tmp_path / ".claude"
    target.mkdir()
    broken = "<!-- daedalus:my-plugin open -->\nhalf\n\nuser tail\n"
    (target / "CLAUDE.md").write_text(broken, encoding="utf-8")
    project = _project(claude_md=WorkspaceDoc(name="my-plugin", body="always lint"))
    result = compile_project(project, tmp_path)
    assert (target / "CLAUDE.md").read_text(encoding="utf-8") == broken
    assert any(e.rule == "unmergeable_claude_md" for e in result.warnings)


def test_marketplace_build_emits_nothing(tmp_path):
    project = PluginProject(
        name="my-plugin",
        claude_md=WorkspaceDoc(name="my-plugin", body="x"),
        rules=[WorkspaceDoc(name="testing", body="y")],
    )  # 기본 MARKETPLACE
    compile_project(project, tmp_path)
    assert not (tmp_path / ".claude").exists()


def test_invalid_rule_name_blocks_compile(tmp_path):
    """이름이 파일명이 되므로 컴파일 게이트에서는 에러로 승격된다."""
    project = _project(rules=[WorkspaceDoc(name="Testing Rules", body="x")])
    result = compile_project(project, tmp_path)
    assert any(e.rule == "compile_invalid_component_name" for e in result.errors)
    assert not (tmp_path / ".claude" / "rules").exists()
