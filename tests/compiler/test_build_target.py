# tests/compiler/test_build_target.py
"""WP-TG/WP-MW: 빌드 타깃 컴파일 — MARKETPLACE 스테이징 vs LOCAL 직접 설치.

LOCAL은 **컴파일이 곧 설치**다. out_dir가 대상 작업 폴더이고, 산출물이 CC가
실제로 읽는 위치(.claude/skills, .claude/agents)에 바로 놓이며, .mcp.json과
.claude/settings.local.json이 생성/병합된다. 이전의 INSTALL.md/install.ps1/
install.sh 동봉 방식은 폐기됐다.
"""
from __future__ import annotations

import json

from daedalus.compiler import compile_project
from daedalus.compiler.emit import expand_root_token, referenced_mcp_servers
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.hook import CommandHook, HookDef, HookEvent
from daedalus.model.project import PluginProject

from tests.compiler.builders import make_agent, make_procedural


# ─────────────────────── MARKETPLACE — 바이트 동일 하위 호환 게이트 ───────────────────────


def test_marketplace_is_default_and_unaffected(tmp_path):
    """build_target을 명시하지 않아도 MARKETPLACE — plugin.json 생성, 설치 부산물 없음."""
    skill = make_procedural(name="my-skill")
    project = PluginProject(name="p", skills=[skill])
    assert project.build_target is BuildTarget.MARKETPLACE

    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    assert (tmp_path / ".claude-plugin" / "plugin.json").exists()
    assert (tmp_path / "skills" / "my-skill" / "SKILL.md").exists()
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".mcp.json").exists()


def test_marketplace_explicit_matches_omitted_byte_identical(tmp_path):
    """build_target=MARKETPLACE를 명시해도 산출이 기본값과 바이트 동일."""
    skill = make_procedural(name="my-skill")

    out_default = tmp_path / "default"
    proj_default = PluginProject(name="p", skills=[skill])
    compile_project(proj_default, out_default)

    out_explicit = tmp_path / "explicit"
    proj_explicit = PluginProject(
        name="p", skills=[skill], build_target=BuildTarget.MARKETPLACE,
    )
    compile_project(proj_explicit, out_explicit)

    for rel in ("skills/my-skill/SKILL.md", ".claude-plugin/plugin.json"):
        assert (out_default / rel).read_bytes() == (out_explicit / rel).read_bytes()


def test_marketplace_expands_root_to_plugin_root(tmp_path):
    """MARKETPLACE 빌드는 ${ROOT}를 ${CLAUDE_PLUGIN_ROOT}로 확장한다 (WP-RT)."""
    body = "참조: ${ROOT}/files/doc.txt"
    skill = make_procedural(name="my-skill", body=body)
    project = PluginProject(name="p", skills=[skill])
    result = compile_project(project, tmp_path)
    assert result.ok
    text = (tmp_path / "skills" / "my-skill" / "SKILL.md").read_text(encoding="utf-8")
    assert "${CLAUDE_PLUGIN_ROOT}/files/doc.txt" in text
    assert "${CLAUDE_PROJECT_DIR}" not in text
    assert "${ROOT}" not in text, "중립 토큰은 산출에 남으면 안 된다"


# ─────────────────────── LOCAL — 컴파일이 곧 설치 ───────────────────────


def test_local_build_installs_into_dot_claude(tmp_path):
    """스킬/에이전트가 CC가 실제로 읽는 <작업 폴더>/.claude/ 밑으로 바로 나간다."""
    agent = make_agent("worker")
    skill = make_procedural(name="my-skill")
    project = PluginProject(
        name="p", skills=[skill], agents=[agent], build_target=BuildTarget.LOCAL,
    )
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    assert (tmp_path / ".claude" / "skills" / "my-skill" / "SKILL.md").exists()
    assert (tmp_path / ".claude" / "agents" / "worker.md").exists()
    # 루트에는 놓지 않는다 — 거기 놓인 산출물은 CC가 읽지 않는다
    assert not (tmp_path / "skills").exists()
    assert not (tmp_path / "agents").exists()


def test_local_build_omits_plugin_json_and_install_scripts(tmp_path):
    skill = make_procedural(name="my-skill")
    project = PluginProject(name="p", skills=[skill], build_target=BuildTarget.LOCAL)
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    assert not (tmp_path / ".claude-plugin").exists()
    assert not (tmp_path / "INSTALL.md").exists()
    assert not (tmp_path / "install.ps1").exists()
    assert not (tmp_path / "install.sh").exists()


