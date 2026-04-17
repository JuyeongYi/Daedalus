# 툴 아키텍처 개선 — 세션 이어서 작업용 문서

- **작성일:** 2026-04-17
- **세션 주제:** daedalus model 층의 툴(Tool) 관련 구조 점검 + 개선 설계
- **진행 상태:** 치명적 문제 ①②는 설계 결정 완료. ③④⑤⑥ 및 부수적 문제 미진행.
- **같이 볼 문서:** [점검 리포트](../superpowers/specs/2026-04-17-tool-architecture-review.md)

---

## 1. 왜 이 작업을 하는가

Daedalus의 `daedalus/model/` 내 툴 관련 코드가 타입 약하고 검증 공백이 있음.
내장 툴·MCP·사용자 정의 CLI를 모두 한 모델로 다룰 수 있는 구조가 필요.

구체 문제(리포트 §2 참조):
- 모든 툴 식별자가 자유 문자열 → 오타 미검출
- `allowedTools` ↔ `ToolExecution.tool` 연계 검증 없음
- `success_condition: str` 포맷 미정의
- `command: str` shell 분기 처리 없음
- MCP 서버 레지스트리 부재 등

---

## 2. 누적 결정 사항 (문제 ①② 설계 완료)

| 코드 | 내용 | 요약 |
|---|---|---|
| **α** | 서브커맨드 처리 | UserDefinedTool은 **한 툴 = 한 명령어 단위**. `GitCommit`/`GitPush`를 별개로 선언. CC `allowedTools` granularity가 서브커맨드 단위라 1:1 매핑. |
| **D** | 툴 모델 전체 형태 | **ABC + 3 서브클래스 + 프로젝트 Registry**. `Tool(ABC) → BuiltinTool / MCPTool / UserDefinedTool`. `PluginProject.tool_shelf` 보유. strategy.py 기존 스타일과 일관. |
| **Z** | Shelf vs FSM-assigned | **2계층 물리 분리**. shelf = 프로젝트, assigned = 컴포넌트의 이름 참조. "참조 유무가 곧 상태" → drift 원천봉쇄. |
| **S1** | 스킬 deny 리스트 | **추가 안 함**. CC 실제 스펙 그대로 (스킬은 `allowedTools`만). |
| **S2** | 필드 네이밍 | **CC 네이밍 그대로 유지**. 스킬=`allowedTools`, 에이전트=`tools`+`disallowedTools`. |
| **S3** | 검증 정책 | **Strict 에러 + Auto-assist**. FSM-used ⊄ effective permission이면 ValidationError. UI/CLI가 "FSM에서 쓰는 툴을 allowedTools에 자동 채우기" 기능 제공. |
| **B1** | `ToolExecution.tool` 타입 | **이름 문자열 + Validator resolve**. 직렬화/역직렬화/컴파일 단순. 참조는 한 번 끊지만 Validator에서 이름→객체로 resolve. |

### 핵심 공식

**Effective permission (유효 권한)**

```
eff(allow, deny) =
    (allow if allow is not None else ALL_TOOLS)
    ∖ (deny if deny is not None else ∅)
```

**검증 제약 (Validator 규칙 1)**

```
fsm_used_tools ⊆ eff(allowedTools, disallowedTools)
```

---

## 3. 설계 스케치 (다음 세션이 구현 계획서 만들 출발점)

### 새 모듈 (예상 신규 파일)

**`daedalus/model/plugin/tool.py` (신규)**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from daedalus.model.plugin.enums import SkillShell

class ClaudeCodeTool(Enum):
    READ = "Read"
    WRITE = "Write"
    EDIT = "Edit"
    BASH = "Bash"
    GREP = "Grep"
    GLOB = "Glob"
    WEB_FETCH = "WebFetch"
    WEB_SEARCH = "WebSearch"
    TASK = "Task"
    TODO_WRITE = "TodoWrite"
    NOTEBOOK_EDIT = "NotebookEdit"
    SLASH_COMMAND = "SlashCommand"
    AGENT = "Agent"
    # ... 실제 CC 스펙 확인 후 확정

