# daedalus/mcp/tools/body.py
"""본문 도구 — 전문 교체와 섹션 단위 읽기/쓰기 (WP-RF-3b).

**계층: GUI 어댑터다 (WP-RF-2 명시).** core(model/compiler)가 아니라
MainWindow·ProjectViewModel·CommandStack·body_documents 등 view 표면에 결합된
코드로, core 경계 계약(tests/test_import_contracts.py)의 대상이 아니다.
모든 메서드는 **Qt 메인 스레드에서 실행되는 것을 전제**로 한다(service가
MainThreadInvoker로 마샬링한다). 편집 도구는 반드시
``ProjectViewModel.execute``(CommandStack)를 거친다 — 사용자가 Ctrl+Z로
되돌릴 수 있어야 한다.

본문 편집만은 예외적으로 컴포넌트의 QTextDocument에 적용한다 — 우회가 아니라
본문 전용 undo 스택(WP-BU)에 정확히 올리는 경로다. 열린 문서가 있으면 그쪽이
진실이다.
"""
from __future__ import annotations

from typing import Any

from ._base import _BaseTools


class BodyTools(_BaseTools):
    """본문 (body) — QTextDocument 경로 (WP-BU) + 섹션 단위 편집 (WP-BO)."""

    def set_component_body(self, name: str, body: str) -> dict[str, Any]:
        """컴포넌트 본문을 교체한다.

        본문은 캔버스와 분리된 자체 undo 스택을 쓰므로(WP-BU) 그 문서에 적용한다 —
        에디터가 열려 있으면 화면에 즉시 반영되고, 편집기에서 Ctrl+Z로 되돌릴 수 있다.
        """
        from PySide6.QtGui import QTextCursor

        from daedalus.view.editors import body_documents

        comp = self._find_component(name)
        old = str(getattr(comp, "body", "") or "")
        doc = body_documents.registry().document_for(comp)

        cursor = QTextCursor(doc)
        cursor.beginEditBlock()  # 1 undo 단위
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(body)
        cursor.endEditBlock()

        # 에디터가 열려 있으면 textChanged가 모델을 갱신하지만, 닫혀 있으면
        # 아무도 미러링하지 않는다 — 여기서 확정한다.
        comp.body = body
        self._vm.notify(scope="content")
        return {"component": comp.name, "old_length": len(old), "new_length": len(body)}

    def get_body_outline(self, name: str) -> dict[str, Any]:
        """본문의 헤딩 아웃라인 — 전문을 받지 않고 구조만 본다 (WP-BO).

        긴 본문에서 어느 섹션을 읽거나 고칠지 여기서 고른 뒤
        `get_body_section`/`set_body_section`에 heading을 넘긴다.
        코드 펜스 안의 `#` 줄은 헤딩으로 치지 않는다.
        """
        from daedalus.model import outline

        comp = self._find_component(name)
        body = self._body_text(comp)
        entries = outline.parse_outline(body)
        return {
            "component": comp.name,
            "body_length": len(body),
            "outline": [
                {
                    "heading": f"{'#' * e.level} {e.title}",
                    "path": e.path,
                    "line_start": e.line_start + 1,  # 1-based (에디터 표기)
                    "line_end": e.line_end,
                    "length": len(outline.section_text(body, e)),
                }
                for e in entries
            ],
        }

    def get_body_section(self, name: str, heading: str) -> dict[str, Any]:
        """본문에서 섹션 하나만 읽는다 — 헤딩 줄 포함, 하위 헤딩 포함 (WP-BO).

        heading은 제목("배선 규칙"), 레벨 지정("## 배선 규칙"), 또는
        경로("설계 > 배선 규칙")다. 동명 헤딩이 여럿이면 경로로 특정하라는
        에러가 난다 — 조용히 하나를 고르지 않는다.
        """
        from daedalus.model import outline

        comp = self._find_component(name)
        body = self._body_text(comp)
        entry = outline.find_section(body, heading)
        return {
            "component": comp.name,
            "heading": f"{'#' * entry.level} {entry.title}",
            "path": entry.path,
            "line_start": entry.line_start + 1,
            "line_end": entry.line_end,
            "text": outline.section_text(body, entry),
        }

    def set_body_section(self, name: str, heading: str, text: str) -> dict[str, Any]:
        """본문에서 섹션 하나(헤딩 줄 포함)만 교체한다 (WP-BO).

        전문 재전송 없이 그 범위만 바꾼다 — `set_component_body`와 같은 문서
        경로(WP-BU)라 undo 가능하고, 건드리지 않은 구간은 바이트 그대로다.
        text에는 교체 후에도 섹션으로 남도록 자기 헤딩 줄을 포함하라(헤딩을
        빼면 이전 섹션에 흡수된다 — 의도적 병합용).
        """
        from PySide6.QtGui import QTextCursor

        from daedalus.model import outline
        from daedalus.view.editors import body_documents

        comp = self._find_component(name)
        doc = body_documents.registry().document_for(comp)
        body = doc.toPlainText()  # 편집 중에는 문서가 진실이다(WP-BU)
        entry = outline.find_section(body, heading)
        start, end = outline.char_span(body, entry)
        repl = outline.replacement_text(body, entry, text)

        cursor = QTextCursor(doc)
        cursor.beginEditBlock()  # 1 undo 단위
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(repl)
        cursor.endEditBlock()

        comp.body = doc.toPlainText()
        self._vm.notify(scope="content")
        return {
            "component": comp.name,
            "heading": f"{'#' * entry.level} {entry.title}",
            "old_length": end - start,
            "new_length": len(repl),
            "body_length": len(comp.body),
        }

    @staticmethod
    def _body_text(comp: Any) -> str:
        """읽기용 본문 — 열린 문서가 있으면 그쪽이 진실이다(WP-BU).

        문서를 새로 만들지는 않는다 — 읽기가 편집 자원을 만들면 안 된다.
        """
        from daedalus.view.editors import body_documents

        doc = body_documents.registry().peek(comp)
        if doc is not None:
            return doc.toPlainText()
        return str(getattr(comp, "body", "") or "")
