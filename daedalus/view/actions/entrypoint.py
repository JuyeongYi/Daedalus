# daedalus/view/actions/entrypoint.py
"""진입점 프리셋 — user_invocable × disable_model_invocation 세트 지정 (A8).

두 필드는 따로 켜고 끄는 것이 아니라 **네 가지 의미** 중 하나를 고르는 것이다.
따로 두면 "user-invocable인데 모델 인보크도 막힌 진입점"과 "아무 데서도 부를 수
없는 죽은 노드"(False/True)를 실수로 만들 수 있고, 실제로 무엇을 의도했는지
프론트매터만 봐서는 알기 어렵다. 프리셋은 뜻을 이름으로 고르게 한다.

**tri-state가 전제다**(A8): None = 미지정(프론트매터 키 생략 → CC 기본값 위임).
"일반 상태로"는 그 미지정 상태이고, "진입점으로"는 같은 실효 동작을 **못 박은**
선언이라 서로 다르다.

캔버스 노드 우클릭과 스킬 에디터 프론트매터 패널이 **이 모듈을 공유한다**.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from daedalus.model.plugin.enums import FieldVisibility, SkillField
from daedalus.model.plugin.field_matrix import SKILL_FIELD_MATRIX

#: 프리셋이 세트로 지정하는 두 config 속성.
USER_INVOCABLE_ATTR = "user_invocable"
DISABLE_MODEL_ATTR = "disable_model_invocation"


class EntryPreset(Enum):
    """진입 의미론 프리셋 4종."""

    ENTRY = "entry"            # 유저도 모델도 시작 가능
    USER_ONLY = "user_only"    # 슬래시로만 시작
    PURE = "pure"              # 체인 중간 — 모델 인보크만
    DEFAULT = "default"        # 미지정 — CC 기본값에 위임


@dataclass(frozen=True)
class EntryPresetSpec:
    """프리셋 하나 — 표시 문구와 두 필드의 목표값."""

    preset: EntryPreset
    label: str
    description: str
    user_invocable: bool | None
    disable_model_invocation: bool | None


#: 표시 순서 = 메뉴/콤보 순서 (단일 진실 — 캔버스와 에디터가 같은 순서를 보인다).
ENTRY_PRESETS: tuple[EntryPresetSpec, ...] = (
    EntryPresetSpec(
        EntryPreset.ENTRY, "진입점으로",
        "유저도 모델도 시작할 수 있다 (user-invocable: true)",
        user_invocable=True, disable_model_invocation=False,
    ),
    EntryPresetSpec(
        EntryPreset.USER_ONLY, "유저 전용 진입점으로",
        "슬래시 명령으로만 시작한다 (모델 자동 호출 금지)",
        user_invocable=True, disable_model_invocation=True,
    ),
    EntryPresetSpec(
        EntryPreset.PURE, "순수 상태로",
        "체인 중간 — 모델 인보크로만 들어온다 (user-invocable: false)",
        user_invocable=False, disable_model_invocation=False,
    ),
    EntryPresetSpec(
        EntryPreset.DEFAULT, "일반 상태로",
        "두 필드 미지정 — 프론트매터 키를 내보내지 않고 CC 기본값에 맡긴다",
        user_invocable=None, disable_model_invocation=None,
    ),
)

_BY_PRESET = {spec.preset: spec for spec in ENTRY_PRESETS}


def spec_for(preset: EntryPreset) -> EntryPresetSpec:
    return _BY_PRESET[preset]


def supports_entry_presets(component: object) -> bool:
    """이 컴포넌트에 프리셋을 적용할 수 있는가.

    두 필드가 **매트릭스에서 OPTIONAL인 종류에만** 노출한다. FIXED인 종류
    (reference/transfer의 `user_invocable` 등)에 프리셋을 걸면 컴파일이
    `fixed_value`를 강제하므로 **설정했는데 아무 일도 일어나지 않는** 상태가
    된다 — 그건 없느니만 못한 UI다. 에이전트는 두 필드 자체가 없다.
    """
    config = getattr(component, "config", None)
    kind = getattr(config, "kind", None)
    matrix = SKILL_FIELD_MATRIX.get(kind) if isinstance(kind, str) else None
    if matrix is None:
        return False
    return all(
        matrix[field].visibility is FieldVisibility.OPTIONAL
        for field in (SkillField.USER_INVOCABLE, SkillField.DISABLE_MODEL)
    )


def current_entry_preset(component: object) -> EntryPreset | None:
    """현재 값에 정확히 대응하는 프리셋. 어느 것도 아니면 None.

    None이 나오는 조합(예: True/None처럼 반쪽만 지정된 상태)도 정상이다 —
    프리셋은 편의 지름길이지 표현 가능한 상태의 전부가 아니다. 그때는 메뉴에
    체크가 하나도 없고, 아무거나 고르면 그 세트로 정규화된다.
    """
    config = getattr(component, "config", None)
    if config is None or not supports_entry_presets(component):
        return None
    user = getattr(config, USER_INVOCABLE_ATTR, None)
    disable = getattr(config, DISABLE_MODEL_ATTR, None)
    for spec in ENTRY_PRESETS:
        if (
            user is spec.user_invocable
            and disable is spec.disable_model_invocation
        ):
            return spec.preset
    return None


def apply_entry_preset(project_vm, component: object, preset: EntryPreset) -> bool:
    """프리셋을 적용한다 — 두 필드가 **1 undo 단위**. 적용했으면 True.

    한 필드씩 되돌아가면 중간에 "아무 데서도 부를 수 없는 노드"(False/True) 같은
    의미 없는 조합을 거치게 된다. 세트로 골랐으니 세트로 되돌아가야 한다.

    이미 그 프리셋이면 아무것도 하지 않고 False를 돌려준다 — 값이 같은데도
    커맨드를 쌓으면 Ctrl+Z가 아무 변화 없는 단계를 세게 된다.
    """
    from daedalus.view.commands.attr_commands import SetAttrCmd
    from daedalus.view.commands.base import MacroCommand

    if not supports_entry_presets(component):
        return False
    config = getattr(component, "config", None)
    if config is None:
        return False

    spec = spec_for(preset)
    targets = (
        (USER_INVOCABLE_ATTR, spec.user_invocable),
        (DISABLE_MODEL_ATTR, spec.disable_model_invocation),
    )
    if all(getattr(config, attr, None) is value for attr, value in targets):
        return False

    name = getattr(component, "name", "?")
    children = [
        SetAttrCmd(
            config, attr, value,
            label=f"'{name}' {attr} → {value}",
            script=f'set_component_field("{name}", "{attr}", {_json(value)})',
        )
        for attr, value in targets
    ]
    project_vm.execute(
        MacroCommand(children, f"'{name}' 진입 설정: {spec.label}")
    )
    return True


def _json(value: bool | None) -> str:
    return "null" if value is None else ("true" if value else "false")
