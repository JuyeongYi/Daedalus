# tests/mcp/test_external_tools.py
"""외부 플러그인 카탈로그 MCP 도구 (WP-WR D2) — GUI 카탈로그 창과의 패리티.

list_external_plugins/list_marketplace_folders/add_marketplace_folder/
remove_marketplace_folder/fetch_plugin_skills/set_external_plugins.
등록 파일은 conftest가 격리한다.
"""
from __future__ import annotations

import json

import pytest

from daedalus.model.project import PluginProject


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    win = MainWindow()
    win.set_project(PluginProject(name="p"))
    yield win
    win.close()


@pytest.fixture
def tools(window):
    from daedalus.mcp.tools import DaedalusTools

    return DaedalusTools(window)


@pytest.fixture
def marketplace(tmp_path):
    """플러그인 1개(스킬 2개 + .mcp.json 서버 1개) 픽스처 마켓플레이스 폴더."""
    plugin_dir = tmp_path / "catalog" / "alpha"
    meta = plugin_dir / ".claude-plugin"
    meta.mkdir(parents=True)
    (meta / "plugin.json").write_text(
        json.dumps({"name": "alpha", "description": "Alpha."}), encoding="utf-8"
    )
    for skill in ("review", "lint"):
        sdir = plugin_dir / "skills" / skill
        sdir.mkdir(parents=True)
        (sdir / "SKILL.md").write_text(
            f"---\nname: {skill}\ndescription: Does {skill}.\n---\n", encoding="utf-8"
        )
    (plugin_dir / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"alpha-srv": {"command": "x"}}}), encoding="utf-8"
    )
    return tmp_path / "catalog"


def test_folders_empty_note(tools):
    out = tools.list_external_plugins()
    assert out["marketplace_folders"] == []
    assert "add_marketplace_folder" in out["note"]


def test_add_list_remove_folders(tools, marketplace):
    out = tools.add_marketplace_folder(str(marketplace), "mkt")
    assert out["marketplace_folders"][0]["marketplace"] == "mkt"
    assert tools.list_marketplace_folders()["marketplace_folders"][0]["path"] == str(marketplace)
    assert tools.remove_marketplace_folder(str(marketplace)) == {"removed": str(marketplace)}
    assert tools.list_marketplace_folders()["marketplace_folders"] == []


def test_add_nonexistent_folder_rejected(tools):
    with pytest.raises(ValueError, match="실존"):
        tools.add_marketplace_folder("Z:/no/such/dir")


def test_remove_unknown_folder_rejected(tools):
    with pytest.raises(ValueError, match="등록되지 않은"):
        tools.remove_marketplace_folder("C:/never")


def test_list_external_plugins(tools, marketplace):
    tools.add_marketplace_folder(str(marketplace), "mkt")
    out = tools.list_external_plugins()
    plugins = out["marketplace_folders"][0]["plugins"]
    assert [p["plugin_id"] for p in plugins] == ["alpha@mkt"]
    assert plugins[0]["used"] is False
    assert plugins[0]["mcp_servers"] == ["alpha-srv"]
    sources = [s["source"] for s in plugins[0]["skills"]]
    assert sources == ["alpha@mkt:lint", "alpha@mkt:review"]
    assert out["external_plugins"] == []


def test_set_external_plugins_replace_and_undo(tools, window):
    out = tools.set_external_plugins(["alpha@mkt", "beta@mkt", "alpha@mkt"])
    assert out["new"] == ["alpha@mkt", "beta@mkt"]  # 순서 보존·중복 제거
    assert window._project.external_plugins == ["alpha@mkt", "beta@mkt"]
    tools.undo()
    assert window._project.external_plugins == []
    tools.redo()
    assert window._project.external_plugins == ["alpha@mkt", "beta@mkt"]


def test_set_external_plugins_rejects_empty_id(tools):
    with pytest.raises(ValueError, match="빈 플러그인"):
        tools.set_external_plugins(["ok@mkt", "  "])


def test_used_flag_follows_declaration(tools, marketplace):
    tools.add_marketplace_folder(str(marketplace), "mkt")
    tools.set_external_plugins(["alpha@mkt"])
    plugins = tools.list_external_plugins()["marketplace_folders"][0]["plugins"]
    assert plugins[0]["used"] is True


