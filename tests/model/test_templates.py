# tests/model/test_templates.py
"""시작 템플릿 3종 (A7).

이 파일이 고정하는 계약:
  ① 카탈로그와 디스크의 파일이 정확히 대응한다(둘 중 하나만 늘어나면 빨강).
  ② 로드는 **기존 `deserialize_project` 경로**를 그대로 탄다 — 전용 파서 없음.
  ③ 열자마자 F7 검증 **에러 0**, 경고는 개수를 스냅샷으로 못 박는다.
  ④ 본문·설명은 영어다(A12 — 산출로 나가는 사용자 값의 출발점).
  ⑤ 컴파일 게이트를 통과한다(이름 규약·경로 충돌 포함).
"""
from __future__ import annotations

import json
import re
import tempfile

import pytest

from daedalus.compiler.project_compiler import compile_project
from daedalus.model import templates
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import ProceduralSkill, ReferenceSkill
from daedalus.model.serialize import deserialize_project, serialize_project
from daedalus.model.validation import Validator

TEMPLATE_IDS = ("implementation-review", "research-pipeline", "single-skill-reference")

#: 경고 스냅샷 — 늘어나면 그 자리에서 빨강이 되어야 한다(템플릿은 모범 산출이다).
EXPECTED_WARNINGS: dict[str, int] = {
    "implementation-review": 0,
    "research-pipeline": 0,
    "single-skill-reference": 0,
}

_HANGUL = re.compile(r"[가-힣ㄱ-ㆎ]")
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _load(template_id: str):
    warnings: list[str] = []
    project = templates.load_template(template_id, collect_warnings=warnings)
    return project, warnings


# ---------------------------------------------------------------------------
# 카탈로그
# ---------------------------------------------------------------------------


def test_catalogue_matches_files_on_disk():
    """카탈로그 id 집합 = 템플릿 폴더의 파일 stem 집합.

    한쪽만 늘면 "메뉴에 있는데 안 열린다" 또는 "파일은 있는데 아무도 못 연다"가
    된다 — 어느 쪽도 실행 전에는 드러나지 않는다.
    """
    catalogue_ids = [t.id for t in templates.list_templates()]
    assert catalogue_ids == list(TEMPLATE_IDS)
    on_disk = sorted(p.stem for p in templates.TEMPLATE_DIR.glob("*.json"))
    assert on_disk == sorted(TEMPLATE_IDS)
    for template in templates.list_templates():
        assert template.path.is_file()
        assert template.title and template.summary


def test_unknown_template_id_is_rejected():
    with pytest.raises(templates.TemplateError):
        templates.load_template("no-such-template")


