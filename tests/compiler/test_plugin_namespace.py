"""플러그인 네임스페이스 — 한 작업 폴더에 여러 ddls 플러그인 (WP-NS).

실측으로 드러난 기존 결함을 고정한다.

- `schemas/schemas.json`이 **고정 경로**라 두 번째 플러그인이 조용히 덮어썼다.
- `state/`에는 `${ROOT}` 토큰이 붙지 않아 **작업 폴더 CWD 기준**이다. 그래서
  마켓플레이스 플러그인이 한쪽에만 끼어도 `state/<Class>.json`과 고정 파일명
  `state/__progress__.json`이 충돌한다 — LOCAL만의 문제가 아니다.

그래서 네임스페이스는 **양쪽 빌드 타깃 모두**에 적용한다(D12). 배포 전이라
"MARKETPLACE 산출은 바이트 동일"이라는 하위 호환 게이트는 지킬 대상이 없다.
"""
from __future__ import annotations

import pytest

from daedalus.compiler.emit import compile_agent, compile_skill
from daedalus.compiler.emit.manifest import expand_root_token
from daedalus.model.fsm.blackboard import DynamicClass, DynamicField
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.variable import FieldType
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject


def _machine() -> StateMachine:
    entry = EntryPoint(name="start")
    return StateMachine(name="m", initial_state=entry, states=[entry])


def _project(name: str, target: BuildTarget = BuildTarget.MARKETPLACE):
    skill = ProceduralSkill(
        fsm=_machine(), name="collect", description="Collect data.", body="Do it."
    )
    skill.transfer_on = [EventDef(name="done", description="finished")]
    project = PluginProject(name=name, description="demo")
    project.build_target = target
    project.skills.append(skill)
    project.blackboard.class_definitions.append(
        DynamicClass(
            name="Task",
            description="a task",
            fields=[
                DynamicField(name="title", field_type=FieldType.STRING, required=True)
            ],
        )
    )
    return project, skill


def _skill_text(project, skill) -> str:
    return expand_root_token(compile_skill(skill, project=project), project)


# ─────────────────────────── 산출 경로 ───────────────────────────


@pytest.mark.parametrize("target", [BuildTarget.MARKETPLACE, BuildTarget.LOCAL])
def test_schemas_output_path_uses_project_name(tmp_path, target):
    """`schemas/<프로젝트>.json`으로 나간다 — 폴더를 한 겹 더 파지 않는다(D6)."""
    from daedalus.compiler.project_compiler import compile_project

    project, _ = _project("my-plugin", target)
    result = compile_project(project, tmp_path)
    assert not result.errors, result.errors
    written = {path.name for path in result.written}
    assert "my-plugin.json" in written
    assert "schemas.json" not in written


def test_two_projects_do_not_share_any_output_path(tmp_path):
    """두 플러그인을 같은 작업 폴더에 LOCAL 빌드해도 산출 경로가 겹치지 않는다."""
    from daedalus.compiler.project_compiler import compile_project

    alpha, _ = _project("alpha", BuildTarget.LOCAL)
    beta, _ = _project("beta", BuildTarget.LOCAL)
    # 스킬 이름이 같으면 그건 별개의 이름 충돌이다 — 여기서는 고정 경로만 본다.
    beta.skills[0].name = "gather"

    first = compile_project(alpha, tmp_path)
    second = compile_project(beta, tmp_path)
    assert not first.errors and not second.errors

    # 파일 이름이 아니라 **경로**로 본다 — SKILL.md는 스킬 폴더마다 있는 것이
    # 정상이므로 basename만 비교하면 겹치지 않는 산출도 충돌로 잡힌다.
    def rel(result):
        return {path.relative_to(tmp_path).as_posix() for path in result.written}

    overlap = rel(first) & rel(second)
    # .mcp.json·settings.local.json은 병합 편집 대상이라 공유가 정상이다.
    overlap -= {".mcp.json", ".claude/settings.local.json"}
    assert not overlap, f"두 플러그인이 같은 파일을 쓴다: {sorted(overlap)}"


# ─────────────────────────── 본문 지시 ───────────────────────────


@pytest.mark.parametrize("target", [BuildTarget.MARKETPLACE, BuildTarget.LOCAL])
def test_skill_body_points_at_namespaced_schemas(target):
    project, skill = _project("my-plugin", target)
    text = _skill_text(project, skill)
    assert "schemas/my-plugin.json" in text
    assert "schemas/schemas.json" not in text


@pytest.mark.parametrize("target", [BuildTarget.MARKETPLACE, BuildTarget.LOCAL])
def test_skill_body_declares_state_dir(target):
    """`--state-dir`를 명시하지 않으면 유도값에 기대게 되는데, 산출은 명시한다.

    유도가 있어도 본문이 경로를 말해 주어야 사람이 읽고 검증할 수 있다.
    """
    project, skill = _project("my-plugin", target)
    text = _skill_text(project, skill)
    assert "state/my-plugin" in text


@pytest.mark.parametrize("target", [BuildTarget.MARKETPLACE, BuildTarget.LOCAL])
def test_state_file_listing_is_namespaced(target):
    project, skill = _project("my-plugin", target)
    text = _skill_text(project, skill)
    assert "state/my-plugin/Task.json" in text
    assert "state/Task.json" not in text


def test_agent_body_is_namespaced_too():
    project, _ = _project("my-plugin")
    agent = AgentDefinition(fsm=_machine(), name="worker", description="Worker.")
    agent.transfer_on = [EventDef(name="done")]
    project.agents.append(agent)
    text = expand_root_token(compile_agent(agent, project=project), project)
    assert "schemas/my-plugin.json" in text
    assert "state/my-plugin/Task.json" in text
    assert "state/Task.json" not in text
