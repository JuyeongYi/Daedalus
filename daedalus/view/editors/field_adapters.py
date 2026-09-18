# daedalus/view/editors/field_adapters.py
"""프론트매터 필드 위젯의 **어댑터 표** — 위젯 타입 하나당 한 줄.

구 ``frontmatter_panel.py``에서 이동했다(WP-RF 관례 — 이동만·동작 불변).
``frontmatter_panel``이 재-export하므로 기존 임포트 경로가 그대로 동작한다.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLineEdit,
    QSpinBox,
    QTextEdit,
    QWidget,
)

from daedalus.view.widgets.tag_input import TagInput


# ---------------------------------------------------------------------------
# 위젯 어댑터 표 — 위젯 타입 하나당 (읽기, 쓰기, 변경 시그널 이름) 한 줄.
#
# 값 로드(_apply_value) · 값 읽기(_read_widget_value) · 시그널 연결
# (_connect_widget_signal)이 **같은 isinstance 사슬을 세 벌** 복제하고 있었다.
# 위젯 타입이 하나 늘면 세 곳을 함께 고쳐야 하고, 한 곳을 빠뜨리면 "값은
# 채워지는데 편집이 저장되지 않는" 식의 반쪽 고장이 조용히 생긴다.
#
# **순회 순서는 분해 전 elif 사슬의 순서를 그대로 유지한다** — isinstance는
# 서브클래스에도 참이므로 순서가 곧 우선순위다(표의 줄을 옮기면 동작이 바뀐다).
# ---------------------------------------------------------------------------

def _write_spin_box(widget: QSpinBox, current: object, rule) -> None:
    # QSpinBox 기본 상한이 99라 max_turns가 잘릴 수 있다.
    # CC의 실제 상한은 컴파일러 WP에서 확정 — 잠정 1~1000.
    widget.setRange(1, 1000)
    widget.setValue(int(current) if current is not None else 1)


def _write_combo_box(widget: QComboBox, current: object, rule) -> None:
    val = None
    if current is not None:
        val = current.value if hasattr(current, "value") else str(current)
    elif rule.default_value is not None:
        # default_value는 enum(ModelType.INHERIT 등) 또는 스칼라.
        dv = rule.default_value
        val = dv.value if hasattr(dv, "value") else str(dv)
    if val is not None:
        idx = widget.findText(val)
        if idx < 0 and hasattr(widget, "add_unlisted"):  # 후보 밖 저장값도 보인다
            idx = widget.add_unlisted(val)
        if idx >= 0:
            widget.setCurrentIndex(idx)


def _write_check_box(widget: QCheckBox, current: object, rule) -> None:
    widget.setChecked(bool(current) if current is not None else False)


def _write_tag_input(widget: TagInput, current: object, rule) -> None:
    if isinstance(current, list):
        widget.set_tags(current)
    elif isinstance(current, dict):
        # hooks: dict[str, Any] — 키 집합을 태그 목록으로 (WP-SF hooks TagInput 전환)
        widget.set_tags(list(current.keys()))


def _write_text_edit(widget: QTextEdit, current: object, rule) -> None:
    if current is not None:
        widget.setPlainText(str(current))
    widget.setFixedHeight(44)


def _write_line_edit(widget: QLineEdit, current: object, rule) -> None:
    if isinstance(current, list):
        widget.setText(" ".join(current) if current else "")
    elif current is not None:
        widget.setText(str(current))


# (위젯 타입, 표시값 읽기, 현재값 쓰기, 변경 시그널 이름)
_WIDGET_ADAPTERS: tuple[tuple[type, object, object, str], ...] = (
    (QSpinBox, lambda w: w.value(), _write_spin_box, "valueChanged"),
    (QComboBox, lambda w: w.currentText(), _write_combo_box, "currentTextChanged"),
    (QCheckBox, lambda w: w.isChecked(), _write_check_box, "toggled"),
    (TagInput, lambda w: w.get_tags(), _write_tag_input, "tags_changed"),
    (QTextEdit, lambda w: w.toPlainText(), _write_text_edit, "textChanged"),
    (QLineEdit, lambda w: w.text(), _write_line_edit, "editingFinished"),
)


def _adapter_for(widget: QWidget):
    """위젯에 맞는 어댑터 한 줄. 표에 없는 타입이면 None."""
    for entry in _WIDGET_ADAPTERS:
        if isinstance(widget, entry[0]):
            return entry
    return None
