# daedalus/model/validation/project_rules/workflow.py
"""워크플로 배치·전이 의미론 규칙 (이동만 — 동작 불변) — A11 / A3."""
from __future__ import annotations

from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.validation.project_rules.scan import (
    project_machines,
    scan_transitions,
)
from daedalus.model.validation.severity import ValidationError


class _WorkflowRules:
    """전이 스킬 재사용·진입점 의미론 규칙 모음 (_ProjectRules 믹스인)."""

    _scan_transitions = staticmethod(scan_transitions)

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
