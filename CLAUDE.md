# Daedalus

FSM 기반 Claude Code 플러그인 하네스 엔지니어링 도구.
스킬(Skill)과 에이전트(Agent) 컴포넌트를 FSM + Blackboard 모델로 설계하고, 컴파일러 패턴으로 플러그인 파일을 생성한다.

## 개발 환경

```bash
git submodule update --init  # external/ 서브모듈 (설정 편집 위젯)
pip install -e ".[dev]"      # 개발 의존성 설치
pip install -e external/QClaudeCodeSettingEditorWidget  # 설정 편집 위젯 (WP-WS UI)
python -m pytest tests/ -v   # 전체 테스트
python -m pytest tests/model/fsm/ -v      # FSM 코어만
python -m pytest tests/model/plugin/ -v  # 플러그인 레이어만
```

pytest는 `python -m pytest`로 실행한다 (`pytest` 직접 실행 시 command not found).

## 아키텍처

컴파일러 패턴(순수 모델 → 컴파일러 → 플러그인 파일), core 경계 계약, 모듈 지도는
**`docs/design/architecture.md`**가 정본이다. 새 모듈을 만들거나 임포트 방향을 바꾸기 전에 읽는다
(경계 계약은 `tests/test_import_contracts.py`가 소스 AST로 강제한다).

## 설계 원칙 (전 영역 공통)

이 절은 요약이다. 각 원칙이 태어난 사례와 세부 규칙은 아래 "설계 문서"에 있다.

1. **판정·기능의 실체는 한 곳이다.** 같은 조작을 여러 표면(캔버스 메뉴·에디터·레지스트리·MCP)이
   제공하면 전부 같은 함수를 부른다(`view/actions/`, 모델의 판정 함수). 한쪽에 로직을 넣고 다른
   쪽이 흉내 내면 표면마다 결과가 달라진다. 산출·검증·UI가 같은 사실을 말해야 할 때도 같은 판정을 쓴다.
2. **MCP 패리티 (사용자 확정, 상시 적용).** GUI에서 가능한 편집·조회는 MCP로도 가능해야 한다 — 새
   GUI 기능의 대응 MCP 도구(또는 파라미터)를 **같은 WP에서** 만든다. 조회는 개요 ↔ 전문으로 나누고,
   쓸 수 있는 값은 읽을 수도 있어야 한다.
3. **편집은 CommandStack 경유 = undo 가능.** 여러 필드를 세트로 바꾸면 `MacroCommand` 1 undo 단위.
   `SetAttrCmd`에는 **새 객체**를 넘긴다(제자리 수정이면 old/new가 같아 undo가 죽는다). 값이 같으면
   커맨드를 쌓지 않는다. 본문(body)만 컴포넌트별 `QTextDocument`의 별도 undo 스택이다(WP-BU).
   선택·포커스는 편집이 아니므로 스택을 거치지 않는다.
4. **검증기·컴파일러는 파일시스템을 읽지 않는다 — 호출자가 주입한다** (전역 훅 `resolved_hooks`/
   `known_hook_names`, `files_dir`, 서버 정의 …). 주입 인자의 단일 진실은
   `CompileActions.compile_inputs()`이고 Ctrl+B와 MCP `compile_check`가 공유한다.
5. **조용한 실패 금지.** CC가 무시할 키는 배출하지 않고 경고로 알린다. MCP는 잘못된 값·그 타입에
   없는 속성·모호한 지목을 **거부**하며 이유(선택지)를 말한다. 깨진 사용자 파일(JSON·CLAUDE.md
   표식)은 건드리지 않고 경고만 낸다. 참조를 가진 대상을 지울 때는 참조를 몰래 지우지 않고 보고한다
   (지우면 undo로 대상이 돌아와도 참조는 돌아오지 않는다).
6. **산출은 결정적이다** — 같은 모델 → 같은 텍스트, LF, UTF-8(BOM 없음), 정렬 순서 명시.
   **컴파일러가 생성하는 텍스트는 영어**(A12 — 반복 실리는 사용료), 사용자 입력 값은 그대로 나간다
   (`tests/compiler/test_output_language.py`가 게이트).
7. **퇴역 개념은 흔적 없이.** 모델 필드를 삭제하고 구버전 파일은 `serialize.migrate._migrate_v1`
   단방향 마이그레이션으로 흡수한다(호환 잔재를 모델에 남기지 않는다).
8. **외부 CC 규격은 근거를 남긴다.** 공식 문서 확인 날짜, 문서에 없으면 실측(바이너리·실행) 결과를
   설계 문서에 적는다. 훅 규격은 벤더링 스냅샷 + 드리프트 테스트(A4)로 감시한다 — 실패하면 테스트를
   느슨하게 하지 말고 코드를 규격에 맞춘다.
9. **빌드 타깃이 의미를 가른다.** MARKETPLACE는 `plugin.json` 플러그인(CC가 플러그인 서브에이전트의
   `hooks`/`mcpServers`/`permissionMode`를 무시), LOCAL은 **컴파일이 곧 설치**(`.claude/` 반입 +
   `.mcp.json`/settings 병합, 재컴파일 멱등).
