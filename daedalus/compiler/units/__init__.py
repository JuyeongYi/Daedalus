# daedalus/compiler/units/
"""컴파일 참여자 — 산출 종류 하나 = 단위 하나 (WP-5).

모듈 방향은 단방향이다::

    emit/ · workspace · wiring
        ↑
    units/{paths, context, base, gate, sink}      ← 공통 계약
        ↑
    units/{components, hooks, docs, trees, install}  ← 12개 단위
        ↑
    units/registry  (UNITS · UNIT_BY_ID · Planner)
        ↑
    compiler/plan (파사드) → compiler/project_compiler (게이트 + 루프)

여기서 재-export하는 이름이 단위 계층의 공개 표면이다.
"""
from __future__ import annotations

from daedalus.compiler.units.base import (
    CompileUnit,
    CopyUnit,
    MergeUnit,
    OutputMode,
    Phase,
    PlannedOutput,
    TextUnit,
)
from daedalus.compiler.units.context import CompileContext
from daedalus.compiler.units.gate import Gate
from daedalus.compiler.units.registry import (
    PLANNER,
    UNIT_BY_ID,
    UNITS,
    Planner,
    unit_for,
)
from daedalus.compiler.units.sink import MergeOutcome, OutputSink

__all__ = [
    "CompileContext",
    "CompileUnit",
    "CopyUnit",
    "Gate",
    "MergeOutcome",
    "MergeUnit",
    "OutputMode",
    "OutputSink",
    "PLANNER",
    "Phase",
    "PlannedOutput",
    "Planner",
    "TextUnit",
    "UNITS",
    "UNIT_BY_ID",
    "unit_for",
]
