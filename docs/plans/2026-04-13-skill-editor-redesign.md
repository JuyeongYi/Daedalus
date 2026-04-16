# Skill Editor & Node Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SkillSection enum을 제거하고 자유 H1-H6 트리 섹션 + TransferOn 이벤트 카드 구조로 전환하며, EventDef.color를 캔버스 노드 포트에 반영하고 변수 삽입 팝업을 추가한다.

**Architecture:** 모델 레이어에서 `section.py`를 `Section`+`EventDef` 데이터클래스로 교체하고, `ProceduralSkill`/`AgentDefinition`에 `sections`+`transfer_on` 필드를 추가(기존 `output_events` 필드는 프로퍼티로 대체). 뷰 레이어에서 `skill_editor.py`를 3-패널 레이아웃(Frontmatter | TreeSidebar | ContentPanel)으로 전면 재작성하고, `variable_loader.py`로 3-계층 변수를 제공한다. `node_item.py`는 `EventDef.color`를 읽어 포트 색상에 직접 반영한다.

**Tech Stack:** Python 3.12, PyQt6, dataclasses, pyyaml

---

## 파일 구조

### 생성
| 파일 | 역할 |
|------|------|
| `daedalus/view/editors/variable_loader.py` | 3계층 변수 로딩 (builtin + global + project) |
| `tests/view/editors/__init__.py` | 테스트 패키지 init |
| `tests/view/editors/test_variable_loader.py` | VariableLoader 단위 테스트 |
| `tests/view/editors/test_skill_editor.py` | SkillEditor 위젯 스모크 테스트 |

### 수정
| 파일 | 변경 내용 |
|------|---------|
| `daedalus/model/fsm/section.py` | SkillSection enum → Section + EventDef 데이터클래스 |
| `tests/model/fsm/test_section.py` | SkillSection 테스트 제거 → Section/EventDef 테스트로 교체 |
| `daedalus/model/plugin/skill.py` | sections + transfer_on 필드 추가, output_events를 프로퍼티로 교체 |
| `tests/model/plugin/test_skill.py` | output_events 생성자 인수 테스트 업데이트 |
| `daedalus/model/plugin/agent.py` | skill.py와 동일 |
| `tests/model/plugin/test_agent.py` | skill.py 동일 |
| `daedalus/model/validation.py` | transfer_on_not_empty 검증 규칙 추가 |
| `tests/model/test_validation.py` | 새 규칙 테스트 추가 |
| `pyproject.toml` | pyyaml 의존성 추가 |
| `daedalus/view/editors/skill_editor.py` | 전면 재작성 (3-패널 레이아웃) |
| `daedalus/view/canvas/node_item.py` | _event_defs() + EventDef.color 반영 |

---

### Task 1: section.py 교체 — Section + EventDef 데이터클래스

**Files:**
- Modify: `daedalus/model/fsm/section.py`
- Modify: `tests/model/fsm/test_section.py`

- [ ] **Step 1: test_section.py를 새 테스트로 교체 (기존 SkillSection 테스트 전체 삭제)**

```python
# tests/model/fsm/test_section.py
from daedalus.model.fsm.section import Section, EventDef


def test_section_default_fields():
    s = Section(title="Persona")
    assert s.title == "Persona"
    assert s.content == ""
    assert s.children == []


def test_section_with_content():
    s = Section(title="Role", content="You are a writer.")
    assert s.content == "You are a writer."


def test_section_with_children():
    child = Section(title="Background")
    parent = Section(title="Persona", children=[child])
    assert len(parent.children) == 1
    assert parent.children[0].title == "Background"


def test_section_nested_h6():
    """H1 → H2 → H3 → H4 → H5 → H6 깊이 허용."""
    s = Section("H1", children=[
        Section("H2", children=[
            Section("H3", children=[
                Section("H4", children=[
                    Section("H5", children=[
                        Section("H6")
                    ])
                ])
            ])
        ])
    ])
    h6 = s.children[0].children[0].children[0].children[0].children[0]
    assert h6.title == "H6"
    assert h6.children == []


def test_event_def_defaults():
    e = EventDef(name="done")
    assert e.name == "done"
    assert e.color == "#4488ff"
    assert e.description == ""


def test_event_def_custom():
    e = EventDef(name="error", color="#cc3333", description="오류 발생")
    assert e.color == "#cc3333"
    assert e.description == "오류 발생"
```

- [ ] **Step 2: 실패 확인**

```bash
python -m pytest tests/model/fsm/test_section.py -v
```
Expected: `ImportError: cannot import name 'Section' from 'daedalus.model.fsm.section'`

- [ ] **Step 3: section.py 교체**

```python
# daedalus/model/fsm/section.py
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
    color: str = "#4488ff"   # 노드 출력 포트 색상 (CSS hex)
    description: str = ""
```

- [ ] **Step 4: 통과 확인**

```bash
python -m pytest tests/model/fsm/test_section.py -v
```
Expected: 6개 PASS

- [ ] **Step 5: 커밋**

```bash
git add daedalus/model/fsm/section.py tests/model/fsm/test_section.py
git commit -m "feat: replace SkillSection enum with Section+EventDef dataclasses"
```

---

### Task 2: ProceduralSkill + DeclarativeSkill 업데이트

기존 `output_events: list[str]` 필드를 제거하고, `sections` + `transfer_on` 필드를 추가하며, `output_events`를 프로퍼티로 교체한다.

**Files:**
- Modify: `daedalus/model/plugin/skill.py`
- Modify: `tests/model/plugin/test_skill.py`

- [ ] **Step 1: test_skill.py에서 실패할 테스트 추가 + 깨질 테스트 업데이트**

기존 `test_procedural_skill_output_events_custom` (생성자에 `output_events=` 전달)을 아래로 교체한다.
`test_procedural_skill_output_events_default`는 그대로 유지한다 (프로퍼티가 동일 결과를 반환하면 통과함).

```python
# tests/model/plugin/test_skill.py 하단에 추가/교체할 내용
# (기존 test_procedural_skill_output_events_custom 삭제 후 아래로 교체)

from daedalus.model.fsm.section import Section, EventDef


def test_procedural_skill_sections_default():
    fsm = _make_fsm()
    skill = ProceduralSkill(fsm=fsm, name="S", description="d")
    assert skill.sections == []


def test_procedural_skill_transfer_on_default():
    fsm = _make_fsm()
    skill = ProceduralSkill(fsm=fsm, name="S", description="d")
    assert len(skill.transfer_on) == 1
    assert skill.transfer_on[0].name == "done"


def test_procedural_skill_output_events_via_property():
    """output_events는 transfer_on에서 파생된 읽기 전용 프로퍼티."""
    fsm = _make_fsm()
    skill = ProceduralSkill(
        fsm=fsm, name="S", description="d",
        transfer_on=[EventDef("done"), EventDef("error"), EventDef("retry")],
    )
    assert skill.output_events == ["done", "error", "retry"]


def test_declarative_skill_sections_default():
    skill = DeclarativeSkill(name="api-conventions", description="API 컨벤션")
    assert skill.sections == []
```

- [ ] **Step 2: 실패 확인**

```bash
python -m pytest tests/model/plugin/test_skill.py -v
```
Expected: `test_procedural_skill_sections_default` FAIL (AttributeError: 'ProceduralSkill' object has no attribute 'sections')

- [ ] **Step 3: skill.py 업데이트**

```python
# daedalus/model/plugin/skill.py
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field

from daedalus.model.fsm.section import EventDef, Section
from daedalus.model.plugin.base import PluginComponent, WorkflowComponent
from daedalus.model.plugin.config import DeclarativeSkillConfig, ProceduralSkillConfig


@dataclass
class Skill(PluginComponent, ABC):
    """스킬 베이스."""


@dataclass
class ProceduralSkill(Skill, WorkflowComponent):
    """절차형 = Skill + FSM.

    필드 순서 (dataclass MRO):
      fsm (required, WorkflowComponent)
      name, description (required, PluginComponent)
      config, sections, transfer_on (default)
    """
    config: ProceduralSkillConfig = field(default_factory=ProceduralSkillConfig)
    sections: list[Section] = field(default_factory=list)
    transfer_on: list[EventDef] = field(
        default_factory=lambda: [EventDef("done")]
    )

    @property
    def kind(self) -> str:
        return "procedural_skill"

    @property
    def output_events(self) -> list[str]:
        """transfer_on에서 파생된 읽기 전용 프로퍼티 (StateNodeItem 호환)."""
        return [e.name for e in self.transfer_on]


@dataclass
class DeclarativeSkill(Skill):
    """선언형 = Skill only. FSM 없음, transfer_on 없음."""
    content: str = ""
    sections: list[Section] = field(default_factory=list)
    config: DeclarativeSkillConfig = field(default_factory=DeclarativeSkillConfig)

    @property
    def kind(self) -> str:
        return "declarative_skill"
```

- [ ] **Step 4: 통과 확인**

```bash
python -m pytest tests/model/plugin/test_skill.py tests/model/test_validation.py -v
```
Expected: 전체 PASS (test_validation.py의 `_make_procedural` 헬퍼가 기본 인수로 ProceduralSkill 생성하므로 그대로 통과)

- [ ] **Step 5: 커밋**

