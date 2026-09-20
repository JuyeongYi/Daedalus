# daedalus/compiler/units/install.py
"""LOCAL 설치 단위 — 설정 배선과 `.claude/CLAUDE.md` 구역 (WP-5, 이동만).

둘 다 **사용자·팀의 파일을 읽고 병합**한다. "경로 하나 = 산출 하나"라는 계획의
전제를 만족하지 않으므로 행은 `exclusive=False`이고(경로 충돌 게이트·`skipped`
보고 밖), 쓰기 루프가 아니라 `Phase.INSTALL` 단계에서 돈다 — 종전 드라이버에서
진단 스캔 2건 **뒤에** 있던 두 문장이 그 위치를 값으로 보존한 것이다.

`out_root`가 None이면(대상 폴더를 지정하지 않은 dry-run) 폴더를 읽어야 하는
판정만 건너뛴다 — 폴더와 무관한 경고(`missing_mcp_server_def`·
`external_plugin_no_marketplace`)와 토큰 계상은 그대로 낸다. 게이트를
`out_root is not None`으로 좁히면 compile_check의 경고가 통째로 사라진다.
"""
from __future__ import annotations

import json
from pathlib import PurePosixPath

from daedalus.compiler import plan_kinds
from daedalus.compiler.emit import compile_hooks_json, referenced_mcp_servers
from daedalus.compiler.emit.blackboard_tools import (
    bb_server_entry,
    bb_server_name,
    bb_server_needed,
)
from daedalus.compiler.emit.manifest import external_plugin_ids
from daedalus.compiler.token_report import TokenKind
from daedalus.compiler.units.base import MergeUnit, OutputMode, Phase, PlannedOutput
from daedalus.compiler.units.sink import MergeOutcome
from daedalus.compiler.workspace import merge_claude_md
from daedalus.model.validation import ValidationError

#: 토큰 리포트에 실리는 CLAUDE.md 구역 표지 — 파일 경로가 아니라 사람이 읽는 표지다.
_CLAUDE_MD_TOKEN_LABEL = ".claude/CLAUDE.md (plugin section)"


