# Frontmatter Field Matrix Design — Enum 기반 스킬 프론트매터 관리

## 목표

스킬 프론트매터 필드를 전역 매트릭스로 한 번만 정의하고, UI/컴파일러/검증에서 재사용한다. 기존 `FIELD_REGISTRY` + `FieldSpec`을 `SKILL_FIELD_MATRIX` + `FieldRule`로 교체.

## 핵심 개념

### FieldVisibility (4단계)

| 값 | UI | 컴파일 | 설명 |
|---|---|---|---|
| `REQUIRED` | 항상 표시, 입력 필요 | 모델에서 읽어 출력 | name, description, model |
| `OPTIONAL` | 표시, 체크박스 활성/비활성 | 활성 시만 출력 | effort, hooks, context 등 |
| `DEFAULT` | 미표시 | 필드 생략 (Claude Code 기본값) | 해당 스킬 타입에서 불필요한 필드 |
| `FIXED` | 미표시 | 필드 + 고정값 출력 | transfer의 disable-model=true 등 |

### SkillField (14개)

```
NAME, DESCRIPTION, WHEN_TO_USE, ARGUMENT_HINT,
MODEL, EFFORT, ALLOWED_TOOLS, CONTEXT, AGENT, SHELL, PATHS,
HOOKS, DISABLE_MODEL, USER_INVOCABLE
```

### FieldRule

```python
@dataclass
class FieldRule:
    visibility: FieldVisibility
    widget: type[QWidget]          # 위젯 클래스 (인스턴스 아님)
    fixed_value: Any = None        # FIXED일 때 컴파일 출력값
    default_value: Any = None      # REQUIRED일 때 초기값
```

- widget 클래스가 자신의 choices/preset_path 등을 캡슐화
- FieldRule은 visibility + widget + 값만 관리

## 위젯 클래스

### 기존 (PyQt6)
- `QCheckBox` — bool 필드 (disable_model, user_invocable)
- `QLineEdit` — 단일 문자열 (when_to_use, argument_hint, paths)

### 신규 생성

| 클래스 | 부모 | 용도 | 내부 동작 |
|--------|------|------|----------|
| `ModelComboBox` | QComboBox | model 선택 | sonnet/opus/haiku 고정 항목 |
| `EffortComboBox` | QComboBox | effort 선택 | low/medium/high/max 고정 항목 |
| `ContextComboBox` | QComboBox | context 선택 | inline/fork 고정 항목 |
| `ShellComboBox` | QComboBox | shell 선택 | bash/powershell 고정 항목 |
| `TagInput` | QWidget | list[str] 편집 | 텍스트+Enter 태그 추가, x 제거, 자동완성 |
| `HookPresetPicker` | QWidget | hooks 선택 | .claude/hooks/ 스캔 → 체크리스트 |
| `McpPresetPicker` | QWidget | mcpServers 선택 | .claude/mcp/ 스캔 → 체크리스트 |

### 파일 위치

```
daedalus/view/widgets/
├── model_combo.py        # ModelComboBox
├── effort_combo.py       # EffortComboBox
├── context_combo.py      # ContextComboBox
├── shell_combo.py        # ShellComboBox
├── tag_input.py          # TagInput
├── hook_preset_picker.py # HookPresetPicker
└── mcp_preset_picker.py  # McpPresetPicker
```

콤보박스 4개는 단순하므로 하나의 파일 `combo_widgets.py`로 통합 가능.

## 전역 매트릭스

```python
# daedalus/model/plugin/field_matrix.py

SKILL_FIELD_MATRIX: dict[str, dict[SkillField, FieldRule]] = { ... }
```

### 스킬 매트릭스

| 필드 | Procedural | Declarative | Transfer | Reference | 로컬 Procedural | 로컬 Transfer |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| NAME | 필수 | 필수 | 필수 | 필수 | 필수 | 필수 |
| DESCRIPTION | 필수 | 필수 | 필수 | 필수 | 필수 | 필수 |
| WHEN_TO_USE | 옵션 | 옵션 | 기본값 | 기본값 | 기본값 | 기본값 |
| ARGUMENT_HINT | 옵션 | 옵션 | 기본값 | 기본값 | 기본값 | 기본값 |
| MODEL | 필수(sonnet) | 필수(sonnet) | 필수(sonnet) | 필수(sonnet) | 필수(sonnet) | 필수(sonnet) |
| EFFORT | 옵션 | 옵션 | 옵션 | 옵션 | 기본값 | 기본값 |
| ALLOWED_TOOLS | 옵션 | 옵션 | 옵션 | 기본값 | 옵션 | 옵션 |
| CONTEXT | 옵션 | 기본값 | 옵션 | 기본값 | 고정(fork) | 고정(fork) |
| AGENT | 옵션 | 기본값 | 기본값 | 기본값 | 기본값 | 기본값 |
| SHELL | 옵션 | 기본값 | 옵션 | 기본값 | 옵션 | 옵션 |
| PATHS | 옵션 | 옵션 | 기본값 | 기본값 | 기본값 | 기본값 |
| HOOKS | 옵션 | 옵션 | 옵션 | 기본값 | 옵션 | 옵션 |
| DISABLE_MODEL | 옵션 | 옵션 | 고정(true) | 기본값 | 고정(true) | 고정(true) |
| USER_INVOCABLE | 옵션 | 옵션 | 고정(false) | 고정(false) | 고정(false) | 고정(false) |

## 모델 변경

### 신규 파일
- `daedalus/model/plugin/field_matrix.py` — FieldRule, SkillField, FieldVisibility, SKILL_FIELD_MATRIX

### enums.py 추가
- `FieldVisibility` enum
- `SkillField` enum

### 삭제 대상
- `config.py`의 `FieldSpec` 클래스
- `config.py`의 `FIELD_REGISTRY` dict

### 수정 대상
- `skill_editor.py`의 `_FrontmatterPanel` — SKILL_FIELD_MATRIX에서 REQUIRED/OPTIONAL만 읽어 위젯 생성
- `_OptionalRow` — OPTIONAL 필드용 (기존과 동일한 역할)

## _FrontmatterPanel 동작

```python
def __init__(self, component, skill_kind: str):
    matrix = SKILL_FIELD_MATRIX[skill_kind]
    for field, rule in matrix.items():
        if field in (SkillField.NAME, SkillField.DESCRIPTION):
            continue  # 별도 처리 (필수 텍스트)
        if rule.visibility == FieldVisibility.REQUIRED:
            widget = rule.widget()  # 위젯 인스턴스 생성
            # default_value 설정
            lay.addWidget(QLabel(field.value))
            lay.addWidget(widget)
        elif rule.visibility == FieldVisibility.OPTIONAL:
            widget = rule.widget()
            lay.addWidget(_OptionalRow(field.value, widget))
        # DEFAULT, FIXED는 UI에 표시하지 않음
```

## 사용처 요약

| 소비자 | 읽는 것 | 동작 |
|--------|---------|------|
| `_FrontmatterPanel` | visibility, widget | REQUIRED/OPTIONAL → 위젯 생성 |
| 컴파일러 (미구현) | visibility, fixed_value | REQUIRED/OPTIONAL → 모델 읽기, FIXED → 고정값, DEFAULT → 생략 |
| Validator | visibility | REQUIRED 필드 비어있으면 에러 |

## 누락 모델 필드 추가

- `when_to_use: str = ""` → PluginComponent 또는 Skill에 추가
