# daedalus/view/editors/kind_switch_row.py
"""프론트매터 패널의 절차형 ↔ fork 전환 행 (2026-09-13).

실체는 `actions/fork_skill.convert_skill_kind` — 캔버스 메뉴·MCP `convert_skill`과
같은 함수다. 패널 파일이 분해 예산(800줄)을 넘지 않도록 따로 둔다.
"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton


def build_kind_switch_row(panel, component, kind: str) -> None:
    """전환 버튼(+ fork면 안내문)을 패널 그리드에 붙인다. 대상이 아니면 아무것도 안 한다."""
    from daedalus.view.actions.fork_skill import skill_kind_of

    if panel._project_vm is None or skill_kind_of(component) is None:
        return
    target = "procedural" if kind == "fork" else "fork"
    btn = QPushButton("절차형 스킬로 전환" if target == "procedural" else "fork 스킬로 전환")
    btn.setToolTip(
        "이름·본문·포트·배치는 그대로 두고 종류만 바꿉니다(Ctrl+Z로 되돌림). "
        + ("fork 스킬은 allowed_tools를 쓰지 않아 버립니다."
           if target == "fork" else "몸 에이전트 지정을 버립니다.")
    )
    btn.clicked.connect(lambda _=False: _convert(panel, btn, target))
    row = QHBoxLayout()
    row.addWidget(btn)
    row.addStretch()
    panel._add_span_layout(row)
    panel._kind_switch_btn = btn
    if kind == "fork":
        hint = QLabel(
            "도구는 몸 에이전트가 정합니다. 모델·effort는 이 스킬 값이 이기고, "
            "비워 두면 몸 에이전트 값을 씁니다."
        )
        hint.setWordWrap(True)
        panel._add_span_row(hint)


def _convert(panel, btn: QPushButton, target: str) -> None:
    from daedalus.view.actions.fork_skill import convert_skill_kind

    window = panel._main_window()
    if not hasattr(window, "_project_vm"):
        return
    result = convert_skill_kind(window, panel._component, target)
    dropped = ", ".join(result["dropped"])
    btn.setEnabled(False)
    btn.setText(
        f"{target}로 전환됨{f' ({dropped} 버림)' if dropped else ''} — "
        f"탭을 닫았다 열면 필드 구성이 바뀝니다"
    )
