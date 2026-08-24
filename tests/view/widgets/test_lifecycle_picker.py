"""훅 라이프사이클 피커 (A10).

**핵심은 드리프트 방지 테스트다**: `_LAYOUT`의 키 집합이 `HookEvent` 전체와
정확히 일치해야 한다 — 이벤트가 늘거나 줄면 여기가 깨져 다이어그램 갱신을
강제한다. 그 장치가 없으면 새 이벤트가 다이어그램에서 조용히 빠진다.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, QRectF

from daedalus.model.plugin.hook import (
    NO_MATCHER_EVENTS,
    UNDOCUMENTED_EVENTS,
    HookEvent,
)
from daedalus.view.widgets.lifecycle_picker import (
    CANVAS_H,
    CANVAS_W,
    _LAYOUT,
    HookLifecycleDialog,
    HookLifecycleScene,
    event_tooltip,
)


# --- 드리프트 방지 ---


def test_layout_covers_every_event_exactly():
    """이벤트가 늘거나 줄면 이 테스트가 깨져 다이어그램 갱신을 강제한다."""
    assert set(_LAYOUT) == set(HookEvent)
    assert len(_LAYOUT) == len(HookEvent)


def test_layout_keys_are_enum_members_not_strings():
    """값 문자열을 키로 쓰면 enum 개명이 조용히 빠져나간다."""
    assert all(isinstance(key, HookEvent) for key in _LAYOUT)


def test_every_box_is_inside_the_canvas():
    canvas = QRectF(0, 0, CANVAS_W, CANVAS_H)
    for event, box in _LAYOUT.items():
        assert canvas.contains(box.rect), f"{event.value} 박스가 캔버스 밖이다"


def test_boxes_do_not_overlap():
    """겹치면 클릭이 어느 쪽으로 갈지 알 수 없다."""
    boxes = list(_LAYOUT.items())
    for i, (ev_a, a) in enumerate(boxes):
        for ev_b, b in boxes[i + 1:]:
            overlap = a.rect.intersected(b.rect)
            assert overlap.isEmpty(), f"{ev_a.value}와 {ev_b.value} 박스가 겹친다"


def test_labels_are_the_event_values():
    """라벨이 이벤트 값과 다르면 무엇을 고르는지 알 수 없다.

    (원본 다이어그램의 표시 문구가 아니라 실제 이벤트 이름을 쓴다 —
    `Session Start` 같은 띄어쓰기는 설정 파일에서 통하지 않는다.)
    """
    for event, box in _LAYOUT.items():
        assert box.label == event.value


# --- 툴팁 ---


@pytest.mark.parametrize("event", sorted(NO_MATCHER_EVENTS, key=lambda e: e.value))
def test_no_matcher_events_say_so(event):
    assert "matcher 없음" in event_tooltip(event)


def test_matcher_events_say_supported():
    assert "matcher 지원" in event_tooltip(HookEvent.PRE_TOOL_USE)


@pytest.mark.parametrize("event", sorted(UNDOCUMENTED_EVENTS, key=lambda e: e.value))
def test_undocumented_events_say_so(event):
    assert "공식 문서에 없음" in event_tooltip(event)


def test_tooltip_starts_with_the_event_value():
    assert event_tooltip(HookEvent.SESSION_END).startswith("SessionEnd")


# --- 씬 ---


def test_scene_creates_an_item_per_event(qapp):
    scene = HookLifecycleScene()
    for event in HookEvent:
        assert scene.item_for(event) is not None


def test_scene_marks_the_current_event(qapp):
    scene = HookLifecycleScene(HookEvent.POST_COMPACT)
    assert scene.item_for(HookEvent.POST_COMPACT)._current is True
    assert scene.item_for(HookEvent.PRE_COMPACT)._current is False


def test_scene_without_current_marks_nothing(qapp):
    scene = HookLifecycleScene()
    assert not any(scene.item_for(e)._current for e in HookEvent)


def test_items_carry_the_tooltip(qapp):
    scene = HookLifecycleScene()
    item = scene.item_for(HookEvent.TASK_COMPLETED)
    assert "matcher 없음" in item.toolTip()


def test_clicking_an_item_emits_picked(qapp):
    scene = HookLifecycleScene()
    received: list = []
    scene.picked.connect(received.append)

    scene.item_for(HookEvent.SUBAGENT_STOP).mousePressEvent(_FakeMouseEvent())
    assert received == [HookEvent.SUBAGENT_STOP]


def test_item_positions_match_the_layout(qapp):
    scene = HookLifecycleScene()
    for event, box in _LAYOUT.items():
        assert scene.item_for(event).pos() == QPointF(box.x, box.y)


def test_hover_toggles_highlight(qapp):
    scene = HookLifecycleScene()
    item = scene.item_for(HookEvent.PRE_TOOL_USE)
    assert item._hover is False
    item.hoverEnterEvent(_FakeMouseEvent())
    assert item._hover is True
    item.hoverLeaveEvent(_FakeMouseEvent())
    assert item._hover is False


class _FakeMouseEvent:
    def accept(self) -> None:
        pass


# --- 다이얼로그 ---


def test_dialog_selects_and_accepts(qapp):
    dialog = HookLifecycleDialog(HookEvent.STOP)
    received: list = []
    dialog.event_selected.connect(received.append)

    dialog._scene.pick(HookEvent.SESSION_END)
    assert received == [HookEvent.SESSION_END]
    assert dialog.selected is HookEvent.SESSION_END
    assert dialog.result() == HookLifecycleDialog.DialogCode.Accepted
    dialog.deleteLater()


def test_dialog_without_pick_has_no_selection(qapp):
    dialog = HookLifecycleDialog(HookEvent.STOP)
    assert dialog.selected is None
    dialog.deleteLater()


def test_dialog_passes_current_to_the_scene(qapp):
    dialog = HookLifecycleDialog(HookEvent.NOTIFICATION)
    assert dialog._scene.item_for(HookEvent.NOTIFICATION)._current is True
    dialog.deleteLater()


# --- 훅 패널 호출부 ---


def test_hook_panel_button_opens_the_dialog(qapp, monkeypatch):
    """패널은 다이얼로그를 열고 결과를 **콤보에 반영**할 뿐이다 —
    모델 쓰기는 기존 currentIndexChanged → _save_head 경로가 한다."""
    from daedalus.model.plugin.hook import CommandHook, HookDef
    from daedalus.model.project import PluginProject
    from daedalus.view.editors.hook_panel import HookLibraryPanel
    from daedalus.view.widgets import lifecycle_picker

    hook = HookDef(
        name="h", description="", event=HookEvent.PRE_TOOL_USE,
        handlers=[CommandHook(script="x")],
    )
    panel = HookLibraryPanel()
    panel.set_project(PluginProject(name="p", hook_library=[hook]))

    class _FakeDialog:
        def __init__(self, current, parent=None):
            self.current = current
            self.selected = HookEvent.SESSION_END

        def exec(self):
            from PySide6.QtWidgets import QDialog

            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(lifecycle_picker, "HookLifecycleDialog", _FakeDialog)
    panel._lifecycle_btn.click()

    assert panel._event.currentData() is HookEvent.SESSION_END
    assert hook.event is HookEvent.SESSION_END


def test_hook_panel_button_cancel_changes_nothing(qapp, monkeypatch):
    from daedalus.model.plugin.hook import CommandHook, HookDef
    from daedalus.model.project import PluginProject
    from daedalus.view.editors.hook_panel import HookLibraryPanel
    from daedalus.view.widgets import lifecycle_picker

    hook = HookDef(
        name="h", description="", event=HookEvent.PRE_TOOL_USE,
        handlers=[CommandHook(script="x")],
    )
    panel = HookLibraryPanel()
    panel.set_project(PluginProject(name="p", hook_library=[hook]))

    class _FakeDialog:
        def __init__(self, current, parent=None):
            self.selected = None

        def exec(self):
            from PySide6.QtWidgets import QDialog

            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(lifecycle_picker, "HookLifecycleDialog", _FakeDialog)
    panel._lifecycle_btn.click()
    assert hook.event is HookEvent.PRE_TOOL_USE
