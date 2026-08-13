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

    def _find_component(self, name: str, agent: str = "") -> Any:
        """이름으로 컴포넌트를 찾는다.

        agent를 주면 그 에이전트의 **로컬 스킬**을 먼저 뒤진다 — 로컬 스킬은
        project.skills에 없고 agent.skills에만 있다.
        """
        pool = list(self._components())
        if agent:
            for comp in self._components():
                if getattr(comp, "name", None) == agent:
                    pool = list(getattr(comp, "skills", []) or []) + pool
                    break
        for comp in pool:
            if getattr(comp, "name", None) == name:
                return comp
        known = ", ".join(sorted(str(getattr(c, "name", "?")) for c in pool))
        raise ValueError(f"'{name}' 컴포넌트를 찾을 수 없습니다. 사용 가능: {known or '(없음)'}")

    def _find_state_vm(self, name: str, vm: Any = None) -> Any:
        target = vm if vm is not None else self._vm
        found = target.get_state_vm(name)
        if found is None:
            known = ", ".join(sorted(s.model.name for s in target.state_vms))
            raise ValueError(f"캔버스에 '{name}' 노드가 없습니다. 현재 노드: {known or '(없음)'}")
        return found

    # --- 편집 범위 (프로젝트 캔버스 vs 에이전트 내부 FSM) ---

    def _agent_editor(self, agent_obj: Any) -> Any:
        """에이전트 편집기 위젯을 얻는다 — 닫혀 있으면 탭을 연다.

        커맨드가 캔버스 VM을 다루므로, 편집 결과가 화면에 반영되려면 그 에디터가
        살아 있어야 한다. AI가 편집하는 순간 사용자 화면에도 해당 탭이 열리는데,
        이는 협업 관점에서 오히려 바람직하다 — 무엇이 바뀌는지 보인다.
        """
        from daedalus.view.editors.agent_editor import AgentEditor

        win = self._window
        comp_id = getattr(agent_obj, "id", None)
        if comp_id is None:
            raise RuntimeError("에이전트에 id가 없습니다.")
        if comp_id not in win._open_tabs:
            win._open_component(agent_obj)
        index = win._open_tabs.get(comp_id)
        widget = win._tabs.widget(index) if index is not None else None
        if not isinstance(widget, AgentEditor):
            raise RuntimeError(f"에이전트 '{getattr(agent_obj, 'name', '?')}' 편집기를 열지 못했습니다.")
        return widget

    def _scope(self, agent: str = "") -> tuple[Any, Any]:
        """편집 대상 (뷰모델, 백킹 StateMachine)을 고른다.

        agent가 비어 있으면 프로젝트 캔버스, 아니면 그 에이전트의 내부 FSM.
        """
        from daedalus.model.plugin.agent import AgentDefinition

        if not agent:
            return self._vm, self._project.graph
        agent_obj = self._find_component(agent)
        if not isinstance(agent_obj, AgentDefinition):
            kind = self._component_kind(agent_obj)
            raise ValueError(f"'{agent}'는 에이전트가 아닙니다(현재 {kind}).")
        editor = self._agent_editor(agent_obj)
        return editor._graph_vm, agent_obj.fsm

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

    def get_component(self, name: str, agent: str = "") -> dict[str, Any]:
        """스킬/에이전트 하나의 상세 — 본문, 설정, 자체 FSM 요약.

        agent를 지정하면 그 에이전트의 로컬 스킬도 조회 대상에 포함된다.
        """
        comp = self._find_component(name, agent=agent)
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

    def _reject_duplicate_name(self, name: str) -> None:
        if any(getattr(c, "name", None) == name for c in self._components()):
            raise ValueError(f"'{name}' 이름의 컴포넌트가 이미 있습니다.")

    def create_skill(
        self, name: str, kind: str = "procedural", description: str = "", agent: str = ""
    ) -> dict[str, Any]:
        """스킬을 만든다.

        kind: procedural(작업 지침·자체 FSM) / declarative(배경 지식) /
        transfer(전이 시 실행되는 보조 지침) / reference(참조 문서).
        agent를 지정하면 그 에이전트의 **로컬 스킬**로 만든다(procedural/transfer만).
        """
        from daedalus.model.plugin.skill import (
            DeclarativeSkill,
            ProceduralSkill,
            ReferenceSkill,
            TransferSkill,
        )

        if agent:
            return self._create_local_skill(name, kind, description, agent)

        self._reject_duplicate_name(name)
        win = self._window
        factories = {
            "procedural": lambda: ProceduralSkill(
                fsm=win._make_fsm(name), name=name, description=description
            ),
            "declarative": lambda: DeclarativeSkill(name=name, description=description),
            "transfer": lambda: TransferSkill(
                fsm=win._make_fsm(name), name=name, description=description
            ),
            "reference": lambda: ReferenceSkill(name=name, description=description),
        }
        if kind not in factories:
            raise ValueError(
                f"알 수 없는 스킬 종류 '{kind}'. 사용 가능: {', '.join(factories)}"
            )
        win._register_component(factories[kind]())
        return {"created": name, "kind": kind}

    def _create_local_skill(
        self, name: str, kind: str, description: str, agent: str
    ) -> dict[str, Any]:
        """에이전트 내부에만 존재하는 로컬 스킬 (agent_editor._on_add_local_skill 미러링)."""
        from daedalus.model.fsm.machine import StateMachine
        from daedalus.model.fsm.state import SimpleState
        from daedalus.model.plugin.agent import AgentDefinition
        from daedalus.model.plugin.skill import ProceduralSkill, TransferSkill
        from daedalus.view.commands.attr_commands import AppendToListCmd

        agent_obj = self._find_component(agent)
        if not isinstance(agent_obj, AgentDefinition):
            raise ValueError(f"'{agent}'는 에이전트가 아닙니다.")
        if kind not in ("procedural", "transfer"):
            raise ValueError(
                f"로컬 스킬은 procedural / transfer만 가능합니다(요청: {kind})."
            )
        if any(s.name == name for s in agent_obj.skills):
            raise ValueError(f"에이전트 '{agent}'에 '{name}' 스킬이 이미 있습니다.")

        start = SimpleState(name="start")
        fsm = StateMachine(name=f"{name}_fsm", states=[start], initial_state=start)
        # 블랙보드 스코핑 — 로컬 스킬 FSM은 소유 에이전트 FSM 블랙보드의 자식이다.
        if fsm.blackboard.parent is None:
            fsm.blackboard.parent = agent_obj.fsm.blackboard
        skill = (
            ProceduralSkill(fsm=fsm, name=name, description=description)
            if kind == "procedural"
            else TransferSkill(fsm=fsm, name=name, description=description)
        )

        vm, _ = self._scope(agent)  # 에디터를 열어 둔다 — 목록 갱신에 필요
        vm.execute(
            AppendToListCmd(
                agent_obj.skills,
                skill,
                label=f"에이전트 '{agent}'의 로컬 스킬 '{name}' 생성",
                script=f'create_skill("{name}", kind="{kind}", agent="{agent}")',
            )
        )
        editor = self._agent_editor(agent_obj)
        if hasattr(editor, "_refresh_skill_list"):
            editor._refresh_skill_list()
        return {"created": name, "kind": kind, "agent": agent, "local": True}

    def create_agent(self, name: str, description: str = "") -> dict[str, Any]:
        """에이전트를 만든다 — 별도 컨텍스트의 상태 기계(EntryPoint/ExitPoint 포함)."""
        from daedalus.model.plugin.agent import AgentDefinition

        self._reject_duplicate_name(name)
        win = self._window
        agent = AgentDefinition(
            fsm=win._make_agent_fsm(name), name=name, description=description
        )
        win._register_component(agent)
        return {"created": name, "kind": "agent"}

    def rename_component(self, name: str, new_name: str) -> dict[str, Any]:
        """컴포넌트 이름을 바꾼다 — 문자열 참조도 함께 갱신된다."""
        from daedalus.view.commands.component_commands import RenameComponentCmd

        comp = self._find_component(name)
        self._reject_duplicate_name(new_name)
        self._vm.execute(RenameComponentCmd(self._project, comp, name, new_name))
        self._window._registry_panel.set_project(self._project)
        return {"renamed": name, "to": new_name}

    def set_component_description(self, name: str, description: str) -> dict[str, Any]:
        """컴포넌트 설명을 바꾼다.

        아직 커맨드가 아니다 — 프론트매터 편집 전반이 WP-CE에서 커맨드화될 때
        함께 옮겨간다. 그때까지 이 편집만은 Ctrl+Z로 되돌아가지 않는다.
        """
        comp = self._find_component(name)
        old = getattr(comp, "description", "")
        comp.description = description
        self._vm.notify()
        return {"component": name, "old": old, "new": description}

    def place_component(
        self, name: str, x: float = 0.0, y: float = 0.0, agent: str = ""
    ) -> dict[str, Any]:
        """스킬/에이전트를 캔버스에 배치한다.

        agent를 지정하면 그 에이전트의 내부 FSM에 배치한다(로컬 스킬도 이때 찾는다).
        """
        from daedalus.model.fsm.state import SimpleState
        from daedalus.view.commands.state_commands import CreateStateCmd
        from daedalus.view.viewmodel.state_vm import StateViewModel

        vm, fsm = self._scope(agent)
        comp = self._find_component(name, agent=agent)
        state = SimpleState(name=comp.name, skill_ref=comp)
        svm = StateViewModel(model=state, x=float(x), y=float(y))
        vm.execute(CreateStateCmd(vm, svm, fsm=fsm))
        return {
            "placed": comp.name,
            "node": state.name,
            "x": float(x),
            "y": float(y),
            "scope": agent or "project",
        }

    def create_state(
        self, name: str, x: float = 0.0, y: float = 0.0, agent: str = ""
    ) -> dict[str, Any]:
        """컴포넌트가 붙지 않은 빈 상태 노드를 만든다."""
        from daedalus.model.fsm.state import SimpleState
        from daedalus.view.commands.state_commands import CreateStateCmd
        from daedalus.view.viewmodel.state_vm import StateViewModel

        vm, fsm = self._scope(agent)
        state = SimpleState(name=name)
        svm = StateViewModel(model=state, x=float(x), y=float(y))
        vm.execute(CreateStateCmd(vm, svm, fsm=fsm))
        return {"created": name, "x": float(x), "y": float(y), "scope": agent or "project"}

    def move_state(self, name: str, x: float, y: float, agent: str = "") -> dict[str, Any]:
        """노드를 옮긴다."""
        from daedalus.view.commands.state_commands import MoveStateCmd

        vm, _ = self._scope(agent)
        svm = self._find_state_vm(name, vm)
        old_x, old_y = svm.x, svm.y
        vm.execute(MoveStateCmd(svm, old_x, old_y, float(x), float(y)))
        return {"moved": name, "from": [old_x, old_y], "to": [float(x), float(y)]}

    def rename_state(self, name: str, new_name: str, agent: str = "") -> dict[str, Any]:
        """노드 이름을 바꾼다(캔버스 노드 이름 — 컴포넌트 이름과는 별개)."""
        from daedalus.view.commands.state_commands import RenameStateCmd

        vm, _ = self._scope(agent)
        svm = self._find_state_vm(name, vm)
        vm.execute(RenameStateCmd(svm, name, new_name))
        return {"renamed": name, "to": new_name}

    def delete_state(self, name: str, agent: str = "") -> dict[str, Any]:
        """노드와 그에 연결된 전이를 함께 지운다(1 undo 단위)."""
        from daedalus.view.commands.base import MacroCommand
        from daedalus.view.commands.state_commands import DeleteStateCmd
        from daedalus.view.commands.transition_commands import DeleteTransitionCmd

        vm, fsm = self._scope(agent)
        svm = self._find_state_vm(name, vm)
        children: list[Any] = [
            DeleteTransitionCmd(vm, tvm, fsm=fsm) for tvm in vm.get_transitions_for(svm)
        ]
        removed = len(children)
        children.append(DeleteStateCmd(vm, svm, fsm=fsm))
        vm.execute(MacroCommand(children=children, description=f"상태 '{name}' 삭제"))
        return {"deleted": name, "removed_transitions": removed}

    @staticmethod
    def _callee_section_title(skill_name: str, event_name: str) -> str:
        """캔버스(FsmScene._callee_section_title)와 같은 제목 규약을 쓴다."""
        return f"caller: {skill_name} ({event_name})"

    def _agent_call_contract_cmds(
        self, src_ref: Any, tgt_ref: Any, event_name: str
    ) -> list[Any]:
        """에이전트 호출 연결 시 callee의 caller_contracts에 계약 카드를 만든다.

        캔버스가 `_make_agent_call_section_cmds`로 하는 일과 동일하다 — MCP 경로가
        이걸 빠뜨리면 같은 조작인데 결과가 달라진다.
        """
        from daedalus.model.fsm.section import Section
        from daedalus.view.commands.section_commands import AddSectionCmd

        title = self._callee_section_title(src_ref.name, event_name)
        if any(s.title == title for s in tgt_ref.caller_contracts):
            return []
        return [AddSectionCmd(tgt_ref.caller_contracts, Section(title=title, content=""))]

    def add_agent_call(
        self, skill: str, event: str, description: str = "", color: str = ""
    ) -> dict[str, Any]:
        """ProceduralSkill에 **에이전트 호출 포트**를 추가한다.

        에이전트로 가는 전이는 이 포트에서만 나갈 수 있다(캔버스와 같은 규칙).
        포트를 만든 뒤 connect_states(..., trigger=<event>)로 연결한다.
        """
        from daedalus.model.plugin.skill import ProceduralSkill
        from daedalus.view.commands.attr_commands import SetAttrCmd

        comp = self._find_component(skill)
        if not isinstance(comp, ProceduralSkill):
            raise ValueError(
                f"'{skill}'은 ProceduralSkill이 아닙니다 — 에이전트 호출 포트는 절차형 스킬에만 붙는다."
            )
        if any(e.name == event for e in comp.call_agents):
            raise ValueError(f"'{skill}'에 이미 '{event}' 호출 포트가 있습니다.")
        spec: dict[str, Any] = {"name": event}
        if description:
            spec["description"] = description
        if color:
            spec["color"] = color
        new_list = list(comp.call_agents) + self._make_event_defs([spec])
        self._vm.execute(
            SetAttrCmd(
                comp,
                "call_agents",
                new_list,
                label=f"'{skill}' 에이전트 호출 포트 '{event}' 추가",
                script=f'add_agent_call("{skill}", "{event}")',
            )
        )
        return {"skill": skill, "call_agents": [e.name for e in new_list]}

    def connect_states(
        self,
        source: str,
        target: str,
        trigger: str = "",
        guard: str = "",
        target_port: str = "",
        agent: str = "",
    ) -> dict[str, Any]:
        """두 노드를 전이로 잇는다.

        trigger: 출발 스킬의 출력 이벤트(transfer_on) 또는 에이전트 호출 포트
        (call_agents) 이름. 분기가 여러 갈래일 때 이 값이 있어야 어느 경로인지
        표현되고 캔버스 포트도 갈라진다.
        guard: 전이 조건 서술(LLM이 판정할 자연어). 빈 값이면 가드 없음.
        target_port: 도착 스킬의 입력 경로(entry_paths) 이름.
        agent: 지정하면 그 에이전트의 내부 FSM에서 연결한다(기본은 프로젝트 캔버스).

        **에이전트 노드로 가는 전이는 반드시 call_agent 포트에서 나가야 한다** —
        캔버스와 같은 규칙이며, 연결 시 대상 에이전트의 caller_contracts에 계약
        카드가 함께 만들어진다.
        """
        from daedalus.model.fsm.transition import Transition
        from daedalus.model.plugin.agent import AgentDefinition
        from daedalus.model.plugin.skill import ProceduralSkill
        from daedalus.view.commands.base import MacroCommand
        from daedalus.view.commands.transition_commands import CreateTransitionCmd
        from daedalus.view.viewmodel.state_vm import TransitionViewModel

        vm, fsm = self._scope(agent)
        src = self._find_state_vm(source, vm)
        tgt = self._find_state_vm(target, vm)
        src_ref = getattr(src.model, "skill_ref", None)
        tgt_ref = getattr(tgt.model, "skill_ref", None)

        is_agent_call = False
        if isinstance(tgt_ref, AgentDefinition):
            if not isinstance(src_ref, ProceduralSkill):
                raise ValueError(
                    f"에이전트 '{target}'은 ProceduralSkill에서만 호출할 수 있습니다."
                )
            if not trigger:
                raise ValueError(
                    f"에이전트 '{target}'으로의 연결에는 호출 포트 이름이 필요합니다. "
                    f'add_agent_call("{source}", "<포트명>") 으로 포트를 먼저 만들고 '
                    "trigger로 지정하세요."
                )
            if not any(e.name == trigger for e in src_ref.call_agents):
                have = ", ".join(e.name for e in src_ref.call_agents) or "(없음)"
                raise ValueError(
                    f"'{source}'에 '{trigger}' 에이전트 호출 포트가 없습니다(현재: {have}). "
                    f'add_agent_call("{source}", "{trigger}") 로 먼저 만드세요.'
                )
            is_agent_call = True
        elif trigger and isinstance(src_ref, ProceduralSkill):
            # call_agent 포트는 에이전트로만 나갈 수 있다 (캔버스와 같은 규칙)
            if any(e.name == trigger for e in src_ref.call_agents):
                raise ValueError(
                    f"'{trigger}'는 에이전트 호출 포트입니다 — 에이전트가 아닌 "
                    f"'{target}'으로는 연결할 수 없습니다."
                )

        trans = Transition(source=src.model, target=tgt.model)
        if trigger:
            trans.trigger = self._make_trigger(trigger)
        if guard:
            trans.guard = self._make_guard(guard)
        if target_port:
            trans.target_port = target_port
        tvm = TransitionViewModel(model=trans, source_vm=src, target_vm=tgt)

        cmds: list[Any] = [CreateTransitionCmd(vm, tvm, fsm=fsm)]
        if is_agent_call:
            cmds.extend(self._agent_call_contract_cmds(src_ref, tgt_ref, trigger))
        vm.execute(
            cmds[0]
            if len(cmds) == 1
            else MacroCommand(
                children=cmds, description=f"에이전트 호출 '{trigger}→{target}' 연결"
            )
        )
        return {
            "connected": [source, target],
            "trigger": trigger or None,
            "guard": guard or None,
            "target_port": target_port or None,
            "agent_call": is_agent_call,
            "scope": agent or "project",
        }

    @staticmethod
    def _make_trigger(name: str):
        from daedalus.model.fsm.event import CompletionEvent

        return CompletionEvent(name=name)

    @staticmethod
    def _make_guard(condition: str):
        from daedalus.model.fsm.guard import Guard
        from daedalus.model.fsm.strategy import LLMEvaluation

        return Guard(evaluation=LLMEvaluation(prompt=condition))

    def _find_transition_vm(self, source: str, target: str, vm: Any = None) -> Any:
        target_vm = vm if vm is not None else self._vm
        src = self._find_state_vm(source, target_vm)
        for tvm in target_vm.get_transitions_for(src):
            if tvm.source_vm is src and tvm.target_vm.model.name == target:
                return tvm
        raise ValueError(f"'{source}' → '{target}' 전이가 없습니다.")

    def set_transition(
        self,
        source: str,
        target: str,
        trigger: str | None = None,
        guard: str | None = None,
        target_port: str | None = None,
        agent: str = "",
    ) -> dict[str, Any]:
        """이미 있는 전이에 트리거·가드·입력 포트를 설정한다.

        None을 넘긴 항목은 건드리지 않는다. 빈 문자열("")을 넘기면 그 항목을 지운다.
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd
        from daedalus.view.commands.base import MacroCommand

        vm, _ = self._scope(agent)
        tvm = self._find_transition_vm(source, target, vm)
        trans = tvm.model
        cmds: list[Any] = []
        if trigger is not None:
            cmds.append(
                SetAttrCmd(
                    trans,
                    "trigger",
                    self._make_trigger(trigger) if trigger else None,
                    label=f"전이 '{source}→{target}' 트리거: {trigger or '(없음)'}",
                    script=f'set_transition("{source}", "{target}", trigger="{trigger}")',
                )
            )
        if guard is not None:
            cmds.append(
                SetAttrCmd(
                    trans,
                    "guard",
                    self._make_guard(guard) if guard else None,
                    label=f"전이 '{source}→{target}' 가드 설정",
                    script=f'set_transition("{source}", "{target}", guard="{guard}")',
                )
            )
        if target_port is not None:
            cmds.append(
                SetAttrCmd(
                    trans,
                    "target_port",
                    target_port,
                    label=f"전이 '{source}→{target}' 입력 포트: {target_port or '(기본)'}",
                    script=f'set_transition("{source}", "{target}", target_port="{target_port}")',
                )
            )
        if not cmds:
            return {"transition": [source, target], "changed": []}
        vm.execute(
            cmds[0]
            if len(cmds) == 1
            else MacroCommand(children=cmds, description=f"전이 '{source}→{target}' 설정")
        )
        return {
            "transition": [source, target],
            "trigger": trigger,
            "guard": guard,
            "target_port": target_port,
        }

    # --- 포트 (출력 이벤트 / 입력 경로) ---

    @staticmethod
    def _make_event_defs(events: list[dict[str, Any]]) -> list[Any]:
        from daedalus.model.fsm.section import EventDef

        out = []
        for spec in events:
            if isinstance(spec, str):
                out.append(EventDef(name=spec))
                continue
            name = spec.get("name")
            if not name:
                raise ValueError("각 이벤트에는 name이 필요합니다.")
            kwargs: dict[str, Any] = {"name": name}
            if spec.get("description"):
                kwargs["description"] = spec["description"]
            if spec.get("color"):
                kwargs["color"] = spec["color"]
            out.append(EventDef(**kwargs))
        return out

    def set_transfer_on(self, name: str, events: list[dict[str, Any]]) -> dict[str, Any]:
        """스킬/에이전트의 **출력 포트**를 정의한다.

        events: [{"name": "gpu", "description": "GPU 병목", "color": "#ff8844"}, ...]
        분기가 여러 갈래인 노드는 여기에 갈래를 선언해야 캔버스 포트가 갈라지고,
        각 전이의 trigger로 어느 갈래인지 지정할 수 있다.
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd

        comp = self._find_component(name)
        defs = self._make_event_defs(events)
        self._vm.execute(
            SetAttrCmd(
                comp,
                "transfer_on",
                defs,
                label=f"'{name}' 출력 포트 {len(defs)}개 설정",
                script=f'set_transfer_on("{name}", {[d.name for d in defs]})',
            )
        )
        return {"component": name, "transfer_on": [d.name for d in defs]}

    def set_entry_paths(self, name: str, events: list[dict[str, Any]]) -> dict[str, Any]:
        """스킬/에이전트의 **입력 포트**를 정의한다 (어떤 경로로 이 노드에 들어왔는지).

        events 형식은 set_transfer_on과 같다. 전이 쪽에서는 target_port로 지목한다.
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd

        comp = self._find_component(name)
        defs = self._make_event_defs(events)
        self._vm.execute(
            SetAttrCmd(
                comp,
                "entry_paths",
                defs,
                label=f"'{name}' 입력 경로 {len(defs)}개 설정",
                script=f'set_entry_paths("{name}", {[d.name for d in defs]})',
            )
        )
        return {"component": name, "entry_paths": [d.name for d in defs]}

    # --- 블랙보드 ---

    def create_blackboard_class(
        self, name: str, description: str = "", fields: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """프로젝트 블랙보드에 공유 상태 클래스를 만든다.

        fields: [{"name": "frame_ms", "type": "float", "required": true,
                  "collection": "none", "default": null}, ...]
        타입은 string/int/float/bool 4종만 허용된다 — 컨테이너 형상은 collection
        (none/list/set)이 전담한다("문자열 목록" = string × list).
        """
        from daedalus.model.fsm.blackboard import (
            BLACKBOARD_FIELD_TYPES,
            CollectionType,
            DynamicClass,
            DynamicField,
        )
        from daedalus.model.fsm.variable import FieldType
        from daedalus.view.commands.attr_commands import AppendToListCmd

        blackboard = self._project.blackboard
        if any(c.name == name for c in blackboard.class_definitions):
            raise ValueError(f"블랙보드에 '{name}' 클래스가 이미 있습니다.")

        allowed = {t.value: t for t in BLACKBOARD_FIELD_TYPES}
        built: list[Any] = []
        for spec in fields or []:
            fname = spec.get("name")
            if not fname:
                raise ValueError("각 필드에는 name이 필요합니다.")
            raw_type = str(spec.get("type", "string")).lower()
            if raw_type not in allowed:
                raise ValueError(
                    f"필드 '{fname}'의 타입 '{raw_type}'은 블랙보드에서 쓸 수 없습니다. "
                    f"사용 가능: {', '.join(sorted(allowed))}"
                )
            raw_coll = str(spec.get("collection", "none")).lower()
            try:
                collection = CollectionType(raw_coll)
            except ValueError:
                raise ValueError(
                    f"필드 '{fname}'의 collection '{raw_coll}'이 올바르지 않습니다. "
                    "사용 가능: none, list, set"
                ) from None
            built.append(
                DynamicField(
                    name=fname,
                    field_type=FieldType(allowed[raw_type].value),
                    collection=collection,
                    default=spec.get("default"),
                    required=bool(spec.get("required", False)),
                )
            )

        cls = DynamicClass(name=name, description=description, fields=built)
        self._vm.execute(
            AppendToListCmd(
                blackboard.class_definitions,
                cls,
                label=f"블랙보드 클래스 '{name}' 생성",
                script=f'create_blackboard_class("{name}", fields={[f.name for f in built]})',
            )
        )
        self._window._blackboard_panel.set_project(self._project)
        return {"created": name, "fields": [f.name for f in built]}

    def set_state_access(
        self,
        node: str,
        reads: list[str] | None = None,
        writes: list[str] | None = None,
        agent: str = "",
    ) -> dict[str, Any]:
        """캔버스 노드가 읽고 쓰는 블랙보드 경로를 선언한다.

        "클래스" 또는 "클래스.필드" 문자열을 쓴다. 선언하면 캔버스에 📖/✏ 뱃지가
        붙고, 컴파일된 SKILL.md의 절차·블랙보드 단락이 그 클래스로 좁혀진다.
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd
        from daedalus.view.commands.base import MacroCommand

        vm, _ = self._scope(agent)
        svm = self._find_state_vm(node, vm)
        cmds: list[Any] = []
        if reads is not None:
            cmds.append(
                SetAttrCmd(
                    svm.model,
                    "reads",
                    list(reads),
                    label=f"'{node}' 읽기 선언",
                    script=f'set_state_access("{node}", reads={list(reads)})',
                )
            )
        if writes is not None:
            cmds.append(
                SetAttrCmd(
                    svm.model,
                    "writes",
                    list(writes),
                    label=f"'{node}' 쓰기 선언",
                    script=f'set_state_access("{node}", writes={list(writes)})',
                )
            )
        if not cmds:
            return {"node": node, "changed": []}
        vm.execute(
            cmds[0]
            if len(cmds) == 1
            else MacroCommand(children=cmds, description=f"'{node}' 블랙보드 접근 선언")
        )
        return {"node": node, "reads": reads, "writes": writes}

    def disconnect_states(self, source: str, target: str, agent: str = "") -> dict[str, Any]:
        """두 노드 사이의 전이를 지운다."""
        from daedalus.view.commands.transition_commands import DeleteTransitionCmd

        vm, fsm = self._scope(agent)
        src = self._find_state_vm(source, vm)
        matches = [
            tvm
            for tvm in vm.get_transitions_for(src)
            if tvm.source_vm is src and tvm.target_vm.model.name == target
        ]
        if not matches:
            raise ValueError(f"'{source}' → '{target}' 전이가 없습니다.")
        for tvm in matches:
            vm.execute(DeleteTransitionCmd(vm, tvm, fsm=fsm))
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
