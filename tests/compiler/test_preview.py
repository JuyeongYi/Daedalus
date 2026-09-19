# tests/compiler/test_preview.py
"""컴파일 미리보기의 **단일 진입점** 계약 (REFACTOR_SPEC §4-d).

종전에는 GUI(`view/actions/preview.py`)와 MCP(`mcp/tools/query.compile_preview`)가
각자 `isinstance(component, Agent)`로 컴파일러를 골랐다 — 같은 질문의 답이 두 벌이라
종류가 늘면 한 표면만 조용히 틀렸다. 이제 실체는 `compiler/preview.py` 하나다.

두 가지를 **양방향**으로 고정한다:
① 산출 파일이 없어도 미리보기는 렌더된다(참조 용도 랩핑 스킬 — 실사용 코퍼스의
   랩핑 스킬이 전부 이 경로다). 게이트를 `emits_output()`으로 걸면 이게 사라진다.
② 산출 **자리**가 없는 종류(`OUTPUT_LOCATION is NONE`)는 미리볼 것이 없다 —
   `can_preview()`가 거짓이고 `preview_component()`는 이유를 말한다.
"""
from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath

import pytest

from daedalus.compiler.preview import (
    can_preview,
    preview_component,
    preview_path,
)
from daedalus.compiler.token_report import TokenKind
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.roles import OutputLocation
from daedalus.model.project import PluginProject
from tests.compiler.builders import make_agent, make_procedural

_SRC = Path(__file__).resolve().parent.parent.parent / "daedalus"


# ── ① 산출 게이트를 거치지 않는다 ────────────────────────────────────

def test_preview_does_not_go_through_the_output_gate():
    """미리보기의 질문은 "이 컴포넌트가 무엇으로 컴파일되는가"이지 "이번 빌드에
    파일이 나가는가"가 아니다 — `emits_output()`으로 게이트를 걸면 이번 빌드에
    파일이 나가지 않는 컴포넌트의 미리보기가 조용히 사라진다.
    """
    skill = make_procedural("review-step")
    assert can_preview(skill)
    preview = preview_component(skill)
    assert preview.text.startswith("---\n")
    assert skill.name in preview.text


# ── ② 산출 자리가 없는 종류는 미리볼 것이 없다 ────────────────────────

class _NoOutputKind:
    """`OUTPUT_LOCATION is NONE`인 종류의 대역 (WP-9 `ExternalAgent`의 선행 조건).

    계약을 **먼저** 못 박아 두지 않으면, 그런 종류가 생겼을 때 진입점이 눌러도
    아무 일이 없는 메뉴 항목을 보여 주게 된다.
    """

    OUTPUT_LOCATION = OutputLocation.NONE
    kind = "no_output_kind"
    name = "external-thing"


def test_a_kind_without_an_output_location_cannot_be_previewed():
    assert not can_preview(_NoOutputKind())


def test_preview_component_of_an_unpreviewable_kind_says_why():
    """거절 이유는 **사용자의 말**이어야 한다 — emitter 등록은 우리 사정이다.

    게이트가 `preview_component` 안에 있어야 GUI(메뉴 흐리기)와 MCP
    (`compile_preview`)가 같은 이유를 말한다(원칙 2·5). 종전에는 MCP만
    `emitter_for`의 "산출 emitter가 없는 컴포넌트 종류입니다 — 등록: …"를
    받아, 내부 등록 누락처럼 읽혔다(WP-9 리뷰).
    """
    with pytest.raises(ValueError) as exc:
        preview_component(_NoOutputKind())
    message = str(exc.value)
    assert "no_output_kind" in message
    assert "산출 파일이 없어" in message
    # 대안을 말한다 — "부르는 쪽을 미리보라".
    assert "부르는 쪽" in message
    assert "emitter" not in message


# ── 경로 ──────────────────────────────────────────────────────────────

def test_preview_path_comes_from_the_component_kind():
    assert preview_path(make_procedural()) == PurePosixPath(
        "skills/my-skill/SKILL.md"
    )
    assert preview_path(make_agent()) == PurePosixPath("agents/worker.md")


def test_preview_path_follows_the_build_target():
    """LOCAL은 컴파일이 곧 설치다 — 산출이 `.claude/` 밑으로 간다."""
    project = PluginProject(name="p", build_target=BuildTarget.LOCAL)
    skill = make_procedural()
    project.skills.append(skill)
    assert preview_path(skill, project) == PurePosixPath(
        ".claude/skills/my-skill/SKILL.md"
    )


def test_preview_declares_the_token_section_the_real_compile_uses():
    preview = preview_component(make_procedural())
    assert preview.token_kind is TokenKind.CONTEXT
    assert preview.plan_kind


# ── 진입점 게이트 ────────────────────────────────────────────────────

#: 미리보기를 여는 표면 4곳 (`_SRC` 기준 상대 POSIX 경로).
#: `docs/design/editor.md` "컴파일 미리보기"의 진입점 목록과 같은 수여야 한다 —
#: 엣지 메뉴는 전이 스킬이 노드가 아니라 엣지에 붙어 생긴 네 번째 표면이다.
_PREVIEW_ENTRY_POINTS = (
    "view/canvas/context_menus.py",       # 캔버스 노드 우클릭
    "view/canvas/scene.py",               # 전이 엣지 우클릭 (전이 스킬)
    "view/panels/registry_panel.py",      # 레지스트리 우클릭
    "view/editors/frontmatter_panel.py",  # 프론트매터 패널 버튼
)


@pytest.mark.parametrize("rel", _PREVIEW_ENTRY_POINTS)
def test_entry_points_gate_on_the_shared_judgment(rel):
    """진입점은 **같은 판정**(`can_preview`)으로 잠근다.

    각 표면이 "산출이 있는가"를 자기 식으로 다시 물으면(예: `emits_output()`)
    참조 용도 랩핑 스킬의 미리보기가 그 표면에서만 조용히 사라진다 — 실제로
    있었던 실패 모드라 판정 이름 자체를 고정한다.
    """
    tree = ast.parse((_SRC / rel).read_text(encoding="utf-8"))
    names = {
        node.attr if isinstance(node, ast.Attribute) else node.id
        for node in ast.walk(tree)
        if isinstance(node, (ast.Attribute, ast.Name))
    }
    assert "can_preview" in names, rel
    assert "emits_output" not in names, rel


# ── 표면들이 같은 실체를 부른다 (원칙 1·2) ────────────────────────────

def test_gui_preview_text_is_the_shared_implementation():
    from daedalus.view.actions.preview import preview_text, preview_title

    skill = make_procedural()
    assert preview_text(skill) == preview_component(skill).text
    assert preview_title(skill) == f"컴파일 미리보기 — {preview_path(skill)}"


def test_gui_preview_title_of_an_agent_names_the_agent_file():
    from daedalus.view.actions.preview import preview_title

    assert preview_title(make_agent()) == "컴파일 미리보기 — agents/worker.md"