```bash
git add daedalus/model/plugin/skill.py tests/model/plugin/test_skill.py
git commit -m "feat: add sections+transfer_on to ProceduralSkill/DeclarativeSkill, output_events as property"
```

---

### Task 3: AgentDefinition 업데이트

**Files:**
- Modify: `daedalus/model/plugin/agent.py`
- Modify: `tests/model/plugin/test_agent.py`

- [ ] **Step 1: test_agent.py에서 깨질 테스트 교체 + 새 테스트 추가**

기존 `test_agent_output_events_custom` 삭제 후 아래로 교체:

```python
# tests/model/plugin/test_agent.py 하단에 추가/교체

from daedalus.model.fsm.section import EventDef, Section


def test_agent_sections_default():
    fsm = _make_fsm()
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    assert agent.sections == []


def test_agent_transfer_on_default():
    fsm = _make_fsm()
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    assert len(agent.transfer_on) == 1
    assert agent.transfer_on[0].name == "done"


def test_agent_output_events_via_property():
    """output_events는 transfer_on에서 파생된 읽기 전용 프로퍼티."""
    fsm = _make_fsm()
    agent = AgentDefinition(
        fsm=fsm, name="A", description="d",
        transfer_on=[EventDef("done"), EventDef("failed")],
    )
    assert agent.output_events == ["done", "failed"]
```

- [ ] **Step 2: 실패 확인**

```bash
python -m pytest tests/model/plugin/test_agent.py -v
```
Expected: `test_agent_sections_default` FAIL

- [ ] **Step 3: agent.py 업데이트**

```python
# daedalus/model/plugin/agent.py
from __future__ import annotations

from dataclasses import dataclass, field

from daedalus.model.fsm.section import EventDef, Section
from daedalus.model.plugin.base import PluginComponent, WorkflowComponent
from daedalus.model.plugin.config import AgentConfig
from daedalus.model.plugin.policy import ExecutionPolicy


@dataclass
class AgentDefinition(PluginComponent, WorkflowComponent):
    """에이전트 = PluginComponent + FSM.

    필드 순서 (dataclass MRO):
      fsm (required, WorkflowComponent)
      name, description (required, PluginComponent)
      config, execution_policy, sections, transfer_on (default)
    """
    config: AgentConfig = field(default_factory=AgentConfig)
    execution_policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    sections: list[Section] = field(default_factory=list)
    transfer_on: list[EventDef] = field(
        default_factory=lambda: [EventDef("done")]
    )

    @property
    def kind(self) -> str:
        return "agent"

    @property
    def output_events(self) -> list[str]:
        """transfer_on에서 파생된 읽기 전용 프로퍼티 (StateNodeItem 호환)."""
        return [e.name for e in self.transfer_on]
```

- [ ] **Step 4: 전체 테스트 통과 확인**

```bash
python -m pytest tests/ -v
```
Expected: 전체 PASS (기존 102개 + 새 테스트)

- [ ] **Step 5: 커밋**

```bash
git add daedalus/model/plugin/agent.py tests/model/plugin/test_agent.py
git commit -m "feat: add sections+transfer_on to AgentDefinition, output_events as property"
```

---

### Task 4: transfer_on_not_empty 검증 규칙 추가

**Files:**
- Modify: `daedalus/model/validation.py`
- Modify: `tests/model/test_validation.py`

- [ ] **Step 1: test_validation.py 하단에 실패 테스트 추가**

```python
# tests/model/test_validation.py 하단에 추가

from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.fsm.section import EventDef


def _make_procedural_with_transfer_on(transfer_on: list) -> ProceduralSkill:
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    return ProceduralSkill(fsm=fsm, name="MySkill", description="d", transfer_on=transfer_on)


def test_transfer_on_not_empty_fails_when_empty():
    skill = _make_procedural_with_transfer_on([])
    state = SimpleState(name="node", skill_ref=skill)
    sm = _make_sm([state], [])
    errors = Validator.validate(sm)
    assert any(e.rule == "transfer_on_not_empty" for e in errors)


def test_transfer_on_not_empty_passes_when_has_events():
    skill = _make_procedural_with_transfer_on([EventDef("done")])
    state = SimpleState(name="node", skill_ref=skill)
    sm = _make_sm([state], [])
    errors = Validator.validate(sm)
    assert not any(e.rule == "transfer_on_not_empty" for e in errors)


def test_transfer_on_not_empty_ignores_declarative_skill():
    """DeclarativeSkill은 transfer_on 없음 → 규칙 적용 안 됨."""
    from daedalus.model.plugin.skill import DeclarativeSkill
    skill = DeclarativeSkill(name="knowledge", description="d")
    state = SimpleState(name="node", skill_ref=skill)
    sm = _make_sm([state], [])
    errors = Validator.validate(sm)
    assert not any(e.rule == "transfer_on_not_empty" for e in errors)
```

- [ ] **Step 2: 실패 확인**

```bash
python -m pytest tests/model/test_validation.py::test_transfer_on_not_empty_fails_when_empty -v
```
Expected: FAIL (rule not found in errors)

- [ ] **Step 3: validation.py에 규칙 추가**

`_validate_machine` 메서드에 한 줄 추가:
```python
errors.extend(Validator._check_duplicate_skill_ref(sm.states))
errors.extend(Validator._check_transfer_on_not_empty(sm.states))  # ← 새로 추가
```

그리고 새 메서드 추가 (클래스 하단):
```python
@staticmethod
def _check_transfer_on_not_empty(states: list) -> list[ValidationError]:
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.plugin.skill import ProceduralSkill
    from daedalus.model.plugin.agent import AgentDefinition
    errors: list[ValidationError] = []
    for state in states:
        if not isinstance(state, SimpleState):
            continue
        ref = state.skill_ref
        if ref is None:
            continue
        if isinstance(ref, (ProceduralSkill, AgentDefinition)):
            if not ref.transfer_on:
                errors.append(ValidationError(
                    rule="transfer_on_not_empty",
                    message=(
                        f"'{ref.name}' 스킬/에이전트의 transfer_on이 비어 있습니다. "
                        f"최소 하나의 이벤트가 필요합니다."
                    ),
                    source=ref.name,
                ))
    return errors
```

- [ ] **Step 4: 전체 통과 확인**

```bash
python -m pytest tests/model/test_validation.py -v
```
Expected: 전체 PASS

- [ ] **Step 5: 커밋**

```bash
git add daedalus/model/validation.py tests/model/test_validation.py
git commit -m "feat: add transfer_on_not_empty validator rule"
```

---

### Task 5: pyyaml 의존성 + VariableLoader 유틸리티

**Files:**
- Modify: `pyproject.toml`
- Create: `daedalus/view/editors/variable_loader.py`
- Create: `tests/view/editors/__init__.py`
- Create: `tests/view/editors/test_variable_loader.py`

- [ ] **Step 1: test_variable_loader.py 작성 (tests/view/editors/ 디렉토리 먼저 생성)**

```python
# tests/view/editors/__init__.py
# (빈 파일)
```

```python
# tests/view/editors/test_variable_loader.py
from __future__ import annotations

from pathlib import Path

import pytest

from daedalus.view.editors.variable_loader import VariableEntry, load_variables


def test_builtin_variables_always_present():
    entries = load_variables()
    names = [e.name for e in entries]
    assert "$ARGUMENTS" in names
    assert "${CLAUDE_SESSION_ID}" in names
    assert "${CLAUDE_SKILL_DIR}" in names


def test_builtin_source_tag():
    entries = load_variables()
    builtins = [e for e in entries if e.source == "builtin"]
    assert len(builtins) == 5


def test_missing_project_yaml_returns_no_project_entries(tmp_path):
    entries = load_variables(project_dir=tmp_path)
    assert [e for e in entries if e.source == "project"] == []
    assert len([e for e in entries if e.source == "builtin"]) == 5


def test_project_yaml_loaded(tmp_path):
    daedalus_dir = tmp_path / ".daedalus"
    daedalus_dir.mkdir()
    (daedalus_dir / "variables.yaml").write_text(
        '- name: "$MY_VAR"\n  description: "내 변수"\n',
        encoding="utf-8",
    )
    entries = load_variables(project_dir=tmp_path)
    project = [e for e in entries if e.source == "project"]
    assert len(project) == 1
    assert project[0].name == "$MY_VAR"
    assert project[0].description == "내 변수"


def test_invalid_yaml_returns_empty_gracefully(tmp_path):
    daedalus_dir = tmp_path / ".daedalus"
    daedalus_dir.mkdir()
    (daedalus_dir / "variables.yaml").write_text(": invalid: yaml: [", encoding="utf-8")
    entries = load_variables(project_dir=tmp_path)
    assert [e for e in entries if e.source == "project"] == []


def test_variable_entry_dataclass():
    e = VariableEntry(name="$X", description="설명", source="builtin")
    assert e.name == "$X"
    assert e.source == "builtin"
```

- [ ] **Step 2: 실패 확인**

```bash
python -m pytest tests/view/editors/test_variable_loader.py -v
```
Expected: `ImportError: No module named 'daedalus.view.editors.variable_loader'`

- [ ] **Step 3: pyproject.toml에 pyyaml 추가**

```toml
# pyproject.toml
[project]
dependencies = ["PyQt6>=6.6", "pyyaml>=6.0"]
```

그리고 재설치:
```bash
pip install -e ".[dev]"
```

- [ ] **Step 4: variable_loader.py 작성**

