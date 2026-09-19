# daedalus/view/editors/kind_switch_row.py
"""프론트매터 패널의 절차형 ↔ 동기/비동기 fork 전환 행 (2026-09-13/2026-09-17).

실체는 `actions/fork_skill.convert_skill_kind` — 캔버스 메뉴·MCP `convert_skill`과
같은 함수다. 패널 파일이 분해 예산(800줄)을 넘지 않도록 따로 둔다.
"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton

from daedalus.view.kind_ui import switch_noun, ui_by_config_kind


def build_kind_switch_row(panel, component, kind: str) -> None:
    """전환 버튼들(+ fork면 안내문)을 패널 그리드에 붙인다. 대상이 아니면 아무것도 안 한다."""
    from daedalus.view.actions.fork_skill import KINDS, skill_kind_of

    current = skill_kind_of(component)
    if panel._project_vm is None or current is None:
        return
    row = QHBoxLayout()
    first: QPushButton | None = None
    for target in KINDS:
        if target == current:
            continue
        # 라벨·툴팁의 실체는 뷰의 종류 표 `KIND_UI`다 (WP-7 ②) — 전환 가족에
        # 종류를 더할 때 여기 표 세 벌을 따로 고칠 자리가 없어야 한다.
        target_ui = ui_by_config_kind(target)
        btn = QPushButton(target_ui.switch_label)
        btn.setToolTip(
            "이름·본문·포트·배치는 그대로 두고 종류만 바꿉니다(Ctrl+Z로 되돌림). "
            + (target_ui.switch_tooltip or "")
        )
        btn.clicked.connect(
            lambda _=False, b=btn, t=target: _convert(panel, b, t)
        )
        row.addWidget(btn)
        first = first or btn
    row.addStretch()
    panel._add_span_layout(row)
    if kind in ("sync_fork", "async_fork"):
        hint = QLabel(
            "도구는 fork 에이전트가 정합니다. 모델·effort는 이 스킬 값이 이기고, "
            "비워 두면 fork 에이전트 값을 씁니다."
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
    message = (
        f"'{getattr(panel._component, 'name', '?')}' {switch_noun(target)}로 전환됨"
        f"{f' ({dropped} 버림)' if dropped else ''} — 필드 구성이 갱신됐습니다 "
        f"(Ctrl+Z로 되돌릴 수 있습니다)"
    )
    status = getattr(window, "_status_label", None)
    if status is not None:
        status.setText(message)
    # 전환은 열린 편집 탭을 재생성한다 — 이 버튼이 속한 패널이 이미 교체됐으면
    # 남은 것은 삭제 예정 위젯이라 손댈 것이 없다(탭이 열려 있지 않은 단독 패널
    # 경로에서는 그대로 살아 있으므로 여기서 결과를 알린다).
    try:
        btn.setEnabled(False)
        btn.setText(message)
    except RuntimeError:  # pragma: no cover - 위젯이 이미 파괴된 경우
        pass
