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
# 모델 뱃지 이모지 매핑
# ---------------------------------------------------------------------------
from daedalus.model.plugin.enums import ModelType

_MODEL_EMOJI: dict[ModelType, str] = {
    ModelType.OPUS: "Ⓞ",
    ModelType.SONNET: "Ⓢ",
    ModelType.HAIKU: "Ⓗ",
    ModelType.FABLE: "Ⓕ",
}


# ---------------------------------------------------------------------------
# 상태 접근 선언 뱃지 (WP-BB Part C-2) — State.reads/writes
# ---------------------------------------------------------------------------

def state_access_badges(state: object) -> list[tuple[str, str]]:
    """State의 reads/writes 접근 선언 → (이모지, 툴팁) 목록.

    writes가 있으면 ✏(블랙보드 쓰기) 뱃지, reads가 있으면 📖(블랙보드 읽기)
    뱃지 — 둘 다 선언되어 있으면 두 뱃지가 모두 표시된다(노이즈 방지 원칙은
    "선언 있을 때만 렌더"로 지킨다 — 값 자체는 항상 정보성).
    """
    reads = list(getattr(state, "reads", None) or [])
    writes = list(getattr(state, "writes", None) or [])
    result: list[tuple[str, str]] = []
    if writes:
        result.append(("✏", f"블랙보드 쓰기: {', '.join(writes)}"))
    if reads:
        result.append(("📖", f"블랙보드 읽기: {', '.join(reads)}"))
    return result


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def badges_for(component: object) -> list[tuple[str, str]]:
    """component의 config를 읽어 기본값과 다른 필드를 뱃지 목록으로 반환한다.

    Returns:
        list of (emoji, tooltip) tuples, empty list if no notable values.
    """
    config = getattr(component, "config", None)
    if config is None:
        return []
    result: list[tuple[str, str]] = []

    # WP-WR — 랩핑 스킬은 본문의 정본이 외부 스킬이다. 소스를 뱃지로 보인다
    # (미지정도 표시 — 배치는 됐는데 소스가 빈 노드를 화면에서 바로 잡는다).
    if getattr(component, "kind", "") == "wrapped_skill":
        source = getattr(config, "source", None) or "(source 미지정)"
        result.append(("🔗", f"랩핑 스킬 — 본문 정본: {source}"))

    # 진입 의미론 (A8) — user_invocable × disable_model_invocation을 **한 뱃지로**
    # 합친다. 두 필드가 따로 뱃지를 달면 "유저 전용 진입점"에 뱃지가 둘 붙어
    # 같은 사실을 두 번 말하게 된다. tri-state이므로 미지정(None)은 선언 기본값과
    # 같아 _differs가 False — 노이즈 방지 원칙 그대로 뱃지가 없다.
    entry_diff, entry_val = _differs(config, "user_invocable")
    disable_val = getattr(config, "disable_model_invocation", None)
    if entry_diff:
        if entry_val:
            tooltip = (
                "진입점 — /스킬로만 시작 가능 (유저 전용, 모델 자동 호출 금지)"
                if disable_val is True
                else "진입점 — /스킬로 시작 가능"
            )
            result.append(("🚪", tooltip))
        else:
            result.append(("⛔", "유저 호출 차단 — 체인 중간 노드"))

    # disable_model_invocation=True (기본값 대비 변화). 진입점 뱃지가 이미
    # 그 사실을 말했으면 생략한다.
    diff, val = _differs(config, "disable_model_invocation")
    if diff and val and not (entry_diff and entry_val):
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

    # effort HIGH 이상 (HIGH/XHIGH/MAX)
    from daedalus.model.plugin.enums import EffortLevel
    diff, val = _differs(config, "effort")
    if diff and val in (EffortLevel.HIGH, EffortLevel.XHIGH, EffortLevel.MAX):
        result.append(("⚡", f"effort: {val.value}"))

    # hooks 비어있지 않은 dict
    diff, val = _differs(config, "hooks")
    if diff and isinstance(val, dict) and val:
        result.append(("🪝", "훅 부착"))

    return result