```python
# daedalus/view/editors/variable_loader.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass
class VariableEntry:
    name: str
    description: str
    source: Literal["builtin", "global", "project"]


_BUILTIN: list[VariableEntry] = [
    VariableEntry("$ARGUMENTS", "스킬 호출 시 전달된 전체 인수", "builtin"),
    VariableEntry("$ARGUMENTS[0]", "첫 번째 인수 (N은 임의 숫자)", "builtin"),
    VariableEntry("$N", "$ARGUMENTS[N] 단축형", "builtin"),
    VariableEntry("${CLAUDE_SESSION_ID}", "현재 세션 ID", "builtin"),
    VariableEntry("${CLAUDE_SKILL_DIR}", "스킬 SKILL.md 파일의 디렉토리 경로", "builtin"),
]


def load_variables(project_dir: Path | None = None) -> list[VariableEntry]:
    """기본 제공 + 글로벌 + 프로젝트 변수를 병합해 반환.

    우선순위 낮음 → 높음: builtin < global < project
    파일 없으면 해당 레벨은 빈 목록.
    """
    result: list[VariableEntry] = list(_BUILTIN)

    global_file = Path.home() / ".daedalus" / "variables.yaml"
    result.extend(_load_yaml(global_file, "global"))

    if project_dir is not None:
        project_file = project_dir / ".daedalus" / "variables.yaml"
        result.extend(_load_yaml(project_file, "project"))

    return result


def _load_yaml(
    path: Path,
    source: Literal["global", "project"],
) -> list[VariableEntry]:
    if not path.exists():
        return []
    try:
        import yaml  # type: ignore[import-untyped]
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, list):
            return []
        return [
            VariableEntry(
                name=item.get("name", ""),
                description=item.get("description", ""),
                source=source,
            )
            for item in data
            if isinstance(item, dict) and item.get("name")
        ]
    except Exception:
        return []
```

- [ ] **Step 5: 통과 확인**

```bash
python -m pytest tests/view/editors/test_variable_loader.py -v
```
Expected: 6개 PASS

- [ ] **Step 6: 커밋**

```bash
git add pyproject.toml daedalus/view/editors/variable_loader.py tests/view/editors/
git commit -m "feat: add VariableLoader with 3-tier variable resolution (builtin/global/project)"
```

---

### Task 6: SkillEditor 재작성 — _OptionalRow + _FrontmatterPanel

기존 `skill_editor.py` 313줄을 전면 교체한다. 이 태스크에서는 좌측 170px 패널만 구현한다.

**Files:**
- Modify: `daedalus/view/editors/skill_editor.py`
- Create: `tests/view/editors/test_skill_editor.py`

- [ ] **Step 1: 스모크 테스트 작성 (FrontmatterPanel 인스턴스화)**

```python
# tests/view/editors/test_skill_editor.py
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QScrollArea, QWidget

# qapp 픽스처는 tests/view/conftest.py에서 상속됨


def _make_procedural():
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.plugin.skill import ProceduralSkill
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    return ProceduralSkill(fsm=fsm, name="TestSkill", description="테스트")


def _make_declarative():
    from daedalus.model.plugin.skill import DeclarativeSkill
    return DeclarativeSkill(name="Knowledge", description="배경지식")


def _make_agent():
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.plugin.agent import AgentDefinition
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    return AgentDefinition(fsm=fsm, name="TestAgent", description="에이전트")


def test_frontmatter_panel_procedural(qapp):
    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    comp = _make_procedural()
    panel = _FrontmatterPanel(comp)
    assert isinstance(panel, QScrollArea)
    assert panel.width() == 170 or panel.maximumWidth() == 170


def test_frontmatter_panel_declarative(qapp):
    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    comp = _make_declarative()
    panel = _FrontmatterPanel(comp)
    assert isinstance(panel, QScrollArea)


def test_frontmatter_panel_agent(qapp):
    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    comp = _make_agent()
    panel = _FrontmatterPanel(comp)
    assert isinstance(panel, QScrollArea)
```

- [ ] **Step 2: 실패 확인**

```bash
python -m pytest tests/view/editors/test_skill_editor.py::test_frontmatter_panel_procedural -v
```
Expected: `ImportError: cannot import name '_FrontmatterPanel'`

- [ ] **Step 3: skill_editor.py 전면 교체 — 파일 상단부 + _OptionalRow + _FrontmatterPanel**

```python
# daedalus/view/editors/skill_editor.py
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.fsm.section import EventDef, Section
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.config import ProceduralSkillConfig
from daedalus.model.plugin.enums import EffortLevel, ModelType, SkillContext, SkillShell
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill

_INPUT_STYLE = (
    "background: #1a1a2e; border: 1px solid #446; color: #aac; "
    "padding: 3px 5px; border-radius: 3px; font-size: 9px;"
)
_DARK_BG = "#111120"

# QTreeWidgetItem 커스텀 데이터 롤
_ROLE_SECTION = Qt.ItemDataRole.UserRole
_ROLE_IS_TRANSFER_ON = Qt.ItemDataRole.UserRole + 1

_COLOR_PRESETS = [
    "#4488ff", "#cc3333", "#cc8800", "#44aa44",
    "#aa44cc", "#ccaa00", "#44aacc", "#888888",
]


class _OptionalRow(QWidget):
    """체크박스 ON/OFF로 선택적 프론트매터 필드를 표시/비활성화."""

    toggled = pyqtSignal(bool)

    def __init__(
        self,
        label: str,
        widget: QWidget,
        initially_enabled: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(3)

        self._cb = QCheckBox()
        self._cb.setChecked(initially_enabled)
        self._cb.setStyleSheet("QCheckBox::indicator { width: 10px; height: 10px; }")
        layout.addWidget(self._cb)

        lbl = QLabel(label)
        lbl.setStyleSheet("font-size: 8px; color: #88aaff; min-width: 58px;")
        layout.addWidget(lbl)

        self._widget = widget
        widget.setStyleSheet(_INPUT_STYLE)
        layout.addWidget(widget, 1)

        self._cb.toggled.connect(self._update_state)
        self._update_state(initially_enabled)

    def _update_state(self, checked: bool) -> None:
        self._widget.setEnabled(checked)
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(1.0 if checked else 0.4)
        self.setGraphicsEffect(effect)
        self.toggled.emit(checked)

    def is_checked(self) -> bool:
        return self._cb.isChecked()

    def set_checked(self, checked: bool) -> None:
        self._cb.setChecked(checked)


class _FrontmatterPanel(QScrollArea):
    """좌측 170px 고정 패널 — name/description(필수) + 선택 필드 체크박스."""

    changed = pyqtSignal()

    def __init__(
        self,
        component: ProceduralSkill | DeclarativeSkill | AgentDefinition,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._component = component
        self.setFixedWidth(170)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(
            f"QScrollArea {{ background: {_DARK_BG}; border: none; "
            f"border-right: 1px solid #1a1a33; }}"
        )

        inner = QWidget()
        inner.setStyleSheet(f"background: {_DARK_BG};")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(3)

        hdr = QLabel("Frontmatter")
        hdr.setStyleSheet(
            "font-size: 8px; color: #446; text-transform: uppercase; "
            "letter-spacing: 1px; margin-bottom: 4px;"
        )
        lay.addWidget(hdr)

        # --- 필수 필드 ---
        lay.addWidget(self._lbl("name *"))
        self._w_name = QLineEdit(component.name)
        self._w_name.setStyleSheet(_INPUT_STYLE)
        self._w_name.editingFinished.connect(self._save_name)
        lay.addWidget(self._w_name)

        lay.addWidget(self._lbl("description *"))
        self._w_desc = QTextEdit()
        self._w_desc.setPlainText(component.description)
        self._w_desc.setStyleSheet(_INPUT_STYLE)
        self._w_desc.setFixedHeight(44)
        self._w_desc.textChanged.connect(self._save_desc)
        lay.addWidget(self._w_desc)

        # --- 선택 필드 구분선 ---
        sep = QLabel("선택 필드")
        sep.setStyleSheet(
            "font-size: 8px; color: #446; margin-top: 6px; margin-bottom: 2px;"
        )
        lay.addWidget(sep)

        config = getattr(component, "config", None)

        # model
        w_model = QComboBox()
        for e in ModelType:
            w_model.addItem(e.value)
        if config is not None:
            mv = config.model.value if isinstance(config.model, ModelType) else str(config.model)
            idx = w_model.findText(mv)
            if idx >= 0:
                w_model.setCurrentIndex(idx)
        lay.addWidget(
            _OptionalRow(
                "model", w_model,
                initially_enabled=(config is not None and config.model != ModelType.INHERIT),
            )
        )

        # effort
        w_effort = QComboBox()
        for e in EffortLevel:
            w_effort.addItem(e.value)
        if config is not None and config.effort is not None:
            idx = w_effort.findText(config.effort.value)
            if idx >= 0:
                w_effort.setCurrentIndex(idx)
        lay.addWidget(
            _OptionalRow(
                "effort", w_effort,
                initially_enabled=(config is not None and config.effort is not None),
            )
        )

        # allowed-tools (SkillConfig 계열)
        if config is not None and hasattr(config, "allowed_tools"):
            w_tools = QLineEdit(" ".join(config.allowed_tools))
            w_tools.setPlaceholderText("Read Grep WebSearch")
            lay.addWidget(
                _OptionalRow(
                    "allowed-tools", w_tools,
                    initially_enabled=bool(config.allowed_tools),
                )
            )

        # ProceduralSkill 전용 필드
        if isinstance(config, ProceduralSkillConfig):
            w_ctx = QComboBox()
            for e in SkillContext:
                w_ctx.addItem(e.value)
            idx = w_ctx.findText(config.context.value)
            if idx >= 0:
                w_ctx.setCurrentIndex(idx)
            lay.addWidget(_OptionalRow("context", w_ctx, initially_enabled=True))

            w_paths = QLineEdit(" ".join(config.paths) if config.paths else "")
            w_paths.setPlaceholderText("src/**/*.py")
            lay.addWidget(
                _OptionalRow(
                    "paths", w_paths,
                    initially_enabled=bool(config.paths),
                )
            )

            w_shell = QComboBox()
            for e in SkillShell:
                w_shell.addItem(e.value)
            idx = w_shell.findText(config.shell.value)
            if idx >= 0:
                w_shell.setCurrentIndex(idx)
            lay.addWidget(_OptionalRow("shell", w_shell, initially_enabled=True))

            self._w_disable_model = QCheckBox("disable-model-invocation")
            self._w_disable_model.setChecked(config.disable_model_invocation)
            self._w_disable_model.setStyleSheet("color: #88aaff; font-size: 8px;")
            lay.addWidget(self._w_disable_model)

            self._w_user_invocable = QCheckBox("user-invocable")
            self._w_user_invocable.setChecked(config.user_invocable)
            self._w_user_invocable.setStyleSheet("color: #88aaff; font-size: 8px;")
            lay.addWidget(self._w_user_invocable)

        # argument-hint (ProceduralSkill + DeclarativeSkill)
        if config is not None and hasattr(config, "argument_hint"):
            w_hint = QLineEdit(config.argument_hint or "")
            w_hint.setPlaceholderText("[topic]")
            lay.addWidget(
                _OptionalRow(
                    "argument-hint", w_hint,
                    initially_enabled=bool(config.argument_hint),
                )
            )

        lay.addStretch()
        self.setWidget(inner)

    @staticmethod
    def _lbl(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 8px; color: #88aaff;")
        return lbl

    def _save_name(self) -> None:
        self._component.name = self._w_name.text().strip()
        self.changed.emit()

    def _save_desc(self) -> None:
        self._component.description = self._w_desc.toPlainText().strip()
        self.changed.emit()
```

