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


def test_section_tree_builds_items(qapp):
    from daedalus.view.editors.body_editor import SectionTree
    roots, *_ = _tree()
    tree = SectionTree(roots)
    assert tree.tree_widget().topLevelItemCount() == 3


def test_section_tree_min_width(qapp):
    from daedalus.view.editors.body_editor import SectionTree
    tree = SectionTree([])
    assert tree.minimumWidth() >= 100


def test_section_tree_add_sibling(qapp):
    from daedalus.view.editors.body_editor import SectionTree
    roots = [Section("A")]
    tree = SectionTree(roots)
    tree.add_sibling(roots[0])
    assert len(roots) == 2
    assert roots[1].title == "새 섹션"


def test_section_tree_add_child(qapp):
    from daedalus.view.editors.body_editor import SectionTree
    roots = [Section("A")]
    tree = SectionTree(roots)
    tree.add_child(roots[0])
    assert len(roots[0].children) == 1
    assert roots[0].children[0].title == "새 하위 섹션"


def test_section_tree_add_child_depth_limit(qapp):
    from daedalus.view.editors.body_editor import SectionTree
    d3 = Section("D3")
    d2 = Section("D2", children=[d3])
    d1 = Section("D1", children=[d2])
    d0 = Section("D0", children=[d1])
    roots = [d0]
    tree = SectionTree(roots)
    tree.add_child(d3)  # depth 3 → child would be depth 4 → blocked
    assert len(d3.children) == 0


def test_section_tree_delete(qapp):
    from daedalus.view.editors.body_editor import SectionTree
    child = Section("Child")
    parent = Section("Parent", children=[child])
    roots = [parent]
    tree = SectionTree(roots)
    tree.delete_section(child)
    assert len(parent.children) == 0


def test_section_tree_select_by_section(qapp):
    from daedalus.view.editors.body_editor import SectionTree
    roots, setup, reqs, *_ = _tree()
    tree = SectionTree(roots)
    tree.select_section(reqs)
    sel = tree.tree_widget().currentItem()
    assert sel is not None
    assert sel.text(0) == "Requirements"
