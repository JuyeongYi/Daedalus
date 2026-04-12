# Skill Editor & Node Redesign 스펙

## 개요

`SkillSection` enum 기반의 고정 섹션 구조를 제거하고, 스킬/에이전트가 각자의 섹션과 출력 이벤트를 자유롭게 정의하는 구조로 전환한다. TransferOn 섹션의 이벤트(색상 포함)가 캔버스 노드 출력 포트에 실시간 반영된다.

---

## 1. 모델 레이어

### 1-1. `daedalus/model/fsm/section.py` (기존 SkillSection enum 교체)

```python
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class Section:
    """자유 콘텐츠 섹션 (H1–H6 계층)."""
    title: str
    content: str = ""
    children: list[Section] = field(default_factory=list)

@dataclass
class EventDef:
    """TransferOn 출력 이벤트 정의."""
    name: str
    color: str = "#4488ff"   # 노드 출력 포트 색상
    description: str = ""
```

- `Section.children` 깊이 제한: H6(depth=6)까지 허용
- `EventDef.color`: 16진수 CSS 색상 문자열
- `SkillSection` enum 완전 제거

### 1-2. `ProceduralSkill` 변경 (`daedalus/model/plugin/skill.py`)

```python
# 추가
sections: list[Section] = field(default_factory=list)
transfer_on: list[EventDef] = field(default_factory=lambda: [EventDef("done")])

# 제거
# output_events: list[str]

# 하위 호환 프로퍼티 (StateNodeItem 등에서 계속 사용)
@property
def output_events(self) -> list[str]:
    return [e.name for e in self.transfer_on]
```

### 1-3. `AgentDefinition` 변경 (`daedalus/model/plugin/agent.py`)

`ProceduralSkill`과 동일하게 `sections`, `transfer_on` 추가, `output_events` 제거 후 프로퍼티로 대체.

### 1-4. `DeclarativeSkill` 변경 (`daedalus/model/plugin/skill.py`)

`sections: list[Section]` 만 추가. `transfer_on` 없음 (노드로 배치되지 않음, 출력 이벤트 불필요).

### 1-4. Validator 신규 규칙 (`daedalus/model/validation.py`)

| 규칙 | 설명 |
|------|------|
| `transfer_on_not_empty` | `transfer_on`이 빈 리스트이면 `ValidationError` |

---

## 2. 뷰 레이어

### 2-1. SkillEditor 전체 레이아웃

3개 패널 수평 분할:

```
┌─────────────────┬─────────────────┬────────────────────────────┐
│  Frontmatter    │  Tree Sidebar   │  Content Panel             │
│  (170px, 고정)  │  (145px, 고정)  │  (나머지, 확장)            │
└─────────────────┴─────────────────┴────────────────────────────┘
```

### 2-2. Frontmatter 패널

- **레이아웃**: 상단 정렬 (`QVBoxLayout` + `addStretch()` at bottom)
- **필수 필드** (항상 표시, 체크박스 없음):
  - `name` — `QLineEdit`
  - `description` — `QTextEdit` (2줄)
- **선택 필드** (각각 `QCheckBox` + 위젯 쌍):
  - 체크 해제 시: 위젯 비활성화(`setEnabled(False)`) + `opacity: 0.4`
  - 체크 시: 위젯 활성화, 베이크(컴파일) 시 포함
  - 필드 목록: `model`, `effort`, `allowed-tools`, `context`, `paths`, `shell`, `disable-model-invocation`, `user-invocable`, `argument-hint`

### 2-3. Tree Sidebar

- `QTreeWidget` (한 열, 체크박스 없음)
- 각 항목: 타이틀 + H레벨 뱃지 (H1–H6)
- **섹션 추가**: 트리 하단 `+ 섹션 추가` 버튼
  - 선택 항목 없음 → 최상위 H1 추가
  - 선택 항목 있음 → 선택 항목과 같은 레벨(형제) 추가
