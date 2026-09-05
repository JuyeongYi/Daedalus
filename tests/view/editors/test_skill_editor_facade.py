# tests/view/editors/test_skill_editor_facade.py
"""skill_editor.py → 패널 3모듈 분해의 재-export 파사드 완전성 고정.

분해 전 단일 모듈 ``view/editors/skill_editor.py``(1,172줄)에서 외부가 실제로
임포트하던 이름 집합을, 분해 후에도 같은 경로로 전부 접근할 수 있음을 고정한다 —
`component_editor`/`agent_editor`와 십수 개 테스트가
``from daedalus.view.editors.skill_editor import _FrontmatterPanel`` 처럼
언더스코어 이름까지 직접 임포트하므로, 그 경로가 깨지지 않는 것이 분해의 1차
게이트다.
"""
from __future__ import annotations

from pathlib import Path

import daedalus.view.editors.skill_editor as skill_editor

# 분해 전 모듈이 정의하던 이름 — 클래스 6종 + 모듈 수준 상수 9종.
# (PySide6/typing 등 부수 임포트는 소비처가 없어 재-export 대상이 아니다.)
_PRE_SPLIT_NAMES = [
    "SkillEditor",
    "_COLOR_PRESETS",
    "_COL_CHECK",
    "_COL_COUNT",
    "_COL_LABEL",
    "_COL_WIDGET",
    "_ColorPickerPopup",
    "_DIM_OPACITY",
    "_EventCard",
    "_FIELD_ATTR_MAP",
    "_FIELD_ENUM_MAP",
    "_FrontmatterPanel",
    "_LIST_FIELDS",
    "_OptionalRow",
    "_ReferenceLinkPanel",
    "_TOOL_CANDIDATE_FIELDS",
    "_TransferOnPanel",
]


def test_facade_exposes_all_pre_split_names():
    """분해 전 모듈의 이름이 전부 파사드에서 접근 가능해야 한다."""
    missing = [name for name in _PRE_SPLIT_NAMES if not hasattr(skill_editor, name)]
    assert not missing, f"파사드 누락 이름: {missing}"


def test_facade_reexports_are_submodule_objects():
    """파사드의 이름이 각 구현 모듈의 객체와 동일해야 한다 (복제 아님)."""
    from daedalus.view.editors import (
        frontmatter_panel,
        reference_link_panel,
        transfer_on_panel,
    )

    assert skill_editor._FrontmatterPanel is frontmatter_panel._FrontmatterPanel
    assert skill_editor._OptionalRow is frontmatter_panel._OptionalRow
    assert skill_editor._FIELD_ATTR_MAP is frontmatter_panel._FIELD_ATTR_MAP
    assert skill_editor._FIELD_ENUM_MAP is frontmatter_panel._FIELD_ENUM_MAP
    assert skill_editor._LIST_FIELDS is frontmatter_panel._LIST_FIELDS
    assert skill_editor._TOOL_CANDIDATE_FIELDS is frontmatter_panel._TOOL_CANDIDATE_FIELDS
    assert skill_editor._COL_CHECK == frontmatter_panel._COL_CHECK
    assert skill_editor._COL_LABEL == frontmatter_panel._COL_LABEL
    assert skill_editor._COL_WIDGET == frontmatter_panel._COL_WIDGET
    assert skill_editor._COL_COUNT == frontmatter_panel._COL_COUNT
    assert skill_editor._DIM_OPACITY == frontmatter_panel._DIM_OPACITY

    assert skill_editor._TransferOnPanel is transfer_on_panel._TransferOnPanel
    assert skill_editor._EventCard is transfer_on_panel._EventCard
    assert skill_editor._ColorPickerPopup is transfer_on_panel._ColorPickerPopup
    assert skill_editor._COLOR_PRESETS is transfer_on_panel._COLOR_PRESETS

    assert skill_editor._ReferenceLinkPanel is reference_link_panel._ReferenceLinkPanel


def test_split_modules_are_within_soft_budget():
    """분해 목표 — 각 모듈 800줄 이하 (하드 상한 1,200은 위생 테스트가 강제)."""
    from daedalus.view.editors import frontmatter_panel

    editors_dir = Path(frontmatter_panel.__file__).parent
    names = (
        "skill_editor.py",
        "frontmatter_panel.py",
        "transfer_on_panel.py",
        "reference_link_panel.py",
    )
    oversized = {
        name: len((editors_dir / name).read_text(encoding="utf-8").splitlines())
        for name in names
        if len((editors_dir / name).read_text(encoding="utf-8").splitlines()) > 800
    }
    assert not oversized, f"분해 목표(800줄) 초과: {oversized}"


def test_widget_adapter_table_covers_all_three_paths():
    """어댑터 표 한 줄이 로드·읽기·시그널 세 경로를 모두 채워야 한다 (ⓐ).

    분해 전에는 같은 isinstance 사슬이 세 벌 있었다 — 한 곳을 빠뜨리면
    "값은 채워지는데 편집이 저장되지 않는" 반쪽 고장이 조용히 생긴다.
    """
    from daedalus.view.editors.frontmatter_panel import _WIDGET_ADAPTERS

    for widget_type, read_fn, write_fn, signal_name in _WIDGET_ADAPTERS:
        assert callable(read_fn), widget_type
        assert callable(write_fn), widget_type
        # 시그널은 클래스 속성으로 실존해야 한다 (오타가 런타임까지 숨지 않도록).
        assert hasattr(widget_type, signal_name), f"{widget_type}: {signal_name}"
