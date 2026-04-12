from daedalus.model.fsm.section import Section, EventDef


def test_section_default_fields():
    s = Section(title="Persona")
    assert s.title == "Persona"
    assert s.content == ""
    assert s.children == []


def test_section_with_content():
    s = Section(title="Role", content="You are a writer.")
    assert s.content == "You are a writer."


def test_section_with_children():
    child = Section(title="Background")
    parent = Section(title="Persona", children=[child])
    assert len(parent.children) == 1
    assert parent.children[0].title == "Background"


def test_section_nested_h6():
    """H1 → H2 → H3 → H4 → H5 → H6 깊이 허용."""
    s = Section("H1", children=[
        Section("H2", children=[
            Section("H3", children=[
                Section("H4", children=[
                    Section("H5", children=[
                        Section("H6")
                    ])
                ])
            ])
        ])
    ])
    h6 = s.children[0].children[0].children[0].children[0].children[0]
    assert h6.title == "H6"
    assert h6.children == []


def test_event_def_defaults():
    e = EventDef(name="done")
    assert e.name == "done"
    assert e.color == "#4488ff"
    assert e.description == ""


def test_event_def_custom():
    e = EventDef(name="error", color="#cc3333", description="오류 발생")
    assert e.color == "#cc3333"
    assert e.description == "오류 발생"
