"""스펙 드리프트 감시 (A4) — 훅 모델 vs 벤더링된 CC 설정 스키마.

`HookEvent` 31종·`NO_MATCHER_EVENTS`·핸들러 `to_json` 키는 전부 SchemaStore의
`claude-code-settings.json`을 손으로 옮겨 적은 것이다. 상류가 바뀌어도 아무
신호가 나지 않는 것이 이 프로젝트의 최대 유지 부채였다 — **틀린 emit은 도구가
없는 것보다 나쁘다. 조용히 실패하기 때문이다**(설정한 사람은 훅이 걸린 줄 알지만
CC는 그 키를 무시하거나 파일 전체를 거부한다).

이 파일은 **네트워크에 나가지 않는다.** 읽는 것은 저장소에 벤더링된 스냅샷
(`tests/fixtures/specs/claude-code-settings.json`)뿐이다. 상류를 받아오는 것은
`scripts/refresh_cc_schema.py`이고, 스냅샷을 갱신한 커밋에서 이 테스트가
빨개지는 것이 설계 의도다 — 갱신이 곧 사람이 보는 리뷰 지점이 된다.

절차·출처·날짜는 `tests/fixtures/specs/README.md` 참조.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from daedalus.model.plugin.hook import (
    HOOK_HANDLER_TYPES,
    NO_MATCHER_EVENTS,
    UNDOCUMENTED_EVENTS,
    AgentHook,
    CommandHook,
    HookEvent,
    HookHandler,
    HookShell,
    HttpHook,
    McpToolHook,
    PromptHook,
)

SNAPSHOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures" / "specs" / "claude-code-settings.json"
)

# 상류 description이 "이 이벤트는 matcher를 받지 않는다"고 말하는 표현.
# scripts/refresh_cc_schema.py의 같은 목록과 일치해야 한다 — 스크립트가 보여 주는
# diff와 이 테스트의 실패가 같은 판정에서 나와야 한다.
NO_MATCHER_PHRASES = (
    "does not support matchers",
    "matchers are ignored",
    "no matchers",
)


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def hook_event_props(schema: dict[str, Any]) -> dict[str, Any]:
    return schema["properties"]["hooks"]["properties"]


@pytest.fixture(scope="module")
def handler_variants(schema: dict[str, Any]) -> dict[str, set[str]]:
    """`$defs.hookCommand`의 변종 → 허용 속성 집합 (`type` const가 키).

    다섯 변종 모두 `additionalProperties: false`라, 여기 없는 키를 내보내면
    설정 파일이 스키마에 어긋난다 — 부분집합 단언이 곧 실질 계약이다.
    """
    out: dict[str, set[str]] = {}
    for variant in schema["$defs"]["hookCommand"]["anyOf"]:
        props = variant["properties"]
        assert variant.get("additionalProperties") is False, (
            "hookCommand 변종이 추가 속성을 허용하게 바뀌었다 — "
            "부분집합 단언의 전제가 무너졌으니 계약을 다시 판단하라"
        )
        out[props["type"]["const"]] = set(props.keys())
    return out


def _filled_handlers() -> dict[str, HookHandler]:
    """모든 선택 키가 실제로 배출되도록 전 필드를 채운 핸들러 5종.

    빈 값 키는 `to_json`이 생략하므로(결정적 산출), 채우지 않으면 이 테스트가
    `{"type": ...}` 하나만 보고 통과해 버린다.
    """
    common = {"timeout": 30, "condition": "Bash(git *)", "status_message": "checking"}
    return {
        "command": CommandHook(
            script="echo hi",
            args=["--verbose"],
            shell=HookShell.POWERSHELL,
            run_async=True,
            async_rewake=True,
            **common,
        ),
        "prompt": PromptHook(
            prompt="is this safe?", model="haiku", continue_on_block=True, **common
        ),
        "agent": AgentHook(prompt="review the diff", model="opus", **common),
        "http": HttpHook(
            url="https://example.test/hook",
            headers={"X-Token": "abc"},
            allowed_env_vars=["HOME"],
            **common,
        ),
        "mcp_tool": McpToolHook(
            server="memory", tool="store", tool_input={"key": "value"}, **common
        ),
    }


def test_hook_events_match_schema(hook_event_props: dict[str, Any]):
    """`HookEvent` = 스냅샷 `properties.hooks`의 키 — 집합도 순서도.

    순서까지 보는 이유: `compile_hooks_json`이 이벤트 키를 **HookEvent 선언
    순서**로 배출한다(컴파일 정책). 상류가 순서를 바꾸면 우리 산출과 상류 예시가
    갈라지므로 그것도 드리프트다.
    """
    ours = [event.value for event in HookEvent]
    theirs = list(hook_event_props.keys())

    missing = sorted(set(theirs) - set(ours))
    extra = sorted(set(ours) - set(theirs))
    assert not missing, f"스키마에만 있는 훅 이벤트 — HookEvent에 추가하라: {missing}"
    assert not extra, f"HookEvent에만 있는 훅 이벤트 — 상류에서 사라졌다: {extra}"
    assert ours == theirs, (
        "훅 이벤트 선언 순서가 스키마와 다르다 — hooks.json 이벤트 키 순서가 "
        f"이 순서를 따른다.\n  ours:   {ours}\n  schema: {theirs}"
    )


def test_no_matcher_events_match_schema(hook_event_props: dict[str, Any]):
    """`NO_MATCHER_EVENTS` = description이 matcher 미지원이라 명시한 이벤트.

    받지 않는 이벤트에 matcher를 주면 CC가 조용히 무시한다 — 설정한 사람은
    걸린 줄 안다. `HookDef.to_json`이 이 집합으로 matcher 배출을 가른다.
    """
    theirs = {
        name
        for name, node in hook_event_props.items()
        if any(p in node.get("description", "").lower() for p in NO_MATCHER_PHRASES)
    }
    ours = {event.value for event in NO_MATCHER_EVENTS}
    assert ours == theirs, (
        "matcher 미지원 집합이 스키마와 어긋난다 — hook.py의 NO_MATCHER_EVENTS를 "
        f"고쳐라.\n  스키마에만: {sorted(theirs - ours)}\n"
        f"  우리에게만: {sorted(ours - theirs)}"
    )


@pytest.mark.parametrize("kind", sorted(HOOK_HANDLER_TYPES))
def test_handler_json_keys_are_schema_properties(
    kind: str, handler_variants: dict[str, set[str]]
):
    """핸들러 `to_json` 키 ⊆ 그 변종의 속성 집합.

    변종은 `additionalProperties: false`이므로, 모르는 키 하나가 hooks.json
    전체를 스키마 위반으로 만든다.
    """
    assert kind in handler_variants, (
        f"핸들러 타입 `{kind}`가 스키마 $defs.hookCommand에 없다 "
        f"(스키마 변종: {sorted(handler_variants)})"
    )
    handler = _filled_handlers()[kind]
    assert isinstance(handler, HOOK_HANDLER_TYPES[kind])

    emitted = set(handler.to_json("${ROOT}/hooks/scripts/x.sh"))
    allowed = handler_variants[kind]
    assert emitted <= allowed, (
        f"`{kind}` 핸들러가 스키마에 없는 키를 배출한다: "
        f"{sorted(emitted - allowed)} (허용: {sorted(allowed)})"
    )
    # 필수 키가 빠지면 CC가 그 훅 항목을 거부한다 — 부분집합만으로는 못 잡는다.
    variant = next(
        v
        for v in json.loads(SNAPSHOT.read_text(encoding="utf-8"))["$defs"]
        ["hookCommand"]["anyOf"]
        if v["properties"]["type"]["const"] == kind
    )
    required = set(variant.get("required", ()))
    assert required <= emitted, (
        f"`{kind}` 핸들러가 필수 키를 빠뜨린다: {sorted(required - emitted)}"
    )


def test_undocumented_events_match_schema(hook_event_props: dict[str, Any]):
    """`UNDOCUMENTED_EVENTS` = description이 "UNDOCUMENTED"로 시작하는 이벤트.

    (A4 명세의 3종 외 추가분 — 같은 스냅샷을 읽는 같은 성격의 하드코딩이라
    같은 자리에서 고정한다. 편집기가 "공식 문서에 없음"이라고 안내하는 근거다.)
    """
    theirs = {
        name
        for name, node in hook_event_props.items()
        if node.get("description", "").strip().upper().startswith("UNDOCUMENTED")
    }
    ours = {event.value for event in UNDOCUMENTED_EVENTS}
    assert ours == theirs, (
        "미문서화 이벤트 집합이 스키마와 어긋난다 — hook.py의 UNDOCUMENTED_EVENTS를 "
        f"고쳐라.\n  스키마에만: {sorted(theirs - ours)}\n"
        f"  우리에게만: {sorted(ours - theirs)}"
    )
