# daedalus/view/canvas/node_badges.py
"""노드 뱃지 로직 — 프론트매터 enum/bool 시각화.

badges_for(component) → list[tuple[str, str]]  (이모지, 툴팁)

노이즈 방지 원칙: config의 dataclass 선언 기본값과 **다른** 값만 뱃지화.
기본값 조회는 dataclasses.fields() 기반 (_declared_default).
"""
from __future__ import annotations

import dataclasses
from typing import Any


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _declared_default(obj: object, attr: str) -> object:
    """dataclass 선언 기본값(default / default_factory)을 조회한다.

    필드를 찾지 못하면 sentinel _MISSING을 반환한다.
    """
    if dataclasses.is_dataclass(obj):
        for f in dataclasses.fields(obj):  # type: ignore[arg-type]
            if f.name != attr:
                continue
            if f.default is not dataclasses.MISSING:
                return f.default
            if f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
                return f.default_factory()  # type: ignore[misc]
            return _MISSING
    return _MISSING


_MISSING = object()  # sentinel — "선언 기본값 없음"


def _differs(config: object, attr: str) -> tuple[bool, Any]:
    """(다른가, 현재값) 반환. config에 attr이 없으면 (False, None)."""
    current = getattr(config, attr, _MISSING)
    if current is _MISSING:
        return False, None
    default = _declared_default(config, attr)
    if default is _MISSING:
        # default 없는 필드는 required — 값 자체를 비교 기준 없이 노이즈 없음 처리
        return False, current
    differs = current != default
    return differs, current


# ---------------------------------------------------------------------------
# 위임 뱃지 (DelegationDef 전용)
# ---------------------------------------------------------------------------

def _delegation_badges(ref: object) -> list[tuple[str, str]]:
    """DelegationDef ref → (이모지, 툴팁) 목록. 비-DelegationDef는 []."""
    from daedalus.model.plugin.delegation import (
        CompositionMode,
        DelegationDef,
        WaitMode,
    )
    if not isinstance(ref, DelegationDef):
        return []
    result: list[tuple[str, str]] = []
    if ref.wait_mode is WaitMode.FIRE_AND_FORGET:
        result.append(("🔥", "위임 후 즉시 진행 (fire-and-forget)"))
    if ref.composition is CompositionMode.GUIDED:
        result.append(("✨", "구성 자동 결정 (guided)"))
    return result


# ---------------------------------------------------------------------------
# 모델 뱃지 이모지 매핑
# ---------------------------------------------------------------------------
from daedalus.model.plugin.enums import ModelType

_MODEL_EMOJI: dict[ModelType, str] = {
    ModelType.OPUS: "Ⓞ",
    ModelType.SONNET: "Ⓢ",
    ModelType.HAIKU: "Ⓗ",
}


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def badges_for(component: object) -> list[tuple[str, str]]:
    """component의 config를 읽어 기본값과 다른 필드를 뱃지 목록으로 반환한다.

    Returns:
        list of (emoji, tooltip) tuples, empty list if no notable values.
    """
    # DelegationDef: config 없음 — wait_mode/composition 뱃지만
    from daedalus.model.plugin.delegation import DelegationDef
    if isinstance(component, DelegationDef):
        return _delegation_badges(component)

    config = getattr(component, "config", None)
    if config is None:
        return []

    result: list[tuple[str, str]] = []

    # user_invocable — 기본값 대비 변화만 뱃지
    diff, val = _differs(config, "user_invocable")
    if diff:
        if val:
            result.append(("↪", "유저 직접 호출 가능"))
        else:
            result.append(("⛔", "유저 호출 차단"))

    # disable_model_invocation=True (기본 False)
    diff, val = _differs(config, "disable_model_invocation")
    if diff and val:
        result.append(("🚫", "모델 자동 호출 금지"))

    # context=FORK (기본 INLINE)
    from daedalus.model.plugin.enums import SkillContext
    diff, val = _differs(config, "context")
    if diff and val is SkillContext.FORK:
        result.append(("🍴", "포크 컨텍스트"))

    # model != INHERIT
    diff, val = _differs(config, "model")
    if diff and isinstance(val, ModelType) and val in _MODEL_EMOJI:
        emoji = _MODEL_EMOJI[val]
        result.append((emoji, f"모델 고정: {val.value}"))

    # effort HIGH/MAX
    from daedalus.model.plugin.enums import EffortLevel
    diff, val = _differs(config, "effort")
    if diff and val in (EffortLevel.HIGH, EffortLevel.MAX):
        result.append(("⚡", f"effort: {val.value}"))

    # hooks 비어있지 않은 dict
    diff, val = _differs(config, "hooks")
    if diff and isinstance(val, dict) and val:
        result.append(("🪝", "훅 부착"))

    return result
