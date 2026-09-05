

def test_script_name_with_matching_extension_not_doubled():
    """scriptName에 셸 확장자를 붙여 넘겨도 `.sh.sh`가 되지 않는다.

    계약은 "확장자 제외"지만 그 계약을 모르는 호출자(MCP·GUI)가 `foo.sh`를
    넘기는 실수가 실제로 났다 — 정규화로 멱등하게 만든다.
    """
    from daedalus.model.plugin.hook import CommandHook, HookDef, HookEvent
    hook = HookDef(
        name="g", event=HookEvent.PRE_TOOL_USE, description="",
        handlers=[CommandHook(script="echo hi", script_name="guard.sh")],
    )
    assert hook.script_files() == [("guard.sh", "echo hi")]


def test_script_name_with_foreign_extension_preserved():
    """셸과 다른 확장자는 의도로 보고 보존한다 — bash 훅의 x.ps1 → x.ps1.sh."""
    from daedalus.model.plugin.hook import CommandHook, HookDef, HookEvent
    hook = HookDef(
        name="g", event=HookEvent.PRE_TOOL_USE, description="",
        handlers=[CommandHook(script="echo hi", script_name="x.ps1")],
    )
    assert hook.script_files() == [("x.ps1.sh", "echo hi")]


def test_script_name_only_extension_falls_back_to_hook_slug():
    """scriptName이 확장자뿐이면 빈 파일명이 아니라 훅 이름 슬러그로 폴백."""
    from daedalus.model.plugin.hook import CommandHook, HookDef, HookEvent
    hook = HookDef(
        name="my-guard", event=HookEvent.PRE_TOOL_USE, description="",
        handlers=[CommandHook(script="echo hi", script_name=".sh")],
    )
    assert hook.script_files() == [("my-guard.sh", "echo hi")]
