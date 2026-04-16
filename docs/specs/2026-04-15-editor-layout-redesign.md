# Editor Layout Redesign — ComponentEditor 기반 재배치

## 목표

SkillEditor / AgentEditor의 레이아웃 낭비를 제거하고, 재사용 가능한 단일 복합 위젯(`ComponentEditor`)으로 통합한다.

## 현재 문제

- QStackedWidget으로 transfer_on / agent_call / content를 전환 → 한 번에 하나만 보임
- 3컬럼 고정폭(170+100+expand) → 낭비
- SkillEditor와 AgentEditor Content 탭이 거의 동일한 코드를 중복 구현

## 설계

### 재사용 위젯 (기존, 변경 없음)

| 위젯 | 위치 | 역할 |
|------|------|------|
| `SectionTree` | body_editor.py | 섹션 트리 네비게이션 |
| `_FrontmatterPanel` | skill_editor.py | name/description/선택 필드 폼 |
| `BreadcrumbNav` | body_editor.py | 경로 칩 네비게이션 |
| `SectionContentPanel` | body_editor.py | 타이틀 + 본문 편집 |
| `_TransferOnPanel` | skill_editor.py | EventDef 카드 목록 |
| `_ContractButtons` | skill_editor.py | 잠금 계약 섹션 버튼 |
| `VariablePopup` | body_editor.py | 변수 삽입 팝업 |

### 새 위젯: `ComponentEditor`

**파일:** `daedalus/view/editors/component_editor.py`

```
ComponentEditor(component, right_widgets=[], on_notify_fn=None)

QSplitter(Horizontal)
├─ QSplitter(Vertical, min 120)
│  ├─ SectionTree (min 80)
│  └─ _FrontmatterPanel (min 80)
│
├─ QWidget (stretch=1)
│  ├─ BreadcrumbNav
│  └─ SectionContentPanel
│
└─ QSplitter(Vertical, min 120)  ← right_widgets가 있을 때만
   └─ *right_widgets
```

**원칙:**
- 모든 칸 경계는 QSplitter (사용자 조절 가능)
- maximum 없음, minimum만 지정
- right_widgets가 빈 리스트이면 우측 스플리터 생략 → 2컬럼

### 호출부별 구성

```python
# ProceduralSkill (메인, show_call_agents=True)
ComponentEditor(skill, right_widgets=[
    _TransferOnPanel(skill.transfer_on),
    _TransferOnPanel(skill.call_agents, default_color="#8a4a4a", multiline_desc=True),
])

# ProceduralSkill (서브그래프, show_call_agents=False)
ComponentEditor(skill, right_widgets=[
    _TransferOnPanel(skill.transfer_on),
])

# TransferSkill / ReferenceSkill / DeclarativeSkill
ComponentEditor(skill)  # 우측 없음 → 2컬럼

# AgentDefinition (Content 탭)
ComponentEditor(agent, right_widgets=[
    _ContractButtons("🔒 입력 프로시저", agent.caller_contracts),
])
```

### SkillEditor 변경

기존 SkillEditor는 ComponentEditor를 생성하고 right_widgets를 전달하는 얇은 래퍼로 변경.

**삭제 대상:**
- QStackedWidget 전환 로직 (`_on_transfer_on_selected`, `_on_call_agents_selected`)
- 스택 인덱스 관리 코드
- `⇄ TransferOn` / `🤖 AgentCall` 버튼

### AgentEditor 변경

`_build_content_tab`에서 직접 위젯을 조립하던 코드를 ComponentEditor 호출로 교체.

**삭제 대상:**
- Content 탭의 수동 QSplitter 구성 코드
- `_on_tree_selected`, `_on_breadcrumb_selected` 등 중복 시그널 핸들러

### 시그널 흐름

```
SectionTree.section_selected ──→ ComponentEditor._on_tree_selected
                                  ├─ BreadcrumbNav.set_current
                                  └─ SectionContentPanel.show_section

BreadcrumbNav.section_selected ─→ ComponentEditor._on_breadcrumb_selected
                                  ├─ SectionTree.select_section
                                  └─ SectionContentPanel.show_section

_ContractButtons.section_clicked → ComponentEditor._on_contract_clicked
                                  └─ SectionContentPanel.show_section(title_locked=True)

SectionContentPanel.content_changed → ComponentEditor._on_model_changed
_TransferOnPanel.transfer_on_changed → ComponentEditor._on_model_changed
_FrontmatterPanel.changed → ComponentEditor._on_model_changed
```

### minimum 값

| 위젯 | minimum |
|------|---------|
| 좌측 스플리터 전체 | 120px |
| SectionTree | 80px height |
| _FrontmatterPanel | 80px height |
| 중앙 (content) | 200px width |
| 우측 스플리터 전체 | 120px width |
| 우측 개별 위젯 | 60px height |
