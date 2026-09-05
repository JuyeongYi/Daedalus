# daedalus/model/validation/project_rules/build_target.py
"""빌드 타깃(build_target) 규칙 (이동만 — 동작 불변) — WP-TG Part D / WP-LA."""
from __future__ import annotations

from daedalus.model.plugin.enums import BuildTarget, PermissionMode
from daedalus.model.validation.severity import ValidationError


class _BuildTargetRules:
    """빌드 타깃 규칙 모음 (_ProjectRules 믹스인)."""

    @staticmethod
    def _check_mcp_agent_in_marketplace_build(project) -> list[ValidationError]:
        """mcp_agent_in_marketplace_build — build_target=MARKETPLACE인데 에이전트가
        MCP를 사용(config.tools의 mcp__ 접두 또는 mcp_servers 선언)하면 경고.

        CC는 마켓플레이스 플러그인으로 배포되는 에이전트의 MCP 사용을 지원하지
        않는다(mcpServers 등 프론트매터 미지원) — 로컬 플러그인 빌드로 전환하거나
        MCP 사용을 제거하라고 안내한다. LOCAL 빌드면 이 제약이 없으므로 무경고.
        """
        build_target = getattr(project, "build_target", BuildTarget.MARKETPLACE)
        if build_target is not BuildTarget.MARKETPLACE:
            return []
        errors: list[ValidationError] = []
        for agent in getattr(project, "agents", []):
            cfg = getattr(agent, "config", None)
            tools = getattr(cfg, "tools", None) or []
            mcp_servers = getattr(cfg, "mcp_servers", None) or []
            has_mcp_tool = any(
                isinstance(t, str) and t.startswith("mcp__") for t in tools
            )
            if has_mcp_tool or mcp_servers:
                errors.append(ValidationError(
                    rule="mcp_agent_in_marketplace_build",
                    message=(
                        f"에이전트 '{agent.name}'이 MCP를 사용하지만 빌드 타깃이 "
                        f"마켓플레이스 플러그인입니다 — CC는 플러그인 배포 "
                        f"에이전트의 MCP 사용을 지원하지 않습니다. 로컬 플러그인 "
                        f"빌드로 전환하거나 MCP 사용을 제거하세요."
                    ),
                    source=agent.name,
                    subject=agent,
                    path=(f"agent:{agent.name}",),
                ))
        return errors

    @staticmethod
    def _check_unsupported_agent_fields(project) -> list[ValidationError]:
        """unsupported_agent_field_in_marketplace_build — MARKETPLACE 빌드인데
        에이전트가 `hooks` 또는 기본값 아닌 `permissionMode`를 쓰면 경고 (WP-LA).

        CC는 **보안상 플러그인 서브에이전트의 `hooks`/`mcpServers`/
        `permissionMode` 프론트매터를 무시한다** — 값이 나가긴 해도 아무 일도
        일어나지 않으므로, 설계자가 걸어 둔 제약이 조용히 사라진다. MCP는 이미
        `mcp_agent_in_marketplace_build`가 짚으므로 여기서는 나머지 둘만 본다
        (같은 에이전트에 경고가 둘 겹치지 않게).
        """
        from daedalus.model.plugin.enums import AgentField
        from daedalus.model.plugin.field_matrix import agent_field_supported

        build_target = getattr(project, "build_target", BuildTarget.MARKETPLACE)
        if build_target is not BuildTarget.MARKETPLACE:
            return []
        # MCP(mcp_servers)는 아래 규칙에서 제외한다 — 같은 에이전트에 경고가 둘
        # 겹치지 않도록 mcp_agent_in_marketplace_build가 전담한다.
        checked = [AgentField.HOOKS, AgentField.PERMISSION_MODE]
        errors: list[ValidationError] = []
        for agent in getattr(project, "agents", []):
            cfg = getattr(agent, "config", None)
            unsupported: list[str] = []
            for afield in checked:
                if agent_field_supported(afield, build_target):
                    continue  # 지원되면 문제 없음(집합이 바뀌면 자동으로 따라간다)
                if afield is AgentField.HOOKS and getattr(cfg, "hooks", None):
                    unsupported.append("hooks")
                elif afield is AgentField.PERMISSION_MODE:
                    mode = getattr(cfg, "permission_mode", None)
                    if mode is not None and mode is not PermissionMode.DEFAULT:
                        unsupported.append(f"permissionMode({mode.value})")
            if not unsupported:
                continue
            errors.append(ValidationError(
                rule="unsupported_agent_field_in_marketplace_build",
                message=(
                    f"에이전트 '{agent.name}'의 {', '.join(unsupported)}는 "
                    f"마켓플레이스 플러그인에서 무시됩니다 — CC는 보안상 플러그인 "
                    f"서브에이전트의 hooks/mcpServers/permissionMode 프론트매터를 "
                    f"적용하지 않습니다. 로컬 플러그인 빌드로 전환하세요."
                ),
                source=agent.name,
                subject=agent,
                path=(f"agent:{agent.name}",),
            ))
        return errors