class LocalWiringUnit(MergeUnit):
    """LOCAL 빌드의 설치 배선 — 대상 작업 폴더의 설정 파일을 생성/수정한다.

    병합 자체는 `compiler/wiring.wire_workspace`가 한다("Claude Code 실행"
    메뉴와 공유 — 같은 폴더를 두 경로가 다르게 만지면 안 된다). 여기서는
    무엇을 배선할지(참조 서버 ∩ 정의, 프로젝트 훅)를 정하고, 배선하지 못한
    사실을 경고로 변환한다.

    정의 조회는 프로젝트(`mcp_server_defs`)가 우선이고, 없으면 호출 환경이
    준 `extra_server_defs`(예: Daedalus 앱 자신의 daedalus 서버)로 채운다.
    """

    id = plan_kinds.LOCAL_WIRING

    def plan(self, ctx, gate) -> list[PlannedOutput]:
        if not ctx.is_local:
            return []
        return [PlannedOutput(
            rel_path=PurePosixPath(".mcp.json"),
            label=f".mcp.json + .claude/{ctx.settings_filename} (LOCAL 설치 배선)",
            subject=ctx.project,
            kind=plan_kinds.LOCAL_WIRING,
            component=ctx.project,
            mode=OutputMode.MERGE,
            phase=Phase.INSTALL,
            exclusive=False,
        )]

    def emit(self, planned, ctx, sink) -> None:
        from daedalus.compiler.wiring import wire_workspace

        project = ctx.project
        out_dir = ctx.out_root
        defs = dict(ctx.extra_server_defs or {})
        defs.update(getattr(project, "mcp_server_defs", None) or {})  # 프로젝트가 우선
        referenced = referenced_mcp_servers(project)
        entries = {name: defs[name] for name in referenced if name in defs}
        # 블랙보드 서버(WP-BM)는 **우리가 소유한** 정의라 프로젝트의
        # `mcp_server_defs`를 거치지 않는다 — 사용자가 지울 수 있는 값이면
        # 프론트매터의 도구 권한만 남고 서버가 없는 산출이 나온다(원칙 5).
        # 같은 이름을 사용자가 쓰고 있으면 덮지 않고 경고한다.
        if bb_server_needed(project):
            bb_name = bb_server_name(project)
            if bb_name in defs:
                sink.warn(ValidationError(
                    rule="bb_server_name_taken",
                    message=(
                        f"MCP 서버 이름 '{bb_name}'을 프로젝트 정의가 이미 쓰고 "
                        f"있어 블랙보드 서버를 배선하지 못했습니다 — 이 이름은 "
                        f"블랙보드 서버의 규약 이름(bb-<플러그인 이름>)입니다. "
                        f"사용자 정의 쪽 이름을 바꾸세요."
                    ),
                    source=bb_name,
                    subject=project,
                ))
            else:
                entries[bb_name] = bb_server_entry(project)
        provided = set(ctx.provided_server_names or ())
        for name in referenced:
            if name not in defs and name not in provided:
                # 이 판정은 **대상 폴더와 무관**하므로 out_dir가 None이어도
                # (dry_run) 그대로 낸다 — 폴더를 읽어야 하는 것은 병합
                # (`unmergeable_settings_json`)뿐이고 그쪽만 건너뛴다.
                sink.warn(ValidationError(
                    rule="missing_mcp_server_def",
                    message=(
                        f"MCP 서버 '{name}'가 참조되지만 프로젝트에 서버 정의가 없어 "
                        f".mcp.json에 배선하지 못했습니다. set_mcp_server_def(MCP) 또는 "
                        f"프로젝트 속성에서 정의를 추가하거나, 대상 프로젝트의 "
                        f".mcp.json에 직접 추가하세요."
                    ),
                    source=name,
                    subject=project,
                ))

        # WP-WR — 사용 선언된 외부 플러그인(external_plugins)을 enabledPlugins로
        # 활성화한다. 배선의 단일 진실은 선언이다 — 랩핑 스킬 source를 스캔하지
        # 않는다(사용자 확정. 선언·참조의 어긋남은 검증 경고가 짚는다). 형식은
        # settings 스키마(벤더링 스냅샷) 확인: {"plugin-id@marketplace-id": true}.
        # 마켓 표기가 없는 bare 이름은 enabledPlugins 키가 될 수 없어 경고 후 생략
        # (매니페스트 dependencies와 달리 자기-마켓 해소 규칙이 없다). 이 판정은
        # missing_mcp_server_def처럼 **대상 폴더와 무관**하므로 out_dir 조기 반환
        # 앞에 있어야 한다 — 뒤에 두면 out_dir 없는 compile_check(dry-run)에서
        # 경고가 통째로 사라진다.
        enabled_plugins: dict = {}
        for plugin_id in external_plugin_ids(project):
            if "@" not in plugin_id:
                sink.warn(ValidationError(
                    rule="external_plugin_no_marketplace",
                    message=(
                        f"사용 선언된 외부 플러그인 '{plugin_id}'에 마켓플레이스 "
                        f"표기가 없어 enabledPlugins에 올릴 수 없습니다 — "
                        f"`플러그인@마켓` 형식이면 설치 배선까지 자동입니다."
                    ),
                    source=plugin_id,
                    subject=project,
                ))
                continue
            enabled_plugins[plugin_id] = True

        if out_dir is None:
            return  # 대상 폴더를 모르면 병합 판정 자체가 불가능하다

        hooks_text = compile_hooks_json(project, ctx.resolved_hooks)
        hooks_map = json.loads(hooks_text).get("hooks", {}) if hooks_text else None

        baked_settings = dict(project.workspace_settings or {})
        if enabled_plugins:
            merged = dict(baked_settings.get("enabledPlugins") or {})
            merged.update(enabled_plugins)
            baked_settings["enabledPlugins"] = merged

        wired = wire_workspace(
            out_dir, entries, hooks_map, dry_run=ctx.dry_run,
            # WP-WS — 프로젝트의 작업 폴더 설정 베이크. hooks 키는 wire_workspace가
            # 무시한다(훅 정본은 hook_library — hooks_map 경로 전담).
            # WP-WR — 랩핑 소스 플러그인의 enabledPlugins 합성 포함(모델 불변).
            extra_settings=baked_settings or None,
            settings_name=ctx.settings_filename,
        )
        sink.result.written.extend(wired.written)
        for path in wired.unmergeable:
            sink.warn(ValidationError(
                rule="unmergeable_settings_json",
                message=(
                    f"'{path}'가 올바른 JSON이 아니어서 병합하지 않았습니다 — 기존 "
                    f"내용을 지키기 위해 그대로 두었습니다. 파일을 고친 뒤 다시 "
                    f"컴파일하세요."
                ),
                source=str(path),
                subject=project,
            ))