- [ ] **Step 4: 통과 확인**

```bash
python -m pytest tests/view/editors/test_skill_editor.py::test_frontmatter_panel_procedural tests/view/editors/test_skill_editor.py::test_frontmatter_panel_declarative tests/view/editors/test_skill_editor.py::test_frontmatter_panel_agent -v
```
Expected: 3개 PASS

- [ ] **Step 5: 커밋**

```bash
git add daedalus/view/editors/skill_editor.py tests/view/editors/test_skill_editor.py
git commit -m "feat: add _OptionalRow and _FrontmatterPanel (left 170px panel)"
```

---

### Task 7: _TreeSidebar 위젯

**Files:**
- Modify: `daedalus/view/editors/skill_editor.py` (클래스 추가)
- Modify: `tests/view/editors/test_skill_editor.py` (테스트 추가)

- [ ] **Step 1: 스모크 테스트 추가**

```python
# tests/view/editors/test_skill_editor.py 하단에 추가

def test_tree_sidebar_procedural(qapp):
    from daedalus.view.editors.skill_editor import _TreeSidebar
    from daedalus.model.fsm.section import Section
    comp = _make_procedural()
    comp.sections = [
        Section("Persona", children=[Section("Role"), Section("Background")]),
        Section("Style"),
    ]
    sidebar = _TreeSidebar(comp)
    assert sidebar.tree_widget().topLevelItemCount() >= 3  # 2 sections + TransferOn


def test_tree_sidebar_declarative_no_transfer_on(qapp):
    from daedalus.view.editors.skill_editor import _TreeSidebar
    comp = _make_declarative()
    sidebar = _TreeSidebar(comp)
    # DeclarativeSkill은 TransferOn 없음
    has_transfer_on = False
    for i in range(sidebar.tree_widget().topLevelItemCount()):
        item = sidebar.tree_widget().topLevelItem(i)
        if item and item.data(0, Qt.ItemDataRole.UserRole + 1):
            has_transfer_on = True
    assert not has_transfer_on
```

- [ ] **Step 2: 실패 확인**

```bash
python -m pytest tests/view/editors/test_skill_editor.py::test_tree_sidebar_procedural -v
```
Expected: `ImportError: cannot import name '_TreeSidebar'`

- [ ] **Step 3: skill_editor.py에 _TreeSidebar 추가** (_FrontmatterPanel 클래스 아래에 추가)

```python
def _section_depth(item: QTreeWidgetItem) -> int:
    """QTreeWidgetItem의 트리 깊이 (루트=0)."""
    depth = 0
    parent = item.parent()
    while parent is not None:
        depth += 1
        parent = parent.parent()
    return depth


def _build_path(item: QTreeWidgetItem) -> list[str]:
    """루트 → 현재 아이템까지 타이틀 경로."""
    path: list[str] = []
    current: QTreeWidgetItem | None = item
    while current is not None:
        path.insert(0, current.text(0))
        current = current.parent()
    return path


class _TreeSidebar(QWidget):
    """중앙 145px 패널 — 섹션 트리 + TransferOn 고정 항목."""

    section_selected = pyqtSignal(object, list)   # (Section, path: list[str])
    transfer_on_selected = pyqtSignal()
    structure_changed = pyqtSignal()              # 섹션 추가/삭제 시

    def __init__(
        self,
        component: ProceduralSkill | DeclarativeSkill | AgentDefinition,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._component = component
        self.setFixedWidth(145)
        self.setStyleSheet(
            "background: #0f0f22; border-right: 1px solid #1a1a33;"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 8, 6, 6)
        lay.setSpacing(4)

        hdr = QLabel("Sections")
        hdr.setStyleSheet(
            "font-size: 8px; color: #446; text-transform: uppercase; letter-spacing: 1px;"
        )
        lay.addWidget(hdr)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setStyleSheet(
            "QTreeWidget { background: #0f0f22; border: none; color: #aaa; font-size: 9px; }"
            "QTreeWidget::item:selected { background: #1a1a3a; color: #88aaff; }"
            "QTreeWidget::item { padding: 2px 0; }"
        )
        self._tree.itemClicked.connect(self._on_item_clicked)
        lay.addWidget(self._tree, 1)

        btn_add = QPushButton("＋ 섹션 추가")
        btn_add.setStyleSheet(
            "border: 1px dashed #2a2a44; border-radius: 3px; color: #446; "
            "font-size: 9px; padding: 3px; background: transparent;"
        )
        btn_add.clicked.connect(self._on_add_section)
        lay.addWidget(btn_add)

        # TransferOn — ProceduralSkill / AgentDefinition 전용 고정 하단 항목
        self._has_transfer_on = not isinstance(component, DeclarativeSkill)
        if self._has_transfer_on:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("color: #2a4a2a;")
            lay.addWidget(sep)
            self._transfer_on_btn = QPushButton("⇄ TransferOn")
            self._transfer_on_btn.setStyleSheet(
                "background: #132013; border: 1px solid #2a4a2a; border-radius: 3px; "
                "color: #88cc88; font-size: 9px; padding: 3px 6px; text-align: left;"
            )
            self._transfer_on_btn.clicked.connect(self.transfer_on_selected)
            lay.addWidget(self._transfer_on_btn)

        self._rebuild()

    def tree_widget(self) -> QTreeWidget:
        return self._tree

    def _rebuild(self) -> None:
        self._tree.clear()
        for section in self._component.sections:
            item = self._make_item(section)
            self._tree.addTopLevelItem(item)
            self._populate_children(item, section)
        self._tree.expandAll()

    def _make_item(self, section: Section) -> QTreeWidgetItem:
        item = QTreeWidgetItem()
        item.setText(0, section.title)
        item.setData(0, _ROLE_SECTION, section)
        return item

    def _populate_children(self, parent_item: QTreeWidgetItem, section: Section) -> None:
        for child in section.children:
            child_item = self._make_item(child)
            parent_item.addChild(child_item)
            self._populate_children(child_item, child)

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        section: Section | None = item.data(0, _ROLE_SECTION)
        if section is None:
            return
        path = _build_path(item)
        self.section_selected.emit(section, path)

    def _on_add_section(self) -> None:
        selected = self._tree.currentItem()
        new_section = Section(title="새 섹션")
        if selected is None:
            # 최상위 H1 추가
            self._component.sections.append(new_section)
        else:
            section = selected.data(0, _ROLE_SECTION)
            if section is None:
                self._component.sections.append(new_section)
            else:
                # 선택 항목과 같은 레벨 (형제) 추가
                parent_item = selected.parent()
                if parent_item is None:
                    # 루트 레벨
                    idx = self._component.sections.index(section)
                    self._component.sections.insert(idx + 1, new_section)
                else:
                    parent_section: Section = parent_item.data(0, _ROLE_SECTION)
                    idx = parent_section.children.index(section)
                    parent_section.children.insert(idx + 1, new_section)
        self._rebuild()
        self.structure_changed.emit()

    def add_child_to_current(self) -> None:
        """ContentPanel의 '+ 하위 섹션' 버튼이 호출."""
        selected = self._tree.currentItem()
        if selected is None:
            return
        depth = _section_depth(selected)
        if depth >= 5:  # H6 이상 불가
            return
        section: Section = selected.data(0, _ROLE_SECTION)
        if section is None:
            return
        child = Section(title="새 하위 섹션")
        section.children.append(child)
        self._rebuild()
        self.structure_changed.emit()

    def delete_current(self) -> None:
        """ContentPanel의 '삭제' 버튼이 호출."""
        selected = self._tree.currentItem()
        if selected is None:
            return
        section: Section = selected.data(0, _ROLE_SECTION)
        if section is None:
            return
        parent_item = selected.parent()
        if parent_item is None:
            if section in self._component.sections:
                self._component.sections.remove(section)
        else:
            parent_section: Section = parent_item.data(0, _ROLE_SECTION)
            if section in parent_section.children:
                parent_section.children.remove(section)
        self._rebuild()
        self.structure_changed.emit()

    def current_depth(self) -> int:
        """현재 선택 아이템의 깊이 (없으면 -1)."""
        item = self._tree.currentItem()
        return _section_depth(item) if item is not None else -1
```

