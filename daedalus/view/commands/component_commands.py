"""컴포넌트 생성/이름변경 커맨드 (WP-CE 1차).

여기까지 커맨드화된 편집은 캔버스 구조뿐이었다 — 스킬·에이전트를 만들고 이름을
바꾸는 것은 모델에 직접 쓰고 있어서 Ctrl+Z가 듣지 않았고, MCP 표면에도 올릴 수
없었다(AI 편집만 되돌릴 수 없는 비대칭이 생긴다).

**삭제는 아직 커맨드가 아니다.** ``remove_component``는 그래프 placement·skill_ref
None화·위임 참조·graph_layout·edge_layout까지 훑어 정리하므로, 되돌리려면 그
정리 내역 전부를 기록·복원해야 한다. 부분적으로만 복원하는 커맨드는 없느니만
못하므로 WP-CE 본편으로 미룬다.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from daedalus.view.commands.base import Command

if TYPE_CHECKING:
    from daedalus.model.project import PluginProject


def _bucket(project: PluginProject, component: object) -> list:
    """컴포넌트가 들어갈 프로젝트 리스트를 고른다."""
    from daedalus.model.plugin.agent import AgentDefinition
    from daedalus.model.plugin.delegation import DelegationDef

    if isinstance(component, AgentDefinition):
        return project.agents
    if isinstance(component, DelegationDef):
        return project.delegations
    return project.skills


class CreateComponentCmd(Command):
    """스킬/에이전트를 프로젝트에 등록한다."""

    def __init__(self, project: PluginProject, component: object) -> None:
        self._project = project
        self._component = component

    @property
    def description(self) -> str:
        kind = getattr(self._component, "kind", type(self._component).__name__)
        return f"{kind} '{getattr(self._component, 'name', '?')}' 생성"

    @property
    def script_repr(self) -> str:
        kind = getattr(self._component, "kind", "component")
        return f'create_component("{getattr(self._component, "name", "?")}", kind="{kind}")'

    def execute(self) -> None:
        bucket = _bucket(self._project, self._component)
        if not any(c is self._component for c in bucket):
            bucket.append(self._component)
        # 블랙보드 스코핑 배선 — 생성 경로의 책임(app._register_component와 동일).
        fsm = getattr(self._component, "fsm", None)
        if fsm is not None and fsm.blackboard.parent is None:
            fsm.blackboard.parent = self._project.blackboard

    def undo(self) -> None:
        bucket = _bucket(self._project, self._component)
        for i, existing in enumerate(bucket):
            if existing is self._component:
                del bucket[i]
                break


class RenameComponentCmd(Command):
    """컴포넌트 이름 변경 — 문자열 참조 3종까지 함께 되돌린다.

    ``rename_component``가 참조 갱신을 전담하므로, undo도 같은 함수를 옛 이름으로
    한 번 더 부르면 참조가 대칭으로 되돌아온다.
    """

    def __init__(
        self, project: PluginProject, component: object, old_name: str, new_name: str
    ) -> None:
        self._project = project
        self._component = component
        self._old_name = old_name
        self._new_name = new_name

    @property
    def description(self) -> str:
        return f"컴포넌트 이름 변경: '{self._old_name}' → '{self._new_name}'"

    @property
    def script_repr(self) -> str:
        return f'rename_component("{self._old_name}", "{self._new_name}")'

    def execute(self) -> None:
        from daedalus.model.project import rename_component

        rename_component(self._project, self._component, self._new_name)

    def undo(self) -> None:
        from daedalus.model.project import rename_component

        rename_component(self._project, self._component, self._old_name)
