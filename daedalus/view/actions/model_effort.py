# daedalus/view/actions/model_effort.py
"""모델 / effort 지정 — 캔버스와 에디터가 공유하는 쓰기 경로 (A9-2).

에디터에는 이미 콤보가 있다. 여기서 새로 만드는 것은 UI가 아니라 **쓰기
경로의 단일 진실**이다 — 캔버스 우클릭이 config에 직접 쓰면 에디터가 쓰는
`SetAttrCmd` 경로와 갈라져, 같은 값을 바꿨는데 undo 이력이 다르게 남는다.

두 필드는 스킬·에이전트 config에 **같은 이름**으로 있으므로 한 모듈이 둘 다
다룬다(`ComponentConfig.model` / `.effort`).
"""
from __future__ import annotations

from daedalus.model.plugin.enums import EffortLevel, ModelType

MODEL_ATTR = "model"
EFFORT_ATTR = "effort"

#: 표시 순서 — 메뉴/콤보가 이 순서를 그대로 쓴다.
MODEL_CHOICES: tuple[tuple[ModelType, str], ...] = (
    (ModelType.INHERIT, "상속 (inherit)"),
    (ModelType.FABLE, "fable"),
    (ModelType.OPUS, "opus"),
    (ModelType.SONNET, "sonnet"),
    (ModelType.HAIKU, "haiku"),
)

#: effort는 미지정(None)이 있는 tri-state성 필드다 — 첫 항목이 그것이다.
EFFORT_CHOICES: tuple[tuple[EffortLevel | None, str], ...] = (
    (None, "(미지정)"),
    (EffortLevel.LOW, "low"),
    (EffortLevel.MEDIUM, "medium"),
    (EffortLevel.HIGH, "high"),
    (EffortLevel.XHIGH, "xhigh"),
    (EffortLevel.MAX, "max"),
)


def supports_model_effort(component: object) -> bool:
    """config에 두 필드가 있는가 — 스킬·에이전트 전부 True, 빈 노드는 False."""
    config = getattr(component, "config", None)
    return config is not None and hasattr(config, MODEL_ATTR) and hasattr(config, EFFORT_ATTR)


def current_model(component: object) -> ModelType | str | None:
    config = getattr(component, "config", None)
    return getattr(config, MODEL_ATTR, None) if config is not None else None


def current_effort(component: object) -> EffortLevel | None:
    config = getattr(component, "config", None)
    return getattr(config, EFFORT_ATTR, None) if config is not None else None


def set_model(project_vm, component: object, model: ModelType) -> bool:
    """모델 고정을 바꾼다 (undo 가능). 값이 같으면 아무것도 하지 않고 False."""
    return _set(project_vm, component, MODEL_ATTR, model, "모델")


def set_effort(project_vm, component: object, effort: EffortLevel | None) -> bool:
    """effort를 바꾼다 (undo 가능). None = 미지정(프론트매터 키 생략)."""
    return _set(project_vm, component, EFFORT_ATTR, effort, "effort")


def _set(project_vm, component: object, attr: str, value, label: str) -> bool:
    from daedalus.view.commands.attr_commands import SetAttrCmd

    if not supports_model_effort(component):
        return False
    config = component.config  # type: ignore[attr-defined]
    if getattr(config, attr, None) == value:
        return False

    name = getattr(component, "name", "?")
    shown = getattr(value, "value", value)
    project_vm.execute(
        SetAttrCmd(
            config, attr, value,
            label=f"'{name}' {label} → {shown if shown is not None else '(미지정)'}",
            script=f'set_component_field("{name}", "{attr}", "{shown}")',
        )
    )
    return True
