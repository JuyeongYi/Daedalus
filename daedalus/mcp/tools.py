"""MCP 도구 구현 (WP-MCP) — CC가 Daedalus를 함께 보고 함께 편집하는 표면.

모든 메서드는 **Qt 메인 스레드에서 실행되는 것을 전제**로 한다(service가
MainThreadInvoker로 마샬링한다). 여기서 스레드 안전성을 다시 걱정할 필요는 없다.

편집 도구는 반드시 ``ProjectViewModel.execute``(CommandStack)를 거친다 — 그래야
사용자가 Ctrl+Z로 되돌릴 수 있고, 스크립트 리스너에 사람 편집과 같은 형식으로
남는다. 본문 편집만은 예외적으로 컴포넌트의 QTextDocument에 적용하는데, 이는
본문이 캔버스와 분리된 자체 undo 스택을 갖기 때문이다(WP-BU) — 우회가 아니라
그 스택에 정확히 올리는 경로다.

**현재 커맨드화된 편집은 캔버스 구조뿐이다.** 프론트매터·블랙보드·훅 등 폼 편집은
아직 커맨드를 거치지 않으므로 이 표면에 노출하지 않았다(WP-CE에서 커맨드화한 뒤
합류시킨다).
"""
from __future__ import annotations

from typing import Any

_MAX_BODY_PREVIEW = 4000


