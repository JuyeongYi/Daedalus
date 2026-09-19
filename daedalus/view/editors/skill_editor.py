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

from daedalus.model.plugin.agent import Agent
from daedalus.model.plugin.skill import Skill

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
    """**스킬** 편집기 — ComponentEditor + 능력에 따른 우측 패널.

    생산 경로에서 에이전트는 `AgentEditor`가 맡는다(`app._open_component`).
    여기에 에이전트를 넘겨도 터지지는 않지만 **포트 패널은 붙지 않는다** —
    그 패널은 AgentEditor가 따로 만들기 때문에, 둘 다 그리면 같은 목록을
    가리키는 패널이 두 벌 생긴다.
    """

    skill_changed = Signal()

    def __init__(
        self,
        component: Skill | Agent,
        on_notify_fn: Callable[[], None] | None = None,
        parent: QWidget | None = None,
        project_vm=None,
    ) -> None:
        super().__init__(parent)
        from daedalus.view.editors.component_editor import ComponentEditor
        from daedalus.view.panels.file_panel import SkillFilesPanel

        from daedalus.model.plugin.placement import is_state_placeable
        from daedalus.model.plugin.roles import Bucket
        from daedalus.model.plugin.skill import is_reference_usage

        right_widgets: list[QWidget] = []
        # 입력 경로 편집 패널은 없다(WP-IP) — (출처, 트리거)가 경로를 특정하고,
        # 무엇을 넘기는지는 출처가 자기 출력 포트에 적는다.
        # **포트를 갖는 것은 "단일 배치되는 노드"다**(WP-2d): 워크플로 단계로
        # 한 번 놓이는 컴포넌트만 갈래를 선언할 의미가 있다. 종류를 열거하던
        # 자리인데, 그러면 종류가 하나 늘 때마다 여기 빠뜨려 GUI에서 출력
        # 추가가 불가능해진다(WrappedSkill이 실제로 그랬다 — 사용자 보고).
        # 참조 용도로 고정된 wrapped·참조 스킬은 REFERENCE라 자동으로 빠진다
        # (사용자 확정 2026-09-07).
        # 버킷 게이트는 **이 편집기가 맡는 표면**을 긋는다 — 에이전트도
        # PLACEMENT=STATE이지만 그 포트 패널은 AgentEditor가 만든다.
        if component.BUCKET is Bucket.SKILLS and is_state_placeable(component):
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

        # 프론트매터 표 키 — **config.kind가 단일 진실**이다(컴파일러·MCP와 동일).
        kind = component.config.kind

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
