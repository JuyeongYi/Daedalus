"""MCP 도구 구현 (WP-MCP) — CC가 Daedalus를 함께 보고 함께 편집하는 표면.

모든 메서드는 **Qt 메인 스레드에서 실행되는 것을 전제**로 한다(service가
MainThreadInvoker로 마샬링한다). 여기서 스레드 안전성을 다시 걱정할 필요는 없다.

편집 도구는 반드시 ``ProjectViewModel.execute``(CommandStack)를 거친다 — 그래야
사용자가 Ctrl+Z로 되돌릴 수 있고, 스크립트 리스너에 사람 편집과 같은 형식으로
남는다. 본문 편집만은 예외적으로 컴포넌트의 QTextDocument에 적용하는데, 이는
본문이 캔버스와 분리된 자체 undo 스택을 갖기 때문이다(WP-BU) — 우회가 아니라
그 스택에 정확히 올리는 경로다.

**아직 노출하지 않은 편집:** 컴포넌트 삭제(`remove_component`의 정리 범위가 넓어
부분 복원 커맨드가 위험하다)와 나머지 프론트매터 필드. 커맨드화되는 대로 합류시킨다
— 커맨드를 만들기만 하면 `service.TOOL_NAMES`에 이름을 더해 노출된다.
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
            # 에이전트 호출 포트 — 에이전트로 가는 전이는 이 포트에서만 나갈 수 있다
            "call_agents": [
                {"name": e.name, "description": getattr(e, "description", "")}
                for e in (getattr(comp, "call_agents", []) or [])
            ],
            # 에이전트의 잠금 계약 카드 — 누가 이 에이전트를 어느 포트로 부르는지
            "caller_contracts": [
                {"title": s.title, "content": getattr(s, "content", "")}
                for s in (getattr(comp, "caller_contracts", []) or [])
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

    def compile_preview(self, name: str, agent: str = "") -> dict[str, Any]:
        """컴포넌트가 어떤 SKILL.md / 에이전트 .md로 컴파일되는지 — 파일은 쓰지 않는다.

        agent를 지정하면 그 에이전트의 로컬 스킬을 미리 본다(로컬 스킬은
        `skills/<agent>--<skill>/SKILL.md`로 나가며 산출 문구가 조금 다르다).
        """
        from daedalus.compiler.emit import compile_agent, compile_skill
        from daedalus.model.plugin.agent import AgentDefinition

        comp = self._find_component(name, agent=agent)
        project = self._project
        if isinstance(comp, AgentDefinition):
            text = compile_agent(comp, project=project)
        else:
            text = compile_skill(comp, local=bool(agent), project=project)
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

    def set_component_description(
        self, name: str, description: str, agent: str = ""
    ) -> dict[str, Any]:
        """컴포넌트 설명을 바꾼다(프론트매터 description)."""
        from daedalus.view.commands.attr_commands import SetAttrCmd

        comp = self._find_component(name, agent=agent)
        old = getattr(comp, "description", "")
        self._vm.execute(
            SetAttrCmd(
                comp,
                "description",
                description,
                label=f"'{name}' 설명 변경",
                script=f'set_component_description("{name}", ...)',
            )
        )
        self._window._registry_panel.set_project(self._project)
        return {"component": name, "old": old, "new": description}

    def set_component_when_to_use(
        self, name: str, when_to_use: str, agent: str = ""
    ) -> dict[str, Any]:
        """컴포넌트의 when_to_use를 바꾼다.

        별도 프론트매터 키가 아니라 컴파일 시 description과 합류한다
        (`<description> Use when <when_to_use>`) — 모델이 이 스킬을 언제 집어야
        하는지 판단하는 문장이다.
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd

        comp = self._find_component(name, agent=agent)
        old = getattr(comp, "when_to_use", "")
        self._vm.execute(
            SetAttrCmd(
                comp,
                "when_to_use",
                when_to_use,
                label=f"'{name}' when_to_use 변경",
                script=f'set_component_when_to_use("{name}", ...)',
            )
        )
        return {"component": name, "old": old, "new": when_to_use}

    def set_project_properties(
        self,
        name: str = "",
        description: str = "",
        version: str = "",
        build_target: str = "",
    ) -> dict[str, Any]:
        """플러그인 매니페스트 속성을 바꾼다 — 빈 값은 "건드리지 않음".

        name은 plugin.json의 플러그인 식별자가 되므로 `^[a-z0-9][a-z0-9-]*$`를
        지켜야 컴파일 게이트를 통과한다(F7에서는 경고 등급).
        build_target: marketplace / local.
        """
        from daedalus.model.plugin.enums import BuildTarget
        from daedalus.view.commands.attr_commands import SetAttrCmd
        from daedalus.view.commands.base import MacroCommand

        project = self._project
        before = {
            "name": project.name,
            "description": project.description,
            "version": project.version,
            "build_target": project.build_target.value,
        }

        cmds: list[Any] = []
        for attr, value in (
            ("name", name),
            ("description", description),
            ("version", version),
        ):
            if value:
                cmds.append(
                    SetAttrCmd(
                        project,
                        attr,
                        value,
                        label=f"프로젝트 {attr} 변경",
                        script=f'set_project_properties({attr}="{value}")',
                    )
                )
        if build_target:
            try:
                target = BuildTarget(build_target.lower())
            except ValueError:
                allowed = ", ".join(t.value for t in BuildTarget)
                raise ValueError(
                    f"알 수 없는 빌드 타깃 '{build_target}'. 사용 가능: {allowed}"
                ) from None
            cmds.append(
                SetAttrCmd(
                    project,
                    "build_target",
                    target,
                    label=f"빌드 타깃 → {target.value}",
                    script=f'set_project_properties(build_target="{target.value}")',
                )
            )

        if not cmds:
            return {"changed": [], **before}
        self._vm.execute(
            cmds[0]
            if len(cmds) == 1
            else MacroCommand(children=cmds, description="프로젝트 속성 변경")
        )
        self._window._update_title()
        return {
            "before": before,
            "name": project.name,
            "description": project.description,
            "version": project.version,
            "build_target": project.build_target.value,
        }

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

    def remove_agent_call(self, skill: str, event: str) -> dict[str, Any]:
        """ProceduralSkill의 에이전트 호출 포트를 제거한다.

        그 포트를 trigger로 쓰는 전이는 **함께 지우지 않는다**(캔버스에서 포트를
        지웠을 때와 같다) — 남은 전이는 `trigger_unknown_event` 경고로 드러나므로,
        결과의 `orphaned_transitions`를 보고 disconnect_states로 정리하라.
        """
        from daedalus.model.plugin.skill import ProceduralSkill
        from daedalus.view.commands.attr_commands import SetAttrCmd

        comp = self._find_component(skill)
        if not isinstance(comp, ProceduralSkill):
            raise ValueError(f"'{skill}'은 ProceduralSkill이 아닙니다.")
        if not any(e.name == event for e in comp.call_agents):
            known = ", ".join(e.name for e in comp.call_agents) or "(없음)"
            raise ValueError(f"'{skill}'에 '{event}' 호출 포트가 없습니다. 현재: {known}")

        orphaned = [
            [tvm.source_vm.model.name, tvm.target_vm.model.name]
            for tvm in self._vm.transition_vms
            if getattr(tvm.source_vm.model, "skill_ref", None) is comp
            and getattr(getattr(tvm.model, "trigger", None), "name", None) == event
        ]
        new_list = [e for e in comp.call_agents if e.name != event]
        self._vm.execute(
            SetAttrCmd(
                comp,
                "call_agents",
                new_list,
                label=f"'{skill}' 에이전트 호출 포트 '{event}' 제거",
                script=f'remove_agent_call("{skill}", "{event}")',
            )
        )
        return {
            "skill": skill,
            "removed": event,
            "call_agents": [e.name for e in new_list],
            "orphaned_transitions": orphaned,
        }

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

    def set_transfer_on(
        self, name: str, events: list[dict[str, Any]], agent: str = ""
    ) -> dict[str, Any]:
        """스킬/에이전트의 **출력 포트**를 정의한다.

        events: [{"name": "gpu", "description": "GPU 병목", "color": "#ff8844"}, ...]
        분기가 여러 갈래인 노드는 여기에 갈래를 선언해야 캔버스 포트가 갈라지고,
        각 전이의 trigger로 어느 갈래인지 지정할 수 있다.
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd

        comp = self._find_component(name, agent=agent)
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

    def set_entry_paths(
        self, name: str, events: list[dict[str, Any]], agent: str = ""
    ) -> dict[str, Any]:
        """스킬/에이전트의 **입력 포트**를 정의한다 (어떤 경로로 이 노드에 들어왔는지).

        events 형식은 set_transfer_on과 같다. 전이 쪽에서는 target_port로 지목한다.
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd

        comp = self._find_component(name, agent=agent)
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

    # --- 훅 라이브러리 ---

    def _find_hook(self, name: str) -> Any:
        for hook in self._project.hook_library:
            if hook.name == name:
                return hook
        known = ", ".join(h.name for h in self._project.hook_library) or "(없음)"
        raise ValueError(f"'{name}' 훅이 없습니다. 현재 라이브러리: {known}")

    @staticmethod
    def _hook_summary(hook: Any) -> dict[str, Any]:
        # 그룹 단위로 만들어야 command 훅의 스크립트 경로가 채워진다 — 핸들러를
        # 개별로 to_json()하면 경로를 모르므로 command가 빈 값으로 나온다.
        group = hook.to_json()
        return {
            "name": hook.name,
            "event": getattr(hook.event, "value", str(hook.event)),
            "matcher": hook.matcher,
            "description": getattr(hook, "description", ""),
            # CC 스키마 그대로의 핸들러 목록 — 이 값이 hooks.json에 그대로 나간다
            "handlers": group["hooks"],
            # 경로만 보면 무엇이 실행되는지 알 수 없다. 스크립트 본문도 함께 준다.
            "scripts": dict(hook.script_files()),
        }

    @staticmethod
    def _build_hook_handler(spec: dict[str, Any]) -> Any:
        """핸들러 스펙(dict) → HookHandler.

        spec의 `type`이 CC 스키마의 다섯 종(command/prompt/agent/http/mcp_tool)
        중 하나를 고른다. 나머지 키는 그 타입의 필드명을 쓰되, CC 산출 키와
        파이썬 필드명이 다른 셋(`if`/`async`/`input`)은 여기서 옮겨 준다.
        """
        from daedalus.model.plugin.hook import HOOK_HANDLER_TYPES, HookShell

        kind = str(spec.get("type", "command"))
        cls = HOOK_HANDLER_TYPES.get(kind)
        if cls is None:
            allowed = ", ".join(sorted(HOOK_HANDLER_TYPES))
            raise ValueError(f"알 수 없는 훅 핸들러 타입 '{kind}'. 사용 가능: {allowed}")

        # CC 산출 키 → 파이썬 필드명 (예약어 회피 때문에 이름이 다르다).
        # `command`는 CC 산출에서 스크립트 **경로**이지만 입력으로는 스크립트
        # **본문**을 받는다(WP-HS) — 커맨드는 아무리 짧아도 파일로 나가고,
        # 경로는 컴파일러가 정한다.
        aliases = {
            "if": "condition",
            "statusMessage": "status_message",
            "async": "run_async",
            "asyncRewake": "async_rewake",
            "continueOnBlock": "continue_on_block",
            "allowedEnvVars": "allowed_env_vars",
            "input": "tool_input",
            "command": "script",
            "scriptName": "script_name",
        }
        from dataclasses import fields as dc_fields

        valid = {f.name for f in dc_fields(cls)} - {"id"}
        kwargs: dict[str, Any] = {}
        for key, value in spec.items():
            if key == "type":
                continue
            attr = aliases.get(key, key)
            if attr not in valid:
                raise ValueError(
                    f"'{kind}' 훅에 '{key}' 속성은 없습니다. "
                    f"사용 가능: {', '.join(sorted(valid))}"
                )
            if attr == "shell":
                try:
                    value = HookShell(str(value))
                except ValueError:
                    raise ValueError("shell은 bash 또는 powershell이어야 합니다.") from None
            kwargs[attr] = value
        return cls(**kwargs)

    def _refresh_hook_ui(self) -> None:
        """훅 이름 후보(HookPresetPicker)를 쓰는 위젯들이 새 목록을 보게 한다."""
        self._vm.notify()

    def create_hook(
        self,
        name: str,
        event: str = "PreToolUse",
        handlers: list[dict[str, Any]] | None = None,
        matcher: str = "",
        description: str = "",
        command: str = "",
    ) -> dict[str, Any]:
        """프로젝트 훅 라이브러리에 훅을 추가한다.

        구조는 CC settings hooks 스키마 그대로다 — 이벤트 + 선택적 matcher +
        핸들러 목록.

        handlers: [{"type": "command", "command": "echo hi", "timeout": 5}, ...]
        핸들러 타입 5종: command(command/scriptName/args/shell/async/asyncRewake) /
        prompt(prompt/model/continueOnBlock) / agent(prompt/model) /
        http(url/headers/allowedEnvVars) / mcp_tool(server/tool/input).
        모든 타입이 timeout, if, statusMessage를 공통으로 받는다.

        **command 훅의 `command`는 스크립트 본문이다**(WP-HS). 아무리 짧아도
        `hooks/scripts/<이름>.sh` 파일로 나가고, hooks.json에는 루트 기반 경로만
        남는다 — 인라인 셸 문자열은 쓰지 않는다. 파일명은 `scriptName`으로 정하고
        비우면 훅 이름에서 만든다.

        command 인자(핸들러 밖)는 편의용 지름길이다 — handlers 대신 주면 command
        핸들러 하나를 만든다.

        event는 CC 훅 이벤트 31종 중 하나(list_hook_events 참조).
        matcher는 이벤트가 받을 때만 의미가 있다. MCP 도구를 매칭하려면
        `mcp__<서버>__<도구>` 형태를 쓰고, 서버 전체는 `mcp__<서버>__.*`처럼
        `.*`를 붙여야 한다 — 서버 이름까지만 쓰면 아무것도 맞지 않는다.

        훅은 라이브러리에 정의만 해 두는 것이고, 실제로 배출되려면
        set_component_hooks로 스킬/에이전트가 이름으로 참조해야 한다.
        """
        from daedalus.model.plugin.hook import MATCHER_EVENTS, HookDef, HookEvent
        from daedalus.view.commands.attr_commands import AppendToListCmd

        library = self._project.hook_library
        if any(h.name == name for h in library):
            raise ValueError(f"'{name}' 훅이 이미 있습니다.")
        try:
            hook_event = HookEvent(event)
        except ValueError:
            allowed = ", ".join(e.value for e in HookEvent)
            raise ValueError(f"알 수 없는 훅 이벤트 '{event}'. 사용 가능: {allowed}") from None

        specs = list(handlers or [])
        if command:
            specs.append({"type": "command", "command": command})
        built = [self._build_hook_handler(s) for s in specs]

        hook = HookDef(
            name=name,
            description=description,
            event=hook_event,
            matcher=matcher,
            handlers=built,
        )
        self._vm.execute(
            AppendToListCmd(
                library,
                hook,
                label=f"훅 '{name}' 추가",
                script=f'create_hook("{name}", event="{hook_event.value}")',
            )
        )
        self._refresh_hook_ui()
        result = self._hook_summary(hook)
        if matcher and hook_event not in MATCHER_EVENTS:
            result["note"] = (
                f"{hook_event.value}는 matcher를 받지 않습니다 — 무시되고 검증 경고가 뜹니다."
            )
        if not built:
            result["note"] = "핸들러가 없어 아무 일도 하지 않습니다 — handlers를 지정하라."
        return result

    def update_hook(
        self,
        name: str,
        event: str = "",
        handlers: list[dict[str, Any]] | None = None,
        matcher: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """라이브러리의 훅 정의를 고친다.

        빈 문자열/None은 "건드리지 않음"이다. matcher와 description은 ""를 주면
        지워진다. handlers를 주면 **목록 전체를 교체**한다(형식은 create_hook 참조).
        """
        from daedalus.model.plugin.hook import HookEvent
        from daedalus.view.commands.attr_commands import SetAttrCmd
        from daedalus.view.commands.base import MacroCommand

        hook = self._find_hook(name)
        before = self._hook_summary(hook)
        cmds: list[Any] = []

        def _set(attr: str, value: Any) -> None:
            cmds.append(
                SetAttrCmd(
                    hook, attr, value,
                    label=f"훅 '{name}' {attr} 변경",
                    script=f'update_hook("{name}", {attr}=...)',
                )
            )

        if event:
            try:
                _set("event", HookEvent(event))
            except ValueError:
                allowed = ", ".join(e.value for e in HookEvent)
                raise ValueError(f"알 수 없는 훅 이벤트 '{event}'. 사용 가능: {allowed}") from None
        if handlers is not None:
            _set("handlers", [self._build_hook_handler(s) for s in handlers])
        if matcher is not None:
            _set("matcher", matcher)
        if description is not None:
            _set("description", description)

        if not cmds:
            return {"changed": [], **before}
        self._vm.execute(
            cmds[0]
            if len(cmds) == 1
            else MacroCommand(children=cmds, description=f"훅 '{name}' 변경")
        )
        self._refresh_hook_ui()
        return {"before": before, **self._hook_summary(hook)}

    def hook_frontmatter_preview(self, names: list[str] | None = None) -> dict[str, Any]:
        """훅을 **서브에이전트 프론트매터 YAML**로 변환해 돌려준다 (WP-HK).

        에이전트가 `.claude/agents/`에서 직접 쓰는 형식이다. 프로젝트 설치 빌드는
        컴파일이 자동으로 넣어 주지만, 이 프로젝트 밖의 에이전트 파일에 손으로
        붙여넣고 싶을 때 쓴다.

        names를 생략하면 라이브러리 전체. hooks.json 형식이 필요하면
        compile_preview 대신 get_project의 hook_library를 보라.
        """
        from daedalus.compiler.emit import _yaml_block_lines
        from daedalus.model.plugin.hook import HookEvent

        library = self._project.hook_library
        wanted = set(names) if names else {h.name for h in library}
        missing = sorted(wanted - {h.name for h in library})
        if missing:
            raise ValueError(f"라이브러리에 없는 훅: {', '.join(missing)}")

        buckets: dict[str, list[dict[str, Any]]] = {}
        for event in HookEvent:  # 선언 순서 = 결정적
            groups = [
                h.to_json()
                for h in library
                if h.event is event and h.name in wanted and h.handlers
            ]
            if groups:
                buckets[event.value] = groups

        if not buckets:
            return {"hooks": [], "yaml": "", "note": "배출할 핸들러가 없습니다."}

        lines = ["hooks:"] + _yaml_block_lines(buckets, 2)
        return {
            "hooks": sorted(wanted),
            "yaml": "\n".join(lines) + "\n",
        }

    def list_hook_events(self) -> dict[str, Any]:
        """CC 훅 이벤트 전체(31종)와 각 이벤트의 matcher 지원 여부.

        어떤 이벤트가 있는지 몰라 짐작으로 create_hook을 부르는 것을 막는다.
        """
        from daedalus.model.plugin.hook import (
            MATCHER_EVENTS,
            UNDOCUMENTED_EVENTS,
            HookEvent,
        )

        return {
            "events": [
                {
                    "name": e.value,
                    "supports_matcher": e in MATCHER_EVENTS,
                    "undocumented": e in UNDOCUMENTED_EVENTS,
                }
                for e in HookEvent
            ],
            "handler_types": ["command", "prompt", "agent", "http", "mcp_tool"],
        }

    def delete_hook(self, name: str) -> dict[str, Any]:
        """라이브러리에서 훅 정의를 지운다.

        이 훅을 참조하는 컴포넌트의 참조는 **건드리지 않는다**(GUI 훅 라이브러리와
        같은 정책) — 남은 참조는 `dangling_hook_ref` 경고로 드러나므로, 결과의
        `still_referenced_by`를 보고 set_component_hooks로 정리하라.
        """
        from daedalus.view.commands.attr_commands import RemoveFromListCmd

        hook = self._find_hook(name)
        referenced = [
            getattr(comp, "name", "?")
            for comp in self._all_hook_owners()
            if name in (getattr(getattr(comp, "config", None), "hooks", {}) or {})
        ]
        self._vm.execute(
            RemoveFromListCmd(
                self._project.hook_library,
                hook,
                label=f"훅 '{name}' 삭제",
                script=f'delete_hook("{name}")',
            )
        )
        self._refresh_hook_ui()
        return {"deleted": name, "still_referenced_by": referenced}

    def _all_hook_owners(self) -> list[Any]:
        """훅을 참조할 수 있는 컴포넌트 전부 — 에이전트 로컬 스킬까지 포함한다."""
        project = self._project
        owners: list[Any] = [*project.skills, *project.agents]
        for agent in project.agents:
            owners.extend(getattr(agent, "skills", []) or [])
        return owners

    # --- 프론트매터 필드 ---

    @staticmethod
    def _config_field_types(config: Any) -> dict[str, Any]:
        """config 클래스의 필드 이름 → 선언 타입.

        `from __future__ import annotations` 때문에 dataclass의 `f.type`은 문자열이라
        쓸 수 없다 — `get_type_hints`로 실제 타입 객체를 얻는다.
        """
        from typing import get_type_hints

        try:
            return get_type_hints(type(config))
        except Exception:  # noqa: BLE001 — 힌트를 못 얻어도 편집은 막지 않는다
            return {}

    @staticmethod
    def _coerce_field_value(target: Any, value: Any, field: str) -> Any:
        """입력 값을 config 필드의 선언 타입으로 맞춘다.

        MCP로 오는 값은 JSON이라 문자열/리스트/불리언뿐이다. enum 필드는 값
        문자열로 받아 멤버로 바꾸고, 틀리면 허용 목록을 알려준다 — 조용히
        문자열이 들어가면 컴파일 산출이 이상해질 때까지 드러나지 않는다.
        """
        import enum
        from typing import get_args, get_origin

        args = [a for a in get_args(target) if a is not type(None)]
        if args:
            target = args[0]
        origin = get_origin(target)

        if origin in (list, set):
            if not isinstance(value, (list, tuple)):
                raise ValueError(f"'{field}'는 목록이어야 합니다.")
            return [str(v) for v in value]
        if isinstance(target, type) and issubclass(target, enum.Enum):
            try:
                return target(value)
            except ValueError:
                allowed = ", ".join(str(m.value) for m in target)
                raise ValueError(
                    f"'{field}'의 값 '{value}'이 올바르지 않습니다. 사용 가능: {allowed}"
                ) from None
        if target is bool:
            return bool(value)
        if target is int:
            return int(value)
        return value

    def list_component_fields(self, name: str, agent: str = "") -> dict[str, Any]:
        """이 컴포넌트가 받는 프론트매터 필드와 현재 값.

        스킬과 에이전트는 받는 필드가 다르고, 스킬은 종류(procedural/declarative/
        transfer/reference)마다 또 다르다. 짐작으로 set_component_field를 부르지
        않도록 실제 목록을 돌려준다. `emit`은 그 필드가 어디로 나가는지다
        (frontmatter / body / settings).
        """
        import enum
        from typing import get_args

        from daedalus.model.plugin.agent import AgentDefinition
        from daedalus.model.plugin.field_matrix import (
            AGENT_FIELD_MATRIX,
            SKILL_FIELD_MATRIX,
        )

        comp = self._find_component(name, agent=agent)
        config = getattr(comp, "config", None)
        if config is None:
            raise ValueError(f"'{name}'에는 config가 없습니다.")

        if isinstance(comp, AgentDefinition):
            matrix = AGENT_FIELD_MATRIX
        else:
            matrix = SKILL_FIELD_MATRIX.get(self._skill_matrix_key(comp, agent), {})

        hints = self._config_field_types(config)
        out: list[dict[str, Any]] = []
        for fld, rule in matrix.items():
            attr = fld.value
            if not hasattr(config, attr):
                continue
            current = getattr(config, attr)
            entry: dict[str, Any] = {
                "field": attr,
                "frontmatter_key": fld.frontmatter_key,
                "emit": rule.emit.value,
                "visibility": rule.visibility.value,
                "current": getattr(current, "value", current),
            }
            target = hints.get(attr)
            args = [a for a in get_args(target) if a is not type(None)]
            base = args[0] if args else target
            if isinstance(base, type) and issubclass(base, enum.Enum):
                entry["choices"] = [str(m.value) for m in base]
            out.append(entry)
        return {"component": comp.name, "kind": self._component_kind(comp), "fields": out}

    @staticmethod
    def _skill_matrix_key(comp: Any, agent: str) -> str:
        """SKILL_FIELD_MATRIX의 키 — 로컬 스킬은 local_ 접두를 쓴다."""
        kind = str(getattr(comp, "kind", "")).replace("_skill", "")
        if agent and kind in ("procedural", "transfer"):
            return f"local_{kind}"
        return kind

    def set_component_field(
        self, name: str, field: str, value: Any, agent: str = ""
    ) -> dict[str, Any]:
        """스킬/에이전트 프론트매터 필드 하나를 설정한다.

        field는 `list_component_fields`가 돌려주는 이름(model / tools /
        permission_mode / allowed_tools / …). value는 JSON 값이며 enum 필드는 값
        문자열로 준다(예: model="sonnet", permission_mode="acceptEdits").
        목록 필드는 배열로 준다.

        description / when_to_use / hooks는 전용 도구를 쓴다.
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd

        comp = self._find_component(name, agent=agent)
        config = getattr(comp, "config", None)
        if config is None:
            raise ValueError(f"'{name}'에는 config가 없습니다.")
        if field == "hooks":
            raise ValueError("훅 참조는 set_component_hooks를 쓰세요.")
        if not hasattr(config, field):
            known = [
                f["field"] for f in self.list_component_fields(name, agent=agent)["fields"]
            ]
            raise ValueError(
                f"'{self._component_kind(comp)}'에는 '{field}' 필드가 없습니다. "
                f"사용 가능: {', '.join(known)}"
            )

        hints = self._config_field_types(config)
        coerced = self._coerce_field_value(hints.get(field), value, field)
        old = getattr(config, field)
        self._vm.execute(
            SetAttrCmd(
                config,
                field,
                coerced,
                label=f"'{name}' {field} 변경",
                script=f'set_component_field("{name}", "{field}", ...)',
            )
        )
        return {
            "component": comp.name,
            "field": field,
            "old": getattr(old, "value", old),
            "new": getattr(coerced, "value", coerced),
        }

    def set_component_hooks(
        self, name: str, hooks: list[str], agent: str = ""
    ) -> dict[str, Any]:
        """스킬/에이전트가 참조하는 훅 이름 목록을 통째로 지정한다.

        라이브러리에 없는 이름은 거부한다 — 오타는 컴파일까지 조용히 흘러가
        `dangling_hook_ref` 경고로만 드러나기 때문이다.
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd

        comp = self._find_component(name, agent=agent)
        config = getattr(comp, "config", None)
        if config is None:
            raise ValueError(f"'{name}'에는 config가 없어 훅을 붙일 수 없습니다.")

        known = {h.name for h in self._project.hook_library}
        unknown = [h for h in hooks if h not in known]
        if unknown:
            raise ValueError(
                f"라이브러리에 없는 훅: {', '.join(unknown)}. "
                f"사용 가능: {', '.join(sorted(known)) or '(없음)'}"
            )

        # 기존 오버라이드는 유지한다 — 이름만 다시 지정하는 것이 이 도구의 일이다
        current = dict(getattr(config, "hooks", {}) or {})
        new_map = {h: current.get(h, {}) for h in hooks}
        self._vm.execute(
            SetAttrCmd(
                config,
                "hooks",
                new_map,
                label=f"'{name}' 훅 참조 {len(hooks)}개 설정",
                script=f'set_component_hooks("{name}", {list(hooks)})',
            )
        )
        return {"component": name, "hooks": list(new_map)}

    # --- 참조 노드 (ReferenceSkill 배치) ---

    @property
    def _scene(self) -> Any:
        scene = getattr(self._window, "_fsm_scene", None)
        if scene is None:
            raise RuntimeError("프로젝트 캔버스가 준비되지 않았습니다.")
        return scene

    def _find_ref_vm(self, name: str, index: int = 0) -> Any:
        matches = [
            rvm
            for rvm in self._vm.reference_vms
            if getattr(rvm.model, "name", None) == name
        ]
        if not matches:
            raise ValueError(f"캔버스에 '{name}' 참조 노드가 없습니다.")
        if index >= len(matches):
            raise ValueError(
                f"'{name}' 참조 노드는 {len(matches)}개뿐입니다(index={index} 초과)."
            )
        return matches[index]

    def place_reference(self, name: str, x: float = 0.0, y: float = 0.0) -> dict[str, Any]:
        """ReferenceSkill을 프로젝트 캔버스에 참조 노드로 배치한다.

        참조 노드는 상태가 아니라 **여러 상태가 공유하는 문서**라, 같은 스킬을
        여러 번 놓을 수 있다(그래서 place_component가 아니라 별도 도구다).
        놓은 뒤 link_reference로 상태에 연결한다.
        """
        from PySide6.QtCore import QPointF

        from daedalus.model.plugin.skill import ReferenceSkill

        comp = self._find_component(name)
        if not isinstance(comp, ReferenceSkill):
            raise ValueError(
                f"'{name}'은 ReferenceSkill이 아닙니다(현재 {self._component_kind(comp)}) — "
                "일반 스킬·에이전트는 place_component로 배치하라."
            )
        before = len(self._vm.reference_vms)
        self._scene.drop_reference_skill(name, QPointF(float(x), float(y)))
        if len(self._vm.reference_vms) == before:
            raise RuntimeError(f"'{name}' 참조 노드를 배치하지 못했습니다.")
        return {
            "placed": name,
            "index": sum(
                1 for r in self._vm.reference_vms if getattr(r.model, "name", None) == name
            ) - 1,
            "x": float(x),
            "y": float(y),
        }

    def link_reference(self, node: str, reference: str, index: int = 0) -> dict[str, Any]:
        """캔버스 노드를 참조 노드에 잇는다(그 노드가 이 문서를 참조한다는 선언).

        같은 참조 스킬이 여러 번 배치돼 있으면 index로 고른다.
        """
        svm = self._find_state_vm(node)
        rvm = self._find_ref_vm(reference, index)
        before = len(self._vm.reference_links)
        self._scene.create_reference_link(svm, rvm)
        created = len(self._vm.reference_links) > before
        return {"node": node, "reference": reference, "created": created}

    def unlink_reference(self, node: str, reference: str, index: int = 0) -> dict[str, Any]:
        """노드와 참조 노드 사이의 연결을 끊는다(참조 노드 자체는 남는다)."""
        svm = self._find_state_vm(node)
        rvm = self._find_ref_vm(reference, index)
        matches = [
            link
            for link in self._vm.reference_links
            if link.state_vm is svm and link.reference_vm is rvm
        ]
        if not matches:
            raise ValueError(f"'{node}' → '{reference}' 참조 연결이 없습니다.")
        for link in matches:
            self._scene.delete_reference_link(link)
        return {"unlinked": [node, reference], "count": len(matches)}

    def unplace_reference(self, name: str, index: int = 0) -> dict[str, Any]:
        """참조 노드를 캔버스에서 제거한다(연결된 링크도 함께 — 1 undo 단위).

        스킬 자체는 남는다 — 배치만 지운다.
        """
        rvm = self._find_ref_vm(name, index)
        links = sum(1 for l in self._vm.reference_links if l.reference_vm is rvm)
        self._scene.delete_reference_node(rvm)
        return {"unplaced": name, "index": index, "removed_links": links}

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

    def set_component_body(self, name: str, body: str, agent: str = "") -> dict[str, Any]:
        """컴포넌트 본문을 교체한다.

        본문은 캔버스와 분리된 자체 undo 스택을 쓰므로(WP-BU) 그 문서에 적용한다 —
        에디터가 열려 있으면 화면에 즉시 반영되고, 편집기에서 Ctrl+Z로 되돌릴 수 있다.

        agent를 지정하면 그 에이전트의 로컬 스킬 본문을 고친다.
        """
        from PySide6.QtGui import QTextCursor

        from daedalus.view.editors import body_documents

        comp = self._find_component(name, agent=agent)
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
