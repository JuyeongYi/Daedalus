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

    #: create_skill이 받는 종류 (에이전트는 create_agent가 따로 맡는다).
    _SKILL_KINDS = ("procedural", "declarative", "transfer", "reference", "wrapped")

    def _create_component(
        self,
        kind: str,
        name: str,
        description: str,
        x: float | None,
        y: float | None,
    ) -> bool:
        """컴포넌트를 만들고(좌표가 있으면) 캔버스에 놓는다. 배치 여부를 돌려준다.

        **팩토리는 `view/actions/creation`이 단일 진실이다 (S1).** 예전에는 이
        모듈이 같은 5키 dict를 따로 들고 있어, 캔버스 "여기에 만들기"로 만든
        에이전트와 MCP로 만든 에이전트가 서로 다른 물건이 될 수 있었다(기본 포트
        `done`이 양쪽에 하드코딩돼 있었다). 좌표를 주면 생성+배치가
        `create_and_place`의 `MacroCommand`로 묶여 **1 undo 단위**가 된다(G14) —
        캔버스 메뉴와 완전히 같은 경로다.
        """
        from daedalus.view.actions.creation import (
            NO_PLACE_KINDS,
            create_and_place,
            make_component,
        )

        win = self._window
        if x is None and y is None:
            component = make_component(win, kind, name, description)
            if component is None:  # pragma: no cover - 위에서 종류를 이미 검증한다
                raise ValueError(f"알 수 없는 종류 '{kind}'.")
            win._register_component(component)
            return False
        if x is None or y is None:
            raise ValueError(
                "x와 y는 함께 주어야 합니다 — 한쪽만으로는 배치 좌표가 정해지지 않습니다."
            )
        if kind in NO_PLACE_KINDS:
            raise ValueError(
                f"'{kind}' 종류는 캔버스에 노드로 배치되지 않습니다 "
                "(declarative는 배경 지식, transfer는 전이 위의 단계입니다) — "
                "x/y 없이 만드세요."
            )
        component = create_and_place(
            self._scene, win, kind, name, float(x), float(y), description
        )
        if component is None:
            raise RuntimeError(f"'{name}'을(를) 만들지 못했습니다.")
        return True

    def create_skill(
        self,
        name: str,
        kind: str = "procedural",
        description: str = "",
        x: float | None = None,
        y: float | None = None,
        source: str = "",
        usage: str = "",
    ) -> dict[str, Any]:
        """스킬을 만든다.

        kind: procedural(작업 지침·자체 FSM) / declarative(배경 지식) /
        transfer(전이 시 실행되는 보조 지침) / reference(참조 문서) /
        wrapped(다른 플러그인 스킬의 랩핑 — 본문 없음, WP-WR).
        에이전트에게 줄 지식도 전역 스킬로 만든다 — 전역 declarative와 에이전트
        노드에 링크된 reference는 컴파일 시 에이전트 skills 프론트매터에 자동
        합류된다(로컬 스킬은 퇴역, WP-RF-1c).

        source(WP-WR): kind="wrapped" 전용 — `플러그인[@마켓]:스킬` 형식으로
        감쌀 외부 스킬을 지정한다(`list_wrappable_skills`가 후보와 source
        문자열을 준다). source의 플러그인이 external_plugins에 미선언이면
        **선언까지 함께** 1 undo로 들어가고, x/y를 함께 주면 배치까지 같은
        1 undo다(레지스트리 🔗 후보 행의 캔버스 드롭과 같은 실체 —
        `actions/creation.create_wrapped_skill`). 다른 종류에 주면 거절한다
        (조용히 무시하면 "설정했는데 아무 일도 일어나지 않는" 상태가 된다).
        생략하면 나중에 `set_component_field(name, "source", ...)`로 채운다.

        usage(WP-WR): kind="wrapped"+source 전용 — "state"(기본: 워크플로
        단계, SKILL.md 산출·단일 배치) 또는 "reference"(참조 노드 복수 배치,
        **산출 파일 없음** — 링크된 노드의 산출에 consult 지시만 합류).
        생성 시 **고정**되며 한 스킬 두 용도는 금지다(어긋난 배치는
        `wrapped_usage_conflict` 경고). reference의 배치·링크는
        `place_reference`/`link_reference`를 쓴다.

        x/y(G14): **함께** 주면 만들자마자 그 좌표에 배치한다 — 생성과 배치가
        1 undo 단위로 묶인다(캔버스 "여기에 만들기"와 같은 경로). reference는
        상태 노드가 아니라 참조 노드로 놓인다. declarative/transfer는 캔버스
        노드가 아니므로 좌표를 주면 거절한다. 생략하면 만들기만 하고, 나중에
        `place_component`/`place_reference`로 놓는다.
        """
        if kind not in self._SKILL_KINDS:
            raise ValueError(
                f"알 수 없는 스킬 종류 '{kind}'. 사용 가능: {', '.join(self._SKILL_KINDS)}"
            )
        if source and kind != "wrapped":
            raise ValueError(
                f"source는 kind='wrapped' 전용입니다 — '{kind}' 스킬에는 감쌀 "
                "외부 스킬 개념이 없습니다."
            )
        if usage and not source:
            raise ValueError(
                "usage는 kind='wrapped'+source와 함께만 씁니다 — 용도는 랩핑 "
                "스킬의 개념입니다(state/reference)."
            )
        self._reject_duplicate_name(name)
        if source:
            if (x is None) != (y is None):
                raise ValueError(
                    "x와 y는 함께 주어야 합니다 — 한쪽만으로는 배치 좌표가 "
                    "정해지지 않습니다."
                )
            from daedalus.view.actions.creation import create_wrapped_skill

            component = create_wrapped_skill(
                self._window, source, name=name, description=description,
                x=x, y=y, usage=usage or "state",
            )
            if component is None:  # pragma: no cover — 프로젝트는 항상 있다
                raise RuntimeError(f"'{name}'을(를) 만들지 못했습니다.")
            return {
                "created": name,
                "kind": kind,
                "usage": component.config.usage,
                "placed": x is not None,
                "source": source,
                "external_plugins": list(self._project.external_plugins),
            }
        placed = self._create_component(kind, name, description, x, y)
        return {"created": name, "kind": kind, "placed": placed}

    def create_agent(
        self,
        name: str,
        description: str = "",
        x: float | None = None,
        y: float | None = None,
    ) -> dict[str, Any]:
        """에이전트를 만든다 — 별도 컨텍스트의 작업자.

        절차는 본문(set_component_body)에, 결과 분기는 출력 포트
        (set_transfer_on)에 서술한다. 기본 출력 포트 'done' 하나로 시작한다.

        x/y(G14): 함께 주면 만들자마자 그 좌표에 배치한다(1 undo 단위).
        """
        self._reject_duplicate_name(name)
        placed = self._create_component("agent", name, description, x, y)
        return {"created": name, "kind": "agent", "placed": placed}

    def rename_component(self, name: str, new_name: str) -> dict[str, Any]:
        """컴포넌트 이름을 바꾼다 — 문자열 참조도 함께 갱신된다."""
        from daedalus.view.commands.component_commands import RenameComponentCmd

        comp = self._find_component(name)
        self._reject_duplicate_name(new_name)
        self._vm.execute(RenameComponentCmd(self._project, comp, name, new_name))
        self._window._registry_panel.set_project(self._project)
        return {"renamed": name, "to": new_name}

    def delete_component(self, name: str) -> dict[str, Any]:
        """컴포넌트(스킬/에이전트)를 삭제한다 — **undo 가능**(Ctrl+Z).

        캔버스 배치와 연결 전이, 참조 노드 배치, 다른 FSM 안에서 이 컴포넌트를
        가리키던 skill_ref까지 함께 정리하고, 전부 한 번의 undo로 되돌아온다.

        **이름 참조는 정리하지 않는다** — 에이전트 `config.skills`나
        `ProceduralSkillConfig.agent`에 남은 이름은 그대로 둔다(되돌렸을 때
        참조가 돌아오지 않는 비대칭을 만들지 않기 위해서다). 남은 참조는
        `validate_project`의 `dangling_string_reference` 경고가 짚어 준다 —
        결과의 `still_referenced_by`로 그 목록을 함께 돌려준다.

        **랩핑 스킬(kind="wrapped")은 삭제할 수 없다**(사용자 확정 2026-09-07) —
        `set_wrapped_enabled(name, false)`로 끄면 산출·배선에서 빠지고 소스와
        배치는 남아 언제든 되돌릴 수 있다.
        """
        from daedalus.model.plugin.agent import AgentDefinition
        from daedalus.model.plugin.config import AgentConfig, ProceduralSkillConfig
        from daedalus.model.plugin.skill import Skill

        comp = self._find_component(name)
        project = self._project

        still: list[str] = []
        if isinstance(comp, AgentDefinition):
            for skill in project.skills:
                cfg = getattr(skill, "config", None)
                if isinstance(cfg, ProceduralSkillConfig) and cfg.agent == name:
                    still.append(f"skill:{skill.name}.agent")
        if isinstance(comp, Skill):
            for agent in project.agents:
                cfg = getattr(agent, "config", None)
                if isinstance(cfg, AgentConfig) and name in (cfg.skills or []):
                    still.append(f"agent:{agent.name}.skills")

        kind = getattr(comp, "kind", type(comp).__name__)
        self._window.delete_component(comp)
        return {"deleted": name, "kind": kind, "still_referenced_by": still}

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

    def set_entry_preset(self, name: str, preset: str) -> dict[str, Any]:
        """진입 의미론 프리셋을 적용한다 — user_invocable × disable_model_invocation
        세트 지정 (A8/G5).

        preset: entry(진입점으로) / user_only(유저 전용 진입점으로) /
        pure(순수 상태로) / default(일반 상태로 — 두 필드 미지정).

        캔버스 노드 우클릭 "진입점 설정" 서브메뉴·스킬 에디터 프론트매터의
        "진입 설정" 콤보와 **같은 실체**(`view/actions/entrypoint.apply_entry_preset`)를
        호출한다 — 두 필드가 1 undo 단위로 함께 바뀐다. 이미 그 프리셋이면
        아무것도 하지 않는다(`changed`: False).

        FIXED 종류(transfer/reference)와 에이전트에는 적용할 수 없다 — 그
        종류는 컴파일이 값을 강제해 프리셋을 걸어도 아무 일도 일어나지
        않기 때문이다(거부하며 이유를 말한다).
        """
        from daedalus.view.actions.entrypoint import (
            EntryPreset,
            apply_entry_preset,
            current_entry_preset,
            supports_entry_presets,
        )

        comp = self._find_component(name)
        if not supports_entry_presets(comp):
            raise ValueError(
                f"'{name}'({self._component_kind(comp)})에는 진입점 프리셋을 적용할 "
                "수 없습니다 — user_invocable/disable_model_invocation이 고정되어 "
                "있거나(transfer/reference) 그 필드 자체가 없는 종류(에이전트)입니다."
            )
        try:
            target = EntryPreset(preset)
        except ValueError:
            allowed = ", ".join(p.value for p in EntryPreset)
            raise ValueError(f"알 수 없는 프리셋 '{preset}'. 사용 가능: {allowed}") from None

        before = current_entry_preset(comp)
        changed = apply_entry_preset(self._vm, comp, target)
        return {
            "component": name,
            "preset": target.value,
            "changed": changed,
            "before": before.value if before is not None else None,
        }

    def set_project_properties(
        self,
        name: str = "",
        description: str = "",
        version: str = "",
        build_target: str = "",
        emit_progress_hook: bool | None = None,
    ) -> dict[str, Any]:
        """플러그인 매니페스트 속성을 바꾼다 — 빈 값(문자열 필드)/None(불리언
        필드)은 "건드리지 않음".

        name은 plugin.json의 플러그인 식별자가 되므로 `^[a-z0-9][a-z0-9-]*$`를
        지켜야 컴파일 게이트를 통과한다(F7에서는 경고 등급).
        build_target: marketplace / local.
        emit_progress_hook: 세션 시작 시 진행 상태 자동 주입(SessionStart 훅)
        토글 — GUI 프로젝트 속성 다이얼로그의 체크박스와 같다(WP-RS). 문자열
        필드와 규약이 다른 이유: 이 필드는 `bool`(A8 tri-state 아님)이라 빈
        문자열로 "미변경"을 표현할 자리가 없다 — 대신 `None`이 그 자리다.
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
            "emit_progress_hook": project.emit_progress_hook,
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
        if emit_progress_hook is not None:
            cmds.append(
                SetAttrCmd(
                    project,
                    "emit_progress_hook",
                    bool(emit_progress_hook),
                    label=f"진행 상태 자동 주입 → {bool(emit_progress_hook)}",
                    script=f'set_project_properties(emit_progress_hook={bool(emit_progress_hook)})',
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
            "emit_progress_hook": project.emit_progress_hook,
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

        **null = 미지정**(A8). `user_invocable` / `disable_model_invocation`처럼
        tri-state인 필드에 null을 주면 프론트매터 키 자체가 생략되어 CC 기본값에
        위임된다 — "기본값과 같은 값을 못 박는 것"과 다르다. Optional로 선언되지
        않은 필드에 null을 주면 거절한다.

        description / when_to_use / hooks는 전용 도구를 쓴다.
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd

        comp = self._find_component(name)
        config = getattr(comp, "config", None)
        if config is None:
            raise ValueError(f"'{name}'에는 config가 없습니다.")
        if field == "hooks":
            raise ValueError("훅 참조는 set_component_hooks를 쓰세요.")
        if field == "usage":
            raise ValueError(
                "usage는 직접 설정할 수 없습니다 — 랩핑 스킬의 용도는 최초 "
                "배치(또는 create_skill의 usage 인자)가 고정하며, 한 스킬 두 "
                "용도는 금지입니다(WP-WR). 바꾸려면 스킬을 지우고 다시 만드세요."
            )
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
