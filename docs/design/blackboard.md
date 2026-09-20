# 블랙보드 — 공유 상태·접근 선언·MCP 서버

> CLAUDE.md에서 이관한 설계 기록(2026-09-12, 원문 그대로). 코드와 어긋나면 코드가
> 정본이다 — 발견 즉시 이 문서를 고친다. 색인은 루트 `CLAUDE.md`의 "설계 문서" 절.

## Blackboard = 컨텍스트 간 공유 장치

- **역할:** 서로 다른 컨텍스트 간에 외부 데이터를 통해 맥락을 공유하는 장치
- 동일 컨텍스트 내에서는 불필요 — 이미 같은 맥락을 공유
- 스코핑: 최상위 `Blackboard(parent=None)`, 하위 `Blackboard(parent=부모.blackboard)`
- **최상위 블랙보드:** `PluginProject.blackboard`(default_factory) — schemas.json의 소스(DynamicClass 단일 진실). 에이전트/스킬 FSM의 `blackboard.parent`는 **생성 경로의 책임**으로 이 객체에 배선한다 (app.py `_register_component`, **그리고 `deserialize_project` — 역직렬화도 생성 경로**: 스킬/에이전트 FSM→프로젝트 블랙보드로 재연결되어 parent 스코핑이 저장/로드를 견딘다. v1 파일의 에이전트 로컬 스킬은 `_migrate_v1`이 전역 승격하므로 같은 경로를 탄다 — WP-RF-1c). 마이그레이션 없음 — 메모리 내 기존 객체는 강제하지 않는다. 직렬화는 parent를 ID로 평탄화하지 않고 **소유 구조로 재연결**(`_deser_machine`의 `parent_bb` 전달).
- **DynamicClass → JSON Schema 매핑:** `blackboard.py`의 `FIELD_TYPE_TO_JSON_SCHEMA` 정본(STRING→string, INT→integer, FLOAT→number, BOOL→boolean, LIST→array, JSON→object, ANY→{}). CollectionType은 array로 래핑(LIST→items, SET→items+uniqueItems). 컴파일러 `compile_schemas_json(project)`가 프로젝트 블랙보드 class_definitions를 `<out>/schemas/<프로젝트 이름>.json`으로(정의 없으면 None). 파일 이름이 프로젝트 이름인 이유는 WP-NS — 고정 경로였을 때 한 작업 폴더에 ddls 플러그인이 둘 깔리면 나중 것이 앞의 것을 조용히 덮어썼다(경로 충돌 게이트는 한 번의 컴파일 안에서만 돈다).
- **블랙보드 편집 UI (WP-BB):** 모달이 아니라 `view/editors/blackboard_editor.BlackboardPanel`이 MainWindow의 상주
  최상위 탭(인덱스 1, Project FSM(0)과 동급, 항상 존재·닫기 불가)으로 프로젝트 최상위 블랙보드
  `class_definitions`를 편집한다 — 좌: 클래스 목록(추가/삭제/이름변경), 우: description + 필드
  테이블. 편집은 모델 직접 기록 + notify(structure 채널)로, 훅 라이브러리 다이얼로그와 동일하게
  undo 커맨드화 범위 밖이다.

## 상태 접근 선언 (reads/writes) — WP-BB

- **선언 위치는 `State` 베이스**(`model/fsm/state.py`) — "각각의 상태가 접근"이라는 설계에 따라
  `CompositeState`/`ParallelState`가 아니라 `State` 자체에 `reads: list[str]`/`writes: list[str]`
  (기본값 빈 리스트)를 둔다. 값은 `"Class"`(클래스 전체) 또는 `"Class.field"`(필드 수준) 문자열
  참조 — Tool 관례와 동일하게 fsm 레이어는 블랙보드 객체를 직접 참조하지 않고, 실존 검증은
  Validator가 담당한다. 프로젝트 캔버스 placement, 스킬 FSM 상태, 에이전트 FSM 상태 모두 같은
  필드·같은 편집 경로(PropertyPanel)를 공유한다.
