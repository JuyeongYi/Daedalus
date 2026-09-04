# daedalus/mcp/tools/workspace.py
"""작업 폴더 문서 도구 — `.claude/CLAUDE.md`와 `.claude/rules/` (WP-WD).

**계층: GUI 어댑터다 (WP-RF-2 명시).** core가 아니라 MainWindow·ProjectViewModel·
body_documents에 결합된 코드이고, Qt 메인 스레드 실행을 전제로 한다.

본문 편집은 `BodyTools.set_component_body`와 같은 경로를 탄다 — 컴포넌트의
QTextDocument에 적용하므로 에디터가 열려 있으면 즉시 반영되고 편집기 Ctrl+Z로
되돌릴 수 있다(WP-BU). 구조 편집(규칙 추가·삭제·이름 변경)은 GUI 패널과 같은
정책으로 모델에 직접 기록한다 — 블랙보드·훅 패널과 동일하게 커맨드화 범위 밖이다.
"""
from __future__ import annotations

from typing import Any

from ._base import _BaseTools


class WorkspaceTools(_BaseTools):
    """작업 폴더 문서 — 조회·CLAUDE.md 구역·규칙 파일."""

    # ------------------------------------------------------------------
    # 내부
    # ------------------------------------------------------------------

    def _find_rule(self, name: str) -> Any:
        for doc in self._project.rules:
            if doc.name == name:
                return doc
        available = ", ".join(d.name for d in self._project.rules) or "(없음)"
        raise ValueError(f"'{name}' 규칙이 없습니다. 가용: {available}")

    def _write_body(self, doc: Any, body: str) -> int:
        """문서 본문 교체 — 열린 에디터와 undo 스택을 존중한다."""
        from PySide6.QtGui import QTextCursor

        from daedalus.view.editors import body_documents

        old_len = len(doc.body or "")
        text_doc = body_documents.registry().document_for(doc)
        cursor = QTextCursor(text_doc)
        cursor.beginEditBlock()  # 1 undo 단위
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(body)
        cursor.endEditBlock()
        # 에디터가 닫혀 있으면 textChanged로 미러링되지 않는다 — 여기서 확정한다.
        doc.body = body
        return old_len

    def _refresh_panels(self, scope: str = "structure") -> None:
        """패널을 모델과 다시 맞춘다 — MCP 편집이 화면에 바로 보이게 한다."""
        for attr in ("_claude_md_panel", "_rules_panel"):
            panel = getattr(self._window, attr, None)
            if panel is not None:
                panel.set_project(self._project)
        self._vm.notify(scope=scope)

    # ------------------------------------------------------------------
    # 조회
    # ------------------------------------------------------------------

    def list_workspace_docs(self) -> dict[str, Any]:
        """작업 폴더 문서 목록 — CLAUDE.md 구역과 규칙 파일들.

        LOCAL 빌드에서만 배출된다. 본문은 길 수 있으므로 길이만 돌려준다 —
        내용을 보려면 `get_workspace_doc`을 쓴다.
        """
        project = self._project
        claude_md = project.claude_md
        return {
            "build_target": getattr(project.build_target, "value", None),
            "emitted": getattr(project.build_target, "name", "") == "LOCAL",
            "claude_md": (
                None if claude_md is None
                else {"title": claude_md.name, "length": len(claude_md.body or "")}
            ),
            "rules": [
                {"name": doc.name, "length": len(doc.body or "")}
                for doc in project.rules
            ],
        }

    def get_workspace_doc(self, name: str = "") -> dict[str, Any]:
        """문서 본문을 읽는다. name을 비우면 CLAUDE.md 구역, 주면 그 규칙."""
        if not name:
            doc = self._project.claude_md
            if doc is None:
                return {"kind": "claude_md", "exists": False, "body": ""}
            return {
                "kind": "claude_md", "exists": True,
                "title": doc.name, "body": doc.body,
            }
        doc = self._find_rule(name)
        return {"kind": "rule", "exists": True, "name": doc.name, "body": doc.body}

    # ------------------------------------------------------------------
    # CLAUDE.md 구역
    # ------------------------------------------------------------------

    def set_claude_md(self, body: str, title: str = "") -> dict[str, Any]:
        """`.claude/CLAUDE.md`의 이 플러그인 구역 내용을 교체한다.

        파일 전체가 아니라 **구역**이다 — 컴파일이
        `<!-- daedalus:<플러그인> open/close -->` 사이만 갈아끼우므로 그 파일의
        다른 내용(사용자가 쓴 것, 다른 ddls 플러그인의 구역)은 보존된다.

        title은 구역 안 맨 앞에 오는 H1이다(비우면 프로젝트 이름). 본문이 이미
        `# `로 시작하면 제목을 덧붙이지 않는다.
        """
        from daedalus.model.plugin.workspace_doc import WorkspaceDoc

        project = self._project
        if project.claude_md is None:
            project.claude_md = WorkspaceDoc(name=title or project.name)
        elif title:
            project.claude_md.name = title
        old_len = self._write_body(project.claude_md, body)
        self._refresh_panels("content")
        return {
            "title": project.claude_md.name,
            "old_length": old_len,
            "new_length": len(body),
        }

    # ------------------------------------------------------------------
    # 규칙 파일
    # ------------------------------------------------------------------

    def create_rule(self, name: str, body: str = "") -> dict[str, Any]:
        """`.claude/rules/<name>.md`를 새로 만든다.

        이름이 곧 파일명이라 `^[a-z0-9][a-z0-9-]*$`를 따라야 하고(컴파일 게이트가
        강제한다) 중복은 거부한다 — 같은 이름 둘은 서로 덮어쓴다.
        """
        from daedalus.model.plugin.workspace_doc import WorkspaceDoc

        project = self._project
        if any(doc.name == name for doc in project.rules):
            raise ValueError(f"'{name}' 규칙이 이미 있습니다.")
        doc = WorkspaceDoc(name=name, body=body)
        project.rules.append(doc)
        self._refresh_panels()
        return {"name": doc.name, "length": len(body)}

    def set_rule_body(self, name: str, body: str) -> dict[str, Any]:
        """규칙 파일의 본문을 교체한다."""
        doc = self._find_rule(name)
        old_len = self._write_body(doc, body)
        self._refresh_panels("content")
        return {"name": doc.name, "old_length": old_len, "new_length": len(body)}

    def rename_rule(self, name: str, new_name: str) -> dict[str, Any]:
        """규칙 파일 이름을 바꾼다 — 산출 파일명이 함께 바뀐다."""
        doc = self._find_rule(name)
        if new_name != name and any(d.name == new_name for d in self._project.rules):
            raise ValueError(f"'{new_name}' 규칙이 이미 있습니다.")
        doc.name = new_name
        self._refresh_panels()
        return {"old_name": name, "name": new_name}

    def delete_rule(self, name: str) -> dict[str, Any]:
        """규칙 파일을 삭제한다.

        **이미 컴파일된 작업 폴더의 `.claude/rules/<name>.md`는 지우지 않는다** —
        컴파일은 쓰기만 하고 남의 파일을 지우지 않기 때문이다. 산출물에서도 없애려면
        그 파일을 직접 지운다.
        """
        from daedalus.view.editors import body_documents

        doc = self._find_rule(name)
        self._project.rules.remove(doc)
        body_documents.registry().discard(doc)
        self._refresh_panels()
        return {"name": name, "note": "이미 산출된 파일은 지우지 않습니다."}
