# 에이전트 그래프 설계 스펙

에이전트의 서브그래프를 별도 탭에서 편집할 수 있는 UI와, 이를 뒷받침하는 모델 변경.

## 핵심 원칙

- 에이전트 = **별도 컨텍스트에서 동작하는 자족적 함수**
- 서브그래프는 EntryPoint(1개) → 스킬 노드들 → ExitPoint(1+개)로 구성
- ExitPoint = 함수의 **반환값** (transfer_on이 아님)
- 에이전트 내부 스킬은 **에이전트 로컬** — 프로젝트 스킬과 완전 분리

## 1. 모델 변경

### 1.1 AgentDefinition

```python
@dataclass
class AgentDefinition(PluginComponent, WorkflowComponent):
    config: AgentConfig = field(default_factory=AgentConfig)
    execution_policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    sections: list[Section] = field(default_factory=lambda: [Section(title="instruction")])
    skills: list[Skill] = field(default_factory=list)  # 에이전트 로컬 스킬

    # transfer_on 제거

    @property
    def output_events(self) -> list[str]:
        """sub_machine의 ExitPoint 이름 목록."""
        return [s.name for s in self.fsm.states if isinstance(s, ExitPoint)]
```

- `transfer_on: list[EventDef]` 필드 제거
- `skills: list[Skill]` 필드 추가 (ProceduralSkill + TransferSkill)
- `sections` 기본값을 `[Section(title="instruction")]`으로 변경
- `output_events`가 `self.fsm.states`에서 ExitPoint를 필터링하여 반환

### 1.2 ExitPoint에 color 속성 추가

```python
@dataclass
class ExitPoint(State):
    """CompositeState에서 특정 경로로 탈출."""
    color: str = "#4488ff"  # 부모 노드 출력 포트 색상

    @property
    def kind(self) -> str:
        return "exit_point"
```

- 부모 노드의 출력 포트 색상으로 사용 (EventDef.color와 동일 역할)

### 1.3 에이전트 초기 FSM 구조

에이전트 생성 시 sub_machine 기본 구성:

```
StateMachine(
    states=[EntryPoint("entry"), ExitPoint("done")],
    initial_state=EntryPoint("entry"),
    final_states=[ExitPoint("done")],
)
```

### 1.4 노드에서 출력 이벤트/색상 접근

`node_item.py`의 `_event_defs()` / `_output_events()`는 현재 `skill_ref.transfer_on`을 참조.
AgentDefinition에서는 ExitPoint 목록으로 대체 필요.

```python
# AgentDefinition에 추가
@property
def exit_points(self) -> list[ExitPoint]:
    return [s for s in self.fsm.states if isinstance(s, ExitPoint)]

@property
def output_event_defs(self) -> list[EventDef]:
    """노드 포트 렌더링용 — ExitPoint에서 EventDef 호환 객체 생성."""
    return [EventDef(name=ep.name, color=ep.color) for ep in self.exit_points]
```

`node_item.py`의 `_event_defs()`가 `skill_ref`의 타입에 따라:
- ProceduralSkill/TransferSkill → `skill_ref.transfer_on`
- AgentDefinition → `skill_ref.output_event_defs`

## 2. AgentEditor 위젯

### 2.1 탭 구조

```
AgentEditor (QWidget)
└── QTabWidget
    ├── 📐 Graph   — AgentFsmView (FsmCanvasView + 미니 레지스트리)
    ├── 📝 Content — SectionTree + BreadcrumbNav + SectionContentPanel
    └── ⚙ Config  — _FrontmatterPanel
```

- `app.py`에서 `isinstance(component, AgentDefinition)` → `AgentEditor` 생성
- 기존 `SkillEditor`는 ProceduralSkill / DeclarativeSkill / TransferSkill 전용으로 유지
- Content 탭의 `_FrontmatterPanel`, `SectionTree` 등은 기존 위젯 재활용

### 2.2 Graph 탭 레이아웃

```
Graph 탭 (QSplitter Horizontal)
├── 미니 레지스트리 (좌측 사이드바, 최소폭)
│   ├── 에이전트 로컬 ProceduralSkill 목록
│   ├── 에이전트 로컬 TransferSkill 목록
│   └── "＋ 새 스킬" 버튼
└── FsmCanvasView (에이전트 sub_machine 전용 FsmScene)
```

- 미니 레지스트리에서 드래그&드롭으로 노드 배치 (프로젝트 FSM과 동일 UX)
- 에이전트 로컬 스킬만 표시 — 프로젝트 스킬/다른 에이전트 미노출

