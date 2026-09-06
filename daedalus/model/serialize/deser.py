# daedalus/model/serialize/deser.py
"""역방향 직렬화 — JSON 호환 dict → 모델 (WP-SZ 분해, 이동만).

2-pass 다:
  1. 객체 생성 + id→객체 레지스트리 구축 (``_Registry``)
  2. 참조 해소 (state/skill/agent id → 실제 객체)

dangling id 는 ValueError 가 아니라 None 처리하고 경고를 수집한다.
구버전 파일은 ``migrate._migrate_v1`` 을 태운 뒤 v2 로 읽는다.

이 모듈에는 **오케스트레이터(``deserialize_project``)만** 남아 있고, 개별
``_deser_*`` 는 두 형제 모듈로 나뉘어 있다:

  deser_fsm.py    — 순수 FSM 계층(``_Registry`` 포함 — 그것을 소비하는 최하위
                    계층이라 여기 산다) + 변수/전략/액션/가드/이벤트/블랙보드/
                    상태/전이/머신
  deser_plugin.py — 플러그인 계층(본문/포트/config/정책/스킬/에이전트/참조
                    배치/훅/작업 폴더 문서/도구)

아래에서 그 이름들을 **전부 재수입**하므로 ``serialize/__init__.py`` 파사드와
``from daedalus.model.serialize.deser import _deser_tool`` 같은 기존 경로가
무수정으로 동작한다(항등까지 보존 — 재수입이지 복제가 아니다).
"""
from __future__ import annotations

import copy

from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.project import (
    PluginProject,
    _make_project_graph,
)
from daedalus.model.serialize.migrate import _migrate_v1, _promote_local_skills
from daedalus.model.serialize.ser import FORMAT_VERSION

# ── 분해된 형제 모듈 재수입 (파사드 경로 보존 — noqa: F401 성격의 의도된 재-export) ──
from daedalus.model.serialize.deser_fsm import (
    _EVAL_BUILDERS,
    _EXEC_BUILDERS,
    _Registry,
    _apply_state_common,
    _deser_action,
    _deser_actions,
    _deser_blackboard,
    _deser_dynamic_class,
    _deser_dynamic_field,
    _deser_eval,
    _deser_event,
    _deser_exec,
    _deser_guard,
    _deser_machine,
    _deser_region,
    _deser_state,
    _deser_transition,
    _deser_variable,
    _new_id,
    _to_enum,
)
from daedalus.model.serialize.deser_plugin import (
    _deser_agent,
    _deser_body,
    _deser_config,
    _deser_eventdef,
    _deser_hook,
    _deser_hook_handler,
    _deser_policy,
    _deser_ref_placement,
    _deser_skill,
    _deser_tool,
    _deser_workspace_doc,
    _deser_workspace_docs,
)


# ═══════════════════════ 역직렬화 (deserialize) ═══════════════════════


