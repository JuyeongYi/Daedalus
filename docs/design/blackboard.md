# 블랙보드 — 공유 상태·접근 선언·CLI

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
  클래스만으로 좁힌다. **합집합이 비면 단락 자체를 생략한다**(WP-FK2 C3) — 총론·CLI 사용법·
  규칙이 전부 `guides/<플러그인>/blackboard.md`로 갔으므로 접근 선언이 없으면 이 컴포넌트에
  대해 덧붙일 고유 정보가 남지 않는다. `component`는 필수 위치 인자다(빠뜨린 호출이 조용히
  단락을 없애지 않도록 — 원칙 5).
- **CLI 사용법·상태 파일 목록·읽기-수정-쓰기 규칙은 공통 안내 파일에 한 번만 실린다**
  (`compiler.md` 정책 21번). 컴포넌트 산출에는 프론트매터 직후의 **포인터 1줄**이 그 파일을
  가리키고, 진행 명령이 없는 컴포넌트(에이전트 종류들·미배치 스킬)에는
  같은 줄에 `State CLI: daedalus-bb --schemas ${ROOT}/schemas/<플러그인>.json …` 한 줄이 붙는다 —
  **가이드 본문에는 `${ROOT}` 치환 토큰을 쓸 수 없기 때문이다**(치환은 스킬·에이전트 content
  에서만 일어난다, 공식 문서 확인 2026-09-17). 가이드는 경로 자리에 `<SCHEMAS>` 자리표시자를
  쓰고 "너를 보낸 파일에 적힌 `--schemas` 경로를 그대로 쓰라"고 말한다.
- **검증:** `dangling_blackboard_ref`(reads/writes 참조가 블랙보드에 실존하는지, 재귀 +
  프로젝트 그래프 포함)/`orphan_blackboard_field`(어떤 상태도 참조하지 않는 필드 경고 — 클래스
  전체 참조는 그 필드 전부 커버로 간주, 프로젝트 전체에 접근 선언이 하나도 없으면 스킵) 2종.
  둘 다 프로젝트 수준 경고 규칙(아래 Validator 규칙 표 참조).

## 블랙보드 CLI `daedalus-bb` (WP-BB1)

설계 시점의 블랙보드(스키마)와 런타임의 블랙보드(work 폴더 `state/*.json`) 사이를 잇는
도구. 스킬/에이전트 본문의 블랙보드 지시가 "읽기-수정-쓰기"를 말로만 시키면 LLM이 JSON을
손으로 만들다 스키마를 어긴다 — 그 조작을 검증 가능한 명령 하나로 만든 것이 이 CLI다.
`uv tool install`로 앱과 **함께 설치**된다(C+A 설계의 C).

```
daedalus-bb --schemas <경로> [--state-dir DIR] <command>
  read <Class> [--field NAME]    # 파일 전체(JSON) 또는 필드 값
  init <Class> [--force]         # 스키마 기반 초기 객체 (있으면 거부, --force로 재생성)
  write <Class> --set f=v [--append f=v] [--remove f=v]
  validate [Class ...]           # 생략 시 전 클래스
  list                           # 클래스·필드 목록(JSON)
  progress read                  # 이 플러그인의 진행 항목 (없으면 exit 3)
  progress set [--current S] [--completed S]... [--note T] [--prev S]
```

- **exit code:** 0 성공 / 1 **쓰기가 반영되지 않음**(검증 실패, 또는 낙관적 잠금의 쓰기 충돌
  재시도 소진) / 2 사용법·스키마·IO 오류 / 3 대상 상태 파일 없음
  (`read`, 그리고 클래스를 **명시한** `validate`). 전역 옵션은 **하위 명령 앞**에 온다
  (argparse 서브파서 구조).
- **stdout에 나가는 것은 JSON뿐, 진단·안내는 stderr.** 소비자가 LLM이라 출력 채널을 섞으면
  파싱이 깨진다. 다만 "항상 JSON이 나온다"는 뜻은 아니다 — 오류 경로(exit 2/3, init·write의
  exit 1)는 stdout에 **아무것도 쓰지 않으므로** 무조건 `json.loads`를 걸면 그때 깨진다
  (`validate`만 예외 — 실패해도 `{"ok": false, "violations": [...]}`를 stdout에 내고 사람이
  읽을 목록을 stderr에 낸다). 본문 지시를 쓸 때는 exit code로 먼저 갈라야 한다.
  Windows에서 파이프 인코딩이 cp949로 잡혀 한국어가 깨지지 않도록 `main()`이 stdout/stderr를
  UTF-8로 reconfigure한다.
- **왜 `schemas.json`이 단일 진실인가:** CLI는 **설치 대상 프로젝트**(플러그인이 깔린 작업
  폴더)에서 돈다. 그곳에는 Daedalus 모델도 `.daedalus.json`도 없다 — 있는 것은 컴파일 산출
  `schemas/<플러그인>.json`뿐이다. 그래서 `daedalus/cli/**`는 **`daedalus.model`을 임포트하지
  않는다**(순수 stdlib. `tests/test_import_contracts.py`가 core 금지 목록에 더해 AST로 강제).
  모델을 끌어오면 "편집 시점 모델"과 "산출 스키마" 중 무엇이 정본인지가 흐려진다.