def test_template_files_are_format_2():
    """파일은 정본 직렬화기의 산출(format 2)이다 — 손으로 쓴 JSON이 아니다."""
    for template in templates.list_templates():
        with open(template.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["format"] == 2


# ---------------------------------------------------------------------------
# 로드 / 검증
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_template_loads_without_migration_warnings(template_id):
    """format 2 정본이므로 로드 경고(마이그레이션·dangling)가 없어야 한다."""
    project, warnings = _load(template_id)
    assert warnings == []
    assert project.name
    assert _NAME_RE.match(project.name)


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_template_has_no_validation_errors(template_id):
    """F7 에러 0 — 템플릿은 열자마자 유효해야 한다. 경고는 개수 스냅샷."""
    project, _ = _load(template_id)
    findings = Validator().validate_project(project)
    errors = [e for e in findings if not e.is_warning]
    warnings = [e for e in findings if e.is_warning]
    assert errors == [], [f"{e.rule}: {e.message}" for e in errors]
    assert len(warnings) == EXPECTED_WARNINGS[template_id], (
        [f"{e.rule}: {e.message}" for e in warnings]
    )


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_template_compiles(template_id):
    """컴파일 게이트 통과 — 이름 규약·산출 경로 충돌까지 포함한 실물 검사."""
    project, _ = _load(template_id)
    with tempfile.TemporaryDirectory() as out_dir:
        result = compile_project(project, out_dir)
    assert result.errors == []


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_template_round_trips(template_id):
    """로드 → 직렬화 → 재로드가 같은 형상을 준다(저장 경로와 같은 코드다)."""
    project, _ = _load(template_id)
    again = deserialize_project(serialize_project(project))
    assert [s.name for s in again.skills] == [s.name for s in project.skills]
    assert [a.name for a in again.agents] == [a.name for a in project.agents]
    assert len(again.graph.transitions) == len(project.graph.transitions)


# ---------------------------------------------------------------------------
# 내용 규약
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_template_content_is_english(template_id):
    """본문·설명은 영어다 (A12).

    이 값들은 사용자 값이라 컴파일러가 손대지 않고 **그대로 산출에 실린다** —
    출발점이 한국어면 템플릿에서 시작한 플러그인의 산출이 한국어로 나간다.
    """
    project, _ = _load(template_id)
    offenders: list[str] = []

    def check(label: str, text: str) -> None:
        if text and _HANGUL.search(text):
            offenders.append(label)

    check("project.description", project.description)
    for comp in list(project.skills) + list(project.agents):
        check(f"{comp.name}.description", comp.description)
        check(f"{comp.name}.body", getattr(comp, "body", ""))
        check(f"{comp.name}.when_to_use", getattr(comp, "when_to_use", ""))
        for event in list(getattr(comp, "transfer_on", [])) + list(
            getattr(comp, "call_agents", [])
        ):
            check(f"{comp.name}.port:{event.name}", event.description)
    for cls in project.blackboard.class_definitions:
        check(f"blackboard:{cls.name}", cls.description)
    assert offenders == []


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_component_names_follow_convention(template_id):
    """컴포넌트 이름은 산출 디렉토리 이름이 된다 — 규약을 어기면 컴파일이 막힌다."""
    project, _ = _load(template_id)
    for comp in list(project.skills) + list(project.agents):
        assert _NAME_RE.match(comp.name), comp.name
        assert comp.body.strip(), f"{comp.name}: 본문이 비어 있다"
        assert comp.description.strip(), f"{comp.name}: 설명이 비어 있다"


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_entry_skill_is_user_invocable(template_id):
    """진입점이 하나는 있어야 한다 — 아무도 시작할 수 없는 템플릿은 쓸모가 없다."""
    project, _ = _load(template_id)
    entries = [
        s for s in project.skills
        if isinstance(s, ProceduralSkill) and s.config.user_invocable is True
    ]
    assert entries, "user_invocable 스킬이 없다"


# ---------------------------------------------------------------------------
# 아키타입 형상 — 무엇을 보여주는 템플릿인지 자체를 고정한다
# ---------------------------------------------------------------------------


def test_implementation_review_shape():
    """에이전트 2개 + 블랙보드 + 리뷰 반려 루프."""
    project, _ = _load("implementation-review")
    assert len(project.agents) == 2
    assert {c.name for c in project.blackboard.class_definitions} == {
        "TaskSpec", "ReviewFindings",
    }
    # 리뷰어의 반려 갈래가 구현 단계로 되돌아간다(루프가 실제로 그려져 있다)
    reviewer = next(a for a in project.agents if a.name == "reviewer")
    reviewer_state = next(
        s for s in project.graph.states if getattr(s, "skill_ref", None) is reviewer
    )
    loop = [
        t for t in project.graph.transitions
        if t.source is reviewer_state and t.trigger is not None
        and t.trigger.name == "changes-requested"
    ]
    assert len(loop) == 1
    assert loop[0].target.name == "run-implementation"
    # 블랙보드 접근 선언이 노드에 실제로 붙어 있다(캔버스 뱃지 + 산출 구체화)
    assert any(s.writes for s in project.graph.states)
    assert any(s.reads for s in project.graph.states)


def test_research_pipeline_shape():
    """병렬 조사 에이전트 + 합성 스킬 + 블랙보드 3종."""
    project, _ = _load("research-pipeline")
    assert [a.name for a in project.agents] == ["investigator"]
    assert len(project.blackboard.class_definitions) == 3
    dispatch = next(s for s in project.skills if s.name == "dispatch-investigators")
    assert [e.name for e in dispatch.call_agents] == ["investigate"]
    # 조사 결과 갈래 2종이 모두 합성 단계로 모인다
    investigator = project.agents[0]
    assert {e.name for e in investigator.transfer_on} == {
        "findings-recorded", "no-results",
    }


def test_single_skill_reference_shape():
    """스킬 하나 + 참조 문서 — 에이전트도 블랙보드도 없다."""
    project, _ = _load("single-skill-reference")
    assert project.agents == []
    assert project.blackboard.class_definitions == []
    assert any(isinstance(s, ReferenceSkill) for s in project.skills)
    assert len(project.reference_placements) == 1
    placement = project.reference_placements[0]
    assert placement.skill_name == "reference-notes"
    # 참조 노드가 실제 캔버스 노드에 연결돼 있다(고아 참조 배치가 아니다)
    node_names = {s.name for s in project.graph.states}
    assert set(placement.connected_states) <= node_names
    assert placement.connected_states


def test_no_agent_definition_leaks_into_single_skill_template():
    """단일 스킬 템플릿에 에이전트 잔재가 없는지 — 형상 회귀 방지."""
    project, _ = _load("single-skill-reference")
    assert not any(isinstance(c, AgentDefinition) for c in project.skills)
