# daedalus/compiler/units/components.py
"""컴포넌트 산출 단위 — 스킬·에이전트 (WP-5 / WP-6).

**이 단위에는 종류 지식이 없다.** "이 컴포넌트가 몇 개의 파일을, 어느 자리에,
어떤 계획 kind로 내는가"는 `emit/emitters.py`의 emitter가 말하고, 여기는 그
선언(`EmittedFile`)을 계획 행으로 옮기며 경로 규약(`units/paths.output_path`)과
이름 게이트를 건다. 한 컴포넌트가 파일을 여럿 내는 종류가 생기면 그 선언도
`outputs()`가 하고 이 파일은 바뀌지 않는다.

버킷마다 인스턴스가 하나다(`ComponentUnit(Bucket.SKILLS)` /
`ComponentUnit(Bucket.AGENTS)`).

**게이트는 emitter 조회보다 앞에 있다**(§2-g): `c.emits_output()`이 거짓이면
경로도 이름 게이트도 만들지 않고 끝난다. 산출 파일이 없는 종류의 이름은 외부
플러그인의 것일 수 있어 CC 파일명 규약을 따를 이유가 없고, `OUTPUT_LOCATION`이
`NONE`인 종류에는 emitter 자체가 없어 `emitter_for`가 먼저 돌면 죽는다.
"""
from __future__ import annotations

from daedalus.compiler import plan_kinds
from daedalus.compiler.emit.emitters import emitter_for
from daedalus.compiler.units.base import PlannedOutput, TextUnit
from daedalus.compiler.units.paths import output_path
from daedalus.model.plugin.roles import Bucket


class ComponentUnit(TextUnit):
    """한 버킷의 컴포넌트가 내는 산출 전부."""

    def __init__(self, bucket: Bucket) -> None:
        self.bucket = bucket
        self.ids = (
            (plan_kinds.SKILL,) if bucket is Bucket.SKILLS
            else (plan_kinds.AGENT,)
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
            # (원칙 1). `OUTPUT_LOCATION`이 NONE인 종류(외부 플러그인 에이전트)
            # 가 여기서 빠진다. `emit/guides.py`의 포인터 판정이 같은 메서드를
            # 쓰므로 "계획에 오른 집합"과 "포인터 판정 대상 집합"이 어긋날 수 없다.
            if not component.emits_output():
                continue
            emitter = emitter_for(component)
            files = emitter.outputs(component)
            if not files:
                continue
            # 이름 게이트는 **컴포넌트당 한 번**이다 — 한 컴포넌트가 파일을
            # 여럿 내도 이름은 하나라 두 번 걸면 같은 에러가 두 줄 나간다.
            gate.check_output_name(component.name, files[0].label, component)
            for emitted in files:
                out.append(PlannedOutput(
                    rel_path=output_path(
                        emitted.location, emitted.name, ctx.cc_prefix,
                    ),
                    label=emitted.label,
                    subject=component,
                    kind=emitted.plan_kind,
                    component=component,
                    expands_root=emitter.expands_root,
                    token_kind=emitter.token_kind,
                ))
        return out

    def render(self, planned, ctx) -> str:
        return emitter_for(planned.component).render(
            planned.component, ctx.project, ctx.resolved_hooks,
        )
