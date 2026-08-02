# WP-TM — 도구/MCP 카탈로그 + 프론트매터 자동완성

## 배경

스킬 `allowed-tools`/에이전트 `tools` 프론트매터는 이미 모델·필드매트릭스·직렬화·
컴파일 배출까지 배선돼 있다(TagInput 편집). 빠진 것은 **입력 후보**다 — 사용자가
`Bash(git add *)`, `mcp__playwright__browser_click` 같은 문자열을 기억해 칠 수는
없다. 사용자 확정 설계: 카탈로그 디렉토리의 항목 파일이 후보를 공급한다.

## 확정 설계 (사용자와 합의됨)

- 카탈로그 = `~/.daedalus/catalogue/*.json`(글로벌) + `<프로젝트>/.daedalus/catalogue/*.json`
  (프로젝트, 이름 충돌 시 우선). 파일 1개 = 항목 1개, **파일명 stem = 항목/서버 이름**.
- 파일 스키마: `{"description": str?, "tool": [str...]?, "mcp": [str...]?}`
  - `tool`: CC allowed-tools 문법 그대로의 권한 문자열 (서브커맨드 스코프 포함)
  - `mcp`: MCP 도구 이름. 삽입 시 `mcp__<stem>__<도구>`로 확장, 이미 `mcp__`로
    시작하면 그대로.
- **삽입 의미론 = 확장 삽입**: 후보 선택 시 평문 문자열이 config에 들어간다.
  모델에 카탈로그 참조를 남기지 않는다 (프로젝트 자립성).
- `.mcp.json` 생성은 범위 밖. 대신 컴파일 시 `mcp__X__` 접두에서 서버 이름을
  추출해 "요구 환경" 언급.

## Part A — 카탈로그 로더 (view 측, variable_loader 패턴)

`daedalus/view/editors/catalogue_loader.py` 신규:

```python
@dataclass(frozen=True)
class CatalogueEntry:
    name: str                 # 파일명 stem
    description: str
    tools: tuple[str, ...]    # "tool" 키
    mcp: tuple[str, ...]      # "mcp" 키 (원문 그대로)
    source: str               # "global" | "project"

def load_catalogue(project_dir: Path | None = None) -> list[CatalogueEntry]
def expanded_mcp(entry) -> list[str]   # mcp__<stem>__<t> 확장 규칙
def candidate_strings(entries, project) -> list[str]
    # 합성: CC_BUILTIN_TOOLS(14종) + 각 entry의 tool/expanded_mcp
    #      + 프로젝트 에이전트들의 f"Agent({name})"
```

- 파싱 실패/스키마 불일치 파일은 조용히 스킵하지 말고 stderr 경고 1줄 + 무시.
- `CC_BUILTIN_TOOLS`는 validation.py의 frozenset 재사용 (단일 진실).

## Part B — TagInput 자동완성

`widgets/tag_input.py`: `set_candidates(list[str])` + QCompleter(부분 일치,
대소문자 무시) 부착. 스킬/에이전트 에디터에서 ALLOWED_TOOLS/DISALLOWED_TOOLS/
TOOLS 필드의 TagInput에 `candidate_strings(...)` 주입 (hook의
set_hook_name_provider 패턴 참조 — 프로젝트/카탈로그 변화에 동적).

카탈로그 "항목 전체 삽입"(그룹 일괄): TagInput 후보에 `📦 <entry.name>` 유사
가상 항목을 넣지 말고, 완성 목록에서 entry 이름을 고르면 그 entry의 전체
문자열이 일괄 삽입되는 방식 — 구현 복잡도가 크면 v1에서 개별 문자열 후보만으로
축소 가능(명세 이탈로 보고).

## Part C — 컴파일러: 요구 환경 자동 언급

`compiler/emit.py`: 스킬/에이전트의 allowed_tools·tools 값에서 `mcp__<server>__`
접두를 파싱해 서버 이름 집합을 얻고, 비어 있지 않으면 본문 끝(다음 단계 단락
앞/에이전트 요구 환경 단락에 합류)에:

```
## 요구 환경
이 스킬은 다음 MCP 서버가 연결되어 있어야 한다: `playwright`, `github`
```

기존 에이전트 SETTINGS(요구 환경) 단락과 중복되지 않게 합류. 결정적 정렬(이름순).

## Part D — 테스트

1. 로더: 글로벌/프로젝트 병합·우선, mcp__ 확장 규칙, 스키마 불일치 스킵.
2. 후보 합성: 빌트인 + 카탈로그 + Agent(이름).
3. TagInput completer 동작 (후보 주입 → completion 목록).
4. 컴파일: mcp__ 포함 allowed_tools → 요구 환경 단락, 미포함 → 단락 없음, 결정적.

## 비목표

- .mcp.json / plugin.json mcpServers 생성
- 프론트매터 문자열의 실존 검증 (권한 패턴은 자유 문자열)
- tool_shelf 통합 (역할 분리 유지)

## 작업 관례

- 브랜치 `wp-tm` (이미 생성돼 있으면 체크아웃만). master 직접 작업 금지.
- 테스트는 반드시 `python -m pytest tests/ -q` (pytest 직접 실행 불가).
- Pyright 진단은 스테일이 잦다 — 런타임 테스트로 판정.
- 커밋은 Part 단위 이상, 메시지는 한국어. push 금지.
- Qt 바인딩은 PySide6. QTest 타이핑 입력은 ASCII만.
- 카탈로그 로더 테스트는 실제 홈 디렉토리를 건드리지 말고 tmp_path + 경로 주입으로.
- CLAUDE.md 갱신: view/editors 항목에 catalogue_loader, widgets 항목에 TagInput
  자동완성, 컴파일 정책에 요구 환경 자동 언급 반영.
