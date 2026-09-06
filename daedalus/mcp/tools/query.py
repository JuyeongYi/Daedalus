# daedalus/mcp/tools/query.py
"""조회 도구 + undo 스택 — get_project/get_selection/get_component/
validate_project/compile_preview/get_history/undo/redo (WP-RF-3b).

**계층: GUI 어댑터다 (WP-RF-2 명시).** core(model/compiler)가 아니라
MainWindow·ProjectViewModel·CommandStack·body_documents 등 view 표면에 결합된
코드로, core 경계 계약(tests/test_import_contracts.py)의 대상이 아니다.
모든 메서드는 **Qt 메인 스레드에서 실행되는 것을 전제**로 한다(service가
MainThreadInvoker로 마샬링한다). 편집 도구는 반드시
``ProjectViewModel.execute``(CommandStack)를 거친다 — 사용자가 Ctrl+Z로
되돌릴 수 있어야 한다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ._base import _MAX_BODY_PREVIEW, _BaseTools


class QueryTools(_BaseTools):
    """읽기 도구 — 캔버스 요약 헬퍼 + 프로젝트/선택/컴포넌트 조회."""

    def _placement_summary(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for svm in self._vm.state_vms:
            model = svm.model
            ref = getattr(model, "skill_ref", None)
            out.append(
                {
                    "node": model.name,
                    "component": getattr(ref, "name", None),
                    "kind": self._component_kind(ref) if ref is not None else "empty",
                    "x": round(svm.x, 1),
                    "y": round(svm.y, 1),
                    "reads": list(getattr(model, "reads", []) or []),
                    "writes": list(getattr(model, "writes", []) or []),
                }
            )
        return out

    def _transition_summary(self) -> list[dict[str, Any]]:
        # guard 서술은 컴파일러의 `_describe_guard`를 그대로 쓴다 (Q2) —
        # 화면·산출·조회가 같은 문구를 말해야 한다(가드를 쓸 수는 있는데
        # 읽을 수는 없던 갭). 쓰기는 set_transition(guard="...")이고 그 자연어가
        # LLM 판정 문구로 들어간다.
        from daedalus.compiler.emit.sections import _describe_guard

        out: list[dict[str, Any]] = []
        for tvm in self._vm.transition_vms:
            trans = tvm.model
            trigger = getattr(trans, "trigger", None)
            guard = _describe_guard(getattr(trans, "guard", None))
            out.append(
                {
                    "source": tvm.source_vm.model.name,
                    "target": tvm.target_vm.model.name,
                    "trigger": getattr(trigger, "name", None),
                    "guard": guard or None,
                    "transfer_skill": getattr(getattr(trans, "skill_ref", None), "name", None),
                    # 엣지 경유점(WP-ER) 개수 — 좌표까지는 싣지 않는다(캔버스 표현).
                    "waypoint_count": len(getattr(tvm, "waypoints", []) or []),
                }
            )
        return out

    def _reference_summary(self) -> list[dict[str, Any]]:
        """캔버스에 배치된 참조 노드 — 같은 스킬이 여러 번 놓일 수 있어 index를 함께 준다."""
        out: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        for rvm in self._vm.reference_vms:
            name = str(getattr(rvm.model, "name", "?"))
            index = counts.get(name, 0)
            counts[name] = index + 1
            out.append(
                {
                    "component": name,
                    "index": index,
                    "x": round(rvm.x, 1),
                    "y": round(rvm.y, 1),
                    "linked_nodes": [
                        link.state_vm.model.name
                        for link in self._vm.reference_links
                        if link.reference_vm is rvm
                    ],
                }
            )
        return out

    # ------------------------------------------------------------------
    # 읽기 도구
    # ------------------------------------------------------------------

    #: get_project 구획 이름 → 그 구획이 담는 키 (Q4). 순서가 기본(sections 생략)
    #: 응답의 병합 순서이기도 하다 — 기존 dict와 키 집합이 완전히 같아야 하위 호환이다.
    _PROJECT_SECTION_NAMES = ("meta", "components", "canvas", "blackboard", "hooks")

    def _workspace_doc_signal(self) -> dict[str, Any]:
        """작업 폴더 문서(WP-WD)의 개수 신호 (Q6) — `claude_md` 유무 + `rules` 개수.

        `claude_md`는 **내용이 있는가**로 본다 — 빈 문서는 컴파일이 구역을
        제거하므로(멱등) 있으나 마나다.
        """
        project = self._project
        claude_md = getattr(project, "claude_md", None)
        return {
            "claude_md": bool(claude_md is not None and (claude_md.body or "").strip()),
            "rules": len(getattr(project, "rules", None) or []),
        }

    def _project_sections(self) -> dict[str, dict[str, Any]]:
        project = self._project
        blackboard = getattr(project, "blackboard", None)
        classes = list(getattr(blackboard, "class_definitions", []) or [])
        return {
            "meta": {
                "name": project.name,
                "description": project.description,
                "version": project.version,
                "build_target": getattr(getattr(project, "build_target", None), "value", None),
                "saved_path": getattr(self._window, "_current_path", None),
                "emit_progress_hook": getattr(project, "emit_progress_hook", None),
                "mcp_server_defs": dict(getattr(project, "mcp_server_defs", None) or {}),
                # WP-WR — 사용 선언된 외부 플러그인("이름[@마켓]"). 후보·상세는
                # list_wrappable_skills, 편집은 set_external_plugins.
                "external_plugins": list(
                    getattr(project, "external_plugins", None) or []
                ),
                # 작업 폴더 문서(WP-WD)의 **존재 신호**만 (Q6) — 내용은
                # list_workspace_docs/get_workspace_doc이 준다. 신호가 없으면
                # 그 표면이 있다는 것 자체를 몰라 CLAUDE.md 구역과 규칙이
                # 조용히 잊힌다(개요 ↔ 전문 분리와 같은 논리).
                "workspace_docs": self._workspace_doc_signal(),
                "can_undo": self._window._active_stack.can_undo,
                "can_redo": self._window._active_stack.can_redo,
            },
            "components": {
                "skills": [
                    {
                        "name": s.name,
                        "kind": self._component_kind(s),
                        "description": s.description,
                    }
                    for s in project.skills
                ],
                "agents": [
                    {"name": a.name, "description": a.description} for a in project.agents
                ],
            },
            "canvas": {
                "placements": self._placement_summary(),
                "transitions": self._transition_summary(),
                "references": self._reference_summary(),
            },
            "blackboard": {
                "blackboard_classes": [
                    {
                        "name": c.name,
                        "description": getattr(c, "description", ""),
                        "fields": [f.name for f in getattr(c, "fields", [])],
                    }
                    for c in classes
                ],
            },
            "hooks": {
                "hook_library": [
                    self._hook_summary(h) for h in getattr(project, "hook_library", []) or []
                ],
                # 가려지지 않은 전역 훅(A1, G7) — 개요만(스크립트 본문은 get_hook).
                "global_hooks": [self._hook_summary(h) for h in self._visible_global_hooks()],
            },
        }

    def get_project(self, sections: list[str] | None = None) -> dict[str, Any]:
        """지금 열려 있는 프로젝트의 전체 개요 — 컴포넌트 목록, 캔버스 배치, 블랙보드.

        `hook_library`는 **개요만** 준다(이름·이벤트·matcher·핸들러 개수) —
        핸들러 스키마와 스크립트 본문까지 보려면 `get_hook(name)`을 쓰라.
        `global_hooks`도 같은 개요 — 프로젝트 훅에 가려지지 않은 전역 훅만
        나온다(A1, G7). 프로젝트로 가져와 고치려면 `copy_global_hook`.

        `meta`의 `workspace_docs`(Q6)는 작업 폴더 문서(WP-WD)의 **존재 신호**만
        준다(`{claude_md: bool, rules: N}`) — 내용은 `list_workspace_docs`/
        `get_workspace_doc`이다.

        sections(Q4): 구획만 골라 받는다 — `meta`/`components`/`canvas`/
        `blackboard`/`hooks` 중 목록. **생략하면 전체**(축약 기본값 전환은 아직
        결정 전이다).
        """
        groups = self._project_sections()
        names = sections if sections is not None else list(self._PROJECT_SECTION_NAMES)
        unknown = [s for s in names if s not in groups]
        if unknown:
            raise ValueError(
                f"알 수 없는 구획: {', '.join(unknown)}. "
                f"사용 가능: {', '.join(self._PROJECT_SECTION_NAMES)}"
            )
        result: dict[str, Any] = {}
        for name in names:
            result.update(groups[name])
        return result

    def get_selection(self) -> dict[str, Any]:
        """사용자가 지금 캔버스에서 선택한 것 — "이거 고쳐줘"의 '이거'를 알아내는 통로."""
        from daedalus.view.canvas.edge_item import TransitionEdgeItem
        from daedalus.view.canvas.node_item import StateNodeItem
        from daedalus.view.canvas.ref_node_item import ReferenceNodeItem

        scene = getattr(self._window, "_fsm_scene", None)
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        refs: list[str] = []
        if scene is not None:
            for item in scene.selectedItems():
                if isinstance(item, StateNodeItem):
                    model = item.state_vm.model
                    ref = getattr(model, "skill_ref", None)
                    nodes.append(
                        {
                            "node": model.name,
                            "component": getattr(ref, "name", None),
                            "kind": self._component_kind(ref) if ref is not None else "empty",
                        }
                    )
                elif isinstance(item, TransitionEdgeItem):
                    tvm = item.transition_vm
                    edges.append(
                        {
                            "source": tvm.source_vm.model.name,
                            "target": tvm.target_vm.model.name,
                        }
                    )
                elif isinstance(item, ReferenceNodeItem):
                    refs.append(str(getattr(item._ref_vm.model, "name", "?")))

        tabs = getattr(self._window, "_tabs", None)
        active_tab = None
        if tabs is not None:
            active_tab = tabs.tabText(tabs.currentIndex())

        return {
            "active_tab": active_tab,
            "selected_nodes": nodes,
            "selected_transitions": edges,
            "selected_references": refs,
            "empty": not (nodes or edges or refs),
        }

    def focus_node(self, name: str) -> dict[str, Any]:
        """캔버스에서 그 노드를 선택하고 화면 가운데로 가져온다 (G16).

        `get_selection`의 **쓰기 짝**이다 — CC가 "이 노드 얘기입니다"를 사용자
        화면에서 가리키는 통로다(검증 결과 항목을 더블클릭했을 때와 같은
        `ValidationActions.focus_in_project_canvas`를 부른다: 프로젝트 FSM 탭으로
        전환 + 단독 선택 + 센터링).

        **선택은 편집이 아니므로 undo 대상이 아니다** — 커맨드 스택에 쌓이면
        Ctrl+Z가 "무엇을 보고 있었는가"를 되감는 빈 단계로 채워진다.
        """
        svm = self._find_state_vm(name)
        self._window._validation_actions.focus_in_project_canvas(svm.model)
        return {"focused": name, "component": getattr(
            getattr(svm.model, "skill_ref", None), "name", None
        )}

    def select_nodes(self, names: list[str]) -> dict[str, Any]:
        """캔버스 노드 여러 개를 한꺼번에 선택한다 (G16) — 빈 목록이면 선택 해제.

        `focus_node`와 달리 화면을 이동시키지 않는다(어디로 가야 할지 정할 수
        없다). 없는 이름은 후보를 나열하며 거부한다 — 일부만 선택해 놓고 성공을
        보고하면 사용자는 나머지도 선택된 줄 안다. 선택은 편집이 아니므로 undo
        대상이 아니다.
        """
        vms = [self._find_state_vm(n) for n in names]
        count = self._scene.select_state_vms(vms)
        return {"selected": [v.model.name for v in vms], "count": count}

    def get_component(self, name: str) -> dict[str, Any]:
        """스킬/에이전트 하나의 상세 — 본문, 설정, 자체 FSM 요약.

        `config`에는 **비기본값 필드만** 실린다 — 미지정(None)·선언 기본값과
        같은 값은 생략된다(빈 dict = 전부 기본값). 전체 필드 목록·현재값·
        선택지는 `list_component_fields`로 조회하라.
        """
        comp = self._find_component(name)
        config = getattr(comp, "config", None)
        body = str(getattr(comp, "body", "") or "")
        truncated = len(body) > _MAX_BODY_PREVIEW
        fsm = getattr(comp, "fsm", None)

        info: dict[str, Any] = {
            "name": comp.name,
            "kind": self._component_kind(comp),
            "description": getattr(comp, "description", ""),
            "when_to_use": getattr(comp, "when_to_use", ""),
            "body": body[:_MAX_BODY_PREVIEW],
            "body_truncated": truncated,
            "body_length": len(body),
            "transfer_on": [
                {"name": e.name, "description": getattr(e, "description", "")}
                for e in (getattr(comp, "transfer_on", []) or [])
            ],
            # 에이전트 호출 포트 — 에이전트로 가는 전이는 이 포트에서만 나갈 수 있다
            "call_agents": [
                {"name": e.name, "description": getattr(e, "description", "")}
                for e in (getattr(comp, "call_agents", []) or [])
            ],
        }
        if config is not None:
            # 비기본값만 싣는다(Q3) — 선언 기본값과 같은 필드(대개 None 미지정)는
            # list_component_fields가 이미 전체 상세(선택지·emit 위치 포함)를
            # 주므로 여기서 vars() 전체를 다시 덤프하는 것은 중복 소음이다.
            defaults = type(config)()

            def _cfg_val(v: Any) -> Any:
                return getattr(v, "value", v)

            info["config"] = {
                key: _cfg_val(value)
                for key, value in vars(config).items()
                if not key.startswith("_")
                and key != "id"
                and _cfg_val(value) != _cfg_val(getattr(defaults, key, None))
            }
        if fsm is not None:
            info["fsm"] = {
                "states": [s.name for s in fsm.states],
                "transitions": [
                    {"source": t.source.name, "target": t.target.name}
                    for t in fsm.transitions
                ],
            }
        return info

    def validate_project(
        self, severity: str = "", component: str = ""
    ) -> dict[str, Any]:
        """F7 검증과 같은 결과 — 컴파일을 막는 에러와 경고를 구분해 돌려준다.

        severity(Q5): "error" 또는 "warning"만 남긴다. 생략하면 전부.
        component(Q5): 그 스킬/에이전트에 관한 것만 남긴다 — 캔버스 노드 우클릭
        "관련 경고 보기"와 **같은 판정**(`view/actions/warnings.findings_for`)이라
        subject·path 루트·**그래프 placement 노드** 세 경로를 모두 본다(placement를
        빼면 `mid_chain_user_invocable`처럼 subject가 노드인 규칙을 통째로 놓친다).

        **개수는 필터 전후를 둘 다 낸다** — `error_count`/`warning_count`는
        걸러진 목록 기준이고 `total_*`가 프로젝트 전체다. 필터를 걸어 0을 보고
        "컴파일이 통과한다"로 읽으면 안 된다.
        """
        from daedalus.model.validation import Validator

        # 전역 훅(A1)을 포함한 이름 집합을 주입 — 검증기는 파일시스템 무접근.
        errors = Validator().validate_project(
            self._project,
            known_hook_names=frozenset(self._window.resolved_hooks()),
        )
        total_errors = sum(1 for e in errors if not e.is_warning)
        total_warnings = sum(1 for e in errors if e.is_warning)

        if component:
            from daedalus.view.actions.warnings import findings_for

            comp = self._find_component(component)
            errors = findings_for(errors, comp, self._project)
        if severity:
            if severity not in ("error", "warning"):
                raise ValueError(
                    f"알 수 없는 severity '{severity}'. 사용 가능: error, warning"
                )
            want_warning = severity == "warning"
            errors = [e for e in errors if e.is_warning is want_warning]

        return {
            "error_count": sum(1 for e in errors if not e.is_warning),
            "warning_count": sum(1 for e in errors if e.is_warning),
            "total_error_count": total_errors,
            "total_warning_count": total_warnings,
            "filtered": bool(severity or component),
            "issues": [
                {
                    "rule": e.rule,
                    "severity": "warning" if e.is_warning else "error",
                    "message": e.message,
                    "path": list(getattr(e, "path", ()) or ()),
                }
                for e in errors
            ],
        }

    def list_tool_candidates(self) -> dict[str, Any]:
        """allowed-tools 계열 자동완성 후보 전체(G9) — CC 빌트인 + 카탈로그 + `Agent(이름)`.

        ALLOWED_TOOLS/TOOLS/DISALLOWED_TOOLS TagInput이 보여주는 목록과 **같은
        산출**이다(`catalogue_loader.candidate_strings` 재사용) — 카탈로그에
        무엇이 있는지 몰라 이름을 짐작으로 적는 것을 막는다. 읽기 전용, 카탈로그
        로드는 GUI와 같은 경로(저장 경로 기준 프로젝트 폴더 + 전역 `~/.daedalus/
        catalogue/`)를 쓴다.
        """
        from daedalus.view.editors.catalogue_loader import candidate_strings, load_catalogue

        current_path = getattr(self._window, "_current_path", None)
        project_dir = Path(current_path).parent if current_path else None
        entries = load_catalogue(project_dir=project_dir)
        return {"candidates": candidate_strings(entries, self._project)}

    def compile_preview(self, name: str) -> dict[str, Any]:
        """컴포넌트가 어떤 SKILL.md / 에이전트 .md로 컴파일되는지 — 파일은 쓰지 않는다.

        토큰 추정(A5-lite)을 함께 준다: `tokens`/`chars`와, 파일당 임계를 넘으면
        `token_notice` 한 줄. 검증 경고가 아니라 **정보성 계기판**이다 —
        컴파일을 막지 않고 산출 텍스트도 바꾸지 않는다.
        """
        from daedalus.compiler.emit import compile_agent, compile_skill
        from daedalus.compiler.token_report import TokenReport
        from daedalus.model.plugin.agent import AgentDefinition

        comp = self._find_component(name)
        project = self._project
        is_agent = isinstance(comp, AgentDefinition)
        if is_agent:
            # 전역 훅(A1)까지 해소해 넘긴다 — LOCAL 빌드의 에이전트
            # 프론트매터 hooks가 실제 컴파일과 같은 내용이어야 미리보기다.
            text = compile_agent(
                comp, project=project, resolved_hooks=self._window.resolved_hooks(),
            )
        else:
            text = compile_skill(comp, project=project)
        report = TokenReport()
        entry = report.add(comp.name, "agent" if is_agent else "skill", text)
        return {
            "name": comp.name,
            "kind": self._component_kind(comp),
            "text": text,
            "chars": entry.chars,
            "tokens": entry.tokens,
            "token_threshold": report.threshold,
            "token_notice": report.notice(),
        }

    def compile_check(
        self, out_dir: str | None = None,
        settings_filename: str = "settings.json",
    ) -> dict[str, Any]:
        """컴파일을 **파일을 쓰지 않고** 예행한다 — 게이트 판정 + 경고 전부 + 토큰 요약.

        `validate_project`가 못 보여주는 컴파일러 경고를 여기서 본다:
        `dangling_file_ref`, `unknown_skill_files_dir`, `dangling_skill_file_ref`,
        `missing_mcp_server_def`, `unmergeable_settings_json`,
        `unmergeable_claude_md`, `rule_body_frontmatter`. 이 경고들은 실제
        컴파일(GUI Ctrl+B)에서만 나오던 것이라, MCP로만 저작하면 영영 보이지
        않았다.

        out_dir: 컴파일 대상 폴더(LOCAL 빌드면 설치 대상 작업 폴더). **생략
        가능** — 생략하면 계획 경로가 상대 경로가 되고, 대상 폴더를 읽어야
        판정하는 경고 2종(`unmergeable_settings_json`/`unmergeable_claude_md`)만
        건너뛴다. 나머지 판정은 그대로다.

        settings_filename(WP-WS): LOCAL 빌드의 설정 산출 파일 —
        "settings.json"(기본, 공유) 또는 "settings.local.json"(개인). 병합
        판정(unmergeable_settings_json)이 이 파일을 읽는다.

        디스크는 절대 바뀌지 않는다(쓰기·복사·JSON 병합 전부 생략) — 따라서
        undo 대상도 아니다. 동봉 파일 루트·전역 훅·서버 정의 주입은 Ctrl+B
        컴파일과 **같은 경로**를 쓰므로 결과가 실제 컴파일과 일치한다.
        """
        from daedalus.compiler import compile_project

        project = self._project
        result = compile_project(
            project, out_dir, dry_run=True, settings_filename=settings_filename, **self._window.compile_inputs(),
        )

        base = Path(out_dir) if out_dir else None

        def rel(path: Any) -> str:
            p = Path(path)
            if base is not None:
                try:
                    return p.relative_to(base).as_posix()
                except ValueError:
                    return p.as_posix()
            return p.as_posix()

        report = result.token_report
        return {
            "ok": result.ok,
            "out_dir": out_dir,
            "build_target": getattr(
                getattr(project, "build_target", None), "value", None
            ),
            "error_count": len(result.errors),
            "warning_count": len(result.warnings),
            "issues": [
                {
                    "rule": e.rule,
                    "severity": "warning" if e.is_warning else "error",
                    "message": e.message,
                    "source": getattr(e, "source", None),
                    "path": list(getattr(e, "path", ()) or ()),
                }
                for e in (*result.errors, *result.warnings)
            ],
            # 게이트에 막히면 written이 비고 skipped에 막힌 산출이 들어간다.
            "planned_files": [rel(p) for p in result.written],
            "planned_copies": [rel(p) for p in result.copied_files],
            "skipped": [{"reason": r, "label": label} for r, label in result.skipped],
            "tokens": {
                "total_tokens": report.total_tokens,
                "total_chars": report.total_chars,
                "threshold": report.threshold,
                "over_threshold": [
                    {"path": e.path, "kind": e.kind, "tokens": e.tokens, "chars": e.chars}
                    for e in report.over_threshold()
                ],
                "notice": report.notice(),
            },
        }

    # ------------------------------------------------------------------
    # undo 스택 (활성 탭 기준 — 사람이 Ctrl+Z/Ctrl+Y를 누른 것과 같다)
    # ------------------------------------------------------------------

    def undo(self) -> dict[str, Any]:
        """활성 탭의 undo — 사람이 Ctrl+Z를 누른 것과 같다."""
        stack = self._window._active_stack
        if not stack.can_undo:
            return {"undone": None, "can_undo": False}
        label = stack.history[-1].description
        self._window._undo()
        return {"undone": label, "can_undo": stack.can_undo}

    def redo(self) -> dict[str, Any]:
        stack = self._window._active_stack
        if not stack.can_redo:
            return {"redone": None, "can_redo": False}
        label = stack.redo_history[0].description
        self._window._redo()
        return {"redone": label, "can_redo": stack.can_redo}

    def get_history(self, limit: int = 20) -> dict[str, Any]:
        """최근 편집 이력 — 사람이 방금 무엇을 했는지 CC가 따라잡는 통로."""
        stack = self._window._active_stack
        history = stack.history[-limit:]
        return {
            "entries": [
                {"description": c.description, "script": c.script_repr} for c in history
            ],
            "can_undo": stack.can_undo,
            "can_redo": stack.can_redo,
        }