- [ ] **Step 4: 통과 확인**

```bash
python -m pytest tests/view/editors/test_skill_editor.py -v
```
Expected: 5개 PASS

- [ ] **Step 5: 커밋**

```bash
git add daedalus/view/editors/skill_editor.py tests/view/editors/test_skill_editor.py
git commit -m "feat: add _TreeSidebar with section tree, add/delete/child navigation"
```

---

### Task 8: _ContentPanel + _TransferOnPanel + _EventCard + _ColorPickerPopup

**Files:**
- Modify: `daedalus/view/editors/skill_editor.py` (클래스 추가)
- Modify: `tests/view/editors/test_skill_editor.py` (테스트 추가)

- [ ] **Step 1: 스모크 테스트 추가**

```python
# tests/view/editors/test_skill_editor.py 하단에 추가

def test_content_panel_show_section(qapp):
    from daedalus.model.fsm.section import Section
    from daedalus.view.editors.skill_editor import _ContentPanel
    panel = _ContentPanel()
    section = Section(title="Role", content="You are a writer.")
    panel.show_section(section, ["Persona", "Role"])
    assert panel.current_section() is section


def test_transfer_on_panel_procedural(qapp):
    from daedalus.view.editors.skill_editor import _TransferOnPanel
    from daedalus.model.fsm.section import EventDef
    events = [EventDef("done"), EventDef("error", color="#cc3333")]
    panel = _TransferOnPanel(events)
    assert isinstance(panel, QWidget)


def test_event_card_renders(qapp):
    from daedalus.view.editors.skill_editor import _EventCard
    from daedalus.model.fsm.section import EventDef
    e = EventDef("done", color="#4488ff")
    card = _EventCard(e, can_delete=False)
    assert isinstance(card, QFrame)
```

- [ ] **Step 2: 실패 확인**

```bash
python -m pytest tests/view/editors/test_skill_editor.py::test_content_panel_show_section -v
```
Expected: `ImportError: cannot import name '_ContentPanel'`

- [ ] **Step 3: skill_editor.py에 4개 클래스 추가** (_TreeSidebar 아래에 추가)

```python
class _ColorPickerPopup(QFrame):
    """8색 프리셋 팔레트 팝업 (모달 아님)."""

    color_selected = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: #1a1a2e; border: 1px solid #3a4a6a; border-radius: 5px; }"
        )
        self.setWindowFlags(Qt.WindowType.Popup)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        for hex_color in _COLOR_PRESETS:
            btn = QPushButton()
            btn.setFixedSize(18, 18)
            btn.setStyleSheet(
                f"background: {hex_color}; border: 2px solid #333; border-radius: 9px;"
            )
            btn.clicked.connect(lambda _checked, c=hex_color: self._emit(c))
            lay.addWidget(btn)

    def _emit(self, color: str) -> None:
        self.color_selected.emit(color)
        self.hide()


class _EventCard(QFrame):
    """TransferOn 패널의 이벤트 한 항목 카드."""

    delete_requested = pyqtSignal(object)   # EventDef
    changed = pyqtSignal()

    def __init__(
        self,
        event_def: EventDef,
        can_delete: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._event = event_def
        self._popup = _ColorPickerPopup()
        self._popup.color_selected.connect(self._on_color_picked)

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._update_border()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # 색상 원 버튼
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(14, 14)
        self._color_btn.setStyleSheet(
            f"background: {event_def.color}; border: 2px solid #335; border-radius: 7px;"
        )
        self._color_btn.clicked.connect(self._show_color_popup)
        lay.addWidget(self._color_btn)

        # 이름 + 설명 컬럼
        col = QVBoxLayout()
        col.setSpacing(3)

        name_row = QHBoxLayout()
        self._w_name = QLineEdit(event_def.name)
        self._w_name.setStyleSheet(
            "background: transparent; border: none; border-bottom: 1px solid #335; "
            "color: #88aaff; font-size: 11px; font-weight: bold;"
        )
        self._w_name.setFixedWidth(100)
        self._w_name.editingFinished.connect(self._on_name_changed)
        name_row.addWidget(self._w_name)
        name_lbl = QLabel("이벤트 이름")
        name_lbl.setStyleSheet("font-size: 8px; color: #335;")
        name_row.addWidget(name_lbl)
        name_row.addStretch()
        col.addLayout(name_row)

        self._w_desc = QLineEdit(event_def.description)
        self._w_desc.setPlaceholderText("간략한 설명 (선택)")
        self._w_desc.setStyleSheet(_INPUT_STYLE)
        self._w_desc.editingFinished.connect(self._on_desc_changed)
        col.addWidget(self._w_desc)

        lay.addLayout(col, 1)

        # 삭제 버튼
        self._del_btn = QPushButton("✕")
        self._del_btn.setFixedSize(20, 20)
        self._del_btn.setEnabled(can_delete)
        self._del_btn.setStyleSheet(
            "color: #335; background: transparent; border: none; font-size: 11px;"
        )
        self._del_btn.clicked.connect(lambda: self.delete_requested.emit(self._event))
        lay.addWidget(self._del_btn)

    def _update_border(self) -> None:
        c = QColor(self._event.color)
        border = c.name()
        bg = c.darker(300).name()
        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 5px; }}"
        )

    def _show_color_popup(self) -> None:
        pos = self._color_btn.mapToGlobal(self._color_btn.rect().bottomLeft())
        self._popup.move(pos)
        self._popup.show()

    def _on_color_picked(self, color: str) -> None:
        self._event.color = color
        self._color_btn.setStyleSheet(
            f"background: {color}; border: 2px solid #335; border-radius: 7px;"
        )
        self._update_border()
        self.changed.emit()

    def _on_name_changed(self) -> None:
        self._event.name = self._w_name.text().strip() or self._event.name
        self._w_name.setText(self._event.name)
        self.changed.emit()

    def _on_desc_changed(self) -> None:
        self._event.description = self._w_desc.text()
        self.changed.emit()


class _TransferOnPanel(QWidget):
    """TransferOn 선택 시 우측에 표시되는 이벤트 카드 목록."""

    transfer_on_changed = pyqtSignal()

    def __init__(
        self,
        transfer_on: list[EventDef],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._transfer_on = transfer_on
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        hdr = QLabel("출력 이벤트 정의 — 노드 포트로 자동 반영")
        hdr.setStyleSheet("font-size: 9px; color: #446; margin-bottom: 4px;")
        lay.addWidget(hdr)

        self._cards_widget = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(6)
        lay.addWidget(self._cards_widget)

        btn_add = QPushButton("＋ 이벤트 추가")
        btn_add.setStyleSheet(
            "border: 1px dashed #2a4a2a; border-radius: 5px; color: #446; "
            "font-size: 9px; padding: 7px; background: transparent;"
        )
        btn_add.clicked.connect(self._on_add_event)
        lay.addWidget(btn_add)

        hint = QLabel("색상 원 클릭 → 색상 팔레트 선택. 변경 즉시 캔버스 노드에 반영.")
        hint.setStyleSheet("font-size: 8px; color: #335;")
        lay.addWidget(hint)

        lay.addStretch()
        self._rebuild_cards()

    def _rebuild_cards(self) -> None:
        while self._cards_layout.count():
            child = self._cards_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        for event_def in self._transfer_on:
            can_delete = len(self._transfer_on) > 1
            card = _EventCard(event_def, can_delete=can_delete)
            card.changed.connect(self.transfer_on_changed)
            card.delete_requested.connect(self._on_delete_event)
            self._cards_layout.addWidget(card)

    def _on_add_event(self) -> None:
        self._transfer_on.append(EventDef("new_event"))
        self._rebuild_cards()
        self.transfer_on_changed.emit()

    def _on_delete_event(self, event_def: EventDef) -> None:
        if len(self._transfer_on) <= 1:
            return
        self._transfer_on.remove(event_def)
        self._rebuild_cards()
        self.transfer_on_changed.emit()


class _ContentPanel(QWidget):
    """우측 패널 — 브레드크럼 툴바 + 타이틀 인라인 편집 + QTextEdit."""

    add_child_requested = pyqtSignal()
    delete_requested = pyqtSignal()
    variable_insert_requested = pyqtSignal()
    content_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._section: Section | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # --- 툴바 ---
        toolbar = QWidget()
        toolbar.setStyleSheet("background: #111120; border-bottom: 1px solid #1a1a33;")
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(10, 5, 10, 5)
        tb_lay.setSpacing(6)

        self._breadcrumb = QLabel("")
        self._breadcrumb.setStyleSheet("font-size: 9px; color: #446;")
        tb_lay.addWidget(self._breadcrumb)
        tb_lay.addStretch()

        self._btn_variable = QPushButton("{ } 변수 삽입")
        self._btn_variable.setStyleSheet(
            "background: #1a2a1a; border: 1px solid #3a7a3a; border-radius: 3px; "
            "padding: 2px 8px; font-size: 9px; color: #88cc88;"
        )
        self._btn_variable.clicked.connect(self.variable_insert_requested)
        tb_lay.addWidget(self._btn_variable)

        self._btn_add_child = QPushButton("＋ 하위 섹션")
        self._btn_add_child.setStyleSheet(
            "background: #1a1a2e; border: 1px solid #333; border-radius: 3px; "
            "padding: 2px 7px; font-size: 9px; color: #668;"
        )
        self._btn_add_child.clicked.connect(self.add_child_requested)
        tb_lay.addWidget(self._btn_add_child)

        self._btn_delete = QPushButton("삭제")
        self._btn_delete.setStyleSheet(
            "background: #2a1a1a; border: 1px solid #443; border-radius: 3px; "
            "padding: 2px 7px; font-size: 9px; color: #885;"
        )
        self._btn_delete.clicked.connect(self.delete_requested)
        tb_lay.addWidget(self._btn_delete)

        lay.addWidget(toolbar)

        # --- 타이틀 인라인 편집 ---
        title_area = QWidget()
        title_area.setStyleSheet(f"background: {_DARK_BG};")
        ta_lay = QVBoxLayout(title_area)
        ta_lay.setContentsMargins(12, 8, 12, 4)
        self._w_title = QLineEdit()
        self._w_title.setPlaceholderText("섹션 타이틀")
        self._w_title.setStyleSheet(
            "background: transparent; border: none; border-bottom: 1px solid #333; "
            "color: #ccc; font-size: 14px; font-weight: bold;"
        )
        self._w_title.editingFinished.connect(self._save_title)
        ta_lay.addWidget(self._w_title)
        lay.addWidget(title_area)

        # --- 본문 텍스트 ---
        self._w_content = QTextEdit()
        self._w_content.setStyleSheet(
            f"background: {_DARK_BG}; color: #aaa; border: none; "
            "font-family: Consolas, monospace; font-size: 10px; padding: 4px 12px;"
        )
        self._w_content.textChanged.connect(self._save_content)
        lay.addWidget(self._w_content, 1)

    def current_section(self) -> Section | None:
        return self._section

    def show_section(self, section: Section, path: list[str]) -> None:
        self._section = section
        crumb = " › ".join(path)
        self._breadcrumb.setText(crumb)
        self._w_title.setText(section.title)
        self._w_content.blockSignals(True)
        self._w_content.setPlainText(section.content)
        self._w_content.blockSignals(False)

    def set_add_child_enabled(self, enabled: bool) -> None:
        self._btn_add_child.setEnabled(enabled)

    def insert_variable(self, var_name: str) -> None:
        self._w_content.insertPlainText(var_name)

    def _save_title(self) -> None:
        if self._section is not None:
            self._section.title = self._w_title.text().strip() or self._section.title
            self.content_changed.emit()

    def _save_content(self) -> None:
        if self._section is not None:
            self._section.content = self._w_content.toPlainText()
            self.content_changed.emit()
```

