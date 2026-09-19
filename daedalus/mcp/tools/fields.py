# daedalus/mcp/tools/fields.py
"""프론트매터 필드 도구 — 목록/설정 (`list_component_fields`/`set_component_field`).

**계층: GUI 어댑터다 (WP-RF-2 명시).** core(model/compiler)가 아니라
MainWindow·ProjectViewModel·CommandStack 등 view 표면에 결합된 코드로, core 경계
계약(tests/test_import_contracts.py)의 대상이 아니다. 모든 메서드는 **Qt 메인
스레드에서 실행되는 것을 전제**로 한다(service가 MainThreadInvoker로 마샬링한다).
편집 도구는 반드시 ``ProjectViewModel.execute``(CommandStack)를 거친다.

**왜 `props.py`에서 떨어져 나왔는가 (WP-8 ①).** `props.py`는 생성·이름·프로젝트
속성과 프론트매터 필드라는 **두 책임**을 693줄에 담고 있었고, 종류 어휘와 필드
허용을 레지스트리·매트릭스에서 파생시키면 그대로 800줄 경계를 넘는다
(CLAUDE.md 코드 위생 — "기능을 더하기 전에 먼저 쪼갠다"). 분해는 **이동만**이고
동작은 한 줄도 바뀌지 않았다.

`FieldTools`는 `PropsTools`의 기저다 — `DaedalusTools`의 메서드 표면과
`tests/mcp/test_tools_facade.py`의 멤버 집합이 그대로 유지된다(재-export).
"""
from __future__ import annotations

from typing import Any

from daedalus.model.plugin.enums import AgentField, SkillField

from ._base import _BaseTools

#: 매트릭스 행이 있어도(또는 config 필드가 있어도) `set_component_field`가
#: 받지 않고 **전용 도구로 안내**하는 필드. 거절 문구의 "사용 가능" 목록도
#: 같은 집합을 뺀다 — 설정되지 않는 이름을 선택지로 내놓으면 안 된다(원칙 5).
_DEDICATED_TOOL_FIELDS: frozenset[str] = frozenset({"hooks", "usage", "enabled"})


