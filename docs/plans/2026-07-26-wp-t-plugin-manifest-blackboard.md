# WP-T: 설치 가능한 플러그인 산출 — plugin.json 매니페스트 + 블랙보드 사용 지침

작성: 2026-07-26. 대상 구현자: sonnet (명세 완성형 — 설계 결정은 본 문서에서 전부 확정됨.
문서에 없는 설계 판단이 필요해 보이면 임의 결정하지 말고 가장 보수적인(범위 최소) 해석을 따르라).

## 배경

시운전(스킬 2 + 에이전트 1 + 훅 + 블랙보드 미니 플러그인 컴파일) 결과, 산출물은
CC 규약과 거의 일치하나 "설치 가능한 플러그인"까지 갭 2개가 확인됐다:

1. **`.claude-plugin/plugin.json` 매니페스트 미생성** — 이게 없으면 산출 디렉토리를
   CC 플러그인으로 설치할 수 없다. CC는 `.claude-plugin/plugin.json`을 매니페스트로
   읽고 `skills/`·`agents/`·`hooks/hooks.json`은 규약 위치에서 자동 발견한다.
2. **블랙보드 단절** — `schemas/schemas.json`은 생성되지만 SKILL.md/agent .md 본문
   어디에도 "상태 파일을 만들고 갱신하라"는 지침이 없다. 스키마만 있고 사용 지침이
   없으면 런타임(LLM)은 블랙보드를 무시한다.

부수 확인: 새 프로젝트 기본 이름이 `"새 프로젝트"`(한글)이고 프로젝트 이름/메타를
편집할 UI가 없다. 매니페스트 이름 게이트(아래 A-5)를 넣으면 새 프로젝트가 전부
컴파일 거부되므로, 프로젝트 속성 편집 UI(Part C)가 이 WP에 반드시 포함되어야 한다.

## 비목표 (이 WP에서 하지 않는 것)

- 스킬 프론트매터의 비표준 `hooks:` 키 정리 (별도 WP에서 재검토)
- `.mcp.json` 생성, ToolExecution 실행 래퍼 (Tier 2 / WP-HOOK 영역)
- 에이전트 로컬 FSM 블랙보드의 class_definitions 반영 — schemas.json의 단일 진실은
  **프로젝트 최상위 블랙보드**다 (CLAUDE.md 확정 사항). 본 WP의 지침 단락도 프로젝트
  최상위 `class_definitions`만 다룬다.
- marketplace.json 등 배포 메타데이터

## Part A — plugin.json 매니페스트

### A-1. 모델: `PluginProject`에 메타 필드 2개 추가 (`daedalus/model/project.py`)

`name` 필드 바로 뒤에 추가:

```python
description: str = ""      # 플러그인 설명 — plugin.json description (빈 값이면 키 생략)
version: str = "0.1.0"     # 플러그인 버전 — plugin.json version (semver 문자열)
```

`__post_init__` 등 다른 로직 변경 없음.

### A-2. 직렬화 왕복 (`daedalus/model/serialize.py`)

- `serialize_project`: 최상위 dict에 `"description"`, `"version"` 키 추가 (항상 기록 —
  산출 JSON의 결정성 유지).
- `deserialize_project`: `d.get("description", "")`, `d.get("version", "0.1.0")`.
  구버전 파일(키 부재)은 기본값으로 조용히 복원 — **경고 없음** (graph 키 부재와 동일 정책).

### A-3. 배출 함수 (`daedalus/compiler/emit.py`)

`compile_schemas_json` 근처에 추가:

```python
def compile_plugin_manifest(project) -> str:
    """프로젝트 → .claude-plugin/plugin.json 텍스트 (LF, 결정적, 항상 생성)."""
```

- JSON 오브젝트 키 순서 고정: `name` → `description`(빈 문자열이면 키 생략) → `version`.
- 직렬화 스타일은 `compile_hooks_json`과 동일: `json.dumps(obj, ensure_ascii=False, indent=2)`
  → CRLF 정규화 → 말미 개행 보장. 반환형은 `str`이며 `None` 없음 (매니페스트는 무조건 생성).

### A-4. 산출 계획 합류 (`daedalus/compiler/project_compiler.py`)

`_plan_outputs`에서 schemas.json 항목 뒤에 **무조건** 추가:

```python
plan.append(_PlannedOutput(
    rel_path=PurePosixPath(".claude-plugin") / "plugin.json",
    label="plugin.json (플러그인 매니페스트)",
    subject=project,
    kind="plugin_manifest",
    component=project,
))
```

