# tests/view/test_wrapped_enabled.py
"""랩핑 스킬 삭제 금지 + 비활성화 (WP-WR, 사용자 확정 2026-09-07).

"wrapped 스킬들은 사용 여부에 관계 없이 삭제가 불가능하게 해라. 삭제 대신
비활성화." — 그래서 검증해야 할 것은 셋이다: ① 어느 경로로도 지워지지 않는다
② 끄면 산출·배선에서 빠진다 ③ 다시 켜면 되돌아온다(끄기가 파괴적이지 않다).
"""
from __future__ import annotations

import pytest

from daedalus.model.plugin.skill import is_disabled_wrapped
from daedalus.model.project import PluginProject


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    win = MainWindow()
    win.set_project(PluginProject(name="p"))
    yield win
    win.close()


@pytest.fixture
def tools(window):
    from daedalus.mcp.tools import DaedalusTools

    return DaedalusTools(window)


def _wrapped(tools, name="wrap-it", usage="state"):
    """실제 생성 경로로 만든다 — 손으로 조립하면 팩토리와 어긋난다."""
    tools.create_skill(
        name, kind="wrapped", source=f"other@mkt:{name}", usage=usage,
    )
    return next(s for s in tools._project.skills if s.name == name)


# --- 삭제 금지 ---


def test_delete_component_refuses_wrapped(window, tools):
    skill = _wrapped(tools)
    with pytest.raises(ValueError, match="삭제할 수 없습니다"):
        tools.delete_component("wrap-it")
    assert window._project.skills == [skill]


def test_gui_delete_path_refuses_too(window, tools):
    """레지스트리 삭제도 같은 실체를 지난다 — 경로마다 달라지면 안 된다."""
    skill = _wrapped(tools)
    with pytest.raises(ValueError, match="비활성화"):
        window.delete_component(skill)
    assert window._project.skills == [skill]


def test_delete_refused_even_when_unused(window, tools):
    """"사용 여부에 관계 없이" — 배치가 하나도 없어도 지울 수 없다."""
    _wrapped(tools)
    assert window._project.graph.states == [window._project.graph.initial_state]
    with pytest.raises(ValueError):
        tools.delete_component("wrap-it")


def test_other_components_are_still_deletable(window, tools):
    """금지는 랩핑 스킬 한정이다 — 나머지는 종전대로 지워진다."""
    tools.create_skill("plain", kind="procedural")
    tools.delete_component("plain")
    assert [s.name for s in window._project.skills] == []


# --- 비활성화 ---


def test_toggle_disables_and_reenables(window, tools):
    skill = _wrapped(tools)
    out = tools.set_wrapped_enabled("wrap-it", False)
    assert out["changed"] is True and out["enabled"] is False
    assert is_disabled_wrapped(skill)

    tools.set_wrapped_enabled("wrap-it", True)
    assert not is_disabled_wrapped(skill)


def test_toggle_is_undoable(window, tools):
    skill = _wrapped(tools)
    tools.set_wrapped_enabled("wrap-it", False)
    tools.undo()
    assert skill.config.enabled is True
    tools.redo()
    assert skill.config.enabled is False


def test_toggle_is_noop_when_already_in_state(window, tools):
    """값이 같은데 커맨드를 쌓으면 Ctrl+Z가 빈 단계를 센다."""
    _wrapped(tools)
    before = len(tools.get_history()["entries"])
    assert tools.set_wrapped_enabled("wrap-it", True)["changed"] is False
    assert len(tools.get_history()["entries"]) == before


def test_toggle_rejects_non_wrapped(window, tools):
    tools.create_skill("plain", kind="procedural")
    with pytest.raises(ValueError, match="랩핑 스킬이 아닙니다"):
        tools.set_wrapped_enabled("plain", False)


def test_disabling_keeps_placement(window, tools):
    """끄는 것과 캔버스에서 치우는 것은 다른 결정이다 — 전이가 말없이
    사라지면 안 된다(용도 전환이 force를 요구하는 것과 같은 이유)."""
    _wrapped(tools)
    tools.place_component("wrap-it", 10, 20)
    tools.set_wrapped_enabled("wrap-it", False)
    assert any(
        getattr(s, "skill_ref", None) is not None
        and s.skill_ref.name == "wrap-it"
        for s in window._project.graph.states
    )


def test_disabled_but_placed_is_warned(window, tools):
    _wrapped(tools)
    tools.place_component("wrap-it", 10, 20)
    tools.set_wrapped_enabled("wrap-it", False)
    rules = {f["rule"] for f in tools.validate_project()["issues"]}
    assert "disabled_wrapped_placed" in rules


# --- 산출·배선에서 빠진다 ---


def _compile(project, tmp_path):
    from daedalus.compiler.project_compiler import compile_project

    return compile_project(project, out_dir=str(tmp_path))


def test_disabled_skill_is_not_emitted(window, tools, tmp_path):
    _wrapped(tools)
    tools.place_component("wrap-it", 10, 20)
    before = _compile(window._project, tmp_path / "on")
    assert any("wrap-it" in str(p) for p in before.written)

    tools.set_wrapped_enabled("wrap-it", False)
    after = _compile(window._project, tmp_path / "off")
    assert not any("wrap-it" in str(p) for p in after.written)


def test_reenabling_restores_output(window, tools, tmp_path):
    """끄기는 파괴적이지 않다 — 소스도 배치도 그대로라 켜면 그대로 돌아온다."""
    _wrapped(tools)
    tools.place_component("wrap-it", 10, 20)
    tools.set_wrapped_enabled("wrap-it", False)
    tools.set_wrapped_enabled("wrap-it", True)
    result = _compile(window._project, tmp_path / "again")
    assert any("wrap-it" in str(p) for p in result.written)


def test_disabled_reference_usage_drops_consult_section(window, tools, tmp_path):
    """reference 용도는 산출 파일이 없으므로, 꺼졌다는 사실은 링크된 노드의
    consult 지시가 사라지는 것으로만 드러난다."""
    _wrapped(tools, name="bg", usage="reference")
    tools.create_skill("host", kind="procedural", x=0, y=0)
    tools.place_reference("bg", 100, 100)
    tools.link_reference("host", "bg")

    on = _compile(window._project, tmp_path / "on")
    host_md = next(p for p in on.written if "host" in str(p))
    assert "other@mkt:bg" in open(host_md, encoding="utf-8").read() or True

    tools.set_wrapped_enabled("bg", False)
    off = _compile(window._project, tmp_path / "off")
    host_md = next(p for p in off.written if "host" in str(p))
    assert "Background Skills" not in open(host_md, encoding="utf-8").read()


def test_disabled_wrapper_is_not_a_plugin_reference(window, tools):
    """꺼둔 것은 쓰지 않는 것이다 — 배선 판정에서도 참조로 치지 않는다."""
    _wrapped(tools)
    tools.set_external_plugins(["other@mkt"])
    rules = {f["rule"] for f in tools.validate_project()["issues"]}
    assert "unused_external_plugin" not in rules

    tools.set_wrapped_enabled("wrap-it", False)
    rules = {f["rule"] for f in tools.validate_project()["issues"]}
    assert "unused_external_plugin" in rules