def test_local_build_substitutes_file_refs_in_skill_body(tmp_path):
    body = "참조: ${ROOT}/files/doc.txt 확인하라."
    skill = make_procedural(name="my-skill", body=body)
    project = PluginProject(name="p", skills=[skill], build_target=BuildTarget.LOCAL)
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    text = (
        tmp_path / ".claude" / "skills" / "my-skill" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "${CLAUDE_PROJECT_DIR}/files/doc.txt" in text
    assert "${CLAUDE_PLUGIN_ROOT}/files/" not in text
    assert "${ROOT}" not in text


def test_local_build_substitutes_file_refs_in_agent_body(tmp_path):
    agent = make_agent("worker")
    agent.body = "에이전트 참조: ${ROOT}/files/agent-doc.txt"
    project = PluginProject(name="p", agents=[agent], build_target=BuildTarget.LOCAL)
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]

    agent_text = (
        tmp_path / ".claude" / "agents" / "worker.md"
    ).read_text(encoding="utf-8")
    assert "${CLAUDE_PROJECT_DIR}/files/agent-doc.txt" in agent_text


# ─────────────────────── LOCAL — 훅: settings.local.json 병합 ───────────────────────


def _hooked_project() -> PluginProject:
    hook = HookDef(
        name="fmt-on-edit", description="포맷", event=HookEvent.POST_TOOL_USE,
        handlers=[CommandHook(script="run-formatter")],
    )
    skill = make_procedural(name="my-skill")
    skill.config.hooks = {"fmt-on-edit": {}}
    return PluginProject(
        name="p", skills=[skill], hook_library=[hook], build_target=BuildTarget.LOCAL,
    )


def test_local_hooks_merge_into_settings_local(tmp_path):
    """LOCAL은 hooks/hooks.json 파일 대신 settings.local.json의 hooks 섹션이다 —
    컴파일이 곧 설치이므로 CC가 실제로 읽는 자리에 놓는다."""
    result = compile_project(_hooked_project(), tmp_path)
    assert result.ok, [e.message for e in result.errors]

    assert not (tmp_path / "hooks" / "hooks.json").exists()
    settings = json.loads(
        (tmp_path / ".claude" / "settings.local.json").read_text(encoding="utf-8")
    )
    groups = settings["hooks"]["PostToolUse"]
    command = groups[0]["hooks"][0]["command"]
    assert command == "${CLAUDE_PROJECT_DIR}/hooks/scripts/fmt-on-edit.sh"
    # 스크립트 파일은 그 경로가 가리키는 위치에 실제로 있다
    assert (tmp_path / "hooks" / "scripts" / "fmt-on-edit.sh").exists()


def test_local_hooks_merge_is_idempotent(tmp_path):
    """재컴파일해도 같은 훅 그룹이 불어나지 않는다 — 불어나면 훅이 여러 번 실행된다."""
    project = _hooked_project()
    compile_project(project, tmp_path)
    compile_project(project, tmp_path)
    settings = json.loads(
        (tmp_path / ".claude" / "settings.local.json").read_text(encoding="utf-8")
    )
    assert len(settings["hooks"]["PostToolUse"]) == 1


def test_local_hooks_merge_preserves_existing_settings(tmp_path):
    """사용자가 이미 갖고 있던 설정은 지우지 않는다 — 병합은 추가만 한다."""
    settings_path = tmp_path / ".claude" / "settings.local.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({
        "permissions": {"allow": ["Bash(ls:*)"]},
        "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo mine"}]}]},
    }), encoding="utf-8")

    result = compile_project(_hooked_project(), tmp_path)
    assert result.ok

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["permissions"] == {"allow": ["Bash(ls:*)"]}
    assert settings["hooks"]["SessionStart"][0]["hooks"][0]["command"] == "echo mine"
    assert "PostToolUse" in settings["hooks"]


def test_local_broken_settings_left_untouched_with_warning(tmp_path):
    """깨진 JSON에 병합을 강행하면 수기 설정을 덮어쓴다 — 건드리지 않고 경고한다."""
    settings_path = tmp_path / ".claude" / "settings.local.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text("{ not json", encoding="utf-8")

    result = compile_project(_hooked_project(), tmp_path)
    assert result.ok  # 경고일 뿐 컴파일 자체는 성공
    assert settings_path.read_text(encoding="utf-8") == "{ not json"
    assert any(w.rule == "unmergeable_settings_json" for w in result.warnings)


# ─────────────────────── LOCAL — MCP 배선: .mcp.json + enabledMcpjsonServers ───────────────────────


def _mcp_project(**kwargs) -> PluginProject:
    skill = make_procedural(name="my-skill")
    skill.config.allowed_tools = ["mcp__daedalus__get_project", "Read"]
    return PluginProject(
        name="p", skills=[skill], build_target=BuildTarget.LOCAL, **kwargs,
    )


_DAEDALUS_DEF = {"type": "http", "url": "http://127.0.0.1:8787/mcp"}


def test_referenced_mcp_servers_collects_all_axes():
    agent = make_agent("worker")
    agent.config.tools = ["mcp__github__create_issue"]
    agent.config.mcp_servers = ["memory"]
    project = _mcp_project(agents=[agent])
    assert referenced_mcp_servers(project) == [
        "daedalus", "github", "memory",
    ]


def test_local_wires_mcp_json_and_enables_server(tmp_path):
    project = _mcp_project(mcp_server_defs={"daedalus": dict(_DAEDALUS_DEF)})
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]

    mcp = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp["mcpServers"]["daedalus"] == _DAEDALUS_DEF

    settings = json.loads(
        (tmp_path / ".claude" / "settings.local.json").read_text(encoding="utf-8")
    )
    assert settings["enabledMcpjsonServers"] == ["daedalus"]