`compile_project`의 쓰기 분기에 `elif item.kind == "plugin_manifest": text = compile_plugin_manifest(project)` 추가.
모듈 docstring의 "CC 플러그인 출력 구조" 목록에도 `.claude-plugin/plugin.json` 한 줄 추가.

### A-5. 게이트: 프로젝트 이름 규약 (`project_compiler.py` + `validation.py`)

- `_plan_outputs` 시작부에서 `check_name(project.name, f"프로젝트 '{project.name}'", project)` 호출.
  프로젝트 이름은 plugin.json의 `name`(플러그인 식별자)이 되므로 컴포넌트 이름과 동일하게
  `^[a-z0-9][a-z0-9-]*$` 규약을 컴파일 게이트에서 **에러로** 강제한다. 기존
  `compile_invalid_component_name` rule을 재사용한다 (새 rule 만들지 말 것).
  에러 메시지에는 조치를 명시하라: "파일 → 프로젝트 속성…에서 이름을 변경하세요" 취지의 문구.
- `validation.py`의 `validate_project`: 프로젝트 이름에도 기존 `invalid_component_name`
  규칙 적용(컴포넌트와 동일 등급 — 빈 이름=에러, 규약 불일치=경고). 기존
  `_COMPONENT_NAME_RE`·메시지 세분화 로직을 재사용하고, `subject=project`,
  `path=("project",)`로 발급한다. **주의**: `duplicate_component_name` 등 다른 규칙에
  프로젝트 이름을 끌어들이지 말 것 — 이름 규약 검사만.

## Part B — 블랙보드 사용 지침 단락

### B-1. 배출 함수 (`emit.py`)

```python
def _blackboard_section(project) -> list[str]:
    """프로젝트 최상위 블랙보드 class_definitions → '## 공유 상태 (블랙보드)' 블록.

    정의가 없으면 빈 리스트 (단락 생략).
    """
```

정의가 1개 이상일 때 정확히 다음 블록들을 반환한다 (결정적 문구 — 그대로 사용):

```
## 공유 상태 (블랙보드)
```

```
이 워크플로의 컨텍스트 간 공유 상태는 작업 폴더의 `state/` 디렉토리에 JSON 파일로
유지한다. 각 파일의 구조는 플러그인의 `schemas/schemas.json`에 정의된 스키마를 따른다.
```

클래스 목록 (한 블록, `class_definitions` 선언 순서, description 빈 값이면 ` — ` 이하 생략):

```
- `<ClassName>` → `state/<ClassName>.json` — <description>
```

규칙 블록 (한 블록):

```
규칙:
- 파일을 수정하기 전에 반드시 현재 내용을 읽어라 (읽기-수정-쓰기).
- 파일이 없으면 스키마에 맞는 초기 객체로 생성하라.
- 스키마의 required 필드는 항상 채워라.
```

### B-2. 배출 위치

- **`compile_skill`**: `isinstance(skill, ProceduralSkill) and project is not None and not local`
  일 때, tool_shelf 단락 뒤 · "다음 단계" 단락 **앞**에 `blocks.extend(_blackboard_section(project))`.
  로컬 스킬 제외 이유: 로컬 스킬은 소유 에이전트 컨텍스트에서 실행되고 에이전트 .md가
  이미 같은 단락을 받는다(중복 방지). Declarative/Transfer/Reference 스킬 제외 —
  워크플로 수행 주체가 아니다.
- **`compile_agent`**: `project is not None`일 때 본문 마지막(위임 지침 뒤)에 동일 단락.

## Part C — 프로젝트 속성 UI (`daedalus/view/app.py`)

### C-1. 새 프로젝트 기본 이름 변경

`_new_project`의 `PluginProject(name="새 프로젝트")` → `PluginProject(name="new-plugin")`.
(한글 이름은 A-5 게이트와 충돌 — 기본값부터 규약 준수.)

### C-2. "프로젝트 속성…" 다이얼로그

- 파일 메뉴의 "다른 이름으로 저장" 뒤에 액션 "프로젝트 속성…" 추가 (단축키 없음).
- 핸들러 `_edit_project_properties`: 작은 `QDialog`(QFormLayout)로 3개 필드 편집 —
  이름(QLineEdit), 설명(QLineEdit), 버전(QLineEdit). OK 시:
  - 이름이 바뀌었으면 `self._project.name = 새값` (프로젝트 이름은 문자열 참조 대상이
    아니므로 `rename_component` 불요 — 단순 대입).
  - description/version 대입.
  - `self._update_title()` + 상태바에 "프로젝트 속성 변경됨" 표시.
  - 이름 규약 검사는 여기서 **막지 않는다** — 편집 중 자유, F7 경고/컴파일 게이트가 잡는다.
