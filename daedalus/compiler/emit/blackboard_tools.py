# daedalus/compiler/emit/blackboard_tools.py
"""블랙보드 도구 **권한 유도**의 단일 진실 (WP-BM).

"이 컴포넌트의 파일이 어떤 블랙보드 도구를 선언하는가"가 여기 하나다. 같은
사실을 세 표면이 말하기 때문이다: ① `.mcp.json`의 서버 정의 ② 스킬
`allowed-tools`/에이전트 `tools` 프론트매터 ③ 본문·가이드 산문. 한 곳에서
유도하지 않으면 권한은 있는데 이름이 다른, 혹은 반대로 산문만 있고 권한이
없는 산출이 나온다(원칙 1·5).

이름·`.mcp.json` 값은 리프 모듈 `blackboard_names.py`에 있고 여기서
**재-export**한다(임포트 방향은 그쪽 docstring 참조).

reads/writes → 도구의 대응은 좁게 준다(원칙 5 — 필요 없는 권한을 주면 캔버스의
📖/✏ 선언과 산출 권한이 다른 말을 한다):

| 선언 | 도구 |
|---|---|
| reads | `read` · `list` |
| writes | `init` · `write` · `validate` |
| 진행 기록(종류의 `ProgressUse` 선언) | `progress_read` · `progress_set` |
"""
from __future__ import annotations

from daedalus.cli.mcp_server import TOOL_NAMES
from daedalus.compiler.emit.blackboard_names import (  # noqa: F401 — 재-export
    bb_schemas_arg,
    bb_server_entry,
    bb_server_name,
    bb_tool,
    bb_tool_glob,
    bb_tool_prefix,
    plugin_name,
)
from daedalus.compiler.emit.common import _graph_placements
from daedalus.compiler.emit.section_plan import ProgressUse, plan_for_kind
from daedalus.compiler.emit.sections import _component_access_union
from daedalus.model.plugin.placement import fork_skills_using
from daedalus.model.plugin.roles import OutputLocation

#: reads 선언이 있을 때 주는 도구.
READ_TOOLS: tuple[str, ...] = ("list", "read")

#: writes 선언이 있을 때 주는 도구. `validate`가 여기 있는 이유는 쓰기 뒤에
#: 확인하는 것이 쓰는 쪽의 일이기 때문이다 — 읽기만 하는 단계가 남의 상태를
#: 검증하고 고치라고 말할 일은 없다.
WRITE_TOOLS: tuple[str, ...] = ("init", "validate", "write")

#: 진행 기록 도구. `ProgressUse`가 어느 쪽을 주는지 가른다.
PROGRESS_READ_TOOLS: tuple[str, ...] = ("progress_read",)
PROGRESS_WRITE_TOOLS: tuple[str, ...] = ("progress_set",)


def blackboard_in_use(project) -> bool:
    """이 프로젝트가 블랙보드를 쓰는가 — 클래스 정의가 있으면 참.

    `.mcp.json` 배선과 가이드 배출이 같은 질문을 물으므로 판정은 여기 하나다.
    """
    bb = getattr(project, "blackboard", None)
    return bool(getattr(bb, "class_definitions", None))


def _progress_tools(component, project) -> list[str]:
    """진행 기록 도구 — 종류의 `ProgressUse` 선언 × 그래프 배치.

    선언은 절 표(`section_plan.SECTION_PLANS`)에 있다: 진행 산문을 내는 표와
    권한을 유도하는 표가 **같은 표**여야 "명령은 있는데 권한이 없다"가 생기지
    않는다(원칙 1).
    """
    use = plan_for_kind(getattr(type(component), "KIND", None)).progress_use
    if use is ProgressUse.NONE:
        return []
    if not _progress_prose_applies(component, project, use):
        return []
    tools = list(PROGRESS_READ_TOOLS) if use.reads else []
    if use.writes:
        tools.extend(PROGRESS_WRITE_TOOLS)
    return tools


def _progress_prose_applies(component, project, use: ProgressUse) -> bool:
    """그 산문이 실제로 나가는 조건.

    전이 스킬(`WRITE`)만 자기 배치가 아니라 **프로젝트에 배치가 하나라도 있는가**
    를 본다 — 엣지 위의 단계라 자기 placement가 없기 때문이다
    (`section_plan._provide_transfer_progress`와 같은 게이트).
    """
    if project is None:
        return False
    if use is ProgressUse.WRITE:
        from daedalus.compiler.emit.common import _graph_placements_any

        return _graph_placements_any(project)
    return bool(_graph_placements(component, project))