def test_local_mcp_merge_preserves_other_servers(tmp_path):
    (tmp_path / ".mcp.json").write_text(json.dumps({
        "mcpServers": {"other": {"command": "other-server"}},
    }), encoding="utf-8")

    project = _mcp_project(mcp_server_defs={"daedalus": dict(_DAEDALUS_DEF)})
    result = compile_project(project, tmp_path)
    assert result.ok

    mcp = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp["mcpServers"]["other"] == {"command": "other-server"}
    assert mcp["mcpServers"]["daedalus"] == _DAEDALUS_DEF


def test_local_mcp_wiring_is_idempotent(tmp_path):
    project = _mcp_project(mcp_server_defs={"daedalus": dict(_DAEDALUS_DEF)})
    compile_project(project, tmp_path)
    compile_project(project, tmp_path)
    settings = json.loads(
        (tmp_path / ".claude" / "settings.local.json").read_text(encoding="utf-8")
    )
    assert settings["enabledMcpjsonServers"] == ["daedalus"]


def test_extra_server_defs_fill_gaps(tmp_path):
    """호출 환경이 아는 정의(예: Daedalus 자신의 서버)가 빈 자리를 채운다 —
    앱이 이미 아는 것을 사용자에게 등록시키지 않는다."""
    project = _mcp_project()  # mcp_server_defs 없음
    result = compile_project(
        project, tmp_path, extra_server_defs={"daedalus": dict(_DAEDALUS_DEF)},
    )
    assert result.ok
    mcp = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp["mcpServers"]["daedalus"] == _DAEDALUS_DEF
    assert not any(w.rule == "missing_mcp_server_def" for w in result.warnings)


def test_project_defs_override_extra(tmp_path):
    """프로젝트에 명시된 정의가 환경 주입보다 우선한다 — 사용자가 적은 것이 진실."""
    mine = {"type": "http", "url": "http://127.0.0.1:9000/mcp"}
    project = _mcp_project(mcp_server_defs={"daedalus": mine})
    result = compile_project(
        project, tmp_path, extra_server_defs={"daedalus": dict(_DAEDALUS_DEF)},
    )
    assert result.ok
    mcp = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp["mcpServers"]["daedalus"] == mine


def test_local_missing_server_def_warns(tmp_path):
    """참조는 있는데 정의가 없으면 배선하지 못한 사실을 경고로 알린다 —
    조용히 빠지면 설치 후 스킬이 죽은 도구를 가리키는 이유를 알 수 없다."""
    project = _mcp_project()  # mcp_server_defs 없음
    result = compile_project(project, tmp_path)
    assert result.ok
    assert not (tmp_path / ".mcp.json").exists()
    warns = [w for w in result.warnings if w.rule == "missing_mcp_server_def"]
    assert len(warns) == 1
    assert "daedalus" in warns[0].message


def test_marketplace_does_not_wire_mcp(tmp_path):
    """MCP 배선은 LOCAL 전용 — 마켓플레이스 스테이징 산출은 불변이다."""
    skill = make_procedural(name="my-skill")
    skill.config.allowed_tools = ["mcp__daedalus__get_project"]
    project = PluginProject(
        name="p", skills=[skill],
        mcp_server_defs={"daedalus": dict(_DAEDALUS_DEF)},
    )
    result = compile_project(project, tmp_path)
    assert result.ok
    assert not (tmp_path / ".mcp.json").exists()
    assert not any(w.rule == "missing_mcp_server_def" for w in result.warnings)


# ─────────────────────── LOCAL — files/ 안전 ───────────────────────


