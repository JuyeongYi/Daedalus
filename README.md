# Daedalus

FSM 기반 Claude Code 플러그인 하네스 엔지니어링 도구.

스킬(Skill)과 에이전트(Agent)를 FSM + Blackboard 모델로 설계하고, 컴파일러 패턴으로 Claude Code가 읽는 플러그인 파일을 생성한다.

## 개요

Daedalus는 Claude Code 플러그인 개발을 위한 시각적 편집 환경이다. 워크플로를 그래프로 그리면 그것이 정식 FSM 모델이 되고, 컴파일러가 SKILL.md·에이전트 `.md`·훅·스키마로 배출한다.

```
모델 (model/) → 컴파일러 (compiler/) → 플러그인 파일
```

편집 표면은 둘이다 — **GUI**(PySide6 노드 에디터)와 **앱 내장 MCP 서버**. 후자는 조회용 API가 아니라 사람이 GUI에서 작업하는 중에 Claude Code가 같은 프로젝트를 함께 편집하는 통로이고, MCP 편집도 사용자의 undo 스택에 들어간다.

설계 근거·함정·실측 기록은 [`CLAUDE.md`](CLAUDE.md)가 정본이다. 이 문서는 개요만 다룬다.

## 설치

Python 3.12 이상이 필요하다.

### 사용자 설치 — `uv tool install`

저장소를 클론하지 않고 GitHub에서 바로 설치한다.

```bash
uv tool install git+https://github.com/JuyeongYi/Daedalus.git
```

두 명령이 PATH에 놓인다.

| 명령 | 용도 |
|------|------|
| `daedalus` | GUI 편집기 (앱 내장 MCP 서버 포함) |
| `daedalus-bb` | 블랙보드·진행 상태 CLI — **컴파일된 플러그인이 런타임에 호출한다** |

`daedalus-bb`가 함께 설치되는 것이 중요하다. 산출된 스킬 본문이 블랙보드를 읽고 쓸 때 이 명령을 부르므로, 없으면 모델이 상태 JSON을 손으로 편집하는 경로로 물러난다.

특정 리비전을 고정하거나 갱신·제거하려면:

```bash
uv tool install git+https://github.com/JuyeongYi/Daedalus.git@<태그 또는 SHA>
uv tool upgrade daedalus
uv tool uninstall daedalus
```

**설정 편집 위젯은 자동으로 함께 받는다** — 별도 저장소지만 `pyproject.toml`에 git 의존성으로 선언돼 있다(아래 "외부 위젯" 절 참조).

### 개발 설치

```bash
git submodule update --init                          # external/ 서브모듈
pip install -e ".[dev]"
pip install -e external/QClaudeCodeSettingEditorWidget
```

서브모듈의 editable 설치는 위에서 받은 배포판 위젯을 **덮는다**(나중에 설치한 쪽이 이긴다). 위젯을 함께 고칠 때 필요한 순서다.

## 실행

```bash
daedalus              # uv tool install로 설치한 경우
python -m daedalus    # 저장소에서 직접 실행
```

명령줄 옵션 — `--mcp-port PORT`(그 포트만 쓴다, 점유 시 실패), `--no-mcp`(서버 미기동). 나머지 인자는 Qt에 그대로 넘어간다.

## 테스트

```bash
python -m pytest tests/ -q
```

`pytest`를 직접 실행하면 command not found가 난다 — `python -m pytest`를 쓴다.

## 외부 위젯 — QClaudeCodeSettingEditorWidget

작업 폴더 설정(`.claude/settings.json` / `settings.local.json`)을 편집하는 탭의 실체는 **별도 저장소의 위젯**이다. SchemaStore의 Claude Code 설정 스키마를 읽어 전 키의 편집 UI를 자동 생성하므로, 설정 키가 늘어도 Daedalus 쪽 코드를 고치지 않는다.

- 저장소: <https://github.com/JuyeongYi/QClaudeCodeSettingEditorWidget>
- 배포 이름: `qclaudecodesettingeditorwidget` / 임포트도 같은 이름
- 저장소 안 위치: `external/QClaudeCodeSettingEditorWidget` (git 서브모듈)

**없어도 앱은 정상 동작한다.** 설정 탭이 안내 자리 표시자로 바뀔 뿐이고 나머지 기능은 영향을 받지 않는다. 서브모듈을 초기화하지 않은 클론에서 GUI를 띄우면 이 상태가 된다.

