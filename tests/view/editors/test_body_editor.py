from __future__ import annotations

from daedalus.model.fsm.section import Section


def _tree() -> tuple[list[Section], Section, Section, Section, Section]:
    """4-level test tree.

    Overview
    Setup
      Requirements
        System Reqs
      Installation
    Usage
    """
    sys_reqs = Section("System Reqs")
    reqs = Section("Requirements", children=[sys_reqs])
    install = Section("Installation")
    setup = Section("Setup", children=[reqs, install])
    overview = Section("Overview")
    usage = Section("Usage")
    roots = [overview, setup, usage]
    return roots, setup, reqs, sys_reqs, install


def test_find_path_root():
    from daedalus.view.editors.body_editor import find_path
    roots, setup, *_ = _tree()
    assert find_path(setup, roots) == [setup]


def test_find_path_nested():
    from daedalus.view.editors.body_editor import find_path
    roots, setup, reqs, sys_reqs, _ = _tree()
    assert find_path(sys_reqs, roots) == [setup, reqs, sys_reqs]


def test_find_path_not_found():
    from daedalus.view.editors.body_editor import find_path
    roots, *_ = _tree()
    orphan = Section("Orphan")
    assert find_path(orphan, roots) is None


def test_section_depth_root():
    from daedalus.view.editors.body_editor import section_depth
    roots, setup, *_ = _tree()
    assert section_depth(setup, roots) == 0


def test_section_depth_nested():
    from daedalus.view.editors.body_editor import section_depth
    roots, _, _, sys_reqs, _ = _tree()
    assert section_depth(sys_reqs, roots) == 2


def test_section_depth_not_found():
    from daedalus.view.editors.body_editor import section_depth
    roots, *_ = _tree()
    orphan = Section("Orphan")
    assert section_depth(orphan, roots) == -1
