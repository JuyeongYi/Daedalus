# Daedalus UI 스켈레톤 설계 — A단계

## 목표

기존 model/ 레이어를 건드리지 않고, PyQt6 기반 노드 에디터 UI의 최초 스켈레톤을 구현한다.
A단계 범위: SimpleState + Transition만 캔버스에서 배치/연결 가능.

## 로드맵

| 단계 | 캔버스 요소 | 설명 |
|------|-----------|------|
| **A (현재)** | SimpleState + Transition | 노드 배치, 화살표 연결 |
| B | + CompositeState | 에이전트 개념, 서브 머신 포함 노드 |
| C | + ParallelState, PseudoState, Guard, Action | 전체 FSM 요소 |

---

## 1. 패키지 구조

```
daedalus/
├── __main__.py                 # QApplication 생성 + MainWindow 실행
├── model/                      # M — 기존 코어 (불변)
│   ├── fsm/
│   └── plugin/
└── view/                       # V — 새 UI 레이어
    ├── __init__.py
    ├── app.py                  # MainWindow (QMainWindow + DockWidget 구성)
    ├── commands/               # Command 패턴 (Undo/Redo)
    │   ├── __init__.py
    │   ├── base.py             # Command(ABC), MacroCommand, CommandStack
    │   ├── state_commands.py   # CreateStateCmd, DeleteStateCmd, MoveStateCmd, RenameStateCmd
    │   └── transition_commands.py  # CreateTransitionCmd, DeleteTransitionCmd
    ├── viewmodel/              # 모델 래퍼 (UI 전용 상태 추가)
    │   ├── __init__.py
    │   ├── state_vm.py         # StateViewModel, TransitionViewModel
    │   └── project_vm.py       # ProjectViewModel (전체 편집 세션 상태)
    ├── canvas/                 # QGraphicsScene/View 기반 캔버스
    │   ├── __init__.py
    │   ├── scene.py            # FsmScene (QGraphicsScene)
    │   ├── canvas_view.py      # FsmCanvasView (QGraphicsView, pan/zoom)
    │   ├── node_item.py        # StateNodeItem (QGraphicsItem)
    │   └── edge_item.py        # TransitionEdgeItem (QGraphicsPathItem)
    ├── editors/                # 비-캔버스 에디터
    │   ├── __init__.py
    │   └── decl_skill_editor.py    # DeclarativeSkill 폼 에디터 (A단계: placeholder)
    └── panels/                 # 도킹 패널
        ├── __init__.py
        ├── tree_panel.py       # ProjectTreePanel (QTreeView)
        ├── property_panel.py   # PropertyPanel (선택한 노드/전이 속성 편집)
        └── history_panel.py    # HistoryPanel (커맨드 이력)
```

### 의존 방향

```
view/canvas, view/panels, view/editors
              ↓
        view/viewmodel  ←→  view/commands
              ↓
        model/ (읽기 전용 참조, 수정 없음)
```

- `view/` → `model/` 단방향 의존
- `model/`은 `view/`를 전혀 모름
- `commands`는 `viewmodel`을 통해서만 모델에 접근

---

## 2. Command 패턴

### 기반 클래스

```python
class Command(ABC):
    @property
    @abstractmethod
    def description(self) -> str:
        """Undo/Redo 메뉴 및 히스토리 패널에 표시될 설명."""

    @abstractmethod
    def execute(self) -> None: ...

    @abstractmethod
    def undo(self) -> None: ...


class MacroCommand(Command):
    """여러 커맨드를 하나의 Undo 단위로 묶음."""
    children: list[Command]
    _description: str

    def execute(self) -> None:
        for cmd in self.children:
            cmd.execute()

    def undo(self) -> None:
        for cmd in reversed(self.children):
            cmd.undo()
```

### CommandStack

