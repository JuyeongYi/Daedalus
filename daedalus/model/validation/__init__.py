# daedalus/model/validation/
"""모델 검증 — 머신 수준 규칙 + 프로젝트 수준 규칙 (순수 — 파일시스템·Qt 무관).

여기서는 모델만 본다. 파일시스템을 훑어야 아는 규칙(dangling_file_ref 등)은
``compiler/project_compiler.py`` 소관이며, 등급 판정 일관성을 위해 규칙 이름만
``WARNING_RULES``에 등록되어 있다.

WP-RF-3d: 구 단일 모듈 ``model/validation.py``를 패키지로 분해했다 (이동만, 동작
불변). 이 ``__init__``은 **재-export 파사드**다 — 분해 전 모듈의 모든 속성
(public + 테스트가 쓰는 _언더스코어 헬퍼 + 부수 임포트)을 그대로 제공하므로
``from daedalus.model.validation import Validator, _strip_markdown_code`` 같은
기존 임포트가 전부 무수정으로 동작한다.

구획:
  severity.py      — ValidationError(+ is_warning) / WARNING_RULES
  machine_rules.py — 머신 수준 규칙(_MachineRules 믹스인) + SKIPPABLE_RULES
  project_rules.py — 프로젝트 수준 규칙(_ProjectRules 믹스인) + CC_BUILTIN_TOOLS
                     + 코드 스팬 제거 헬퍼(_strip_markdown_code)

``Validator``는 두 믹스인을 합성한 클래스다 — ``Validator._check_*`` 이름은
분해 전과 동일하게 전부 살아 있다(외부 호출부·테스트 호환).
"""
from __future__ import annotations

# ── 분해 전 모듈의 부수 임포트 (파사드 완전성 — dir 기준 public 집합 보존) ──
import re
from dataclasses import dataclass, field

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import ChoiceState, EntryPoint, ExitPoint, TerminateState
from daedalus.model.fsm.state import CompositeState, ParallelState, State
from daedalus.model.fsm.strategy import (
    CompositeEvaluation,
    CompositeExecution,
    EvaluationStrategy,
    ExecutionStrategy,
    ToolEvaluation,
    ToolExecution,
)
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.variable import VariableScope
from daedalus.model.plugin.enums import BuildTarget, PermissionMode

# ── 분해된 구현 재-export ──
from daedalus.model.validation.severity import (
    WARNING_RULES,
    ValidationError,
)
from daedalus.model.validation.machine_rules import (
    SKIPPABLE_RULES,
    _MachineRules,
)
from daedalus.model.validation.project_rules import (
    CC_BUILTIN_TOOLS,
    _CODE_FENCE_RE,
    _INLINE_CODE_RE,
    _ProjectRules,
    _strip_markdown_code,
)


class Validator(_MachineRules, _ProjectRules):
    """검증기 — 머신 수준(_MachineRules) + 프로젝트 수준(_ProjectRules) 합성.

    상태를 갖지 않는 staticmethod 모음이므로 인스턴스화 없이 쓴다
    (``Validator.validate(sm)`` / ``Validator.validate_project(project)``).
    """
