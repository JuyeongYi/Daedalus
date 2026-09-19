# daedalus/view/actions/external_registration.py
"""외부 플러그인 항목을 프로젝트에 **등록**하는 액션 (WP-C).

두 조작의 실체가 여기 하나씩 있고, 레지스트리 도크(🔌/🧷 탭)와 MCP가 **같은
함수**를 부른다(원칙 1) — 한쪽에만 자동 사용 선언을 넣으면 GUI로 등록한
프로젝트와 MCP로 등록한 프로젝트가 서로 다른 물건이 된다.

1. `register_external_agent` — 카탈로그의 외부 에이전트를 `external_agent`
   (그래프 노드) 또는 `external_fork_agent`(fork 실행 기반)로 등록한다.
   **역할은 등록 시점에 고정**이라 같은 정본이 이미 등록돼 있으면 거절한다
   (사용자 확정 2026-09-19). 플러그인이 아직 사용 선언되지 않았으면 **같은
   MacroCommand 안에서** 선언까지 한다 — 선언 없는 등록은 빌드가 배선을 내지
   않아 런타임에 조용히 사라진다(원칙 5).
2. `add_skill_ref_to_agent` — 외부 플러그인 스킬 참조(`플러그인:스킬`)를
   에이전트 `config.skills`에 더한다. 외부 스킬을 쓰는 **유일한 경로**다(WP-B).

둘 다 `CommandStack` 경유라 Ctrl+Z 하나로 되돌아간다(원칙 3) —
`SetAttrCmd`에는 항상 **새 리스트**를 넘기고, 값이 같으면 커맨드를 쌓지 않는다.
"""
from __future__ import annotations

from daedalus.model.plugin.agent import ExternalAgent, ExternalForkAgent

#: 외부 정본을 갖는 **에이전트 종류**의 config 어휘 — 등록이 고를 수 있는 역할.
#: 클래스 선언에서 파생한다(kind 문자열을 손으로 적지 않는다).
EXTERNAL_AGENT_KINDS: tuple[str, ...] = (
    ExternalAgent.CONFIG_CLS.KIND,
    ExternalForkAgent.CONFIG_CLS.KIND,
)


def declare_plugin_cmd(project, source: str):
    """`source`의 플러그인이 미선언이면 선언을 더하는 `SetAttrCmd` (아니면 None).

    카탈로그 창의 체크박스(`WrapCatalogDialog.set_plugin_used`)와 **같은 필드를
    같은 방식으로** 바꾼다 — 새 리스트를 `SetAttrCmd`로 대입한다(제자리 수정은
    undo가 같은 객체를 가리켜 죽는다).
    """
    from daedalus.model.plugin.config import (
        declared_external_plugin_ids,
        external_plugin_id_declared,
    )
    from daedalus.view.commands.attr_commands import SetAttrCmd

    plugin_id, sep, _ = (source or "").partition(":")
    plugin_id = plugin_id.strip()
    if not sep or not plugin_id:
        # 형식이 깨진 정본 참조 — 선언할 플러그인을 알 수 없다. 검증의
        # `external_source_missing`이 고칠 자리를 말한다(여기서 지어내지 않는다).
        return None
    declared = declared_external_plugin_ids(project)
    if external_plugin_id_declared(plugin_id, declared):
        return None
    new_list = [*(getattr(project, "external_plugins", None) or []), plugin_id]
    return SetAttrCmd(
        project,
        "external_plugins",
        new_list,
        label=f"외부 플러그인 사용 선언: {plugin_id}",
        script=f"set_external_plugins({new_list!r})",
    )


