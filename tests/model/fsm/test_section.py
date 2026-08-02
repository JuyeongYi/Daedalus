from daedalus.model.fsm.section import Section, EventDef, render_markdown


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


# ─────────────────────── render_markdown (WP-SB 마이그레이션 헬퍼) ───────────────────────


def test_render_markdown_heading_depth():
    """중첩 깊이에 따라 H1/H2/H3 헤딩이 배출된다."""
    tree = [
        Section("Top", "root content", children=[
            Section("Mid", "mid content", children=[
                Section("Leaf", "leaf content"),
            ]),
        ]),
    ]
    text = render_markdown(tree)
    assert text == "# Top\n\nroot content\n\n## Mid\n\nmid content\n\n### Leaf\n\nleaf content"


def test_render_markdown_empty_content_emits_heading_only():
    """content가 빈 섹션은 헤딩 줄만 배출된다(빈 content 블록 생략)."""
    text = render_markdown([Section("Heading", "")])
    assert text == "# Heading"


def test_render_markdown_multiple_roots_joined_with_blank_line():
    text = render_markdown([Section("A", "a"), Section("B", "b")])
    assert text == "# A\n\na\n\n# B\n\nb"


def test_render_markdown_empty_list_returns_empty_string():
    assert render_markdown([]) == ""


def test_render_markdown_depth_caps_at_h6():
    """min(depth, 6) 규약 — H6를 넘는 깊이는 여전히 ###### 로 고정."""
    tree = [Section("H1", children=[
        Section("H2", children=[
            Section("H3", children=[
                Section("H4", children=[
                    Section("H5", children=[
                        Section("H6", children=[
                            Section("H7-would-be"),
                        ]),
                    ]),
                ]),
            ]),
        ]),
    ])]
    text = render_markdown(tree)
    assert "###### H6" in text
    assert "###### H7-would-be" in text  # depth 7 → min(7,6) = 6


def test_event_def_defaults():
    e = EventDef(name="done")
    assert e.name == "done"
    assert e.color == "#4488ff"
    assert e.description == ""


def test_event_def_custom():
    e = EventDef(name="error", color="#cc3333", description="오류 발생")
    assert e.color == "#cc3333"
    assert e.description == "오류 발생"
