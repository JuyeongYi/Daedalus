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
from .placement_prose import kinds_with_placement, placement_role_prose


class CanvasTools(_BaseTools):
    """프로젝트 캔버스의 구조 편집 — 전부 CommandStack 경유."""

    def place_component(
        self, name: str, x: float = 0.0, y: float = 0.0
    ) -> dict[str, Any]:
        """스킬/에이전트를 캔버스에 **상태 노드로** 배치한다.

        배치 가능 판정의 실체는 `model/plugin/placement.is_state_placeable`
        하나다(캔버스 드롭·레지스트리·"여기에 만들기"와 공용) — 표면마다
        음성 목록을 따로 들면 MCP만 조용히 엉뚱한 노드를 만든다(원칙 1·5).

        **이미 배치된 컴포넌트는 거부한다** — 캔버스 드롭의 "이미 배치됨" 조기
        반환과 같은 가드다. 두 번 놓으면 `no_duplicate_skill_ref`로 프로젝트가
        컴파일되지 않는다.
        """
        from daedalus.model.fsm.state import SimpleState
        from daedalus.model.plugin.placement import (
            is_reference_placed,
            is_state_placeable,
        )
        from daedalus.view.commands.state_commands import CreateStateCmd
        from daedalus.view.viewmodel.state_vm import StateViewModel

        vm, fsm = self._scope()
        comp = self._find_component(name)
        if not is_state_placeable(comp):
            if is_reference_placed(comp):
                raise ValueError(
                    f"'{comp.name}'은(는) 참조로 배치되는 종류라 상태 노드가 "
                    f"될 수 없습니다 — 참조 노드는 place_reference로 놓습니다."
                )
            # 거절 문구도 **배치 역할 선언**에서 파생한다(P5) — 종류 이름을
            # 손으로 열거하면 새 종류가 생기는 날 문구가 거짓말을 한다(거절은
            # 되는데 이유가 다른 종류의 설명이다).
            role = comp.effective_placement()
            others = ", ".join(kinds_with_placement(role))
            raise ValueError(
                f"'{comp.name}'({comp.kind})은(는) 캔버스에 배치되지 않는 "
                f"종류입니다 — {placement_role_prose(role)}. 같은 배치 역할인 "
                f"종류: {others or '(없음)'}."
            )
        # 이미 배치된 컴포넌트는 두 번 놓지 않는다 — 캔버스 드롭의 조기 반환과
        # 같은 가드다(`view/canvas/scene.py`). 없으면 MCP만 같은 스킬을 두 노드로
        # 놓아 프로젝트가 `no_duplicate_skill_ref`로 컴파일 불가가 된다 — 캔버스는
        # 조용히 무시하지만 MCP는 이유를 말하고 거부한다(원칙 5).
        for svm in vm.state_vms:
            if getattr(svm.model, "skill_ref", None) is comp:
                raise ValueError(
                    f"'{comp.name}'은(는) 이미 노드 '{svm.model.name}'으로 "
                    f"배치돼 있습니다 — 옮기려면 move_state를 씁니다."
                )
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
        출발은 호출 포트를 가질 수 있는 컴포넌트면 된다 — 단계 스킬, 그리고
        **에이전트**(2026-09-12 — CC 중첩 스폰 허용). 깊이·모델
        티어 제약은 검증이 짚는다(agent_chain_too_deep/agent_calls_higher_model).

        **두 질문을 다른 술어로 묻는다.** 출발이 호출 포트를 가질 수 있는가는
        `is_state_placeable`(단일 배치 노드인가 — 포트 도구와 같은 실체)이고,
        도착이 "위임 대상"인가는 `DELEGATION_TARGET` 선언이다(WP-2d). 도착에도
        배치 판정을 쓰면 스킬 대상에도 True가 되어 **모든 스킬 간 전이가 호출
        포트를 요구**하게 된다. fork 에이전트는 선언상 위임 대상이지만 애초에
        노드가 될 수 없어 `_find_state_vm`에서 "그런 노드가 없다"로 먼저 걸린다.
        """
        from daedalus.model.fsm.transition import Transition
        from daedalus.model.plugin.placement import is_state_placeable
        from daedalus.view.commands.transition_commands import CreateTransitionCmd
        from daedalus.view.viewmodel.state_vm import TransitionViewModel

        vm, fsm = self._scope()
        src = self._find_state_vm(source, vm)
        tgt = self._find_state_vm(target, vm)
        src_ref = getattr(src.model, "skill_ref", None)
        tgt_ref = getattr(tgt.model, "skill_ref", None)
        # 호출 포트를 가질 수 있는가 — `PortTools._require_call_port_owner`와
        # **같은 술어**(단일 배치 노드인가)를 쓴다(원칙 1).
        src_has_call_ports = is_state_placeable(src_ref)
        # 이 노드로 가는 전이가 "위임"인가 — 종류가 아니라 선언이 답한다(Q9).
        tgt_is_delegation = tgt_ref is not None and tgt_ref.DELEGATION_TARGET

        is_agent_call = False
        if tgt_is_delegation:
            if not src_has_call_ports:
                raise ValueError(
                    f"에이전트 '{target}'은 호출 포트를 가진 컴포넌트에서만 호출할 수 "
                    f"있습니다 — 단계 스킬, 에이전트."
                )
            if not trigger:
                raise ValueError(
                    f"에이전트 '{target}'으로의 연결에는 호출 포트 이름이 필요합니다. "
                    f'add_agent_call("{source}", "<포트명>") 으로 포트를 먼저 만들고 '
                    "trigger로 지정하세요."
                )
            ports = src_ref.call_ports()
            if not any(e.name == trigger for e in ports):
                have = ", ".join(e.name for e in ports) or "(없음)"
                raise ValueError(
                    f"'{source}'에 '{trigger}' 에이전트 호출 포트가 없습니다(현재: {have}). "
                    f'add_agent_call("{source}", "{trigger}") 로 먼저 만드세요.'
                )
            is_agent_call = True
        elif trigger and src_has_call_ports:
            # call_agent 포트는 에이전트로만 나갈 수 있다 (캔버스와 같은 규칙)
            if any(e.name == trigger for e in src_ref.call_ports()):
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
        create_transfer: str | None = None,
    ) -> dict[str, Any]:
        """이미 있는 전이에 트리거·가드·transfer 스킬을 설정한다.

        None을 넘긴 항목은 건드리지 않는다. 빈 문자열("")을 넘기면 그 항목을 지운다.
        transfer는 전이 도중 실행할 TransferSkill의 이름이다 — 라이브러리에 없는
        이름은 후보를 나열하며 거부한다(오타가 조용히 None이 되는 것 방지).

        create_transfer(G15): 그 이름의 **TransferSkill을 새로 만들어** 이 전이에
        붙인다 — 캔버스 엣지 메뉴의 "새 Transfer Skill 생성..."과 같은 커맨드
        조립이라 생성과 할당이 **1 undo 단위**다(따로 만들어 붙이면 Ctrl+Z가 두
        번 필요하고 중간에 고아 스킬이 남는 상태를 거친다). 이미 있는 이름은
        거부한다. `transfer`와 함께 줄 수 없다(같은 자리를 두 번 정한다).
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd
        from daedalus.view.commands.base import MacroCommand

        vm, _ = self._scope()
        tvm = self._find_transition_vm(source, target, vm)
        trans = tvm.model
        cmds: list[Any] = []
        if create_transfer is not None:
            if transfer is not None:
                raise ValueError(
                    "transfer와 create_transfer는 함께 줄 수 없습니다 — "
                    "기존 스킬을 붙이거나(transfer) 새로 만들거나(create_transfer) 하나만."
                )
            cmds.extend(self._create_transfer_commands(create_transfer, tvm))
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
            "transfer": create_transfer if create_transfer is not None else transfer,
            "created_transfer": create_transfer,
        }

    def _create_transfer_commands(self, name: str, tvm: Any) -> list[Any]:
        """TransferSkill 생성 + 이 전이에 할당 (G15) — 씬과 같은 커맨드 조립.

        `FsmScene._create_and_assign_transfer_skill`은 이름을 모달로 묻는 부분과
        커맨드 조립이 한 몸이라 그대로 부를 수 없다 — 대신 **같은 두 커맨드**
        (`AddSkillToProjectCmd` → `SetTransitionSkillRefCmd`)를 쓴다. FSM 팩토리도
        레지스트리·캔버스 생성 경로와 같은 `window._make_fsm`이다.
        """
        from daedalus.model.plugin.skill import TransferSkill
        from daedalus.view.commands.transition_commands import (
            AddSkillToProjectCmd,
            SetTransitionSkillRefCmd,
        )

        if not name.strip():
            raise ValueError("create_transfer 이름이 비어 있습니다.")
        name = name.strip()
        self._reject_duplicate_name(name)
        skill = TransferSkill(
            fsm=self._window._make_fsm(name), name=name, description=""
        )
        return [
            AddSkillToProjectCmd(self._project, skill),
            SetTransitionSkillRefCmd(tvm, skill),
        ]

    def _find_transfer_skill(self, name: str) -> Any:
        """이름으로 전이 스킬을 찾는다 — 없으면 후보 나열 거부.

        "전이 스킬인가"는 **엣지에 붙는 배치 역할인가**로 묻는다(WP-2d) —
        캔버스 엣지 메뉴·검증과 같은 술어다.
        """
        from daedalus.model.plugin.placement import is_edge_placeable

        transfers = [s for s in self._project.skills if is_edge_placeable(s)]
        for skill in transfers:
            if skill.name == name:
                return skill
        known = ", ".join(s.name for s in transfers) or "(없음)"
        raise ValueError(
            f"TransferSkill '{name}'이 없습니다. 사용 가능: {known} — "
            f"create_skill(kind=\"transfer\")로 먼저 만드세요."
        )

    # --- 참조 노드 (ReferenceSkill 배치) ---
    #
    # `_scene`은 `_base.py`가 소유한다 — PropsTools의 생성+배치(G14)도 같은 씬을
    # 쓰므로 한쪽 믹스인에 두면 합성 순서에 기대는 호출이 된다.

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
        """참조 문서를 프로젝트 캔버스에 참조 노드로 배치한다.

        대상은 **참조로 배치되는 종류**다(판정의 단일 진실은
        `placement.is_reference_placed`). 참조 노드는 상태가 아니라 **여러
        상태가 공유하는 문서**라, 같은 스킬을 여러 번 놓을 수 있다(그래서
        place_component가 아니라 별도 도구다). 놓은 뒤 link_reference로 상태에
        연결한다.
        """
        from PySide6.QtCore import QPointF

        from daedalus.model.plugin.placement import is_reference_placed

        comp = self._find_component(name)
        if not is_reference_placed(comp):
            raise ValueError(
                f"'{name}'은 참조 문서가 아닙니다(현재 {comp.kind}) — "
                "일반 스킬·에이전트는 place_component로 배치하세요."
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

    def move_reference(
        self, name: str, x: float, y: float, index: int = 0
    ) -> dict[str, Any]:
        """참조 노드를 옮긴다 (G13) — `move_state`의 짝.

        같은 참조 스킬이 여러 번 배치돼 있으면 index로 고른다(`place_reference`가
        돌려주는 index, `get_project`의 references에도 있다). 캔버스 드래그와 같은
        `MoveRefCmd`라 모델 `reference_placements` 좌표까지 sync되고 undo된다.
        """
        from daedalus.view.commands.reference_commands import MoveRefCmd

        rvm = self._find_ref_vm(name, index)
        old_x, old_y = rvm.x, rvm.y
        self._vm.execute(
            MoveRefCmd(
                rvm,
                old_x=old_x, old_y=old_y,
                new_x=float(x), new_y=float(y),
                sync_fn=self._scene._sync_refs_to_model,
            )
        )
        return {
            "moved": name,
            "index": index,
            "from": [old_x, old_y],
            "to": [float(x), float(y)],
        }

    def set_transition_waypoints(
        self, source: str, target: str, points: list[list[float]] | None = None
    ) -> dict[str, Any]:
        """전이의 경유점(WP-ER)을 **통째로 교체**한다 (G10) — 소스→타깃 순서.

        points: `[[x, y], ...]`. 생략하거나 빈 목록이면 전부 지운다(직선 복원 —
        캔버스 엣지 메뉴의 "경유점 모두 제거"와 같다).

        캔버스는 추가·드래그·제거를 하나씩 하지만 MCP로 좌표를 하나씩 넣는 것은
        의미가 없으므로 여기서는 **교체 1종만** 낸다 — 기존
        `ClearWaypointsCmd`+`AddWaypointCmd`를 `MacroCommand`로 묶어 1 undo 단위다
        (새 커맨드를 만들면 캔버스 조작과 되돌림 단위가 어긋난다).
        읽기는 `get_project`의 전이 요약 `waypoint_count`다.
        """
        from daedalus.view.commands.base import MacroCommand
        from daedalus.view.commands.transition_commands import (
            AddWaypointCmd,
            ClearWaypointsCmd,
        )

        vm, _ = self._scope()
        tvm = self._find_transition_vm(source, target, vm)
        coords: list[tuple[float, float]] = []
        for i, point in enumerate(points or []):
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise ValueError(
                    f"points[{i}]는 [x, y] 두 값이어야 합니다 (받은 값: {point!r})."
                )
            coords.append((float(point[0]), float(point[1])))

        before = len(tvm.waypoints)
        cmds: list[Any] = []
        if tvm.waypoints:
            cmds.append(ClearWaypointsCmd(tvm))
        cmds.extend(
            AddWaypointCmd(tvm, i, cx, cy) for i, (cx, cy) in enumerate(coords)
        )
        if cmds:
            vm.execute(
                cmds[0]
                if len(cmds) == 1
                else MacroCommand(
                    children=cmds,
                    description=f"전이 '{source}→{target}' 경유점 {len(coords)}개 설정",
                )
            )
        return {
            "transition": [source, target],
            "waypoints": [list(p) for p in tvm.waypoints],
            "removed": before,
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
