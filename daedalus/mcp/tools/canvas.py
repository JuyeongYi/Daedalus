# daedalus/mcp/tools/canvas.py
"""캔버스 구조 편집 — 배치/상태/전이/참조 노드 (WP-RF-3b).

**계층: GUI 어댑터다 (WP-RF-2 명시).** core(model/compiler)가 아니라
MainWindow·ProjectViewModel·CommandStack·body_documents 등 view 표면에 결합된
코드로, core 경계 계약(tests/test_import_contracts.py)의 대상이 아니다.
모든 메서드는 **Qt 메인 스레드에서 실행되는 것을 전제**로 한다(service가
MainThreadInvoker로 마샬링한다). 편집 도구는 반드시
``ProjectViewModel.execute``(CommandStack)를 거친다 — 사용자가 Ctrl+Z로
되돌릴 수 있어야 한다.

에이전트 호출은 캔버스와 같은 규칙을 강제한다(WP-CE) — 에이전트 노드 입력은
call_agent 포트에서만, call_agent 포트는 에이전트로만.
"""
from __future__ import annotations

from typing import Any

from ._base import _BaseTools


class CanvasTools(_BaseTools):
    """프로젝트 캔버스의 구조 편집 — 전부 CommandStack 경유."""

    def place_component(
        self, name: str, x: float = 0.0, y: float = 0.0
    ) -> dict[str, Any]:
        """스킬/에이전트를 캔버스에 배치한다."""
        from daedalus.model.fsm.state import SimpleState
        from daedalus.view.commands.state_commands import CreateStateCmd
        from daedalus.view.viewmodel.state_vm import StateViewModel

        vm, fsm = self._scope()
        comp = self._find_component(name)
        state = SimpleState(name=comp.name, skill_ref=comp)
        svm = StateViewModel(model=state, x=float(x), y=float(y))
        vm.execute(CreateStateCmd(vm, svm, fsm=fsm))
        return {
            "placed": comp.name,
            "node": state.name,
            "x": float(x),
            "y": float(y),
        }

    def create_state(
        self, name: str, x: float = 0.0, y: float = 0.0
    ) -> dict[str, Any]:
        """컴포넌트가 붙지 않은 빈 상태 노드를 만든다."""
        from daedalus.model.fsm.state import SimpleState
        from daedalus.view.commands.state_commands import CreateStateCmd
        from daedalus.view.viewmodel.state_vm import StateViewModel

        vm, fsm = self._scope()
        state = SimpleState(name=name)
        svm = StateViewModel(model=state, x=float(x), y=float(y))
        vm.execute(CreateStateCmd(vm, svm, fsm=fsm))
        return {"created": name, "x": float(x), "y": float(y)}

    def move_state(self, name: str, x: float, y: float) -> dict[str, Any]:
        """노드를 옮긴다."""
        from daedalus.view.commands.state_commands import MoveStateCmd

        vm, _ = self._scope()
        svm = self._find_state_vm(name, vm)
        old_x, old_y = svm.x, svm.y
        vm.execute(MoveStateCmd(svm, old_x, old_y, float(x), float(y)))
        return {"moved": name, "from": [old_x, old_y], "to": [float(x), float(y)]}

    def rename_state(self, name: str, new_name: str) -> dict[str, Any]:
        """노드 이름을 바꾼다(캔버스 노드 이름 — 컴포넌트 이름과는 별개)."""
        from daedalus.view.commands.state_commands import RenameStateCmd

        vm, _ = self._scope()
        svm = self._find_state_vm(name, vm)
        vm.execute(RenameStateCmd(svm, name, new_name))
        return {"renamed": name, "to": new_name}

    def delete_state(self, name: str) -> dict[str, Any]:
        """노드와 그에 연결된 전이를 함께 지운다(1 undo 단위)."""
        from daedalus.view.commands.base import MacroCommand
        from daedalus.view.commands.state_commands import DeleteStateCmd
        from daedalus.view.commands.transition_commands import DeleteTransitionCmd

        vm, fsm = self._scope()
        svm = self._find_state_vm(name, vm)
        children: list[Any] = [
            DeleteTransitionCmd(vm, tvm, fsm=fsm) for tvm in vm.get_transitions_for(svm)
        ]
        removed = len(children)
        children.append(DeleteStateCmd(vm, svm, fsm=fsm))
        vm.execute(MacroCommand(children=children, description=f"상태 '{name}' 삭제"))
        return {"deleted": name, "removed_transitions": removed}

    def connect_states(
        self,
        source: str,
        target: str,
        trigger: str = "",
        guard: str = "",
    ) -> dict[str, Any]:
        """두 노드를 전이로 잇는다.

        trigger: 출발 스킬의 출력 이벤트(transfer_on) 또는 에이전트 호출 포트
        (call_agents) 이름. 분기가 여러 갈래일 때 이 값이 있어야 어느 경로인지
        표현되고 캔버스 포트도 갈라진다. 이 갈래가 무엇을 뜻하는지는 출발 스킬의
        transfer_on description에 적는다 — 도착 쪽 입력 포트 선언은 없다(WP-IP).
        guard: 전이 조건 서술(LLM이 판정할 자연어). 빈 값이면 가드 없음.

        **에이전트 노드로 가는 전이는 반드시 call_agent 포트에서 나가야 한다** —
        캔버스와 같은 규칙이다. 호출 계약은 컴파일러가 그래프(호출 포트 + 전이)
        에서 유도하므로 에이전트 쪽에 따로 입력할 것이 없다(WP-CT).
        """
        from daedalus.model.fsm.transition import Transition
        from daedalus.model.plugin.agent import AgentDefinition
        from daedalus.model.plugin.skill import ProceduralSkill
        from daedalus.view.commands.transition_commands import CreateTransitionCmd
        from daedalus.view.viewmodel.state_vm import TransitionViewModel

        vm, fsm = self._scope()
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
        tvm = TransitionViewModel(model=trans, source_vm=src, target_vm=tgt)

        # WP-CT — 계약 카드 자동 생성은 퇴역했다(캔버스와 동일). 호출 계약은
        # 컴파일러가 그래프(호출 포트 + 전이)에서 유도한다.
        vm.execute(CreateTransitionCmd(vm, tvm, fsm=fsm))
        return {
            "connected": [source, target],
            "trigger": trigger or None,
            "guard": guard or None,
            "agent_call": is_agent_call,
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
        transfer: str | None = None,
    ) -> dict[str, Any]:
        """이미 있는 전이에 트리거·가드·transfer 스킬을 설정한다.

        None을 넘긴 항목은 건드리지 않는다. 빈 문자열("")을 넘기면 그 항목을 지운다.
        transfer는 전이 도중 실행할 TransferSkill의 이름이다 — 라이브러리에 없는
        이름은 후보를 나열하며 거부한다(오타가 조용히 None이 되는 것 방지).
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd
        from daedalus.view.commands.base import MacroCommand

        vm, _ = self._scope()
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
        if transfer is not None:
            cmds.append(
                SetAttrCmd(
                    trans,
                    "skill_ref",
                    self._find_transfer_skill(transfer) if transfer else None,
                    label=f"전이 '{source}→{target}' transfer: {transfer or '(해제)'}",
                    script=f'set_transition("{source}", "{target}", transfer="{transfer}")',
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
            "transfer": transfer,
        }

    def _find_transfer_skill(self, name: str) -> Any:
        """이름으로 전역 TransferSkill을 찾는다 — 없으면 후보 나열 거부."""
        from daedalus.model.plugin.skill import TransferSkill

        transfers = [
            s for s in self._project.skills if isinstance(s, TransferSkill)
        ]
        for skill in transfers:
            if skill.name == name:
                return skill
        known = ", ".join(s.name for s in transfers) or "(없음)"
        raise ValueError(
            f"TransferSkill '{name}'이 없습니다. 사용 가능: {known} — "
            f"create_skill(kind=\"transfer\")로 먼저 만드세요."
        )

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

    def disconnect_states(self, source: str, target: str) -> dict[str, Any]:
        """두 노드 사이의 전이를 지운다."""
        from daedalus.view.commands.transition_commands import DeleteTransitionCmd

        vm, fsm = self._scope()
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