def test_local_files_copy_does_not_delete_user_files(tmp_path):
    """LOCAL의 out_dir는 사용자의 작업 폴더다 — 기존 files/를 지우면 사용자
    파일이 사라진다. 덮어쓰기 복사만 한다."""
    src = tmp_path / "plugin-src" / "files"
    src.mkdir(parents=True)
    (src / "tpl.md").write_text("템플릿", encoding="utf-8")

    target = tmp_path / "workdir"
    (target / "files").mkdir(parents=True)
    (target / "files" / "user-data.csv").write_text("소중한 것", encoding="utf-8")

    skill = make_procedural(name="my-skill")
    project = PluginProject(name="p", skills=[skill], build_target=BuildTarget.LOCAL)
    result = compile_project(project, target, files_dir=src)
    assert result.ok

    assert (target / "files" / "user-data.csv").exists(), "사용자 파일이 지워졌다"
    assert (target / "files" / "tpl.md").exists()


def test_marketplace_files_copy_still_clears_stale(tmp_path):
    """MARKETPLACE 스테이징은 종전대로 삭제 후 복사 — 스테일 잔존 방지."""
    src = tmp_path / "plugin-src" / "files"
    src.mkdir(parents=True)
    (src / "new.md").write_text("새것", encoding="utf-8")

    out = tmp_path / "out"
    (out / "files").mkdir(parents=True)
    (out / "files" / "stale.md").write_text("옛것", encoding="utf-8")

    skill = make_procedural(name="my-skill")
    project = PluginProject(name="p", skills=[skill])
    result = compile_project(project, out, files_dir=src)
    assert result.ok
    assert not (out / "files" / "stale.md").exists()
    assert (out / "files" / "new.md").exists()


# ─────────────────────── expand_root_token (WP-RT) ───────────────────────


def test_expand_root_leaves_raw_cc_variables_untouched():
    """확장 대상은 ${ROOT}뿐 — 사용자가 직접 쓴 CC 변수는 건드리지 않는다."""
    text = "파일: ${ROOT}/files/a.txt, 스크립트: ${CLAUDE_PLUGIN_ROOT}/scripts/run.sh"

    local = PluginProject(name="p", build_target=BuildTarget.LOCAL)
    out = expand_root_token(text, local)
    assert "${CLAUDE_PROJECT_DIR}/files/a.txt" in out
    assert "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" in out


def test_expand_root_without_project_is_marketplace():
    assert expand_root_token("${ROOT}/files/a.txt") == "${CLAUDE_PLUGIN_ROOT}/files/a.txt"


# ─────────────────────── WP-RT: 구버전 본문 마이그레이션 ───────────────────────


def test_legacy_file_ref_migrated_on_load():
    """구버전 프로젝트를 열면 files/ 참조가 ${ROOT}로 바뀐다 — 사용자 조치 불필요."""
    from daedalus.model.serialize import deserialize_project, serialize_project

    skill = make_procedural(name="my-skill", body="참조: ${ROOT}/files/doc.txt")
    data = serialize_project(PluginProject(name="p", skills=[skill]))
    # 저장 파일을 구버전 형태로 되돌린다
    data["format"] = 1
    data["skills"][0]["body"] = "참조: ${CLAUDE_PLUGIN_ROOT}/files/doc.txt"

    loaded = deserialize_project(data)
    assert loaded.skills[0].body == "참조: ${ROOT}/files/doc.txt"


def test_legacy_non_files_usage_not_migrated():
    """files/ 외 용도는 무엇을 의도했는지 알 수 없으므로 건드리지 않는다 —
    검증 경고(plugin_root_in_local_build)가 짚는다."""
    from daedalus.model.serialize import deserialize_project, serialize_project

    skill = make_procedural(name="my-skill", body="x")
    data = serialize_project(PluginProject(name="p", skills=[skill]))
    data["format"] = 1
    data["skills"][0]["body"] = "스크립트: ${CLAUDE_PLUGIN_ROOT}/scripts/run.sh"

    loaded = deserialize_project(data)
    assert loaded.skills[0].body == "스크립트: ${CLAUDE_PLUGIN_ROOT}/scripts/run.sh"


def test_local_gate_rejection_writes_nothing(tmp_path):
    """검증 게이트 에러로 거부되면 설치 배선(JSON 수정)도 하지 않는다 —
    반쪽 설치가 남으면 안 된다."""
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.fsm.state import SimpleState

    real = SimpleState(name="real")
    orphan = SimpleState(name="orphan")
    bad_fsm = StateMachine(name="bad", initial_state=orphan, states=[real])
    skill = make_procedural(name="bad-skill", fsm=bad_fsm)
    project = PluginProject(
        name="p", skills=[skill], build_target=BuildTarget.LOCAL,
        mcp_server_defs={"daedalus": dict(_DAEDALUS_DEF)},
    )

    result = compile_project(project, tmp_path)
    assert not result.ok
    assert result.written == []
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".mcp.json").exists()
