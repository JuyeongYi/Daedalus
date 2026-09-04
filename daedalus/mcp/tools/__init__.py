# daedalus/mcp/tools/
"""MCP 도구 구현 (WP-MCP) — CC가 Daedalus를 함께 보고 함께 편집하는 표면.

**계층: 이 모듈은 GUI 어댑터다 (WP-RF-2 명시).** core(model/compiler)가 아니라
MainWindow·ProjectViewModel·CommandStack·body_documents 등 view 표면에 깊이
결합된 코드로, core 경계 계약(tests/test_import_contracts.py)의 **대상이 아니다**.
WP-RF-3b 분해의 근거가 된 성격이다 — 순수 조회/편집 로직과 Qt(뷰) 마샬링을
나눌 때, 여기 있는 것은 전부 어댑터 쪽이다.

모든 메서드는 **Qt 메인 스레드에서 실행되는 것을 전제**로 한다(service가
MainThreadInvoker로 마샬링한다). 여기서 스레드 안전성을 다시 걱정할 필요는 없다.

편집 도구는 반드시 ``ProjectViewModel.execute``(CommandStack)를 거친다 — 그래야
사용자가 Ctrl+Z로 되돌릴 수 있고, 스크립트 리스너에 사람 편집과 같은 형식으로
남는다. 본문 편집만은 예외적으로 컴포넌트의 QTextDocument에 적용하는데, 이는
본문이 캔버스와 분리된 자체 undo 스택을 갖기 때문이다(WP-BU) — 우회가 아니라
그 스택에 정확히 올리는 경로다.

컴포넌트 삭제(`delete_component`)도 A2에서 합류했다 — `RemoveComponentCmd`가
캔버스 정리를 기존 커맨드로 조립하고 모델 잔여분만 스냅샷하므로 1 undo 단위로
되돌아온다. 남은 미노출 편집은 없으며, 새 편집은 커맨드를 만든 뒤
`service.TOOL_NAMES`에 이름을 더하면 노출된다.
"""

# WP-RF-3b: 구 단일 모듈 ``mcp/tools.py``를 패키지로 분해했다 (이동만, 동작
# 불변). 이 ``__init__``은 **재-export 파사드**다 — ``from daedalus.mcp.tools
# import DaedalusTools`` 등 기존 임포트가 전부 무수정으로 동작한다.
# ``DaedalusTools``는 도메인별 믹스인의 합성 클래스이고, 메서드 이름·시그니처·
# docstring은 분해 전과 동일하다(SDK가 docstring·시그니처로 입력 스키마를
# 만든다 — service._wrap의 functools.wraps 경로). TOOL_NAMES는 service.py에
# 있다.
#
# 구획:
#   _base.py      — 공통 헬퍼 (_project/_vm/_find_component/_find_state_vm/_scope)
#   query.py      — 조회 (get_project/get_selection/get_component/validate_project/
#                   compile_preview) + undo 스택 (undo/redo/get_history)
#   session.py    — 세션 (save_project/open_project/export_package/list_recent_projects)
#   canvas.py     — 캔버스 구조 (place/create_state/move/rename/delete/connect/
#                   disconnect/set_transition/참조 노드)
#   ports.py      — 포트 (set_transfer_on/add_agent_call/remove_agent_call)
#   blackboard.py — 블랙보드 (create_blackboard_class/set_state_access)
#   hooks.py      — 훅 라이브러리 (create/update/delete_hook/set_component_hooks/조회)
#   body.py       — 본문 (set_component_body/get_body_outline/get_body_section/
#                   set_body_section)
#   props.py      — 생성·속성 (create_skill/create_agent/rename_component/
#                   description/when_to_use/field/project_properties/set_mcp_server_def)
from __future__ import annotations

# ── 분해 전 모듈의 부수 임포트 (파사드 완전성 — dir 기준 공개 집합 보존) ──
import os  # noqa: F401
from typing import Any  # noqa: F401

from ._base import _MAX_BODY_PREVIEW, _BaseTools  # noqa: F401
from .blackboard import BlackboardTools
from .body import BodyTools
from .canvas import CanvasTools
from .hooks import HookTools
from .ports import PortTools
from .props import PropsTools
from .workspace import WorkspaceTools
from .query import QueryTools
from .session import SessionTools


class DaedalusTools(
    QueryTools,
    SessionTools,
    CanvasTools,
    PortTools,
    BlackboardTools,
    HookTools,
    BodyTools,
    PropsTools,
    WorkspaceTools,
):
    """MainWindow 하나에 붙는 도구 모음."""
