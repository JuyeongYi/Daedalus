"""빌드 타깃별 편집 잠금 (WP-EL).

CC는 플러그인 서브에이전트의 hooks/mcpServers/permissionMode를 보안상 무시한다.
편집을 그대로 두면 "설정했는데 아무 일도 일어나지 않는" 상태가 되고, 설계자가
건 제약이 조용히 사라진다. 마켓플레이스 빌드에서는 편집기가 잠그고, 컴파일러도
배출하지 않으며, 값이 남아 있으면 검증이 경고한다 — 세 계층이 같은 집합을 본다.
"""
from __future__ import annotations

import pytest

from daedalus.model.plugin.enums import AgentField, BuildTarget
from daedalus.model.plugin.field_matrix import (
    MARKETPLACE_UNSUPPORTED_AGENT_FIELDS,
    agent_field_supported,
)
from daedalus.model.project import PluginProject

from tests.compiler.builders import make_agent


# --- 순수 판정 (단일 진실) ---


def test_marketplace_blocks_the_three_fields():
    for field in (AgentField.HOOKS, AgentField.MCP_SERVERS, AgentField.PERMISSION_MODE):
        assert not agent_field_supported(field, BuildTarget.MARKETPLACE)


def test_local_allows_everything():
    """프로젝트 설치는 플러그인이 아니므로 플러그인 제약을 받지 않는다."""
    for field in AgentField:
        assert agent_field_supported(field, BuildTarget.LOCAL)


def test_unrelated_fields_are_never_blocked():
    for field in (AgentField.TOOLS, AgentField.MODEL, AgentField.MAX_TURNS):
        assert agent_field_supported(field, BuildTarget.MARKETPLACE)


def test_unsupported_set_matches_cc_docs():
    assert MARKETPLACE_UNSUPPORTED_AGENT_FIELDS == frozenset({
        AgentField.HOOKS, AgentField.MCP_SERVERS, AgentField.PERMISSION_MODE,
    })


# --- 편집기 잠금 ---


def _panel(qapp, build_target):
    from daedalus.view.editors.skill_editor import _FrontmatterPanel

    return _FrontmatterPanel(make_agent(), skill_kind="agent", build_target=build_target)


def _row_for(panel, field):
    """필드의 잠금 대상 — OPTIONAL 필드는 _OptionalRow, 아니면 위젯 자체.

    내부 위젯의 isEnabled()로 판정하면 안 된다: OPTIONAL 행은 체크가 꺼져 있을 때
    내부 위젯을 원래 비활성으로 두므로, 잠금과 "아직 안 켬"이 구분되지 않는다.
    """
    from daedalus.view.editors.skill_editor import _OptionalRow

    widget = panel._field_widgets.get(field)
    if widget is None:
        return None
    node = widget.parent()
    while node is not None and not isinstance(node, _OptionalRow):
        node = node.parent()
    return node if node is not None else widget


@pytest.mark.parametrize(
    "field",
    [AgentField.PERMISSION_MODE, AgentField.HOOKS, AgentField.MCP_SERVERS],
)
def test_marketplace_panel_disables_unsupported_field(qapp, field):
    panel = _panel(qapp, BuildTarget.MARKETPLACE)
    row = _row_for(panel, field)
    if row is None:
        pytest.skip(f"{field}는 편집 위젯이 없다")
    # 행 전체가 잠겨야 한다 — 위젯만 잠그면 체크박스가 살아 있어
    # "켤 수는 있는데 아무 일도 안 일어나는" 상태가 된다.
    assert not row.isEnabled()


@pytest.mark.parametrize(
    "field",
    [AgentField.PERMISSION_MODE, AgentField.HOOKS, AgentField.MCP_SERVERS],
)
def test_local_panel_keeps_field_editable(qapp, field):
    panel = _panel(qapp, BuildTarget.LOCAL)
    row = _row_for(panel, field)
    if row is None:
        pytest.skip(f"{field}는 편집 위젯이 없다")
    assert row.isEnabled()


def test_supported_field_stays_editable_in_marketplace(qapp):
    panel = _panel(qapp, BuildTarget.MARKETPLACE)
    row = _row_for(panel, AgentField.TOOLS)
    assert row is not None and row.isEnabled()


