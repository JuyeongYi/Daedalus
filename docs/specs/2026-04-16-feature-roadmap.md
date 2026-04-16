# Daedalus Feature Roadmap

플러그인 FSM을 완전히 구축하기 위한 미구현 기능 목록.
2026-04-16 기준 현재 상태 분석 결과.

---

## Layer 1: FSM 모델링 완성

캔버스에서 FSM의 **제어 흐름**과 **데이터 흐름**을 완전히 표현하기 위해 필요한 항목.

### 1-1. ChoiceState 배치

- **무엇:** if/else 분기 노드. 진입 즉시 Guard를 평가하여 나가는 전이 중 하나를 선택.
- **편집 위치:** 캔버스(노드 배치) + PropertyPanel(이름)
- **의존:** Guard 편집(1-3)과 세트. Guard 없이는 의미 없음.
- **모델:** `pseudo.py: ChoiceState` — 이미 존재.

### 1-2. TerminateState 배치

- **무엇:** FSM 강제 종료 노드. 에러 상황 등에서 워크플로우를 즉시 중단.
- **편집 위치:** 캔버스(노드 배치) + PropertyPanel(이름)
- **모델:** `pseudo.py: TerminateState` — 이미 존재.

### 1-3. Guard 편집

- **무엇:** 전이 조건. "이 엣지를 탈 수 있는가?"
- **편집 위치:** 엣지 선택 → PropertyPanel 또는 전용 패널
- **필요 UI:** Strategy 선택(LLM/Tool/MCP/Expression) + 파라미터 입력
- **모델:** `guard.py: Guard`, `strategy.py: EvaluationStrategy` 계열 — 이미 존재.

### 1-4. Variable I/O

- **무엇:** 상태(스킬 노드)의 입력/출력 변수 정의.
- **편집 위치:** 노드 선택 → PropertyPanel
- **필요 UI:** 변수 추가/삭제, scope/field_type/required/default 설정
- **모델:** `state.py: State.inputs/outputs`, `variable.py: Variable` — 이미 존재.
- **의존:** data_map(1-5)과 세트. 변수를 정의해야 배선이 가능.

### 1-5. Transition data_map

- **무엇:** 소스 상태의 output → 타겟 상태의 input 변수 배선.
- **편집 위치:** 엣지 선택 → PropertyPanel
- **필요 UI:** 소스 outputs / 타겟 inputs 목록에서 매핑 설정
- **모델:** `transition.py: Transition.data_map` — 이미 존재.
- **의존:** Variable I/O(1-4) 선행 필요.

### 1-6. Action 편집

- **무엇:** 상태 진입/퇴장 시, 전이 시 실행할 동작 설정.
- **편집 위치:** 노드/엣지 선택 → PropertyPanel
- **필요 UI:** Strategy 선택(LLM/Tool/MCP/Composite) + 파라미터 입력
- **대상 필드:**
  - State: `on_entry`, `on_exit` (+ `on_entry_start/end`, `on_exit_start/end`, `on_active`)
  - Transition: `on_traverse` (+ `on_guard_check`, `on_traverse_start/end`)
- **모델:** `action.py: Action`, `strategy.py: ExecutionStrategy` 계열 — 이미 존재.

### 1-7. Blackboard

- **무엇:** FSM 레벨의 공유 데이터 저장소. 서로 다른 컨텍스트 간 데이터 공유.
- **편집 위치:** 프로젝트/에이전트 설정 패널 (별도 탭 또는 도킹 패널)
- **필요 UI:**
  - 공유 Variable 추가/삭제/편집
  - DynamicClass 정의 (필드 스키마)
  - parent 스코핑 시각화
- **모델:** `blackboard.py: Blackboard, DynamicClass, DynamicField` — 이미 존재.

### 1-8. ParallelState / Region

- **무엇:** 여러 작업을 동시에 돌리는 병렬 실행 상태. 각 Region이 독립 FSM.
- **편집 위치:** 캔버스(새 노드 타입) + 더블클릭으로 Region 편집 진입
- **필요 UI:** Region 추가/삭제, 각 Region 내부 FSM 편집 (AgentFsmScene과 유사한 구조)
- **모델:** `state.py: ParallelState, Region` — 이미 존재.
- **복잡도:** 높음. AgentEditor처럼 별도 편집 뷰 필요.

---

## Layer 2: 플러그인 메타데이터 완성

모델에 필드가 있지만 에디터에서 편집할 수 없는 것들.
기존 에디터에 필드/위젯을 추가하는 작업.

### 2-1. AgentConfig 전체 편집

- **대상 필드:**
  - `tools: list[str]` — 사용 가능 도구 목록
  - `disallowed_tools: list[str]` — 금지 도구 목록
  - `permission_mode: PermissionMode` — 권한 모드
  - `max_turns: int` — 최대 턴 수
  - `mcp_servers: list[dict]` — MCP 서버 설정
  - `memory: MemoryScope` — 메모리 스코프
  - `background: bool` — 백그라운드 실행
  - `isolation: AgentIsolation` — 워크트리 격리
  - `initial_prompt: str` — 시작 프롬프트