class ClaudeMdUnit(MergeUnit):
    """`.claude/CLAUDE.md`의 이 플러그인 구역을 갱신한다 (WP-WD/D9).

    이 파일은 **쓰기 전에 읽어야** 하고 결과가 기존 내용에 달려 있어 "경로
    하나 = 산출 하나"라는 계획의 전제와 맞지 않는다 — 그래서 `exclusive=False`
    이고 병합 단위다.

    out_root가 None이면(dry_run에서 대상 폴더를 지정하지 않은 경우) 기존 파일을
    읽을 수 없어 병합 판정 자체가 불가능하다 — 비용만 계상하고 물러난다.
    """

    id = plan_kinds.CLAUDE_MD

    def plan(self, ctx, gate) -> list[PlannedOutput]:
        if not ctx.is_local:
            return []
        return [PlannedOutput(
            rel_path=ctx.cc_prefix / "CLAUDE.md",
            label=".claude/CLAUDE.md (플러그인 구역)",
            subject=ctx.project,
            kind=plan_kinds.CLAUDE_MD,
            component=ctx.project,
            mode=OutputMode.MERGE,
            phase=Phase.INSTALL,
            # ${ROOT} 미확장은 현행 보존이다(T8 — backlog).
            token_kind=TokenKind.CONTEXT,
            exclusive=False,
        )]

    @staticmethod
    def _token(doc) -> tuple[str, str, str] | None:
        """계상할 비용 — 토큰 리포트에는 **이 플러그인의 구역 본문만** 싣는다
        (A5-lite). 파일 전체는 다른 플러그인·사용자가 쓴 내용까지 포함해서 이
        컴파일이 만든 비용이 아니다. 다만 CLAUDE.md는 매 세션 통째로 실리므로
        구역 본문의 비용은 실재한다. **두 경로가 같은 한 자리를 쓴다.**
        """
        if doc is None or not doc.has_content():
            return None
        return (_CLAUDE_MD_TOKEN_LABEL, plan_kinds.CLAUDE_MD, doc.body or "")

    def emit(self, planned, ctx, sink) -> None:
        project = ctx.project
        doc = getattr(project, "claude_md", None)
        token = self._token(doc)
        if ctx.out_root is None:
            if token is not None:
                sink.note_tokens(*token, token_kind=planned.token_kind)
            return
        path = sink.out(planned.rel_path)
        existing, read_error = sink.read_existing(planned)
        if read_error is not None:  # pragma: no cover - 권한 등 환경 의존
            sink.warn(ValidationError(
                rule="unmergeable_claude_md",
                message=f"'{path}'를 읽을 수 없어 병합하지 않았습니다: {read_error}",
                source=str(path), subject=project,
            ))
            return
        if existing is None and (doc is None or not doc.has_content()):
            return  # 쓸 내용도 없고 기존 파일도 없다 — 빈 파일을 만들지 않는다

        text, warning = merge_claude_md(
            existing,
            project.name,
            title=(doc.name if doc is not None and doc.name else project.name),
            body=(doc.body if doc is not None else ""),
        )
        if warning is not None:
            sink.merge(planned, MergeOutcome(text=None, warning=ValidationError(
                rule="unmergeable_claude_md",
                message=f"{warning} 표식을 고친 뒤 다시 컴파일하세요: {path}",
                source=str(path), subject=project,
            )))
            return
        sink.merge(planned, MergeOutcome(text=text, token=token))