def test_locked_row_explains_why(qapp):
    """잠긴 이유를 알려주지 않으면 사용자는 고장으로 읽는다."""
    panel = _panel(qapp, BuildTarget.MARKETPLACE)
    row = _row_for(panel, AgentField.PERMISSION_MODE)
    assert row is not None
    tip = row.toolTip()
    assert "permissionMode" in tip and "프로젝트 설치" in tip


def test_default_build_target_is_marketplace(qapp):
    """build_target 없이 만드는 기존 호출부는 마켓플레이스로 취급된다."""
    from daedalus.view.editors.skill_editor import _FrontmatterPanel

    panel = _FrontmatterPanel(make_agent(), skill_kind="agent")
    row = _row_for(panel, AgentField.PERMISSION_MODE)
    if row is not None:
        assert not row.isEnabled()


# --- 컴파일러 (편집기 잠금과 같은 집합을 본다) ---


def test_marketplace_compile_omits_unsupported_fields():
    from daedalus.compiler.emit import compile_agent
    from daedalus.model.plugin.config import AgentConfig
    from daedalus.model.plugin.enums import PermissionMode

    agent = make_agent()
    agent.config = AgentConfig(permission_mode=PermissionMode.BYPASS)
    project = PluginProject(name="p", agents=[agent])

    text = compile_agent(agent, project=project)
    assert "permissionMode" not in text


def test_local_compile_emits_permission_mode():
    from daedalus.compiler.emit import compile_agent
    from daedalus.model.plugin.config import AgentConfig
    from daedalus.model.plugin.enums import PermissionMode

    agent = make_agent()
    agent.config = AgentConfig(permission_mode=PermissionMode.BYPASS)
    project = PluginProject(
        name="p", agents=[agent], build_target=BuildTarget.LOCAL,
    )

    assert "permissionMode: bypassPermissions" in compile_agent(agent, project=project)


# --- 플러그인 전용 변수 ---


def test_plugin_data_variable_warned_in_local_build():
    """${CLAUDE_PLUGIN_DATA}도 플러그인 스킬에서만 치환된다 — 이전에는 안 짚었다."""
    from daedalus.model.validation import Validator

    from tests.compiler.builders import make_procedural

    skill = make_procedural(body="캐시는 ${CLAUDE_PLUGIN_DATA}/cache 에 둔다")
    project = PluginProject(
        name="p", skills=[skill], build_target=BuildTarget.LOCAL,
    )

    rules = [e.rule for e in Validator().validate_project(project)]
    assert "plugin_root_in_local_build" in rules


def test_files_reference_is_not_warned():
    """files/ 참조는 컴파일이 ${CLAUDE_PROJECT_DIR}로 치환하므로 정상이다."""
    from daedalus.model.validation import Validator

    from tests.compiler.builders import make_procedural

    skill = make_procedural(body="체크리스트: ${CLAUDE_PLUGIN_ROOT}/files/list.md")
    project = PluginProject(
        name="p", skills=[skill], build_target=BuildTarget.LOCAL,
    )

    rules = [e.rule for e in Validator().validate_project(project)]
    assert "plugin_root_in_local_build" not in rules


def test_project_dir_variable_is_never_warned():
    """${CLAUDE_PROJECT_DIR}은 플러그인 여부와 무관하게 치환된다(v2.1.196+)."""
    from daedalus.model.validation import Validator

    from tests.compiler.builders import make_procedural

    skill = make_procedural(body="스크립트: ${CLAUDE_PROJECT_DIR}/scripts/run.sh")
    project = PluginProject(
        name="p", skills=[skill], build_target=BuildTarget.LOCAL,
    )

    rules = [e.rule for e in Validator().validate_project(project)]
    assert "plugin_root_in_local_build" not in rules


def test_plugin_variables_are_fine_in_marketplace_build():
    from daedalus.model.validation import Validator

    from tests.compiler.builders import make_procedural

    skill = make_procedural(body="${CLAUDE_PLUGIN_DATA}/cache 와 ${CLAUDE_PLUGIN_ROOT}/bin")
    project = PluginProject(name="p", skills=[skill])

    rules = [e.rule for e in Validator().validate_project(project)]
    assert "plugin_root_in_local_build" not in rules
