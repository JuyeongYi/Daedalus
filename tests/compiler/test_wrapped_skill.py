# tests/compiler/test_wrapped_skill.py
"""스킬 랩핑 (WP-WR) — 모델·직렬화·emit·의존성 배선·검증.

D1=런타임 참조(사용자 확정): 산출 본문은 소스 복사가 아니라 인보크 지시 +
우리 그래프 유도 단락. 소스는 자기 플러그인에서 실행돼 경로 변수·프론트매터가
소스 기준으로 동작한다.

배선(dependencies/enabledPlugins)의 단일 진실은 **`PluginProject.
external_plugins` 사용 선언**이다(사용자 확정 2026-09-06) — 랩핑 스킬 source는
배선에 쓰이지 않고, 선언·참조의 어긋남은 검증 경고 2종이 짚는다.
"""
from __future__ import annotations

import json

from daedalus.compiler.emit import compile_skill
from daedalus.compiler.emit.manifest import compile_plugin_manifest
from daedalus.compiler.emit.skill import parse_wrapped_source
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.config import WrappedSkillConfig
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.skill import WrappedSkill
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project
from daedalus.model.validation import Validator


def _wrapped(name: str = "review-step", source: str = "other@mkt:code-review") -> WrappedSkill:
    entry = EntryPoint(name="start")
    return WrappedSkill(
        fsm=StateMachine(name=f"{name}_fsm", states=[entry], initial_state=entry),
        name=name, description="Wrapped review step.",
        config=WrappedSkillConfig(source=source),
    )


def _project_with_wrapped(source: str = "other@mkt:code-review", declare: bool = True,
                          build_target: BuildTarget = BuildTarget.MARKETPLACE):
    """랩핑 스킬 1개 + (기본) 그 플러그인 사용 선언까지 갖춘 프로젝트."""
    project = PluginProject(name="p", build_target=build_target)
    project.skills.append(_wrapped(source=source))
    if declare:
        plugin_id = source.partition(":")[0]
        project.external_plugins.append(plugin_id)
    return project


# ─────────────────────────── source 파싱 ───────────────────────────


def test_parse_wrapped_source():
    assert parse_wrapped_source("other@mkt:code-review") == ("other@mkt", "code-review")
    assert parse_wrapped_source("bare-plugin:skill") == ("bare-plugin", "skill")
    assert parse_wrapped_source("") == ("", "")
    assert parse_wrapped_source("no-colon") == ("", "")
    assert parse_wrapped_source(":skill-only") == ("", "")


# ─────────────────────────── 직렬화 왕복 ───────────────────────────


def test_wrapped_skill_roundtrip():
    project = PluginProject(name="p")
    project.skills.append(_wrapped())
    loaded = deserialize_project(serialize_project(project))
    skill = loaded.skills[0]
    assert skill.kind == "wrapped_skill"
    assert skill.config.source == "other@mkt:code-review"
    assert skill.output_events == ["done"]


def test_external_plugins_roundtrip():
    project = PluginProject(name="p")
    project.external_plugins.extend(["other@mkt", "bare-plugin"])
    loaded = deserialize_project(serialize_project(project))
    assert loaded.external_plugins == ["other@mkt", "bare-plugin"]


def test_legacy_file_without_external_plugins_loads_empty():
    data = serialize_project(PluginProject(name="p"))
    del data["external_plugins"]
    assert deserialize_project(data).external_plugins == []


# ─────────────────────────── emit ───────────────────────────


def test_compile_emits_invoke_instruction_not_body():
    text = compile_skill(_wrapped())
    assert "## Procedure" in text
    # 공식 크로스 플러그인 표기 `/플러그인:스킬` — 마켓 표기는 설치 식별자라
    # 인보크 토큰에는 붙지 않는다 (공식 문서 확인 2026-09-06)
    assert "invoke `/other:code-review`" in text
    assert "plugin `other`" in text
    assert "other@mkt" not in text.split("## Requirements")[0]
    assert "return here and continue" in text  # 워크플로 복귀 지시


def test_compile_requirements_mention_plugin():
    text = compile_skill(_wrapped())
    assert "## Requirements" in text
    assert "plugin `other@mkt`" in text
    assert "enabledPlugins" in text


def test_compile_empty_source_omits_instruction():
    """소스 미지정은 지시 단락 생략 — 빈 참조로 산출을 오염시키지 않는다."""
    text = compile_skill(_wrapped(source=""))
    assert "invoke the skill" not in text
    assert "## Procedure" not in text


def test_placed_wrapped_gets_graph_sections():
    """배치되면 재개·다음 단계 등 그래프 유도 단락을 받는다 (procedural과 동급)."""
    project = PluginProject(name="p")
    wrapped = _wrapped()
    project.skills.append(wrapped)
    from daedalus.model.plugin.config import DeclarativeSkillConfig
    from daedalus.model.plugin.skill import DeclarativeSkill

    follow = DeclarativeSkill(name="after", description="d",
                              config=DeclarativeSkillConfig())
    project.skills.append(follow)
    node = SimpleState(name="review-step", skill_ref=wrapped)
    done = SimpleState(name="after", skill_ref=follow)
    project.graph.states.extend([node, done])
    project.graph.transitions.append(
        Transition(source=node, target=done, trigger=CompletionEvent(name="done"))
    )
    text = compile_skill(wrapped, project=project)
    assert "## Resuming Work" in text
    assert "## Next Steps" in text