def test_skill_entries_carry_skill_ref_and_used_by(tools, marketplace):
    """`skill_ref`(WP-B)는 fork 에이전트 skills:에 넣을 마켓 없는 이름이고,
    `used_by`는 그 참조를 config.skills에 가진 에이전트 이름 목록이다
    (원칙 2 — 쓸 수 있는 값은 읽을 수도 있어야 한다)."""
    tools.add_marketplace_folder(str(marketplace), "mkt")
    tools.set_external_plugins(["alpha@mkt"])
    tools.create_agent("helper", kind="fork_agent")
    tools.set_component_field("helper", "skills", ["alpha:review"])

    plugins = tools.list_external_plugins()["marketplace_folders"][0]["plugins"]
    by_name = {s["name"]: s for s in plugins[0]["skills"]}
    assert by_name["review"]["skill_ref"] == "alpha:review"
    assert by_name["review"]["used_by"] == ["helper"]
    assert by_name["lint"]["skill_ref"] == "alpha:lint"
    assert by_name["lint"]["used_by"] == []


def test_get_project_meta_lists_external_plugins(tools):
    tools.set_external_plugins(["alpha@mkt"])
    out = tools.get_project(sections=["meta"])
    assert out["external_plugins"] == ["alpha@mkt"]


def test_reference_skill_has_no_output_ports(tools):
    """참조 스킬은 단일 배치 노드가 아니라 출력 포트를 갖지 않는다."""
    tools.create_skill("ref", kind="reference")
    with pytest.raises(ValueError, match="출력 포트"):
        tools.set_transfer_on("ref", [{"name": "done"}])


# --- 미설치 플러그인 (마켓이 선언만 한 것) ---


def _declare_marketplace(root, name, declared):
    import json as _json
    meta = root / ".claude-plugin"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "marketplace.json").write_text(
        _json.dumps({"name": name, "plugins": declared}), encoding="utf-8"
    )


def test_unfetched_hidden_by_default_but_counted(tools, marketplace):
    _declare_marketplace(marketplace, "mkt", [
        {"name": "alpha"},
        {"name": "remote-only", "description": "아직 안 받음"},
    ])
    tools.add_marketplace_folder(str(marketplace), "mkt")

    out = tools.list_external_plugins()
    names = [p["name"] for p in out["marketplace_folders"][0]["plugins"]]
    assert names == ["alpha"]  # 실물을 읽은 것만
    assert out["unfetched_count"] == 1
    assert "include_unfetched" in out["unfetched_note"]

    full = tools.list_external_plugins(include_unfetched=True)
    plugins = {p["name"]: p for p in full["marketplace_folders"][0]["plugins"]}
    assert set(plugins) == {"alpha", "remote-only"}
    assert plugins["alpha"]["files_from"] == "marketplace"
    # 실물이 없으면 스킬을 알 수 없다
    assert plugins["remote-only"]["has_files"] is False
    assert plugins["remote-only"]["skills"] == []


def test_unfetched_plugin_can_be_declared(tools, window, marketplace):
    """실물이 없어도 **사용 선언은 된다** — 빌드가 의존성을 배선하고 설치는 CC가 한다."""
    _declare_marketplace(marketplace, "mkt", [{"name": "remote-only"}])
    tools.add_marketplace_folder(str(marketplace), "mkt")

    tools.set_external_plugins(["remote-only@mkt"])
    assert window._project.external_plugins == ["remote-only@mkt"]
    full = tools.list_external_plugins(include_unfetched=True)
    plugins = {p["name"]: p for p in full["marketplace_folders"][0]["plugins"]}
    assert plugins["remote-only"]["used"] is True


