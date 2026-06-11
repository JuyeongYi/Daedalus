"""ValidationPanel 단위 테스트."""
from __future__ import annotations

from daedalus.model.validation import ValidationError
from daedalus.view.panels.validation_panel import ValidationPanel


def _err(rule: str, message: str = "m", is_warn: bool = False) -> ValidationError:
    """테스트용 ValidationError 생성 헬퍼."""
    # is_warn=True → WARNING_RULES에 있는 rule 사용 (missing_required_input)
    # is_warn=False → 에러 rule 사용 (no_nested_agent)
    if is_warn:
        return ValidationError(rule="missing_required_input", message=message, source="s")
    return ValidationError(rule=rule, message=message, source="s")


def test_empty_errors_shows_no_problem(qapp):
    """에러 없을 때 요약 레이블이 '문제 없음'을 표시한다."""
    panel = ValidationPanel()
    panel.set_errors([])
    assert "문제 없음" in panel._summary_label.text()


def test_row_count_matches_error_count(qapp):
    """set_errors 후 테이블 행 수가 에러 개수와 일치한다."""
    panel = ValidationPanel()
    errors = [
        ValidationError(rule="no_nested_agent", message="중첩 에이전트", source="A"),
        ValidationError(rule="missing_required_input", message="필수 입력 누락", source="B"),
        ValidationError(rule="unreachable_state", message="도달 불가", source="C"),
    ]
    panel.set_errors(errors)
    assert panel._table.rowCount() == 3


def test_errors_sorted_before_warnings(qapp):
    """에러가 경고보다 먼저 표시된다."""
    panel = ValidationPanel()
    warn = ValidationError(rule="missing_required_input", message="경고", source="w")
    err = ValidationError(rule="no_nested_agent", message="에러", source="e")
    panel.set_errors([warn, err])  # 경고를 먼저 전달

    # 첫 번째 행은 에러여야 한다 (심각도 아이콘 ✖)
    sev_item = panel._table.item(0, 0)
    assert sev_item is not None
    assert sev_item.text() == "✖"


def test_double_click_triggers_callback(qapp):
    """더블클릭 시 on_item_activated 콜백에 ValidationError가 전달된다."""
    received: list[ValidationError] = []

    def _cb(e: ValidationError) -> None:
        received.append(e)

    panel = ValidationPanel(on_item_activated=_cb)
    err = ValidationError(rule="no_nested_agent", message="중첩 에이전트", source="A")
    panel.set_errors([err])

    # 내부 _on_double_click을 직접 호출 (QTest 없이도 동작 확인 가능)
    item = panel._table.item(0, 0)
    assert item is not None
    panel._on_double_click(item)

    assert len(received) == 1
    assert received[0] is err


def test_summary_shows_error_and_warning_counts(qapp):
    """요약 레이블에 에러/경고 개수가 표시된다."""
    panel = ValidationPanel()
    errors = [
        ValidationError(rule="no_nested_agent", message="에러1", source="A"),
        ValidationError(rule="missing_required_input", message="경고1", source="B"),
        ValidationError(rule="unreachable_state", message="경고2", source="C"),
    ]
    panel.set_errors(errors)
    text = panel._summary_label.text()
    assert "오류 1" in text
    assert "경고 2" in text


def test_path_displayed_in_row(qapp):
    """path가 있으면 테이블 경로 열에 표시된다."""
    panel = ValidationPanel()
    err = ValidationError(
        rule="no_nested_agent",
        message="중첩 에이전트",
        source="A",
        path=("agent:Writer", "agent:Inner"),
    )
    panel.set_errors([err])
    path_item = panel._table.item(0, 3)
    assert path_item is not None
    assert "agent:Writer" in path_item.text()
    assert "agent:Inner" in path_item.text()