# ─────────────────────────── 의존성 배선 — 선언(external_plugins) 기반 ───────────────────────────


def test_manifest_dependencies_from_declaration():
    """dependencies는 external_plugins 선언에서 나온다 — 랩핑 스킬이 없어도."""
    project = PluginProject(name="p")
    project.external_plugins.extend(["second", "other@mkt", "other@mkt"])
    manifest = json.loads(compile_plugin_manifest(project))
    assert manifest["dependencies"] == ["other@mkt", "second"]  # 정렬·중복 제거


def test_manifest_ignores_wrapped_sources_without_declaration():
    """랩핑 스킬 source는 배선에 쓰이지 않는다(선언이 단일 진실) — 어긋남은
    undeclared_external_plugin 경고 소관."""
    project = _project_with_wrapped(declare=False)
    manifest = json.loads(compile_plugin_manifest(project))
    assert "dependencies" not in manifest


def test_manifest_no_dependencies_key_without_declaration():
    manifest = json.loads(compile_plugin_manifest(PluginProject(name="p")))
    assert "dependencies" not in manifest


def test_local_compile_bakes_enabled_plugins(tmp_path):
    from daedalus.compiler.project_compiler import compile_project

    project = _project_with_wrapped(build_target=BuildTarget.LOCAL)
    result = compile_project(project, tmp_path)
    assert not result.errors
    obj = json.loads(
        (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert obj["enabledPlugins"] == {"other@mkt": True}
    # 모델은 불변 — enabledPlugins는 컴파일 합성이다
    assert "enabledPlugins" not in project.workspace_settings


def test_local_enabled_plugins_without_any_wrapped_skill(tmp_path):
    """사용 선언만으로 배선된다 — 랩핑 스킬을 만들 필요가 없다(사용자 확정)."""
    from daedalus.compiler.project_compiler import compile_project

    project = PluginProject(name="p", build_target=BuildTarget.LOCAL)
    project.external_plugins.append("other@mkt")
    result = compile_project(project, tmp_path)
    assert not result.errors
    obj = json.loads(
        (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert obj["enabledPlugins"] == {"other@mkt": True}


def test_local_bare_declaration_warns_and_skips_enable(tmp_path):
    from daedalus.compiler.project_compiler import compile_project

    project = PluginProject(name="p", build_target=BuildTarget.LOCAL)
    project.external_plugins.append("bare-plugin")
    result = compile_project(project, tmp_path)
    rules = [w.rule for w in result.warnings]
    assert "external_plugin_no_marketplace" in rules
    settings = tmp_path / ".claude" / "settings.json"
    if settings.exists():
        assert "enabledPlugins" not in json.loads(settings.read_text(encoding="utf-8"))


def test_local_enabled_plugins_to_chosen_settings_file(tmp_path):
    """settings_filename 선택(WP-WS)이 enabledPlugins 베이크에도 그대로 적용된다."""
    from daedalus.compiler.project_compiler import compile_project

    project = _project_with_wrapped(build_target=BuildTarget.LOCAL)
    result = compile_project(project, tmp_path, settings_filename="settings.local.json")
    assert not result.errors
    obj = json.loads(
        (tmp_path / ".claude" / "settings.local.json").read_text(encoding="utf-8")
    )
    assert obj["enabledPlugins"] == {"other@mkt": True}
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_local_existing_enabled_plugins_preserved(tmp_path):
    """대상 폴더에 이미 있는 enabledPlugins 항목은 불가침 — 추가/갱신만·멱등."""
    from daedalus.compiler.project_compiler import compile_project

    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(
        json.dumps({"enabledPlugins": {"user-added@x": True}}), encoding="utf-8"
    )
    project = _project_with_wrapped(build_target=BuildTarget.LOCAL)
    compile_project(project, tmp_path)
    obj = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
    assert obj["enabledPlugins"] == {"user-added@x": True, "other@mkt": True}
    # 재컴파일 멱등
    compile_project(project, tmp_path)
    obj2 = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
    assert obj2 == obj


def test_local_dry_run_writes_nothing_but_reports(tmp_path):
    from daedalus.compiler.project_compiler import compile_project

    project = _project_with_wrapped(build_target=BuildTarget.LOCAL)
    result = compile_project(project, tmp_path, dry_run=True)
    assert not result.errors
    assert not (tmp_path / ".claude").exists()  # 디스크 완전 불변
    assert any(str(p).endswith("settings.json") for p in result.written)


def test_bare_declaration_warning_survives_dry_run_without_out_dir():
    """bare 선언 판정은 대상 폴더와 무관하다 — out_dir 없는 compile_check에서도
    경고가 나와야 한다(missing_mcp_server_def와 같은 규약)."""
    from daedalus.compiler.project_compiler import compile_project

    project = PluginProject(name="p", build_target=BuildTarget.LOCAL)
    project.external_plugins.append("bare-plugin")
    result = compile_project(project, None, dry_run=True)
    assert "external_plugin_no_marketplace" in [w.rule for w in result.warnings]


def test_marketplace_build_wires_manifest_dependencies(tmp_path):
    """MARKETPLACE 빌드 산출 파일에 dependencies가 실제로 실린다."""
    from daedalus.compiler.project_compiler import compile_project

    project = _project_with_wrapped()  # 기본 MARKETPLACE + 선언
    result = compile_project(project, tmp_path)
    assert not result.errors
    manifest = json.loads(
        (tmp_path / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["dependencies"] == ["other@mkt"]


# ─────────────── 외부 플러그인 제공 MCP 서버 (provided_server_names) ───────────────


def _project_with_agent_server(server: str = "extsrv"):
    from daedalus.model.plugin.agent import AgentDefinition
    from daedalus.model.plugin.config import AgentConfig
    from daedalus.model.fsm.section import EventDef

    project = PluginProject(name="p", build_target=BuildTarget.LOCAL)
    entry = EntryPoint(name="start")
    project.agents.append(AgentDefinition(
        fsm=StateMachine(name="a_fsm", states=[entry], initial_state=entry),
        name="worker", description="w",
        config=AgentConfig(mcp_servers=[server]),
        transfer_on=[EventDef(name="done")],
    ))
    return project


def test_provided_server_names_suppress_missing_def(tmp_path):
    """사용 선언된 외부 플러그인이 동봉 .mcp.json으로 제공하는 서버는 정의가
    없어도 missing_mcp_server_def를 내지 않는다 — 플러그인 활성화가 가져온다."""
    from daedalus.compiler.project_compiler import compile_project

    project = _project_with_agent_server("extsrv")
    without = compile_project(project, tmp_path / "a", dry_run=True)
    assert "missing_mcp_server_def" in [w.rule for w in without.warnings]
    with_provided = compile_project(
        project, tmp_path / "b", dry_run=True,
        provided_server_names={"extsrv"},
    )
    assert "missing_mcp_server_def" not in [w.rule for w in with_provided.warnings]


# ─────────────────────────── 검증 ───────────────────────────


def test_wrapped_source_missing_warns():
    project = PluginProject(name="p")
    project.skills.append(_wrapped(source=""))
    rules = [e.rule for e in Validator.validate_project(project)]
    assert "wrapped_source_missing" in rules


def test_valid_declared_source_no_warning():
    project = _project_with_wrapped()
    rules = [e.rule for e in Validator.validate_project(project)]
    assert "wrapped_source_missing" not in rules
    assert "undeclared_external_plugin" not in rules
    assert "unused_external_plugin" not in rules


def test_undeclared_external_plugin_warns():
    """랩핑 스킬이 미선언 플러그인을 가리키면 경고 — 선언이 없으면 배선이
    나가지 않아 런타임에 스킬을 찾지 못한다."""
    project = _project_with_wrapped(declare=False)
    rules = [e.rule for e in Validator.validate_project(project)]
    assert "undeclared_external_plugin" in rules


def test_unused_external_plugin_warns():
    """선언했는데 어떤 랩핑 스킬도 참조하지 않으면 경고만 — 배선은 그대로
    나간다(의도적 활성화 허용, 사용자 확정)."""
    project = PluginProject(name="p")
    project.external_plugins.append("other@mkt")
    issues = Validator.validate_project(project)
    rules = [e.rule for e in issues]
    assert "unused_external_plugin" in rules
    assert all(e.is_warning for e in issues if e.rule == "unused_external_plugin")


def test_marketplace_mismatch_is_both_warnings():
    """alpha@mkt 선언 ↔ alpha 참조는 다른 설치 대상 — 양쪽 경고."""
    project = PluginProject(name="p")
    project.skills.append(_wrapped(source="alpha:skill"))
    project.external_plugins.append("alpha@mkt")
    rules = [e.rule for e in Validator.validate_project(project)]
    assert "undeclared_external_plugin" in rules
    assert "unused_external_plugin" in rules


def test_same_source_multiple_wrappers_is_normal():
    """같은 source의 복수 랩핑은 정상(사용자 확정 — 재사용은 랩퍼 복수로)."""
    project = PluginProject(name="p")
    project.skills.append(_wrapped(name="review-a"))
    project.skills.append(_wrapped(name="review-b"))
    project.external_plugins.append("other@mkt")
    issues = Validator.validate_project(project)
    assert not [e for e in issues if not e.is_warning]
    assert "wrapped_source_missing" not in [e.rule for e in issues]
    assert "undeclared_external_plugin" not in [e.rule for e in issues]
