# daedalus/model/serialize/migrate.py
"""format 1 → 2 단방향 마이그레이션 (WP-SZ 분해, 이동만).

``deserialize_project`` 가 format 1(또는 키 부재 구버전) 파일을 읽기 전에 태우는
집약 마이그레이션이다. 왕복 보존은 없다 — 열면 v2 로 저장된다.

``_deser_section`` 이 여기 있는 이유: ``sections`` 트리는 v1 파일에만 존재하는
형태이고(WP-SB 로 본문은 ``body`` 단일 문자열이 됐다), 유일한 호출자가
``_migrate_v1`` 이다. deser 에 두면 ``deser → migrate → deser`` 순환이 생긴다.
"""
from __future__ import annotations

import copy
from typing import Any

from daedalus.model.fsm.section import Section, render_markdown
from daedalus.model.serialize.ser import FORMAT_VERSION


# ═══════════════════════ v1 → v2 마이그레이션 ═══════════════════════


def _migrate_v1(data: dict, warnings: list[str]) -> dict:
    """format 1(또는 키 부재) dict → format 2 dict. 단방향 — 입력은 변형하지 않는다.

    흩어져 있던 구버전 마이그레이션을 한 함수로 집약했다 (WP-RF-1b):
      1. delegation 정의 드롭 (퇴역 개념 — 경고 후 드롭)
      1-b. 에이전트 로컬 스킬 → **전역 스킬로 승격** (WP-RF-1c — 이름 충돌 시
         ``<agent>--<name>``으로 개명, 승격마다 경고 1건. 승격된 스킬은 이후
         전역 스킬과 완전히 같은 경로를 탄다 — 본문 마이그레이션·블랙보드
         parent 재배선 포함)
      2. 컴포넌트 본문: ``sections`` 트리 → ``body`` 평탄화(render_markdown) +
         ``${CLAUDE_PLUGIN_ROOT}/files/`` → ``${ROOT}/files/`` 치환(WP-RT)
      3. 퇴역 키 드롭: ``entry_paths`` / ``caller_contracts`` /
         전이의 ``target_port`` (WP-IP/WP-CT — 경고 없음, 퇴역 개념)
      4. 에이전트 출력 포트: ``transfer_on`` 부재 시 내부 FSM의 ExitPoint
         이름·색 승계 (WP-AF)
      5. 훅: 커맨드 하나짜리 구버전(HookDef.command/timeout) → handlers 목록,
         핸들러의 ``command`` → ``script`` (WP-HK/WP-HS)
      6. ``field_type: "number"`` → ``"float"`` (FieldType.NUMBER 퇴역)
    """
    from daedalus.model.plugin.variables import migrate_legacy_file_refs

    data = copy.deepcopy(data)
    data["format"] = FORMAT_VERSION

    # 1) delegation 드롭 — 위임을 가리키던 placement skill_ref는 해당 id가
    # 레지스트리에 없으므로 pass2에서 dangling 경고와 함께 None으로 정리된다.
    dropped_delegations = data.pop("delegations", [])
    if dropped_delegations:
        names = ", ".join(
            f"'{d.get('name', '?')}'" for d in dropped_delegations
        )
        warnings.append(
            f"위임 정의 {len(dropped_delegations)}건({names})은 퇴역한 개념이라 "
            f"드롭했습니다 — 위임 지시는 스킬 본문에 서술하세요."
        )

    # 1-b) 에이전트 로컬 스킬 → 전역 스킬 승격 (WP-RF-1c).
    _promote_local_skills(data, warnings)
    # 1-c) 절차형 `context: fork` → fork 스킬 종류 (2026-09-13).
    converted = migrate_skill_context(data, warnings)
    # 1-d) fork 스킬 1종 → sync/async 2종 + fork 에이전트 종류 (2026-09-17).
    # 반드시 1-c **뒤**다 — 1-c가 만든 fork 스킬도 대상이고, 그 스킬에는
    # "이전 산출" 이력이 없어 미배치 경고를 내지 않는다.
    migrate_fork_split(data, warnings, skip_warning_for=converted)

    # 2)+3) 컴포넌트 공통 — 본문 평탄화 + 경로 변수 치환 + 퇴역 키 드롭
    def _migrate_component(d: dict) -> None:
        if "body" not in d and "sections" in d:
            d["body"] = render_markdown(
                [_deser_section(s) for s in d["sections"]]
            )
        d.pop("sections", None)
        d["body"] = migrate_legacy_file_refs(d.get("body") or "")
        d.pop("entry_paths", None)
        d.pop("caller_contracts", None)

    for s in data.get("skills", []) or []:
        _migrate_component(s)
    for a in data.get("agents", []) or []:
        _migrate_component(a)
        # 4) ExitPoint → transfer_on 승계 (이름·색, 단방향 — 경고 없음).
        # ExitPoint 상태 자체는 fsm에 남는다(순수 FSM 개념).
        if not a.get("transfer_on"):
            exit_states = [
                st for st in (a.get("fsm") or {}).get("states", [])
                if st.get("kind") == "exit_point"
            ]
            if exit_states:
                a["transfer_on"] = [
                    {
                        "name": st.get("name", ""),
                        "color": st.get("color", "#cc6666"),
                        "description": "",
                    }
                    for st in exit_states
                ]

    # 3) 전이의 target_port 드롭 — 모든 머신(스킬/에이전트 fsm(승격된 로컬 포함) +
    # 프로젝트 그래프, sub_machine/Region 재귀)의 transitions에서.
    for machine in _v1_all_machines(data):
        for t in machine.get("transitions", []) or []:
            t.pop("target_port", None)

    # 5) 훅 마이그레이션 — 훅 하나 = 커맨드 하나였던 시절의 형태.
    for h in data.get("hook_library", []) or []:
        if "handlers" not in h:
            legacy_command = h.pop("command", "") or ""
            legacy_timeout = h.pop("timeout", None)
            h["handlers"] = (
                [{
                    "kind": "command",
                    "script": legacy_command,
                    "timeout": legacy_timeout,
                }]
                if legacy_command or legacy_timeout is not None
                else []
            )
        else:
            for hh in h.get("handlers", []) or []:
                if (
                    isinstance(hh, dict)
                    and "script" not in hh
                    and "command" in hh
                ):
                    hh["script"] = hh.pop("command") or ""

    # 6) field_type "number" → "float" — Variable/DynamicField dict는 머신 내부
    # (상태 inputs/outputs·액션 output_variable·머신 블랙보드)와 프로젝트 최상위
    # 블랙보드에만 있다. mcp_server_defs 같은 자유 형식 config의 우연한
    # "field_type" 키를 건드리지 않도록 그 범위만 걷는다.
    for machine in _v1_all_machines(data):
        _v1_scrub_number(machine)
    _v1_scrub_number(data.get("blackboard"))
    return data


