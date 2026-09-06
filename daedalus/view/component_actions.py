# daedalus/view/component_actions.py
"""컴포넌트 생성·이름 변경·삭제 (WP-RF-3e 관례).

`MainWindow`의 협력 객체다(Mixin 아님). 담당은 레지스트리/캔버스 양쪽이
공유하는 컴포넌트 수명주기다 — 이름 입력 다이얼로그, 백킹 FSM 팩토리,
프로젝트 등록, 이름 변경, 삭제.

**컴포넌트 팩토리는 `view/actions/creation.make_component` 하나뿐이다.**
이전에는 이 모듈(레지스트리 경로)과 `creation.py`(캔버스 "여기에 만들기"
경로)가 같은 5키 dict를 문자 그대로 중복 보유했다 — 한쪽만 고치면 어디서
만들었느냐에 따라 다른 물건이 되므로, `creation.py`의 docstring이 요구하는
공유를 실제로 실현한다(FSM 생성은 그쪽이 다시 `window._make_fsm`/
`_make_agent_fsm`을 부르므로 팩토리의 단일 진실이 유지된다).

상태(`_project`/`_project_vm`/`_open_tabs` …)의 단일 진실은 계속 윈도우이고,
이 객체는 그것을 복제하지 않고 `self._w.<attr>`로 직접 읽고 쓴다.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QInputDialog, QMessageBox

if TYPE_CHECKING:  # pragma: no cover - 타입 전용
    from daedalus.view.app import MainWindow


class ComponentActions:
    """컴포넌트 생성/이름 변경/삭제를 담당하는 MainWindow 협력 객체."""

    #: 종류 → 이름 입력 다이얼로그 제목 (알 수 없는 종류 방어에도 쓰인다).
    _COMPONENT_TITLES = {
        "procedural": "새 Procedural Skill",
        "declarative": "새 Declarative Skill",
        "transfer": "새 Transfer Skill",
        "reference": "새 Reference Skill",
        "wrapped": "새 Wrapped Skill",
        "agent": "새 Agent",
    }

    def __init__(self, window: MainWindow) -> None:
        self._w = window

    # --- 생성 ---

    def ask_unique_name(self, dialog_title: str) -> str | None:
        """이름 입력 다이얼로그 + 중복 검증. 취소 시 None."""
        w = self._w
        if w._project is None:
            return None
        existing = (
            {s.name for s in w._project.skills}
            | {a.name for a in w._project.agents}
        )
        while True:
            name, ok = QInputDialog.getText(w, dialog_title, "이름:")
            if not ok or not name.strip():
                return None
            name = name.strip()
            if name in existing:
                QMessageBox.warning(w, "이름 중복", f"'{name}' 이름이 이미 존재합니다.")
                continue
            return name

    def make_fsm(self, name: str) -> object:
        from daedalus.model.fsm.machine import StateMachine
        from daedalus.model.fsm.state import SimpleState as _SS
        s = _SS(name="start")
        return StateMachine(name=f"{name}_fsm", states=[s], initial_state=s)

    def make_agent_fsm(self, name: str) -> object:
        """에이전트 백킹 FSM — WP-AF 이후 형식상의 최소 기계.

        내부 FSM은 퇴역했다(절차는 본문, 결과 분기는 transfer_on). fsm 필드는
        WorkflowComponent 계약상 남아 있으므로 EntryPoint 하나짜리 빈 기계를
        준다 — 서술할 것이 없어 컴파일 산출에도 나타나지 않는다.
        """
        from daedalus.model.fsm.machine import StateMachine
        from daedalus.model.fsm.pseudo import EntryPoint
        entry = EntryPoint(name="entry")
        return StateMachine(
            name=f"{name}_fsm",
            states=[entry],
            initial_state=entry,
        )

    def register_component(self, component: object) -> None:
        """컴포넌트를 프로젝트에 등록한다 (WP-CE — 커맨드 경유라 Ctrl+Z로 되돌아간다).

        리스트 추가와 블랙보드 스코핑 배선은 CreateComponentCmd가 전담한다.
        """
        w = self._w
        if w._project is None:
            return
        from daedalus.view.commands.component_commands import CreateComponentCmd

        w._project_vm.execute(CreateComponentCmd(w._project, component))
        w._registry_panel.set_project(w._project)

    def on_new_component(self, kind: str) -> None:
        from daedalus.view.actions.creation import make_component

        if kind not in self._COMPONENT_TITLES:
            return  # 알 수 없는 종류 — 프로그램적 발화 방어
        name = self.ask_unique_name(self._COMPONENT_TITLES.get(kind, "새 컴포넌트"))
        if name is None:
            return
        # 팩토리는 캔버스 "여기에 만들기" 경로와 공유한다 — 만들어지는 물건이
        # 경로에 따라 달라지면 안 된다.
        self.register_component(make_component(self._w, kind, name))

    # --- 이름 변경 ---

    def on_component_renamed(
        self, component: object, old_name: str, new_name: str
    ) -> None:
        """_FrontmatterPanel.renamed 시그널 핸들러.

        1. 중복 이름 검사 — 다른 컴포넌트와 동명이면 거부(component.name을 old로 원복).
        2. rename_component로 문자열 참조 일괄 갱신.
        3. notify(structure) — 레지스트리/탭 타이틀 갱신 트리거.
        """
        w = self._w
        if w._project is None:
            return

        # 중복 이름 방지
        existing = (
            {s.name for s in w._project.skills if s is not component}
            | {a.name for a in w._project.agents if a is not component}
        )
        if new_name in existing:
            QMessageBox.warning(
                w, "이름 중복",
                f"'{new_name}' 이름이 이미 존재합니다.\n이름이 원래대로 되돌아갑니다.",
            )
            # component.name이 이미 new_name으로 바뀌었으므로 old_name으로 원복
            component.name = old_name  # type: ignore[union-attr]
            return

        # component.name은 _save_name에서 renamed 발화 전에 아직 old_name임.
        # RenameComponentCmd가 old_name → new_name 변경 + 참조 갱신을 수행하고,
        # undo 시 같은 함수를 옛 이름으로 불러 대칭으로 되돌린다 (WP-CE).
        from daedalus.view.commands.component_commands import RenameComponentCmd

        w._project_vm.execute(
            RenameComponentCmd(w._project, component, old_name, new_name)
        )

    # --- 삭제 ---

    def on_delete_component(self, component: object) -> None:
        """레지스트리 우클릭 '삭제' → 확인 후 삭제 커맨드 실행."""
        w = self._w
        if w._project is None:
            return

        comp_name = getattr(component, "name", str(component))

        # 참조 요약 수집 (간략 — validate 없이 빠른 사전 검사)
        ref_lines: list[str] = []
        if w._project is not None:
            from daedalus.model.fsm.state import SimpleState

            def _scan_fsm_refs(sm_obj) -> int:
                count = 0
                if sm_obj is None:
                    return 0
                for state in sm_obj.states:
                    if isinstance(state, SimpleState) and state.skill_ref is component:
                        count += 1
                return count

            for sk in w._project.skills:
                n = _scan_fsm_refs(getattr(sk, "fsm", None))
                if n:
                    ref_lines.append(f"  스킬 '{sk.name}'의 FSM: {n}개 배치")
            for ag in w._project.agents:
                n = _scan_fsm_refs(getattr(ag, "fsm", None))
                if n:
                    ref_lines.append(f"  에이전트 '{ag.name}'의 FSM: {n}개 배치")

        msg = f"'{comp_name}'을(를) 삭제하시겠습니까?"
        if ref_lines:
            msg += "\n\n다음 위치에서 참조 중입니다 (삭제 시 None으로 정리됩니다):\n"
            msg += "\n".join(ref_lines[:10])
            if len(ref_lines) > 10:
                msg += f"\n  ... 외 {len(ref_lines) - 10}건"

        reply = QMessageBox.question(
            w,
            "컴포넌트 삭제",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 위임은 한 방향이다 — 창의 동명 위임으로 되돌아가지 않고 실체를 직접 부른다.
        self.delete_component(component)
        w._status_label.setText(f"'{comp_name}' 삭제됨 (Ctrl+Z로 되돌릴 수 있습니다)")

    def delete_component(self, component: object) -> None:
        """컴포넌트 삭제 — 확인 다이얼로그 없이 커맨드로 실행한다 (A2).

        GUI 레지스트리 삭제와 MCP `delete_component`가 공유하는 실체다. 조작
        경로에 따라 Ctrl+Z가 듣고 안 듣고가 갈리면 협업 도구로 실격이다.

        **`_load_project_graph()`를 부르지 않는다** — 커맨드가 캔버스 VM을 직접
        떼어냈고, 여기서 모델로부터 VM을 다시 만들면 undo가 되돌려 놓을 VM 객체와
        캔버스에 있는 VM 객체가 서로 다른 물건이 되어(전이 VM이 사라진 노드 VM을
        가리킨다) 되돌린 그래프가 깨진다.
        """
        from daedalus.view.commands.component_commands import RemoveComponentCmd

        w = self._w
        if w._project is None:
            return

        comp_id = getattr(component, "id", None)

        # 본문 문서 캐시 정리 — 삭제된 컴포넌트의 undo 이력을 들고 있을 이유가
        # 없다 (WP-BU). 되돌리면 본문 자체는 모델에 살아 돌아오고, 탭을 다시 열
        # 때 문서가 새로 만들어진다(본문 편집 이력만 잃는다).
        from daedalus.view.editors import body_documents
        body_documents.registry().discard(component)

        # 열린 탭 닫기
        if comp_id is not None and comp_id in w._open_tabs:
            w._close_tab(w._open_tabs[comp_id])

        # 레지스트리는 별도로 갱신하지 않는다 — execute의 notify가
        # _on_project_vm_changed → set_placed_ids → _rebuild를 태우고, 그 rebuild가
        # 프로젝트 목록을 처음부터 다시 읽으므로 undo 복원도 같은 경로로 반영된다.
        w._project_vm.execute(
            RemoveComponentCmd(w._project, w._project_vm, component)
        )
