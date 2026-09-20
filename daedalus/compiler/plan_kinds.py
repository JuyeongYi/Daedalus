# daedalus/compiler/plan_kinds.py
"""산출 계획 kind 문자열의 **유일한 소유자** (WP-5).

계획 한 행의 `kind`는 두 가지를 동시에 말한다 — "무엇이 나가는가"와 "누가
그것을 쓰는가"(`units.registry.UNIT_BY_ID`의 조회 키). 그 문자열이 모듈마다
흩어져 있으면 새 산출을 더할 때 어디를 고쳐야 하는지 아무도 말해 주지 않고,
빠뜨린 자리는 조용한 no-op가 된다 — 쓰기 루프의 `else: raise`가 잡아 주기
전까지는.

그래서 리터럴은 여기에만 둔다(`tests/test_kind_literals.py`가 AST로 강제한다).
다른 모듈은 이름으로 참조한다. 값 자체는 저장 파일에 나가지 않는다 —
`CompileResult.skipped`의 라벨과 토큰 리포트 항목의 `kind`에만 실린다.

이 모듈은 **리프**다: 아무것도 임포트하지 않는다. 그래야 `emit/guides.py`가
계획 어휘를 재-export하면서도 `compiler.plan`/`compiler.units` 쪽으로 가는
역방향 간선을 만들지 않는다(§R1 방향 계약).
"""
from __future__ import annotations

# ── 컴포넌트 산출 (TEXT) ──
SKILL = "skill"
AGENT = "agent"

# ── 복사 ──
SKILL_FILE = "skill_file"
FILES_TREE = "files_tree"

# ── 프로젝트 수준 텍스트 산출 ──
HOOKS_JSON = "hooks_json"
HOOK_SCRIPT = "hook_script"
WORKSPACE_RULE = "workspace_rule"
GUIDE_WORKFLOW = "guide_workflow"
GUIDE_BLACKBOARD = "guide_blackboard"
SCHEMAS_JSON = "schemas_json"
PLUGIN_MANIFEST = "plugin_manifest"
MCP_JSON = "mcp_json"

# ── LOCAL 설치 (MERGE, Phase.INSTALL) ──
LOCAL_WIRING = "local_wiring"
CLAUDE_MD = "claude_md"

#: 공통 안내 파일 kind 둘 — `emit/guides.py`가 이 이름을 재-export한다.
GUIDE_KINDS: tuple[str, ...] = (GUIDE_WORKFLOW, GUIDE_BLACKBOARD)
