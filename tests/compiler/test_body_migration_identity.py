# tests/compiler/test_body_migration_identity.py
"""WP-SB 동일성 게이트 (핵심 완료 조건).

구버전 직렬화 dict(섹션 트리 보유 스킬/에이전트)를 deserialize_project로 로드해
body로 마이그레이션한 뒤 compile_skill/compile_agent한 산출 텍스트가, 같은 섹션
트리를 마이그레이션 없이 (섹션 트리를 직접 blocks.extend로 배출하던) 기존 방식으로
직접 렌더한 산출과 문자열 동일해야 한다.

아래 `_legacy_*` 함수들은 WP-SB 이전 compile_skill/compile_agent의 본문 배출
방식(`blocks.extend(_render_sections(sections, depth=1))`)을 그대로 재현한
골든 참조 구현이다 — body와 무관한 나머지 블록(프론트매터/FSM 절차/tool_shelf 등)은
emit.py의 실제 내부 헬퍼를 그대로 재사용해, 이 테스트가 "본문 배출 방식 전환"
하나만을 격리해서 검증하도록 한다.

(위임(delegation) 노드 산출은 WP-RF-1a로 퇴역 — 이 픽스처 FSM에는 위임 배치가
없어 골든 참조에서 해당 블록을 제거해도 산출이 동일하다.)
"""
from __future__ import annotations

from daedalus.compiler import emit as _emit
from daedalus.compiler.emit import compile_agent, compile_skill
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.section import Section
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.config import DeclarativeSkillConfig, ProceduralSkillConfig
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project


# ─────────────────────── 골든 참조: 구버전 렌더링/조립 ───────────────────────


def _legacy_render_sections(sections: list[Section], depth: int = 1) -> list[str]:
    """WP-SB 이전 compiler/emit.py의 _render_sections 동결 사본."""
    blocks: list[str] = []
    for sec in sections:
        hashes = "#" * min(depth, 6)
        blocks.append(f"{hashes} {sec.title}".rstrip())
        content = (sec.content or "").strip("\n")
        if content.strip():
            blocks.append(content)
        if sec.children:
            blocks.extend(_legacy_render_sections(sec.children, depth + 1))
    return blocks