def needs_skill_context_migration(data: dict) -> bool:
    """스킬 config에 퇴역한 `context` 키가 남아 있는가 (format 2 파일 게이트)."""
    return any(
        isinstance(s.get("config"), dict) and "context" in s["config"]
        for s in data.get("skills", []) or []
    )


def migrate_skill_context(data: dict, warnings: list[str]) -> set[str]:
    """퇴역한 스킬 `context`/`agent` 키를 흡수한다 (제자리 변형, 2026-09-13).

    fork 실행은 별도 스킬 종류가 됐다(사용자 확정) — 절차형·선언형·전이형은
    더 이상 context·agent를 갖지 않는다.
    - 절차형 + `context: fork` → fork 스킬. `agent`가 비었으면 CC가 조용히 쓰던
      `general-purpose`를 명시한다. fork에서 효과가 없는 `allowed_tools`는
      버리고 경고한다.
    - 그 밖(inline 절차형, 전이형의 fork 포함)은 키를 버린다 — 전이형 fork는
      표현할 곳이 없어 경고한다.

    Returns: 이 호출이 fork 스킬로 바꾼 스킬 이름 집합. `migrate_fork_split`이
    그 집합을 **경고에서만** 제외한다(v1 파일에는 대응 산출 이력이 없다).
    """
    converted: set[str] = set()
    for s in data.get("skills", []) or []:
        cfg = s.get("config")
        if not isinstance(cfg, dict):
            continue
        if s.get("kind") in _FORK_SKILL_KINDS:
            # 이미 fork 스킬인 것은 건드리지 않는다 — 여기서 `agent`를 팝하면
            # 퇴역 키가 아니라 **살아 있는 필드**를 지운다.
            continue
        context = cfg.pop("context", None)
        agent = cfg.pop("agent", None)
        name = s.get("name", "?")
        if context != "fork":
            continue
        if s.get("kind") == "procedural_skill":
            s["kind"] = "fork_skill"
            cfg["kind"] = "fork"
            cfg["agent"] = agent or "general-purpose"
            dropped = cfg.pop("allowed_tools", None) or []
            cfg["allowed_tools"] = []
            note = (
                f" — fork에서 효과가 없는 allowed_tools({', '.join(dropped)})는 버렸습니다"
                if dropped else ""
            )
            converted.add(name)
            warnings.append(
                f"스킬 '{name}'(context: fork)을 fork 스킬로 바꿨습니다"
                f" (agent: {cfg['agent']}){note}."
            )
        else:
            warnings.append(
                f"스킬 '{name}'의 context: fork는 이 종류에서 퇴역해 버렸습니다 — "
                f"서브에이전트 실행이 필요하면 fork 스킬을 쓰세요."
            )
    return converted