- **하위 섹션 추가**: 콘텐츠 패널 툴바의 `+ 하위 섹션` 버튼 → 현재 선택 섹션의 직계 자식 추가 (현재 레벨이 H6이면 버튼 비활성화)
- **삭제**: 콘텐츠 패널 툴바의 `삭제` 버튼
- **TransferOn**: 항상 트리 최하단 고정, 삭제 불가. 선택 시 Content Panel 대신 TransferOn 패널 표시. `DeclarativeSkill`은 TransferOn 없음

### 2-4. Content Panel (일반 섹션)

```
[브레드크럼]  Persona › Role          [+ 하위 섹션]  [삭제]
─────────────────────────────────────────────────────────
[인라인 타이틀 편집: QLineEdit, 배경 투명]
─────────────────────────────────────────────────────────
[QTextEdit, 자유 텍스트]
```

### 2-5. TransferOn 패널 (TransferOn 선택 시)

이벤트 카드 목록:

```
출력 이벤트 정의 — 노드 포트로 자동 반영
┌──────────────────────────────────────────┐
│ ● done          [이름 QLineEdit]         │  ← ●: 색상 원, 클릭 시 팔레트
│ 설명 QLineEdit (선택, placeholder 표시)  │
│                                      [✕] │  ← 마지막 이벤트는 ✕ 비활성화
└──────────────────────────────────────────┘
┌──────────────────────────────────────────┐
│ ● error         ...                      │
└──────────────────────────────────────────┘
[+ 이벤트 추가]
```

색상 팔레트: 8색 프리셋 (`QColorDialog` 없이 소형 팝업 위젯)
- `#4488ff` (blue), `#cc3333` (red), `#cc8800` (orange), `#44aa44` (green)
- `#aa44cc` (purple), `#ccaa00` (yellow), `#44aacc` (cyan), `#888888` (gray)

---

## 3. 노드 출력 포트 색상 반영

### `StateNodeItem` 변경 (`daedalus/view/canvas/node_item.py`)

`_output_events()` → `_event_defs()` 로 교체:

```python
def _event_defs(self) -> list[EventDef]:
    ref = self._state_vm.model.skill_ref
    if ref is None:
        return []
    return list(ref.transfer_on)
```

포트 렌더링 시 `EventDef.color` 사용:

```python
# 기존: 하드코딩된 색상 분기
# 변경: event_def.color 직접 사용
port_color = QColor(event_def.color)
```

### 리액티비티 체인

```
SkillEditor (TransferOn 패널)
  → transfer_on 변경
  → on_notify_fn() = project_vm.notify()
  → FsmScene._rebuild()
  → StateNodeItem.update_from_model()
  → _event_defs() 재호출 → 포트 갱신
```

추가 배선 불필요. 기존 notify 체인이 그대로 동작.

---

## 4. 테스트 계획

| 테스트 | 내용 |
|--------|------|
| `test_section_tree_depth` | H6 초과 자식 추가 시 UI 버튼 비활성화 확인 |
| `test_event_def_output_events_property` | `transfer_on` → `output_events` 프로퍼티 파생 |
| `test_transfer_on_not_empty_validator` | 빈 `transfer_on` → `ValidationError` |
| `test_event_color_reflects_on_port` | `EventDef.color` 변경 → `StateNodeItem` 포트 색상 변경 |
| `test_optional_frontmatter_checkbox` | 체크 해제 필드는 베이크 대상에서 제외 |

---

## 5. 변수 삽입 기능

### 5-1. 변수 파일 계층

우선순위 낮음 → 높음 순으로 병합. 이름 충돌 시 높은 우선순위가 덮어씀.

| 레벨 | 경로 | 설명 |
|------|------|------|
| 기본 제공 | 하드코딩 | Claude Code 공식 변수 5종 |
| 글로벌 | `~/.daedalus/variables.yaml` | 모든 프로젝트 공유 |
| 프로젝트 | `.daedalus/variables.yaml` | 현재 프로젝트 전용 |

`variables.yaml` 형식:

```yaml
- name: "$PROJECT_NAME"
  description: "현재 프로젝트 이름"
- name: "$CUSTOM_VAR"
  description: "사용자 정의 변수 설명"
```

