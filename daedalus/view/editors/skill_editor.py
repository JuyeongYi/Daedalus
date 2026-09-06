# daedalus/view/editors/skill_editor.py
"""스킬/에이전트 편집기 + 분해된 패널 3종의 재-export 파사드.

이 모듈은 1,172줄까지 자라 프론트매터 폼·출력 포트 카드·참조 링크라는 서로
독립적인 세 책임을 한 파일에 담고 있었다(위생 규칙 ①). WP-RF 관례대로
**이동만·동작 불변**으로 형제 모듈 셋으로 쪼갰고, 여기 남은 것은 `SkillEditor`
하나다:

- ``frontmatter_panel``  — 필드 매트릭스 기반 프론트매터 폼(`_FrontmatterPanel` 외)
- ``transfer_on_panel``  — 출력 포트 이벤트 카드 목록(`_TransferOnPanel` 외)
- ``reference_link_panel`` — 참조 스킬 링크 관리(`_ReferenceLinkPanel`)

아래 재-export는 파사드다 — `component_editor`/`agent_editor`와 십수 개 테스트가
``from daedalus.view.editors.skill_editor import _FrontmatterPanel`` 처럼 이 경로로
언더스코어 이름까지 직접 임포트하므로, 그 경로가 무수정으로 계속 동작해야 한다
(`tests/view/editors/test_skill_editor_facade.py`가 고정).
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget

from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill, ReferenceSkill, TransferSkill

# --- 재-export 파사드 (분해 전 이름 그대로) -------------------------------
from daedalus.view.editors.frontmatter_panel import (  # noqa: F401
    _COL_CHECK,
    _COL_COUNT,
    _COL_LABEL,
    _COL_WIDGET,
    _DIM_OPACITY,
    _FIELD_ATTR_MAP,
    _FIELD_ENUM_MAP,
    _LIST_FIELDS,
    _TOOL_CANDIDATE_FIELDS,
    _FrontmatterPanel,
    _OptionalRow,
)
from daedalus.view.editors.reference_link_panel import _ReferenceLinkPanel  # noqa: F401
from daedalus.view.editors.transfer_on_panel import (  # noqa: F401
    _COLOR_PRESETS,
    _ColorPickerPopup,
    _EventCard,
    _TransferOnPanel,
)


class SkillEditor(QWidget):
    """스킬/에이전트 편집기 — ComponentEditor + 타입별 우측 패널."""

    skill_changed = Signal()

    def __init__(
        self,
        component: ProceduralSkill | DeclarativeSkill | TransferSkill | ReferenceSkill | AgentDefinition,
        on_notify_fn: Callable[[], None] | None = None,
        parent: QWidget | None = None,
        project_vm=None,
    ) -> None:
        super().__init__(parent)
        from daedalus.view.editors.component_editor import ComponentEditor
        from daedalus.view.panels.file_panel import SkillFilesPanel

        from daedalus.model.plugin.skill import WrappedSkill, is_reference_usage

        right_widgets: list[QWidget] = []
        # 입력 경로 편집 패널은 없다(WP-IP) — (출처, 트리거)가 경로를 특정하고,
        # 무엇을 넘기는지는 출처가 자기 출력 포트에 적는다.
        # WrappedSkill도 워크플로 단계라 출력 포트·에이전트 호출을 procedural과
        # 동일하게 갖는다(WP-WR — 본문만 외부 정본이지 배선은 우리 소유.
        # 이 분기에서 빠져 있어 GUI에서 출력 추가가 불가능했다 — 사용자 보고).
        # 단, **참조 용도로 고정된 wrapped는 제외** — 참조는 워크플로 단계가
        # 아니라 포트가 무의미하다(사용자 확정 2026-09-07).
        if (isinstance(component, (ProceduralSkill, WrappedSkill))
                and not is_reference_usage(component)):
            right_widgets.append(_TransferOnPanel(component.transfer_on, title="⇄ Transfer On"))
            right_widgets.append(
                _TransferOnPanel(component.call_agents, title="🤖 Agent Call", default_color="#8a4a4a", multiline_desc=True)
            )
        # 참조 링크 관리 (A9-7) — 캔버스 우클릭 "링크 추가"와 같은 함수.
        # 참조 용도 wrapped도 같은 패널이다(is_reference_usage 단일 판정).
        if is_reference_usage(component) and project_vm is not None:
            right_widgets.append(_ReferenceLinkPanel(component, project_vm))

        # 스킬별 동봉 파일 (WP-SF) — 전역 파일 독과 **동시에** 떠서, 이 스킬
        # 전용 파일을 본문으로 바로 드래그할 수 있다.
        right_widgets.append(SkillFilesPanel(component))

        # Determine skill_kind for field matrix
        from daedalus.model.plugin.skill import WrappedSkill

        if isinstance(component, WrappedSkill):
            kind = "wrapped"
        elif isinstance(component, ProceduralSkill):
            kind = "procedural"
        elif isinstance(component, TransferSkill):
            kind = "transfer"
        elif isinstance(component, DeclarativeSkill):
            kind = "declarative"
        elif isinstance(component, ReferenceSkill):
            kind = "reference"
        else:
            kind = None

        self._editor = ComponentEditor(
            component,
            right_widgets=right_widgets,
            on_notify_fn=self._on_notify,
            skill_kind=kind,
            project_vm=project_vm,
        )

        self._on_notify_fn = on_notify_fn

        # right_widgets의 changed 시그널 연결
        for w in right_widgets:
            if hasattr(w, "transfer_on_changed"):
                w.transfer_on_changed.connect(self._editor._on_model_changed)

        self._editor.changed.connect(self.skill_changed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._editor)

    def _on_notify(self) -> None:
        self.skill_changed.emit()
        if self._on_notify_fn is not None:
            self._on_notify_fn()
