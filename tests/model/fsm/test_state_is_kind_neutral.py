# tests/model/fsm/test_state_is_kind_neutral.py
"""`model/fsm/state.py`는 컴포넌트 **종류**를 알지 못한다 (REFACTOR_SPEC Q35).

예전 `SimpleState.skill_ref`의 타입은 `StepSkill | DeclarativeSkill |
AgentDefinition | None`이라는 **종류 열거 표**였는데, 배치 가능한
배치 가능한 종류가 빠져 있어도 아무것도 실패하지 않았다 — 타입 주석뿐이라
런타임이 읽지 않는 표였고, 새 종류를 더한 사람에게 "여기도 고쳐라"라고
말해 주는 장치가 없었다(카탈로그 M11 👻, 스멜 ⑤).

이 테스트는 그 표가 **다시 생기지 못하게** 한다. 판정의 실체는
`component.effective_placement()`이고 fsm 레이어는 기저 타입만 안다.

소스 텍스트 스캔이다 — 임포트하지 않으므로 헤드리스 안전하고, `TYPE_CHECKING`
블록 안의 주석 전용 임포트도 그대로 잡힌다.
"""
from __future__ import annotations

import ast
from pathlib import Path

_STATE_PY = (
    Path(__file__).resolve().parents[3]
    / "daedalus" / "model" / "fsm" / "state.py"
)

#: 구체 컴포넌트 9종 + 종류를 좁히는 추상 기저 (REFACTOR_SPEC §0-a COMP 집합에서
#: `PluginComponent`만 뺀 것 — 기저 하나는 종류 표가 아니다).
FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "Skill", "StepSkill", "ForkSkill", "Agent",
    "ProceduralSkill", "SyncForkSkill", "AsyncForkSkill", "DeclarativeSkill",
    "TransferSkill", "ReferenceSkill", "AgentDefinition",
    "ForkAgent", "ExternalAgent",
})


def _names_in_source() -> set[str]:
    tree = ast.parse(_STATE_PY.read_text(encoding="utf-8"), filename=str(_STATE_PY))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.alias):
            found.add(node.name.rsplit(".", 1)[-1])
            if node.asname:
                found.add(node.asname)
    return found


def test_state_module_names_no_concrete_component_kind():
    offenders = sorted(_names_in_source() & FORBIDDEN_NAMES)
    assert not offenders, (
        "model/fsm/state.py가 컴포넌트 종류를 이름으로 알고 있다 — 배치 판정은 "
        f"`effective_placement()`가 답한다: {offenders}"
    )


def test_skill_ref_is_annotated_with_the_base_type():
    """기저 타입 주석이 실제로 있는지 — 위 테스트는 주석을 지워도 통과한다."""
    tree = ast.parse(_STATE_PY.read_text(encoding="utf-8"), filename=str(_STATE_PY))
    annotations = {
        node.target.id: ast.unparse(node.annotation)
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert annotations.get("skill_ref") == "PluginComponent | None"
