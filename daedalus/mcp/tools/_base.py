# daedalus/mcp/tools/_base.py
"""공통 헬퍼 — 프로젝트/뷰모델 접근, 컴포넌트·노드 조회, 편집 범위 (WP-RF-3b).

**계층: GUI 어댑터다 (WP-RF-2 명시).** core(model/compiler)가 아니라
MainWindow·ProjectViewModel·CommandStack·body_documents 등 view 표면에 결합된
코드로, core 경계 계약(tests/test_import_contracts.py)의 대상이 아니다.
모든 메서드는 **Qt 메인 스레드에서 실행되는 것을 전제**로 한다(service가
MainThreadInvoker로 마샬링한다). 편집 도구는 반드시
``ProjectViewModel.execute``(CommandStack)를 거친다 — 사용자가 Ctrl+Z로
되돌릴 수 있어야 한다.

`_BaseTools`는 모든 도메인 믹스인의 공통 베이스다 — MainWindow 참조 하나를
들고, 이름 → 컴포넌트/노드 해소와 편집 범위(`_scope`)를 제공한다.
"""
from __future__ import annotations

from typing import Any

_MAX_BODY_PREVIEW = 4000


class _BaseTools:
    """MainWindow 하나에 붙는 도구 믹스인들의 공통 베이스."""

    def __init__(self, window: Any) -> None:
        self._window = window

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    @property
    def _project(self) -> Any:
        project = getattr(self._window, "_project", None)
        if project is None:
            raise RuntimeError("열려 있는 프로젝트가 없습니다.")
        return project

    @property
    def _vm(self) -> Any:
        return self._window._project_vm

    def _components(self) -> list[Any]:
        project = self._project
        return [*project.skills, *project.agents]

    def _find_component(self, name: str) -> Any:
        """이름으로 컴포넌트(전역 스킬/에이전트)를 찾는다."""
        pool = list(self._components())
        for comp in pool:
            if getattr(comp, "name", None) == name:
                return comp
        known = ", ".join(sorted(str(getattr(c, "name", "?")) for c in pool))
        raise ValueError(f"'{name}' 컴포넌트를 찾을 수 없습니다. 사용 가능: {known or '(없음)'}")

    def _find_state_vm(self, name: str, vm: Any = None) -> Any:
        target = vm if vm is not None else self._vm
        found = target.get_state_vm(name)
        if found is None:
            known = ", ".join(sorted(s.model.name for s in target.state_vms))
            raise ValueError(f"캔버스에 '{name}' 노드가 없습니다. 현재 노드: {known or '(없음)'}")
        return found

    # --- 편집 범위 ---

    def _scope(self) -> tuple[Any, Any]:
        """편집 대상 (뷰모델, 백킹 StateMachine) — 항상 프로젝트 캔버스.

        WP-AF — 에이전트 내부 FSM은 퇴역했다(절차는 본문 산문, 결과 분기는
        transfer_on). 캔버스 편집의 대상은 프로젝트 그래프 하나뿐이다.
        """
        return self._vm, self._project.graph

    @staticmethod
    def _hook_summary(hook: Any) -> dict[str, Any]:
        """훅 1건의 **개요** — 목록에 실리는 축약본 (Q1).

        전문(핸들러 CC 스키마 + 스크립트 본문)은 `get_hook`이 준다.
        `get_project`가 훅마다 셸 스크립트 전문을 싣던 것을 여기서 끊는다 —
        `get_body_outline` ↔ `get_body_section` 분리와 같은 논리다.

        소유가 `_BaseTools`인 이유: `QueryTools.get_project`와 `HookTools`가
        함께 쓰므로, 어느 한쪽 믹스인에 두면 합성 순서에 의존하는 호출이 된다.
        """
        return {
            "name": hook.name,
            "event": getattr(hook.event, "value", str(hook.event)),
            "matcher": hook.matcher,
            "description": getattr(hook, "description", ""),
            "handler_count": len(getattr(hook, "handlers", []) or []),
        }

    def _visible_global_hooks(self) -> list[Any]:
        """이 프로젝트에서 이름이 가려지지 않은 전역 훅 (A1, G7).

        `HookLibraryPanel._global_hooks`와 같은 판정 — 동명 프로젝트 훅이 있으면
        그쪽이 이긴다(병합 규칙, `hook_store.resolve_hooks`와 동일 우선순위)이므로
        가려진 전역은 뺀다. 둘 다 보이면 어느 쪽이 실제로 쓰이는지 알 수 없다.

        소유가 `_BaseTools`인 이유: `QueryTools.get_project`와 `HookTools`가
        함께 쓴다(`_hook_summary`와 같은 사정).
        """
        from daedalus.model.plugin.hook_store import load_global_hooks

        shadowed = {h.name for h in getattr(self._project, "hook_library", None) or []}
        return [h for h in load_global_hooks() if h.name not in shadowed]

    @staticmethod
    def _component_kind(comp: Any) -> str:
        return str(getattr(comp, "kind", type(comp).__name__))

    def _reject_duplicate_name(self, name: str) -> None:
        if any(getattr(c, "name", None) == name for c in self._components()):
            raise ValueError(f"'{name}' 이름의 컴포넌트가 이미 있습니다.")