**훅 설정은 이 위젯으로 편집하지 않는다.** 훅의 정본은 훅 라이브러리 탭이고, 설정 쪽에서 중복 편집하면 진실이 둘이 된다 — 위젯이 훅 카테고리를 제외하고, 저장·베이크·MCP 세 층이 각각 방어한다.

**함정 — 서브모듈 SHA와 배포 의존성은 별개다.** `pyproject.toml`의 참조는 위젯의 `main`을 추적하고 서브모듈은 특정 커밋에 고정돼 있다. 서브모듈을 올렸다고 해서 `uv tool install`이 같은 커밋을 받는다는 보장이 없으므로, 위젯을 갱신할 때는 배포 설치도 최신을 받는지 확인해야 한다.

## 아키텍처

```
daedalus/
├── model/          # 순수 도메인 모델 (Qt 무관)
│   ├── fsm/        # FSM 코어 — 상태·전이·가드·액션·블랙보드
│   ├── plugin/     # 플러그인 메타데이터 — 스킬·에이전트·훅·도구·필드 매트릭스
│   ├── serialize/  # 모델 ↔ JSON (안정 ID 기반, format 2 + v1 마이그레이션)
│   ├── validation/ # 검증 규칙 (머신 수준 + 프로젝트 수준)
│   ├── project.py  # PluginProject — 최상위 컨테이너
│   ├── package.py  # 프로젝트 패키지(폴더) + .ddpj 아카이브
│   ├── outline.py  # 본문 마크다운 아웃라인 (파생 인덱스)
│   └── templates.py# 시작 템플릿 카탈로그
├── compiler/       # 순수 모델 → 플러그인 파일 (Qt 무관, 순수 stdlib)
│   ├── emit/       # SKILL.md · 에이전트 .md · hooks.json · 매니페스트 텍스트 생성
│   ├── project_compiler.py # 검증 게이트 + 산출 계획 + 파일 쓰기
│   ├── wiring.py   # .mcp.json / settings 병합 (LOCAL 설치 배선)
│   ├── workspace.py# .claude/CLAUDE.md 구역 병합
│   └── token_report.py # 산출물 토큰 비용 추정 (표시 전용)
├── mcp/            # 앱 내장 MCP 서버 — Claude Code와 협업하는 창구
├── cli/            # daedalus-bb — 설치 대상에서 도는 런타임 CLI
├── templates/      # 시작 템플릿 시드 파일
└── view/           # PySide6 노드 에디터
```

**경계 계약:** core(`model/` + `compiler/` + `mcp/endpoint.py` + `cli/`)는 Qt 바인딩·GUI 레이어·MCP SDK·uvicorn을 임포트할 수 없다. `cli/`는 여기에 더해 `daedalus.model`도 임포트할 수 없다 — 설치 대상 프로젝트에서 도는 물건이라 검증 정본이 산출된 스키마 파일 자체다. `tests/test_import_contracts.py`가 **소스 AST 기준**으로 강제한다.

## 핵심 개념

### 컴포넌트

| 종류 | 본질 | FSM 관계 |
|------|------|---------|
| `ProceduralSkill` | 작업 지침 | 자체 FSM을 가진 독립 워크플로 |
| `DeclarativeSkill` | 배경 지식 | FSM 없음 |
| `TransferSkill` | 전이 위에 놓인 1:1 중간 상태 | 자체 FSM 보유, 전이 하나에만 붙는다 |
| `ReferenceSkill` | 참조 문서 | FSM 없음, 참조 노드로 복수 배치 |
| `WrappedSkill` | 다른 플러그인 스킬의 랩핑 | 본문 없음 — 정본은 외부 스킬(런타임 참조) |
| `AgentDefinition` | 별도 컨텍스트의 작업자 | **내부 FSM 없음** — 절차는 본문, 결과 분기는 출력 포트 |

### FSM

- **상태**: `SimpleState` / `CompositeState`(하위 머신) / `ParallelState`(Region별 병렬 + 조인 전략) / 의사 상태 4종(Choice·Terminate·Entry·Exit)
- **전이**: 트리거(완료 이벤트) + 가드 + 액션 + `data_map`. 캔버스에서 경유점으로 경로를 손보정할 수 있다
- **전략**: LLM / Tool / MCP / Expression 기반 가드·액션
- **프로젝트 그래프**: 캔버스의 노드와 전이가 들어가는 정식 `StateMachine`. 직렬화·컴파일·검증의 단일 진실이다