def deserialize_project(
    data: dict,
    *,
    collect_warnings: list[str] | None = None,
) -> PluginProject:
    """JSON 호환 dict → PluginProject. 2-pass 참조 해소.

    collect_warnings: 호출자가 리스트를 주면 역직렬화 중 발생한 dangling id
      경고 문자열을 해당 리스트에 채워준다. None이면 경고를 버린다(기존 동작).
      반환 타입은 항상 PluginProject — 변경 없음.

    format 1(또는 키 부재 구버전)은 ``_migrate_v1``로 단방향 마이그레이션한
    뒤 읽는다. format 2는 마이그레이션 없이 읽는다. 미지의 상위 format은
    명시 에러(미래 버전 파일을 조용히 오독하지 않는다).
    """
    reg = _Registry()
    fmt = data.get("format")
    if fmt is None or fmt == 1:
        data = _migrate_v1(data, reg.warnings)
    elif fmt == FORMAT_VERSION:
        # RF-1b 시점(로컬 스킬 승격 이전)의 코드가 저장한 format 2 파일에는
        # 에이전트 인라인 로컬 스킬("skills" 키)이 남아 있을 수 있다 — format
        # 게이트만 보고 건너뛰면 스킬 이름·본문이 경고 없이 통째로 드롭된다.
        # v1과 동일한 승격 마이그레이션을 태운다 (WP-RF-1c 리뷰 지적).
        if any(a.get("skills") for a in data.get("agents", []) or []):
            data = copy.deepcopy(data)
            _promote_local_skills(data, reg.warnings)
    else:
        raise ValueError(
            f"지원하지 않는 파일 형식 버전: {fmt!r} "
            f"(지원: {FORMAT_VERSION}, 구버전 1은 로드 시 마이그레이션)"
        )

    # ── pass 1: 컴포넌트(skill/agent) 객체 생성 + 등록 ──
    skills = [_deser_skill(s, reg) for s in data.get("skills", [])]
    agents = [_deser_agent(a, reg) for a in data.get("agents", [])]

    blackboard = _deser_blackboard(data.get("blackboard"), parent=None)

    # 프로젝트 그래프 — 노드/전이를 정식 FSM으로 복원. skill_ref(component id)는
    # 이미 pass1에서 등록된 skills/agents를 가리키며 pass2 pending이 해소한다.
    # 하위 호환: "graph" 키 부재(구버전 파일) → default와 동일한 빈 그래프 생성.
    graph_data = data.get("graph")
    if graph_data is not None:
        graph = _deser_machine(graph_data, reg, parent_bb=blackboard)
    else:
        graph = _make_project_graph()

    project = PluginProject(
        name=data.get("name", ""),
        description=data.get("description", ""),
        version=data.get("version", "0.1.0"),
        skills=skills,
        agents=agents,
        reference_placements=[
            _deser_ref_placement(r) for r in data.get("reference_placements", [])
        ],
        tool_shelf=[_deser_tool(t) for t in data.get("tool_shelf", [])],
        hook_library=[_deser_hook(h) for h in data.get("hook_library", [])],
        blackboard=blackboard,
        graph=graph,
        graph_layout={k: list(v) for k, v in data.get("graph_layout", {}).items()},
        # WP-ER — 구버전 키 부재 → 빈 dict (경고 없음).
        edge_layout={
            k: [list(pt) for pt in v] for k, v in data.get("edge_layout", {}).items()
        },
        # WP-RS Part B — 구버전 파일(키 부재) → 기본 True.
        emit_progress_hook=data.get("emit_progress_hook", True),
        # WP-TG — 구버전 파일(키 부재) → MARKETPLACE(경고 없음, 하위 호환 게이트).
        build_target=_to_enum(
            BuildTarget, data.get("build_target"), BuildTarget.MARKETPLACE
        ),
        # WP-MW — 구버전 파일(키 부재) → 빈 dict (경고 없음).
        mcp_server_defs={
            k: dict(v) for k, v in data.get("mcp_server_defs", {}).items()
        },
        # WP-WS — 구버전 파일(키 부재) → 빈 dict (경고 없음).
        workspace_settings=dict(data.get("workspace_settings") or {}),
        # WP-WD — 구버전 파일(키 부재) → None / 빈 리스트 (경고 없음).
        claude_md=_deser_workspace_doc(data.get("claude_md")),
        rules=_deser_workspace_docs(data.get("rules")),
    )

    # ── pass 2: 모든 참조(state/skill/agent id) 해소 ──
    reg.run_pending()

    # ── 블랙보드 parent 구조 재연결 (최상위) ──
    # 역직렬화도 생성 경로다 — view 생성 경로(_register_component)와 동일한
    # 스코핑을 복원한다: 최상위 스킬/에이전트 FSM → 프로젝트 블랙보드.
    # (v1 파일의 에이전트 로컬 스킬은 _migrate_v1이 전역 스킬로 승격하므로
    # 여기서 전역 스킬과 같은 경로를 탄다.) 중첩 sub_machine은 _deser_machine의
    # parent_bb 전달로 이미 구조 재연결되어 있다.
    for skill in project.skills:
        fsm = getattr(skill, "fsm", None)
        if fsm is not None and fsm.blackboard.parent is None:
            fsm.blackboard.parent = project.blackboard
    for agent in project.agents:
        if agent.fsm.blackboard.parent is None:
            agent.fsm.blackboard.parent = project.blackboard

    # ── 경고 전달 ──
    if collect_warnings is not None:
        collect_warnings.extend(reg.warnings)

    return project