- **편집 UI:** `PropertyPanel.show_state`의 reads/writes TagInput 2개. 자동완성 후보는
  `tag_input.set_blackboard_candidate_provider`/`get_blackboard_candidates`(WP-TM 도구 후보와
  동일한 provider 패턴)로 프로젝트 블랙보드의 "클래스"+"클래스.필드" 전체를 제공한다.
- **캔버스 뱃지:** `node_badges.state_access_badges(state)` — writes 있으면 ✏("블랙보드 쓰기: …"),
  reads 있으면 📖("블랙보드 읽기: …") 뱃지(둘 다 선언되면 둘 다 렌더). `StateNodeItem.paint`가 기존
  컴포넌트 뱃지(`badges_for`)에 합류시킨다 — 선언이 있을 때만 노출되어 노이즈가 없다.
- **컴파일러 구체화:** FSM 절차 단락(`_describe_fsm`/`_describe_agent_fsm`)의 상태 항목에
  `(읽기: \`A.x\`, \`B\` / 쓰기: \`A.y\`)` 접미사가 이름순 정렬로 합류한다(선언 없으면 문구
  생략). 블랙보드 단락(`_blackboard_section(project, component)`)은 component(스킬/에이전트)
  자체 FSM(재귀) + 프로젝트 그래프 placement의 reads/writes 합집합(`_component_access_union`)을
  구해, 비어있지 않으면 "이 스킬/에이전트가 읽는 것/쓰는 것"을 명시하고 파일 목록을 관련
  클래스만으로 좁힌다. **합집합이 비면 단락 자체를 생략한다**(WP-FK2 C3) — 총론·도구 사용법·
  규칙이 전부 `guides/<플러그인>/blackboard.md`로 갔으므로 접근 선언이 없으면 이 컴포넌트에
  대해 덧붙일 고유 정보가 남지 않는다. `component`는 필수 위치 인자다(빠뜨린 호출이 조용히
  단락을 없애지 않도록 — 원칙 5).
- **도구 사용법·상태 파일 목록·읽기-수정-쓰기 규칙은 공통 안내 파일에 한 번만 실린다**
  (`compiler.md` 정책 21번). 컴포넌트 산출에는 프론트매터 직후의 **포인터 1줄**이 그 파일을
  가리키고, 그 아래에 `Blackboard tools: mcp__…__* (MCP server bb-<플러그인>)` 한 줄이
  **무조건** 따라붙는다 — 도구가 보이지 않을 때 무엇이 안 떠 있는지 말할 수 있어야 하기
  때문이다(원칙 5). 종전에는 `State CLI:` 줄이 조건부로 붙었는데, 그 이유(가이드가 쓸 수 없는
  `${ROOT}` 치환 토큰 대신 실제 경로를 컴포넌트 파일에 남긴다)는 WP-BM으로 사라졌다 —
  도구 이름에는 경로가 없다.
- **reads/writes 선언은 프론트매터 권한이 된다**(WP-BM). 캔버스의 📖/✏ 뱃지와 산출 권한이
  같은 사실을 말한다 — 유도 규칙은 `compiler.md` 정책 22번.
- **검증:** `dangling_blackboard_ref`(reads/writes 참조가 블랙보드에 실존하는지, 재귀 +
  프로젝트 그래프 포함)/`orphan_blackboard_field`(어떤 상태도 참조하지 않는 필드 경고 — 클래스
  전체 참조는 그 필드 전부 커버로 간주, 프로젝트 전체에 접근 선언이 하나도 없으면 스킵) 2종.
  둘 다 프로젝트 수준 경고 규칙(아래 Validator 규칙 표 참조).

## 블랙보드 stdio MCP 서버 `daedalus-bb` (WP-BB1 → WP-BM)

설계 시점의 블랙보드(스키마)와 런타임의 블랙보드(work 폴더 `state/*.json`) 사이를 잇는
도구. 스킬/에이전트 본문의 블랙보드 지시가 "읽기-수정-쓰기"를 말로만 시키면 LLM이 JSON을
손으로 만들다 스키마를 어긴다 — 그 조작을 **검증 가능한 도구 호출**로 만든 것이 이 서버다.
`uv tool install`로 앱과 **함께 설치**된다(C+A 설계의 C). 진입점 `main()`은 stdout/stderr를 UTF-8로
재설정한다 — Windows 콘솔 기본(cp949)에서 한글·`—`가 든 도움말·진단이 `UnicodeEncodeError`로
죽는다(옛 CLI와 같은 처치, 2026-09-20 머지 검토에서 재발 확인 후 테스트로 고정).