- [ ] **Step 4: 통과 확인**

```bash
python -m pytest tests/view/editors/test_skill_editor.py -v
```
Expected: 8개 PASS

- [ ] **Step 5: 커밋**

```bash
git add daedalus/view/editors/skill_editor.py tests/view/editors/test_skill_editor.py
git commit -m "feat: add _EventCard, _ColorPickerPopup, _TransferOnPanel, _ContentPanel"
```

---

### Task 9: _VariablePopup 위젯 + SkillEditor 통합

**Files:**
- Modify: `daedalus/view/editors/skill_editor.py` (_VariablePopup + SkillEditor 클래스 추가)
- Modify: `tests/view/editors/test_skill_editor.py` (통합 스모크 테스트 추가)

- [ ] **Step 1: 스모크 테스트 추가**

```python
# tests/view/editors/test_skill_editor.py 하단에 추가

def test_variable_popup_shows_builtins(qapp):
    from daedalus.view.editors.skill_editor import _VariablePopup
    from daedalus.view.editors.variable_loader import load_variables
    entries = load_variables()
    popup = _VariablePopup(entries)
    assert isinstance(popup, QFrame)


def test_skill_editor_procedural_smoke(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    comp = _make_procedural()
    editor = SkillEditor(comp)
    assert isinstance(editor, QWidget)


def test_skill_editor_declarative_smoke(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    comp = _make_declarative()
    editor = SkillEditor(comp)
    assert isinstance(editor, QWidget)


def test_skill_editor_agent_smoke(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    comp = _make_agent()
    editor = SkillEditor(comp)
    assert isinstance(editor, QWidget)


def test_skill_editor_changed_signal_exists(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    comp = _make_procedural()
    editor = SkillEditor(comp)
    # skill_changed 시그널이 존재하는지 확인 (기존 API 호환)
    assert hasattr(editor, "skill_changed")
```

- [ ] **Step 2: 실패 확인**

```bash
python -m pytest tests/view/editors/test_skill_editor.py::test_skill_editor_procedural_smoke -v
```
Expected: `ImportError` 또는 `AttributeError`

- [ ] **Step 3: skill_editor.py에 _VariablePopup + SkillEditor 추가**

```python
class _VariablePopup(QFrame):
    """변수 선택 팝업 — 클릭 시 variable_selected 시그널 방출."""

    variable_selected = pyqtSignal(str)

    def __init__(
        self,
        entries: list,        # list[VariableEntry]
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: #1a1a2e; border: 1px solid #3a4a6a; border-radius: 5px; }"
        )
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setFixedWidth(300)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(8, 5, 8, 5)
        hdr_lbl = QLabel("변수 선택 — 클릭 시 커서 위치에 삽입")
        hdr_lbl.setStyleSheet("font-size: 8px; color: #446;")
        hdr_row.addWidget(hdr_lbl)
        hdr_row.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(16, 16)
        close_btn.setStyleSheet("background: transparent; border: none; color: #335; font-size: 9px;")
        close_btn.clicked.connect(self.hide)
        hdr_row.addWidget(close_btn)
        hdr_widget = QWidget()
        hdr_widget.setStyleSheet("border-bottom: 1px solid #252540;")
        hdr_widget.setLayout(hdr_row)
        lay.addWidget(hdr_widget)

        # 소스별 그룹화
        from daedalus.view.editors.variable_loader import VariableEntry
        _SOURCE_LABELS = {
            "builtin": ("기본 제공", "#4477aa"),
            "global":  ("글로벌 (~/.daedalus/variables.yaml)", "#4a7a4a"),
            "project": ("프로젝트 (.daedalus/variables.yaml)", "#7a7a4a"),
        }
        current_source: str | None = None
        for entry in entries:
            if entry.source != current_source:
                current_source = entry.source
                label_text, label_color = _SOURCE_LABELS.get(
                    entry.source, (entry.source, "#446")
                )
                grp = QLabel(label_text)
                grp.setStyleSheet(
                    f"font-size: 8px; color: {label_color}; "
                    "text-transform: uppercase; letter-spacing: 0.5px; "
                    "padding: 4px 8px 2px 8px;"
                )
                lay.addWidget(grp)
            row = QPushButton()
            row.setStyleSheet(
                "background: transparent; border: none; text-align: left; "
                "padding: 3px 8px; font-size: 9px; color: #aaa;"
                "QPushButton:hover { background: #252540; }"
            )
            row.setText(f"{entry.name}   {entry.description}")
            row.clicked.connect(lambda _c, n=entry.name: self._emit(n))
            lay.addWidget(row)

    def _emit(self, name: str) -> None:
        self.variable_selected.emit(name)
        self.hide()


class SkillEditor(QWidget):
    """ProceduralSkill / DeclarativeSkill / AgentDefinition 3-패널 편집기.

    레이아웃:
      _FrontmatterPanel (170px) | _TreeSidebar (145px) | QStackedWidget (나머지)
        stack[0] = _ContentPanel  (섹션 선택 시)
        stack[1] = _TransferOnPanel  (TransferOn 선택 시)
    """

    skill_changed = pyqtSignal()  # 기존 API 호환

    def __init__(
        self,
        component: ProceduralSkill | DeclarativeSkill | AgentDefinition,
        on_notify_fn: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._component = component
        self._on_notify_fn = on_notify_fn

        from daedalus.view.editors.variable_loader import load_variables
        self._variables = load_variables()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 좌측: Frontmatter
        self._fm = _FrontmatterPanel(component)
        self._fm.changed.connect(self._on_model_changed)
        lay.addWidget(self._fm)

        # 중앙: Tree Sidebar
        self._sidebar = _TreeSidebar(component)
        self._sidebar.section_selected.connect(self._on_section_selected)
        self._sidebar.transfer_on_selected.connect(self._on_transfer_on_selected)
        self._sidebar.structure_changed.connect(self._on_model_changed)
        lay.addWidget(self._sidebar)

        # 우측: Stack (ContentPanel | TransferOnPanel)
        self._stack = QStackedWidget()

        self._content_panel = _ContentPanel()
        self._content_panel.add_child_requested.connect(self._on_add_child)
        self._content_panel.delete_requested.connect(self._on_delete_section)
        self._content_panel.variable_insert_requested.connect(self._on_variable_insert)
        self._content_panel.content_changed.connect(self._on_model_changed)
        self._stack.addWidget(self._content_panel)  # index 0

        if not isinstance(component, DeclarativeSkill):
            transfer_on = component.transfer_on
        else:
            transfer_on = []
        self._transfer_on_panel = _TransferOnPanel(transfer_on)
        self._transfer_on_panel.transfer_on_changed.connect(self._on_model_changed)
        self._stack.addWidget(self._transfer_on_panel)  # index 1

        lay.addWidget(self._stack, 1)

        # 변수 팝업 (ContentPanel 위에 플로팅)
        self._var_popup = _VariablePopup(self._variables, parent=self._content_panel)
        self._var_popup.variable_selected.connect(self._content_panel.insert_variable)
        self._var_popup.hide()

        # 초기 상태: 첫 번째 섹션 선택 또는 빈 화면
        if component.sections:
            first = component.sections[0]
            self._content_panel.show_section(first, [first.title])
            self._stack.setCurrentIndex(0)

    def _on_section_selected(self, section: Section, path: list[str]) -> None:
        self._content_panel.show_section(section, path)
        depth = self._sidebar.current_depth()
        self._content_panel.set_add_child_enabled(depth < 5)
        self._stack.setCurrentIndex(0)

    def _on_transfer_on_selected(self) -> None:
        self._stack.setCurrentIndex(1)

    def _on_add_child(self) -> None:
        self._sidebar.add_child_to_current()

    def _on_delete_section(self) -> None:
        self._sidebar.delete_current()

    def _on_variable_insert(self) -> None:
        if self._var_popup.isVisible():
            self._var_popup.hide()
            return
        from PyQt6.QtCore import QPoint
        btn = self._content_panel._btn_variable
        pos = btn.mapTo(self._content_panel, QPoint(0, btn.height()))
        self._var_popup.move(pos)
        self._var_popup.show()
        self._var_popup.raise_()

    def _on_model_changed(self) -> None:
        self.skill_changed.emit()
        if self._on_notify_fn is not None:
            self._on_notify_fn()
```

