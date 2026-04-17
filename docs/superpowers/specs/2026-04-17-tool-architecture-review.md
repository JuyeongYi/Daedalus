# 툴 아키텍처 점검 리포트

- **작성일:** 2026-04-17
- **범위:** Daedalus `daedalus/model/` 내 툴(Tool) 관련 모델·검증·UI
- **목적:** 현 구조 파악 / 약점(튼튼함) 식별 / 개선 기능 제안
- **상태:** 점검 결과 문서. 구현 여부는 후속 논의에서 결정.

---

## 1. 현재 구조 요약

| 계층 | 위치 | 핵심 클래스 / 필드 | 역할 |
|---|---|---|---|
| 평가 전략 (Guard) | `model/fsm/strategy.py` | `ToolEvaluation(tool, command, success_condition)`, `MCPEvaluation(server, tool, arguments, success_condition)`, `CompositeEvaluation(op, children)` | 전이 조건 평가 |
| 실행 전략 (Action) | `model/fsm/strategy.py` | `ToolExecution(tool, command)`, `MCPExecution(server, tool, arguments)`, `CompositeExecution(mode, children)` | 액션 실행 |
| Action 래퍼 | `model/fsm/action.py` | `Action(name, execution, output_variable: Variable \| None)` | 실행 + 단일 산출물 매핑 |
| 스킬 설정 | `model/plugin/config.py` | `SkillConfig.allowed_tools: list[str]` | 스킬이 쓸 수 있는 툴 선언 |
| 에이전트 설정 | `model/plugin/config.py` | `AgentConfig.tools / disallowed_tools: list[str] \| None`, `mcp_servers: list[dict] \| None` | 에이전트 툴 권한·MCP 선언 |
| 검증 | `model/validation.py` | 7개 규칙 | 구조 검증 — **툴 관련 규칙 0개** |
| UI 입력 | `view/widgets/tag_input.py`, `model/plugin/field_matrix.py` | `TagInput` (list[str]) | `allowed_tools` 등의 자유 문자열 태그 입력 |

### 검증 규칙 전체 목록 (참고)

1. `initial_state_in_states`
2. `final_states_in_states`
3. `no_nested_agent`
4. `no_agent_to_agent`
5. `missing_required_input`
6. `pseudo_state_hooks`
7. `completion_event_on_composite`
8. `no_duplicate_skill_ref`
9. `transfer_on_not_empty`

→ 툴(식별자, 권한, MCP 서버 등록 여부) 관련 검증 없음.

---

## 2. 튼튼함(Robustness) 관점 — 발견된 약점

### 🔴 치명적 (실사용 시 문제를 반드시 일으킬 수준)

1. **모든 툴 식별자가 자유 문자열.**
   내장 툴(`Read`, `Write`, `Bash`, …)을 표현하는 enum·레지스트리가 없음. `ToolExecution(tool="Reed")` 같은 오타가 런타임/컴파일러까지 살아남는다.

2. **`allowed_tools` ↔ `ToolExecution.tool` 연계 검증 없음.**
   스킬 본문 Action에서 쓰는 툴이 프론트매터 `allowed_tools`에 선언되지 않아도 모델 검증을 통과한다.

3. **`AgentConfig.tools` / `disallowed_tools` 교집합 검증 없음.**
   같은 툴을 허용하고 동시에 금지해도 경고가 안 나온다.

4. **`success_condition: str` 포맷 미정의.**
   `"exit_code == 0"`과 `"stdout.contains('OK')"`를 같은 자리에서 받지만 스키마가 없어 컴파일러가 해석할 근거가 없다.

5. **`command: str` 단일 문자열.**
   인자 이스케이프·쉘 분기(`SkillShell.BASH` vs `POWERSHELL`) 처리 로직 부재. 쉘에 따라 다른 커맨드가 필요할 때 표현 수단이 없다.

6. **`Action.output_variable`이 단일.**
   `CompositeExecution` children이 각각 산출물을 낼 수 있지만 매핑 수단이 1:1로 제한됨.

7. **MCP 서버 레지스트리 부재.**
   `MCPExecution.server="github"`가 `AgentConfig.mcp_servers`에 실제로 선언됐는지 검증 불가. 서버 이름/버전/설정이 타입 없는 `list[dict]`로 들어감.