```python
class CommandStack:
    undo_stack: list[Command]
    redo_stack: list[Command]
    changed: Signal              # Qt 시그널 — 히스토리 패널 갱신 트리거

    def execute(self, cmd: Command) -> None:
        cmd.execute()
        self.undo_stack.append(cmd)
        self.redo_stack.clear()  # 새 동작 이후 redo 무효화
        self.changed.emit()

    def undo(self) -> None: ...
    def redo(self) -> None: ...
    def can_undo(self) -> bool: ...
    def can_redo(self) -> bool: ...

    @property
    def history(self) -> list[Command]: ...

    @property
    def current_index(self) -> int: ...

    def goto(self, index: int) -> None:
        """히스토리 특정 지점으로 점프."""
```

### A단계 구체 커맨드 (6개)

| 커맨드 | execute | undo |
|--------|---------|------|
| `CreateStateCmd` | ViewModel에 SimpleState 추가 + 노드 생성 | 제거 |
| `DeleteStateCmd` | 호출 측에서 연결 전이 DeleteTransitionCmd + DeleteStateCmd를 MacroCommand로 조립하여 실행 | 상태 + 전이 복원 |
| `MoveStateCmd` | 노드 좌표 변경 (old_pos 저장) | old_pos 복원 |
| `RenameStateCmd` | 이름 변경 (old_name 저장) | old_name 복원 |
| `CreateTransitionCmd` | 두 상태 간 전이 추가 | 제거 |
| `DeleteTransitionCmd` | 전이 제거 (전체 상태 스냅샷 저장) | 복원 |

### 드래그 병합

노드 드래그 중 매 프레임 커맨드를 쌓지 않는다:
- 드래그 시작 시 `old_pos` 기록
- 드래그 종료 시 `MoveStateCmd(state_vm, old_pos, new_pos)` 한 번만 실행
- 드래그 중에는 ViewModel 좌표를 직접 갱신 (커맨드 스택 미경유)

---

## 3. ViewModel 레이어

### StateViewModel / TransitionViewModel

```python
@dataclass
class StateViewModel:
    model: SimpleState
    x: float = 0.0
    y: float = 0.0
    width: float = 140.0
    height: float = 60.0
    selected: bool = False

@dataclass
class TransitionViewModel:
    model: Transition
    source_vm: StateViewModel
    target_vm: StateViewModel
    selected: bool = False
```

### ProjectViewModel

```python
class ProjectViewModel:
    """전체 편집 세션의 상태를 관리. 단일 진실 공급원."""
    state_vms: list[StateViewModel]
    transition_vms: list[TransitionViewModel]
    command_stack: CommandStack

    def execute(self, cmd: Command) -> None:
        self.command_stack.execute(cmd)
        self.notify()

    def get_state_vm(self, name: str) -> StateViewModel | None: ...
    def get_transitions_for(self, state_vm: StateViewModel) -> list[TransitionViewModel]: ...

    # 옵저버
    def add_listener(self, callback: Callable) -> None: ...
    def notify(self) -> None: ...
```

- `ProjectViewModel`이 `CommandStack`을 소유
- 옵저버 패턴으로 캔버스/패널에 변경 통지 (Qt 시그널 연동)
- 직렬화 추가 시 `ProjectViewModel` → JSON 변환만 구현하면 됨

---

## 4. 메인 윈도우 레이아웃

QDockWidget 기반 자유 배치. 기본값은 3-패널 클래식 + 히스토리.

```
┌──────────┬──────────────────────────────┬───────────┐
│ 트리뷰    │ [Skill: init ✕] [Skill: x ✕] │ 프로퍼티   │
│          │  ┌─────────────────────────┐  │           │
│          │  │                         │  │           │
│          │  │   캔버스 or 폼 에디터     │  │           │
│          │  │                         │  │           │
├──────────┤  └─────────────────────────┘  │           │
│ 히스토리  │                              │           │
│ (접힘)    │                              │           │
└──────────┴──────────────────────────────┴───────────┘
```