- [ ] **Step 4: 전체 테스트 통과 확인**

```bash
python -m pytest tests/view/editors/test_skill_editor.py -v
```
Expected: 13개 PASS

```bash
python -m pytest tests/ -v
```
Expected: 전체 PASS (기존 + 새 테스트 전부)

- [ ] **Step 5: 커밋**

```bash
git add daedalus/view/editors/skill_editor.py tests/view/editors/test_skill_editor.py
git commit -m "feat: add _VariablePopup and SkillEditor integration (3-panel layout)"
```

---

### Task 10: StateNodeItem — _event_defs() + EventDef.color 반영

기존 `_PORT_COLORS` dict 방식 → `EventDef.color` 직접 사용으로 변경.

**Files:**
- Modify: `daedalus/view/canvas/node_item.py`
- Modify: `tests/view/editors/test_skill_editor.py` (캔버스 반영 테스트 추가)

- [ ] **Step 1: 포트 색상 반영 테스트 추가**

```python
# tests/view/editors/test_skill_editor.py 하단에 추가

def test_node_item_port_color_from_event_def(qapp):
    """EventDef.color가 StateNodeItem 포트 색상에 반영되는지 확인."""
    from PyQt6.QtGui import QColor
    from daedalus.model.fsm.section import EventDef
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.plugin.skill import ProceduralSkill
    from daedalus.view.viewmodel.state_vm import StateViewModel
    from daedalus.view.canvas.node_item import StateNodeItem

    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    skill = ProceduralSkill(
        fsm=fsm, name="ColorSkill", description="d",
        transfer_on=[EventDef("done", color="#aa44cc"), EventDef("error", color="#cc3333")],
    )
    state = SimpleState(name="node", skill_ref=skill)
    vm = StateViewModel(model=state)
    item = StateNodeItem(vm)

    defs = item._event_defs()
    assert len(defs) == 2
    assert defs[0].color == "#aa44cc"
    assert defs[1].color == "#cc3333"
    # _output_events() 프로퍼티도 호환 확인
    assert item._output_events() == ["done", "error"]
```

- [ ] **Step 2: 실패 확인**

```bash
python -m pytest tests/view/editors/test_skill_editor.py::test_node_item_port_color_from_event_def -v
```
Expected: `AttributeError: 'StateNodeItem' object has no attribute '_event_defs'`

- [ ] **Step 3: node_item.py 업데이트**

`_PORT_COLORS` dict와 `_PORT_DEFAULT_COLOR` 제거. `_output_events()` 메서드 유지하되 `_event_defs()` 추가. `paint()` 메서드의 포트 렌더링 루프 수정.

```python
# daedalus/view/canvas/node_item.py
# 변경 1: 상단 임포트에 추가
from daedalus.model.fsm.section import EventDef

# 변경 2: _PORT_COLORS, _PORT_DEFAULT_COLOR 딕셔너리 제거
# (아래 두 줄 삭제)
# _PORT_COLORS: dict[str, QColor] = { ... }
# _PORT_DEFAULT_COLOR = QColor("#cc8800")

# 변경 3: StateNodeItem 클래스에 _event_defs() 메서드 추가
# (_output_events 메서드 바로 아래에 추가)
def _event_defs(self) -> list[EventDef]:
    """skill_ref.transfer_on에서 EventDef 목록 반환."""
    ref = self._state_vm.model.skill_ref
    if ref is not None and hasattr(ref, "transfer_on"):
        return list(ref.transfer_on)
    return []

# 변경 4: _output_events()는 하위 호환 유지
def _output_events(self) -> list[str]:
    ref = self._state_vm.model.skill_ref
    if ref is not None and hasattr(ref, "output_events"):
        return list(ref.output_events)
    return []

# 변경 5: paint() 메서드의 출력 포트 렌더링 루프 교체
# 기존:
#   for i, event_name in enumerate(events):
#       port_color = _PORT_COLORS.get(event_name, _PORT_DEFAULT_COLOR)
# 교체 후:
```

`paint()` 메서드 내 출력 포트 루프 전체 교체:

```python
# paint() 메서드 내 출력 포트 섹션 (기존 for 루프 교체)
event_defs = self._event_defs()
if not event_defs:
    # skill_ref 없는 빈 상태: 기본 "done" 표시
    event_defs = [EventDef("done", color="#4488ff")]

n_defs = len(event_defs)
for i, edef in enumerate(event_defs):
    y = self._output_port_y(i, n_defs)
    port_color = QColor(edef.color)
    painter.setPen(QPen(QColor("#111"), 1))
    painter.setBrush(QBrush(port_color))
    painter.drawEllipse(QPointF(_W, y), _PORT_R, _PORT_R)
    lbl_rect = QRectF(_W + _PORT_R + 2, y - 7, _LABEL_W - 4, 14)
    painter.setPen(QPen(port_color.lighter(140)))
    painter.setFont(QFont("Segoe UI", 7))
    painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignVCenter, edef.name)
```

`_height()`, `output_port_scene_pos()`, `_get_output_port_event()` 메서드들은 기존 `_output_events()` 호출을 그대로 사용 가능 (output_events 프로퍼티가 동일한 이름 목록을 반환하므로).

전체 변경된 `node_item.py` 파일:

