# Shell Script Invocation Strategy for Daedalus Compiler

**Date:** 2026-05-11
**Status:** Investigation / Design Notes
**Scope:** Daedalus 컴파일러가 ClaudeManager(CM) 산출 셸 스크립트를 Claude Code 플러그인 안에서 호출하는 방식

## 배경

### 두 프로젝트 역할 매핑

| 프로젝트 | 역할 | 산출물 |
|---------|------|--------|
| **ClaudeManager (CM)** | claude 호출 셸 스크립트 빌더 | `.bat` / `.ps1` / `.sh` (`-p "<프롬프트>"` 인자, `wt --startingDirectory`로 작업 디렉토리) |
| **Daedalus** | FSM + Blackboard 모델 → 플러그인 컴파일 | `SKILL.md` / `Agent.md` (compiler/ 미구현) |

### 제약

- **CM 스크립트는 plain**: 헤더 메타, `--describe` 자기소개, 사이드카 JSON 모두 없음. CM은 빌더이고 산출물은 그저 claude를 호출하는 셸 파일
- **모든 메타·바인딩은 Daedalus 모델 안에**: 사용자가 캔버스에서 "이 노드의 Action은 이 스크립트 호출"이라고 적어 둠
- **인보크 책임은 Daedalus가 컴파일한 산출물**이 짊

### 통합 흐름

```
ClaudeManager GUI
    │ (사용자가 프로필 + 프롬프트 + CLI 옵션 조합)
    ▼
.ps1/.bat/.sh 스크립트 export
    │ (~/.claudemanager/workspaces/<encode>/<config>/script.ps1)
    │
    ├──[A. 직접 실행 경로]──► wt + claude -p ─► claude 세션
    │                          (CM 단독 사용 — Daedalus 우회)
    │
    └──[B. Daedalus import]──► Daedalus 캔버스 노드
                                   │ (사용자가 FSM Action 속성에 스크립트 경로 입력)
                              FSM 모델 (Action.execution = ToolExecution(script_path))
                                   │ compile
                                   ▼
                              SKILL.md / Agent.md / hooks.json / commands/*.md
                                   │
                                   ▼
                              Claude Code 플러그인
                                   │ (claude가 로드)
                              claude 세션이 인보크 ─► Bash 도구로 .ps1 호출
```

핵심: **같은 스크립트가 두 방향**으로 흐름. 직접 실행(셸→claude) + 플러그인 안에서 호출(claude→셸).

---

## 인보크 메커니즘 — 5가지 레이어

결정론 수준 vs 표현력의 트레이드오프:

| L | 메커니즘 | 결정론 | LLM 의존도 | Daedalus FSM 적합 |
|---|---------|--------|-----------|------------------|
| L1 | SKILL.md 본문에 Bash 호출 텍스트 | 낮음 | 높음 | 일반 SimpleState |
| L2 | + TodoWrite 체크리스트 강제 | 중 | 중 | 순차 State 체인 |
| L3 | 슬래시 명령 (`commands/*.md`) | 중 | 낮음 (사용자 트리거) | EntryPoint |
| L4 | 훅 매처 (`hooks.json`) | 높음 | 낮음 (이벤트 트리거) | 라이프사이클 노드 |
| L5 | 외부 오케스트레이터 + claude 재호출 | 매우 높음 | 매우 낮음 | 복잡 FSM 전체 |

### L1 — SKILL.md 본문에서 Bash 도구로 호출

컴파일러가 FSM 노드의 `ToolExecution(shell, command=...)`를 만나면 본문에 명령형 텍스트로 박음:

```markdown
## Step 2: Run analyze

Use the Bash tool to execute:

```bash
pwsh -File "$CLAUDE_PLUGIN_ROOT/scripts/analyze.ps1" -p "$PROMPT_VAR"
```

Parse stdout as JSON. Store result as `analysis_result`.
```

**컴파일 시 Daedalus가 자동 주입**:
- `$CLAUDE_PLUGIN_ROOT` (Claude Code 환경변수)
- 스크립트 경로 (FSM Action 속성)
- 인자 (FSM Action에서 전달된 args/prompt)
- 출력 변수 이름 (FSM의 Variable.scope=LOCAL → 본문에 "이 변수에 저장하세요" 텍스트)

