"""compile_preview의 토큰 추정 노출 (A5-lite).

MCP 소비자가 LLM이라, 미리보기 텍스트를 받으면서 그 비용을 함께 알 수 있어야
"이 스킬이 얼마나 실리는가"를 판단할 수 있다.
"""
from __future__ import annotations

import pytest

from daedalus.compiler.token_report import DEFAULT_FILE_TOKEN_THRESHOLD, estimate_tokens
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject


def _skill(name: str, body: str) -> ProceduralSkill:
    s = SimpleState(name="s")
    fsm = StateMachine(name=name, initial_state=s, states=[s], final_states=[s])
    return ProceduralSkill(fsm=fsm, name=name, description="d", body=body)


@pytest.fixture
def tools(qapp):
    from daedalus.mcp.tools import DaedalusTools
    from daedalus.view.app import MainWindow

    project = PluginProject(
        name="p",
        skills=[
            _skill("small", "short body"),
            _skill("fat", "word " * (DEFAULT_FILE_TOKEN_THRESHOLD * 2)),
        ],
    )
    win = MainWindow()
    win.set_project(project)
    yield DaedalusTools(win)
    win.close()


def test_compile_preview_reports_tokens(tools):
    out = tools.compile_preview("small")
    assert out["chars"] == len(out["text"])
    assert out["tokens"] == estimate_tokens(out["text"])
    assert out["token_threshold"] == DEFAULT_FILE_TOKEN_THRESHOLD
    assert out["token_notice"] is None


def test_compile_preview_notice_over_threshold(tools):
    out = tools.compile_preview("fat")
    assert out["tokens"] > DEFAULT_FILE_TOKEN_THRESHOLD
    assert out["token_notice"] is not None
    assert "fat" in out["token_notice"]
    # 미리보기 텍스트 자체는 리포트의 영향을 받지 않는다.
    assert out["text"].startswith("---")
