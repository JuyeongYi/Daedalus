# tests/compiler/test_local_agent_settings.py
"""WP-LA: LOCAL 빌드에서만 나가는 에이전트 프론트매터 hooks / mcpServers.

CC는 **보안상 플러그인 서브에이전트의 hooks/mcpServers/permissionMode
프론트매터를 무시**한다(sub-agents 문서). `.claude/agents/`로 반입되는 LOCAL
빌드에서만 실제로 동작하므로, 이 두 필드는 그때만 배출한다.

산출 형식은 CC 문서의 예제를 그대로 따른다:

    hooks:
      PreToolUse:
        - matcher: "Bash"
          hooks:
            - type: command
              command: "..."
    mcpServers:
      - github
"""
from __future__ import annotations

import pytest

yaml = pytest.importorskip("yaml", reason="프론트매터 파싱 검증에 PyYAML이 필요하다")

from daedalus.compiler.emit import compile_agent
from daedalus.model.plugin.config import AgentConfig
from daedalus.model.plugin.enums import BuildTarget, ModelType, PermissionMode
from daedalus.model.plugin.hook import HookDef, HookEvent
from daedalus.model.project import PluginProject

from tests.compiler.builders import make_agent


def _frontmatter(text: str) -> dict:
    """산출 텍스트의 프론트매터를 실제 YAML로 파싱한다.

    문자열 포함 검사로는 "그럴듯한 들여쓰기"가 통과해 버린다 — CC가 읽는 것은
    YAML이므로 YAML로 읽어 확인한다.
    """
    assert text.startswith("---\n")
    end = text.index("\n---", 4)
    return yaml.safe_load(text[4:end])


def _local_project(agent, hooks=()) -> PluginProject:
    return PluginProject(
        name="p",
        agents=[agent],
        hook_library=list(hooks),
        build_target=BuildTarget.LOCAL,
    )


def _hook(name="guard", event=HookEvent.PRE_TOOL_USE, **kw) -> HookDef:
    from daedalus.model.plugin.hook import CommandHook

    return HookDef(
        name=name,
        description="",
        event=event,
        matcher=kw.get("matcher", ""),
        handlers=[CommandHook(
            script=kw.get("command", "./scripts/check.sh"),
            timeout=kw.get("timeout"),
        )],
    )


# ─────────────────────── hooks ───────────────────────


def test_local_build_emits_hooks_frontmatter():
    agent = make_agent()
    agent.config = AgentConfig(model=ModelType.SONNET, hooks={"guard": {}})
    hook = _hook(matcher="Bash", command="./scripts/validate.sh")
    project = _local_project(agent, [hook])

    fm = _frontmatter(compile_agent(agent, project=project))
    # command는 스크립트 경로다(WP-HS). ${ROOT}는 파일 쓰기 직전에 확장되므로
    # compile_agent 단독 산출에는 중립 토큰이 남아 있다(test_build_target이 확장을 고정).
    assert fm["hooks"] == {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [{"type": "command", "command": "${ROOT}/hooks/scripts/guard.sh"}],
            }
        ]
    }


def test_hook_timeout_emitted_when_set():
    agent = make_agent()
    agent.config = AgentConfig(hooks={"guard": {}})
    project = _local_project(agent, [_hook(matcher="Bash", timeout=5)])

    entry = _frontmatter(compile_agent(agent, project=project))["hooks"]["PreToolUse"][0]
    assert entry["hooks"][0]["timeout"] == 5


def test_matcher_omitted_for_events_that_ignore_it():
    """matcher를 받지 않는 이벤트에서는 키가 없어야 한다.

    (Stop처럼 matcher를 받는 이벤트는 그대로 배출된다 — 어느 이벤트가 받는지는
    스키마 기준이며 NO_MATCHER_EVENTS가 단일 진실이다.)
    """
    agent = make_agent()
    agent.config = AgentConfig(hooks={"oncwd": {}})
    hook = _hook(name="oncwd", event=HookEvent.CWD_CHANGED, matcher="Bash")
    project = _local_project(agent, [hook])

    group = _frontmatter(compile_agent(agent, project=project))["hooks"]["CwdChanged"][0]
    assert "matcher" not in group


