# daedalus/view/editors/kind_matrix.py
"""컴포넌트 종류 → (프론트매터 규칙 표, 위젯 표, 에이전트 여부) — 얇은 어댑터.

**표를 고르는 규칙의 실체는 여기가 아니다** — `model.plugin.field_matrix.matrix_for`
하나이고 컴파일러·MCP·편집기가 전부 그것을 부른다. 이 모듈이 하는 일은 그 결과에
**뷰에만 있는 위젯 표**(model → view 의존 역전)를 짝지어 주는 것뿐이다.

컴파일러는 뷰를 임포트할 수 없으므로(import 계약) 이 모듈이 단일 진실이 될 수는
없다. 따로 두는 이유는 프론트매터 패널 파일이 분해 예산(800줄)을 넘지 않게
하는 것이다(WP-RF 관례).
"""
from __future__ import annotations

from typing import Any


def matrix_for(component: object) -> tuple[dict[Any, Any], dict[Any, type], bool]:
    """이 컴포넌트의 (규칙 표, 위젯 표, 에이전트 여부).

    Raises:
        ValueError: 모델의 `matrix_for`가 그대로 올린다 — config.kind가 어느
            표에도 없으면 조용한 빈 폼 대신 **이유를 말하는 실패**가 난다
            (예전에 `.get(kind, {})` 폴백이 빈 프론트매터 폼 회귀를 냈다).
    """
    from daedalus.model.plugin.agent import Agent
    from daedalus.model.plugin.field_matrix import matrix_for as model_matrix_for
    from daedalus.view.editors.field_widgets import AGENT_FIELD_WIDGETS, FIELD_WIDGETS

    is_agent = isinstance(component, Agent)
    rules = model_matrix_for(component)
    widget_map = AGENT_FIELD_WIDGETS if is_agent else FIELD_WIDGETS
    return rules, widget_map, is_agent