class FieldTools(_BaseTools):
    """프론트매터 필드 조회·편집 — 표를 고르는 규칙은 model의 `matrix_for` 하나다."""

    @staticmethod
    def _config_field_types(config: Any) -> dict[str, Any]:
        """config 클래스의 필드 이름 → 선언 타입.

        `from __future__ import annotations` 때문에 dataclass의 `f.type`은 문자열이라
        쓸 수 없다 — `get_type_hints`로 실제 타입 객체를 얻는다.
        """
        from typing import get_type_hints

        try:
            return get_type_hints(type(config))
        except Exception:  # noqa: BLE001 — 힌트를 못 얻어도 편집은 막지 않는다
            return {}

    @staticmethod
    def _coerce_field_value(target: Any, value: Any, field: str) -> Any:
        """입력 값을 config 필드의 선언 타입으로 맞춘다.

        MCP로 오는 값은 JSON이라 문자열/리스트/불리언뿐이다. enum 필드는 값
        문자열로 받아 멤버로 바꾸고, 틀리면 허용 목록을 알려준다 — 조용히
        문자열이 들어가면 컴파일 산출이 이상해질 때까지 드러나지 않는다.
        """
        import enum
        from typing import get_args, get_origin

        raw_args = get_args(target)
        optional = type(None) in raw_args
        args = [a for a in raw_args if a is not type(None)]
        if args:
            target = args[0]
        origin = get_origin(target)

        # None = 미지정으로 되돌리기 (A8 tri-state). Optional 선언(`bool | None`
        # 등)일 때만 받는다 — 아무 필드에나 null을 허용하면 non-Optional 필드에
        # None이 들어가 타입 계약이 깨진다.
        if value is None:
            if optional:
                return None
            raise ValueError(
                f"'{field}'는 미지정(null)을 받지 않습니다 — 값을 주세요."
            )

        if origin in (list, set):
            if not isinstance(value, (list, tuple)):
                raise ValueError(f"'{field}'는 목록이어야 합니다.")
            return [str(v) for v in value]
        if isinstance(target, type) and issubclass(target, enum.Enum):
            try:
                return target(value)
            except ValueError:
                allowed = ", ".join(str(m.value) for m in target)
                raise ValueError(
                    f"'{field}'의 값 '{value}'이 올바르지 않습니다. 사용 가능: {allowed}"
                ) from None
        if target is bool:
            # bool(value)를 쓰면 안 된다 — MCP 클라이언트가 불리언을 문자열로
            # 보내는 경우가 실재하고, bool("false")는 True다(실사고: 라이브
            # 프로젝트의 user_invocable=false 지정이 조용히 True로 저장됐다).
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                low = value.strip().lower()
                if low in ("true", "1"):
                    return True
                if low in ("false", "0"):
                    return False
            raise ValueError(
                f"'{field}'는 불리언입니다 — true 또는 false로 주세요 "
                f"(받은 값: {value!r})."
            )
        if target is int:
            return int(value)
        return value

    def list_component_fields(self, name: str) -> dict[str, Any]:
        """이 컴포넌트가 받는 프론트매터 필드와 현재 값.

        스킬과 에이전트는 받는 필드가 다르고, 스킬은 종류(procedural/sync_fork/
        async_fork/declarative/transfer/reference)마다, 에이전트는
        종류(agent/fork_agent/external_agent)마다 또 다르다. 짐작으로 set_component_field를
        부르지 않도록 실제 목록을 돌려준다. `emit`은 그 필드가 어디로 나가는지다
        (frontmatter / body / settings).
        """
        import enum
        from typing import get_args

        from daedalus.model.plugin.field_matrix import matrix_for

        comp = self._find_component(name)
        # 표를 고르는 규칙의 실체는 model의 `matrix_for` 하나다 — 조용한
        # 빈 dict 폴백(예전 버그)도, 이유를 못 말하는 맨 첨자도 쓰지 않는다.
        # config가 없으면 `matrix_for`가 이름과 클래스를 찍고 거절하므로
        # 여기서 형상을 문자열로 더듬지 않는다(WP-8 — 래칫 ②).
        matrix = matrix_for(comp)
        config = comp.config

        hints = self._config_field_types(config)
        out: list[dict[str, Any]] = []
        for fld, rule in matrix.items():
            attr = fld.value
            if not hasattr(config, attr):
                continue
            current = getattr(config, attr)
            entry: dict[str, Any] = {
                "field": attr,
                "frontmatter_key": fld.frontmatter_key,
                "emit": rule.emit.value,
                "visibility": rule.visibility.value,
                "current": getattr(current, "value", current),
            }
            target = hints.get(attr)
            args = [a for a in get_args(target) if a is not type(None)]
            base = args[0] if args else target
            if isinstance(base, type) and issubclass(base, enum.Enum):
                entry["choices"] = [str(m.value) for m in base]
            out.append(entry)
        return {"component": comp.name, "kind": comp.kind, "fields": out}

    def set_component_field(
        self, name: str, field: str, value: Any
    ) -> dict[str, Any]:
        """스킬/에이전트 프론트매터 필드 하나를 설정한다.

        field는 `list_component_fields`가 돌려주는 이름(model / tools /
        permission_mode / allowed_tools / …). value는 JSON 값이며 enum 필드는 값
        문자열로 준다(예: model="sonnet", permission_mode="acceptEdits").
        목록 필드는 배열로 준다.

        **null = 미지정**(A8). `user_invocable` / `disable_model_invocation`처럼
        tri-state인 필드에 null을 주면 프론트매터 키 자체가 생략되어 CC 기본값에
        위임된다 — "기본값과 같은 값을 못 박는 것"과 다르다. Optional로 선언되지
        않은 필드에 null을 주면 거절한다.

        **설정 가능한 필드 = 그 종류의 매트릭스에서 FIXED가 아닌 행**(P4).
        FIXED 행(fork의 `context`/`background`, transfer·reference의
        `user_invocable` 등)은 종류가 값을 정하고 컴파일러가 강제 배출하므로,
        config에 기록해도 산출에 도달하지 않는다 — 조용한 no-op 대신 **이유를
        말하며 거절**한다(원칙 5).

        description / when_to_use / hooks / usage / enabled는 전용 도구를 쓴다 —
        거절이 그 도구 이름을 말한다.

        **`skills`는 외부 플러그인 참조(`플러그인:스킬`, WP-B)를 받는다** —
        선언 안 된 플러그인이어도 **거절하지 않는다**(형식은 유효하고 사용자가
        곧 선언할 수도 있다). 대신 응답에 `warning`을 실어 미선언 플러그인
        id를 말한다 — 검증(`undeclared_external_plugin`)이 같은 사실을 짚는다.
        """
        from daedalus.model.plugin.enums import FieldVisibility
        from daedalus.model.plugin.field_matrix import matrix_for
        from daedalus.view.commands.attr_commands import SetAttrCmd

        comp = self._find_component(name)
        config = comp.config
        if field == "hooks":
            raise ValueError("훅 참조는 set_component_hooks를 쓰세요.")
        # 허용 판정은 **매트릭스 한 곳**에서 나온다(P4). 예전에는 "config에
        # 속성이 있는가"만 물어서, 매트릭스에 없는 필드(fork의 allowed_tools —
        # fork에서는 에이전트 도구가 이긴다)나 종류가 고정하는 필드까지 받아
        # 저장하고는 산출에서 조용히 사라졌다.
        rule = {fld.value: r for fld, r in matrix_for(comp).items()}.get(field)
        if rule is not None and rule.visibility is FieldVisibility.FIXED:
            fixed = getattr(rule.fixed_value, "value", rule.fixed_value)
            raise ValueError(
                f"'{comp.kind}'의 '{field}'는 종류가 값을 고정하는 필드라 "
                f"설정할 수 없습니다(고정값: {fixed!r}) — 값을 바꾸려면 종류를 "
                f"바꿉니다(convert_skill)."
            )
        if rule is None or not hasattr(config, field):
            # **선택지는 실제로 설정되는 것만** 말한다(원칙 5). 예전에는
            # `list_component_fields`를 그대로 흘려서, 같은 호출이 거절하는
            # FIXED 행과 전용 도구 필드까지 "사용 가능"으로 내놓았다.
            known = [
                f["field"]
                for f in self.list_component_fields(name)["fields"]
                if f["visibility"] != FieldVisibility.FIXED.value
                and f["field"] not in _DEDICATED_TOOL_FIELDS
            ]
            raise ValueError(
                f"'{comp.kind}'에는 '{field}' 필드가 없습니다. "
                f"사용 가능: {', '.join(known)}"
            )

        if field == SkillField.AGENT.value:
            # fork 에이전트 — 틀린 이름은 CC가 조용히 general-purpose로 돌리므로 여기서 거절한다.
            from daedalus.view.actions.fork_skill import validate_fork_agent

            validate_fork_agent(self._project, value if isinstance(value, str) else "")
        hints = self._config_field_types(config)
        coerced = self._coerce_field_value(hints.get(field), value, field)
        old = getattr(config, field)
        self._vm.execute(
            SetAttrCmd(
                config,
                field,
                coerced,
                label=f"'{name}' {field} 변경",
                script=f'set_component_field("{name}", "{field}", ...)',
            )
        )
        out: dict[str, Any] = {
            "component": comp.name,
            "field": field,
            "old": getattr(old, "value", old),
            "new": getattr(coerced, "value", coerced),
        }
        if field == AgentField.SKILLS.value:
            warning = self._undeclared_external_skill_plugins_warning(comp)
            if warning:
                out["warning"] = warning
        return out

    def _undeclared_external_skill_plugins_warning(self, comp: Any) -> str | None:
        """`skills`에 방금 들어간 외부 참조 중 미선언 플러그인이 있으면 경고 문구.

        실체는 `comp.external_plugin_refs()`(config의 것을 합친 컴포넌트
        판정, WP-B) 하나다 — 프로젝트 검증의 `undeclared_external_plugin`과
        같은 술어를 쓴다(`external_plugin_id_declared` → `plugin_ids_match`).
        """
        from daedalus.model.plugin.config import (
            declared_external_plugin_ids,
            external_plugin_id_declared,
        )

        declared = declared_external_plugin_ids(self._project)
        missing = sorted({
            plugin_id
            for plugin_id in comp.external_plugin_refs()
            if not external_plugin_id_declared(plugin_id, declared)
        })
        if not missing:
            return None
        return (
            f"선언되지 않은 외부 플러그인 참조: {', '.join(missing)} — "
            f"set_external_plugins로 선언하지 않으면 빌드가 dependencies/"
            f"enabledPlugins를 배선하지 않아 런타임에 그 스킬을 찾지 못합니다."
        )