**표면은 하나다.** 종전의 argparse CLI는 WP-BM에서 폐기됐다(사용자 확정 2026-09-20) — 같은
조작을 두 표면이 제공하면 산출 문서가 어느 쪽을 가리킬지 정해야 하고, 셸 따옴표·exit code
해석 계층이 산출에 그대로 남는다. 도구로 내면 노드의 reads/writes 선언이 그대로 **프론트매터
권한**으로 번역되는 이점도 함께 온다(`compiler.md` 정책 22번).

```
daedalus-bb --schemas <경로> [--state-dir DIR]        # stdio MCP 서버로 뜬다
```

### 도구 7개

| 도구 | 입력 | 결과 |
|---|---|---|
| `list` | — | `{"schemas", "state_dir", "classes": [{name, description?, file, fields}]}` |
| `read` | `cls`, `field?` | 파일 전체(객체) 또는 `{"field": …, "value": …}` |
| `init` | `cls`, `force=false` | 만든 객체 |
| `write` | `cls`, `set?`, `append?`, `remove?` (전부 `{필드: 값}`) | 쓴 뒤의 객체 |
| `validate` | `classes?` | `{"ok", "checked", "missing", "violations"}` |
| `progress_read` | — | 이 플러그인의 진행 항목 |
| `progress_set` | `current?`, `completed?`, `note?`, `prev?` | 갱신된 항목 |

- **실패는 예외가 아니라 결과다.** `{"ok": false, "error": {"kind", "message", "detail"?}}`.
  kind는 셋뿐이고(`core.ERROR_KINDS`가 단일 진실 — 등록되지 않은 kind로 오류를 만들면
  `ValueError`다) 종전 CLI의 exit code 3/2/1과 1:1이었다:
  - `not_found` — 대상 상태 파일(또는 진행 항목)이 없다.
  - `usage` — 사용법·스키마·IO 오류(없는 클래스/필드, 코어션 실패, 깨진 파일 …).
  - `rejected` — **쓰기가 반영되지 않았다**: 검증 실패(`detail`에 위반 목록) 또는 낙관적
    잠금 재시도 소진. 어느 쪽이든 파일은 그대로다.
  소비자가 모델이므로 종전 CLI가 stderr로 내던 진단은 `message`에 합친다.
- **`validate`의 `ok`는 "물어본 것이 전부 있고 전부 유효한가"**다. 위반이 있거나, **이름을
  명시한** 호출에서 그 파일이 없으면 거짓이다(종전 exit 3과 같은 판정 — 물어본 대상이 없다는
  것 자체가 대답이고, 결과만 훑는 호출자가 "검사했고 정상"으로 읽으면 안 된다). 이름을 생략한
  전 클래스 순회에서 부재는 고장이 아니라 `missing`으로만 보고한다.
- **값은 JSON 타입 그대로 받되 문자열이면 코어션이 돈다**(`coerce_value`). 스키마 타입이
  `integer`인데 `"3"`이 오면 3이 되고, `3`이 오면 그대로다. 문자열이 아닌 값은 손대지 않으며
  타입이 어긋나면 쓰기 직전 검증 게이트가 잡는다(조용히 고치지 않는다 — 원칙 5).
  boolean 문자열은 true/1/yes/y/on ↔ false/0/no/n/off. 컬렉션 필드의 `set` 값은 JSON 배열
  문자열 통째 또는 배열, `append`/`remove`의 값은 원소 하나 또는 원소 배열이다.
- **서버 이름은 `bb-<플러그인>`**이고 컴파일러가 같은 규약으로 `.mcp.json`을 낸다
  (`compiler.md` 정책 22번). 한 작업 폴더에 Daedalus 플러그인이 여럿이면 스키마와 상태 폴더가
  다르므로 서버도 각각이다.