### 2.3 Content 탭

기존 SkillEditor의 우측 영역과 동일한 구조:
- SectionTree + BreadcrumbNav + SectionContentPanel
- 초기 섹션: `# instruction`
- `# workflow`는 편집기에서 노출하지 않음 (빌드 시 자동 생성)

### 2.4 Config 탭

기존 `_FrontmatterPanel`을 그대로 사용:
- name, description (필수)
- FIELD_REGISTRY 기반 선택 필드 (AgentConfig)

## 3. 서브그래프 캔버스 동작

### 3.1 EntryPoint / ExitPoint 렌더링

`_TYPE_STYLE` 딕셔너리 확장:

| kind | bg | border | header | icon |
|------|------|---------|--------|------|
| `entry_point` | `#1a1a3a` | `#4488ff` | `▶ ENTRY` | 없음 |
| `exit_point` | `#2a1a1a` | ExitPoint.color | `⏹ EXIT` | 없음 |

차이점:
- EntryPoint: **출력 포트만** 있음 (입력 포트 없음) — 서브그래프의 시작점
- ExitPoint: **입력 포트만** 있음 (출력 포트 없음) — 서브그래프의 종료점
- 두 유형 모두 드래그 이동 가능, 크기는 일반 노드와 동일

포트 제한 구현:
- `StateNodeItem`에서 `state_vm.model`이 EntryPoint/ExitPoint인지 체크
- EntryPoint: `paint()`에서 입력 포트 원 렌더링 생략, `is_input_port()` → False 고정
- ExitPoint: `paint()`에서 출력 포트 원/라벨 렌더링 생략, `_get_output_port_event()` → None 고정
- 이로써 전이 드래그 시 EntryPoint에 입력 연결 불가, ExitPoint에서 출력 연결 불가

### 3.2 제약 규칙

| 규칙 | 설명 |
|------|------|
| EntryPoint 개수 | 정확히 1개. 삭제/추가 불가 |
| ExitPoint 개수 | 1개 이상. 자유롭게 추가/삭제. 마지막 1개는 삭제 불가 |
| 에이전트 노드 배치 | 불가 (기존 `no_nested_agent` Validator 규칙) |
| Declarative 스킬 | 서브그래프에 미노출 |
| EntryPoint 전이 | 출력 전이만 가능 (입력 전이 불가) |
| ExitPoint 전이 | 입력 전이만 가능 (출력 전이 불가) |

### 3.3 컨텍스트 메뉴

**빈 공간 우클릭:**
- "빈 상태 추가"
- "ExitPoint 추가"

**EntryPoint 우클릭:**
- (삭제 비활성)

**ExitPoint 우클릭:**
- "이름 변경"
- "색상 변경"
- "삭제" (마지막 1개면 비활성)

**일반 노드 우클릭:**
- 프로젝트 FSM과 동일 (삭제, 전이 관련)

### 3.4 ExitPoint 더블클릭

ExitPoint를 더블클릭하면 해당 로컬 스킬 편집기가 열리지 않음 (ExitPoint는 스킬이 아님).
일반 스킬 노드 더블클릭 → AgentEditor 내에서 별도 탭이 아닌, Content 탭 전환 + 해당 스킬 선택 등은 향후 고려.

## 4. ExitPoint → 부모 노드 동기화

단방향 흐름:

```
서브그래프 ExitPoint 변경
  → AgentDefinition.output_events (computed property)
  → on_notify_fn() 호출
  → 프로젝트 FSM _rebuild()
  → 해당 에이전트 노드 update_from_model()
  → 출력 포트 개수/이름/색상 갱신
```

부모 노드의 출력 포트는 읽기 전용 파생값. TransferOn 패널은 에이전트에 노출하지 않음.

## 5. Undo/Redo

- 서브그래프 조작은 프로젝트 VM의 커맨드 스택에 기록 (현재 SkillEditor와 동일)
- ExitPoint 추가/삭제/이름변경/색상변경 → 전용 Command 클래스
- 부모 노드 포트 갱신은 커맨드 실행 후 `notify()`로 자동 트리거

## 6. 범위 제외

이 스펙에서 다루지 않는 항목:
- 참조 스킬 (agent_plan.md의 새 항목 — 별도 설계)
- 컴파일러/빌드 단계 (`# workflow` 자동 생성)
- Blackboard 시각화
- CompositeState 모델 변경 (현재 모델로 충분)