10. **사용자 확정 결정은 설계 문서에 "사용자 확정 (날짜)"로 기록**하고, 뒤집을 때는 사용자에게 확인한다.

## 설계 문서 (`docs/design/`)

작업 영역에 해당하는 문서를 **먼저 읽는다**. 문서와 코드가 어긋나면 코드가 정본이고 문서를 즉시 고친다
(코드 위생 스멜 ⑤). 기능을 바꾸면 같은 커밋에서 해당 문서를 갱신한다.

| 문서 | 다루는 것 |
|------|-----------|
| `architecture.md` | 컴파일러 패턴·경계 계약·요약 모듈 지도 + 파일 단위 상세 지도(각 모듈의 책임·분해 이력·테스트 봉합선) |
| `plugin-model.md` | 스킬 6종·에이전트 표, fork 스킬(fork 에이전트 세 종류·전환·실측), `SKILL_FIELD_MATRIX`/`FieldRule`, `FieldType`, 진입 의미론 tri-state + 진입점 프리셋(A8), config 계층 |
| `fsm-model.md` | CompositeState/Region/조인, FSM+블랙보드 하이브리드, body·Section·EventDef, 입력 포트 퇴역(WP-IP), `PluginProject.graph`(EntryPoint 격하 WP-EP), CompletionEvent, 전략 패턴, 안정 ID + 직렬화·마이그레이션 |
| `agents.md` | 에이전트 내부 FSM 퇴역(WP-AF), 출력 포트, 로컬 스킬 승격, 그래프 유도 호출 계약(WP-CT) |
| `wrapped-skills.md` | 외부 플러그인 스킬 랩핑(WP-WR) — 서브에이전트 강제 산출, 사용 선언 배선, 용도 state/reference, 비활성화, 카탈로그·클론 캐시 |
| `blackboard.md` | 최상위 블랙보드·JSON Schema 매핑, 상태 reads/writes 접근 선언(WP-BB), `daedalus-bb` CLI 계약(WP-BB1) |
| `workspace-and-build-target.md` | 빌드 타깃(WP-TG), 작업 폴더 문서 `.claude/CLAUDE.md` 구역·rules `paths:`(WP-WD/A13), 작업 폴더 설정 베이크(WP-WS) |
| `editor.md` | 본문 부분 접근(WP-BO), 엣지 경유점(WP-ER), 드래그 이동(WP-DM), 본문 undo 스택(WP-BU), 삭제 커맨드(A2), 미저장 변경 확인 |
| `mcp-server.md` | 앱 내장 MCP 서버 — 전송·스레드·SDK 호환, 도구 영역별 규약, 패리티 원칙 상세 |
| `hooks.md` | 훅 3단 구조·핸들러 5종·배출 규칙·`enabled`, 라이프사이클 피커(A10), 규격 드리프트 감시(A4), 전역 훅 2단 스코프(A1) |
| `validation.md` | Validator 구성, 머신 수준·프로젝트 수준 규칙 표, skip_rules |
| `project-files.md` | 시작 템플릿(A7), 폴더=프로젝트·`.ddpj`(WP-PK), 공용 `files/`(WP-FR), 스킬별 `skill-files/`(WP-SF) |
| `compiler.md` | 산출 구조(MARKETPLACE/LOCAL), 컴파일 정책 1~20번(게이트·다음 단계·작업 재개·진입 맥락·LOCAL 설치·dry-run·토큰 리포트·위임·fork 스킬), 산출 언어 |

`docs/guide/`는 **사용자 안내서**다(번호 = 읽는 순서: 01 컨셉 · 02 레지스트리 · 03 블랙보드 · 04 로컬 vs 마켓 ·
05 로컬 전용 기능 · 06 MCP). 설계 정본이 아니므로 기능을 바꾸면 해당 안내서도 같은 커밋에서 맞춘다.

`docs/MCP.md`는 같은 MCP 서버를 **쓰는 쪽**(도구 지도·연결·협업 관례) 문서다 — 설계 정본인
`docs/design/mcp-server.md`와 역할이 다르니 한쪽만 고치지 않는다.

`docs/design/`에는 **구현된 사실만** 둔다. 구현되지 않은 모든 것(설계 완료·결정 대기 설계, 제안, 보류, 잔여, 위생,
테스트 부채)은 **`docs/backlog.md` 한 문서**에 모은다 — 끝낸 항목은 거기서 지우고 결과를 `docs/design/`에 반영한다.

## 구현 시 주의사항

### 코드 위생 — 파일 비대 방지 (사용자 확정, WP-RF 재발 방지)

- **파일 크기 경계**: 소스 파일이 ~800줄을 넘으면 분해를 검토하고, **1,200줄
  상한은 `tests/test_code_hygiene.py`가 강제**한다(허용 목록은 비어 있다 — 신규 등재는 규칙 위반).
  기존 큰 파일에 기능을 추가할 때가 분해의 적기다 — 기능을 더하기 전에 먼저 쪼갠다.