**결정론 한계**: claude가 본문을 무시하면 끝. 강한 워딩(`MUST`, `EXTREMELY-IMPORTANT`) 추가 가능하지만 보장 아님.

**Daedalus FSM 매핑**: `SimpleState.on_entry`의 `Action`이 `ToolExecution(shell)` → L1로 컴파일.

### L2 — TodoWrite 체크리스트로 강제

L1을 더 결정적으로 만드는 superpowers 트릭. SKILL.md frontmatter에 체크리스트 표시:

```markdown
---
name: analyze-workflow
description: ...
---

## Checklist

You MUST create a TodoWrite task for each:

1. Run analyze script — `Bash: pwsh -File $CLAUDE_PLUGIN_ROOT/scripts/analyze.ps1 ...`
2. Parse JSON output → save to `analysis_result`
3. Run codecheck script — `Bash: pwsh -File $CLAUDE_PLUGIN_ROOT/scripts/codecheck.ps1 ...`
4. Run Planner if `analysis_result.needs_planning == true`
```

superpowers `brainstorming/SKILL.md:24` 패턴 그대로. TodoWrite 항목으로 박히면 claude가 하나씩 처리하면서 누락이 줄어듦. 순차 실행 강제력 ↑.

**Daedalus FSM 매핑**: 여러 SimpleState가 직렬로 연결된 체인 → 컴파일러가 하나의 체크리스트 스킬로 합성.

### L3 — 슬래시 명령으로 진입점 노출

`commands/<name>.md` 자동 생성:

```markdown
---
description: Run the analyze workflow
argument-hint: <target file>
---

Execute the analyze workflow with argument: $ARGUMENTS

First step: use Bash to run:
```bash
pwsh -File "$CLAUDE_PLUGIN_ROOT/scripts/analyze.ps1" -p "$ARGUMENTS"
```

Then proceed through the workflow defined in skills/analyze-workflow/SKILL.md.
```

**결정론**: 트리거 자체는 사용자가 정확히 통제 (`/analyze`만 치면 됨). 트리거 이후는 다시 L1/L2 수준.

**Daedalus FSM 매핑**: `EntryPoint` 가상 상태 → 그 EntryPoint를 슬래시 명령으로 노출하기로 사용자가 캔버스에서 표시.

### L4 — 훅으로 결정론적 자동 호출

LLM 의지에 전혀 의존하지 않는 유일한 메커니즘.

`hooks.json`:
```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Edit|Write",
      "hooks": [{
        "type": "command",
        "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd\" post-edit-analyze"
      }]
    }]
  }
}
```

`hooks/post-edit-analyze` (thin wrapper):
```bash
#!/usr/bin/env bash
exec pwsh -File "${CLAUDE_PLUGIN_ROOT}/scripts/analyze.ps1" --check-only
```

→ 파일 수정 직후 무조건 analyze.ps1 실행. claude 의지 무관.

**한계**:
- 라이프사이클 이벤트(SessionStart, PreToolUse, PostToolUse, UserPromptSubmit 등)에만 묶임
- 임의 시점 호출 불가
- 결과를 claude에게 다시 보여주려면 stderr/stdout 출력 (claude가 그 출력을 읽긴 함)
- claude에게 "이 결과로 다음 결정 내려" 양방향은 어려움

**Daedalus FSM 매핑**:
- `EntryPoint(trigger=SessionStart)` → SessionStart 훅
- `Transition(trigger=PostEdit)` → PostToolUse 훅

**컴파일 시 Daedalus가 자동 검증**: SessionStart 매처에 `compact` 빠뜨리지 않았는지, 무한 루프 위험(셸이 또 Edit 트리거?) 검사.

### L5 — 외부 오케스트레이터 패턴 (결정론 최고)

Daedalus FSM 풍부함을 가장 잘 보존하는 방법. 컴파일러가 SKILL.md 외에 **FSM 런타임 JSON + 오케스트레이터 셸**까지 생성:

```
plugin_root/
├── skills/analyze-workflow/SKILL.md      # claude용 step 가이드
├── scripts/                              # CM 스크립트 그대로 복사
│   ├── analyze.ps1
│   ├── codecheck.ps1
│   └── Planner.ps1
├── fsm/
│   └── analyze-workflow.json             # 컴파일된 FSM 데이터
└── bin/
    └── orchestrate.ps1                   # 외부 오케스트레이터
```