파일이 없으면 해당 레벨은 빈 목록으로 처리. 최초 실행 시 글로벌 파일을 기본 값으로 자동 생성하지 않음 (사용자가 필요할 때 직접 생성).

**기본 제공 변수 (5종):**

| 변수 | 설명 |
|------|------|
| `$ARGUMENTS` | 스킬 호출 시 전달된 전체 인수 |
| `$ARGUMENTS[0]` | 첫 번째 인수 (예시; N은 임의 숫자) |
| `$N` | `$ARGUMENTS[N]` 단축형 |
| `${CLAUDE_SESSION_ID}` | 현재 세션 ID |
| `${CLAUDE_SKILL_DIR}` | 스킬 SKILL.md 파일의 디렉토리 경로 |

### 5-2. UI — 변수 삽입 팝업

Content Panel 툴바에 `{ } 변수 삽입` 버튼 추가 (기존 `+ 하위 섹션`, `삭제` 버튼 왼쪽):

```
[{ } 변수 삽입]  [+ 하위 섹션]  [삭제]
```

버튼 클릭 시 툴바 아래에 소형 팝업 위젯(`QFrame`, 비모달):

```
┌─────────────────────────────────────┐
│ 기본 제공                            │
│  $ARGUMENTS        스킬 호출 인수    │
│  $ARGUMENTS[0]     첫 번째 인수     │
│  ${CLAUDE_SESSION_ID}  세션 ID      │
│  ${CLAUDE_SKILL_DIR}   스킬 디렉토리 │
├─────────────────────────────────────┤
│ 글로벌 (~/.daedalus/variables.yaml) │
│  $PROJECT_NAME     프로젝트 이름     │
├─────────────────────────────────────┤
│ 프로젝트 (.daedalus/variables.yaml) │
│  $MY_VAR           내 커스텀 변수   │
└─────────────────────────────────────┘
```

- 항목 클릭 → `QTextEdit.insertPlainText(variable.name)` (커서 위치 삽입)
- 팝업 외부 클릭 시 닫힘
- 파일이 없는 레벨의 섹션은 표시하지 않음

### 5-3. 변수 파일 로딩

`VariableLoader` 유틸리티 (새 파일 `daedalus/view/editors/variable_loader.py`):

```python
def load_variables(project_dir: Path | None = None) -> list[VariableEntry]:
    """기본 제공 + 글로벌 + 프로젝트 변수를 병합해 반환."""
```

`VariableEntry(name: str, description: str, source: Literal["builtin", "global", "project"])`

- `SkillEditor` 초기화 시 `load_variables(project_dir)` 호출
- `variables.yaml` 파일 변경 감지는 스코프 외 (재시작 필요)

---

## 6. 테스트 계획

| 테스트 | 내용 |
|--------|------|
| `test_section_tree_depth` | H6 초과 자식 추가 시 UI 버튼 비활성화 확인 |
| `test_event_def_output_events_property` | `transfer_on` → `output_events` 프로퍼티 파생 |
| `test_transfer_on_not_empty_validator` | 빈 `transfer_on` → `ValidationError` |
| `test_event_color_reflects_on_port` | `EventDef.color` 변경 → `StateNodeItem` 포트 색상 변경 |
| `test_optional_frontmatter_checkbox` | 체크 해제 필드는 베이크 대상에서 제외 |
| `test_variable_loader_merge` | 글로벌+프로젝트 yaml 병합, 이름 충돌 시 프로젝트 우선 |
| `test_variable_loader_missing_file` | yaml 파일 없을 때 빈 목록 반환 (예외 없음) |

---

## 7. 스코프 외

- **베이크(컴파일러)**: `sections`/`transfer_on` → SKILL.md 파일 생성 (`compiler/` 미구현)
- **색상 커스텀 입력**: 프리셋 8색 외 임의 색상 입력 (추후)
- **섹션 드래그 재정렬**: 트리 항목 드래그로 순서 변경 (추후)
- **variables.yaml 변경 감지**: 파일 수정 시 자동 리로드 (추후)