### 🟡 부수적 (개선 필요)

8. **빈 문자열 기본값.** `tool: str = ""`, `command: str = ""` 등이 dataclass 기본값이라 "깡통" 인스턴스가 무검증으로 생성된다. `__post_init__` 차단 없음.

9. **`ToolEvaluation` / `ToolExecution` 구조 중복.**
   평가 = 실행 + 성공조건. 공통 베이스 또는 "평가는 실행 + Condition" 구조 리팩터 여지 있음.

10. **TagInput 자동완성 없음.**
    내장 툴 목록, 프로젝트에 등록된 MCP 툴 목록을 알지 못해 사용자가 매번 손으로 정확한 문자열을 쳐야 한다.

11. **`MCPEvaluation.arguments` 스키마 미확인.**
    `dict[str, Any]`만 있고 대상 MCP 툴 시그니처와의 일치성을 검증하지 않는다.

12. **툴 권한 모드와 MCP 조합 정합성 미검증.**
    `permission_mode`, `tools`, `mcp_servers`가 서로 모순되어도 경고 없음 (예: `DONT_ASK` + `disallowed_tools`에 `Bash` 포함 등).

---

## 3. 추가하면 좋을 기능 (우선순위별)

### Tier 1 — 토대 (다른 모든 개선의 전제)

- **A. 내장 툴 레지스트리 (`ClaudeCodeTool` enum).**
  `READ`, `WRITE`, `EDIT`, `BASH`, `GREP`, `GLOB`, `WEB_FETCH`, `WEB_SEARCH`, `TASK`, `TODO_WRITE`, `NOTEBOOK_EDIT`, `SLASH_COMMAND`, `AGENT` 등 Claude Code 내장 툴을 enum화. MCP 툴은 `mcp__{server}__{name}` 포맷으로 별도 표현.
- **B. 툴 관련 검증 규칙 3개 추가.**
  - `tool_in_allowed_tools`: Skill Action이 쓰는 `tool`이 `config.allowed_tools`에 선언됐는지
  - `tools_disallowed_conflict`: `AgentConfig.tools` ∩ `disallowed_tools` 비어 있는지
  - `mcp_server_declared`: `MCPExecution.server`가 `AgentConfig.mcp_servers`에 선언됐는지

### Tier 2 — 컴파일러 구현 전 권장

- **C. `Command` 객체 도입.**
  `Command(executable: str, args: list[str], shell: SkillShell | None = None, env: dict[str, str] = {})`. `ToolExecution.command: str | Command`로 확장.
- **D. `SuccessCondition` 계층화.**
  `ExitCodeCondition(expected: int = 0)`, `StdoutContainsCondition(needle: str)`, `RegexMatchCondition(pattern: str, target: Literal["stdout","stderr"])`, `JsonPathCondition(path, expected)`, `ExpressionCondition(expr: str)` 등 하위 클래스. `success_condition: str`을 `condition: SuccessCondition`으로 교체.

### Tier 3 — 확장

- **E. `Action.output_mapping: dict[str, Variable]`.**
  단일 `output_variable` 대신 이름 키로 매핑. `CompositeExecution` children별 산출물을 표현.
- **F. UI 자동완성.**
  `TagInput`이 내장 툴 enum과 프로젝트에 등록된 MCP 툴을 후보로 제시. 권한 모순은 실시간 경고.
- **G. `MCPServerDefinition` 타입 모델.**
  `AgentConfig.mcp_servers: list[dict]` → `list[MCPServerDefinition]`. 프로젝트 레벨 MCP 레지스트리로 승격해 서버 이름 중복·미선언 검증 기반 제공.

---

## 4. 후속 논의 지점

- 어느 Tier까지를 이번 스코프로 잡을 것인가?
- Tier 1은 독립 PR로 먼저 들어갈 만한가? (의존성이 가장 적음)
- Tier 2(Command / SuccessCondition)는 컴파일러 작업 착수 전에 반드시 선행해야 하는가?
- MCP 서버 모델링(G)의 우선순위를 올릴 이유가 있는가?
- 현재 검증 규칙 9개의 네이밍/조직과 일관성 있게 새 규칙을 추가할지, 별도 그룹으로 분리할지?