@dataclass
class Tool(ABC):
    name: str
    @property
    @abstractmethod
    def kind(self) -> str: ...

@dataclass
class BuiltinTool(Tool):
    builtin: ClaudeCodeTool
    @property
    def kind(self) -> str: return "builtin"

@dataclass
class MCPTool(Tool):
    server: str
    # name은 Tool.name 재사용 ("mcp__server__tool" 풀 이름)
    @property
    def kind(self) -> str: return "mcp"

@dataclass
class UserDefinedTool(Tool):
    command: str
    shell: SkillShell = SkillShell.BASH
    @property
    def kind(self) -> str: return "user"
```

### 기존 파일 수정

**`daedalus/model/project.py`**
```python
@dataclass
class PluginProject:
    name: str
    tool_shelf: list[Tool] = field(default_factory=list)   # ★ 신규
    skills: list[Skill] = field(default_factory=list)
    agents: list[AgentDefinition] = field(default_factory=list)
    reference_placements: list[ReferencePlacement] = field(default_factory=list)
```

**`daedalus/model/plugin/config.py`** (필드 유지, 의미 재해석)
- `SkillConfig.allowed_tools: list[str]` — shelf의 `Tool.name` 참조
- `AgentConfig.tools: list[str] | None` — 동일
- `AgentConfig.disallowed_tools: list[str] | None` — 동일

**`daedalus/model/fsm/strategy.py`** (유지, 의미 재해석)
- `ToolExecution.tool: str` — shelf의 `Tool.name` 참조
- `ToolEvaluation.tool: str` — 동일

### 신규 검증 규칙 (`daedalus/model/validation.py`)

기존 9개에 더해:

| 규칙 | 유형 | 내용 |
|---|---|---|
| `tool_in_effective_permission` | 에러 | FSM Action이 쓰는 툴이 containing 컴포넌트의 eff() 안에 있는가 |
| `allow_deny_disjoint` | 경고 | `tools ∩ disallowed_tools == ∅` (에이전트) |
| `permission_list_on_shelf` | 에러 | allow/deny 각 이름이 `project.tool_shelf`에 존재 |
| `tool_shelf_unique` | 에러 | shelf 내 Tool.name 중복 금지 |
| `bypass_permission_skip` | 메타 | `permission_mode == BYPASS`이면 위 규칙 스킵 (경고 1회) |
| `unused_shelf_tool` | 정보성 | shelf에만 있고 참조 없는 Tool (에러 아님) |

### UI 영향

- `TagInput` — shelf 기반 자동완성 후보 제공 (미구현 상태에서 가능성만)
- "Auto-assist" 버튼 — skill/agent 편집기에서 "FSM 툴 allowedTools에 자동 채움"

---

## 4. 남은 치명적 문제 (미진행)

| 문제 | 현상 | 예상 해결 방향 |
|---|---|---|
| **③** allow ∩ disallow 교집합 | 에이전트에서 `tools`와 `disallowed_tools`에 같은 항목 들어가도 무검증 | ①②의 `allow_deny_disjoint` 규칙으로 이미 제안됨. **확정만** 남음 |
| **④** `success_condition: str` 포맷 미정의 | 문자열 스키마 없음 → 컴파일러 해석 근거 없음 | `SuccessCondition(ABC)` 계층: `ExitCodeCondition`, `StdoutContainsCondition`, `RegexMatchCondition`, `JsonPathCondition`, `ExpressionCondition` |
| **⑤** `command: str` shell 분기 없음 | 인자 이스케이프·쉘 종류 처리 로직 부재 | `Command(executable, args, shell=None, env={})` 객체. `ToolExecution.command: str \| Command` |
| **⑥** `Action.output_variable` 단일 | `CompositeExecution` children별 출력 매핑 불가 | `Action.output_mapping: dict[str, Variable]` |

---

## 5. 부수적 문제 (Tier 3, 미진행)

- 빈 문자열 기본값 (`tool: str = ""`) → `__post_init__` 방어
- `ToolEvaluation` / `ToolExecution` 구조 중복 → 베이스 통합 또는 재구성
- `TagInput` 자동완성 미지원 → shelf 기반 후보 제안
- `MCPEvaluation.arguments` 스키마 미확인 → MCP 툴 메타데이터 레지스트리
- `permission_mode` vs `tools` vs `mcp_servers` 모순 검증 부재

---

## 6. 보류된 후속 작업 (메모에 저장됨)

- **AgentConfig 실제 Claude Code agent 프론트매터 스펙 점검 필요** — 현재 필드가 실제와 어긋나는 부분 있음
- **`AGENT_FIELD_MATRIX` 신설** — `SKILL_FIELD_MATRIX`(`daedalus/model/plugin/field_matrix.py`)와 동일 구조로
- 메모 파일: `agent-field-matrix-needed.md` (memory store)

→ 툴 논의 종료 후 독립 과제로 다룰 것.

---

## 7. 다음 세션 재개 지점

**옵션 A — 빠른 승리:** 문제 ③ 확정만 (규칙 `allow_deny_disjoint`은 이미 설계됨). 5분짜리.

**옵션 B — 남은 치명적 문제 순차 진행:** ④ → ⑤ → ⑥. 각 1~2 화면.
- ④부터 가면 `SuccessCondition` 계층 설계 (Evaluation/Execution 대칭 여부, Expression 문법 범위 등)
- ⑤는 `Command` 객체 필드 확정 (env, cwd, timeout 포함 여부)
- ⑥은 `output_mapping`의 키 규약 (Action name? Variable name?)

**옵션 C — 구현 계획서 작성:** 지금까지 결정으로 충분하면 바로 `docs/superpowers/plans/YYYY-MM-DD-tool-architecture-plan.md` 작성 후 Tier 1 (Tool enum + 6개 검증 규칙) 구현 착수.

**옵션 D — 점검 리포트의 Tier 2+ 합류:** 문제 ④⑤⑥는 Tier 2(Command/SuccessCondition)와 거의 동일. Tier 1 먼저 끝내고 Tier 2를 함께 설계하는 편이 스코프 정돈됨.

**권장:** 옵션 A + C 조합 — 문제 ③ 확정(5분) → 구현 계획서 → Tier 1 착수. 문제 ④⑤⑥는 Tier 2에서 묶어서.

---

## 8. 관련 파일 지도

### 현 세션 산출물

- `docs/superpowers/specs/2026-04-17-tool-architecture-review.md` — 점검 리포트 (리포트/백그라운드)
- `docs/continue/2026-04-17-tool-architecture-session.md` — **이 문서** (세션 이어서 작업용)
- 브라우저 디자인 캔버스 (참고용, gitignore됨): `.superpowers/brainstorm/827-1776402833/content/` 안의 `problem-01-v*.html`, `problem-02-v*.html`

### 손대야 할 파일 (다음 세션 참고)

**신규:**
- `daedalus/model/plugin/tool.py`

**수정:**
- `daedalus/model/project.py` — `tool_shelf` 추가
- `daedalus/model/validation.py` — 신규 규칙 6개
- 테스트: `tests/model/plugin/test_tool.py` (신규), `tests/model/test_validation.py` (기존에 규칙 추가)

**유지 (의미 재해석만):**
- `daedalus/model/plugin/config.py` — `allowed_tools` 등 필드 유지, shelf 이름 참조로 재해석
- `daedalus/model/fsm/strategy.py` — `ToolExecution.tool: str` 유지, shelf 이름 참조로 재해석

---

## 9. 세션 시작 체크리스트 (다음에 이 문서 열 때)

1. [ ] 이 문서 + 리포트(`2026-04-17-tool-architecture-review.md`) 둘 다 읽기
2. [ ] 메모 파일 확인: `agent-field-matrix-needed`
3. [ ] §7 옵션 중 선택
4. [ ] 선택한 옵션으로 진행 (A/C 권장)
