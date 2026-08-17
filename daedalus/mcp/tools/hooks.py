# daedalus/mcp/tools/hooks.py
"""훅 라이브러리 도구 — 정의 CRUD + 컴포넌트 참조 + 조회 (WP-RF-3b).

**계층: GUI 어댑터다 (WP-RF-2 명시).** core(model/compiler)가 아니라
MainWindow·ProjectViewModel·CommandStack·body_documents 등 view 표면에 결합된
코드로, core 경계 계약(tests/test_import_contracts.py)의 대상이 아니다.
모든 메서드는 **Qt 메인 스레드에서 실행되는 것을 전제**로 한다(service가
MainThreadInvoker로 마샬링한다). 편집 도구는 반드시
``ProjectViewModel.execute``(CommandStack)를 거친다 — 사용자가 Ctrl+Z로
되돌릴 수 있어야 한다.

라이브러리가 정의의 단일 진실이고 컴포넌트는 이름으로 참조한다(WP-CE 4차).
삭제는 참조를 건드리지 않는다 — 남은 참조는 `dangling_hook_ref` 경고로
드러난다.
"""
from __future__ import annotations

from typing import Any

from ._base import _BaseTools


class HookTools(_BaseTools):
    """훅 라이브러리 — GUI 훅 패널과 같은 모델을 CommandStack 경유로 편집."""

    def _find_hook(self, name: str) -> Any:
        for hook in self._project.hook_library:
            if hook.name == name:
                return hook
        known = ", ".join(h.name for h in self._project.hook_library) or "(없음)"
        raise ValueError(f"'{name}' 훅이 없습니다. 현재 라이브러리: {known}")

    @staticmethod
    def _hook_summary(hook: Any) -> dict[str, Any]:
        # 그룹 단위로 만들어야 command 훅의 스크립트 경로가 채워진다 — 핸들러를
        # 개별로 to_json()하면 경로를 모르므로 command가 빈 값으로 나온다.
        group = hook.to_json()
        return {
            "name": hook.name,
            "event": getattr(hook.event, "value", str(hook.event)),
            "matcher": hook.matcher,
            "description": getattr(hook, "description", ""),
            # CC 스키마 그대로의 핸들러 목록 — 이 값이 hooks.json에 그대로 나간다
            "handlers": group["hooks"],
            # 경로만 보면 무엇이 실행되는지 알 수 없다. 스크립트 본문도 함께 준다.
            "scripts": dict(hook.script_files()),
        }

    @staticmethod
    def _build_hook_handler(spec: dict[str, Any]) -> Any:
        """핸들러 스펙(dict) → HookHandler.

        spec의 `type`이 CC 스키마의 다섯 종(command/prompt/agent/http/mcp_tool)
        중 하나를 고른다. 나머지 키는 그 타입의 필드명을 쓰되, CC 산출 키와
        파이썬 필드명이 다른 셋(`if`/`async`/`input`)은 여기서 옮겨 준다.
        """
        from daedalus.model.plugin.hook import HOOK_HANDLER_TYPES, HookShell

        kind = str(spec.get("type", "command"))
        cls = HOOK_HANDLER_TYPES.get(kind)
        if cls is None:
            allowed = ", ".join(sorted(HOOK_HANDLER_TYPES))
            raise ValueError(f"알 수 없는 훅 핸들러 타입 '{kind}'. 사용 가능: {allowed}")

        # CC 산출 키 → 파이썬 필드명 (예약어 회피 때문에 이름이 다르다).
        # `command`는 CC 산출에서 스크립트 **경로**이지만 입력으로는 스크립트
        # **본문**을 받는다(WP-HS) — 커맨드는 아무리 짧아도 파일로 나가고,
        # 경로는 컴파일러가 정한다.
        aliases = {
            "if": "condition",
            "statusMessage": "status_message",
            "async": "run_async",
            "asyncRewake": "async_rewake",
            "continueOnBlock": "continue_on_block",
            "allowedEnvVars": "allowed_env_vars",
            "input": "tool_input",
            "command": "script",
            "scriptName": "script_name",
        }
        from dataclasses import fields as dc_fields

        valid = {f.name for f in dc_fields(cls)} - {"id"}
        kwargs: dict[str, Any] = {}
        for key, value in spec.items():
            if key == "type":
                continue
            attr = aliases.get(key, key)
            if attr not in valid:
                raise ValueError(
                    f"'{kind}' 훅에 '{key}' 속성은 없습니다. "
                    f"사용 가능: {', '.join(sorted(valid))}"
                )
            if attr == "shell":
                try:
                    value = HookShell(str(value))
                except ValueError:
                    raise ValueError("shell은 bash 또는 powershell이어야 합니다.") from None
            kwargs[attr] = value
        return cls(**kwargs)

    def _refresh_hook_ui(self) -> None:
        """훅 이름 후보(HookPresetPicker)를 쓰는 위젯들이 새 목록을 보게 한다."""
        self._vm.notify()

    def create_hook(
        self,
        name: str,
        event: str = "PreToolUse",
        handlers: list[dict[str, Any]] | None = None,
        matcher: str = "",
        description: str = "",
        command: str = "",
    ) -> dict[str, Any]:
        """프로젝트 훅 라이브러리에 훅을 추가한다.

        구조는 CC settings hooks 스키마 그대로다 — 이벤트 + 선택적 matcher +
        핸들러 목록.

        handlers: [{"type": "command", "command": "echo hi", "timeout": 5}, ...]
        핸들러 타입 5종: command(command/scriptName/args/shell/async/asyncRewake) /
        prompt(prompt/model/continueOnBlock) / agent(prompt/model) /
        http(url/headers/allowedEnvVars) / mcp_tool(server/tool/input).
        모든 타입이 timeout, if, statusMessage를 공통으로 받는다.

        **command 훅의 `command`는 스크립트 본문이다**(WP-HS). 아무리 짧아도
        `hooks/scripts/<이름>.sh` 파일로 나가고, hooks.json에는 루트 기반 경로만
        남는다 — 인라인 셸 문자열은 쓰지 않는다. 파일명은 `scriptName`으로 정하고
        비우면 훅 이름에서 만든다.

        command 인자(핸들러 밖)는 편의용 지름길이다 — handlers 대신 주면 command
        핸들러 하나를 만든다.

        event는 CC 훅 이벤트 31종 중 하나(list_hook_events 참조).
        matcher는 이벤트가 받을 때만 의미가 있다. MCP 도구를 매칭하려면
        `mcp__<서버>__<도구>` 형태를 쓰고, 서버 전체는 `mcp__<서버>__.*`처럼
        `.*`를 붙여야 한다 — 서버 이름까지만 쓰면 아무것도 맞지 않는다.

        훅은 라이브러리에 정의만 해 두는 것이고, 실제로 배출되려면
        set_component_hooks로 스킬/에이전트가 이름으로 참조해야 한다.
        """
        from daedalus.model.plugin.hook import MATCHER_EVENTS, HookDef, HookEvent
        from daedalus.view.commands.attr_commands import AppendToListCmd

        library = self._project.hook_library
        if any(h.name == name for h in library):
            raise ValueError(f"'{name}' 훅이 이미 있습니다.")
        try:
            hook_event = HookEvent(event)
        except ValueError:
            allowed = ", ".join(e.value for e in HookEvent)
            raise ValueError(f"알 수 없는 훅 이벤트 '{event}'. 사용 가능: {allowed}") from None

        specs = list(handlers or [])
        if command:
            specs.append({"type": "command", "command": command})
        built = [self._build_hook_handler(s) for s in specs]

        hook = HookDef(
            name=name,
            description=description,
            event=hook_event,
            matcher=matcher,
            handlers=built,
        )
        self._vm.execute(
            AppendToListCmd(
                library,
                hook,
                label=f"훅 '{name}' 추가",
                script=f'create_hook("{name}", event="{hook_event.value}")',
            )
        )
        self._refresh_hook_ui()
        result = self._hook_summary(hook)
        if matcher and hook_event not in MATCHER_EVENTS:
            result["note"] = (
                f"{hook_event.value}는 matcher를 받지 않습니다 — 무시되고 검증 경고가 뜹니다."
            )
        if not built:
            result["note"] = "핸들러가 없어 아무 일도 하지 않습니다 — handlers를 지정하라."
        return result

    def update_hook(
        self,
        name: str,
        event: str = "",
        handlers: list[dict[str, Any]] | None = None,
        matcher: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """라이브러리의 훅 정의를 고친다.

        빈 문자열/None은 "건드리지 않음"이다. matcher와 description은 ""를 주면
        지워진다. handlers를 주면 **목록 전체를 교체**한다(형식은 create_hook 참조).
        """
        from daedalus.model.plugin.hook import HookEvent
        from daedalus.view.commands.attr_commands import SetAttrCmd
        from daedalus.view.commands.base import MacroCommand

        hook = self._find_hook(name)
        before = self._hook_summary(hook)
        cmds: list[Any] = []

        def _set(attr: str, value: Any) -> None:
            cmds.append(
                SetAttrCmd(
                    hook, attr, value,
                    label=f"훅 '{name}' {attr} 변경",
                    script=f'update_hook("{name}", {attr}=...)',
                )
            )

        if event:
            try:
                _set("event", HookEvent(event))
            except ValueError:
                allowed = ", ".join(e.value for e in HookEvent)
                raise ValueError(f"알 수 없는 훅 이벤트 '{event}'. 사용 가능: {allowed}") from None
        if handlers is not None:
            _set("handlers", [self._build_hook_handler(s) for s in handlers])
        if matcher is not None:
            _set("matcher", matcher)
        if description is not None:
            _set("description", description)

        if not cmds:
            return {"changed": [], **before}
        self._vm.execute(
            cmds[0]
            if len(cmds) == 1
            else MacroCommand(children=cmds, description=f"훅 '{name}' 변경")
        )
        self._refresh_hook_ui()
        return {"before": before, **self._hook_summary(hook)}

    def hook_frontmatter_preview(self, names: list[str] | None = None) -> dict[str, Any]:
        """훅을 **서브에이전트 프론트매터 YAML**로 변환해 돌려준다 (WP-HK).

        에이전트가 `.claude/agents/`에서 직접 쓰는 형식이다. 프로젝트 설치 빌드는
        컴파일이 자동으로 넣어 주지만, 이 프로젝트 밖의 에이전트 파일에 손으로
        붙여넣고 싶을 때 쓴다.

        names를 생략하면 라이브러리 전체. hooks.json 형식이 필요하면
        compile_preview 대신 get_project의 hook_library를 보라.
        """
        from daedalus.compiler.emit import _yaml_block_lines
        from daedalus.model.plugin.hook import HookEvent

        library = self._project.hook_library
        wanted = set(names) if names else {h.name for h in library}
        missing = sorted(wanted - {h.name for h in library})
        if missing:
            raise ValueError(f"라이브러리에 없는 훅: {', '.join(missing)}")

        buckets: dict[str, list[dict[str, Any]]] = {}
        for event in HookEvent:  # 선언 순서 = 결정적
            groups = [
                h.to_json()
                for h in library
                if h.event is event and h.name in wanted and h.handlers
            ]
            if groups:
                buckets[event.value] = groups

        if not buckets:
            return {"hooks": [], "yaml": "", "note": "배출할 핸들러가 없습니다."}

        lines = ["hooks:"] + _yaml_block_lines(buckets, 2)
        return {
            "hooks": sorted(wanted),
            "yaml": "\n".join(lines) + "\n",
        }

    def list_hook_events(self) -> dict[str, Any]:
        """CC 훅 이벤트 전체(31종)와 각 이벤트의 matcher 지원 여부.

        어떤 이벤트가 있는지 몰라 짐작으로 create_hook을 부르는 것을 막는다.
        """
        from daedalus.model.plugin.hook import (
            MATCHER_EVENTS,
            UNDOCUMENTED_EVENTS,
            HookEvent,
        )

        return {
            "events": [
                {
                    "name": e.value,
                    "supports_matcher": e in MATCHER_EVENTS,
                    "undocumented": e in UNDOCUMENTED_EVENTS,
                }
                for e in HookEvent
            ],
            "handler_types": ["command", "prompt", "agent", "http", "mcp_tool"],
        }

    def delete_hook(self, name: str) -> dict[str, Any]:
        """라이브러리에서 훅 정의를 지운다.

        이 훅을 참조하는 컴포넌트의 참조는 **건드리지 않는다**(GUI 훅 라이브러리와
        같은 정책) — 남은 참조는 `dangling_hook_ref` 경고로 드러나므로, 결과의
        `still_referenced_by`를 보고 set_component_hooks로 정리하라.
        """
        from daedalus.view.commands.attr_commands import RemoveFromListCmd

        hook = self._find_hook(name)
        referenced = [
            getattr(comp, "name", "?")
            for comp in self._all_hook_owners()
            if name in (getattr(getattr(comp, "config", None), "hooks", {}) or {})
        ]
        self._vm.execute(
            RemoveFromListCmd(
                self._project.hook_library,
                hook,
                label=f"훅 '{name}' 삭제",
                script=f'delete_hook("{name}")',
            )
        )
        self._refresh_hook_ui()
        return {"deleted": name, "still_referenced_by": referenced}

    def _all_hook_owners(self) -> list[Any]:
        """훅을 참조할 수 있는 컴포넌트 전부 — 스킬 + 에이전트."""
        project = self._project
        return [*project.skills, *project.agents]

    def set_component_hooks(
        self, name: str, hooks: list[str]
    ) -> dict[str, Any]:
        """스킬/에이전트가 참조하는 훅 이름 목록을 통째로 지정한다.

        라이브러리에 없는 이름은 거부한다 — 오타는 컴파일까지 조용히 흘러가
        `dangling_hook_ref` 경고로만 드러나기 때문이다.
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd

        comp = self._find_component(name)
        config = getattr(comp, "config", None)
        if config is None:
            raise ValueError(f"'{name}'에는 config가 없어 훅을 붙일 수 없습니다.")

        known = {h.name for h in self._project.hook_library}
        unknown = [h for h in hooks if h not in known]
        if unknown:
            raise ValueError(
                f"라이브러리에 없는 훅: {', '.join(unknown)}. "
                f"사용 가능: {', '.join(sorted(known)) or '(없음)'}"
            )

        # 기존 오버라이드는 유지한다 — 이름만 다시 지정하는 것이 이 도구의 일이다
        current = dict(getattr(config, "hooks", {}) or {})
        new_map = {h: current.get(h, {}) for h in hooks}
        self._vm.execute(
            SetAttrCmd(
                config,
                "hooks",
                new_map,
                label=f"'{name}' 훅 참조 {len(hooks)}개 설정",
                script=f'set_component_hooks("{name}", {list(hooks)})',
            )
        )
        return {"component": name, "hooks": list(new_map)}
