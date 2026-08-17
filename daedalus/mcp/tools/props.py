# daedalus/mcp/tools/props.py
"""컴포넌트 생성·속성 도구 — 생성/이름/설명/프론트매터 필드/프로젝트 속성 (WP-RF-3b).

**계층: GUI 어댑터다 (WP-RF-2 명시).** core(model/compiler)가 아니라
MainWindow·ProjectViewModel·CommandStack·body_documents 등 view 표면에 결합된
코드로, core 경계 계약(tests/test_import_contracts.py)의 대상이 아니다.
모든 메서드는 **Qt 메인 스레드에서 실행되는 것을 전제**로 한다(service가
MainThreadInvoker로 마샬링한다). 편집 도구는 반드시
``ProjectViewModel.execute``(CommandStack)를 거친다 — 사용자가 Ctrl+Z로
되돌릴 수 있어야 한다.
"""
from __future__ import annotations

from typing import Any

from ._base import _BaseTools


class PropsTools(_BaseTools):
    """컴포넌트 생성 + 속성/프론트매터 편집 + 프로젝트 속성."""

    def create_skill(
        self, name: str, kind: str = "procedural", description: str = ""
    ) -> dict[str, Any]:
        """스킬을 만든다.

        kind: procedural(작업 지침·자체 FSM) / declarative(배경 지식) /
        transfer(전이 시 실행되는 보조 지침) / reference(참조 문서).
        에이전트에게 줄 지식도 전역 스킬로 만든다 — 전역 declarative와 에이전트
        노드에 링크된 reference는 컴파일 시 에이전트 skills 프론트매터에 자동
        합류된다(로컬 스킬은 퇴역, WP-RF-1c).
        """
        from daedalus.model.plugin.skill import (
            DeclarativeSkill,
            ProceduralSkill,
            ReferenceSkill,
            TransferSkill,
        )

        self._reject_duplicate_name(name)
        win = self._window
        factories = {
            "procedural": lambda: ProceduralSkill(
                fsm=win._make_fsm(name), name=name, description=description
            ),
            "declarative": lambda: DeclarativeSkill(name=name, description=description),
            "transfer": lambda: TransferSkill(
                fsm=win._make_fsm(name), name=name, description=description
            ),
            "reference": lambda: ReferenceSkill(name=name, description=description),
        }
        if kind not in factories:
            raise ValueError(
                f"알 수 없는 스킬 종류 '{kind}'. 사용 가능: {', '.join(factories)}"
            )
        win._register_component(factories[kind]())
        return {"created": name, "kind": kind}

    def create_agent(self, name: str, description: str = "") -> dict[str, Any]:
        """에이전트를 만든다 — 별도 컨텍스트의 작업자.

        절차는 본문(set_component_body)에, 결과 분기는 출력 포트
        (set_transfer_on)에 서술한다. 기본 출력 포트 'done' 하나로 시작한다.
        """
        from daedalus.model.fsm.section import EventDef
        from daedalus.model.plugin.agent import AgentDefinition

        self._reject_duplicate_name(name)
        win = self._window
        agent = AgentDefinition(
            fsm=win._make_agent_fsm(name), name=name, description=description,
            transfer_on=[EventDef(name="done")],
        )
        win._register_component(agent)
        return {"created": name, "kind": "agent"}

    def rename_component(self, name: str, new_name: str) -> dict[str, Any]:
        """컴포넌트 이름을 바꾼다 — 문자열 참조도 함께 갱신된다."""
        from daedalus.view.commands.component_commands import RenameComponentCmd

        comp = self._find_component(name)
        self._reject_duplicate_name(new_name)
        self._vm.execute(RenameComponentCmd(self._project, comp, name, new_name))
        self._window._registry_panel.set_project(self._project)
        return {"renamed": name, "to": new_name}

    def set_component_description(
        self, name: str, description: str
    ) -> dict[str, Any]:
        """컴포넌트 설명을 바꾼다(프론트매터 description)."""
        from daedalus.view.commands.attr_commands import SetAttrCmd

        comp = self._find_component(name)
        old = getattr(comp, "description", "")
        self._vm.execute(
            SetAttrCmd(
                comp,
                "description",
                description,
                label=f"'{name}' 설명 변경",
                script=f'set_component_description("{name}", ...)',
            )
        )
        self._window._registry_panel.set_project(self._project)
        return {"component": name, "old": old, "new": description}

    def set_component_when_to_use(
        self, name: str, when_to_use: str
    ) -> dict[str, Any]:
        """컴포넌트의 when_to_use를 바꾼다.

        별도 프론트매터 키가 아니라 컴파일 시 description과 합류한다
        (`<description> Use when <when_to_use>`) — 모델이 이 스킬을 언제 집어야
        하는지 판단하는 문장이다.
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd

        comp = self._find_component(name)
        old = getattr(comp, "when_to_use", "")
        self._vm.execute(
            SetAttrCmd(
                comp,
                "when_to_use",
                when_to_use,
                label=f"'{name}' when_to_use 변경",
                script=f'set_component_when_to_use("{name}", ...)',
            )
        )
        return {"component": name, "old": old, "new": when_to_use}

    def set_project_properties(
        self,
        name: str = "",
        description: str = "",
        version: str = "",
        build_target: str = "",
    ) -> dict[str, Any]:
        """플러그인 매니페스트 속성을 바꾼다 — 빈 값은 "건드리지 않음".

        name은 plugin.json의 플러그인 식별자가 되므로 `^[a-z0-9][a-z0-9-]*$`를
        지켜야 컴파일 게이트를 통과한다(F7에서는 경고 등급).
        build_target: marketplace / local.
        """
        from daedalus.model.plugin.enums import BuildTarget
        from daedalus.view.commands.attr_commands import SetAttrCmd
        from daedalus.view.commands.base import MacroCommand

        project = self._project
        before = {
            "name": project.name,
            "description": project.description,
            "version": project.version,
            "build_target": project.build_target.value,
        }

        cmds: list[Any] = []
        for attr, value in (
            ("name", name),
            ("description", description),
            ("version", version),
        ):
            if value:
                cmds.append(
                    SetAttrCmd(
                        project,
                        attr,
                        value,
                        label=f"프로젝트 {attr} 변경",
                        script=f'set_project_properties({attr}="{value}")',
                    )
                )
        if build_target:
            try:
                target = BuildTarget(build_target.lower())
            except ValueError:
                allowed = ", ".join(t.value for t in BuildTarget)
                raise ValueError(
                    f"알 수 없는 빌드 타깃 '{build_target}'. 사용 가능: {allowed}"
                ) from None
            cmds.append(
                SetAttrCmd(
                    project,
                    "build_target",
                    target,
                    label=f"빌드 타깃 → {target.value}",
                    script=f'set_project_properties(build_target="{target.value}")',
                )
            )

        if not cmds:
            return {"changed": [], **before}
        self._vm.execute(
            cmds[0]
            if len(cmds) == 1
            else MacroCommand(children=cmds, description="프로젝트 속성 변경")
        )
        self._window._update_title()
        return {
            "before": before,
            "name": project.name,
            "description": project.description,
            "version": project.version,
            "build_target": project.build_target.value,
        }

    def set_mcp_server_def(
        self, name: str, config: dict | None = None
    ) -> dict[str, Any]:
        """MCP 서버 정의(이름 → `.mcp.json` 서버 객체)를 등록/갱신/삭제한다 (WP-MW).

        config 예: {"type": "http", "url": "http://127.0.0.1:8787/mcp"} 또는
        {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"]}.
        config=None(또는 빈 dict)이면 그 이름의 정의를 삭제한다.

        컴포넌트는 서버를 이름으로만 참조한다(tools/allowed_tools의 mcp__<서버>__
        접두, mcp_servers 선언). 정의는 **로컬 빌드의 설치 배선**에 쓰인다 —
        컴파일이 대상 작업 폴더의 `.mcp.json`에 병합하고 `.claude/
        settings.local.json`의 `enabledMcpjsonServers`에 이름을 올린다. 정의 없이
        참조만 있으면 컴파일이 `missing_mcp_server_def` 경고를 낸다.
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd

        if not name:
            raise ValueError("서버 이름이 비어 있습니다.")
        project = self._project
        current = dict(getattr(project, "mcp_server_defs", None) or {})
        old = current.get(name)

        updated = dict(current)
        if config:
            updated[name] = dict(config)
            action = "updated" if name in current else "added"
        else:
            if name not in current:
                known = ", ".join(sorted(current)) or "(없음)"
                raise ValueError(f"'{name}' 정의가 없습니다. 현재 정의: {known}")
            del updated[name]
            action = "removed"

        # SetAttrCmd는 값을 복사하지 않으므로 새 dict를 만들어 넘긴다 — 제자리
        # 수정이면 undo가 같은 객체를 가리켜 되돌릴 수 없다.
        self._vm.execute(SetAttrCmd(
            project,
            "mcp_server_defs",
            updated,
            label=f"MCP 서버 정의 {action}: {name}",
            script=f'set_mcp_server_def("{name}", ...)',
        ))
        return {"server": name, "action": action, "old": old, "new": updated.get(name)}

    # --- 프론트매터 필드 ---

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

        args = [a for a in get_args(target) if a is not type(None)]
        if args:
            target = args[0]
        origin = get_origin(target)

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
            return bool(value)
        if target is int:
            return int(value)
        return value

    def list_component_fields(self, name: str) -> dict[str, Any]:
        """이 컴포넌트가 받는 프론트매터 필드와 현재 값.

        스킬과 에이전트는 받는 필드가 다르고, 스킬은 종류(procedural/declarative/
        transfer/reference)마다 또 다르다. 짐작으로 set_component_field를 부르지
        않도록 실제 목록을 돌려준다. `emit`은 그 필드가 어디로 나가는지다
        (frontmatter / body / settings).
        """
        import enum
        from typing import get_args

        from daedalus.model.plugin.agent import AgentDefinition
        from daedalus.model.plugin.field_matrix import (
            AGENT_FIELD_MATRIX,
            SKILL_FIELD_MATRIX,
        )

        comp = self._find_component(name)
        config = getattr(comp, "config", None)
        if config is None:
            raise ValueError(f"'{name}'에는 config가 없습니다.")

        if isinstance(comp, AgentDefinition):
            matrix = AGENT_FIELD_MATRIX
        else:
            matrix = SKILL_FIELD_MATRIX.get(self._skill_matrix_key(comp), {})

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
        return {"component": comp.name, "kind": self._component_kind(comp), "fields": out}

    @staticmethod
    def _skill_matrix_key(comp: Any) -> str:
        """SKILL_FIELD_MATRIX의 키."""
        return str(getattr(comp, "kind", "")).replace("_skill", "")

    def set_component_field(
        self, name: str, field: str, value: Any
    ) -> dict[str, Any]:
        """스킬/에이전트 프론트매터 필드 하나를 설정한다.

        field는 `list_component_fields`가 돌려주는 이름(model / tools /
        permission_mode / allowed_tools / …). value는 JSON 값이며 enum 필드는 값
        문자열로 준다(예: model="sonnet", permission_mode="acceptEdits").
        목록 필드는 배열로 준다.

        description / when_to_use / hooks는 전용 도구를 쓴다.
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd

        comp = self._find_component(name)
        config = getattr(comp, "config", None)
        if config is None:
            raise ValueError(f"'{name}'에는 config가 없습니다.")
        if field == "hooks":
            raise ValueError("훅 참조는 set_component_hooks를 쓰세요.")
        if not hasattr(config, field):
            known = [
                f["field"] for f in self.list_component_fields(name)["fields"]
            ]
            raise ValueError(
                f"'{self._component_kind(comp)}'에는 '{field}' 필드가 없습니다. "
                f"사용 가능: {', '.join(known)}"
            )

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
        return {
            "component": comp.name,
            "field": field,
            "old": getattr(old, "value", old),
            "new": getattr(coerced, "value", coerced),
        }
