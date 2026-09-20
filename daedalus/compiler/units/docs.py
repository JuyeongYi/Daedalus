# daedalus/compiler/units/docs.py
"""프로젝트 수준 텍스트 산출 단위 (WP-5, 이동만).

작업 폴더 규칙 문서(LOCAL 전용) · 공통 안내 파일 2종 · 블랙보드 스키마 ·
플러그인 매니페스트 · 마켓플레이스 `.mcp.json`. 다섯 다 "프로젝트 하나에 파일
0..1개"라 구조가 같고, 합류 조건과 렌더 함수만 다르다.
"""
from __future__ import annotations

import json
from pathlib import PurePosixPath

from daedalus.compiler import plan_kinds
from daedalus.compiler.emit import compile_plugin_manifest, compile_schemas_json
from daedalus.compiler.emit.blackboard_tools import (
    bb_server_entry,
    bb_server_name,
    bb_server_needed,
)
from daedalus.compiler.emit.guides import (
    blackboard_guide_referenced,
    compile_guide,
    guide_rel_path,
    workflow_guide_referenced,
)
from daedalus.compiler.token_report import TokenKind
from daedalus.compiler.units.base import PlannedOutput, TextUnit
from daedalus.compiler.workspace import has_manual_frontmatter, render_rule
from daedalus.model.validation import ValidationError


class WorkspaceRuleUnit(TextUnit):
    """`.claude/rules/<이름>.md` — LOCAL 전용 작업 폴더 규칙 문서 (WP-WD/A13)."""

    id = plan_kinds.WORKSPACE_RULE

    def plan(self, ctx, gate) -> list[PlannedOutput]:
        # 마켓플레이스 플러그인은 설치 대상 작업 폴더의 .claude/에 쓸 수 없으므로
        # 계획에 넣지 않는다(경고는 Validator 소관). 규칙 이름은 파일명이 되므로
        # 컴포넌트와 같은 이름 게이트를 통과해야 한다.
        if not ctx.is_local:
            return []
        out: list[PlannedOutput] = []
        for doc in getattr(ctx.project, "rules", None) or []:
            if not doc.has_content():
                continue  # 배출할 내용이 없으면 빈 파일을 만들지 않는다
            gate.check_output_name(doc.name, f"규칙 문서 '{doc.name}'", doc)
            # paths 필드와 본문 수기 프론트매터가 겹치면 `---` 블록이 둘 나간다.
            # 본문은 건드리지 않는다 — 합치려면 사용자의 키를 해석해야 하고,
            # 조용한 변형은 "내가 쓴 게 사라졌다"로 돌아온다(A13).
            if doc.paths and has_manual_frontmatter(doc.body or ""):
                gate.warn(ValidationError(
                    rule="rule_body_frontmatter",
                    message=(
                        f"규칙 '{doc.name}'의 본문이 '---'로 시작하는데 paths 필드도 "
                        f"설정돼 있습니다 — 프론트매터가 두 번 배출되어 뒤의 것이 "
                        f"본문으로 읽힙니다. 본문의 프론트매터를 지우고 그 내용을 "
                        f"paths 필드로 옮기세요."
                    ),
                    source=f"rules/{doc.name}.md",
                    subject=doc,
                ))
            out.append(PlannedOutput(
                rel_path=ctx.cc_prefix / "rules" / f"{doc.name}.md",
                label=f"rules/{doc.name}.md (workspace rule)",
                subject=doc,
                kind=plan_kinds.WORKSPACE_RULE,
                component=doc,
                # ${ROOT} 미확장은 현행 보존이다(T8 — backlog). 규칙 문서 본문의
                # 토큰은 확장 없이 그대로 나간다.
                expands_root=False,
                token_kind=TokenKind.CONTEXT,
            ))
        return out

    def render(self, planned, ctx) -> str:
        # 본문 그대로 + paths 프론트매터(A13). paths가 비면 프론트매터가
        # 아예 나가지 않아 필드 도입 전과 산출이 바이트 단위로 같다.
        return render_rule(planned.component)


class GuideUnit(TextUnit):
    """공통 안내 파일 (WP-FK2 C3) — 루트 직하 `guides/<플러그인>/`.

    **포인터가 하나도 나가지 않으면 계획에 넣지 않는다**: 아무도 읽지 않는
    파일이 산출에 남으면 "이건 뭐냐"가 되고, 토큰 리포트도 쓰이지 않는 비용을
    센다. 가이드가 둘이라 인스턴스도 둘이다 — 종전 `compile_guide` 안의 kind
    디스패치가 인스턴스 선언으로 바뀌었다(C6).
    """

    def __init__(self, kind: str, what: str, referenced) -> None:
        self.id = kind
        self.what = what
        self.referenced = referenced

    def plan(self, ctx, gate) -> list[PlannedOutput]:
        project = ctx.project
        if not self.referenced(project):
            return []
        rel = guide_rel_path(project, self.id)
        return [PlannedOutput(
            rel_path=PurePosixPath(rel),
            label=f"{rel} ({self.what})",
            subject=project,
            kind=self.id,
            component=project,
            expands_root=True,
            token_kind=TokenKind.CONTEXT,
            is_guide=True,
        )]

    def render(self, planned, ctx) -> str:
        return compile_guide(ctx.project, self.id) or ""