- **스키마 파일은 기동 시점에 읽지 않는다.** 읽으면 스키마가 없는 작업 폴더에서 서버가 통째로
  죽어 모델이 "도구가 없다"는 것 말고는 아무 이유도 듣지 못한다. 각 도구 호출이 그때 읽고,
  실패는 그 호출의 `usage` 결과가 된다(원칙 5). 스키마를 호출마다 다시 읽는 두 번째 이유는
  **재컴파일**이다 — 세션 중에 플러그인이 다시 컴파일될 수 있고, 낡은 스키마로 검증하면 방금
  만든 클래스를 "없다"고 거절한다.

### 계층과 계약

- **`daedalus/cli/core.py`** — 판정의 실체(스키마 로드·검증·초기 객체·코어션·`write_state_checked`·
  명령 함수). **출력 채널이 없다**: 값을 돌려주고 실패는 `BlackboardError(kind, message, detail)`다.
  성공 경로의 진단(재시도 안내·생성 알림)은 호출자가 넘긴 `on_note` 콜백으로 나간다.
- **`daedalus/cli/progress.py`** — 진행 파일(`state/__progress__.json`), 같은 규약. 원자적 쓰기와
  낙관적 잠금은 **모듈 경유로**(`core.write_state_checked`) 부른다 — 이름으로 끌어오면 봉합선이
  둘이 되어 경쟁 재현 테스트가 한쪽만 감싼다.
- **`daedalus/cli/mcp_server.py`** — 표면. 도구 이름 → 핸들러는 `TOOLS` **선언 표**다(문자열
  `getattr` 디스패치가 아니다 — 이름만 적으면 핸들러가 고아로 보이고 오타가 기동까지 숨는다).
  핸들러 메서드에 `tool_` 접두가 붙는 이유는 노출 이름(`validate` 등)이 저장소의 동명 심볼과
  섞이지 않게 하기 위해서다.
- **SDK 버전 흡수는 `daedalus/mcp_compat.py` 한 곳**이다(앱 내장 MCP 서버와 공유). 그 모듈이
  core 스코프 **밖**이라 `daedalus/cli/**`의 순수 stdlib 제약이 MCP 서버를 내면서도 그대로 산다.

### 왜 `schemas.json`이 단일 진실인가

서버는 **설치 대상 프로젝트**(플러그인이 깔린 작업 폴더)에서 돈다. 그곳에는 Daedalus 모델도
`.daedalus.json`도 없다 — 있는 것은 컴파일 산출 `schemas/<플러그인>.json`뿐이다. 그래서
`daedalus/cli/**`는 **`daedalus.model`을 임포트하지 않는다**(`tests/test_import_contracts.py`가
core 금지 목록에 더해 AST로 강제). 모델을 끌어오면 "편집 시점 모델"과 "산출 스키마" 중 무엇이
정본인지가 흐려진다.

- **검증기는 최소 구현이다.** 범용 JSON Schema가 아니라 컴파일러(`FIELD_TYPE_TO_JSON_SCHEMA`
  + CollectionType 래핑)가 **실제로 만들어내는 형상**만 다룬다: `type`(string/integer/number/
  boolean/array/object) · `properties` · `required` · `items` · `uniqueItems`. `bool`은 Python에서
  `int`의 하위형이라 integer/number 검사보다 **먼저** 배제한다(안 그러면 `true`가 정수로 통과한다).
  스키마에 없는 키는 위반이 아니다(JSON Schema 기본) — 쓰기 경로로는 애초에 들어올 수 없다.
- **`write`는 검증 게이트 뒤에 있고 쓰기는 원자적이다.** 읽기-수정-쓰기 후 검증에 실패하면
  `rejected` + 파일 완전 불변, 통과하면 임시 파일 + `os.replace`로 교체한다(반쯤 쓰인 상태 파일
  없음). 파일이 없으면 초기 객체에서 시작한다.