### 블랙보드

컨텍스트 사이에 데이터를 넘기는 장치다. 같은 컨텍스트 안에서는 필요 없다.

- 설계 시점에 클래스·필드를 정의하고, 각 상태가 `reads`/`writes`로 접근을 **선언**한다
- 컴파일이 그 선언을 산출 본문에 구체화하고, 캔버스는 뱃지로 보여 준다
- 런타임 상태는 작업 폴더의 `state/<플러그인>/<클래스>.json`이고 스키마는 `schemas/<플러그인>.json`이다 — 이름으로 갈라 두어 한 작업 폴더에 플러그인이 여럿 깔려도 서로 덮지 않는다
- 조작은 `daedalus-bb`가 전담한다. 스키마 검증·원자적 쓰기·낙관적 잠금을 코드가 보장하므로, 모델이 JSON을 손으로 만들다 스키마를 어기는 경로가 막힌다

### 빌드 타깃

| 타깃 | 산출 | 쓰임 |
|------|------|------|
| `MARKETPLACE` (기본) | `.claude-plugin/plugin.json` + `skills/` + `agents/` | 배포용 플러그인 |
| `LOCAL` | **컴파일이 곧 설치** — `.claude/skills/`·`.claude/agents/`로 바로 나가고 `.mcp.json`·설정·`.claude/CLAUDE.md` 구역·`.claude/rules/`까지 배선 | MCP·훅을 쓰는 에이전트 |

MCP를 쓰는 에이전트는 CC 정책상 마켓플레이스 플러그인으로 배포할 수 없다(프론트매터가 무시된다). 그것이 LOCAL 타깃이 있는 이유다.

### 프로젝트 패키지

폴더가 곧 프로젝트다 — `<폴더>/.daedalus.json` + `<폴더>/files/` + `<폴더>/skill-files/`. `.ddpj`는 그 폴더를 묶은 결정적 zip이고, 푸는 쪽은 zip slip을 쓰기 전에 검사한다.

## 검증

`Validator.validate_project(project)` — 머신 수준 **18종** + 프로젝트 수준 **31종**. 등급(에러/경고)의 단일 진실은 `validation/severity.py`의 `WARNING_RULES`다.

- **머신 수준**: 초기·최종 상태 포함성, 중첩 에이전트 금지, 에이전트 간 직접 전이 금지, 전이 끝점 존재, 도달 불가 상태, Choice 완전성, 병렬 조인 수, 중복 배치, 출력 포트 필수성 등
- **프로젝트 수준**: 이름 중복·규약, 문자열 참조 실존(도구·훅·블랙보드·컴포넌트), 빌드 타깃 적합성, 진입점 의미론, 전이 스킬 재사용 금지, 작업 폴더 문서 규칙, 외부 플러그인 선언 정합 등

컴파일은 **에러 1건이라도 있으면 파일을 쓰지 않는다**. 이름 규약 불일치와 산출 경로 충돌은 편집 중에는 경고지만 컴파일 게이트에서 에러로 승격된다.

## GUI

상주 탭 6개(닫을 수 없다) — **Project FSM** / **🗂 블랙보드** / **🪝 훅** / **📌 CLAUDE.md** / **📐 규칙** / **⚙ 설정**. 뒤 세 개는 LOCAL 빌드에서만 보인다. 컴포넌트를 열면 편집 탭이 그 뒤에 붙는다.

- **캔버스**: 드래그로 스킬·에이전트 배치, 포트 연결로 전이 생성, 경유점으로 엣지 정리, 우클릭으로 진입점 프리셋·미리보기·모델/effort·관련 경고
- **마크다운 에디터**: 하이라이팅, 서식 툴바, `/` 슬래시 메뉴, 찾기/바꾸기, TOC, 파일 드래그 시 참조 토큰 치환. 본문은 컴포넌트마다 **독립 undo 스택**을 갖는다
- **훅 라이브러리**: 이벤트 31종 × 핸들러 5종의 3단 구조 편집 + 라이프사이클 다이어그램 피커. 전역(`~/.daedalus/hooks/`)과 프로젝트 2단 스코프
- **패널**: 레지스트리 / 파일 / 프로퍼티 / 히스토리 / 검증 결과(F7)
- **단축키**: `Ctrl+N` 새 프로젝트, `Ctrl+O` 폴더 열기, `Ctrl+B` 컴파일, `F7` 검증