- **검증기는 최소 구현이다.** 범용 JSON Schema가 아니라 컴파일러(`FIELD_TYPE_TO_JSON_SCHEMA`
  + CollectionType 래핑)가 **실제로 만들어내는 형상**만 다룬다: `type`(string/integer/number/
  boolean/array/object) · `properties` · `required` · `items` · `uniqueItems`. `bool`은 Python에서
  `int`의 하위형이라 integer/number 검사보다 **먼저** 배제한다(안 그러면 `true`가 정수로 통과한다).
  스키마에 없는 키는 위반이 아니다(JSON Schema 기본) — CLI 경로로는 애초에 들어올 수 없다.
- **write는 검증 게이트 뒤에 있고 쓰기는 원자적이다.** 읽기-수정-쓰기 후 검증에 실패하면
  exit 1 + 파일 완전 불변, 통과하면 임시 파일 + `os.replace`로 교체한다(반쯤 쓰인 상태 파일
  없음). 파일이 없으면 초기 객체에서 시작한다.
- **write는 남의 쓰기를 덮지 않는다 — 낙관적 잠금 + 재시도.** 병렬 서브에이전트가
  같은 클래스를 갱신하면 읽기-수정-쓰기 사이에 남이 쓴 내용을 통째로 덮어써 **한쪽
  갱신이 조용히 사라졌다**(lost update). 이제 읽은 시점의 **원문**을 기억하고
  `write_state_checked`가 `os.replace` 직전에 디스크와 비교해, 달라졌으면 쓰지 않고
  **다시 읽어 같은 수정을 새 내용 위에 재적용**한다(최대 `_WRITE_MAX_ATTEMPTS`=3회).
  그래서 두 쓰기가 모두 살아남는다 — 병합할 수 없는 충돌을 다루는 것이 아니라 잃어버린
  갱신을 막는 것이 목적이다. 소진되면 exit 1 + stderr 안내이고 남의 마지막 쓰기는 그대로
  남는다. **검증 실패는 재시도하지 않는다**(다시 읽어도 같은 값이 같은 위반이다).
  - **mtime이 아니라 내용을 비교한다** — Windows의 mtime 해상도(파일시스템에 따라 수십
    ms~2초)로는 빠른 연속 쓰기를 구분하지 못해 남의 쓰기를 못 본 채 덮어쓴다.
  - **완전한 상호배제는 아니다.** 비교와 `os.replace` 사이의 창은 남는다 — 그것까지
    막으려면 파일 잠금이 필요한데, 크래시로 남은 잠금 파일을 깨는 휴리스틱이 그 자체로
    새 고장을 만든다. 창이 마이크로초 수준으로 좁아지는 것이 실질 이득이고 잃는 것은 없다.
  - 테스트(`tests/cli/test_blackboard_concurrency.py`)는 `write_state_checked`를 감싸
    **비교 직전에** 파일을 바꿔치기한다 — 실제 경쟁과 같은 지점이어야 재시도 경로가 돈다.
- **코어션:** `--set f=v`의 값은 스키마 타입으로 변환(integer/number/boolean/string, boolean은
  true/1/yes/y/on ↔ false/0/no/n/off). 컬렉션 필드는 `--append`/`--remove`(원소 단위, `--remove`는
  **모든** 일치 원소 제거 — "이후 그 값은 없다"가 기대 동작) 또는 `--set f='["a","b"]'`(JSON 배열
  통째). `uniqueItems`(SET 컬렉션)면 append·set 양쪽에서 중복 제거. 적용 순서는 set → append → remove.
  **`--remove`는 없는 것을 만들지 않는다** — 키가 없으면(비required 필드의 초기 상태) 아무 일도
  일어나지 않고, 리스트가 아닌 값(스키마 위반)도 건드리지 않는다(빈 배열로 덮으면 고장이 조용히
  지워진다 — 그 위반은 검증 게이트가 잡는다). 값 형식 검사는 키 유무와 무관하게 그대로 돈다.
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
  stderr에 나열하고 exit 2. 필드 오타는 상태 파일 유무보다 **먼저** 판정한다(파일이 없다고
  대답하면 오타를 못 찾는다).
- `validate`에서 상태 파일이 없는 클래스는 위반이 아니라 `"missing"`으로 보고한다(아직
  초기화되지 않은 상태는 고장이 아니다). 파싱 불가 파일은 위반이다. **이름을 생략한 전 클래스
  순회는 미초기화여도 exit 0**이지만, **클래스를 명시한 호출에서 그 파일이 없으면 exit 3**이다
  (`read`와 같은 뜻) — 물어본 대상이 없다는 것 자체가 대답이고, exit code만 보는 호출자가
  "검사했고 정상"으로 읽으면 안 된다. 위반이 있으면 그쪽이 우선(exit 1).
- **컴파일러 산출 형상과의 결합은 테스트가 고정한다.** CLI는 모델을 임포트할 수 없지만
  `tests/`는 양쪽을 볼 수 있으므로, `tests/cli/test_schema_contract.py`가
  `compile_schemas_json`이 **실제로 만든 텍스트**를 스키마 파일로 깔고 list/init/write/
  validate를 돌린다(가이드 텍스트의 명령·옵션 이름이 실제 파서와 일치하는지는
  `tests/compiler/test_guides.py`가 따로 고정한다 — 예전에는 `test_blackboard_section.py`가 맡았다)(손으로 쓴 픽스처만 쓰면 컴파일러가 형상을 바꿔도 CLI 테스트는 전부 초록인
  채 런타임만 깨진다). `BLACKBOARD_FIELD_TYPES` 밖 legacy 타입(ANY/JSON/bare LIST)도 경고
  등급이라 실제로 산출에 나오므로 함께 고정한다.