`bin/orchestrate.ps1` (Daedalus 자동 생성):
```powershell
param([string]$Prompt)
$fsm = Get-Content "$PSScriptRoot/../fsm/analyze-workflow.json" | ConvertFrom-Json
$blackboard = @{}
$state = $fsm.initial_state

while ($state -ne $null -and $fsm.final_states -notcontains $state) {
    $stateDef = $fsm.states.$state

    foreach ($action in $stateDef.on_entry) {
        switch ($action.execution.type) {
            "shell" {
                $script = "$PSScriptRoot/../scripts/$($action.execution.script)"
                $result = & $script -p $action.execution.prompt
                $blackboard[$action.output_variable] = $result | ConvertFrom-Json
            }
            "llm" {
                # claude 세션을 단일 step으로 호출
                $result = claude -p $action.execution.prompt `
                    --plugin-dir "$PSScriptRoot/.." `
                    --output-format stream-json `
                    --max-turns 3
                $blackboard[$action.output_variable] = $result
            }
        }
    }

    # 다음 상태 결정 (Guard 평가)
    $state = Evaluate-Transitions $stateDef.transitions $blackboard
}
```

**호출 진입점**: 사용자가 `pwsh bin/orchestrate.ps1 -Prompt "..."` 또는 슬래시 명령에서 이 오케스트레이터를 Bash로 호출.

**장점**:
- Daedalus FSM 모델의 결정론·Guard·Blackboard·CompletionEvent 전부 보존
- claude는 단일 step만 책임 (한 번에 한 작업)
- ToolExecution(shell)과 LLMExecution이 자연스럽게 공존

**단점**:
- claude 세션 컨텍스트 단절 (매 LLM step마다 새 세션) — Blackboard로 보완
- 비용 증가 (세션 부트스트랩 반복)
- 디버깅 어려움 (오케스트레이터 외부에서 step별 추적 필요)

**Daedalus FSM 매핑**: 전체 StateMachine → orchestrator.ps1 한 파일. 특히 **CompositeState(에이전트)**가 있으면 L5가 사실상 필수 — 별도 컨텍스트 + 별도 Blackboard의 격리를 SKILL.md 만으론 표현 불가.

---

## Daedalus 모델 → 인보크 레이어 매핑

| Daedalus FSM 요소 | 권장 인보크 레이어 | 이유 |
|------------------|------------------|------|
| `SimpleState` + `Action(ToolExecution(shell))` | L1 / L2 | 단순 셸 호출 |
| `EntryPoint(trigger=SessionStart\|UserPromptSubmit)` | L4 | 자동 발동 |
| `EntryPoint(trigger=slash_command)` | L3 | 사용자 의도 명확 |
| `Transition(trigger=PostEdit)` | L4 | 이벤트 결정론 |
| `ProceduralSkill` 전체 | L1+L2 | SKILL.md로 묶기 |
| `CompositeState`(에이전트) | L5 | 격리 컨텍스트 필요 |
| `ParallelState`(Region) | L5 | 병렬 실행 강제 |
| `Guard(EvaluationStrategy=Expression)` | L5 | LLM이 정확한 표현식 평가 못 함 |
| `Guard(EvaluationStrategy=LLM)` | L1 | claude가 자연어로 판단 |
| `Blackboard` 공유 | L5 권장 | 외부 JSON 파일로 영속 |

→ 단순 워크플로우는 L1+L2+L4 조합으로 충분, FSM의 풍부한 표현이 필요하면 L5로 fallback.

---

## 공통 인보크 contract

CM 스크립트가 plain이므로, **Daedalus 호출하는 측에서** 모든 컨텍스트를 명시적으로 주입해야 합니다 (superpowers "명시적 컨텍스트 주입" 원칙).

### 호출 표준 형태

```bash
pwsh -File "$PLUGIN_ROOT/scripts/<script>.ps1" \
    -p "<prompt>" \
    [additional CM-known flags: --continue, --resume, --name]