```python
# daedalus/view/canvas/node_item.py
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

from daedalus.model.fsm.section import EventDef
from daedalus.view.viewmodel.state_vm import StateViewModel

_W = 160.0
_HEADER_H = 20.0
_PORT_R = 6.0
_PORT_SPACING = 22.0
_PORT_PAD = 12.0
_LABEL_W = 44.0

_TYPE_STYLE: dict[str | None, tuple[str, str, str, str]] = {
    "procedural_skill": ("#1a2a1a", "#4a8a4a", "PROCEDURAL", "⚙"),
    "declarative_skill": ("#2a2a1a", "#8a8a4a", "DECLARATIVE", "📄"),
    "agent":             ("#2a1a1a", "#8a4a4a", "AGENT",       "🤖"),
    None:                ("#1a1a2a", "#334466", "STATE",        ""),
}


class StateNodeItem(QGraphicsItem):
    """캔버스 위의 스킬/에이전트 노드."""

    def __init__(
        self, state_vm: StateViewModel, parent: QGraphicsItem | None = None
    ) -> None:
        super().__init__(parent)
        self._state_vm = state_vm
        self.setPos(state_vm.x, state_vm.y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self._drag_start_pos: QPointF | None = None
        self._dragging_connection = False
        self._drag_event_name: str | None = None
        self._sync_height()

    @property
    def state_vm(self) -> StateViewModel:
        return self._state_vm

    def _event_defs(self) -> list[EventDef]:
        """skill_ref.transfer_on에서 EventDef 목록 반환."""
        ref = self._state_vm.model.skill_ref
        if ref is not None and hasattr(ref, "transfer_on"):
            return list(ref.transfer_on)
        return []

    def _output_events(self) -> list[str]:
        """하위 호환용 — 이벤트 이름 목록만 반환."""
        ref = self._state_vm.model.skill_ref
        if ref is not None and hasattr(ref, "output_events"):
            return list(ref.output_events)
        return []

    def _height(self) -> float:
        n = max(1, len(self._output_events()))
        port_area = _PORT_SPACING * n + _PORT_PAD * 2
        return _HEADER_H + max(44.0, port_area)

    def _output_port_y(self, i: int, n: int) -> float:
        body_h = self._height() - _HEADER_H
        spacing = body_h / (n + 1)
        return _HEADER_H + spacing * (i + 1)

    def _sync_height(self) -> None:
        new_h = self._height()
        if self._state_vm.height != new_h:
            self.prepareGeometryChange()
            self._state_vm.height = new_h

    def update_from_model(self) -> None:
        self._sync_height()
        self.update()

    def boundingRect(self) -> QRectF:
        h = self._height()
        return QRectF(-_PORT_R * 2 - 2, 0, _W + _PORT_R * 2 + 2 + _LABEL_W, h)

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionGraphicsItem | None,
        widget: QWidget | None = None,
    ) -> None:
        if painter is None:
            return

        ref = self._state_vm.model.skill_ref
        kind = ref.kind if ref is not None else None
        bg_str, border_str, header_label, icon = _TYPE_STYLE.get(kind, _TYPE_STYLE[None])
        border_color = QColor(border_str)
        active_border = border_color.lighter(160) if self.isSelected() else border_color

        h = self._height()
        events = self._output_events() or ["done"]
        n = len(events)

        # 본체
        body_rect = QRectF(0, 0, _W, h)
        painter.setPen(QPen(active_border, 2))
        painter.setBrush(QBrush(QColor(bg_str)))
        painter.drawRoundedRect(body_rect, 7, 7)

        # 헤더
        header_rect = QRectF(1, 1, _W - 2, _HEADER_H - 1)
        hdr_bg = QColor(bg_str).darker(140)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(hdr_bg))
        painter.drawRoundedRect(header_rect, 6, 6)
        painter.drawRect(QRectF(1, 10, _W - 2, _HEADER_H - 11))

        painter.setPen(QPen(border_color.lighter(130)))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(
            header_rect.adjusted(6, 0, -20, 0),
            Qt.AlignmentFlag.AlignVCenter, header_label,
        )
        if icon:
            painter.drawText(
                header_rect.adjusted(0, 0, -4, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                icon,
            )

        # 이름
        name_rect = QRectF(4, _HEADER_H, _W - 8, h - _HEADER_H - 12)
        text_color = QColor("#eee") if self.isSelected() else QColor("#ccc")
        painter.setPen(QPen(text_color))
        font = QFont("Segoe UI", 11)
        if self.isSelected():
            font.setBold(True)
        painter.setFont(font)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignCenter, self._state_vm.model.name)

        # 서브텍스트
        subtext_rect = QRectF(4, h - 12, _W - 8, 12)
        painter.setPen(QPen(border_color.lighter(80)))
        painter.setFont(QFont("Segoe UI", 7))
        painter.drawText(subtext_rect, Qt.AlignmentFlag.AlignCenter, kind or "state")

        # 입력 포트 (좌측 중앙)
        painter.setPen(QPen(QColor("#333"), 1))
        painter.setBrush(QBrush(QColor("#888")))
        painter.drawEllipse(QPointF(0.0, h / 2), _PORT_R, _PORT_R)

        # 출력 포트 — EventDef.color 직접 사용
        event_defs = self._event_defs()
        if not event_defs:
            event_defs = [EventDef("done", color="#4488ff")]
        n_defs = len(event_defs)
        for i, edef in enumerate(event_defs):
            y = self._output_port_y(i, n_defs)
            port_color = QColor(edef.color)
            painter.setPen(QPen(QColor("#111"), 1))
            painter.setBrush(QBrush(port_color))
            painter.drawEllipse(QPointF(_W, y), _PORT_R, _PORT_R)
            lbl_rect = QRectF(_W + _PORT_R + 2, y - 7, _LABEL_W - 4, 14)
            painter.setPen(QPen(port_color.lighter(140)))
            painter.setFont(QFont("Segoe UI", 7))
            painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignVCenter, edef.name)

    def output_port_scene_pos(self, event_name: str) -> QPointF:
        events = self._output_events() or ["done"]
        n = len(events)
        try:
            i = events.index(event_name)
        except ValueError:
            i = 0
        return self.mapToScene(QPointF(_W, self._output_port_y(i, n)))

    def input_port_scene_pos(self) -> QPointF:
        return self.mapToScene(QPointF(0.0, self._height() / 2))

    def _get_output_port_event(self, local_pos: QPointF) -> str | None:
        events = self._output_events() or ["done"]
        n = len(events)
        hit_r = _PORT_R * 1.8
        for i, name in enumerate(events):
            y = self._output_port_y(i, n)
            dx = local_pos.x() - _W
            dy = local_pos.y() - y
            if dx * dx + dy * dy <= hit_r * hit_r:
                return name
        return None

    def is_input_port(self, local_pos: QPointF) -> bool:
        h = self._height()
        dy = local_pos.y() - h / 2
        return local_pos.x() <= _PORT_R * 2 and abs(dy) <= _PORT_R * 2

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            event_name = self._get_output_port_event(event.pos())
            if event_name is not None:
                self._dragging_connection = True
                self._drag_event_name = event_name
                sc: Any = self.scene()
                if sc is not None and hasattr(sc, "begin_transition_drag"):
                    sc.begin_transition_drag(self, event_name)
                event.accept()
                return
        self._drag_start_pos = self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging_connection:
            sc: Any = self.scene()
            if sc is not None and hasattr(sc, "update_transition_drag"):
                sc.update_transition_drag(self.mapToScene(event.pos()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        sc: Any = self.scene()
        if self._dragging_connection:
            self._dragging_connection = False
            self._drag_event_name = None
            if sc is not None and hasattr(sc, "end_transition_drag"):
                sc.end_transition_drag(self.mapToScene(event.pos()))
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self._drag_start_pos is not None and self._drag_start_pos != self.pos():
            if sc is not None and hasattr(sc, "handle_node_moved"):
                sc.handle_node_moved(self, self._drag_start_pos, self.pos())
        self._drag_start_pos = None
```

- [ ] **Step 4: 전체 테스트 통과 확인**

```bash
python -m pytest tests/ -v
```
Expected: 전체 PASS

- [ ] **Step 5: 커밋**

```bash
git add daedalus/view/canvas/node_item.py tests/view/editors/test_skill_editor.py
git commit -m "feat: StateNodeItem reads EventDef.color for port rendering"
```

---

## 자체 검토

### 스펙 커버리지

| 스펙 항목 | 구현 태스크 |
|-----------|------------|
| Section + EventDef 데이터클래스 | Task 1 |
| ProceduralSkill sections/transfer_on | Task 2 |
| DeclarativeSkill sections 추가 | Task 2 |
| AgentDefinition sections/transfer_on | Task 3 |
| output_events 프로퍼티 하위 호환 | Task 2, 3 |
| transfer_on_not_empty 검증 규칙 | Task 4 |
| VariableLoader 3-계층 | Task 5 |
| variables.yaml 파일 형식 | Task 5 |
| _FrontmatterPanel (170px, 상단 정렬) | Task 6 |
| 선택 필드 체크박스 + opacity 0.4 | Task 6 |
| _TreeSidebar (145px, H1-H6 뱃지) | Task 7 |
| TransferOn 트리 최하단 고정 | Task 7 |
| 섹션 추가 (형제/H1) | Task 7 |
| 하위 섹션 추가 (H6이면 비활성) | Task 7, 9 |
| _ContentPanel 브레드크럼 + 타이틀 편집 | Task 8 |
| _TransferOnPanel 이벤트 카드 | Task 8 |
| _EventCard 색상 원 + 이름 + 설명 | Task 8 |
| _ColorPickerPopup 8색 프리셋 | Task 8 |
| _VariablePopup 버튼 + 팝업 | Task 9 |
| SkillEditor 통합 | Task 9 |
| EventDef.color → 노드 포트 색상 | Task 10 |
| DeclarativeSkill 그래프 배치 불가 (이미 완료) | 기존 코드 |

### 누락 항목 없음. 플레이스홀더 없음.

### 타입 일관성

- `Section` / `EventDef` — Task 1에서 정의, Task 2-10 전체에서 동일 임포트 경로(`daedalus.model.fsm.section`) 사용
- `ProceduralSkill.transfer_on: list[EventDef]` — Task 2에서 정의, Task 9의 `_TransferOnPanel(transfer_on)` 호출과 일치
- `_event_defs() -> list[EventDef]` — Task 10에서 정의, Task 10 내부에서만 사용
- `_output_events() -> list[str]` — Task 2의 프로퍼티와 Task 10의 메서드가 동일 이름 목록 반환하여 `output_port_scene_pos()` 호환 유지