class SchemasUnit(TextUnit):
    """블랙보드 스키마 — 정의가 있을 때만 계획에 합류.

    파일 이름이 **프로젝트 이름**인 이유는 WP-NS다: 이전의 고정 경로
    'schemas/schemas.json'은 한 작업 폴더에 ddls 플러그인이 둘 깔리면 나중
    것이 앞의 것을 조용히 덮어썼다(경로 충돌 게이트는 한 번의 컴파일 안에서만
    도므로 잡지 못한다). 이름은 컴파일 게이트가 '^[a-z0-9][a-z0-9-]*$'를
    강제하므로 파일명으로 안전하다.
    """

    id = plan_kinds.SCHEMAS_JSON

    def plan(self, ctx, gate) -> list[PlannedOutput]:
        project = ctx.project
        schemas_text = compile_schemas_json(project)
        if schemas_text is None:
            return []
        return [PlannedOutput(
            rel_path=PurePosixPath("schemas") / f"{project.name}.json",
            label=f"schemas/{project.name}.json (blackboard class definitions)",
            subject=project,
            kind=plan_kinds.SCHEMAS_JSON,
            component=project,
            token_kind=TokenKind.TOTAL_ONLY,
            payload=schemas_text,
        )]

    def render(self, planned, ctx) -> str:
        return planned.payload or ""


class ManifestUnit(TextUnit):
    """plugin.json (플러그인 매니페스트) — MARKETPLACE 빌드에서만 생성한다.

    매니페스트 없이는 산출 디렉토리를 CC 플러그인으로 설치할 수 없다. LOCAL
    빌드는 컴파일이 곧 설치라 매니페스트도 설치 스크립트도 없다 (WP-MW —
    이전의 INSTALL.md/install.ps1/install.sh 동봉은 폐기됐다).
    """

    id = plan_kinds.PLUGIN_MANIFEST

    def plan(self, ctx, gate) -> list[PlannedOutput]:
        if ctx.is_local:
            return []
        return [PlannedOutput(
            rel_path=PurePosixPath(".claude-plugin") / "plugin.json",
            label="plugin.json (플러그인 매니페스트)",
            subject=ctx.project,
            kind=plan_kinds.PLUGIN_MANIFEST,
            component=ctx.project,
            token_kind=TokenKind.TOTAL_ONLY,
        )]

    def render(self, planned, ctx) -> str:
        return compile_plugin_manifest(ctx.project)


class McpJsonUnit(TextUnit):
    """`.mcp.json` — MARKETPLACE 빌드의 플러그인 루트 MCP 서버 정의 (WP-BM).

    블랙보드 stdio 서버(`bb-<플러그인>`)를 플러그인이 **직접 들고 간다**. CC는
    플러그인 루트의 이 파일을 읽어 서버를 띄우고, `${CLAUDE_PLUGIN_ROOT}` 치환도
    여기서 동작한다(실측 2026-09-20 — `docs/design/blackboard.md`). 그래서 설치한
    사람이 손으로 배선할 것이 없다.

    LOCAL 빌드에는 이 단위가 없다 — 컴파일이 곧 설치라 **작업 폴더의**
    `.mcp.json`에 병합해야 하고, 그 경로는 사용자 파일을 읽어 합치는
    `LocalWiringUnit`이 전담한다(같은 파일을 두 단위가 쓰면 뒤가 앞을 덮는다).

    사용자가 정의한 MCP 서버(`mcp_server_defs`)는 여기 싣지 않는다 — 마켓플레이스
    빌드에서 그것은 "설치한 환경에 이미 있어야 하는 것"이고, 에이전트 산출의
    "## Requirements" 단락이 그렇게 말한다. 우리가 소유한 서버만 우리가 싣는다.
    """

    id = plan_kinds.MCP_JSON

    def plan(self, ctx, gate) -> list[PlannedOutput]:
        if ctx.is_local or not bb_server_needed(ctx.project):
            return []
        _warn_if_name_taken(ctx, gate)
        return [PlannedOutput(
            rel_path=PurePosixPath(".mcp.json"),
            label=".mcp.json (blackboard MCP server)",
            subject=ctx.project,
            kind=plan_kinds.MCP_JSON,
            component=ctx.project,
            token_kind=TokenKind.TOTAL_ONLY,
        )]

    def render(self, planned, ctx) -> str:
        entry = {bb_server_name(ctx.project): bb_server_entry(ctx.project)}
        return json.dumps({"mcpServers": entry}, ensure_ascii=False, indent=2) + "\n"


def _warn_if_name_taken(ctx, gate) -> None:
    """사용자 정의 서버가 `bb-<플러그인>` 이름을 이미 쓰고 있으면 경고 (WP-BM).

    두 정의가 같은 이름을 다투면 어느 쪽이 이기든 한쪽이 **조용히** 사라진다 —
    블랙보드 도구가 안 보이거나, 사용자 서버가 엉뚱한 프로세스로 바뀐다.
    """
    name = bb_server_name(ctx.project)
    defs = dict(ctx.extra_server_defs or {})
    defs.update(getattr(ctx.project, "mcp_server_defs", None) or {})
    if name not in defs:
        return
    gate.warn(ValidationError(
        rule="bb_server_name_taken",
        message=(
            f"MCP 서버 이름 '{name}'을 프로젝트 정의가 이미 쓰고 있습니다 — 이 "
            f"이름은 블랙보드 서버가 쓰는 규약 이름({name} = bb-<플러그인 이름>)"
            f"이라 둘 중 하나가 조용히 가려집니다. 사용자 정의 쪽 이름을 바꾸세요."
        ),
        source=name,
        subject=ctx.project,
    ))


#: 가이드 단위 2개 — 선언 순서가 계획 순서다.
GUIDE_UNITS: tuple[GuideUnit, ...] = (
    GuideUnit(plan_kinds.GUIDE_WORKFLOW, "shared workflow guide",
              workflow_guide_referenced),
    GuideUnit(plan_kinds.GUIDE_BLACKBOARD, "shared blackboard guide",
              blackboard_guide_referenced),
)
