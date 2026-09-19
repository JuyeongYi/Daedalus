# daedalus/mcp/tools/props.py
"""컴포넌트 생성·속성 도구 — 생성/이름/설명/프로젝트 속성 (WP-RF-3b · WP-8 ①).

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

from daedalus.model.plugin.enums import AgentField, SkillField
from daedalus.model.plugin.kinds import config_kinds_in
from daedalus.model.plugin.placement import is_canvas_placeable_role
from daedalus.model.plugin.roles import Bucket

from .fields import FieldTools
from .placement_prose import placement_role_prose


class PropsTools(FieldTools):
    """컴포넌트 생성 + 이름·설명·프로젝트 속성 편집.

    프론트매터 필드 도구(`list_component_fields`/`set_component_field`)는
    기저 `FieldTools`(`fields.py`)에 있다 — 한 파일에 두 책임을 두지 않는다(WP-8 ①).
    """

    #: create_skill이 받는 종류 (에이전트는 create_agent가 따로 맡는다).
    #: **레지스트리에서 파생**한다(WP-3) — 손으로 적어 두면 새 종류가 GUI에는
    #: 있고 MCP에는 없는 상태가 되고, 그것이 곧 MCP 패리티 파손이다(원칙 2).
    _SKILL_KINDS = config_kinds_in(Bucket.SKILLS)
    #: create_agent가 받는 종류 — 워크플로 에이전트 / fork 스킬의 실행 기반 /
    #: 외부 플러그인 에이전트 2역할.
    _AGENT_KINDS = config_kinds_in(Bucket.AGENTS)

    @staticmethod
    def _config_field_names(kind: str) -> frozenset[str]:
        """이 config 종류가 **실제로 가진** 필드 이름 (P3).

        생성 인자(`fork_agent` 등)가 어느 종류에 유효한지는
        손으로 적은 kind 목록이 아니라 **그 종류의 config 클래스**가 답한다 —
        목록을 따로 들면 새 종류가 인자를 갖고도 거절당하고(👻), 그 거절은
        테스트도 컴파일도 실패시키지 않는다.
        """
        from dataclasses import fields as dataclass_fields

        from daedalus.model.plugin.kinds import spec_by_config_kind

        return frozenset(
            f.name for f in dataclass_fields(spec_by_config_kind(kind).config_cls)
        )

    @classmethod
    def _reject_arg_the_kind_cannot_hold(
        cls, bucket: Bucket, kind: str, arg: str, field: str, absent: str
    ) -> None:
        """그 종류의 config에 없는 필드를 가리키는 생성 인자를 거절한다 (P3).

        거절은 **이유와 선택지**를 말한다(원칙 5) — 어느 종류가 이 인자를 받는지는
        레지스트리를 훑어 만든다. 순서는 선언 순서라 결정적이다.
        """
        from dataclasses import fields as dataclass_fields

        from daedalus.model.plugin.kinds import KIND_REGISTRY

        if field in cls._config_field_names(kind):
            return
        owners = [
            spec.config_kind
            for spec in KIND_REGISTRY.values()
            if spec.bucket is bucket
            and any(f.name == field for f in dataclass_fields(spec.config_cls))
        ]
        raise ValueError(
            f"{arg}는 설정에 '{field}'를 가진 종류 전용입니다 — "
            f"'{kind}'에는 {absent}. 사용 가능: {', '.join(owners) or '(없음)'}"
        )

    def _create_component(
        self,
        kind: str,
        name: str,
        description: str,
        x: float | None,
        y: float | None,
        agent: str | None = None,
        source: str | None = None,
    ) -> bool:
        """컴포넌트를 만들고(좌표가 있으면) 캔버스에 놓는다. 배치 여부를 돌려준다.

        **팩토리는 `view/actions/creation`이 단일 진실이다 (S1).** 예전에는 이
        모듈이 같은 5키 dict를 따로 들고 있어, 캔버스 "여기에 만들기"로 만든
        에이전트와 MCP로 만든 에이전트가 서로 다른 물건이 될 수 있었다(기본 포트
        `done`이 양쪽에 하드코딩돼 있었다). 좌표를 주면 생성+배치가
        `create_and_place`의 `MacroCommand`로 묶여 **1 undo 단위**가 된다(G14) —
        캔버스 메뉴와 완전히 같은 경로다.
        """
        from daedalus.model.plugin.kinds import spec_by_config_kind
        from daedalus.view.actions.creation import create_and_place, make_component

        win = self._window
        if x is None and y is None:
            component = make_component(
                win, kind, name, description, agent=agent, source=source
            )
            if component is None:  # pragma: no cover - 위에서 종류를 이미 검증한다
                raise ValueError(f"알 수 없는 종류 '{kind}'.")
            win._register_component(component)
            return False
        if x is None or y is None:
            raise ValueError(
                "x와 y는 함께 주어야 합니다 — 한쪽만으로는 배치 좌표가 정해지지 않습니다."
            )
        # 배치 가능성은 종류 목록이 아니라 **배치 역할 선언**이 답한다(P5) —
        # 음성 목록(`NO_PLACE_KINDS`)은 `is_canvas_placeable`과 어긋나도
        # 조용했다(WP-7 ②). 판정의 실체는 `model.plugin.placement` 하나이고,
        # 여기서 enum 비교를 손으로 적으면 갈린다(원칙 1). 컴포넌트가 아직
        # 없으므로(만들기 전에 거절한다) 역할을 받는 입구를 쓴다.
        role = spec_by_config_kind(kind).placement
        if not is_canvas_placeable_role(role):
            raise ValueError(
                f"'{kind}' 종류는 캔버스에 노드로 배치되지 않습니다 "
                f"({placement_role_prose(role)}) — x/y 없이 만드세요."
            )
        component = create_and_place(
            self._scene, win, kind, name, float(x), float(y), description,
            agent=agent, source=source,
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
        fork_agent: str = "",
    ) -> dict[str, Any]:
        """스킬을 만든다.

        kind: procedural(작업 지침·자체 FSM) / declarative(배경 지식) /
        transfer(전이 시 실행되는 보조 지침) / reference(참조 문서) /
        sync_fork/async_fork(본문이 서브에이전트의 작업 지시가 되는 단계 —
        sync는 `background: false`로 부른 쪽이 보고를 기다리고, async는
        `background: true`로 보고가 작업 알림으로 온다. 2026-09-17).

        fork_agent: 설정에 `agent`를 가진 종류(sync_fork/async_fork) 전용 —
        fork 에이전트(프론트매터 `agent`). 내장(general-purpose/Explore/Plan)
        또는 프로젝트에 **등록된 fork 에이전트**의 이름 중 하나다(정확 일치).
        다른 플러그인의 에이전트를 쓰려면 먼저
        `create_agent(kind="external_fork_agent", source="플러그인:이름")`으로
        등록하고 **그 컴포넌트 이름**을 준다 — 산출의 `agent:`에는 등록된
        source 원문이 나간다. 생략하면 general-purpose.
        절차형 ↔ fork 2종 전환은 `convert_skill`.
        에이전트에게 줄 지식도 전역 스킬로 만든다 — 전역 declarative와 에이전트
        노드에 링크된 reference는 컴파일 시 에이전트 skills 프론트매터에 자동
        합류된다(로컬 스킬은 퇴역, WP-RF-1c).

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
        if fork_agent:
            self._reject_arg_the_kind_cannot_hold(
                Bucket.SKILLS, kind, "fork_agent", SkillField.AGENT.value,
                "본문을 실행할 서브에이전트 개념이 없습니다",
            )
            from daedalus.view.actions.fork_skill import validate_fork_agent

            validate_fork_agent(self._project, fork_agent)
        self._reject_duplicate_name(name)
        placed = self._create_component(
            kind, name, description, x, y, agent=fork_agent or None
        )
        out: dict[str, Any] = {"created": name, "kind": kind, "placed": placed}
        # 실행 기반을 응답에 싣는 것은 "그 설정에 `agent`가 있는 종류"의
        # 성질이다 — fork 2종을 이름으로 열거하던 자리(P3).
        if SkillField.AGENT.value in self._config_field_names(kind):
            out["fork_agent"] = fork_agent or "general-purpose"
        return out

    def create_agent(
        self,
        name: str,
        description: str = "",
        x: float | None = None,
        y: float | None = None,
        kind: str = "agent",
        source: str = "",
    ) -> dict[str, Any]:
        """에이전트를 만든다 — 별도 컨텍스트의 작업자.

        kind: "agent"(워크플로 에이전트 — 캔버스 노드) / "fork_agent"(fork
        스킬의 실행 기반 — fsm·포트·배치 없음) / "external_agent"(다른
        플러그인의 서브에이전트를 **그래프 노드**로) / "external_fork_agent"
        (같은 것을 **fork 스킬의 실행 기반**으로). 캔버스에 놓이지 않는
        종류에 x/y를 주면 거절한다.

        source: 설정에 `source`를 가진 종류(external_agent/external_fork_agent)
        전용 — 그 플러그인의 서브에이전트를 가리키는 `플러그인[@마켓]:이름`
        원문이다(CC가 찾는 이름, 정확 일치). `list_external_plugins`의 에이전트
        행 `agent_type`이 그 값이다. **역할은 등록 시점에 고정된다** — 같은
        source를 두 종류로 등록하면 `external_source_role_conflict` 에러이고,
        역할을 바꾸려면 지우고 다시 만든다(사용자 확정 2026-09-19).

        절차는 본문(set_component_body)에, 결과 분기는 출력 포트
        (set_transfer_on)에 서술한다. 워크플로 에이전트는 기본 출력 포트
        'done' 하나로 시작한다(fork 에이전트는 포트가 없다 — 결과 분기는
        그를 부르는 fork 스킬의 보고 양식이 정한다). 외부 종류는 본문이
        없다(정본이 그 플러그인의 파일이고 우리는 산출 파일을 내지 않는다).

        x/y(G14): 함께 주면 만들자마자 그 좌표에 배치한다(1 undo 단위).
        """
        if kind not in self._AGENT_KINDS:
            raise ValueError(
                f"알 수 없는 에이전트 종류 '{kind}'. "
                f"사용 가능: {', '.join(self._AGENT_KINDS)}"
            )
        if source:
            self._reject_arg_the_kind_cannot_hold(
                Bucket.AGENTS, kind, "source", AgentField.SOURCE.value,
                "외부 정본 참조라는 개념이 없습니다",
            )
        self._reject_duplicate_name(name)
        placed = self._create_component(
            kind, name, description, x, y, source=source or None
        )
        out: dict[str, Any] = {"created": name, "kind": kind, "placed": placed}
        # 외부 정본을 갖는 종류만 응답에 싣는다 — "그 설정에 `source`가 있는
        # 종류"의 성질이지 종류 이름을 열거할 일이 아니다(create_skill 선례).
        if AgentField.SOURCE.value in self._config_field_names(kind):
            out["source"] = source
        return out

    def convert_skill(self, name: str, to: str) -> dict[str, Any]:
        """절차형 ↔ 동기/비동기 fork 스킬 전환 — **1 undo** (2026-09-17).

        to: "procedural" / "sync_fork" / "async_fork". 이름·본문·설명·포트·전이·
        배치는 그대로다. fork로 갈 때 `allowed_tools`(fork에서 효과 없음)를,
        절차형으로 갈 때 `agent`를 버리고 `dropped`로 알린다. sync ↔ async는
        버리는 것이 없다(`agent` 보존). fork의 fork 에이전트는 기본
        general-purpose이고 `set_component_field(name, "agent", ...)`로 바꾼다.

        편집기 "…로 전환" 버튼·캔버스 우클릭과 같은 실체
        (`actions/fork_skill.convert_skill_kind`).
        """
        from daedalus.view.actions.fork_skill import convert_skill_kind

        comp = self._find_component(name)
        result = convert_skill_kind(self._window, comp, to)
        return {"component": name, **result}

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
        fork 스킬 `agent`에 남은 이름은 그대로 둔다(되돌렸을 때
        참조가 돌아오지 않는 비대칭을 만들지 않기 위해서다). 남은 참조는
        `validate_project`의 `dangling_string_reference` 경고가 짚어 준다 —
        결과의 `still_referenced_by`로 그 목록을 함께 돌려준다.

        삭제할 수 없는 종류가 있으면 이유와 함께 거절한다(`can_delete()`).
        """
        from daedalus.model.plugin.placement import fork_skills_using
        from daedalus.model.plugin.roles import Bucket

        comp = self._find_component(name)
        project = self._project

        # 누가 이 이름을 문자열로 들고 있는가(Q14) — 종류를 열거하는 대신
        # **네임스페이스**(버킷)로 묻고, 설정이 무엇을 가리키는지는 설정이
        # `name_refs()`로 말한다(WP-2d). 새 설정 종류가 이름 참조를 들면
        # 여기 고치지 않아도 자동으로 잡힌다.
        still: list[str] = []
        if comp.BUCKET is Bucket.AGENTS:
            # 역참조 목록의 실체는 model의 `fork_skills_using` 하나다 —
            # 화면(삭제 확인·"사용하는 fork 스킬")·산출과 같은 목록을 말한다.
            still.extend(
                f"skill:{skill_name}.agent"
                for skill_name in fork_skills_using(comp, project)
            )
        else:
            for agent in project.agents:
                if name in agent.config.name_refs(Bucket.SKILLS):
                    still.append(f"agent:{agent.name}.skills")

        kind = comp.kind
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
        # `when_to_use`는 기저가 선언한 형상이다(에이전트는 기본값 "") —
        # 문자열로 더듬을 필요가 없다(WP-2d Q4).
        old = comp.when_to_use
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
                f"'{name}'({comp.kind})에는 진입점 프리셋을 적용할 "
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