#: 마이그레이션이 인식하는 fork 스킬 kind — 구 단일 종류 + 새 2종.
_FORK_SKILL_KINDS: tuple[str, ...] = (
    "fork_skill", "sync_fork_skill", "async_fork_skill",
)


def needs_fork_split_migration(data: dict) -> bool:
    """구 단일 fork 종류(`fork_skill`) 또는 미분류 fork 에이전트가 남아 있는가.

    format 2 파일 게이트다 — fork 2종 분리(2026-09-17) 이전에 저장된 파일은
    format이 같아도 내용이 다르므로 내용으로 스니핑한다
    (`needs_skill_context_migration` 선례).
    """
    if any(
        s.get("kind") == "fork_skill" for s in data.get("skills", []) or []
    ):
        return True
    return bool(_fork_agent_names(data))


def _fork_agent_names(data: dict) -> set[str]:
    """fork 에이전트로 재분류할 프로젝트 에이전트 이름 — 미배치 + fork 스킬이 참조.

    **모든 접근이 방어적이다**: pseudo 상태에는 `skill_ref` 키가 아예 없고
    (`ser.py`의 SimpleState 분기만 그 키를 쓴다), `graph`·`config` 키 부재는
    구버전 파일의 정상 입력이다.
    """
    placed = {
        st.get("skill_ref")
        for st in ((data.get("graph") or {}).get("states") or [])
    } - {None}
    fork_targets = {
        (s.get("config") or {}).get("agent")
        for s in data.get("skills", []) or []
        if s.get("kind") in _FORK_SKILL_KINDS
    } - {None, ""}
    return {
        a.get("name")
        for a in data.get("agents", []) or []
        if a.get("id") not in placed
        and a.get("name") in fork_targets
        and a.get("kind") != "fork_agent"
    } - {None}


def migrate_fork_split(
    data: dict, warnings: list[str], *, skip_warning_for: set[str] | None = None
) -> None:
    """fork 스킬 1종 → sync/async 2종 + 에이전트 재분류 (제자리 변형, 2026-09-17).

    1. `fork_skill` → `sync_fork_skill`(`config.kind` `fork` → `sync_fork`).
       오늘 산출이 배치된 fork에 `background: false`를 냈으므로 **배치된 fork는
       동기가 곧 종전 동작**이라 경고가 없다. **미배치 fork**는 background 키가
       아예 없어 CC 기본값(백그라운드)으로 돌았으므로 동작이 바뀐다 — 경고 1건.
    2. 미배치 + fork 스킬이 참조하는 프로젝트 에이전트 → `fork_agent` 종류로.
       fsm·포트·배치·background·isolation 키를 드롭한다(없는 개념의 잔재 금지).
       배치 + 참조는 건드리지 않는다(검증이 짚는다).
    """
    skip = skip_warning_for or set()
    placed_ids = {
        st.get("skill_ref")
        for st in ((data.get("graph") or {}).get("states") or [])
    } - {None}
    rename = _fork_agent_names(data)

    for s in data.get("skills", []) or []:
        if s.get("kind") != "fork_skill":
            continue
        s["kind"] = "sync_fork_skill"
        cfg = s.get("config")
        if isinstance(cfg, dict) and cfg.get("kind") == "fork":
            cfg["kind"] = "sync_fork"
        name = s.get("name", "?")
        if s.get("id") in placed_ids or name in skip:
            continue
        warnings.append(
            f"미배치 fork 스킬 '{name}'을(를) 동기 fork로 이관했습니다 — 이전 "
            f"산출은 background 키가 없어 CC 기본값(백그라운드)으로 돌았습니다. "
            f"비동기가 필요하면 종류를 비동기 fork로 바꾸세요."
        )

    for a in data.get("agents", []) or []:
        if a.get("name") not in rename:
            continue
        a["kind"] = "fork_agent"
        a.setdefault("config", {})["kind"] = "fork_agent"
        for k in ("fsm", "transfer_on", "call_agents", "execution_policy",
                  "reference_placements", "graph_layout", "edge_layout"):
            a.pop(k, None)
        a["config"].pop("background", None)
        a["config"].pop("isolation", None)
        warnings.append(
            f"에이전트 '{a.get('name', '?')}'을(를) fork 에이전트 종류로 이관했습니다."
        )