class DaedalusTools:
    """MainWindow 하나에 붙는 도구 모음."""

    def __init__(self, window: Any) -> None:
        self._window = window

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    @property
    def _project(self) -> Any:
        project = getattr(self._window, "_project", None)
        if project is None:
            raise RuntimeError("열려 있는 프로젝트가 없습니다.")
        return project

    @property
    def _vm(self) -> Any:
        return self._window._project_vm

    def _components(self) -> list[Any]:
        project = self._project
        return [*project.skills, *project.agents, *project.delegations]

    def _find_component(self, name: str) -> Any:
        for comp in self._components():
            if getattr(comp, "name", None) == name:
                return comp
        known = ", ".join(sorted(str(getattr(c, "name", "?")) for c in self._components()))
        raise ValueError(f"'{name}' 컴포넌트를 찾을 수 없습니다. 사용 가능: {known or '(없음)'}")

    def _find_state_vm(self, name: str) -> Any:
        vm = self._vm.get_state_vm(name)
        if vm is None:
            known = ", ".join(sorted(s.model.name for s in self._vm.state_vms))
            raise ValueError(f"캔버스에 '{name}' 노드가 없습니다. 현재 노드: {known or '(없음)'}")
        return vm

    @staticmethod
    def _component_kind(comp: Any) -> str:
        return str(getattr(comp, "kind", type(comp).__name__))

    def _placement_summary(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for svm in self._vm.state_vms:
            model = svm.model
            ref = getattr(model, "skill_ref", None)
            out.append(
                {
                    "node": model.name,
                    "component": getattr(ref, "name", None),
                    "kind": self._component_kind(ref) if ref is not None else "empty",
                    "x": round(svm.x, 1),
                    "y": round(svm.y, 1),
                    "reads": list(getattr(model, "reads", []) or []),
                    "writes": list(getattr(model, "writes", []) or []),
                }
            )
        return out

    def _transition_summary(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for tvm in self._vm.transition_vms:
            trans = tvm.model
            trigger = getattr(trans, "trigger", None)
            out.append(
                {
                    "source": tvm.source_vm.model.name,
                    "target": tvm.target_vm.model.name,
                    "trigger": getattr(trigger, "name", None),
                    "target_port": getattr(trans, "target_port", "") or None,
                    "transfer_skill": getattr(getattr(trans, "skill_ref", None), "name", None),
                }
            )
        return out

    # ------------------------------------------------------------------
    # 읽기 도구
    # ------------------------------------------------------------------

    def get_project(self) -> dict[str, Any]:
        """지금 열려 있는 프로젝트의 전체 개요 — 컴포넌트 목록, 캔버스 배치, 블랙보드."""
        project = self._project
        blackboard = getattr(project, "blackboard", None)
        classes = list(getattr(blackboard, "class_definitions", []) or [])
        return {
            "name": project.name,
            "description": project.description,
            "version": project.version,
            "build_target": getattr(getattr(project, "build_target", None), "value", None),
            "saved_path": getattr(self._window, "_current_path", None),
            "skills": [
                {
                    "name": s.name,
                    "kind": self._component_kind(s),
                    "description": s.description,
                }
                for s in project.skills
            ],
            "agents": [
                {"name": a.name, "description": a.description} for a in project.agents
            ],
            "placements": self._placement_summary(),
            "transitions": self._transition_summary(),
            "blackboard_classes": [
                {
                    "name": c.name,
                    "description": getattr(c, "description", ""),
                    "fields": [f.name for f in getattr(c, "fields", [])],
                }
                for c in classes
            ],
            "can_undo": self._window._active_stack.can_undo,
            "can_redo": self._window._active_stack.can_redo,
        }

    def get_selection(self) -> dict[str, Any]:
        """사용자가 지금 캔버스에서 선택한 것 — "이거 고쳐줘"의 '이거'를 알아내는 통로."""
        from daedalus.view.canvas.edge_item import TransitionEdgeItem
        from daedalus.view.canvas.node_item import StateNodeItem
        from daedalus.view.canvas.ref_node_item import ReferenceNodeItem

        scene = getattr(self._window, "_fsm_scene", None)
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        refs: list[str] = []
        if scene is not None:
            for item in scene.selectedItems():
                if isinstance(item, StateNodeItem):
                    model = item.state_vm.model
                    ref = getattr(model, "skill_ref", None)
                    nodes.append(
                        {
                            "node": model.name,
                            "component": getattr(ref, "name", None),
                            "kind": self._component_kind(ref) if ref is not None else "empty",
                        }
                    )
                elif isinstance(item, TransitionEdgeItem):
                    tvm = item.transition_vm
                    edges.append(
                        {
                            "source": tvm.source_vm.model.name,
                            "target": tvm.target_vm.model.name,
                        }
                    )
                elif isinstance(item, ReferenceNodeItem):
                    refs.append(str(getattr(item._ref_vm.model, "name", "?")))

        tabs = getattr(self._window, "_tabs", None)
        active_tab = None
        if tabs is not None:
            active_tab = tabs.tabText(tabs.currentIndex())

        return {
            "active_tab": active_tab,
            "selected_nodes": nodes,
            "selected_transitions": edges,
            "selected_references": refs,
            "empty": not (nodes or edges or refs),
        }

    def get_component(self, name: str) -> dict[str, Any]:
        """스킬/에이전트 하나의 상세 — 본문, 설정, 자체 FSM 요약."""
        comp = self._find_component(name)
        config = getattr(comp, "config", None)
        body = str(getattr(comp, "body", "") or "")
        truncated = len(body) > _MAX_BODY_PREVIEW
        fsm = getattr(comp, "fsm", None)

        info: dict[str, Any] = {
            "name": comp.name,
            "kind": self._component_kind(comp),
            "description": getattr(comp, "description", ""),
            "when_to_use": getattr(comp, "when_to_use", ""),
            "body": body[:_MAX_BODY_PREVIEW],
            "body_truncated": truncated,
            "body_length": len(body),
            "transfer_on": [
                {"name": e.name, "description": getattr(e, "description", "")}
                for e in (getattr(comp, "transfer_on", []) or [])
            ],
            "entry_paths": [
                {"name": e.name, "description": getattr(e, "description", "")}
                for e in (getattr(comp, "entry_paths", []) or [])
            ],
        }
        if config is not None:
            info["config"] = {
                key: (getattr(value, "value", value))
                for key, value in vars(config).items()
                if not key.startswith("_") and key != "id"
            }
        if fsm is not None:
            info["fsm"] = {
                "states": [s.name for s in fsm.states],
                "transitions": [
                    {"source": t.source.name, "target": t.target.name}
                    for t in fsm.transitions
                ],
            }
        return info

    def validate_project(self) -> dict[str, Any]:
        """F7 검증과 같은 결과 — 컴파일을 막는 에러와 경고를 구분해 돌려준다."""
        from daedalus.model.validation import Validator

        errors = Validator().validate_project(self._project)
        return {
            "error_count": sum(1 for e in errors if not e.is_warning),
            "warning_count": sum(1 for e in errors if e.is_warning),
            "issues": [
                {
                    "rule": e.rule,
                    "severity": "warning" if e.is_warning else "error",
                    "message": e.message,
                    "path": list(getattr(e, "path", ()) or ()),
                }
                for e in errors
            ],
        }

    def compile_preview(self, name: str) -> dict[str, Any]:
        """컴포넌트가 어떤 SKILL.md / 에이전트 .md로 컴파일되는지 — 파일은 쓰지 않는다."""
        from daedalus.compiler.emit import compile_agent, compile_skill
        from daedalus.model.plugin.agent import AgentDefinition

        comp = self._find_component(name)
        project = self._project
        if isinstance(comp, AgentDefinition):
            text = compile_agent(comp, project=project)
        else:
            text = compile_skill(comp, project=project)
        return {"name": comp.name, "kind": self._component_kind(comp), "text": text}

    # ------------------------------------------------------------------
    # 편집 도구 (CommandStack 경유 — 사용자가 Ctrl+Z로 되돌릴 수 있다)
    # ------------------------------------------------------------------

    def place_component(self, name: str, x: float = 0.0, y: float = 0.0) -> dict[str, Any]:
        """스킬/에이전트를 프로젝트 캔버스에 배치한다."""
        from daedalus.model.fsm.state import SimpleState
        from daedalus.view.commands.state_commands import CreateStateCmd
        from daedalus.view.viewmodel.state_vm import StateViewModel

        comp = self._find_component(name)
        state = SimpleState(name=comp.name, skill_ref=comp)
        svm = StateViewModel(model=state, x=float(x), y=float(y))
        self._vm.execute(CreateStateCmd(self._vm, svm, fsm=self._project.graph))
        return {"placed": comp.name, "node": state.name, "x": float(x), "y": float(y)}

    def create_state(self, name: str, x: float = 0.0, y: float = 0.0) -> dict[str, Any]:
        """컴포넌트가 붙지 않은 빈 상태 노드를 만든다."""
        from daedalus.model.fsm.state import SimpleState
        from daedalus.view.commands.state_commands import CreateStateCmd
        from daedalus.view.viewmodel.state_vm import StateViewModel

        state = SimpleState(name=name)
        svm = StateViewModel(model=state, x=float(x), y=float(y))
        self._vm.execute(CreateStateCmd(self._vm, svm, fsm=self._project.graph))
        return {"created": name, "x": float(x), "y": float(y)}

    def move_state(self, name: str, x: float, y: float) -> dict[str, Any]:
        """노드를 옮긴다."""
        from daedalus.view.commands.state_commands import MoveStateCmd

        svm = self._find_state_vm(name)
        old_x, old_y = svm.x, svm.y
        self._vm.execute(MoveStateCmd(svm, old_x, old_y, float(x), float(y)))
        return {"moved": name, "from": [old_x, old_y], "to": [float(x), float(y)]}

    def rename_state(self, name: str, new_name: str) -> dict[str, Any]:
        """노드 이름을 바꾼다(캔버스 노드 이름 — 컴포넌트 이름과는 별개)."""
        from daedalus.view.commands.state_commands import RenameStateCmd

        svm = self._find_state_vm(name)
        self._vm.execute(RenameStateCmd(svm, name, new_name))
        return {"renamed": name, "to": new_name}

    def delete_state(self, name: str) -> dict[str, Any]:
        """노드와 그에 연결된 전이를 함께 지운다(1 undo 단위)."""
        from daedalus.view.commands.base import MacroCommand
        from daedalus.view.commands.state_commands import DeleteStateCmd
        from daedalus.view.commands.transition_commands import DeleteTransitionCmd

        svm = self._find_state_vm(name)
        graph = self._project.graph
        children: list[Any] = [
            DeleteTransitionCmd(self._vm, tvm, fsm=graph)
            for tvm in self._vm.get_transitions_for(svm)
        ]
        removed = len(children)
        children.append(DeleteStateCmd(self._vm, svm, fsm=graph))
        self._vm.execute(MacroCommand(children=children, description=f"상태 '{name}' 삭제"))
        return {"deleted": name, "removed_transitions": removed}

    def connect_states(self, source: str, target: str) -> dict[str, Any]:
        """두 노드를 전이로 잇는다."""
        from daedalus.model.fsm.transition import Transition
        from daedalus.view.commands.transition_commands import CreateTransitionCmd
        from daedalus.view.viewmodel.state_vm import TransitionViewModel

        src = self._find_state_vm(source)
        tgt = self._find_state_vm(target)
        trans = Transition(source=src.model, target=tgt.model)
        tvm = TransitionViewModel(model=trans, source_vm=src, target_vm=tgt)
        self._vm.execute(CreateTransitionCmd(self._vm, tvm, fsm=self._project.graph))
        return {"connected": [source, target]}

    def disconnect_states(self, source: str, target: str) -> dict[str, Any]:
        """두 노드 사이의 전이를 지운다."""
        from daedalus.view.commands.transition_commands import DeleteTransitionCmd

        src = self._find_state_vm(source)
        matches = [
            tvm
            for tvm in self._vm.get_transitions_for(src)
            if tvm.source_vm is src and tvm.target_vm.model.name == target
        ]
        if not matches:
            raise ValueError(f"'{source}' → '{target}' 전이가 없습니다.")
        for tvm in matches:
            self._vm.execute(DeleteTransitionCmd(self._vm, tvm, fsm=self._project.graph))
        return {"disconnected": [source, target], "count": len(matches)}

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

    def undo(self) -> dict[str, Any]:
        """활성 탭의 undo — 사람이 Ctrl+Z를 누른 것과 같다."""
        stack = self._window._active_stack
        if not stack.can_undo:
            return {"undone": None, "can_undo": False}
        label = stack.history[-1].description
        self._window._undo()
        return {"undone": label, "can_undo": stack.can_undo}

    def redo(self) -> dict[str, Any]:
        stack = self._window._active_stack
        if not stack.can_redo:
            return {"redone": None, "can_redo": False}
        label = stack.redo_history[0].description
        self._window._redo()
        return {"redone": label, "can_redo": stack.can_redo}

    def get_history(self, limit: int = 20) -> dict[str, Any]:
        """최근 편집 이력 — 사람이 방금 무엇을 했는지 CC가 따라잡는 통로."""
        stack = self._window._active_stack
        history = stack.history[-limit:]
        return {
            "entries": [
                {"description": c.description, "script": c.script_repr} for c in history
            ],
            "can_undo": stack.can_undo,
            "can_redo": stack.can_redo,
        }
