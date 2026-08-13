"""본문별 독립 undo 스택 (WP-BU).

고친 고장: ``show_body``가 ``setPlainText``로 내용만 갈아끼웠기 때문에, 다른
컴포넌트를 잠깐 열었다 돌아오면 그 문서의 undo 이력이 통째로 사라져 본문
되돌리기가 불가능했다. 검증은 **컴포넌트를 왕복한 뒤 undo가 먹는지**로 한다 —
왕복 없이 undo만 확인하면 고장이 있어도 통과한다.
"""
from __future__ import annotations

import pytest
from PySide6.QtGui import QTextCursor

from daedalus.view.editors import body_documents


@pytest.fixture(autouse=True)
def _isolate_registry():
    """모듈 전역 레지스트리를 테스트마다 비운다."""
    body_documents.registry().clear()
    yield
    body_documents.registry().clear()


def _make(name: str, body: str = ""):
    from daedalus.model.plugin.skill import DeclarativeSkill
    return DeclarativeSkill(name=name, description="d", body=body)


def _panel():
    from daedalus.view.editors.body_editor import SectionContentPanel
    return SectionContentPanel()


def _type(panel, text: str) -> None:
    """undo 가능한 실제 편집. setPlainText는 undo 스택을 지우므로 쓸 수 없다."""
    cursor = panel._w_content.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(text)


def test_undo_survives_component_switch(qapp):
    """A 편집 → B로 전환 → A 복귀 후에도 undo가 살아있다 (핵심 회귀)."""
    panel = _panel()
    a = _make("a", "alpha")
    b = _make("b", "beta")

    panel.show_body(a)
    _type(panel, " edited")
    assert a.body == "alpha edited"

    panel.show_body(b)      # 다른 컴포넌트로 이탈
    panel.show_body(a)      # 복귀

    panel._w_content.undo()
    assert panel._w_content.toPlainText() == "alpha"
    # 모델도 따라와야 한다 — undo가 textChanged를 발생시키므로 _save_body가 미러링한다
    assert a.body == "alpha"


def test_each_component_keeps_its_own_document(qapp):
    panel = _panel()
    a = _make("a", "alpha")
    b = _make("b", "beta")

    doc_a = body_documents.registry().document_for(a)
    doc_b = body_documents.registry().document_for(b)
    assert doc_a is not doc_b

    panel.show_body(a)
    _type(panel, "-A")
    panel.show_body(b)
    _type(panel, "-B")

    # 각자 자기 편집만 갖는다
    assert a.body == "alpha-A"
    assert b.body == "beta-B"

    # b의 undo가 a를 건드리지 않는다
    panel._w_content.undo()
    assert b.body == "beta"
    assert a.body == "alpha-A"


def test_document_is_reused_across_switches(qapp):
    """왕복해도 같은 문서 객체 — 새로 만들면 이력이 사라진다."""
    panel = _panel()
    a = _make("a", "alpha")
    b = _make("b", "beta")

    panel.show_body(a)
    first = panel._w_content.document()
    panel.show_body(b)
    panel.show_body(a)
    assert panel._w_content.document() is first


def test_initial_body_is_not_undoable(qapp):
    """문서 생성 시 주입한 본문이 undo 한 단계로 남으면 안 된다."""
    panel = _panel()
    a = _make("a", "alpha")
    panel.show_body(a)

    panel._w_content.undo()
    assert panel._w_content.toPlainText() == "alpha"
    assert a.body == "alpha"


def test_discard_drops_document(qapp):
    a = _make("a", "alpha")
    reg = body_documents.registry()
    reg.document_for(a)
    assert len(reg) == 1

    reg.discard(a)
    assert len(reg) == 0


def test_clear_drops_all_documents(qapp):
    reg = body_documents.registry()
    reg.document_for(_make("a"))
    reg.document_for(_make("b"))
    assert len(reg) == 2

    reg.clear()
    assert len(reg) == 0


def test_sync_from_model_updates_existing_document(qapp):
    """외부에서 body를 직접 바꾼 경우에만 쓰는 경로."""
    a = _make("a", "alpha")
    reg = body_documents.registry()
    doc = reg.document_for(a)

    a.body = "rewritten"
    reg.sync_from_model(a)
    assert doc.toPlainText() == "rewritten"


def test_document_for_does_not_clobber_live_edits(qapp):
    """이미 문서가 있으면 모델을 다시 밀어넣지 않는다 (이력 보존)."""
    panel = _panel()
    a = _make("a", "alpha")
    panel.show_body(a)
    _type(panel, " edited")

    doc = body_documents.registry().document_for(a)
    assert doc.toPlainText() == "alpha edited"
