# daedalus/model/validation/project_rules/workflow.py
"""워크플로 배치·전이 의미론 규칙 (이동만 — 동작 불변) — A11 / A3."""
from __future__ import annotations

from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.validation.project_rules.scan import (
    project_machines,
    scan_transitions,
)
from daedalus.model.validation.severity import ValidationError


#: 한 체인에 이어 붙일 수 있는 에이전트 수. CC는 주 대화 기준 **3계층**까지
#: 서브에이전트 중첩을 허용하고, 한계에 닿은 서브에이전트에게서는 Agent 도구를
#: 회수한다 — 그러면 위임 지시를 따를 수 없어 그 에이전트가 혼자 처리한다.
#: 스킬은 메인 스레드에서 돌므로 그 스킬이 부른 에이전트가 1계층이다.
MAX_AGENT_CHAIN = 3


def _agent_call_edges(project) -> list[tuple]:
    """프로젝트 그래프의 **에이전트 → 에이전트** 전이 목록.

    반환: [(source_state, target_state, caller_agent, callee_agent, port)] — 선언 순서.
    스킬 → 에이전트는 대상이 아니다(메인 스레드가 부르므로 중첩이 아니다).
    """
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.plugin.agent import AgentDefinition

    graph = getattr(project, "graph", None)
    if graph is None:
        return []
    out: list[tuple] = []
    for trans in getattr(graph, "transitions", []) or []:
        src, tgt = trans.source, trans.target
        if not isinstance(src, SimpleState) or not isinstance(tgt, SimpleState):
            continue
        caller, callee = src.skill_ref, tgt.skill_ref
        if not isinstance(caller, AgentDefinition) or not isinstance(callee, AgentDefinition):
            continue
        port = getattr(getattr(trans, "trigger", None), "name", "") or ""
        out.append((src, tgt, caller, callee, port))
    return out