- **편집 위치:** AgentEditor Content 탭 확장 또는 별도 Config 탭
- **필요 위젯:** TagInput(tools), ComboBox(permission_mode, isolation), SpinBox(max_turns), CheckBox(background), TextEdit(initial_prompt)

### 2-2. ExecutionPolicy

- **무엇:** 병렬 에이전트 실행 정책 (고정/동적, 수량, 합류 전략).
- **편집 위치:** AgentEditor
- **필요 위젯:** ComboBox(mode), SpinBox(count), ComboBox(join)
- **모델:** `policy.py: ExecutionPolicy, JoinStrategy` — 이미 존재.

### 2-3. EventDef.description

- **무엇:** transfer_on / call_agents 이벤트 포트의 설명 텍스트.
- **편집 위치:** SkillEditor EventCard
- **필요 위젯:** QLineEdit 추가
- **영향:** 노드 포트 툴팁 표시 가능.

---

## Layer 3: agent_plan.md 미구현 항목

### 3-1. 툴 리스트

- **무엇:** 사용 가능한 CLI 도구, MCP 서버 등의 선택 가능한 목록.
- **현재:** 모델에 `AgentConfig.tools`, `SkillConfig.allowed_tools` 필드 존재. TagInput으로 자유 입력만 가능.
- **필요:** 도구 자동완성/프리셋, MCP 서버 설정 UI.
- **구현 방식:** 논의 필요.

### 3-2. 훅 생성 UI

- **무엇:** 훅 정의 및 후킹 시점 지정.
- **현재:** `HookPresetPicker` (JSON 프리셋 선택)만 존재.
- **필요:** 훅 생성/편집 폼, 시점 선택(PreSubagentStart, PostToolUse 등).
- **구현 방식:** 논의 필요.

### 3-3. 플러그인 로드

- **무엇:** 외부 플러그인의 스킬/에이전트/훅/MCP를 불러오기.
- **규칙:**
  - 외부 플러그인의 스킬은 FSM 기반이 아닐 확률이 높아 참조 스킬로 취급.
  - `.daedalus` 폴더가 있고 직렬화된 정보가 있는 경우에만 로드.
- **의존:** 직렬화/역직렬화(4-1) 선행 필요.

---

## Layer 4: 신규 기능

현재 모델에도 없고, 기존 계획에도 없는 새로운 기능 영역.

### 4-1. 직렬화 / 역직렬화

- **무엇:** 프로젝트를 파일로 저장하고 불러오기.
- **필요성:** 현재 세션이 끝나면 작업 내용이 사라짐. 도구의 기본 전제 조건.
- **포맷:** YAML 또는 JSON (pyproject.toml에 pyyaml 의존성 이미 존재).
- **범위:** PluginProject 전체 (skills, agents, FSM, blackboard, 캔버스 좌표).

### 4-2. Compiler

- **무엇:** model → SKILL.md / Agent .md 파일 생성.
- **필요성:** 도구의 최종 출력물. 이것 없이는 만든 FSM을 실제로 쓸 수 없음.
- **CLAUDE.md 기재:** `compiler/` — 미구현 예정으로 이미 계획됨.

### 4-3. 실시간 Validation 피드백

- **무엇:** 캔버스에서 Validator 규칙 위반을 시각적으로 표시.
- **현재:** `validation.py`에 7개 규칙 존재하지만 UI와 연결 안 됨.
- **UI:** 위반 노드에 빨간 테두리, 위반 엣지에 경고 아이콘, 하단 패널에 오류 목록.

### 4-4. 생성 파일 프리뷰

- **무엇:** Compiler가 생성할 .md 파일 내용을 편집기 내에서 미리보기.
- **의존:** Compiler(4-2) 선행 필요.

### 4-5. FSM 시뮬레이션

- **무엇:** 설계한 상태 전이를 단계별로 시각적 워크스루.
- **UI:** 현재 상태 하이라이트, 다음 가능한 전이 표시, Guard 평가 시뮬레이션.
- **필요성:** 설계한 흐름이 의도대로 동작하는지 검증.

### 4-6. 복사 / 붙여넣기

- **무엇:** 노드 + 전이 그룹을 복제.
- **UI:** Ctrl+C/V, 또는 우클릭 메뉴.
- **범위:** 단일 노드 또는 선택 영역 복제.

### 4-7. 검색

- **무엇:** 대규모 그래프에서 노드/스킬 이름 검색 및 포커스 이동.
- **UI:** Ctrl+F → 검색바 → 결과 노드로 카메라 이동.

### 4-8. 외부 스크립트 실행 노드

- **무엇:** 별도 프로그램이 생성한 에이전트 실행 스크립트(`.ps1`, `.sh` 등)를 실행하는 노드.
- **전제:**
  - 스크립트는 실행 위치에 이미 존재 (Daedalus가 생성하지 않음)
  - 스크립트 내부에 `claude --print` 등 비대화형 CLI 플래그가 설정됨
  - cwd는 실행 시점에 결정
- **기존 노드와의 차이:** ProceduralSkill은 본문(마크다운)을 직접 정의. 이 노드는 외부 스크립트에 실행을 위임.
- **모델:** 새로운 상태/스킬 유형 필요 (기존 모델에 없음)
