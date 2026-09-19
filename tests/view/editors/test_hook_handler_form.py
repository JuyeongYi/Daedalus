# tests/view/editors/test_hook_handler_form.py
"""훅 핸들러 폼의 **종류 디스패치 계약** (WP-11).

타입별 필드 구성과 저장은 종전에 같은 다섯 분기를 두 벌 갖고 있었다. 한쪽만
고치면 "폼에는 보이는데 저장되지 않는" 조용한 실패가 된다. 이제 둘 다
`singledispatch`이고, 이 테스트가 **모델의 종류 표(`HOOK_HANDLER_TYPES`)와
등록 표가 같은지**를 양방향으로 고정한다 — 새 핸들러 종류를 더하고 폼 등록을
빠뜨리면 여기서 실패한다.
"""
from __future__ import annotations

from daedalus.model.plugin.hook import (
    HOOK_HANDLER_TYPES,
    CommandHook,
    HookHandler,
    HttpHook,
    McpToolHook,
    PromptHook,
)
from daedalus.view.editors.hook_handler_form import (
    _HandlerForm,
    build_type_fields,
    save_type_fields,
)


def _registered(dispatcher) -> set[type]:
    """`object` 폴백을 뺀 등록 클래스 집합."""
    return {cls for cls in dispatcher.registry if cls is not object}


def test_every_handler_kind_has_a_form_registration():
    assert _registered(build_type_fields) == set(HOOK_HANDLER_TYPES.values())


def test_every_handler_kind_has_a_save_registration():
    assert _registered(save_type_fields) == set(HOOK_HANDLER_TYPES.values())


def test_build_and_save_registrations_are_the_same_set():
    """구성과 저장은 짝이다 — 한쪽만 등록하면 값이 조용히 버려진다."""
    assert _registered(build_type_fields) == _registered(save_type_fields)


def test_fallback_does_not_raise_for_unknown_handler(qapp):
    """모르는 종류는 공통 필드만 있는 폼으로 열린다 — 프로젝트가 안 열리는 것이 아니라."""

    class _UnknownHook(HookHandler):
        @property
        def kind(self) -> str:
            return "unknown"

        def _payload(self, script_ref: str = "") -> dict:
            return {}

        def summary(self) -> str:
            return "?"

    handler = _UnknownHook()
    form = _HandlerForm(handler, lambda: None, None)
    form._condition.setText("Bash(git *)")
    assert handler.condition == "Bash(git *)"


def test_command_form_round_trips_type_fields(qapp):
    handler = CommandHook(script="echo hi", script_name="greet")
    changed: list[int] = []
    form = _HandlerForm(handler, lambda: changed.append(1), None)
    form._script.setPlainText("echo bye")
    assert handler.script == "echo bye"
    assert changed


def test_prompt_form_saves_continue_on_block(qapp):
    handler = PromptHook(prompt="check")
    form = _HandlerForm(handler, lambda: None, None)
    form._continue_on_block.setChecked(True)
    assert handler.continue_on_block is True


def test_http_form_saves_headers(qapp):
    handler = HttpHook(url="https://x")
    form = _HandlerForm(handler, lambda: None, None)
    form._headers.setPlainText("X-A: 1")
    assert handler.headers == {"X-A": "1"}


def test_mcp_tool_form_saves_input(qapp):
    handler = McpToolHook(server="s", tool="t")
    form = _HandlerForm(handler, lambda: None, None)
    form._input.setPlainText("k: v")
    assert handler.tool_input == {"k": "v"}