- **코드 스멜 감지**: 작업 중 ① 한 파일에 책임 3개 이상 ② 같은 로직 3곳 복제
  ③ 죽은 코드/임포트 ④ 퇴역 개념의 호환 잔재 ⑤ 문서-코드 불일치를 발견하면
  그 자리에서 고치거나 리팩토링 항목으로 보고한다.
- **주기적 리팩토링**: 큰 기능 묶음이 끝날 때마다 파일 크기·스멜을 재실측해
  필요 여부를 보고한다. 분해는 WP-RF 확립 관례를 따른다 — 이동만·동작 불변,
  재-export 파사드, 기존 테스트 무수정 통과, AST/토큰 비교로 이동 충실성 검증.

### ABC + dataclass

`@dataclass class Foo(ABC):`만으로는 인스턴스화가 막히지 않는다.
반드시 `@abstractmethod`가 하나 이상 있어야 TypeError 발생.
이 프로젝트에서는 모든 ABC 클래스에 `@property @abstractmethod kind(self) -> str`를 추가한다.
(Qt 메타클래스와 섞이는 믹스인은 ABC로 만들지 않는다 — 예: `DraggableItemMixin`.)

### dataclass 다중 상속 필드 순서

`ProceduralSkill(Skill, WorkflowComponent)` 같은 다중 상속 dataclass에서
부모의 required 필드(default 없음)보다 앞에 default 필드가 오면 Python 에러가 난다.
자식 클래스에서 부모 필드를 `field(default=None)`으로 오버라이드하지 않는다 —
`fsm`은 required로 유지하고, 테스트에서는 항상 keyword 인수로 전달한다.
안정 ID(`id`)는 `kw_only=True`라 이 제약을 받지 않는다.

### dataclass 동등성 정책

FSM 모델 클래스(State 계열·pseudo 4종·Transition·StateMachine·Region·Section)는
`@dataclass(eq=False)` — identity 동등성 + hashable. 서브클래스에 `@dataclass`를
다시 적용할 때 `eq=False`를 빠뜨리면 `__eq__` 재생성 + unhashable로 되돌아가므로 주의.
plugin 레이어(Skill, AgentDefinition 등)와 값 객체(EventDef, Variable 등)는 기본
dataclass(값 동등성, unhashable) 유지 — 컬렉션 멤버십에는 list/`id()` 사용.

### notify 채널 (structure / content)

`ProjectViewModel.notify(scope=...)`/`add_listener(listener, scope=...)`는 두 채널을 구분한다.
**structure**(기본값, 추가·삭제·이동 — 캔버스 `_rebuild`·레지스트리 등 무거운 리스너)와
**content**(텍스트 키스트로크)는 서로 격리돼 교차 호출이 없다. 둘 다 봐야 하는 리스너(미저장
변경 표시 등)는 **양쪽에 등록**한다. 텍스트 편집 패널은 위젯 재생성으로 편집 중 위젯이 파괴되지
않도록 in-place 동기화한다. `call_notify(fn, scope)`가 scope를 받는 콜백에만 채널을 전달한다.

### 테스트 봉합선과 함정

- 루트 `tests/conftest.py` autouse 픽스처가 격리한다: `MainWindow.confirm_discard_changes`(항상
  True — 확인 다이얼로그가 뜨면 헤드리스 스위트가 멈춘다), 전역 훅 폴더, 사용자 템플릿 폴더, 외부
  마켓플레이스 등록 파일. 실제 홈 디렉토리를 읽는 테스트를 만들지 않는다.
- `_new_project`를 부르는 테스트는 `SessionIO.exec_new_project_dialog`를 스텁한다. 캔버스 wrapped
  드롭은 `FsmScene._ask_wrapped_usage`, 플러그인 클론은 `plugin_cache._shallow_clone`이 봉합선이다.
- MainWindow는 MCP 서버를 자동 기동하지 않는다(`__main__.main`만 기동 — 테스트가 창을 수십 개 만든다).
  작업 폴더 설정 위젯은 지연 생성이다(즉시 만들면 스위트가 타임아웃).
- 캔버스 드래그 검증은 **release 완료 후 vm 좌표로** 한다(드래그 도중·`item.pos()` 단언은 고장을
  숨긴다). 경유점 핸들의 press/release에서 `super()`를 빼거나 `setVisible(False)`로 숨기지 않는다.
- 본문 undo 검증은 **다른 컴포넌트로 전환했다 복귀한 뒤** 한다. 타이핑 시뮬레이션은
  `QTextCursor.insertText`(`setPlainText`는 undo 스택을 지운다).

## 미구현 항목

`docs/backlog.md` — 결정 대기 설계(A5 컴파일 분할·A1 평가 루프·WP-LK 스토어 링크), 제안, 컴파일러 Tier 2(도구·스크립트
실행), 보류, 기능 잔여, 코드 위생·테스트 부채.