def _promote_local_skills(data: dict, warnings: list[str]) -> None:
    """에이전트 인라인 로컬 스킬 dict를 전역 skills로 승격 (제자리 변형).

    이름 충돌(기존 전역 스킬·에이전트·이미 승격된 스킬)이면 "<agent>--<name>"
    으로 개명하고, 그마저 충돌하면 "-2", "-3"… 접미를 붙여 반드시 유일한
    이름을 만든다(중복을 통과시키면 duplicate_component_name 게이트에 걸릴
    때까지 조용히 숨는다). 개명 시 소유 에이전트 config의 ``skills`` 참조도
    새 이름으로 치환한다 — 그대로 두면 충돌한 전역 스킬로 조용히 재지정된다.

    승격된 dict는 data["skills"]에 합류해 이후 단계(본문 마이그레이션·머신
    순회)와 역직렬화에서 전역 스킬과 같은 경로를 탄다 — id가 보존되므로
    에이전트 FSM 전이의 transfer skill_ref도 그대로 해소된다.

    v1 마이그레이션(_migrate_v1 1-b)과, RF-1b 시점 코드가 남긴 인라인 로컬
    스킬이 든 format 2 파일 로드 양쪽에서 호출된다.
    """
    global_skills = data.get("skills")
    if not isinstance(global_skills, list):
        global_skills = []
        data["skills"] = global_skills
    taken_names = {s.get("name", "") for s in global_skills} | {
        a.get("name", "") for a in data.get("agents", []) or []
    }
    for a in data.get("agents", []) or []:
        for local in a.pop("skills", []) or []:
            agent_name = a.get("name", "?")
            original = local.get("name", "")
            promoted_name = original
            if promoted_name in taken_names:
                promoted_name = f"{agent_name}--{original}"
                suffix = 2
                while promoted_name in taken_names:
                    promoted_name = f"{agent_name}--{original}-{suffix}"
                    suffix += 1
            local["name"] = promoted_name
            taken_names.add(promoted_name)
            renamed = (
                f" (개명: '{promoted_name}')" if promoted_name != original else ""
            )
            if promoted_name != original:
                # 소유 에이전트의 수동 skills 선언이 옛 이름을 가리키면 새
                # 이름으로 따라간다 (다른 에이전트의 동명 참조는 전역 스킬을
                # 가리키던 것이므로 건드리지 않는다).
                cfg = a.get("config")
                if isinstance(cfg, dict) and isinstance(cfg.get("skills"), list):
                    cfg["skills"] = [
                        promoted_name if n == original else n
                        for n in cfg["skills"]
                    ]
            warnings.append(
                f"에이전트 '{agent_name}'의 로컬 스킬 '{original}'을(를) 전역 "
                f"스킬로 승격했습니다{renamed} — 로컬 스킬은 퇴역한 개념입니다."
            )
            global_skills.append(local)


def _v1_all_machines(data: dict):
    """v1 dict의 모든 머신 dict를 순회 (sub_machine/Region 재귀 포함)."""

    def _walk(m: dict):
        yield m
        for st in m.get("states", []) or []:
            sub = st.get("sub_machine")
            if sub:
                yield from _walk(sub)
            for r in st.get("regions", []) or []:
                rsub = r.get("sub_machine")
                if rsub:
                    yield from _walk(rsub)

    def _components():
        # 에이전트 로컬 스킬은 이 함수 호출 전에 이미 전역 skills로 승격돼 있다
        # (WP-RF-1c — _migrate_v1의 1-b 단계가 머신 순회보다 먼저다).
        for s in data.get("skills", []) or []:
            yield s
        for a in data.get("agents", []) or []:
            yield a

    for comp in _components():
        fsm = comp.get("fsm")
        if fsm:
            yield from _walk(fsm)
    graph = data.get("graph")
    if graph:
        yield from _walk(graph)


def _v1_scrub_number(node: Any) -> None:
    """주어진 서브트리에서 ``"field_type": "number"`` → ``"float"`` (제자리 치환)."""
    if isinstance(node, dict):
        if node.get("field_type") == "number":
            node["field_type"] = "float"
        for v in node.values():
            _v1_scrub_number(v)
    elif isinstance(node, list):
        for v in node:
            _v1_scrub_number(v)


# ── section / eventdef ──

def _deser_section(d: dict) -> Section:
    return Section(
        title=d.get("title", ""),
        content=d.get("content", ""),
        children=[_deser_section(c) for c in d.get("children", [])],
    )