def test_matcher_kept_for_events_that_accept_it():
    agent = make_agent()
    agent.config = AgentConfig(hooks={"onstop": {}})
    project = _local_project(agent, [_hook(name="onstop", event=HookEvent.STOP, matcher="x")])

    group = _frontmatter(compile_agent(agent, project=project))["hooks"]["Stop"][0]
    assert group["matcher"] == "x"


def test_multiple_events_keep_declaration_order():
    agent = make_agent()
    agent.config = AgentConfig(hooks={"post": {}, "pre": {}})
    library = [
        _hook(name="pre", event=HookEvent.PRE_TOOL_USE, matcher="Bash"),
        _hook(name="post", event=HookEvent.POST_TOOL_USE, matcher="Edit|Write"),
    ]
    project = _local_project(agent, library)

    hooks = _frontmatter(compile_agent(agent, project=project))["hooks"]
    # HookEvent 선언 순서 = 결정적 키 순서
    assert list(hooks) == ["PreToolUse", "PostToolUse"]


def test_same_event_multiple_hooks_become_separate_groups():
    agent = make_agent()
    agent.config = AgentConfig(hooks={"a": {}, "b": {}})
    library = [
        _hook(name="a", matcher="Bash", command="./a.sh"),
        _hook(name="b", matcher="Read", command="./b.sh"),
    ]
    project = _local_project(agent, library)

    groups = _frontmatter(compile_agent(agent, project=project))["hooks"]["PreToolUse"]
    assert [g["matcher"] for g in groups] == ["Bash", "Read"]


def test_dangling_hook_reference_is_skipped_not_crashed():
    """라이브러리에 없는 이름은 조용히 빠진다 — dangling_hook_ref가 따로 짚는다."""
    agent = make_agent()
    agent.config = AgentConfig(hooks={"missing": {}})
    project = _local_project(agent, [])

    assert "hooks" not in _frontmatter(compile_agent(agent, project=project))


# ─────────────────────── mcpServers ───────────────────────


def test_local_build_emits_declared_mcp_servers():
    agent = make_agent()
    agent.config = AgentConfig(mcp_servers=["github"])
    project = _local_project(agent)

    assert _frontmatter(compile_agent(agent, project=project))["mcpServers"] == ["github"]


def test_mcp_servers_derived_from_tool_names():
    """tools의 mcp__<server>__ 접두에서 추출한 서버도 함께 나간다(요구 환경 단락과 같은 규칙)."""
    agent = make_agent()
    agent.config = AgentConfig(tools=["Read", "mcp__daedalus__get_project"])
    project = _local_project(agent)

    assert _frontmatter(compile_agent(agent, project=project))["mcpServers"] == ["daedalus"]


def test_declared_and_derived_servers_merge_sorted_without_duplicates():
    agent = make_agent()
    agent.config = AgentConfig(
        mcp_servers=["daedalus", "slack"],
        tools=["mcp__daedalus__undo", "mcp__github__list_prs"],
    )
    project = _local_project(agent)

    servers = _frontmatter(compile_agent(agent, project=project))["mcpServers"]
    assert servers == ["daedalus", "github", "slack"]


# ─────────────────────── 마켓플레이스 하위 호환 ───────────────────────


def test_marketplace_build_omits_both_fields():
    """마켓플레이스에서는 CC가 무시하는 필드를 내보내지 않는다."""
    agent = make_agent()
    agent.config = AgentConfig(hooks={"guard": {}}, mcp_servers=["github"])
    project = PluginProject(
        name="p", agents=[agent], hook_library=[_hook(matcher="Bash")],
    )

    fm = _frontmatter(compile_agent(agent, project=project))
    assert "hooks" not in fm and "mcpServers" not in fm


