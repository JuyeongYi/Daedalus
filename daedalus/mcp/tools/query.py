# daedalus/mcp/tools/query.py
"""조회 도구 + undo 스택 — get_project/get_selection/get_component/
validate_project/compile_preview/get_history/undo/redo (WP-RF-3b).

**계층: GUI 어댑터다 (WP-RF-2 명시).** core(model/compiler)가 아니라
MainWindow·ProjectViewModel·CommandStack·body_documents 등 view 표면에 결합된
코드로, core 경계 계약(tests/test_import_contracts.py)의 대상이 아니다.
모든 메서드는 **Qt 메인 스레드에서 실행되는 것을 전제**로 한다(service가
MainThreadInvoker로 마샬링한다). 편집 도구는 반드시
``ProjectViewModel.execute``(CommandStack)를 거친다 — 사용자가 Ctrl+Z로
되돌릴 수 있어야 한다.
"""
from __future__ import annotations

from typing import Any

from ._base import _MAX_BODY_PREVIEW, _BaseTools


class QueryTools(_BaseTools):
    """읽기 도구 — 캔버스 요약 헬퍼 + 프로젝트/선택/컴포넌트 조회."""

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
                    "transfer_skill": getattr(getattr(trans, "skill_ref", None), "name", None),
                }
            )
        return out

    def _reference_summary(self) -> list[dict[str, Any]]:
        """캔버스에 배치된 참조 노드 — 같은 스킬이 여러 번 놓일 수 있어 index를 함께 준다."""
        out: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        for rvm in self._vm.reference_vms:
            name = str(getattr(rvm.model, "name", "?"))
            index = counts.get(name, 0)
            counts[name] = index + 1
            out.append(
                {
                    "component": name,
                    "index": index,
                    "x": round(rvm.x, 1),
                    "y": round(rvm.y, 1),
                    "linked_nodes": [
                        link.state_vm.model.name
                        for link in self._vm.reference_links
                        if link.reference_vm is rvm
                    ],
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
            "references": self._reference_summary(),
            "hook_library": [
                self._hook_summary(h) for h in getattr(project, "hook_library", []) or []
            ],
            "emit_progress_hook": getattr(project, "emit_progress_hook", None),
            "mcp_server_defs": dict(getattr(project, "mcp_server_defs", None) or {}),
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
            # 에이전트 호출 포트 — 에이전트로 가는 전이는 이 포트에서만 나갈 수 있다
            "call_agents": [
                {"name": e.name, "description": getattr(e, "description", "")}
                for e in (getattr(comp, "call_agents", []) or [])
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
    # undo 스택 (활성 탭 기준 — 사람이 Ctrl+Z/Ctrl+Y를 누른 것과 같다)
    # ------------------------------------------------------------------

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
