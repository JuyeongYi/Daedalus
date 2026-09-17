# tests/compiler/test_plan_facade.py
"""WP-FK2 C0: project_compiler.py → plan.py 분해의 재-export 파사드 고정 (이동만).

분해 전 `project_compiler`에서 임포트하던 이름이 전부 그대로 살아 있어야 한다 —
`view/panels/file_panel.py`·`view/session_io.py`·`view/compile_actions.py`가
`SKILL_FILES_DIRNAME`을 그 경로로 읽고 있고, 기존 테스트가 게이트 헬퍼를 직접
부른다. 파사드가 **구현 모듈의 같은 객체**를 내보내는지도 함께 고정한다(복제가
아니라 재-export여야 계획과 쓰기가 같은 판정을 본다).
"""
from __future__ import annotations

import daedalus.compiler.plan as plan
import daedalus.compiler.project_compiler as pc

#: 분해로 plan.py에 옮겨간 이름 — project_compiler에서 계속 임포트 가능해야 한다.
_MOVED_NAMES = [
    "SKILL_FILES_DIRNAME",
    "_OUTPUT_NAME_RE",
    "_PlannedOutput",
    "_hook_script_name_conflicts",
    "_is_link_like",
    "_iter_tree_files",
    "_plan_outputs",
    "_skill_dir_name",
]


def test_project_compiler_still_exposes_moved_names():
    missing = [name for name in _MOVED_NAMES if not hasattr(pc, name)]
    assert not missing, f"파사드 누락 이름: {missing}"


def test_facade_reexports_are_the_same_objects():
    for name in _MOVED_NAMES:
        assert getattr(pc, name) is getattr(plan, name), name


def test_plan_module_is_qt_and_view_free():
    """plan.py는 core 표면이다 — 경계 계약은 tests/test_import_contracts.py가
    AST로 강제하지만, 임포트 자체가 가능한지도 여기서 확인한다."""
    assert plan.SKILL_FILES_DIRNAME == "skill-files"
    assert plan._OUTPUT_NAME_RE.match("my-skill")
    assert not plan._OUTPUT_NAME_RE.match("My_Skill")
