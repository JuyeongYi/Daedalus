# daedalus/compiler/units/hooks.py
"""훅 산출 단위 — `hooks/hooks.json`과 훅 스크립트 (WP-5, 이동만).

**계획 단계에서 한 번 렌더해 `payload`에 메모한다.** 종전에는 계획이
`compile_hooks_json`을 부르고(합류 판정) 쓰기 루프가 **다시** 불러 같은 텍스트를
두 번 만들었다 — 순수 함수라 결과는 같지만, "판정과 산출이 같은 텍스트를 본다"는
보장이 코드에 없었다. 이제 계획 행이 텍스트를 들고 다니고 `render()`는 그것을
돌려준다.
"""
from __future__ import annotations

from pathlib import PurePosixPath

from daedalus.compiler import plan_kinds
from daedalus.compiler.emit import compile_hook_scripts, compile_hooks_json
from daedalus.compiler.token_report import TokenKind
from daedalus.compiler.units.base import PlannedOutput, TextUnit
from daedalus.compiler.units.paths import _hook_script_name_conflicts
from daedalus.model.plugin.hook import HOOK_SCRIPT_DIR


class HooksUnit(TextUnit):
    """hooks.json(MARKETPLACE 전용) + 훅 스크립트 파일."""

    ids = (plan_kinds.HOOKS_JSON, plan_kinds.HOOK_SCRIPT)

    def plan(self, ctx, gate) -> list[PlannedOutput]:
        project = ctx.project
        # hooks.json (SETTINGS) — 프로젝트가 참조하는 훅이 있을 때만 계획에 합류.
        # LOCAL은 hooks/hooks.json 파일을 만들지 않는다 — 컴파일이 곧 설치이므로
        # 훅은 <out>/.claude/<settings>의 hooks 섹션에 병합된다(LocalWiringUnit,
        # WP-MW). 훅 스크립트 파일은 양쪽 타깃 모두 hooks/scripts/로 나간다
        # (LOCAL의 커맨드가 ${CLAUDE_PROJECT_DIR}/hooks/scripts/…를 가리킨다).
        hooks_text = compile_hooks_json(project, ctx.resolved_hooks)
        if hooks_text is None:
            return []
        out: list[PlannedOutput] = []
        if not ctx.is_local:
            out.append(PlannedOutput(
                rel_path=PurePosixPath("hooks") / "hooks.json",
                label="hooks.json (lifecycle hooks)",
                subject=project,
                kind=plan_kinds.HOOKS_JSON,
                component=project,
                token_kind=TokenKind.TOTAL_ONLY,
                payload=hooks_text,
            ))
        for error in _hook_script_name_conflicts(project, ctx.resolved_hooks):
            gate.fail(error)
        # 훅 스크립트 — 커맨드는 아무리 짧아도 파일로 나가고 hooks.json에는
        # 루트 기반 경로만 남는다 (WP-HS).
        for filename, body in compile_hook_scripts(project, ctx.resolved_hooks):
            out.append(PlannedOutput(
                rel_path=PurePosixPath(HOOK_SCRIPT_DIR) / filename,
                label=f"훅 스크립트 {filename}",
                subject=project,
                kind=plan_kinds.HOOK_SCRIPT,
                component=project,
                script_name=filename,
                token_kind=TokenKind.TOTAL_ONLY,
                payload=body,
            ))
        return out

    def render(self, planned, ctx) -> str:
        return planned.payload or ""