class _WorkflowRules:
    """전이 스킬 재사용·진입점 의미론·에이전트 중첩 규칙 모음 (_ProjectRules 믹스인)."""

    _scan_transitions = staticmethod(scan_transitions)
    _agent_call_edges = staticmethod(_agent_call_edges)

    @staticmethod
    def _check_agent_chain_depth(project) -> list[ValidationError]:
        """agent_chain_too_deep — 에이전트 호출 체인이 CC 깊이 제한을 넘으면 에러.

        에이전트가 에이전트를 부르는 것은 2026-09-12부터 허용되지만, CC의 중첩
        한계(주 대화 기준 3계층)를 넘는 체인은 **설계대로 돌지 않는다** — 한계에
        닿은 서브에이전트는 Agent 도구를 빼앗겨 위임하지 못하고 혼자 처리한다.
        조용히 다르게 도는 것이므로 경고가 아니라 에러다.

        순환(A→B→A)은 깊이가 무한이라 같은 규칙이 잡되 메시지를 달리한다.
        """
        edges = _agent_call_edges(project)
        if not edges:
            return []

        adj: dict[int, list[int]] = {}
        node: dict[int, object] = {}
        for src, tgt, caller, callee, _port in edges:
            node[id(src)], node[id(tgt)] = caller, callee
            adj.setdefault(id(src), []).append(id(tgt))
            adj.setdefault(id(tgt), [])

        errors: list[ValidationError] = []
        longest: dict[int, int] = {}
        on_stack: dict[int, bool] = {}
        cycles: list[list[int]] = []
        stack: list[int] = []

        def walk(key: int) -> int:
            """key에서 시작하는 체인의 최대 에이전트 수(자기 포함)."""
            if on_stack.get(key):
                cycles.append(stack[stack.index(key):] + [key])
                return 0  # 순환은 별도 보고 — 깊이 계산에는 0으로 접는다
            if key in longest:
                return longest[key]
            on_stack[key] = True
            stack.append(key)
            best = 0
            for nxt in adj.get(key, []):
                best = max(best, walk(nxt))
            stack.pop()
            on_stack[key] = False
            longest[key] = best + 1
            return longest[key]

        for key in list(adj):
            walk(key)

        seen_cycle: set[tuple[str, ...]] = set()
        for cyc in cycles:
            names = tuple(getattr(node.get(k), "name", "?") for k in cyc)
            if names in seen_cycle:
                continue
            seen_cycle.add(names)
            errors.append(ValidationError(
                rule="agent_chain_too_deep",
                message=(
                    f"에이전트 호출이 순환합니다: {' → '.join(names)}. 깊이가 "
                    f"무한이라 CC 중첩 한계({MAX_AGENT_CHAIN}계층)에 반드시 걸립니다 — "
                    f"순환 구간을 끊고 스킬을 경유하세요."
                ),
                source=" -> ".join(names),
                subject=node.get(cyc[0]),
                path=("project",),
            ))

        # 체인의 시작점(들어오는 에이전트 호출이 없는 노드)에서만 보고한다 —
        # 같은 체인을 노드마다 반복해서 짚으면 같은 사실이 여러 번 나온다.
        has_incoming = {tgt for outs in adj.values() for tgt in outs}
        for key, depth in sorted(longest.items(), key=lambda kv: -kv[1]):
            if key in has_incoming or depth <= MAX_AGENT_CHAIN:
                continue
            errors.append(ValidationError(
                rule="agent_chain_too_deep",
                message=(
                    f"에이전트 '{getattr(node.get(key), 'name', '?')}'에서 시작하는 "
                    f"호출 체인이 {depth}단계입니다 — CC는 주 대화 기준 "
                    f"{MAX_AGENT_CHAIN}계층까지만 중첩을 허용하고, 한계에 닿은 "
                    f"에이전트는 Agent 도구를 빼앗겨 위임하지 못한 채 혼자 "
                    f"처리합니다. 중간을 스킬로 끊으면 그 스킬이 메인 스레드에서 "
                    f"돌아 깊이가 다시 1부터 시작합니다."
                ),
                source=getattr(node.get(key), "name", "?"),
                subject=node.get(key),
                path=("project",),
            ))
        return errors

    @staticmethod
    def _check_agent_calls_higher_model(project) -> list[ValidationError]:
        """agent_calls_higher_model — 자기보다 상위 모델의 에이전트 호출 금지 (사용자 확정 2026-09-12).

        상위 모델이 필요한 판단은 메인 스레드가 부르게 한다 — 하위 모델이 상위
        모델을 부리는 구조는 "무엇을 시킬지"를 결정하는 쪽이 더 얕게 보는 것이라
        비용만 크고 판단은 나아지지 않는다.

        어느 한쪽이라도 `INHERIT`(미지정)면 건너뛴다 — 물려받는 값이라 상위/하위가
        성립하지 않는다. 티어 표의 단일 진실은 `model/plugin/enums.MODEL_TIER`.
        """
        from daedalus.model.plugin.enums import MODEL_TIER, ModelType

        def tier(component) -> int | None:
            model = getattr(getattr(component, "config", None), "model", None)
            return MODEL_TIER.get(model) if isinstance(model, ModelType) else None

        errors: list[ValidationError] = []
        for src, _tgt, caller, callee, port in _agent_call_edges(project):
            caller_tier, callee_tier = tier(caller), tier(callee)
            if caller_tier is None or callee_tier is None:
                continue
            if callee_tier <= caller_tier:
                continue
            port_note = f"(포트 '{port}') " if port else ""
            errors.append(ValidationError(
                rule="agent_calls_higher_model",
                message=(
                    f"에이전트 '{caller.name}'"
                    f"({caller.config.model.value})가 {port_note}상위 모델 에이전트 "
                    f"'{callee.name}'({callee.config.model.value})를 호출합니다. "
                    f"상위 모델은 메인 스레드가 부르게 하세요 — 호출 포트를 스킬로 "
                    f"옮기거나 두 에이전트의 모델 티어를 맞추세요."
                ),
                source=f"{caller.name}->{callee.name}",
                subject=src,
                path=("project",),
            ))
        return errors

    @staticmethod
    def _check_transfer_skill_reused(project) -> list[ValidationError]:
        """transfer_skill_reused — 한 TransferSkill이 2개 이상 전이에 붙으면 에러 (A11).

        **프레이밍(사용자 확정): TransferSkill은 전이 위에 놓인 1:1 중간 상태다.**
        A→B 전이에 T가 붙으면 의미론은 A→T→B이고, T는 입력 하나(그 전이)·출력
        하나(계속 진행)뿐인 통과 노드다. 그래서 재사용 금지는 특별 규칙이 아니라
        `no_duplicate_skill_ref`와 **같은 논리**다 — 하나의 상태가 두 자리에
        동시에 있을 수 없다.

        모델 구조는 그대로다(`Transition.skill_ref`) — 이건 산출 의미론과 검증의
        프레이밍이지 그래프에 실제 중간 노드를 만든다는 뜻이 아니다.

        순회 범위는 프로젝트 그래프 + 각 스킬/에이전트 FSM(재귀)이다 —
        `dangling_tool_ref`/블랙보드 규칙과 같은 범위.
        """
        from daedalus.model.plugin.skill import TransferSkill

        # id(스킬) → (스킬, [경로 표지…]) — 어디에 붙었는지 알려 줘야 고칠 수 있다.
        uses: dict[int, tuple[object, list[str]]] = {}

        def _make_visitor(label: str):
            def _visit(trans) -> None:
                ref = getattr(trans, "skill_ref", None)
                if not isinstance(ref, TransferSkill):
                    return
                entry = uses.setdefault(id(ref), (ref, []))
                src = getattr(getattr(trans, "source", None), "name", "?")
                tgt = getattr(getattr(trans, "target", None), "name", "?")
                entry[1].append(f"{label}: {src}→{tgt}")
            return _visit

        graph = getattr(project, "graph", None)
        if graph is not None:
            scan_transitions(graph, _make_visitor("project"))
        for label, sm in project_machines(project):
            scan_transitions(sm, _make_visitor(label))

        errors: list[ValidationError] = []
        for _key, (skill, places) in uses.items():
            if len(places) < 2:
                continue
            errors.append(ValidationError(
                rule="transfer_skill_reused",
                message=(
                    f"전이 스킬 '{skill.name}'이 전이 {len(places)}곳에 붙어 "
                    f"있습니다 ({', '.join(places)}). 전이 스킬은 그 전이 위에 "
                    f"놓인 중간 상태이므로 전이 하나에만 속합니다 — 하나의 상태가 "
                    f"두 자리에 동시에 있을 수 없다는 점에서 "
                    f"no_duplicate_skill_ref와 같은 논리입니다. 전이마다 따로 "
                    f"만드세요. 같은 지침이 여러 전이에 필요하면 그 내용을 "
                    f"Declarative 스킬로 만들어 각 전이 스킬이 참조하게 하세요."
                ),
                source=skill.name,
                subject=skill,
            ))
        return errors

    @staticmethod
    def _check_mid_chain_user_invocable(project) -> list[ValidationError]:
        """mid_chain_user_invocable — 체인 중간 배치인데 user-invocable이면 경고 (A3).

        원칙(사용자 확정): **user-invocable은 진입점으로 기능할 노드만 true여야
        한다.** `/skill`로 직접 부를 수 있다는 것은 "여기서 시작해도 된다"는
        선언인데, 앞 단계가 채워 놓은 블랙보드·진행 상태를 전제하는 중간 스킬을
        맥락 없이 시작하면 그 전제가 통째로 비어 있는 채로 돈다.

        false로 두어도 **모델 인보크는 그대로 되므로 체인은 끊기지 않는다** —
        앞 스킬의 "다음 단계" 지시가 여전히 이 스킬을 부른다. 잃는 것은 사람이
        직접 부르는 통로뿐이고, 그것이 정확히 막고 싶은 것이다.

        대상은 **프로젝트 그래프에 배치된 ProceduralSkill 중 incoming 전이가
        1개 이상**인 것뿐이다:
        - incoming 0개 = 진입점 후보이므로 정상.
        - 배치 안 된 스킬 = 독립 스킬이라 user_invocable true가 정상.
        - EntryPoint에서 오는 전이는 incoming으로 세지 않는다 — 그것이 곧
          "여기서 시작한다"는 뜻이다(WP-EP로 캔버스에 그리지 않을 뿐, 구버전
          파일의 시작 전이는 모델에 남아 있다).

        **tri-state(A8) 판정은 실효값 기준이다.** `None`(미지정)은 프론트매터
        키가 생략되어 CC 기본값 **true**로 동작하므로 경고 대상이다 — 설계에서
        선언하지 않았다는 이유로 넘어가면, 실제로는 `/스킬`로 시작할 수 있는
        중간 노드가 조용히 남는다. 다만 메시지에 미지정임을 병기해 무엇을
        고쳐야 하는지 알린다. **명시 `False`만 통과한다.**
        """
        from daedalus.model.fsm.state import SimpleState
        from daedalus.model.plugin.skill import ProceduralSkill

        graph = getattr(project, "graph", None)
        if graph is None:
            return []

        incoming: dict[int, int] = {}
        for trans in graph.transitions:
            if isinstance(trans.source, EntryPoint):
                continue
            incoming[id(trans.target)] = incoming.get(id(trans.target), 0) + 1

        errors: list[ValidationError] = []
        for state in graph.states:
            if not isinstance(state, SimpleState):
                continue
            skill = state.skill_ref
            if not isinstance(skill, ProceduralSkill):
                continue
            if not incoming.get(id(state)):
                continue  # 진입점 후보
            declared = getattr(skill.config, "user_invocable", None)
            if declared is False:
                continue  # 명시적으로 끔 — 유일한 통과 조건
            note = (
                "user-invocable입니다"
                if declared
                else "user_invocable이 미지정(생략 시 CC 기본값 true)입니다"
            )
            errors.append(ValidationError(
                rule="mid_chain_user_invocable",
                message=(
                    f"스킬 '{skill.name}'은 체인 중간(선행 전이 있음)에 배치돼 "
                    f"있는데 {note} — 사용자가 앞 단계의 맥락 없이 "
                    f"직접 시작할 수 있습니다. 진입점으로 쓸 것이 아니면 "
                    f"user_invocable을 false로 지정하세요(모델 인보크는 그대로 "
                    f"되므로 체인은 끊기지 않습니다)."
                ),
                source=skill.name,
                subject=state,
                path=("project",),
            ))
        return errors