## 앱 내장 MCP 서버 — AI와 함께 편집하기

GUI가 켜지면 `127.0.0.1`에 Streamable HTTP로 MCP 서버가 함께 뜬다(기본 포트 8787). 도구 메뉴 → "MCP 서버 정보..."가 접속 주소와 `.mcp.json` 스니펫을 주고, "Claude Code 실행"은 프로젝트 폴더에서 배선까지 마친 새 세션을 띄운다.

**거의 모든 기능이 MCP로 노출돼 있다 — 도구 86종.** 그래서 실제 사용감은 "도구를 호출한다"기보다 **옆자리에 앉은 사람과 같은 파일을 놓고 작업하는 쪽**에 가깝다.

- Claude가 사용자의 화면을 안다 — `get_selection`(지금 선택한 것), `get_history`(방금 한 편집), `focus_node`(말로 설명하는 대신 그 노드를 선택해 보인다)
- 편집이 **한 undo 스택을 공유한다** — 사용자가 `Ctrl+Z`로 Claude의 작업을 되돌릴 수 있고 히스토리 패널에 사람 편집과 같은 형식으로 남는다
- 본문 편집은 에디터의 `QTextDocument`로 들어간다 — 열려 있으면 타이핑하듯 반영된다

**패리티 원칙:** GUI에서 가능한 편집·조회는 MCP로도 가능해야 한다. 새 GUI 기능을 넣을 때 대응 도구를 같은 작업에서 함께 만든다 — 나중에 채우는 갭이 아니라 완성 조건이다.

도구 지도·연결 방법·함께 쓰는 관례는 [`docs/MCP.md`](docs/MCP.md)를 참조.

## 컴파일러

`compile_project(project, out_dir, ...)` — 검증 게이트를 통과하면 산출 계획을 세우고 파일을 쓴다. 출력은 결정적이다(같은 모델 → 같은 텍스트, LF, BOM 없음).

산출에 합류하는 것:

- 프론트매터 — 필드 매트릭스에서 `emit==FRONTMATTER`인 필드만(FIXED 강제, 선언 기본값과 같으면 생략)
- FSM 절차 서술, 다음 단계, 진입 맥락, 호출 계약, 출구 — 전부 **그래프에서 유도**한다
- 작업 재개 규약(`state/__progress__.json`), 블랙보드 사용 지침, 요구 환경(MCP 서버)
- 훅 스크립트·`hooks.json`(MARKETPLACE) 또는 설정 병합(LOCAL), `schemas/<플러그인>.json`, `files/`·`skill-files/` 복사

**산출 언어는 영어다.** 컴파일러가 생성하는 문구는 영어이고 사용자가 입력한 값(본문·설명·포트 설명)은 그대로 나간다. 자동 단락은 모든 스킬에 반복해서 실리므로 토큰 비용이 곧 사용료다.

`compile_project(..., dry_run=True)`는 파일을 하나도 쓰지 않고 게이트 판정과 경고만 본다. MCP `compile_check`가 이것을 쓴다.

## 현재 구현 범위

- [x] FSM 코어 + 플러그인 메타데이터 모델
- [x] 직렬화(안정 ID, format 2 + v1 마이그레이션) · 프로젝트 패키지 · 시작 템플릿
- [x] 검증기 — 머신 18종 + 프로젝트 31종
- [x] PySide6 노드 에디터 · 마크다운 에디터 · 훅 라이브러리 · 블랙보드 편집
- [x] 컴파일러 — SKILL.md / 에이전트 .md / plugin.json / hooks.json / schemas / files 복사
- [x] 빌드 타깃(마켓플레이스 · 로컬) + LOCAL 설치 배선(.mcp.json · settings · CLAUDE.md 구역 · rules)
- [x] 앱 내장 MCP 서버 (도구 86종)
- [x] 블랙보드·진행 상태 CLI (`daedalus-bb`)
- [x] 외부 플러그인 스킬 랩핑
- [ ] 컴파일러 Tier 2 — ToolExecution/ToolEvaluation 실행 래퍼, MCP 서버 실행 코드
- [ ] 컴파일 분할(점진 공개) — 설계 문서만 있고 구현 전

테스트는 2,616건이 통과한다(1건 skip).

## 라이선스

MIT
