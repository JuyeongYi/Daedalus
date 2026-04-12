from daedalus.model.fsm.section import SkillSection


def test_skill_section_members():
    assert SkillSection.INSTRUCTIONS.value == "instructions"
    assert SkillSection.WHEN_ENTER.value == "when_enter"
    assert SkillSection.WHEN_FINISHED.value == "when_finished"
    assert SkillSection.WHEN_ACTIVE.value == "when_active"
    assert SkillSection.WHEN_ERROR.value == "when_error"
    assert SkillSection.CONTEXT.value == "context"


def test_skill_section_count():
    assert len(SkillSection) == 6


def test_skill_section_order():
    members = list(SkillSection)
    assert members[0] == SkillSection.INSTRUCTIONS
    assert members[-1] == SkillSection.CONTEXT
