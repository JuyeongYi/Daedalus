"""프론트매터 YAML 표기 — 어떤 사용자 값이든 파싱 결과가 원래 값과 같아야 한다 (2026-09-13).

예전 `_yaml_scalar`는 `": "`와 일부 선두 문자만 감쌌다 — 설명의 ` #`는 주석으로 잘리고,
줄바꿈·앞 따옴표·끝 `:`는 파싱 에러, `123`은 숫자, `Bash(a, b)`는 도구 두 개가 됐다.
"""
from __future__ import annotations

import pytest
import yaml

from daedalus.compiler.emit import compile_skill
from daedalus.compiler.emit.frontmatter import _yaml_scalar
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.config import DeclarativeSkillConfig
from daedalus.model.plugin.skill import DeclarativeSkill, TransferSkill

TRICKY = [
    "Plan work #2 steps",
    "line1\nline2",
    '"quoted" start',
    "ends with colon:",
    "123",
    "1.5",
    "C:\\new\\dir",
    "%percent",
    "`code` first",
    "key: value inside",
    "tab\there",
    "yes",
    "한국어 설명 — 그대로",
]


def _frontmatter(text: str) -> dict:
    return yaml.safe_load(text.split("---")[1])


@pytest.mark.parametrize("desc", TRICKY)
def test_description_roundtrips(desc):
    skill = DeclarativeSkill(name="x", description=desc, body="b")
    assert _frontmatter(compile_skill(skill))["description"] == desc


@pytest.mark.parametrize("value", [*TRICKY, "  padded ", ""])
def test_scalar_roundtrips(value):
    """설명 조립은 앞뒤 공백을 걷어내므로, 공백 보존은 표기 함수 수준에서 확인한다."""
    assert yaml.safe_load(f"k: {_yaml_scalar(value)}")["k"] == value


def test_flow_list_items_keep_commas():
    tools = ["Bash(git add, git commit)", "Read", "mcp__srv__tool", "Edit[x]"]
    skill = DeclarativeSkill(
        name="x", description="d", body="b",
        config=DeclarativeSkillConfig(allowed_tools=tools),
    )
    assert _frontmatter(compile_skill(skill))["allowed-tools"] == tools


def test_plain_values_stay_unquoted():
    """따옴표는 필요할 때만 — 기존 산출이 바뀌지 않는다."""
    for s in ("sonnet", "한국어 설명 — 그대로", "mcp__daedalus__get_project", "Use when ready."):
        assert _yaml_scalar(s) == s


def test_transfer_skill_is_model_invocable():
    """전이 스킬은 앞 스킬이 모델에게 부르게 하는 단계다 — 모델 호출이 막히면 죽은 단계."""
    s = SimpleState(name="s")
    tr = TransferSkill(
        fsm=StateMachine(name="t", states=[s], initial_state=s),
        name="t", description="d", body="b",
    )
    fm = _frontmatter(compile_skill(tr))
    assert fm["disable-model-invocation"] is False
    assert fm["user-invocable"] is False
