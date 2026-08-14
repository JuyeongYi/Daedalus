# tests/compiler/test_build_target.py
"""WP-TG Part C/E: 빌드 타깃(MARKETPLACE/LOCAL) 컴파일."""
from __future__ import annotations

import json

from daedalus.compiler import compile_project
from daedalus.compiler.emit import (
    compile_install_md,
    compile_install_ps1,
    compile_install_sh,
    expand_root_token,
)
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.hook import HookDef, HookEvent
from daedalus.model.project import PluginProject

from tests.compiler.builders import make_agent, make_procedural


# ─────────────────────── MARKETPLACE — 바이트 동일 하위 호환 게이트 ───────────────────────


def test_marketplace_is_default_and_unaffected(tmp_path):
    """build_target을 명시하지 않아도 MARKETPLACE — plugin.json 생성, 설치 산출물 없음."""
    skill = make_procedural(name="my-skill")
    project = PluginProject(name="p", skills=[skill])
    assert project.build_target is BuildTarget.MARKETPLACE

    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    assert (tmp_path / ".claude-plugin" / "plugin.json").exists()
    assert not (tmp_path / "INSTALL.md").exists()
    assert not (tmp_path / "install.ps1").exists()
    assert not (tmp_path / "install.sh").exists()


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


# ─────────────────────── LOCAL — plugin.json 부재 + 설치 산출물 ───────────────────────


def test_local_build_omits_plugin_json(tmp_path):
    skill = make_procedural(name="my-skill")
    project = PluginProject(name="p", skills=[skill], build_target=BuildTarget.LOCAL)
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    assert not (tmp_path / ".claude-plugin").exists()


def test_local_build_emits_install_files(tmp_path):
    skill = make_procedural(name="my-skill")
    project = PluginProject(name="p", skills=[skill], build_target=BuildTarget.LOCAL)
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]

    install_md = tmp_path / "INSTALL.md"
    install_ps1 = tmp_path / "install.ps1"
    install_sh = tmp_path / "install.sh"
    assert install_md.exists()
    assert install_ps1.exists()
    assert install_sh.exists()
    assert {install_md, install_ps1, install_sh} <= set(result.written)

    # 결정적: 두 번 컴파일해도 바이트 동일
    out2 = tmp_path.parent / (tmp_path.name + "-2")
    compile_project(project, out2)
    assert install_md.read_bytes() == (out2 / "INSTALL.md").read_bytes()
    assert install_ps1.read_bytes() == (out2 / "install.ps1").read_bytes()
    assert install_sh.read_bytes() == (out2 / "install.sh").read_bytes()


def test_local_build_still_emits_skills_agents_layout(tmp_path):
    agent = make_agent("worker")
    skill = make_procedural(name="my-skill")
    project = PluginProject(
        name="p", skills=[skill], agents=[agent], build_target=BuildTarget.LOCAL,
    )
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    assert (tmp_path / "skills" / "my-skill" / "SKILL.md").exists()
    assert (tmp_path / "agents" / "worker.md").exists()


def test_local_build_hooks_json_still_generated(tmp_path):
    """LOCAL 빌드도 hooks/hooks.json은 동일 레이아웃으로 배출된다."""
    from daedalus.model.plugin.hook import CommandHook

    hook = HookDef(
        name="fmt-on-edit", description="포맷", event=HookEvent.POST_TOOL_USE,
        handlers=[CommandHook(command="run-formatter")],
    )
    skill = make_procedural(name="my-skill")
    skill.config.hooks = {"fmt-on-edit": {}}
    project = PluginProject(
        name="p", skills=[skill], hook_library=[hook], build_target=BuildTarget.LOCAL,
    )
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    hooks_path = tmp_path / "hooks" / "hooks.json"
    assert hooks_path.exists()
    obj = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert "PostToolUse" in obj["hooks"]


def test_local_build_substitutes_file_refs_in_skill_body(tmp_path):
    body = "참조: ${ROOT}/files/doc.txt 확인하라."
    skill = make_procedural(name="my-skill", body=body)
    project = PluginProject(name="p", skills=[skill], build_target=BuildTarget.LOCAL)
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    text = (tmp_path / "skills" / "my-skill" / "SKILL.md").read_text(encoding="utf-8")
    assert "${CLAUDE_PROJECT_DIR}/files/doc.txt" in text
    assert "${CLAUDE_PLUGIN_ROOT}/files/" not in text
    assert "${ROOT}" not in text