```

CM 스크립트는 `-p "<prompt>"`만 표준 입력으로 받고, 나머지 env/cli 설정은 스크립트 내부에 박혀 있음 (CM README:106).

→ Daedalus는 **prompt 텍스트만 동적으로 결정**하면 됨.

### cwd 전달

CM은 `wt --startingDirectory`로 작업 디렉토리 처리 (CM CLAUDE.md:88). Daedalus 인보크 측에서:

| 레이어 | cwd 처리 |
|--------|---------|
| L1 (SKILL 본문) | 본문에 `cd "<dir>"` 명시 또는 셸 호출 전 `Push-Location` |
| L4 (훅) | `$env:CLAUDE_PROJECT_DIR` 사용 |
| L5 (오케스트레이터) | 오케스트레이터가 명시적으로 `Set-Location` |

### 환경변수 주입

Daedalus가 호출 시점에 추가 env를 박을 수 있음:
```powershell
$env:DAEDALUS_STATE = "analyzing"
$env:DAEDALUS_BLACKBOARD_PATH = "$plugin_root/.daedalus/blackboard.json"
& "$plugin_root/scripts/analyze.ps1" -p $prompt
```

CM 스크립트는 이 추가 env를 무시(자기 env만 씀)하지만, Daedalus는 후처리·추적에 활용 가능.

### 출력 캡처

CM 스크립트는 claude 출력을 그대로 stdout으로 흘림. `--output-format stream-json` 옵션이 CM 측에 켜져 있으면 JSON. Daedalus 인보크 측에서 파싱:

```powershell
$jsonOutput = & "$plugin_root/scripts/analyze.ps1" -p $prompt 2>$null
$lastResult = ($jsonOutput | Where-Object { $_ -match '"type":"result"' } |
               Select-Object -Last 1) | ConvertFrom-Json
$blackboard[$varName] = $lastResult.result
```

→ Daedalus 컴파일러가 이 파싱 코드를 자동 생성 (FSM Action의 `output_variable.field_type`에 따라 JSON/STRING으로 분기).

---

## 무한 루프 / 재진입 가드

CM 스크립트가 `claude`를 호출하므로 양방향 호출 시 재귀 위험:

1. Daedalus 플러그인 로드된 claude가 L4 훅으로 `analyze.ps1` 호출
2. `analyze.ps1`은 그 자체로 `claude -p ...`를 실행
3. 새 claude도 같은 플러그인 로드 → 또 훅 발동 → 또 `analyze.ps1` …

**Daedalus 컴파일러가 자동 삽입할 가드** (wrapper에서, CM 스크립트 자체는 안 건드림):

```bash
# hooks/post-edit-analyze (Daedalus 자동 생성 wrapper)
#!/usr/bin/env bash
if [ -n "${DAEDALUS_REENTRY_GUARD:-}" ]; then
    exit 0  # 재진입 차단
