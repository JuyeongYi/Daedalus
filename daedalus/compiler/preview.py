# daedalus/compiler/preview.py
"""컴파일 미리보기의 **단일 진입점** (WP-6, 원칙 1·2).

"이 컴포넌트가 컴파일되면 어떤 파일로, 어떤 텍스트로 나가는가"를 묻는 표면이
셋이다 — 캔버스/레지스트리 우클릭, 프론트매터 패널 버튼(`view/actions/preview.py`),
그리고 MCP `compile_preview`(`mcp/tools/query.py`). 종전에는 그 셋이 각자
`isinstance(component, Agent)`로 스킬/에이전트를 갈라 컴파일러를 골랐다 — 같은
질문의 답이 세 벌이라, 종류가 늘면 한 표면만 조용히 틀린 파일 이름을 말한다.

이제 판정은 여기 하나다: `emitter_for(component)`가 종류를 알고, 경로는
`units/paths.output_path`가 안다.

**산출 게이트를 거치지 않는다.** 참조 용도·비활성 랩핑 스킬은 컴파일 산출 파일이
없지만 미리보기는 정상 렌더된다(종전 동작 — 실사용 코퍼스의 랩핑 스킬 9개가 전부
이 경로다). 미리보기의 질문은 "이 컴포넌트가 무엇으로 컴파일되는가"이지 "이번
빌드에 파일이 나가는가"가 아니다. 렌더할 수 없는 것은 **산출 자리가 아예 없는
종류**(`OUTPUT_LOCATION is NONE`)뿐이고, 그때는 `can_preview()`가 거짓이며
`preview_component()`는 이유를 말하는 `ValueError`를 낸다(원칙 5).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from daedalus.compiler.emit.emitters import emitter_for
from daedalus.compiler.token_report import TokenKind
from daedalus.compiler.units.context import CompileContext
from daedalus.compiler.units.paths import output_path
from daedalus.model.plugin.roles import OutputLocation


@dataclass(frozen=True)
class Preview:
    """미리보기 1건 — 텍스트와 **그 텍스트가 어디로 나가는지**."""

    text: str
    #: 산출 계획 kind(`plan_kinds.SKILL` | `AGENT`) — 토큰 리포트 항목 이름.
    plan_kind: str
    #: 토큰 계상 구간 — 실제 컴파일과 같은 구간으로 세야 계기판이 미리보기다.
    token_kind: TokenKind
    #: 산출 루트 기준 상대 경로.
    rel_path: PurePosixPath


def can_preview(component) -> bool:
    """이 컴포넌트를 미리볼 수 있는가 — 산출 자리가 있는 종류인가.

    `emits_output()`이 **아니다**: 그것으로 걸면 참조 용도 랩핑 스킬의 미리보기가
    사라진다(오늘 동작). 진입점은 이 판정으로 액션을 비활성화한다.
    """
    return type(component).OUTPUT_LOCATION is not OutputLocation.NONE


def preview_path(component, project=None) -> PurePosixPath:
    """이 컴포넌트가 나갈 산출 경로 — 텍스트를 만들지 않는다(제목 표시용).

    `project`를 주면 그 빌드 타깃의 경로다(LOCAL은 `.claude/` 밑).
    """
    ctx = CompileContext.build(project, dry_run=True)
    return output_path(
        type(component).OUTPUT_LOCATION, component.name, ctx.cc_prefix,
    )


def preview_component(component, project=None, resolved_hooks=None) -> Preview:
    """이 컴포넌트가 컴파일되면 나올 산출 1건. 파일은 쓰지 않는다.

    `project`를 주면 그래프에서 유도하는 단락(다음 단계·진입 맥락·호출 계약·
    블랙보드)까지 포함된 **실제와 같은** 산출이 된다 — 주지 않으면 컴포넌트
    자체만으로 만들 수 있는 부분만 나온다.
    """
    emitter = emitter_for(component)
    ctx = CompileContext.build(project, dry_run=True)
    return Preview(
        text=emitter.render(component, project, resolved_hooks),
        plan_kind=emitter.plan_kind,
        token_kind=emitter.token_kind,
        rel_path=output_path(
            type(component).OUTPUT_LOCATION, component.name, ctx.cc_prefix,
        ),
    )
