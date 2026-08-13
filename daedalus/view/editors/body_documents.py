"""컴포넌트 본문(body) 문서 레지스트리 — 본문마다 독립 undo 스택 (WP-BU).

``QPlainTextEdit.setPlainText``는 내용을 갈아끼우면서 그 문서의 undo 이력을
지운다. ``SectionContentPanel.show_body``가 컴포넌트를 전환할 때마다 이걸
호출했기 때문에, 다른 컴포넌트를 잠깐 열었다 돌아오면 본문 되돌리기 이력이
통째로 사라져 있었다. 컴포넌트 id별로 ``QTextDocument``를 보관하고 에디터에
``attach_document``로 갈아끼우면 각 문서가 자기 undo 스택을 그대로 들고 있어
탭을 옮겨다녀도 이력이 유지된다.

**캔버스 CommandStack과는 의도적으로 분리된 스택이다.** 본문 타이핑이 노드
이동·전이 생성과 한 스택에 섞이면 Ctrl+Z가 무엇을 되돌릴지 예측할 수 없다 —
포커스가 에디터에 있으면 그 문서의 undo가, 캔버스에 있으면 CommandStack의
undo가 동작하는 것이 사용자가 기대하는 동작이다.

문서와 모델(``component.body``)의 관계: **문서가 편집 중 진실**이고 모델은
``textChanged``로 계속 미러링된다(undo/redo도 textChanged를 발생시키므로 모델이
따라간다). 모델을 외부에서 직접 바꾼 경우에만 ``sync_from_model``로 문서를
맞춰야 하며, 이때는 그 문서의 undo 이력이 초기화된다.
"""
from __future__ import annotations

from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QPlainTextDocumentLayout


def _key(component: object) -> str:
    """컴포넌트의 안정 id를 문서 키로 쓴다.

    id가 없는 객체(테스트 더미 등)는 파이썬 identity로 폴백한다 — 세션 안에서만
    유효하지만, 레지스트리 자체가 세션 수명 캐시라 문제되지 않는다.
    """
    comp_id = getattr(component, "id", None)
    if isinstance(comp_id, str) and comp_id:
        return comp_id
    return f"obj:{id(component):x}"


class BodyDocumentRegistry:
    """컴포넌트 id → QTextDocument 캐시.

    문서는 부모 없이 생성해 이 레지스트리의 dict가 소유한다
    (``QPlainTextEdit.setDocument``는 소유권을 가져가지 않는다).
    """

    def __init__(self) -> None:
        self._documents: dict[str, QTextDocument] = {}

    def document_for(self, component: object) -> QTextDocument:
        """컴포넌트의 본문 문서를 반환. 없으면 body로 초기화해 만든다.

        이미 있으면 **모델과 비교하지 않고 그대로 돌려준다** — 편집 중 문서가
        진실이고, 모델을 다시 밀어넣으면 undo 이력이 날아가기 때문이다.
        """
        key = _key(component)
        doc = self._documents.get(key)
        if doc is not None:
            return doc
        doc = QTextDocument()
        # QPlainTextEdit는 문서가 QPlainTextDocumentLayout을 쓸 것을 요구한다 —
        # 맨 QTextDocument를 그대로 넘기면 setDocument가 거부하고 편집기가 빈
        # 문서를 들게 된다("Document set does not support QPlainTextDocumentLayout").
        doc.setDocumentLayout(QPlainTextDocumentLayout(doc))
        doc.setPlainText(str(getattr(component, "body", "") or ""))
        # 초기 내용 주입이 undo 한 단계로 남으면 Ctrl+Z 한 번에 본문이 통째로
        # 비워진다 — 문서 생성 시점을 되돌릴 수 없는 바닥으로 만든다.
        doc.clearUndoRedoStacks()
        doc.setModified(False)
        self._documents[key] = doc
        return doc

    def sync_from_model(self, component: object) -> None:
        """모델 body를 문서에 강제 반영한다 (외부 변경 경로 전용).

        undo 이력이 초기화되므로, 사용자 타이핑을 모델에 반영하는 평상시
        경로(textChanged → _save_body)에서는 **호출하면 안 된다**.
        """
        key = _key(component)
        doc = self._documents.get(key)
        if doc is None:
            return
        body = str(getattr(component, "body", "") or "")
        if doc.toPlainText() == body:
            return
        doc.setPlainText(body)
        doc.clearUndoRedoStacks()

    def discard(self, component: object) -> None:
        """컴포넌트 삭제 시 그 문서를 버린다."""
        self._documents.pop(_key(component), None)

    def clear(self) -> None:
        """프로젝트 전환 — 모든 문서를 버린다."""
        self._documents.clear()

    def __len__(self) -> int:
        return len(self._documents)


# 모듈 전역 레지스트리 — 편집 세션 전체가 하나를 공유한다. 컴포넌트 하나는
# 탭 하나에서만 열리므로(app._open_tabs) 문서를 두 에디터가 동시에 쓰는 일은
# 없다.
_REGISTRY = BodyDocumentRegistry()


def registry() -> BodyDocumentRegistry:
    return _REGISTRY
