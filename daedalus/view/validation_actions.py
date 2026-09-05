# daedalus/view/validation_actions.py
"""검증 실행 + 검증 결과 → 캔버스 노드 포커스 (WP-RF-3e).

`MainWindow`의 협력 객체다(Mixin 아님). 검증 dock 표시는 컴파일 경로
(`CompileActions`)와도 공유하므로, 이 객체가 그 단일 진실이다.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QDockWidget

from daedalus.model.validation import ValidationError, Validator

if TYPE_CHECKING:  # pragma: no cover - 타입 전용
    from daedalus.view.app import MainWindow


class ValidationActions:
    """F7 검증과 결과 항목 내비게이션을 담당하는 MainWindow 협력 객체."""

    def __init__(self, window: MainWindow) -> None:
        self._w = window

    # --- 검증 ---

    def run_validation(self) -> None:
        """F7 — 프로젝트 전체 검증 실행 후 ValidationPanel 갱신."""
        w = self._w
        if w._project is None:
            w._status_label.setText("검증: 프로젝트가 없습니다.")
            return

        # 전역 훅(A1)까지 아는 이름 집합을 주입한다 — 검증기는 파일시스템을
        # 읽지 않으므로, 넘기지 않으면 전역 훅 참조가 전부 dangling으로 보인다.
        errors = Validator.validate_project(
            w._project, known_hook_names=frozenset(w.resolved_hooks()),
        )
        w._validation_panel.set_errors(errors)

        # 검증 패널이 숨겨져 있으면 표시
        self.show_validation_dock()

        error_count = sum(1 for e in errors if not e.is_warning)
        warning_count = sum(1 for e in errors if e.is_warning)
        if not errors:
            w._status_label.setText("검증: 문제 없음")
        else:
            w._status_label.setText(
                f"검증: 오류 {error_count} / 경고 {warning_count}"
            )

    def show_component_findings(self, component: object) -> int:
        """이 컴포넌트에 관한 검증 결과만 패널에 채우고 dock을 연다 (A9-3).

        캔버스 노드 우클릭 "관련 경고 보기"와 에디터의 같은 항목이 공유한다.
        결과 건수를 돌려준다 — 0건이면 상태바로 그 사실을 말한다(빈 패널만
        띄우면 "필터가 안 먹은 것"과 구분되지 않는다).
        """
        from daedalus.view.actions.warnings import findings_for

        w = self._w
        if w._project is None:
            return 0
        errors = Validator.validate_project(
            w._project, known_hook_names=frozenset(w.resolved_hooks()),
        )
        found = findings_for(errors, component, w._project)
        name = getattr(component, "name", "?")
        w._validation_panel.set_errors(found)
        self.show_validation_dock()
        if found:
            w._status_label.setText(f"'{name}' 관련 검증 결과 {len(found)}건")
        else:
            w._status_label.setText(f"'{name}'에 관한 검증 결과가 없습니다.")
        return len(found)

    def show_validation_dock(self) -> None:
        """검증 dock을 표시하고 앞으로 올린다 (F7/컴파일 공용)."""
        validation_dock = self.find_validation_dock()
        if validation_dock is not None:
            validation_dock.show()
            validation_dock.raise_()

    def find_validation_dock(self) -> QDockWidget | None:
        """'검증' 도킹 위젯을 반환한다."""
        w = self._w
        for dock in w.findChildren(QDockWidget):
            if dock.widget() is w._validation_panel:
                return dock
        return None

    # --- 결과 항목 → 노드 포커스 ---

    def on_validation_item_activated(self, error: ValidationError) -> None:
        """ValidationPanel 더블클릭 → 해당 노드 포커스."""
        if self._w._project is None:
            return

        subject = error.subject
        if subject is None:
            return

        # path의 첫 요소로 에이전트 컨텍스트 판별
        path = error.path
        agent_name: str | None = None
        if path:
            first = path[0]
            if first.startswith("agent:"):
                agent_name = first[len("agent:"):]

        if agent_name is not None:
            # 에이전트 탭 내부 노드
            self.focus_in_agent_tab(agent_name, subject)
        else:
            # 프로젝트 캔버스(탭 0)
            self.focus_in_project_canvas(subject)

    def focus_in_project_canvas(self, subject: object) -> None:
        """프로젝트 FSM 캔버스(탭 0)에서 subject와 identity 일치하는 노드를 선택+센터링.

        subject가 캔버스에 없으면(삭제된 노드 등) 상태바에 안내를 표시하고 no-op.
        """
        # app 모듈은 이 모듈을 임포트하므로 탭 인덱스 상수는 지역 임포트로 가져온다
        # (모듈 최상단이면 순환 임포트).
        from daedalus.view.app import _FSM_TAB_INDEX

        w = self._w
        # 프로젝트 자체가 subject인 검증 항목(예: 프로젝트 이름 규약)은 캔버스
        # 노드가 아니다 — 조치 위치를 안내하고 끝낸다.
        if subject is w._project:
            w._status_label.setText(
                "프로젝트 이름/속성은 파일 → 프로젝트 속성…에서 수정하세요."
            )
            return
        w._tabs.setCurrentIndex(_FSM_TAB_INDEX)
        if w._fsm_scene is None:
            return
        for svm, node_item in w._fsm_scene._node_items.items():
            if svm.model is subject:
                w._fsm_scene.clearSelection()
                node_item.setSelected(True)
                view = w._tabs.widget(_FSM_TAB_INDEX)
                if hasattr(view, "centerOn"):
                    view.centerOn(node_item)  # type: ignore[union-attr]
                elif hasattr(view, "ensureVisible"):
                    view.ensureVisible(node_item)  # type: ignore[union-attr]
                return
        # subject가 캔버스에 없음 — 삭제된 노드일 수 있음
        name = getattr(subject, "name", None)
        if name:
            w._status_label.setText(
                f"'{name}' 노드가 캔버스에 없습니다 (이미 삭제되었을 수 있습니다)."
            )

    def focus_in_agent_tab(self, agent_name: str, subject: object) -> None:
        """에이전트 탭이 열려 있으면 그 탭으로 전환, 없으면 상태바 안내.

        WP-AF로 에이전트 내부 FSM이 퇴역해 AgentEditor에는 캔버스가 없다 —
        노드 단위 포커스는 프로젝트 캔버스(focus_in_project_canvas) 몫이고
        여기서는 탭 전환까지만 한다.
        """
        from daedalus.view.editors.agent_editor import AgentEditor

        w = self._w
        for i in range(w._tabs.count()):
            widget = w._tabs.widget(i)
            if isinstance(widget, AgentEditor):
                ag = getattr(widget, "_agent", None)
                if ag is not None and ag.name == agent_name:
                    w._tabs.setCurrentIndex(i)
                    return
        # 탭이 열려 있지 않음
        w._status_label.setText(
            f"에이전트 '{agent_name}' 탭을 열어 확인하세요."
        )
