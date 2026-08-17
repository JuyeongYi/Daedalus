"""본문 부분 접근 MCP 도구 (WP-BO) — outline / get_section / set_section.

set_body_section은 set_component_body와 같은 문서 경로(WP-BU)를 타야 한다 —
에디터 undo가 듣고, 건드리지 않은 구간이 바이트 보존되는지까지 확인한다.
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject

_BODY = """\
# 개요

도입.

## 규칙

규칙 내용.

## 완료

끝."""


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    s1 = SimpleState(name="Start")
    fsm = StateMachine(name="f", initial_state=s1, states=[s1], final_states=[s1])
    skill = ProceduralSkill(fsm=fsm, name="init", description="d")
    skill.body = _BODY
    win = MainWindow()
    win.set_project(PluginProject(name="p", skills=[skill]))
    yield win
    win.close()


@pytest.fixture
def tools(window):
    from daedalus.mcp.tools import DaedalusTools

    return DaedalusTools(window)


# --- outline ---


def test_outline_lists_headings_without_body(tools):
    out = tools.get_body_outline("init")
    assert [e["heading"] for e in out["outline"]] == ["# 개요", "## 규칙", "## 완료"]
    assert "text" not in out["outline"][0]  # 구조만 — 본문 전송 없음
    assert out["outline"][1]["line_start"] == 5  # 1-based


def test_outline_of_empty_body(tools, window):
    tools._find_component("init").body = ""
    from daedalus.view.editors import body_documents

    body_documents.registry().clear()  # 문서 캐시가 옛 본문을 들고 있지 않게
    assert tools.get_body_outline("init")["outline"] == []


# --- get_section ---


def test_get_section_returns_span_text(tools):
    out = tools.get_body_section("init", "규칙")
    assert out["text"] == "## 규칙\n\n규칙 내용.\n"
    assert out["heading"] == "## 규칙"


def test_get_section_ambiguous_raises(tools):
    tools.set_component_body("init", "## 항목\n\nA\n\n# 다른\n\n## 항목\n\nB")
    with pytest.raises(ValueError, match="여러 섹션과 일치"):
        tools.get_body_section("init", "항목")


def test_get_section_missing_raises_with_outline(tools):
    with pytest.raises(ValueError, match="아웃라인"):
        tools.get_body_section("init", "없음")


# --- set_section ---


def test_set_section_replaces_only_that_span(tools):
    tools.set_body_section("init", "규칙", "## 규칙\n\n새 규칙.\n")
    comp = tools._find_component("init")
    assert comp.body.startswith("# 개요\n\n도입.\n\n")  # 앞 구간 바이트 보존
    assert comp.body.endswith("## 완료\n\n끝.")  # 뒷 구간 바이트 보존
    assert "규칙 내용" not in comp.body
    assert "새 규칙." in comp.body


def test_set_section_is_undoable_in_body_document(tools):
    """문서 경로(WP-BU) — 문서 undo로 되돌아가고 모델이 따라간다."""
    from daedalus.view.editors import body_documents

    tools.set_body_section("init", "규칙", "## 규칙\n\n교체.\n")
    doc = body_documents.registry().document_for(tools._find_component("init"))
    assert doc.isUndoAvailable()
    doc.undo()
    assert "규칙 내용" in doc.toPlainText()


def test_set_section_reads_document_truth_not_stale_model(tools):
    """편집 중에는 문서가 진실 — 모델이 뒤처져 있어도 문서 기준으로 집는다."""
    from PySide6.QtGui import QTextCursor
    from daedalus.view.editors import body_documents

    comp = tools._find_component("init")
    doc = body_documents.registry().document_for(comp)
    cursor = QTextCursor(doc)
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText("\n\n## 추가\n\n문서에만 있는 섹션.")
    # comp.body는 갱신하지 않는다 — 에디터 미개방 상황의 문서 선행 상태 재현

    out = tools.get_body_section("init", "추가")
    assert "문서에만 있는 섹션" in out["text"]
    tools.set_body_section("init", "추가", "## 추가\n\n교체됨.")
    assert "교체됨." in comp.body  # set은 모델을 확정한다


def test_read_does_not_create_document(tools):
    """읽기(outline/get)는 편집 자원을 만들지 않는다 — peek 경로."""
    from daedalus.view.editors import body_documents

    reg = body_documents.registry()
    reg.clear()
    tools.get_body_outline("init")
    tools.get_body_section("init", "규칙")
    assert len(reg) == 0
    tools.set_body_section("init", "규칙", "## 규칙\n\n쓰기는 만든다.\n")
    assert len(reg) == 1


def test_tools_are_exposed(qapp):
    from daedalus.mcp.service import TOOL_NAMES

    for name in ("get_body_outline", "get_body_section", "set_body_section"):
        assert name in TOOL_NAMES
