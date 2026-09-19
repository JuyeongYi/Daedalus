# daedalus/mcp/tools/ports.py
"""포트 도구 — 출력 포트(transfer_on)와 에이전트 호출 포트(call_agents) (WP-RF-3b).

**계층: GUI 어댑터다 (WP-RF-2 명시).** core(model/compiler)가 아니라
MainWindow·ProjectViewModel·CommandStack·body_documents 등 view 표면에 결합된
코드로, core 경계 계약(tests/test_import_contracts.py)의 대상이 아니다.
모든 메서드는 **Qt 메인 스레드에서 실행되는 것을 전제**로 한다(service가
MainThreadInvoker로 마샬링한다). 편집 도구는 반드시
``ProjectViewModel.execute``(CommandStack)를 거친다 — 사용자가 Ctrl+Z로
되돌릴 수 있어야 한다.

구조(노드+선)만 만들면 분기가 표현되지 않는다 — 여러 갈래로 나가는 노드는
transfer_on에 갈래를 선언하고 각 전이에 trigger를 물려야 캔버스 포트가
갈라지고 라벨이 보인다.
"""
from __future__ import annotations

from typing import Any

from ._base import _BaseTools


def _usage_escape_hatch(comp: Any) -> str:
    """포트 거절에 덧붙이는 **빠져나갈 길** — 지금 참조 용도인 컴포넌트에만.

    거절은 이유와 대안을 함께 말해야 한다(원칙 5). 종류 이름만 돌려주면
    "wrapped_skill인데 랩핑 스킬은 포트를 갖는다고 적혀 있다"는 자기모순으로
    읽힌다 — 포트를 막는 것은 **종류가 아니라 이 인스턴스의 용도**다.
    """
    from daedalus.model.plugin.placement import is_reference_placed
    from daedalus.model.plugin.roles import BodySource

    # 용도 스위치를 가진 종류는 오늘 랩핑 스킬 하나뿐이다 — 본문 정본이
    # 외부인 스킬(`BODY_SOURCE`)로 좁힌다. 참조 스킬(REFERENCE지만 정본이
    # 자기 것)에게 `set_wrapped_usage`를 권하면 없는 길을 가리킨다.
    # 배치 역할 비교는 손으로 적지 않는다 — 이름 붙은 술어가 실체다(원칙 1).
    if (
        is_reference_placed(comp)
        and getattr(type(comp), "BODY_SOURCE", None) is BodySource.EXTERNAL
    ):
        name = getattr(comp, "name", "")
        return (
            f" 이 컴포넌트는 지금 **참조 용도**로 고정돼 있습니다 — "
            f'set_wrapped_usage("{name}", "state")로 바꾸면 포트를 가질 수 있습니다.'
        )
    return ""