def access_tools(component, project) -> list[str]:
    """이 컴포넌트의 reads/writes 선언 + 진행 기록 쓰임이 요구하는 도구 (정렬 전)."""
    reads, writes = _component_access_union(component, project)
    tools: list[str] = []
    if reads and blackboard_in_use(project):
        tools.extend(READ_TOOLS)
    if writes and blackboard_in_use(project):
        tools.extend(WRITE_TOOLS)
    tools.extend(_progress_tools(component, project))
    return tools


def bb_tools_for(component, project) -> list[str]:
    """이 컴포넌트의 **자기 파일**이 선언할 블랙보드 도구 (호출 가능한 이름, 정렬).

    "그 컴포넌트가 무엇을 읽고 쓰는가"가 아니라 **"그 파일이 무엇을 부여할 수
    있는가"**가 질문이다. 둘이 갈리는 자리가 fork다:

    - **fork 스킬은 빈 목록이다.** `context: fork` 스킬의 본문은 서브에이전트의
      작업 지시로 갈 뿐이고, 도구를 부여하는 것은 그 서브에이전트의 정의 파일
      (fork 에이전트)이다. 빈 약속을 프론트매터에 적으면 "권한을 줬다"고
      읽히지만 아무 일도 일어나지 않는다(원칙 5).
    - **fork 에이전트는 자기를 쓰는 fork 스킬들의 접근을 물려받는다.** 캔버스에
      놓이는 것은 스킬이고 reads/writes 선언도 거기 있으므로, 권한을 실을 수
      있는 유일한 파일이 그 접근을 대신 선언한다.

    산출 파일이 없는 종류(외부 플러그인 에이전트 2종)도 빈 목록이다 — 권한을
    실을 파일 자체가 없다. 블랙보드를 쓰는 fork 스킬이 외부 fork 에이전트를
    기반으로 하면 검증 경고 `bb_tools_unreachable`이 그 자리를 말한다.
    """
    if project is None:
        return []
    if type(component).OUTPUT_LOCATION is OutputLocation.NONE:
        return []
    if _is_fork_skill(component):
        return []
    tools = set(access_tools(component, project))
    for skill in _fork_skills_of(component, project):
        tools.update(access_tools(skill, project))
    if not tools:
        return []
    order = {name: index for index, name in enumerate(TOOL_NAMES)}
    return [bb_tool(project, name) for name in sorted(tools, key=order.__getitem__)]


def _is_fork_skill(component) -> bool:
    """fork 스킬인가 — 판정은 "결과가 보고인가"라는 절 표의 선언 하나다."""
    from daedalus.compiler.emit.section_plan import OutcomeStyle

    kind = getattr(type(component), "KIND", None)
    if kind is None:
        return False
    try:
        plan = plan_for_kind(kind)
    except ValueError:
        return False
    return plan.outcome_style is not OutcomeStyle.NEXT_STEPS


def _fork_skills_of(component, project) -> list:
    """이 컴포넌트를 fork 실행 기반으로 쓰는 fork 스킬 객체 목록.

    술어는 종류의 선언 `IS_FORK_BASE`다(Q27) — "타입이 ForkAgent인가"가 아니라
    "fork 실행 기반이 될 수 있는 종류인가"가 묻는 것이고, 그 선언을 갖는 종류가
    늘어도 여기는 바뀌지 않는다(`tests/test_polymorphism_ratchet.py`).
    """
    if not type(component).IS_FORK_BASE:
        return []
    names = set(fork_skills_using(component, project))
    return [s for s in getattr(project, "skills", None) or [] if s.name in names]


def bb_server_needed(project) -> bool:
    """이 프로젝트의 산출에 블랙보드 서버가 필요한가.

    질문은 "블랙보드 클래스가 있는가"가 아니라 **"권한을 받은 파일이 하나라도
    나가는가"**다. 진행 기록만 쓰는 워크플로(블랙보드 클래스 0개)도 서버가
    필요하고, 반대로 클래스만 정의하고 아무도 읽고 쓰지 않으면 서버를 띄울
    이유가 없다. `.mcp.json` 배선과 프론트매터 권한이 같은 판정을 쓰므로
    "도구는 선언됐는데 서버가 없다"가 성립하지 않는다(원칙 1·5).
    """
    from daedalus.compiler.emit.common import emitted_components

    if project is None:
        return False
    return any(bb_tools_for(c, project) for c in emitted_components(project))