- **`write`는 남의 쓰기를 덮지 않는다 — 낙관적 잠금 + 재시도.** 병렬 서브에이전트가
  같은 클래스를 갱신하면 읽기-수정-쓰기 사이에 남이 쓴 내용을 통째로 덮어써 **한쪽
  갱신이 조용히 사라졌다**(lost update). 이제 읽은 시점의 **원문**을 기억하고
  `write_state_checked`가 `os.replace` 직전에 디스크와 비교해, 달라졌으면 쓰지 않고
  **다시 읽어 같은 수정을 새 내용 위에 재적용**한다(최대 `_WRITE_MAX_ATTEMPTS`=3회).
  그래서 두 쓰기가 모두 살아남는다 — 병합할 수 없는 충돌을 다루는 것이 아니라 잃어버린
  갱신을 막는 것이 목적이다. 소진되면 `rejected`이고 남의 마지막 쓰기는 그대로 남는다.
  **검증 실패는 재시도하지 않는다**(다시 읽어도 같은 값이 같은 위반이다).
  - **mtime이 아니라 내용을 비교한다** — Windows의 mtime 해상도(파일시스템에 따라 수십
    ms~2초)로는 빠른 연속 쓰기를 구분하지 못해 남의 쓰기를 못 본 채 덮어쓴다.
  - **완전한 상호배제는 아니다.** 비교와 `os.replace` 사이의 창은 남는다 — 그것까지
    막으려면 파일 잠금이 필요한데, 크래시로 남은 잠금 파일을 깨는 휴리스틱이 그 자체로
    새 고장을 만든다. 창이 마이크로초 수준으로 좁아지는 것이 실질 이득이고 잃는 것은 없다.
  - 테스트(`tests/cli/test_blackboard_concurrency.py`)는 **코어의** `write_state_checked`를 감싸
    **비교 직전에** 파일을 바꿔치기한다 — 실제 경쟁과 같은 지점이어야 재시도 경로가 돈다.
- **컬렉션 연산:** 컬렉션 필드는 `append`/`remove`(원소 단위, `remove`는 **모든** 일치 원소 제거 —
  "이후 그 값은 없다"가 기대 동작) 또는 `set`(배열 통째). `uniqueItems`(SET 컬렉션)면 append·set
  양쪽에서 중복 제거. 적용 순서는 set → append → remove. **`remove`는 없는 것을 만들지 않는다** —
  키가 없으면(비required 필드의 초기 상태) 아무 일도 일어나지 않고, 리스트가 아닌 값(스키마
  위반)도 건드리지 않는다(빈 배열로 덮으면 고장이 조용히 지워진다 — 그 위반은 검증 게이트가
  잡는다). 값 형식 검사는 키 유무와 무관하게 그대로 돈다.
- **초기 객체:** required 필드만 채우고 비required는 생략한다. 값은 **선언 타입에 맞는
  `default`가 스키마에 있으면 그 값**, 없으면 타입별 제로값(string `""`/integer `0`/number
  `0.0`/boolean `false`/array `[]`/object `{}`/무제약(ANY) `null`)이다. 컴파일러가 `default`를
  실제로 배출하므로(`_class_to_json_schema`) 그것을 무시하면 default `true`인 required boolean이
  `false`로 초기화된다. 다만 default는 **타입이 보장되지 않는다** — 블랙보드 편집기가 default
  셀을 자유 텍스트로 받아 boolean 필드에 문자열 `"true"`가 실릴 수 있다. 그래서 선언 타입에
  맞을 때만 쓰고 어긋나면 제로값으로 물러난다(어긋난 default 때문에 `init` 자체가 실패하는 것이
  더 나쁘다 — 어긋남은 `list` 출력에 그대로 보인다).
- **`state/__progress__.json`은 스키마 밖 규약 파일**(WP-RS 진행 상태)이라 `validate` 전 클래스
  순회의 대상이 아니다 — 그 파일이 깨져 있어도 블랙보드 검증은 통과한다.
- **미존재 이름은 즉시 거부한다.** 클래스가 없으면 가용 클래스를, 필드가 없으면 가용 필드를
  `message`에 나열하고 `usage`다. 필드 오타는 상태 파일 유무보다 **먼저** 판정한다(파일이 없다고
  대답하면 오타를 못 찾는다).