def default_registration_name(project, agent_type: str) -> str:
    """등록될 컴포넌트의 기본 이름 — 에이전트 이름, 충돌 시 `<플러그인>-<이름>`.

    구버전 파일 마이그레이션과 **같은 규칙**이다
    (`model.plugin.names.external_ref_name_candidates`) — 같은 외부 에이전트가
    등록 경로에 따라 다른 이름으로 태어나면 안 된다.
    """
    from daedalus.model.plugin.names import (
        external_ref_name_candidates,
        free_component_name,
    )

    taken = {
        c.name
        for c in [
            *(getattr(project, "skills", None) or []),
            *(getattr(project, "agents", None) or []),
        ]
    }
    return free_component_name(taken, *external_ref_name_candidates(agent_type))


def register_external_agent(
    window,
    agent_type: str,
    kind: str,
    *,
    name: str | None = None,
    description: str = "",
    scene=None,
    x: float | None = None,
    y: float | None = None,
) -> object:
    """외부 플러그인 에이전트를 컴포넌트로 등록한다 — **1 undo 단위**.

    Args:
        agent_type: 카탈로그가 낸 `플러그인[@마켓]:이름` 원문(CC가 찾는 이름).
        kind: `external_agent`(그래프 노드) / `external_fork_agent`(fork 기반).
        name: 컴포넌트 이름. 생략하면 `default_registration_name`.
        scene/x/y: 함께 주면 캔버스에도 **같은 undo 단위로** 놓는다(배치되지
            않는 종류면 좌표는 무시된다 — `creation.placement_cmds`).

    Raises:
        ValueError: 종류·정본이 잘못됐거나, 같은 정본이 **이미 등록**돼 있을 때
            (역할 고정 — 조용히 두 번째를 만들면 `external_source_role_conflict`
            에러가 되어 컴파일이 멈춘다).
    """
    from daedalus.model.plugin.wrap_catalog import registered_external_component
    from daedalus.view.actions.creation import make_component, placement_cmds
    from daedalus.view.commands.base import Command, MacroCommand
    from daedalus.view.commands.component_commands import CreateComponentCmd

    if kind not in EXTERNAL_AGENT_KINDS:
        raise ValueError(
            f"'{kind}'는 외부 정본을 갖는 에이전트 종류가 아닙니다 — "
            f"사용 가능: {', '.join(EXTERNAL_AGENT_KINDS)}"
        )
    agent_type = (agent_type or "").strip()
    if not agent_type:
        raise ValueError(
            "등록할 외부 에이전트의 정본(`플러그인:이름`)이 비어 있습니다."
        )
    project = getattr(window, "_project", None)
    if project is None:
        raise ValueError("열려 있는 프로젝트가 없습니다.")

    existing = registered_external_component(project, agent_type)
    if existing is not None:
        raise ValueError(
            f"'{agent_type}'은(는) 이미 '{existing.name}'({existing.kind})로 "
            f"등록돼 있습니다 — 한 외부 에이전트의 역할은 등록할 때 하나로 "
            f"고정됩니다(그래프 노드 / fork 실행 기반). 역할을 바꾸려면 "
            f"'{existing.name}'을(를) 지우고 다시 등록하세요."
        )

    name = (name or "").strip() or default_registration_name(project, agent_type)
    component = make_component(window, kind, name, description, source=agent_type)
    if component is None:  # pragma: no cover - 위에서 종류를 이미 검증한다
        raise ValueError(f"알 수 없는 종류 '{kind}'.")

    children: list[Command] = []
    declare = declare_plugin_cmd(project, agent_type)
    if declare is not None:
        children.append(declare)
    children.append(CreateComponentCmd(project, component))
    if scene is not None and x is not None and y is not None:
        children.extend(placement_cmds(scene, window, component, x, y))
    window._project_vm.execute(
        MacroCommand(children, f"외부 에이전트 '{agent_type}' 등록")
    )
    panel = getattr(window, "_registry_panel", None)
    if panel is not None:
        panel.set_project(project)
    return component