def test_fetch_plugin_skills_clones_uninstalled(tools, marketplace, monkeypatch):
    """지목했을 때만 받아온다 — 테스트는 인터넷·git 없이 클론을 흉내 낸다."""
    from daedalus.model.plugin import plugin_cache

    _declare_marketplace(marketplace, "mkt", [{
        "name": "remote-only",
        "source": {"source": "git-subdir", "url": "https://github.com/o/r.git",
                   "path": "plugins/x", "sha": "abc"},
    }])
    tools.add_marketplace_folder(str(marketplace), "mkt")

    def _clone(source, dest):
        sdir = dest / source.path / "skills" / "review"
        sdir.mkdir(parents=True)
        (sdir / "SKILL.md").write_text(
            "---\nname: review\ndescription: Reviews code.\n---\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(plugin_cache, "_shallow_clone", _clone)
    monkeypatch.setattr(
        plugin_cache, "cache_dir", lambda home_dir=None: marketplace / "_cache",
    )

    out = tools.fetch_plugin_skills("remote-only@mkt")
    # 클론이라 이름뿐 아니라 설명까지 나오고, source는 그대로 랩핑에 쓴다
    assert out["skills"] == [{
        "name": "review",
        "description": "Reviews code.",
        "source": "remote-only@mkt:review",
    }]


def test_fetch_plugin_skills_reads_local_when_files_present(tools, marketplace):
    """실물이 이미 있으면 받지 않는다 — 그 자리에서 읽어 돌려준다."""
    tools.add_marketplace_folder(str(marketplace), "mkt")
    out = tools.fetch_plugin_skills("alpha@mkt")
    assert out["has_files"] is True
    assert out["files_from"] == "marketplace"
    assert [s["name"] for s in out["skills"]] == ["lint", "review"]


def test_fetch_plugin_skills_unknown_id_rejected(tools, marketplace):
    tools.add_marketplace_folder(str(marketplace), "mkt")
    with pytest.raises(ValueError, match="카탈로그에"):
        tools.fetch_plugin_skills("nope@mkt")


# --- 외부 에이전트에는 훅을 붙일 수 없다 (프론트매터 매트릭스 게이트) ---


def _external_agent(window, name="reviewer"):
    from daedalus.model.plugin.agent import ExternalAgent
    from daedalus.model.plugin.config import ExternalAgentConfig

    agent = ExternalAgent(
        name=name, description="d",
        config=ExternalAgentConfig(source="alpha@mkt:review"),
    )
    window._project.agents.append(agent)
    return agent


def test_set_component_hooks_rejects_external_agent(tools, window):
    """산출 파일이 없는 종류는 훅을 받지 않는다 — 조용한 no-op 대신 거절(원칙 5).

    붙여 두면 저장·직렬화까지는 되지만 컴파일에는 닿지 않는다(프론트매터가
    나갈 파일 자체가 없다). 판정의 실체는 `component_supports_hooks` 하나이고
    GUI 폼도 같은 매트릭스를 읽는다.
    """
    agent = _external_agent(window)
    tools.create_hook("guard", event="PreToolUse", command="echo hi")
    with pytest.raises(ValueError, match="훅을 붙일 수 없습니다"):
        tools.set_component_hooks("reviewer", ["guard"])
    assert not (agent.config.hooks or {})


def test_set_component_hooks_accepts_a_skill(tools):
    """대조군 — `hooks` 행이 있는 종류는 그대로 받는다."""
    tools.create_skill("step", kind="procedural")
    tools.create_hook("guard", event="PreToolUse", command="echo hi")
    out = tools.set_component_hooks("step", ["guard"])
    assert out == {"component": "step", "hooks": ["guard"]}


# ────────── WP-C: 에이전트 행의 등록 상태 (레지스트리 🔌 탭과의 패리티) ──────────


@pytest.fixture
def marketplace_with_agent(tmp_path):
    """에이전트 1개짜리 플러그인 — 등록 표면의 모집단."""
    plugin_dir = tmp_path / "agent-catalog" / "hookify"
    meta = plugin_dir / ".claude-plugin"
    meta.mkdir(parents=True)
    (meta / "plugin.json").write_text(
        json.dumps({"name": "hookify"}), encoding="utf-8"
    )
    agents = plugin_dir / "agents"
    agents.mkdir()
    (agents / "doctor.md").write_text(
        "---\nname: doctor\ndescription: Doctors.\n---\n", encoding="utf-8"
    )
    return tmp_path / "agent-catalog"


def test_agent_rows_report_the_registered_kind_and_name(
    tools, marketplace_with_agent
):
    """`registered_as`/`registered_name` — GUI 🔌 탭이 회색으로 보여 주는 것과
    같은 판정이다(쓸 수 있는 값은 읽을 수도 있어야 한다)."""
    tools.add_marketplace_folder(str(marketplace_with_agent), "mkt")

    def _row():
        plugins = tools.list_external_plugins()["marketplace_folders"][0]["plugins"]
        return plugins[0]["agents"][0]

    row = _row()
    assert row["agent_type"] == "hookify:doctor"
    assert row["registered_as"] is None
    assert row["registered_name"] is None
    assert row["already_used"] is False

    out = tools.create_agent(
        "my-doctor", kind="external_fork_agent", source="hookify:doctor"
    )
    assert out["declared_plugin"] == "hookify"
    row = _row()
    assert row["registered_as"] == "external_fork_agent"
    assert row["registered_name"] == "my-doctor"
    assert row["already_used"] is True


def test_registering_the_same_source_twice_is_refused(
    tools, marketplace_with_agent
):
    """역할은 등록 시점에 고정된다 — 두 번째는 **거절**이고 이유를 말한다."""
    tools.create_agent("a", kind="external_agent", source="hookify@mkt:doctor")
    with pytest.raises(ValueError, match="이미"):
        tools.create_agent(
            "b", kind="external_fork_agent", source="hookify:doctor"
        )
    assert [a.name for a in tools._project.agents] == ["a"]