def test_local_build_substitutes_file_refs_in_agent_and_local_skill_body(tmp_path):
    agent = make_agent("worker")
    agent.body = "에이전트 참조: ${ROOT}/files/agent-doc.txt"
    local_skill = make_procedural(
        name="local-helper", body="로컬 참조: ${ROOT}/files/local-doc.txt",
    )
    agent.skills = [local_skill]
    project = PluginProject(name="p", agents=[agent], build_target=BuildTarget.LOCAL)
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]

    agent_text = (tmp_path / "agents" / "worker.md").read_text(encoding="utf-8")
    assert "${CLAUDE_PROJECT_DIR}/files/agent-doc.txt" in agent_text

    local_text = (
        tmp_path / "skills" / "worker--local-helper" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "${CLAUDE_PROJECT_DIR}/files/local-doc.txt" in local_text


def test_expand_root_leaves_raw_cc_variables_untouched():
    """확장 대상은 ${ROOT}뿐 — 사용자가 직접 쓴 CC 변수는 건드리지 않는다.

    files/ 이외 용도의 ${CLAUDE_PLUGIN_ROOT}는 프로젝트 설치 빌드에서 치환되지
    않는 죽은 경로이지만, 무엇을 의도했는지 알 수 없으므로 컴파일러가 임의로
    바꾸지 않고 plugin_root_in_local_build 경고에 맡긴다.
    """
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
    data["skills"][0]["body"] = "참조: ${CLAUDE_PLUGIN_ROOT}/files/doc.txt"

    loaded = deserialize_project(data)
    assert loaded.skills[0].body == "참조: ${ROOT}/files/doc.txt"


def test_legacy_non_files_usage_not_migrated():
    """files/ 외 용도는 무엇을 의도했는지 알 수 없으므로 건드리지 않는다 —
    검증 경고(plugin_root_in_local_build)가 짚는다."""
    from daedalus.model.serialize import deserialize_project, serialize_project

    skill = make_procedural(name="my-skill", body="x")
    data = serialize_project(PluginProject(name="p", skills=[skill]))
    data["skills"][0]["body"] = "스크립트: ${CLAUDE_PLUGIN_ROOT}/scripts/run.sh"

    loaded = deserialize_project(data)
    assert loaded.skills[0].body == "스크립트: ${CLAUDE_PLUGIN_ROOT}/scripts/run.sh"


def test_local_gate_rejection_skips_install_files(tmp_path):
    """검증 게이트 에러로 거부되면 LOCAL 전용 산출물도 쓰지 않는다."""
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.fsm.state import SimpleState

    real = SimpleState(name="real")
    orphan = SimpleState(name="orphan")
    bad_fsm = StateMachine(name="bad", initial_state=orphan, states=[real])
    skill = make_procedural(name="bad-skill", fsm=bad_fsm)
    project = PluginProject(name="p", skills=[skill], build_target=BuildTarget.LOCAL)

    result = compile_project(project, tmp_path)
    assert not result.ok
    assert result.written == []
    assert not (tmp_path / "INSTALL.md").exists()
    assert not (tmp_path / "install.ps1").exists()
    assert not (tmp_path / "install.sh").exists()


# ─────────────────────── 설치 스크립트 텍스트 검증 ───────────────────────


def test_install_md_mentions_structure_and_scripts():
    project = PluginProject(name="my-local-plugin", build_target=BuildTarget.LOCAL)
    text = compile_install_md(project)
    assert "\r" not in text
    assert text.endswith("\n")
    assert "install.ps1" in text
    assert "install.sh" in text
    assert "skills/" in text
    assert "agents/" in text
    assert "files/" in text
    assert "hooks/hooks.json" in text
    assert "settings.json" in text
    assert "my-local-plugin" in text


def test_install_ps1_content_deterministic_and_handles_args():
    text = compile_install_ps1()
    assert "\r" not in text
    assert text.endswith("\n")
    assert "Target" in text
    assert "Usage:" in text  # 인자 미지정 시 사용법 출력 (ASCII — 콘솔 인코딩 안전)
    assert ".claude\\skills" in text
    assert ".claude\\agents" in text
    assert "files" in text
    assert "hooks" in text
    assert text == compile_install_ps1()  # 결정적


def test_install_sh_content_deterministic_and_handles_args():
    text = compile_install_sh()
    assert "\r" not in text
    assert text.endswith("\n")
    assert text.startswith("#!/usr/bin/env bash")
    assert "Usage:" in text  # 인자 미지정 시 사용법 출력 (ASCII — 콘솔 인코딩 안전)
    assert ".claude/skills" in text
    assert ".claude/agents" in text
    assert "files" in text
    assert "hooks" in text
    assert text == compile_install_sh()  # 결정적


# ── 리뷰 반영 회귀 (schemas 복사 · ASCII 메시지) ──


def test_local_install_docs_and_scripts_cover_schemas():
    """schemas/도 설치 대상에 포함된다 — 본문이 schemas/schemas.json을 가리키는데
    설치 경로에서 유실되던 문제 (리뷰 지적 A)."""
    from daedalus.compiler.emit import (
        compile_install_md, compile_install_ps1, compile_install_sh,
    )
    from daedalus.model.project import PluginProject

    md = compile_install_md(PluginProject(name="p"))
    assert "schemas" in md
    ps1 = compile_install_ps1()
    sh = compile_install_sh()
    assert "schemas" in ps1 and "schemas" in sh


def test_install_scripts_messages_are_ascii():
    """스크립트 출력 메시지는 ASCII — Windows PowerShell 5.1(cp949)에서
    한국어가 깨지던 문제 (리뷰 지적 B). 산출은 BOM 없는 UTF-8 규약 유지."""
    from daedalus.compiler.emit import compile_install_ps1, compile_install_sh

    for text in (compile_install_ps1(), compile_install_sh()):
        assert text.isascii(), "설치 스크립트에 비ASCII 문자가 있으면 콘솔에서 깨진다"
