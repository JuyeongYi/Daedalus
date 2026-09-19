# daedalus/compiler/units/components.py
"""컴포넌트 산출 단위 — 스킬·에이전트·랩핑 러너 (WP-5, 이동만).

계획 쪽은 `plan._plan_outputs`의 스킬/에이전트 문단, 쓰기 쪽은
`project_compiler`의 `skill`/`agent`/`wrapped_runner` 분기를 그대로 옮겼다.

버킷마다 인스턴스가 하나다(`ComponentUnit(Bucket.SKILLS)` /
`ComponentUnit(Bucket.AGENTS)`) — 산출 경로 규약과 라벨만 다르고 나머지는 같다.

**게이트는 emitter 조회보다 앞에 있다**(§2-g): `c.emits_output()`이 거짓이면
경로도 이름 게이트도 만들지 않고 끝난다. 산출 파일이 없는 종류의 이름은 외부
플러그인의 것일 수 있어 CC 파일명 규약을 따를 이유가 없다. WP-6이 텍스트
조립을 `ComponentEmitter`로 옮기면 이 단위는 게이트와 경로만 남는다.
"""
from __future__ import annotations

from pathlib import PurePosixPath

from daedalus.compiler import plan_kinds
from daedalus.compiler.emit import compile_agent, compile_skill
from daedalus.compiler.emit.wrapped import compile_wrapped_runner, needs_runner_agent
from daedalus.compiler.token_report import TokenKind
from daedalus.compiler.units.base import PlannedOutput, TextUnit
from daedalus.compiler.units.paths import _skill_dir_name
from daedalus.model.plugin.roles import Bucket

#: 러너 행 표지 — 같은 컴포넌트가 두 파일을 낼 때 어느 쪽인지 말한다.
RUNNER_PAYLOAD = "runner"

_LABEL_FMT = {
    Bucket.SKILLS: "스킬 '{name}'",
    Bucket.AGENTS: "에이전트 '{name}'",
}


class ComponentUnit(TextUnit):
    """한 버킷의 컴포넌트가 내는 산출 전부."""

    def __init__(self, bucket: Bucket) -> None:
        self.bucket = bucket
        self.ids = (
            (plan_kinds.SKILL, plan_kinds.WRAPPED_RUNNER)
            if bucket is Bucket.SKILLS else (plan_kinds.AGENT,)
        )

    def _components(self, ctx) -> list:
        project = ctx.project
        if self.bucket is Bucket.SKILLS:
            return list(getattr(project, "skills", None) or [])
        return list(getattr(project, "agents", None) or [])

    def plan(self, ctx, gate) -> list[PlannedOutput]:
        out: list[PlannedOutput] = []
        for component in self._components(ctx):
            # 산출 파일 보유 판정의 실체는 컴포넌트의 `emits_output()` 하나다
            # (원칙 1). 참조 용도 wrapped와 비활성 랩핑 스킬이 여기서 빠진다
            # (둘 다 WP-WR 사용자 확정 2026-09-07). `emit/guides.py`의 포인터
            # 판정이 같은 메서드를 쓰므로 "계획에 오른 집합"과 "포인터 판정 대상
            # 집합"이 어긋날 수 없다.
            if not component.emits_output():
                continue
            label = _LABEL_FMT[self.bucket].format(name=component.name)
            gate.check_output_name(component.name, label, component)
            out.append(PlannedOutput(
                rel_path=self._rel_path(component, ctx),
                label=label,
                subject=component,
                kind=(
                    plan_kinds.SKILL if self.bucket is Bucket.SKILLS
                    else plan_kinds.AGENT
                ),
                component=component,
                expands_root=True,
                token_kind=TokenKind.CONTEXT,
            ))
            # state 용도 랩핑 스킬의 실행 서브에이전트 (WP-WR, 사용자 확정
            # 2026-09-12 — 외부 플러그인 스킬은 서브에이전트에서만 쓴다). 이름이
            # 랩퍼와 같아 사용자 에이전트와는 duplicate_component_name이 이미 막는다.
            if needs_runner_agent(component):
                out.append(PlannedOutput(
                    rel_path=ctx.cc_prefix / "agents" / f"{component.name}.md",
                    label=f"랩핑 스킬 '{component.name}'의 실행 서브에이전트",
                    subject=component,
                    kind=plan_kinds.WRAPPED_RUNNER,
                    component=component,
                    expands_root=True,
                    token_kind=TokenKind.CONTEXT,
                    payload=RUNNER_PAYLOAD,
                ))
        return out

    def _rel_path(self, component, ctx) -> PurePosixPath:
        if self.bucket is Bucket.SKILLS:
            return (
                ctx.cc_prefix / "skills" / _skill_dir_name(component.name) / "SKILL.md"
            )
        return ctx.cc_prefix / "agents" / f"{component.name}.md"

    def render(self, planned, ctx) -> str:
        if planned.payload == RUNNER_PAYLOAD:
            return compile_wrapped_runner(planned.component)
        if self.bucket is Bucket.AGENTS:
            return compile_agent(
                planned.component, project=ctx.project,
                resolved_hooks=ctx.resolved_hooks,
            )
        return compile_skill(
            planned.component, project=ctx.project,
            resolved_hooks=ctx.resolved_hooks,
        )