- 다이얼로그 클래스는 app.py 안에 두지 말고 `daedalus/view/editors/project_properties.py`
  신규 파일로 (`ProjectPropertiesDialog(QDialog)`, 생성자에 project를 받아 초기값 표시,
  `apply_to(project)` 메서드로 대입). 테스트에서 QDialog.exec 없이 위젯 값 →
  `apply_to` 경로를 직접 검증할 수 있게 한다.

## 테스트 (신규 + 기존 갱신)

pytest는 반드시 `python -m pytest tests/ -q`로 실행 (`pytest` 직접 실행 불가).

### 신규: `tests/compiler/test_plugin_manifest.py`

1. `compile_plugin_manifest` — name/version 포함, 키 순서(name→description→version),
   description 빈 문자열이면 키 없음, 말미 개행 + LF.
2. `compile_project` — `.claude-plugin/plugin.json`이 **항상** written에 포함되고
   내용이 `compile_plugin_manifest` 결과와 일치.
3. 프로젝트 이름 규약 위반(예: `"새 프로젝트"`) → `compile_invalid_component_name`
   에러로 거부, 파일 미생성.
4. serialize 왕복 — description/version 보존, 구버전 dict(키 부재) → 기본값 + 경고 0건.

### 신규: `tests/compiler/test_blackboard_section.py`

1. class_definitions 있는 프로젝트의 전역 ProceduralSkill → "## 공유 상태 (블랙보드)"
   포함 + `state/<ClassName>.json` 라인 + "다음 단계"보다 앞에 위치.
2. 정의 0개 → 단락 없음.
3. 로컬 스킬(`local=True`) → 단락 없음.
4. DeclarativeSkill → 단락 없음.
5. `compile_agent(project=...)` → 단락 포함(본문 마지막).
6. description 없는 DynamicClass → ` — ` 접미 없음.

### 신규: `tests/view/test_project_properties.py` (기존 view 테스트의 QApplication 픽스처 재사용)

1. `ProjectPropertiesDialog` 초기값 = project 현재값.
2. 위젯 값 변경 → `apply_to(project)` → name/description/version 반영.
3. `_new_project` 기본 이름이 `"new-plugin"`.

### 기존 갱신

- `compile_project`의 written 개수/경로를 검증하는 기존 테스트 전부: 매니페스트 1건
  추가를 반영해 갱신 (`tests/compiler/` 및 `tests/model/` 그레프로 `written` 검색).
- 기존 컴파일 테스트의 프로젝트 이름이 규약 불일치(대문자·한글·공백)면 A-5 게이트로
  깨진다 — 테스트 프로젝트 이름을 규약에 맞게 수정하라 (게이트를 약화하지 말 것).
- validation 테스트: 프로젝트 이름 `invalid_component_name` 경고 발급 케이스 1개 추가.

## 문서

`CLAUDE.md` 갱신:
- 컴파일러 출력 구조에 `.claude-plugin/plugin.json` 추가.
- 컴파일 정책에 매니페스트(정책 A-3 요약)와 블랙보드 지침 단락(정책 B 요약) 추가.
- `PluginProject` 설명에 description/version 필드 언급.

## 수용 기준

1. `python -m pytest tests/ -q` 전체 통과 (기존 855 + 신규).
2. 시운전 스크립트 수준의 프로젝트를 컴파일하면 `.claude-plugin/plugin.json`이 생기고,
   블랙보드 정의가 있으면 전역 ProceduralSkill과 에이전트 .md에 "## 공유 상태 (블랙보드)"
   단락이 나온다.
3. `compiler/`는 PyQt 무관 유지 (import 순수성 테스트 통과).
4. 산출 텍스트는 결정적, LF, UTF-8(BOM 없음).

## 준수 사항 (프로젝트 관례)

- FSM 모델 클래스는 `@dataclass(eq=False)` — 이 WP에서 새 dataclass는
  `ProjectPropertiesDialog`(QDialog — dataclass 아님)뿐이므로 해당 없음.
- 커밋 메시지는 한국어, 말미에 빈 줄 후 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- **push 금지.**
- Pyright 진단은 스테일이 잦다 — 런타임 테스트로 판정하라.
