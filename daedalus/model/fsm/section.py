from __future__ import annotations

from enum import Enum


class SkillSection(Enum):
    """스킬 본문 섹션 열거형.

    항목 추가 시 SkillEditor UI가 자동으로 섹션 카드를 추가한다.
    """
    INSTRUCTIONS  = "instructions"   # 항상 활성, 항상 표시
    WHEN_ENTER    = "when_enter"     # on_entry hook
    WHEN_FINISHED = "when_finished"  # on_exit hook
    WHEN_ACTIVE   = "when_active"    # on_active hook
    WHEN_ERROR    = "when_error"     # custom_event hook
    CONTEXT       = "context"        # declarative 배경지식