def add_skill_ref_to_agent(window, agent, skill_ref: str) -> bool:
    """외부 스킬 참조를 에이전트 `config.skills`에 더한다. 변화 없으면 False.

    `skills`를 갖지 않는 종류(외부 정본 에이전트 — 산출 파일이 없다)는 거절한다.
    이미 같은 참조가 있으면 **커맨드를 쌓지 않는다**(원칙 3 — 값이 같으면
    undo 스택에 빈 칸을 만들지 않는다).
    """
    from daedalus.model.plugin.field_matrix import AgentField
    from daedalus.model.plugin.kinds import spec_for
    from daedalus.view.commands.attr_commands import SetAttrCmd

    skill_ref = (skill_ref or "").strip()
    if not skill_ref:
        raise ValueError("더할 스킬 참조가 비어 있습니다.")
    if AgentField.SKILLS not in spec_for(agent).field_matrix:
        raise ValueError(
            f"'{agent.name}'({agent.kind})에는 skills 칸이 없습니다 — 정본이 그 "
            f"플러그인의 파일이라 우리가 프론트매터를 내지 않습니다. "
            f"프로젝트 fork 에이전트나 워크플로 에이전트를 고르세요."
        )
    current = list(getattr(agent.config, "skills", None) or [])
    if skill_ref in current:
        return False
    new_list = [*current, skill_ref]
    window._project_vm.execute(SetAttrCmd(
        agent.config,
        "skills",
        new_list,
        label=f"'{agent.name}' skills에 '{skill_ref}' 추가",
        script=f'set_component_field("{agent.name}", "skills", {new_list!r})',
    ))
    return True


# ─────────────────── 레지스트리 도크 핸들러 (GUI 전용) ───────────────────
#
# 위 두 함수는 MCP와 공유하는 **실체**라 창을 모른다. 아래 둘은 그 실체에
# 창의 옷(거절 다이얼로그·상태 문구·패널 재그리기)을 입힌 얇은 껍질이고
# 레지스트리 시그널만 부른다 — `actions/preview.show_preview_dialog`와 같은
# 지위다. 거절을 삼키지 않는 것이 이 껍질의 유일한 책임이다(원칙 5).


def register_from_registry(window, agent_type: str, kind: str) -> object | None:
    """🔌 탭 우클릭 등록 — 실패는 이유를 담은 경고 다이얼로그로 말한다."""
    from PySide6.QtWidgets import QMessageBox

    try:
        component = register_external_agent(window, agent_type, kind)
    except ValueError as exc:
        QMessageBox.warning(window, "등록할 수 없습니다", str(exc))
        return None
    window._status_label.setText(
        f"'{agent_type}'을(를) '{component.name}'({kind})로 등록했습니다."
    )
    return component


def attach_from_registry(window, skill_ref: str, agent) -> bool:
    """🧷 탭 우클릭 추가 — 값이 같으면 "이미 가지고 있다"고 말한다."""
    from PySide6.QtWidgets import QMessageBox

    try:
        changed = add_skill_ref_to_agent(window, agent, skill_ref)
    except ValueError as exc:
        QMessageBox.warning(window, "추가할 수 없습니다", str(exc))
        return False
    name = getattr(agent, "name", "?")
    window._status_label.setText(
        f"'{name}'의 skills에 '{skill_ref}'를 더했습니다."
        if changed
        else f"'{name}'은(는) 이미 '{skill_ref}'를 가지고 있습니다."
    )
    window._registry_panel.set_project(window._project)
    return changed


def show_catalog(window) -> None:
    """외부 플러그인 카탈로그 창 (WP-WR, D2) — 도구 메뉴와 🔌/🧷 탭의 "+".

    창을 닫으면 레지스트리가 카탈로그를 **다시 훑는다**(WP-C) — 여기서 폴더를
    등록하거나 실물을 받아 왔을 수 있고, 그러면 미등록 목록·스킬 참조 목록이
    달라진다. 스캔은 느려서 매 재그리기에 끼울 수 없으므로 이 자리가 유일한
    명시 새로고침 지점이다.
    """
    from daedalus.view.editors.wrap_catalog_dialog import WrapCatalogDialog

    WrapCatalogDialog(window).exec()
    window._registry_panel.refresh_catalog()
