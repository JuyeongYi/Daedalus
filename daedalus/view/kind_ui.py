# daedalus/view/kind_ui.py
"""컴포넌트 종류의 **뷰 표면** 한 행 — 아이콘·색·노드 스타일·편집기 (WP-7 ②).

모델의 `kinds.KIND_REGISTRY`가 "종류가 몇 가지인가"의 등록 지점이라면, 여기는
"그 종류가 화면에서 어떻게 보이고 무엇으로 편집되는가"의 등록 지점이다. 예전에는
이 사실이 **뷰 안에서만 열다섯 벌**로 흩어져 있었다(카탈로그 V1~V15):
레지스트리의 `_ICON`·`_sections`·`tab_labels`·`_rebuild` isinstance 사다리,
캔버스의 `_TYPE_STYLE`, 다이얼로그 제목 표, 종류 전환 라벨·툴팁 3표,
`app.py`의 편집기 클래스 전수 열거와 탭 접두, `NO_PLACE_KINDS`.

표가 여럿이면 새 종류는 **조용히** 빠진다 — 아이콘 없는 행, 회색 기본 노드(실제
회귀: 한 종류가 빈 상태와 구분되지 않게 그려졌다, 사용자 보고 2026-09-07),
열리지 않는 편집 탭. 그래서 표는 하나고, 조회는 `ui_for()` 하나이며, 없는 종류는
**이유와 선택지를 말하는 ValueError**다(원칙 5).

**모델이 아니라 뷰에 있는 이유**(import 계약): `QColor`·위젯 팩토리는 Qt이고
core(`model/`·`compiler/`·`mcp/endpoint.py`·`cli/`)는 Qt를 임포트할 수 없다.
두 레지스트리는 **kind 문자열로 연결**하고 임포트 방향은 view → model 한 방향이다.

**자동 생성하지 않는다.** 모델 레지스트리를 순회해 기본값을 만들어 주면 "UI가 없는
종류"가 회색 기본 스타일로 조용히 그려진다 — 그 회귀를 이미 겪었다. 빠뜨리면
`tests/test_kind_registry_parity.py`가 집합 등식으로 실패한다.

**위젯 클래스를 값으로 들지 않는다**(R7): `editor_factory`는
**호출 가능 객체**이고 실제 임포트는 그 안에서 지연된다 — 모듈 임포트만으로 편집기
패키지 전체가 끌려오면 임포트 그래프가 굳는다.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtGui import QColor

from daedalus.model.plugin.agent import AgentDefinition, ExternalAgent, ForkAgent
from daedalus.model.plugin.kinds import KIND_REGISTRY, spec_by_config_kind
from daedalus.model.plugin.skill import (
    AsyncForkSkill,
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    SyncForkSkill,
    TransferSkill,
)

#: 종류 전환 명사형을 라벨에서 유도하는 접미(V12) — 버튼과 상태 문구가 같은
#: 어휘를 쓰게 한다("동기 fork 스킬로 전환" ↔ "동기 fork 스킬로 전환됨").
_SWITCH_SUFFIX = "로 전환"


# ─────────────────────────── 편집기 팩토리 ───────────────────────────

def _skill_editor(component, *, on_notify_fn, project, project_vm):
    """스킬 7종 공통 편집기. `project`는 쓰지 않는다(시그니처 통일용)."""
    from daedalus.view.editors.skill_editor import SkillEditor

    return SkillEditor(
        component, on_notify_fn=on_notify_fn, project_vm=project_vm
    )


def _agent_editor(component, *, on_notify_fn, project, project_vm):
    """에이전트 2종 공통 편집기 — 프로젝트를 받아 참조 패널을 채운다."""
    from daedalus.view.editors.agent_editor import AgentEditor

    return AgentEditor(
        component, on_notify_fn=on_notify_fn, project=project,
        project_vm=project_vm,
    )


# ─────────────────────────── 표 ───────────────────────────

@dataclass(frozen=True)
class KindUI:
    """한 종류의 뷰 표면 전부 — 레지스트리 팔레트·캔버스·편집 탭이 함께 읽는다."""

    icon: str
    """레지스트리 행 아이콘 (V1)."""
    section_label: str
    """레지스트리 섹션 제목 + 탭 툴팁 (V2)."""
    section_color: QColor
    """레지스트리 행 기본 글자색 (V2)."""
    tab_label: str
    """레지스트리 탭 라벨 — 짧게, 전체 이름은 툴팁 (V3)."""
    node_style: tuple[str, str, str, str] | None
    """캔버스 상태 노드 (배경, 테두리, 헤더 라벨, 아이콘). `None` = 상태 노드가 아니다 (V5)."""
    dialog_title: str
    """이름 입력 다이얼로그 제목 (V9)."""
    editor_factory: Callable[..., Any]
    """편집 탭 위젯 팩토리 — `(component, *, on_notify_fn, project, project_vm)` (V13/V14)."""
    tab_prefix: str = ""
    """편집 탭 제목 접두 — 종류가 한눈에 보이게(에이전트 2종만)."""
    switch_label: str | None = None
    """종류 전환 버튼 라벨 — `CONVERT_FAMILY`가 있는 종류만 (V12)."""
    switch_tooltip: str | None = None
    """전환 시 **버려지는 것**을 말하는 툴팁 (V12)."""


#: **뷰의 유일한 종류 표.** 키는 모델의 컴포넌트 `KIND`이고 문자열 리터럴은 쓰지
#: 않는다 — 클래스 선언을 참조해야 kind 어휘가 한 곳에서만 정해진다.
KIND_UI: dict[str, KindUI] = {
    ProceduralSkill.KIND: KindUI(
        icon="⚙",
        section_label="⚙ PROCEDURAL",
        section_color=QColor("#88cc88"),
        tab_label="⚙",
        # 헤더 라벨 "PROCEDURAL"은 형용사라 어색 — 배치는 플러그인 FSM의 상태이므로
        # STATE로 표기 (사용자 확정). 종류 구분은 색·아이콘이 담당.
        node_style=("#1a2a1a", "#4a8a4a", "STATE", "⚙"),
        dialog_title="새 Procedural Skill",
        editor_factory=_skill_editor,
        switch_label="절차형 스킬로 전환",
        switch_tooltip="fork 에이전트 지정을 버립니다.",
    ),
    # fork 스킬 2종 — 서브에이전트에서 도는 단계. 다른 종류와 겹치지 않는 구리색
    # (사용자 확정 2026-09-13 — "색은 아예 별도 색상으로"). 비동기는 진한 구리 + ⏳.
    SyncForkSkill.KIND: KindUI(
        icon="🍴",
        section_label="🍴 SYNC FORK",
        section_color=QColor("#c07a3a"),
        tab_label="🍴",
        node_style=("#2a1f14", "#c07a3a", "STATE", "🍴"),
        dialog_title="새 Sync Fork Skill",
        editor_factory=_skill_editor,
        switch_label="동기 fork 스킬로 전환",
        switch_tooltip=(
            "fork 스킬은 allowed_tools를 쓰지 않아 버립니다. 부른 쪽이 보고를 기다립니다."
        ),
    ),
    AsyncForkSkill.KIND: KindUI(
        icon="🍴⏳",
        section_label="🍴⏳ ASYNC FORK",
        section_color=QColor("#8a5a2a"),
        tab_label="🍴⏳",
        node_style=("#1f1610", "#8a5a2a", "STATE", "🍴⏳"),
        dialog_title="새 Async Fork Skill",
        editor_factory=_skill_editor,
        switch_label="비동기 fork 스킬로 전환",
        switch_tooltip=(
            "fork 스킬은 allowed_tools를 쓰지 않아 버립니다. 보고는 작업 알림으로 옵니다."
        ),
    ),
    DeclarativeSkill.KIND: KindUI(
        icon="📄",
        section_label="📄 DECLARATIVE",
        section_color=QColor("#cccc88"),
        tab_label="📄",
        node_style=("#2a2a1a", "#8a8a4a", "DECLARATIVE", "📄"),
        dialog_title="새 Declarative Skill",
        editor_factory=_skill_editor,
    ),
    # 전이 스킬은 엣지에 붙고, 참조 스킬은 **참조 노드**(ref_node_item)로 그려진다
    # — 둘 다 상태 노드 스타일을 갖지 않는다.
    TransferSkill.KIND: KindUI(
        icon="⚡",
        section_label="⚡ TRANSFER",
        section_color=QColor("#88aacc"),
        tab_label="⚡",
        node_style=None,
        dialog_title="새 Transfer Skill",
        editor_factory=_skill_editor,
    ),
    ReferenceSkill.KIND: KindUI(
        icon="📖",
        section_label="📖 REFERENCE",
        section_color=QColor("#66aaaa"),
        tab_label="📖",
        node_style=None,
        dialog_title="새 Reference Skill",
        editor_factory=_skill_editor,
    ),
    AgentDefinition.KIND: KindUI(
        icon="🤖",
        section_label="🤖 AGENTS",
        section_color=QColor("#cc8888"),
        tab_label="🤖",
        node_style=("#2a1a1a", "#8a4a4a", "AGENT", "🤖"),
        dialog_title="새 Agent",
        editor_factory=_agent_editor,
        tab_prefix="🤖 ",
    ),
    # fork 에이전트는 배치되지 않으므로 노드 스타일이 없다.
    ForkAgent.KIND: KindUI(
        icon="🧩",
        section_label="🧩 FORK AGENTS",
        section_color=QColor("#cc8888"),
        tab_label="🧩",
        node_style=None,
        dialog_title="새 Fork Agent",
        editor_factory=_agent_editor,
        tab_prefix="🧩 ",
    ),
    # 외부 플러그인 에이전트(WP-9)도 배치되면 플러그인 FSM의 상태라 헤더는
    # AGENT지만, **정본이 외부에 있고 산출 파일이 없다**는 것이 한눈에 보여야 한다 —
    # 에이전트 계열의 붉은색과 구분되는 자톤 + 플러그 아이콘. 종전에 한 종류가
    # 이 행이 없어 회색 기본 노드로 그려졌던 회귀(2026-09-07)를 다시 내지 않기 위해 반드시 둔다.
    ExternalAgent.KIND: KindUI(
        icon="🔌",
        section_label="🔌 EXTERNAL AGENTS",
        section_color=QColor("#cc88bb"),
        tab_label="🔌",
        node_style=("#2a1a26", "#8a4a7a", "AGENT", "🔌"),
        dialog_title="새 External Agent",
        editor_factory=_agent_editor,
        tab_prefix="🔌 ",
    ),
}


# ─────────────────────────── 조회 ───────────────────────────

def ui_by_kind(kind: object) -> KindUI:
    """컴포넌트 `kind` 문자열 → 뷰 행. 미지 종류는 **이유와 선택지**를 말한다.

    `KeyError`로 두지 않는 이유(원칙 5): 팔레트·캔버스가 죽을 때 사용자가 보는
    것은 "어느 종류의 UI 행이 없다"여야 한다 — 빈 키 이름만 나오면 어디를
    고쳐야 하는지 알 수 없다.
    """
    ui = KIND_UI.get(kind) if isinstance(kind, str) else None
    if ui is None:
        raise ValueError(
            f"뷰 표면(KIND_UI)이 없는 컴포넌트 종류입니다: {kind!r} — "
            f"daedalus/view/kind_ui.py의 KIND_UI에 행을 추가하세요. "
            f"등록된 종류: {', '.join(KIND_UI)}"
        )
    return ui


def ui_for(component: object) -> KindUI:
    """이 **인스턴스**의 뷰 행 — 종류 선언(`KIND`)으로 조회한다."""
    return ui_by_kind(getattr(type(component), "KIND", None))


def ui_by_config_kind(config_kind: object) -> KindUI:
    """config `kind`("procedural") → 뷰 행.

    레지스트리 섹션·생성 다이얼로그·종류 전환은 config 어휘로 말한다 —
    모델 레지스트리가 두 어휘를 짝지어 두었으므로 여기서 번역만 한다.
    """
    return ui_by_kind(spec_by_config_kind(config_kind).kind)


#: config `kind` → 이름 입력 다이얼로그 제목 (V9). 레지스트리 "+"·MCP가 함께 쓴다.
DIALOG_TITLES: dict[str, str] = {
    spec.config_kind: KIND_UI[kind].dialog_title
    for kind, spec in KIND_REGISTRY.items()
    if kind in KIND_UI
}


def switch_noun(config_kind: str) -> str:
    """종류 전환 상태 문구의 명사형 — 버튼 라벨에서 **유도**한다 (V12).

    두 어휘가 갈리면("동기 fork 스킬로 전환" 버튼 ↔ "sync_fork로 전환됨" 문구)
    사용자는 같은 것을 가리키는지 알 수 없다.
    """
    label = ui_by_config_kind(config_kind).switch_label
    if label is None:
        raise ValueError(
            f"'{config_kind}'는 종류 전환 가족이 아닙니다 — switch_label이 없습니다."
        )
    return label.removesuffix(_SWITCH_SUFFIX)
