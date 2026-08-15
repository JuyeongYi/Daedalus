"""상주 패널의 외부 변경 반영 — MCP가 넣은 훅/블랙보드 클래스가 목록에 보이는가.

훅/블랙보드 패널은 자기 편집만 알았다 — MCP `create_hook`이 라이브러리에 훅을
넣어도 목록은 빈 채였다(사용자 보고: "훅 목록에서 check daedalus 이게 안 보이는데").
"""
from __future__ import annotations

import pytest

from daedalus.model.project import PluginProject


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    win = MainWindow()
    win.set_project(PluginProject(name="p"))
    yield win
    win.close()


@pytest.fixture
def tools(window):
    from daedalus.mcp.tools import DaedalusTools

    return DaedalusTools(window)


def test_mcp_created_hook_appears_in_panel(window, tools):
    tools.create_hook("check-mcp", command="echo hi", event="SessionStart")

    labels = [
        window._hook_panel._list.item(i).text()
        for i in range(window._hook_panel._list.count())
    ]
    assert any("check-mcp" in text for text in labels)


def test_mcp_created_blackboard_class_appears_in_panel(window, tools):
    tools.create_blackboard_class(
        "Session", fields=[{"name": "goal", "type": "string"}]
    )

    panel = window._blackboard_panel
    labels = [panel._list.item(i).text() for i in range(panel._list.count())]
    assert any("Session" in text for text in labels)


def test_undo_of_mcp_hook_disappears_from_panel(window, tools):
    """되돌리면 목록에서도 사라져야 한다 — 반영이 단방향 우연이면 안 된다."""
    tools.create_hook("check-mcp", command="echo hi", event="SessionStart")
    tools.undo()

    assert window._hook_panel._list.count() == 0


def test_panel_own_edit_does_not_reset_selection(window, qapp):
    """패널 자신의 편집이 발화한 notify가 목록 재구성으로 되돌아오면
    타이핑 중인 폼의 선택이 리셋된다 — 그 경로는 건너뛴다."""
    panel = window._hook_panel
    panel._add_hook()  # 훅 추가 → 선택됨
    panel._add_hook()
    panel._list.setCurrentRow(1)

    # 이름 타이핑 시뮬레이션 — textChanged 핸들러(_save_head)가 notify를 발화한다
    panel._name.setText("renamed")

    assert panel._list.currentRow() == 1
