# Daedalus

FSM 기반 Claude Code 플러그인 하네스 엔지니어링 도구.

스킬(Skill)과 에이전트(Agent) 컴포넌트를 FSM + Blackboard 모델로 설계하고, 컴파일러 패턴으로 플러그인 파일을 생성한다.

## 개요

Daedalus는 Claude Code 플러그인 개발을 위한 시각적 편집 환경이다. 유한 상태 기계(FSM) 개념을 기반으로 스킬과 에이전트의 실행 흐름을 그래프로 설계하고, 최종적으로 Claude Code가 읽을 수 있는 플러그인 파일을 생성하는 컴파일러 파이프라인을 목표로 한다.

```
모델 (model/) → 컴파일러 (compiler/, 미구현) → 플러그인 파일 (SKILL.md / Agent.md)
```

## 설치

Python 3.12 이상이 필요하다.

```bash
pip install -e ".[dev]"
```

## 실행

```bash
python -m daedalus
```

## 테스트

```bash
python -m pytest tests/ -v
```

## 아키텍처

### 레이어 구조

```
daedalus/
├── model/          # 순수 도메인 모델 (PyQt 무관)
│   ├── fsm/        # FSM 코어 — 상태, 전이, 가드, 액션, 블랙보드
│   ├── plugin/     # Claude 플러그인 메타데이터 — 스킬, 에이전트, 설정
│   ├── project.py  # PluginProject (최상위 컨테이너)
│   └── validation.py  # 7가지 검증 규칙
└── view/           # PyQt6 GUI
    ├── canvas/     # 노드-엣지 그래프 편집기
    ├── editors/    # 스킬/에이전트 속성 편집기
    ├── panels/     # 프로젝트 트리, 레지스트리, 히스토리 패널
    ├── viewmodel/  # 뷰-모델 어댑터
    └── commands/   # Undo/Redo 커맨드
```

### 핵심 개념

| 종류 | 설명 |
|------|------|
| `ProceduralSkill` | 자체 FSM을 가진 절차적 작업 스킬 |
| `DeclarativeSkill` | FSM 없는 선언적 지식 스킬 |
| `AgentDefinition` | 별도 컨텍스트에서 동작하는 에이전트 (자체 FSM + Blackboard) |
| `Section` | 스킬 컨텐츠의 H1-H6 트리 섹션 |
| `EventDef` | 스킬/에이전트 출력 이벤트 정의 (이름 + 색상) |
| `Blackboard` | 컨텍스트 간 공유 데이터 저장소 |

### FSM 구성 요소

- **State**: `SimpleState`, `CompositeState` (에이전트), `ParallelState` (병렬 실행)
- **Transition**: Guard 조건 + Action 실행 + 이벤트 트리거
- **Blackboard**: 계층적 스코프의 공유 변수 저장소
- **Strategy**: LLM / Tool / MCP / Expression 기반 가드·액션 전략

### 검증 규칙

| 규칙 | 내용 |
|------|------|
| `initial_state_in_states` | 초기 상태가 상태 목록에 포함되어야 함 |
| `final_states_in_states` | 최종 상태들이 상태 목록에 포함되어야 함 |
| `no_nested_agent` | CompositeState 안에 CompositeState 불가 |
| `no_agent_to_agent` | Agent → Agent 직접 전이 불가 (Skill 경유 필수) |
| `missing_required_input` | LOCAL scope 필수 입력이 data_map에 없으면 경고 |
| `pseudo_state_hooks` | 가상 상태에 lifecycle 훅 설정 시 경고 |
| `completion_event_on_composite` | CompositeState 출력 전이에 CompletionEvent 없으면 경고 |

## GUI 주요 기능

- **캔버스**: 드래그로 스킬/에이전트 노드 배치, 포트 연결로 전이 생성
- **스킬 에디터**: 3-패널 레이아웃 — Frontmatter / Section 트리 / 컨텐츠 편집
- **레지스트리 패널**: 프로젝트 내 스킬·에이전트 목록 및 드래그 팔레트
- **히스토리 패널**: Undo/Redo 커맨드 스택 시각화
- **프로퍼티 패널**: 선택된 노드의 속성 표시

## 현재 구현 범위

- [x] FSM 코어 모델 (`model/fsm/`)
- [x] 플러그인 메타데이터 모델 (`model/plugin/`)
- [x] 모델 검증기 (`model/validation.py`)
- [x] PyQt6 캔버스 노드 에디터 (`view/canvas/`)
- [x] 스킬 에디터 3-패널 레이아웃 (`view/editors/skill_editor.py`)
- [x] 변수 삽입 팝업 + 3계층 변수 로더 (`view/editors/variable_loader.py`)
- [x] EventDef.color → 캔버스 포트 색상 연동
- [ ] 컴파일러 (`compiler/`) — 모델 → 플러그인 파일 생성

## 라이선스

MIT
