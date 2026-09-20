# daedalus/compiler/emit/blackboard_names.py
"""블랙보드 MCP 서버의 **이름과 배선 값** — 리프 모듈 (WP-BM).

서버 이름·`--schemas` 인자·`.mcp.json` 항목·도구 이름이 여기 있다. 유도
로직(누가 어떤 도구를 받는가)은 한 층 위의 `blackboard_tools.py`다 — 이름은
산문을 만드는 낮은 층(`skill_sections`·`guides`)도 필요로 하는데, 유도는
절 표(`section_plan`)를 읽어야 해서 그 층보다 **위**에 있기 때문이다. 한
모듈에 두면 `skill_sections → blackboard_tools → section_plan → skill_sections`
순환이 된다(`tests/compiler/test_emit_import_acyclic.py`).

**도구 이름은 빌드 타깃이 가른다**(실측 2026-09-20, CC 2.1.278 —
`docs/design/blackboard.md`):

- LOCAL — 서버가 작업 폴더 `.mcp.json`에 실리므로 ``mcp__bb-<플러그인>__<도구>``.
- MARKETPLACE — 서버가 플러그인 `.mcp.json`에 실리므로 CC가 플러그인
  네임스페이스를 붙여 ``mcp__plugin_<플러그인>_bb-<플러그인>__<도구>``가 된다.
  접두 없는 이름은 **존재하지 않는다** — 그것을 `tools:`에 적으면 그 에이전트는
  도구를 하나도 못 본다.
"""
from __future__ import annotations

from daedalus.cli.mcp_server import TOOL_NAMES, server_name
from daedalus.compiler.emit.common import _is_local_build


def plugin_name(project) -> str:
    return getattr(project, "name", "") or "plugin"


def bb_server_name(project) -> str:
    """`.mcp.json`에 실리는 서버 이름 — 실체는 서버 모듈의 규약 함수다."""
    return server_name(plugin_name(project))


def bb_schemas_arg(project) -> str:
    """서버에 넘기는 `--schemas` 값.

    `${ROOT}` 토큰을 쓰지 않는다. 두 타깃의 값이 **확장으로 이어지지 않기**
    때문이다: LOCAL은 작업 폴더 상대 경로(`schemas/<플러그인>.json`)이고
    MARKETPLACE만 `${CLAUDE_PLUGIN_ROOT}`가 필요하다(스키마가 플러그인 안에
    있다). `${ROOT}`를 쓰면 LOCAL에서 `${CLAUDE_PROJECT_DIR}`로 확장되는데,
    그 변수가 `.mcp.json`에서 치환된다는 근거가 없다(원칙 8).
    """
    rel = f"schemas/{plugin_name(project)}.json"
    if _is_local_build(project):
        return rel
    return f"${{CLAUDE_PLUGIN_ROOT}}/{rel}"


def bb_server_entry(project) -> dict:
    """`.mcp.json`의 `mcpServers` 항목 하나 (stdio — CC가 프로세스를 띄운다)."""
    return {
        "command": "daedalus-bb",
        "args": ["--schemas", bb_schemas_arg(project)],
    }


def bb_tool_prefix(project) -> str:
    """도구 이름 접두 — 빌드 타깃이 가른다(모듈 docstring의 실측)."""
    server = bb_server_name(project)
    if _is_local_build(project):
        return f"mcp__{server}__"
    return f"mcp__plugin_{plugin_name(project)}_{server}__"


def bb_tool(project, tool: str) -> str:
    """도구 하나의 **호출 가능한** 이름. 없는 도구를 지목하면 시끄럽게 실패한다."""
    if tool not in TOOL_NAMES:
        raise ValueError(
            f"블랙보드 서버에 없는 도구입니다: {tool!r} — "
            f"등록: {', '.join(TOOL_NAMES)}"
        )
    return f"{bb_tool_prefix(project)}{tool}"


def bb_tool_glob(project) -> str:
    """산문에서 "이 서버의 도구 전부"를 가리키는 표기."""
    return f"{bb_tool_prefix(project)}*"