class PortTools(_BaseTools):
    """포트 (출력 이벤트 / 에이전트 호출 포트)."""

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
        self, name: str, events: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """스킬/에이전트의 **출력 포트**를 정의한다.

        events: [{"name": "gpu", "description": "GPU 병목", "color": "#ff8844"}, ...]
        분기가 여러 갈래인 노드는 여기에 갈래를 선언해야 캔버스 포트가 갈라지고,
        각 전이의 trigger로 어느 갈래인지 지정할 수 있다.

        **출력 포트를 갖는 것은 "단일 배치되는 노드"다**(WP-2d) — 워크플로
        단계로 한 번 놓이는 컴포넌트만 갈래를 선언할 의미가 있다. 참조 용도로
        고정된 랩핑 스킬·참조 스킬·배경 스킬·전이 스킬·fork 에이전트는 전부
        여기서 걸린다. 가드가 없으면 `SetAttrCmd`의 `getattr(..., None)` 폴백
        때문에 없는 필드가 인스턴스 속성으로 생기고, 성공 응답이 돌아간 뒤
        저장 한 번에 사라진다(원칙 5 — 조용한 실패 금지).
        """
        from daedalus.model.plugin.placement import is_state_placeable
        from daedalus.view.commands.attr_commands import SetAttrCmd

        comp = self._find_component(name)
        if not is_state_placeable(comp):
            raise ValueError(
                f"'{name}'({comp.kind})은(는) 출력 포트를 갖지 않습니다 — "
                "출력 포트는 워크플로 단계로 배치되는 컴포넌트(단계 스킬·"
                "state 용도 랩핑 스킬·워크플로 에이전트)만 갖습니다."
                + _usage_escape_hatch(comp)
            )
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

    @staticmethod
    def _require_call_port_owner(comp: Any, name: str) -> Any:
        """에이전트 호출 포트를 가질 수 있는 컴포넌트인지 확인하고 그대로 돌려준다.

        단계 스킬(절차형·fork 2종)·state 용도 랩핑 스킬·**워크플로 에이전트**
        (2026-09-12 — CC 중첩 스폰 허용)가 대상이다. 선언적/참조 스킬, 참조
        용도 랩퍼, fork 에이전트는 워크플로 단계가 아니라 호출 포트가 무의미하다.

        판정은 출력 포트와 **같은 술어**다(WP-2d): 단일 배치되는 노드인가.
        둘이 어긋나면 "출력 포트는 붙는데 호출 포트는 안 붙는" 종류가 생긴다.
        """
        from daedalus.model.plugin.placement import is_state_placeable

        if not is_state_placeable(comp):
            raise ValueError(
                f"'{name}'에는 에이전트 호출 포트를 붙일 수 없습니다 — 단계 스킬"
                f"(절차형·fork), state 용도 랩핑 스킬, 워크플로 에이전트만 가능합니다."
                + _usage_escape_hatch(comp)
            )
        return comp

    def add_agent_call(
        self, skill: str, event: str, description: str = "", color: str = ""
    ) -> dict[str, Any]:
        """스킬/에이전트에 **에이전트 호출 포트**를 추가한다.

        에이전트로 가는 전이는 이 포트에서만 나갈 수 있다(캔버스와 같은 규칙).
        포트를 만든 뒤 connect_states(..., trigger=<event>)로 연결한다.
        에이전트에 붙이면 그 에이전트가 다른 에이전트를 서브에이전트로 부른다 —
        깊이·모델 티어 제약은 검증(agent_chain_too_deep/agent_calls_higher_model)이 짚는다.
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd

        comp = self._require_call_port_owner(self._find_component(skill), skill)
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

    def set_agent_calls(
        self, skill: str, events: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """스킬/에이전트의 **에이전트 호출 포트 전체**를 통째로 교체한다.

        `set_transfer_on`의 call_agents 짝(G6) — `add_agent_call`/
        `remove_agent_call`은 하나씩 넣고 빼는 지름길이고, 이 도구는 여러 포트를
        한 번에 갈아끼운다. 포트 description은 호출 계약(WP-CT)의 유일한
        채널이라 여러 개를 함께 고쳐야 할 때 하나씩 지웠다 다시 만드는 것보다
        이쪽이 안전하다(1 undo 단위).

        events: [{"name": "review", "description": "GPU 병목 조사", "color": "#ff8844"}, ...]
        이 포트를 trigger로 쓰던 전이는 목록에서 빠진 이름이어도 **함께 지우지
        않는다**(remove_agent_call과 같은 정책) — 남은 전이는
        `trigger_unknown_event` 경고로 드러난다.
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd

        comp = self._require_call_port_owner(self._find_component(skill), skill)
        defs = self._make_event_defs(events)
        names = [d.name for d in defs]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"중복된 이벤트 이름: {', '.join(sorted(dupes))}")

        self._vm.execute(
            SetAttrCmd(
                comp,
                "call_agents",
                defs,
                label=f"'{skill}' 에이전트 호출 포트 {len(defs)}개 설정",
                script=f'set_agent_calls("{skill}", {names})',
            )
        )
        return {"skill": skill, "call_agents": names}

    def remove_agent_call(self, skill: str, event: str) -> dict[str, Any]:
        """스킬/에이전트의 에이전트 호출 포트를 제거한다.

        그 포트를 trigger로 쓰는 전이는 **함께 지우지 않는다**(캔버스에서 포트를
        지웠을 때와 같다) — 남은 전이는 `trigger_unknown_event` 경고로 드러나므로,
        결과의 `orphaned_transitions`를 보고 disconnect_states로 정리하라.
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd

        comp = self._require_call_port_owner(self._find_component(skill), skill)
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