def test_marketplace_still_mentions_requirements_in_body():
    """프론트매터로 못 내보내는 대신 본문 "요구 환경" 단락은 그대로 남는다."""
    agent = make_agent()
    agent.config = AgentConfig(hooks={"guard": {}}, mcp_servers=["github"])
    project = PluginProject(
        name="p", agents=[agent], hook_library=[_hook(matcher="Bash")],
    )

    text = compile_agent(agent, project=project)
    assert "## 요구 환경" in text


def test_local_build_drops_requirement_paragraph():
    """LOCAL은 프론트매터가 실물이므로 "설정 파일을 생성하지 않음" 안내가 거짓이 된다."""
    agent = make_agent()
    agent.config = AgentConfig(hooks={"guard": {}}, mcp_servers=["github"])
    project = _local_project(agent, [_hook(matcher="Bash")])

    assert "## 요구 환경" not in compile_agent(agent, project=project)


def test_no_project_argument_behaves_as_marketplace():
    """project 없이 호출하는 기존 경로는 산출이 바뀌지 않는다(하위 호환)."""
    agent = make_agent()
    agent.config = AgentConfig(hooks={"guard": {}}, mcp_servers=["github"])

    fm = _frontmatter(compile_agent(agent))
    assert "hooks" not in fm and "mcpServers" not in fm


def test_local_build_without_settings_is_unchanged():
    agent = make_agent()
    project = _local_project(agent)

    fm = _frontmatter(compile_agent(agent, project=project))
    assert "hooks" not in fm and "mcpServers" not in fm
    assert fm["name"] == "worker"


# ─────────────────────── 검증 규칙 ───────────────────────


def test_marketplace_warns_about_hooks():
    from daedalus.model.validation import Validator

    agent = make_agent()
    agent.config = AgentConfig(hooks={"guard": {}})
    project = PluginProject(
        name="p", agents=[agent], hook_library=[_hook(matcher="Bash")],
    )

    rules = [e.rule for e in Validator().validate_project(project)]
    assert "unsupported_agent_field_in_marketplace_build" in rules


def test_marketplace_warns_about_non_default_permission_mode():
    from daedalus.model.validation import Validator

    agent = make_agent()
    agent.config = AgentConfig(permission_mode=PermissionMode.BYPASS)
    project = PluginProject(name="p", agents=[agent])

    issues = [
        e for e in Validator().validate_project(project)
        if e.rule == "unsupported_agent_field_in_marketplace_build"
    ]
    assert len(issues) == 1
    assert issues[0].is_warning


def test_default_permission_mode_is_not_warned():
    from daedalus.model.validation import Validator

    agent = make_agent()
    agent.config = AgentConfig(permission_mode=PermissionMode.DEFAULT)
    project = PluginProject(name="p", agents=[agent])

    rules = [e.rule for e in Validator().validate_project(project)]
    assert "unsupported_agent_field_in_marketplace_build" not in rules


def test_local_build_is_not_warned():
    from daedalus.model.validation import Validator

    agent = make_agent()
    agent.config = AgentConfig(
        hooks={"guard": {}}, permission_mode=PermissionMode.BYPASS,
    )
    project = _local_project(agent, [_hook(matcher="Bash")])

    rules = [e.rule for e in Validator().validate_project(project)]
    assert "unsupported_agent_field_in_marketplace_build" not in rules


def test_mcp_only_agent_is_not_double_warned():
    """MCP는 mcp_agent_in_marketplace_build가 이미 짚는다 — 경고가 둘 겹치면 안 된다."""
    from daedalus.model.validation import Validator

    agent = make_agent()
    agent.config = AgentConfig(mcp_servers=["github"])
    project = PluginProject(name="p", agents=[agent])

    rules = [e.rule for e in Validator().validate_project(project)]
    assert rules.count("mcp_agent_in_marketplace_build") == 1
    assert "unsupported_agent_field_in_marketplace_build" not in rules