def _legacy_join_blocks(blocks: list[str]) -> str:
    """WP-SB 이전 compiler/emit.py의 _join_blocks 동결 사본."""
    text = "\n\n".join(b for b in blocks if b is not None and b != "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


def _legacy_compile_skill(skill, sections: list[Section]) -> str:
    """WP-SB 이전 compile_skill의 본문 배출(sections 트리 직접 렌더) 재현.

    project 인수 없이 호출한 compile_skill과 동일 범위(프론트매터 + 본문 +
    FSM 절차/위임)만 다룬다 — tool_shelf/블랙보드/다음 단계는 project가 있을
    때만 배출되므로 이 비교에서는 제외.
    """
    kind_key = _emit._skill_kind_key(skill, local=False)
    fm_lines = _emit._frontmatter_lines_skill(skill, kind_key)
    blocks: list[str] = [_emit._frontmatter_block(fm_lines)]
    blocks.extend(_legacy_render_sections(sections, depth=1))
    if isinstance(skill, ProceduralSkill):
        blocks.extend(_emit._describe_fsm(skill.fsm, skill))
    return _legacy_join_blocks(blocks)


def _legacy_compile_agent(agent: AgentDefinition, sections: list[Section]) -> str:
    """WP-SB 이전 compile_agent의 본문 배출(sections 트리 직접 렌더) 재현."""
    fm_lines = _emit._frontmatter_lines_agent(agent)
    blocks: list[str] = [_emit._frontmatter_block(fm_lines)]
    blocks.extend(_legacy_render_sections(sections, depth=1))
    blocks.extend(_emit._invocation_section_agent(agent))
    blocks.extend(_emit._settings_note_agent(agent))
    blocks.extend(_emit._describe_agent_fsm(agent))
    # WP-AF — 출구 단락은 transfer_on 기반으로 분리됐다. original은 transfer_on이
    # 없어 ExitPoint 폴백을 타고, 마이그레이션된 쪽은 승계된 transfer_on을 타서
    # 같은 목록이 나온다 — 본문 마이그레이션 동일성 비교에는 영향이 없다.
    blocks.extend(_emit._agent_outputs_section(agent))
    return _legacy_join_blocks(blocks)


# ─────────────────────── 픽스처: H1~H4 + 빈 content + 자식 중첩 ───────────────────────


def _four_level_tree() -> list[Section]:
    h4 = Section("H4-Leaf", "leaf content")
    # 빈 content 섹션을 형제 사이(중간)에 둔다 — 트리 말단이면 빈 content 회귀의
    # 여분 개행이 끝에 몰려 strip에 흡수되어 게이트가 못 잡는다 (리뷰 지적).
    h3_empty = Section("H3-Empty", "")
    h3 = Section("H3-Mid", "mid content", children=[h3_empty, h4])
    h2 = Section("H2-Sub", "sub content", children=[h3])
    h1 = Section("H1-Top", "top content", children=[h2])
    return [h1]


def _sec_to_dict(sec: Section) -> dict:
    """serialize.py의 _ser_section과 동일한 dict 형태(구버전 파일 흉내)."""
    return {
        "title": sec.title,
        "content": sec.content,
        "children": [_sec_to_dict(c) for c in sec.children],
    }


def _legacy_skill_dict(project: PluginProject, skill_name: str, tree: list[Section]) -> dict:
    """serialize_project 산출에서 skill의 body 키를 sections 키로 치환(구버전 파일 흉내)."""
    data = serialize_project(project)
    skill_d = next(s for s in data["skills"] if s["name"] == skill_name)
    del skill_d["body"]
    skill_d["sections"] = [_sec_to_dict(s) for s in tree]
    return data


def _legacy_agent_dict(project: PluginProject, agent_name: str, tree: list[Section]) -> dict:
    data = serialize_project(project)
    agent_d = next(a for a in data["agents"] if a["name"] == agent_name)
    del agent_d["body"]
    agent_d["sections"] = [_sec_to_dict(s) for s in tree]
    return data


# ─────────────────────── 동일성 게이트 테스트 ───────────────────────


def test_identity_gate_procedural_skill():
    tree = _four_level_tree()
    s1 = SimpleState(name="analyze")
    s2 = SimpleState(name="report")
    fsm = StateMachine(name="f", initial_state=s1, states=[s1, s2], final_states=[s2])
    from daedalus.model.fsm.event import CompletionEvent
    from daedalus.model.fsm.transition import Transition
    fsm.transitions.append(
        Transition(source=s1, target=s2, trigger=CompletionEvent(name="done"))
    )
    original = ProceduralSkill(
        fsm=fsm, name="legacy-proc", description="설명",
        config=ProceduralSkillConfig(),
    )
    project = PluginProject(name="P", skills=[original])

    legacy_text = _legacy_compile_skill(original, tree)

    data = _legacy_skill_dict(project, "legacy-proc", tree)
    restored = deserialize_project(data)
    migrated = restored.skills[0]
    migrated_text = compile_skill(migrated)

    assert migrated_text == legacy_text


def test_identity_gate_declarative_skill():
    tree = _four_level_tree()
    original = DeclarativeSkill(
        name="legacy-decl", description="지식", config=DeclarativeSkillConfig(),
    )
    project = PluginProject(name="P", skills=[original])

    legacy_text = _legacy_compile_skill(original, tree)

    data = _legacy_skill_dict(project, "legacy-decl", tree)
    restored = deserialize_project(data)
    migrated = restored.skills[0]
    migrated_text = compile_skill(migrated)

    assert migrated_text == legacy_text


def test_identity_gate_agent():
    tree = _four_level_tree()
    entry = EntryPoint(name="entry")
    work = SimpleState(name="work")
    done = ExitPoint(name="done")
    fsm = StateMachine(
        name="af", initial_state=entry, states=[entry, work, done],
        final_states=[done],
    )
    from daedalus.model.fsm.transition import Transition
    fsm.transitions.append(Transition(source=entry, target=work))
    original = AgentDefinition(fsm=fsm, name="legacy-agent", description="에이전트")
    project = PluginProject(name="P", agents=[original])

    legacy_text = _legacy_compile_agent(original, tree)

    data = _legacy_agent_dict(project, "legacy-agent", tree)
    restored = deserialize_project(data)
    migrated = restored.agents[0]
    migrated_text = compile_agent(migrated)

    assert migrated_text == legacy_text


def test_identity_gate_body_contains_all_heading_levels():
    """방어 회귀 — 동일성 비교 대상 픽스처가 실제로 H1~H4·빈 content·중첩을 갖는지."""
    tree = _four_level_tree()
    original = DeclarativeSkill(name="legacy-decl2", description="d")
    legacy_text = _legacy_compile_skill(original, tree)
    assert "# H1-Top" in legacy_text
    assert "## H2-Sub" in legacy_text
    assert "### H3-Mid" in legacy_text
    assert "#### H4-Leaf" in legacy_text
    assert "#### H3-Empty" in legacy_text  # 빈 content — 헤딩만