- **인자 하나가 두 경로를 정한다**(WP-NS/D10). `--schemas`는 필수이고 `--state-dir`의 기본값이
  거기서 유도된다(`state/<스키마 stem>`). 따로 받으면 `--state-dir` 누락이 **조용히**
  네임스페이스 밖에 쓰는 사고가 된다 — 검증까지 통과하므로 아무도 눈치채지 못한다. 스키마가
  절대경로여도(마켓플레이스 빌드의 `${CLAUDE_PLUGIN_ROOT}/…`) **stem만** 쓰므로 상태는 항상
  작업 폴더 상대로 남는다.
- **컴파일러 산출 형상과의 결합은 테스트가 고정한다.** 코어는 모델을 임포트할 수 없지만
  `tests/`는 양쪽을 볼 수 있으므로, `tests/cli/test_schema_contract.py`가
  `compile_schemas_json`이 **실제로 만든 텍스트**를 스키마 파일로 깔고 도구를 돌린다(가이드
  텍스트의 도구 이름·인자가 실제 서버 표면과 일치하는지는 `tests/compiler/test_guides.py`가 따로
  고정한다). 손으로 쓴 픽스처만 쓰면 컴파일러가 형상을 바꿔도 코어 테스트는 전부 초록인 채
  런타임만 깨진다. `BLACKBOARD_FIELD_TYPES` 밖 legacy 타입(ANY/JSON/bare LIST)도 경고 등급이라
  실제로 산출에 나오므로 함께 고정한다.

## 실측 — 플러그인 `.mcp.json` 도구의 가시성과 이름 (CC 2.1.278, 2026-09-20)

WP-BM 단계 0. 스크래치패드에 최소 플러그인(`.claude-plugin/plugin.json` + `.mcp.json` +
`agents/probe.md` + `context: fork` 스킬)을 만들고 `claude --plugin-dir <경로> -p "/fkprobe"`로
쟀다. 판정은 서브에이전트 전사(`~/.claude/projects/<cwd>/<세션>/subagents/*.jsonl`)의 도구
호출 성공 여부다.

1. **보인다.** 플러그인 `.mcp.json`이 띄우는 MCP 서버의 도구는 **fork 서브에이전트에서도**
   보이고 호출된다(전사의 `agentType`이 `fkprobe:probe`, 도구 호출 결과가 서버의 반환값).
   그 에이전트의 `tools:` 제한 목록에 도구 이름을 적어 두면 그 하나만 보인다. 그래서 fork
   산출도 블랙보드 도구를 직접 쓸 수 있다 — "메인 대화가 대신 기록한다"는 규약은 진행
   **기록의 소유권** 때문에 남는 것이지 도구가 닿지 않아서가 아니다.
2. **이름에 플러그인 네임스페이스가 붙는다.** 플러그인이 제공한 서버의 도구는
   `mcp__plugin_<플러그인>_<서버>__<도구>`다(실측: 플러그인 `fkprobe`, 서버 `bb-fkprobe` →
   `mcp__plugin_fkprobe_bb-fkprobe__probe_ping`). 접두 없는 `mcp__<서버>__<도구>`는 **존재하지
   않는다** — 그 이름을 `tools:`에 적은 프로브는 도구를 찾지 못했다. 서버 이름의 하이픈은
   그대로 남는다(치환되지 않는다).
3. **작업 폴더 `.mcp.json`은 접두가 없다.** 같은 서버를 작업 폴더의 `.mcp.json`으로 띄우면
   이름은 `mcp__bb-fkprobe__probe_ping`이다. 즉 **도구 이름이 빌드 타깃에 따라 갈린다** —
   유도의 단일 진실은 `compiler/emit/blackboard_tools.py::bb_tool_prefix()`다.
4. `${CLAUDE_PLUGIN_ROOT}` 치환은 플러그인 `.mcp.json`의 `args`에서 **동작한다**(같은 프로브의
   서버가 그 경로로 떴다). 마켓플레이스 빌드가 스키마 절대 경로를 넘길 수 있는 근거다.
5. 곁다리 확인: fork 스킬의 `agent:`는 플러그인 빌드에서 **`플러그인:이름`**이어야 한다.
   접두 없는 이름(`probe`)을 적은 첫 프로브는 전사의 `agentType`이 `general-purpose`로 떨어졌다
   — 조용한 폴백이라 산출이 틀려도 아무 말이 없다(`agents.md`의 이름 해소 규칙과 일치).
