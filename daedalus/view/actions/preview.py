# daedalus/view/actions/preview.py
"""컴파일 미리보기 — 산출 텍스트 + 읽기 전용 다이얼로그 (A9-1).

본문을 고치고 "그래서 SKILL.md가 어떻게 나오는데?"를 확인하려면 지금까지
컴파일을 돌려 파일을 열어야 했다. 그 왕복을 없앤다 — 파일은 쓰지 않는다.

텍스트 생성(`preview_text`)과 표시(`show_preview_dialog`)를 나눈 이유는
**텍스트가 테스트 대상이고 다이얼로그는 아니기 때문**이다. 캔버스 우클릭과
에디터 버튼은 둘 다 `show_preview_dialog`를 부른다.

산출 텍스트와 경로의 실체는 `compiler/preview.py` 하나다(WP-6) — MCP
`compile_preview`도 같은 함수를 부른다(원칙 1·2). 여기 남은 것은 Qt 다이얼로그와
뷰가 쓰는 이름 두 개뿐이다.
"""
from __future__ import annotations


def preview_text(component: object, project=None, resolved_hooks: dict | None = None) -> str:
    """이 컴포넌트가 컴파일되면 나올 텍스트. 파일은 쓰지 않는다.

    `project`를 주면 그래프에서 유도하는 단락(다음 단계·진입 맥락·호출 계약·
    블랙보드)까지 포함된 **실제와 같은** 산출이 된다 — 주지 않으면 컴포넌트
    자체만으로 만들 수 있는 부분만 나온다.
    """
    from daedalus.compiler.preview import preview_component

    return preview_component(
        component, project=project, resolved_hooks=resolved_hooks,
    ).text


def preview_title(component: object) -> str:
    """다이얼로그 제목 — 어떤 파일로 나가는지가 곧 제목이다.

    경로는 컴포넌트 종류가 답한다(`OUTPUT_LOCATION`) — 종전의
    `isinstance(component, Agent)` 갈래가 사라졌다. 빌드 타깃 접두를 붙이지 않는
    것이 의도다(제목은 "무엇이 되는가"이지 "이번 빌드에서 어디에 놓이는가"가
    아니다).
    """
    from daedalus.compiler.preview import preview_path

    return f"컴파일 미리보기 — {preview_path(component)}"


def show_preview_dialog(parent, component: object, project=None, resolved_hooks=None) -> None:
    """미리보기 다이얼로그를 띄운다(모달). 캔버스 메뉴와 에디터 버튼의 공용 진입점."""
    from PySide6.QtWidgets import (
        QDialog,
        QDialogButtonBox,
        QTextEdit,
        QVBoxLayout,
    )

    text = preview_text(component, project=project, resolved_hooks=resolved_hooks)

    dlg = QDialog(parent)
    dlg.setWindowTitle(preview_title(component))
    dlg.setMinimumSize(760, 620)
    lay = QVBoxLayout(dlg)

    view = QTextEdit()
    view.setReadOnly(True)
    # 산출은 마크다운 원문이다 — 렌더하면 프론트매터와 들여쓰기가 사라져
    # "실제로 나가는 텍스트"를 확인한다는 목적이 깨진다.
    view.setPlainText(text)
    view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
    view.setStyleSheet(
        "QTextEdit { font-family: Consolas, monospace; font-size: 12px; "
        "background: #1e1e2e; color: #cdd6f4; border: 1px solid #45475a; }"
    )
    lay.addWidget(view, 1)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(dlg.reject)
    buttons.accepted.connect(dlg.accept)
    lay.addWidget(buttons)

    dlg.exec()