fi
export DAEDALUS_REENTRY_GUARD=1
exec pwsh -File "${CLAUDE_PLUGIN_ROOT}/scripts/analyze.ps1" ...
```

추가 가드:
- L4 훅 매처 검증 시 "셸이 다시 Edit/Write를 트리거하는 경로"를 컴파일러가 정적 분석
- L5 오케스트레이터는 `--plugin-dir`을 안 넘기거나 별도 플러그인 디렉토리 지정으로 재진입 차단 가능

---

## superpowers 패턴 차용 정리

조사 출처: `C:\Users\jylee\source\superpowers_model_specified`

### 부트스트랩 (Daedalus 컴파일러가 자동 생성 가능)

- **SessionStart 훅 + `using-superpowers/SKILL.md` 본문 inline 주입** — 매 세션 첫 컨텍스트에 스킬 사용 본능 시드
- **Polyglot `.cmd` 래퍼** (`hooks/run-hook.cmd`) — 한 파일이 Windows cmd + Unix bash 양쪽에서 유효
- **환경별 JSON 키 3-way 분기** (`session-start:46-55`) — CC(`hookSpecificOutput`) / Cursor(`additional_context`) / Copilot(`additionalContext`)
- **bash 없으면 `exit /b 0` silent fallback** (`run-hook.cmd:38-39`) — 훅 실패가 플러그인 전체를 안 깨뜨림
- **매처에 `compact` 포함** — 컨텍스트 압축 후 본문 재주입

### 디스패치 (서브에이전트)

- **외부 `*-prompt.md` 템플릿 + placeholder 치환** — Daedalus의 `AgentDefinition`을 컴파일할 때 그대로 활용
- **서브에이전트 컨텍스트 비상속 원칙** (`subagent-driven-development/SKILL.md:12`)
- **구조화 상태 enum 리턴** (`implementer-prompt.md:103`: DONE / DONE_WITH_CONCERNS / BLOCKED / NEEDS_CONTEXT)
- **`<SUBAGENT-STOP>` 가드** (`using-superpowers/SKILL.md:8-10`) — 서브에이전트의 부트스트랩 재실행 방지

### cwd 격리 (CM 스크립트 호출 시 활용)

- **셸이 `cd` 후 `claude -p`** — CLI 플래그 아닌 셸 cwd 활용 (CM 스크립트는 이미 `wt --startingDirectory`로 처리)
- **`mktemp -d`로 유니크 cwd → 세션 JSONL 자동 분리** — Daedalus L5 오케스트레이터가 병렬 실행 시 필요
- **cwd 정규화 규칙**: `s|[^a-zA-Z0-9]|-|g`로 세션 JSONL 폴더명 도출
- **macOS `pwd -P` 필수** (`/var` → `/private/var`)

### 자가 테스트 (Daedalus가 생성하는 플러그인을 검증)

- **`claude -p --plugin-dir <자기경로>` 셸에서 호출** — Daedalus가 빌드 후 자동 회귀 테스트 가능
- **`--output-format stream-json` + grep/jq 검증**
- **JSONL 라인 순서로 "premature action" 검출** (`run-test.sh:103-118`)
- **`||  true`로 실패 무시 + 사후 로그 분석**

---

## 점진적 구현 권장 순서

Daedalus의 `compiler/` 미구현 상태에서 시작 시:

1. **L1 컴파일러 먼저** — 가장 단순, FSM의 `SimpleState + ToolExecution(shell)`만 다룸. 모든 FSM은 일단 SKILL.md로 컴파일 가능. 검증 작음.
2. **L3 추가** — `EntryPoint`를 슬래시 명령으로 노출. 사용자 트리거 진입점 확보.
3. **L4 추가** — 훅 매처가 있는 노드 대응. 라이프사이클 트리거 활성화.
4. **L2 추가** — 본문 품질 향상 (체크리스트 + 명령형 워딩 + TodoWrite 강제).
5. **L5 추가** — `CompositeState` / `ParallelState` / 복잡 Guard 등장 시 필수. 외부 오케스트레이터 + FSM JSON + claude 단일 step 호출 구조.

**한 플러그인 안에 여러 레이어 공존 가능**: 슬래시 명령(L3)이 진입점, 본문(L1)이 첫 step 지시, 중간 어디서 L5 오케스트레이터로 위임. 컴파일러는 FSM 모델에서 어느 부분이 어느 레이어로 가는지 결정하는 게 핵심 책임.

---

## 결론 — 한 줄 요약

CM 스크립트는 plain shell로 두되, **Daedalus의 컴파일러가 FSM 모델에서 노드 종류별로 L1~L5 인보크 레이어를 선택**해 SKILL.md / hooks.json / commands/*.md / orchestrator.ps1 산출물을 합성합니다. CM 스크립트 호출 코드는 컴파일러가 표준 contract (cwd, env, 출력 캡처, 재진입 가드)에 따라 자동 inline 주입하므로, CM 측 변경은 필요 없습니다.

## 미해결 / 후속 검토 항목

- **L5 오케스트레이터의 claude 세션 컨텍스트 단절 비용** — 매 LLM step마다 세션 부트스트랩 반복 시 비용·지연 측정 필요
- **CM 스크립트가 자체 `claude -p`를 호출 vs Daedalus가 직접 `claude -p` 호출** — 두 경로의 환경변수·세션 격리 차이 검증
- **L4 훅에서 stdout/stderr가 claude에게 어떻게 노출되는가** — 정확한 표면적 확인 필요 (`additionalContext` 메커니즘 활용 가능성)
- **CompositeState(에이전트)의 `subagent_type` 어떻게 정할 것인가** — Daedalus AgentConfig.isolation 등과 매핑 규칙 미정
- **Blackboard 영속화 포맷** — JSON 파일 vs SQLite vs MCP 서버. `2026-04-17-blackboard-mcp-server-design.md` 참조