| 패널 | 위치 (기본값) | 위젯 | 역할 |
|------|-------------|------|------|
| ProjectTreePanel | 좌측 독 | QTreeView | 프로젝트 구조 탐색 |
| FsmCanvasView | 중앙 QTabWidget | QGraphicsView | 노드 배치/연결 |
| PropertyPanel | 우측 독 | 동적 폼 | 선택한 요소 속성 편집 |
| HistoryPanel | 좌측 하단 독 | QListWidget | 커맨드 이력 + goto |

상단에 메뉴바 (File, Edit, View, Help), 하단에 상태바 (States/Transitions 수, Zoom).

---

## 5. 탭 기반 중앙 편집 영역

중앙은 QTabWidget. 트리에서 컴포넌트 더블클릭 시 타입에 맞는 에디터 탭이 열림.

| 컴포넌트 타입 | 에디터 탭 | A단계 상태 |
|-------------|----------|-----------|
| ProceduralSkill | 캔버스 탭 (FsmCanvasView) | 동작 |
| AgentDefinition | 캔버스 탭 (FsmCanvasView) | 동작 |
| DeclarativeSkill | 폼 탭 (DeclSkillEditor) | placeholder |

- 같은 컴포넌트 재클릭 시 기존 탭으로 포커스
- 탭 닫기 가능 (✕ 버튼)
- 프로퍼티 패널은 현재 활성 탭 + 선택된 요소에 따라 내용 변경

---

## 6. 프로젝트 트리 구조

### 기본 트리 구조

```
📁 MyPlugin
├── 📁 Skills
│   ├── 🔧 init (Procedural)       — 초록
│   ├── 🔧 cleanup (Procedural)    — 초록
│   └── 📄 rules (Declarative)     — 노랑
└── 📁 Agents
    └── 🤖 worker                  — 빨강
```

- Skills/, Agents/ 폴더는 프로젝트 생성 시 자동 생성
- 아이콘 + 컬러로 스킬 유스케이스 구분 (Procedural=초록, Declarative=노랑, Agent=빨강)

### 필터 토글

트리 상단에 `[Procedural] [Declarative]` 토글 버튼.
- 기본값: 둘 다 활성 (전체 표시)
- 토글 OFF 시 해당 유형 숨김
- 아이콘/컬러 구분 + 필터 조합 (D 방식)

---

## 7. 캔버스 인터랙션

### 노드 생성
- 캔버스 빈 영역 우클릭 → 컨텍스트 메뉴 → "상태 추가"
- 클릭 좌표에 새 SimpleState 노드 배치
- `CreateStateCmd` 실행

### 전이 생성
- 노드 가장자리에서 드래그 시작 → 다른 노드 위에서 드롭
- 드래그 중 임시 화살표 표시 (rubberband)
- 드롭 시 `CreateTransitionCmd` 실행

### 선택 / 이동
- 노드 클릭 → 선택 (프로퍼티 패널 갱신)
- 노드 드래그 → 이동 (드롭 시 `MoveStateCmd`)
- Ctrl+클릭 → 다중 선택
- 빈 영역 클릭 → 선택 해제

### 삭제
- 선택 후 Delete 키 또는 우클릭 → "삭제"
- 상태 삭제 시 연결된 전이도 함께 삭제 (`MacroCommand`)

### 캔버스 조작
- 마우스 휠 → 줌
- 중간 버튼 드래그 또는 Alt+드래그 → 패닝

---

## 8. 제약 사항

- **model/ 불변:** 기존 코어 코드 수정 없음. view/에서 읽기 전용 참조만.
- **A단계 범위:** SimpleState + Transition만. CompositeState, ParallelState, PseudoState는 B/C 단계.
- **직렬화 미포함:** 인메모리 전용. 직렬화 추가 가능한 구조만 확보 (ProjectViewModel 기반).
- **DeclarativeSkill 에디터:** A단계에서는 placeholder. 탭 인프라만 구축.

## 9. 의존성

```toml
# pyproject.toml 추가
dependencies = ["PyQt6>=6.6"]
```
