# daedalus/view/canvas/context_menus.py
"""캔버스 컨텍스트 메뉴 구성 — 노드·에이전트·참조 항목 (A8/A9).

`FsmScene`에서 떼어 냈다(코드 위생 상한 — 메뉴 항목이 늘면서 씬이 1,200줄을
넘었다). 씬에는 같은 이름의 **한 줄 위임 메서드**만 남는다: 테스트와 다른
호출부가 `scene._add_component_actions_menu(...)`처럼 씬의 메서드를 직접
부르기 때문이다(WP-RF-3e가 MainWindow 협력 객체에서 쓴 관례와 같다).

여기 함수는 **메뉴를 조립하고 {QAction: 콜러블} 디스패치 표를 돌려줄 뿐**이고,
실제 편집 로직은 전부 `view/actions/`에 있다 — 이 모듈도 호출부다.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QMenu

#: 링크 하이라이트 지속 시간(ms). 선택 상태를 그대로 쓰므로 되돌릴 필요가 없다.
HIGHLIGHT_MS = 2000


# --- 진입점 프리셋 (A8) — 실체는 view/actions/entrypoint.py ---

def add_entry_preset_menu(scene, menu: QMenu, state_vm: StateViewModel) -> dict:
    """"진입점 설정" 서브메뉴를 붙이고 {QAction: EntryPreset}을 돌려준다.

    프리셋을 지원하지 않는 노드(에이전트·빈 상태·FIXED 종류 스킬)에는
    **메뉴를 만들지 않는다** — 눌러도 아무 일도 일어나지 않는 항목은
    없느니만 못하다.
    """
    from daedalus.view.actions.entrypoint import (
        ENTRY_PRESETS,
        current_entry_preset,
        supports_entry_presets,
    )

    component = getattr(state_vm.model, "skill_ref", None)
    if component is None or not supports_entry_presets(component):
        return {}

    submenu = menu.addMenu("진입점 설정")
    if submenu is None:
        return {}
    submenu.setToolTipsVisible(True)
    current = current_entry_preset(component)
    mapping: dict = {}
    for spec in ENTRY_PRESETS:
        act = submenu.addAction(spec.label)
        if act is None:
            continue
        act.setToolTip(spec.description)
        act.setCheckable(True)
        act.setChecked(spec.preset is current)
        mapping[act] = spec.preset
    menu.addSeparator()
    return mapping

def apply_entry_preset_to_node(scene, state_vm: StateViewModel, preset) -> None:
    from daedalus.view.actions.entrypoint import apply_entry_preset

    component = getattr(state_vm.model, "skill_ref", None)
    if component is not None:
        apply_entry_preset(scene._project_vm, component, preset)

# --- 컴포넌트 공통 액션 (A9-1/2/3) — 실체는 view/actions/ ---

def add_trigger_menu(menu: QMenu, transition_vm) -> dict:
    """"트리거 지정" 서브메뉴 — {QAction: 트리거 이름} (A9-8).

    후보는 출발 노드가 선언한 출력 이벤트뿐이다. 자유 입력을 주지 않는 이유는
    포트에 없는 이름을 넣으면 캔버스에서 어느 갈래인지 그릴 수 없고
    `trigger_unknown_event` 경고만 남기 때문이다 — 갈래를 새로 만들려면
    출발 스킬의 transfer_on을 먼저 늘려야 한다.
    """
    from daedalus.view.actions.transitions import current_trigger, trigger_choices

    submenu = menu.addMenu("트리거 지정")
    if submenu is None:
        return {}
    current = current_trigger(transition_vm)
    mapping: dict = {}

    none_act = submenu.addAction("(없음)")
    if none_act is not None:
        none_act.setCheckable(True)
        none_act.setChecked(not current)
        mapping[none_act] = ""

    choices = trigger_choices(transition_vm)
    if choices:
        submenu.addSeparator()
    for name in choices:
        act = submenu.addAction(name)
        if act is None:
            continue
        act.setCheckable(True)
        act.setChecked(name == current)
        mapping[act] = name

    # 포트에 없는 이름이 이미 붙어 있으면(포트 개명 잔재) 그것도 보여 준다 —
    # 안 보이면 무엇이 걸려 있는지 모른 채 고르게 된다.
    if current and current not in choices:
        act = submenu.addAction(f"{current} (포트에 없음)")
        if act is not None:
            act.setCheckable(True)
            act.setChecked(True)
            act.setEnabled(False)
    return mapping


def main_window(scene):
    """이 씬이 놓인 최상위 창. 없으면 None.

    씬은 MainWindow를 참조하지 않는다(캔버스가 창을 알 이유가 없다) —
    다이얼로그 부모나 프로젝트 수준 액션이 필요할 때만 뷰를 통해 거슬러
    올라간다. 뷰가 아직 붙지 않은 헤드리스 생성 경로에서는 None이다.
    """
    views = scene.views()
    return views[0].window() if views else None

def add_component_actions_menu(scene, menu: QMenu, state_vm: StateViewModel) -> dict:
    """스킬/에이전트 placement 공통 항목 — 미리보기·모델/effort·관련 경고.

    {QAction: 무인자 콜러블} 디스패치 표를 돌려준다. placement가 아닌
    노드(빈 상태)에는 아무것도 붙이지 않는다.
    """
    from daedalus.view.actions import model_effort as me

    component = getattr(state_vm.model, "skill_ref", None)
    if component is None:
        return {}

    dispatch: dict = {}

    preview_act = menu.addAction("컴파일 미리보기…")
    if preview_act is not None:
        preview_act.setToolTip("이 컴포넌트가 어떤 파일로 나가는지 — 파일은 쓰지 않는다")
        dispatch[preview_act] = lambda c=component: show_preview(scene, c)

    if me.supports_model_effort(component):
        model_menu = menu.addMenu("모델 지정")
        if model_menu is not None:
            current = me.current_model(component)
            for model, label in me.MODEL_CHOICES:
                act = model_menu.addAction(label)
                if act is None:
                    continue
                act.setCheckable(True)
                act.setChecked(current is model)
                dispatch[act] = (
                    lambda c=component, m=model: me.set_model(scene._project_vm, c, m)
                )
        effort_menu = menu.addMenu("effort 지정")
        if effort_menu is not None:
            current_effort = me.current_effort(component)
            for effort, label in me.EFFORT_CHOICES:
                act = effort_menu.addAction(label)
                if act is None:
                    continue
                act.setCheckable(True)
                act.setChecked(current_effort is effort)
                dispatch[act] = (
                    lambda c=component, e=effort: me.set_effort(scene._project_vm, c, e)
                )

    warn_act = menu.addAction("관련 경고 보기")
    if warn_act is not None:
        dispatch[warn_act] = lambda c=component: show_component_findings(scene, c)

    dispatch.update(add_agent_actions_menu(scene, menu, component))

    menu.addSeparator()
    return dispatch

# --- 에이전트 전용 (A9-4/5) ---

def add_agent_actions_menu(scene, menu: QMenu, component: object) -> dict:
    """에이전트 placement에만 붙는 항목 — 호출자 목록 / 출력 포트 편집."""
    from daedalus.model.plugin.agent import AgentDefinition
    from daedalus.view.actions.agent_links import callers_of

    if not isinstance(component, AgentDefinition):
        return {}

    dispatch: dict = {}
    callers = callers_of(component, scene._project)
    callers_menu = menu.addMenu("호출자 목록")
    if callers_menu is not None:
        callers_menu.setToolTipsVisible(True)
        if not callers:
            act = callers_menu.addAction("(없음)")
            if act is not None:
                act.setEnabled(False)
        for ref in callers:
            act = callers_menu.addAction(ref.label)
            if act is None:
                continue
            if ref.description:
                act.setToolTip(ref.description)
            dispatch[act] = lambda r=ref: focus_state(scene, r.source_state)

    ports_act = menu.addAction("출력 포트 편집…")
    if ports_act is not None:
        dispatch[ports_act] = lambda c=component: open_ports(scene, c)
    return dispatch

# --- 참조 노드 전용 (A9-6/7) ---


def add_reference_actions_menu(scene, menu: QMenu, ref_vm) -> dict:
    """참조 노드 항목 — 링크된 노드 하이라이트 / 링크 추가."""
    from daedalus.view.actions.references import linkable_state_vms, linked_state_vms

    dispatch: dict = {}
    linked = linked_state_vms(scene._project_vm, ref_vm)
    highlight_act = menu.addAction(f"링크된 노드 하이라이트 ({len(linked)})")
    if highlight_act is not None:
        highlight_act.setEnabled(bool(linked))
        dispatch[highlight_act] = lambda r=ref_vm: highlight_reference_links(scene, r)

    candidates = linkable_state_vms(scene._project_vm, ref_vm)
    add_menu = menu.addMenu("링크 추가")
    if add_menu is not None:
        if not candidates:
            act = add_menu.addAction("(연결할 노드 없음)")
            if act is not None:
                act.setEnabled(False)
        for state_vm in candidates:
            act = add_menu.addAction(state_vm.model.name)
            if act is None:
                continue
            dispatch[act] = (
                lambda r=ref_vm, s=state_vm: add_reference_link_on(scene, r, s)
            )
    menu.addSeparator()
    return dispatch

def highlight_reference_links(scene, ref_vm) -> list:
    """링크된 노드를 잠깐 선택 상태로 만든다 (A9-6). 대상 목록을 돌려준다.

    임시 이펙트 아이템을 얹지 않고 **선택 상태**를 쓴다 — 캔버스가 이미
    선택을 굵은 테두리로 그리므로 새 렌더 경로를 만들 이유가 없고, 사용자가
    아무 데나 클릭하면 자연히 풀린다. 모델을 건드리지 않으므로 undo 대상도
    아니다(선택은 편집이 아니다).
    """
    from PySide6.QtCore import QTimer

    from daedalus.view.actions.references import linked_state_vms

    targets = linked_state_vms(scene._project_vm, ref_vm)
    scene.clearSelection()
    for state_vm in targets:
        node = scene._node_items.get(state_vm)
        if node is not None:
            node.setSelected(True)
    if targets:
        QTimer.singleShot(HIGHLIGHT_MS, lambda: clear_highlight(scene))
    return targets

def clear_highlight(scene) -> None:
    """하이라이트 해제 — 씬이 이미 파괴됐으면 조용히 넘어간다.

    2초 뒤에 도는 타이머라 그 사이 프로젝트가 바뀌거나 창이 닫힐 수 있다.
    """
    try:
        scene.clearSelection()
    except RuntimeError:
        pass

def add_reference_link_on(scene, ref_vm, state_vm) -> None:
    from daedalus.view.actions.references import add_reference_link

    add_reference_link(scene, ref_vm, state_vm)

def focus_state(scene, state: object) -> None:
    """그 상태의 노드를 캔버스에서 선택·센터링한다 (검증 결과 점프와 같은 경로)."""
    window = main_window(scene)
    if hasattr(window, "_focus_in_project_canvas"):
        window._focus_in_project_canvas(state)

def open_ports(scene, component: object) -> None:
    window = main_window(scene)
    if hasattr(window, "open_component_ports"):
        window.open_component_ports(component)

def show_preview(scene, component: object) -> None:
    from daedalus.view.actions.preview import show_preview_dialog

    window = main_window(scene)
    resolved = window.resolved_hooks() if hasattr(window, "resolved_hooks") else None
    show_preview_dialog(
        window, component, project=scene._project, resolved_hooks=resolved,
    )

def show_component_findings(scene, component: object) -> None:
    window = main_window(scene)
    if hasattr(window, "show_component_findings"):
        window.show_component_findings(component)
