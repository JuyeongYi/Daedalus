# 미구현 항목

> 구현되지 않은 모든 것의 **단일 문서**다(2026-09-12 — 설계 문서·스펙·백로그에 흩어져 있던 미구현 내용을 모으고
> 이미 구현된 부분은 걷어냈다). 구현된 사실은 `docs/design/`에 쓰고 여기에는 두지 않는다. 착수해 끝내면 해당 절을
> 지우고 결과를 `docs/design/`에 반영한다. 상태는 2026-09-12 코드 대조 기준.

## 요약

| 구분 | 항목 | 막힌 지점 |
|------|------|-----------|
| 결정 대기 — 설계 완료 | §1-1 A5 컴파일 분할 | 결정 D1~D7 |
| 〃 | §1-2 A1 평가 루프 | 결정 D1~D9, early access 스펙 |
| 〃 | §1-3 WP-LK 스토어 빌드 + 링크 | 잔존 의문 U2~U8 |
| 결정 대기 — 제안 단계 | §2 fork 후속(랩핑 실행 에이전트 합치기) · reference 랩핑의 스킬 링크 예외 · statusLine 도구 · 외부 에이전트 노드 · 컴포넌트 도입문 2차 호이스트 · `get_project` 축약 기본값 | 사용자 결정 |
| 규격 정정 후속 | §5 스킬 훅 — 지운 참조 복구 여부 · 중복 실행 미실측 | 사용자 확인 |
| 컴파일러 Tier 2 | §3 도구·스크립트 실행 래퍼, 외부 오케스트레이터 | 설계 전 |
| 보류 | §4 기존 플러그인 임포트 · 블랙보드 단락 rules 이관 · Region 확장 | 개시 미정 |
| 잔여 · 제약 · 위생 · 테스트 | §5~§8 | — |

## 1. 결정 대기 — 설계 완료

### 1-1. A5 — 컴파일 분할(점진 공개) (2026-08-25)

#### 1. 문제

SKILL.md가 커지면 CC는 그 스킬을 인보크할 때마다 본문 **전체**를 컨텍스트에
싣는다. 실사용 스킬 본문이 수백 줄에 이르면, 그 시점에 필요 없는 단락까지
매번 따라 들어와 컨텍스트를 잠식한다.

CC 공식 패턴은 **progressive disclosure**다: SKILL.md는 짧게 유지하고, 무거운
내용은 스킬 디렉토리 안의 보조 파일로 빼서 본문이 **언제 그 파일을 읽어야
하는지**만 알려 준다. 필요할 때만 Read가 도는 구조다.

재료는 전부 구현돼 있다 — `model/outline.py`(분할 지점: 코드 펜스 제외 헤딩 파서), WP-SF `skill-files/` + `${CLAUDE_SKILL_DIR}`(파일 위치), WP-BO의 "구조는 파생으로만" 원칙.

#### 2. 원칙 — 저장 모델은 건드리지 않는다

**분할은 컴파일 시점의 파생이다.** `body`는 계속 마크다운 한 덩이이고, 편집기와
MCP(`get_body_section`/`set_body_section`)가 보는 것도 그대로다. 저장을 섹션
트리로 바꾸는 순간 마크다운↔트리 무손실 왕복 파서가 필요해지고, "저장했더니
본문이 미묘하게 달라짐" 류의 최악의 버그가 생긴다(WP-BO에서 이미 내린 결론).

따라서 이 기능은 **`compiler/emit/skill.py`와 `project_compiler.py`에만** 들어간다.
모델·직렬화·에디터 변경 없음.

#### 3. 무엇을 자르는가

##### 3-1. 자르는 대상은 사용자 본문뿐이다

`compile_skill`이 만드는 블록은 두 종류다:

- **사용자 본문** — `_body_block(skill.body)` 하나.
- **자동 단락** — 작업 재개(WP-RS) · 진입 맥락(WP-IC) · FSM 절차 · tool_shelf ·
  블랙보드(WP-BB2 CLI 지시 포함) · 요구 환경 · 다음 단계 / 작업 완료.

**자동 단락은 절대 분할하지 않는다.** 이것들은 "지금 무엇을 하고 어디로 가는가"를
말하는 제어 정보라, 파일로 빼면 그것을 읽으라는 지시를 읽기 위해 또 본문이
필요해진다. 분할 대상은 `skill.body`에서 파생된 블록 **하나**뿐이다.

##### 3-2. 자르는 지점 — 최상위 헤딩(H2) 경계

`parse_outline(body)`에서 **본문의 최상위 레벨** 헤딩을 고르고, 그 각각의
`line_start..line_end` 구간을 후보 섹션으로 삼는다.

"H2"라고 못 박지 않고 **본문에 실제로 나타나는 가장 얕은 레벨**로 잡는 이유는,
사람마다 본문을 `#`로 시작하기도 하고 `##`로 시작하기도 하기 때문이다. 고정
레벨로 자르면 `#`로 쓴 문서는 통째로 한 덩이가 되어 아무것도 분할되지 않는다.

- 첫 헤딩보다 **앞**에 오는 도입부(preamble)는 자르지 않고 SKILL.md에 남긴다 —
  스킬이 무엇인지 말하는 부분이라 항상 필요하다.
- 하위 헤딩(H3 이하)은 부모 섹션에 **딸려 간다**. 더 잘게 자르면 파일이 늘어나고
  색인이 본문만큼 길어져 이득이 사라진다.

##### 3-3. 자를지 말지 — 임계값 두 개

```
분할 대상 = (SKILL.md 예상 크기 > SPLIT_THRESHOLD)
            AND (섹션 크기 >= SECTION_MIN)
```

- **`SPLIT_THRESHOLD`**: 이 크기 아래면 **아무것도 자르지 않는다**. 작은 스킬을
  쪼개면 Read 왕복만 늘고 컨텍스트는 오히려 커진다.
- **`SECTION_MIN`**: 임계를 넘긴 스킬 안에서도 이 크기 미만 섹션은 남긴다.
  세 줄짜리 섹션을 파일로 빼면 색인 줄이 그 섹션보다 길다.

단위는 **문자 수**로 한다(토큰 추정은 모델마다 다르고, 줄 수는 줄 길이를 무시한다).
구체적 값은 §7의 확정 대상.

#### 4. 산출 형상

```
skills/<skill-name>/
  SKILL.md                 # 프론트매터 + 자동 단락 + 도입부 + 남은 섹션 + 색인
  sections/<slug>.md       # 잘려 나간 섹션 (헤딩 줄 포함)
```

`sections/`를 한 겹 두는 이유: WP-SF의 `skill-files/<스킬>/`가 같은 디렉토리로
복사되므로, 평평하게 두면 사용자 파일과 생성 파일이 섞여 어느 것이 손으로 둔
것인지 알 수 없게 된다. 하위 폴더로 나누면 **경로만 보고 구분된다**.

##### 4-1. 슬러그

`<slug>` = 섹션 제목을 소문자화하고 `[a-z0-9]` 외 문자를 `-`로 바꾼 뒤 중복 `-`를
접고 앞뒤를 트림한 것. 비면 `section`, 충돌하면 `-2`, `-3`… (컴포넌트 개명
충돌 해소와 같은 관례). 한글 제목은 전부 소거되어 빈 문자열이 되므로 **`section-N`
(N = 문서 내 등장 순서)** 로 떨어진다 — §7의 확정 대상.

##### 4-2. SKILL.md에 남는 색인

잘려 나간 자리에 색인 줄을 남긴다. 색인은 **원래 순서 그대로**, 원래 헤딩 레벨을
유지한 채 들어간다 — 본문을 훑는 사람이 목차 구조를 잃지 않게.

```markdown
## <섹션 제목>

이 단락은 `${CLAUDE_SKILL_DIR}/sections/<slug>.md`에 있다. <필요할 때 읽으라는 조건 한 줄>.
```

조건 한 줄을 무엇으로 채우는가가 이 기능의 성패를 가른다 — "필요하면 읽어라"는
아무 정보도 주지 않아 모델이 전부 읽거나 전부 안 읽는다. §7의 확정 대상.

##### 4-3. 참조 토큰

`${CLAUDE_SKILL_DIR}`를 쓴다(WP-SF에서 확인한 CC 공식 변수 — 마켓플레이스/로컬
동일 동작이라 `${ROOT}` 같은 타깃 중립화가 필요 없다). **에이전트는 대상이
아니다** — 단일 `.md`라 전용 디렉토리도 이 변수도 없다(`skill_dir_token_in_agent`
경고가 이미 그것을 짚는다).

#### 5. 결정성

컴파일 산출은 "같은 모델 → 같은 텍스트"가 계약이다. 분할이 그것을 깨지 않도록:

1. **분할 판정은 본문 문자열만 본다.** 파일시스템·환경·시각을 보지 않는다.
2. **슬러그 충돌 해소는 문서 등장 순서**로 한다(집합 순회 금지).
3. **크기 판정은 분할 **전** 본문 기준으로 한 번만 계산한다.** "자르고 나서 다시
   재 보고 또 자른다"는 반복은 임계 근처에서 진동하고, 섹션 하나를 고쳤을 뿐인데
   다른 섹션의 분할 여부가 바뀌는 결과를 낳는다.
4. **`sections/` 파일도 산출 계획(`_plan_outputs`)에 합류시킨다.** 그래야 기존
   `compile_output_path_conflict` 게이트가 WP-SF 동봉 파일과의 충돌을 잡는다 —
   사용자가 `skill-files/<스킬>/sections/x.md`를 두었는데 분할이 같은 경로를
   만들면 조용한 덮어쓰기가 된다. **새 게이트를 만들 필요가 없다는 것이 이
   설계에서 계획 집합을 재사용하는 이유다.**

#### 6. 자동 단락과의 상호작용

- **"다음 단계" / "작업 완료"(WP-RS)는 SKILL.md에 남는다.** 진행 사슬이 여기서
  끊기면 워크플로가 멈춘다.
- **"작업 재개" / "진입 맥락"도 남는다.** 본문보다 **앞**에 배출되는 블록이라
  분할 대상 구간에 애초에 들어오지 않는다.
- **블랙보드 CLI 지시(WP-BB2)도 남는다.** 상태 파일을 어떻게 읽고 쓰는지는
  거의 모든 단계에서 필요하다.
- **본문의 `${CLAUDE_PLUGIN_ROOT}`/`${ROOT}` 파일 참조와 `${CLAUDE_SKILL_DIR}`
  참조는 잘린 조각 안에서도 그대로 동작한다** — 두 변수 모두 런타임 치환이고
  파일 위치와 무관하다. 다만 `${ROOT}` 확장(`expand_root_token`)을 **잘린 조각
  텍스트에도 적용**해야 한다. 지금은 SKILL.md 텍스트에만 걸려 있어, 그대로 두면
  분할된 조각에서만 토큰이 리터럴로 남는다. **구현 시 가장 놓치기 쉬운 지점.**
- **`dangling_file_ref` / `dangling_skill_file_ref` 스캔은 `skill.body`(정본)를
  보므로 영향 없다** — 스캔 대상이 산출 텍스트가 아니라 모델이다.

#### 7. 사용자 확정이 필요한 결정

실측 수단은 이미 있다 — 토큰 비용 리포트(A5-lite, `CompileResult.token_report`)가 산출 파일별 크기를 낸다.

| # | 결정 | 선택지 | 설계자 권고 |
|---|---|---|---|
| D1 | 분할을 **켤 것인가, 기본값은 무엇인가** | ⓐ 항상 자동 ⓑ 프로젝트 속성 토글(기본 off) ⓒ 스킬별 필드 | **ⓑ** — 산출 형상이 크게 바뀌므로 기존 프로젝트가 재컴파일만으로 달라지면 안 된다. `emit_progress_hook`과 같은 자리에 토글. |
| D2 | `SPLIT_THRESHOLD` | 예: 4,000 / 8,000자 | 실사용 스킬 본문 길이를 실측한 뒤 정한다. 근거 없는 숫자를 코드에 박지 않는다. |
| D3 | `SECTION_MIN` | 예: 800 / 1,500자 | 위와 같이 실측 후. |
| D4 | 색인의 "언제 읽어라" 문구를 **어디서 얻는가** | ⓐ 고정 문구 ⓑ 섹션 첫 문장 발췌 ⓒ 헤딩 뒤 인텍스트 속성(`{when=...}`) ⓓ 스킬별 수동 매핑 | **ⓑ + ⓐ 폴백** — 저장 모델을 안 건드리면서 실질 정보를 준다. ⓒ는 WP-BO가 남겨 둔 확장(B안)이지만 마크다운 문법을 오염시킨다. |
| D5 | 한글 제목 슬러그 | ⓐ `section-N` ⓑ 원문 유지(UTF-8 파일명) ⓒ 로마자 전사 | **ⓐ** — 파일명 인코딩 문제를 만들지 않고 결정적이다. 사람이 읽을 이름은 색인 줄에 이미 있다. |
| D6 | 분할 결과를 **미리 볼 수 있어야 하는가** | ⓐ 필요 없음 ⓑ `compile_preview`가 SKILL.md만 ⓒ 조각까지 함께 | **ⓒ** — 무엇이 잘려 나갔는지 못 보면 임계값을 조정할 방법이 없다. |
| D7 | 잘린 조각이 있을 때 **경고를 내는가** | ⓐ 조용히 ⓑ 정보성 경고 1건 | **ⓑ** — "왜 SKILL.md가 짧아졌지"에 대한 답이 결과에 있어야 한다. |

#### 8. 구현 순서 (확정 후)

1. `compiler/split.py` (신규, 순수 함수) — `plan_split(body, threshold, section_min)
   → (남는 본문 텍스트 + 색인, [(slug, 조각 텍스트)])`. 파일시스템 무접근,
   문자열 in / 문자열 out이라 단위 테스트가 전부 문자열 비교다.
2. `emit/skill.py` — `compile_skill(..., split=None)`. `split`이 없으면 **산출
   바이트 불변**(하위 호환 게이트, WP-FR/WP-SF/A1과 같은 관례).
3. `project_compiler.py` — 조각을 `_plan_outputs`의 계획 항목(`kind="skill_section"`)으로
   합류. 경로 충돌 게이트가 자동으로 따라온다.
4. `compile_preview` (MCP) — D6에 따라 조각 목록 동봉.
5. 테스트: 임계 미만 불변 / 임계 초과 분할 / 슬러그 충돌 / 결정성(두 번 컴파일
   바이트 동일) / `${ROOT}` 확장이 조각에도 적용 / WP-SF 동봉 파일과의 경로 충돌
   게이트 / 자동 단락이 잘리지 않음.

#### 9. 하지 않는 것

- **저장 모델 변경**(섹션 일급 객체화 = WP-BO의 C안). 섹션을 여러 스킬이 공유해야
  한다는 요구가 실재할 때 다시 꺼낸다.
- **에이전트 분할.** 전용 디렉토리가 없다(§4-3).
- **자동 단락 분할.** §3-1.
- **본문 자동 요약.** 색인 문구를 LLM으로 만들면 컴파일이 결정적이지 않게 된다.

### 1-2. A1 — 평가 루프: 그래프 → `claude plugin eval` 스켈레톤 (2026-09-06)

#### 0. 전제 — 스펙의 지위

`claude plugin eval`은 **early access**다. 공식 문서 페이지가 없고, 이 설계의
근거는 조사 시점(2026-09)의 오프라인 참고 자료 + `--help` 출력이다. 조사에서
확정된 계약 중 이 설계가 의존하는 것:

- 스위트 위치: 플러그인 폴더의 `evals/`(기본) — `--eval-dir <dir>` 또는
  `plugin.json`의 `"experimental": {"evals": "<dir>"}`로 변경 가능.
- 케이스 = 디렉토리 1개: `prompt.md`(필수, YAML 프론트매터 — 필수 필드는
  `name` 하나) + `graders/<이름>.md`(각각 프론트매터로 타입 선언) +
  `case.yaml`(선택 — `scaffold_script`, `history_file`, `add_dirs`).
- 그레이더 타입 6종: `regex` / `tool_used` / `tool_order` / `file_exists` /
  `llm` / `baseline`. 타깃은 `last_message`(기본) / `trace` /
  `{source: file, path}`(에이전트가 만든 파일 내용).
- 스킬 발화 검사 공식 idiom:
  `type: tool_used, tool: Skill, input_match: '"skill"\s*:\s*"(?:[\w-]+:)?<이름>"'`.
- 샌드박스: run마다 새 임시 워크스페이스 + 독립 `HOME`/`CLAUDE_CONFIG_DIR`,
  지정 플러그인만 로드, scaffold 스크립트는 run 시작 전 실행.

이 계약은 유동적이다 — **드리프트 방어는 §7에서 설계에 직접 반영한다**
(A4 벤더링 관례 연계). 스펙이 바뀌어도 산출이 전부 평문 마크다운이라 사람이
그 자리에서 고칠 수 있다는 것이 마지막 방어선이다.

#### 1. 문제

지금 컴파일러의 보증은 "일관된 산문"까지다 — 전이 문구·진행 기록 규칙·블랙보드
CLI 지시가 서로 모순 없이 배출되는 것은 테스트가 고정하지만, **그 산문을 모델이
실제로 따르는지**는 아무도 검증하지 않는다. worker 훅 미작동류의 사고는 전부
이 간극에서 났다.

CC가 그 간극을 재는 도구(`claude plugin eval`)를 내놓았고, Daedalus는 남들이
손으로 써야 하는 평가 케이스의 골격을 **그래프에서 유도**할 수 있다. FSM으로
설계했기 때문에 공짜로 나오는 구조 — 전이 하나 = 검증 가능한 기대 하나 — 가
이 도구의 차별점이 된다.

#### 2. 원칙

1. **유도는 골격까지, 시나리오는 사람 몫이다.** 어떤 입력이 어느 갈래를 타야
   하는지(가드의 참/거짓)는 그래프에 없다 — 그래프에 있는 것은 "갈래를 탔다면
   무엇이 관측되어야 하는가"뿐이다. 자동 유도는 후자만 만든다.
2. **자동 부분이 틀리면 손으로 고칠 수 있어야 한다.** 산출은 전부 평문
   마크다운/YAML이고, 소유권 경계(§5)가 파일 이름으로 드러나며, 재생성은
   자동 소유 파일만 건드린다.
3. **컴파일의 결정성 계약을 오염시키지 않는다.** 스켈레톤 생성은 컴파일과
   별개의 액션이다(§4-3) — 컴파일은 "같은 모델 → 같은 텍스트"지만, 스켈레톤은
   "없을 때만 만들고 사람이 소유하는 scaffold"라 성격이 다르다.
4. **산출 언어는 영어다(A12).** 그레이더 기준·프롬프트 TODO 문구·주석은
   판사 LLM과 평가 대상 모델이 소비한다. 사용자 값(스킬 이름·transfer_on
   description)은 그대로 통과한다.

#### 3. 그래프 → 평가 항목 사상

##### 3-1. 유도 가능 — 결정적

| 그래프 요소 | 평가 항목 | 그레이더 |
|---|---|---|
| transfer_on 갈래(스킬 타깃 전이) | 그 갈래를 탔다면 후속 스킬이 인보크된다 | `tool_used` + `tool: Skill` + 공식 idiom regex(후속 스킬 이름) |
| 진행 기록 규칙(WP-RS/WP-IC) | 갈래 통과 후 `state/__progress__.json`에 `"prev": "<출발 스킬>"`이 있고 `note`에 갈래(출력 이벤트 이름)가 등장한다 | `regex` + `target: {source: file, path: state/__progress__.json}` (match: contains) |
| 터미널 배치("## 작업 완료") | 완료 시 진행 파일의 해당 스킬 항목이 `"current": "done"` | 위와 같은 `regex`(파일 타깃) |
| 블랙보드 writes 선언 | 해당 클래스 상태 파일이 생성된다 | `file_exists` + `path: state/<플러그인>/<Class>.json` |
| 갈래 커버리지(집계) | 모든 출력 이벤트가 최소 1회 행사 | 케이스 단위 자체가 커버리지다 — 갈래당 케이스 1개(§4-1)이므로 스위트의 pass/fail 표가 곧 커버리지 보고서 |
| 중간 갈래의 재현(선행 단계 생략) | 출발 스킬에서 시작하는 상태를 조성 | `case.yaml`의 `scaffold_script`가 진행 파일을 시드(`current: <출발 스킬>`) — WP-RS 재개 프리앰블이 그 위치에서 재개하게 만든다 (D6) |

진행 기록 단언에서 `prev`를 축으로 잡는 이유: 규약상(WP-IC) `prev`에는 출발
스킬 이름이, `note`에는 갈래 이름이 남는다 — 둘 다 그래프에서 정확한 기대
문자열을 알 수 있는 유일한 필드다. `updated`(타임스탬프)·`note`의 자유 서술부는
값 단언이 불가능하므로 존재/포함만 본다.

##### 3-2. 유도 가능 — 대리(proxy) 검증, 약함을 명시

| 그래프 요소 | 대리 항목 | 왜 약한가 |
|---|---|---|
| 에이전트 위임 전이(call_agents 포트) | `tool_used` + `tool: Task` + `input_match`(에이전트 이름) | 조사 결과 "agent 호출 자체는 불가, tool_used regex로 대리 가능" — 서브에이전트 호출 도구의 입력 형상이 공식 미기재라 regex가 스펙 변경에 취약하다. 생성 파일에 fragile 주석을 명시한다 |
| TransferSkill 수행(A11 — 전이 위의 1:1 중간 상태) | `tool_used` + `tool: Skill` + idiom regex(전이 스킬 이름) | 출발 스킬 지시("follow transition skill X")를 모델이 Skill 인보크가 아니라 본문 인라인 수행으로 따를 수도 있다 — 미인보크가 곧 규약 위반은 아니다 |
| 블랙보드 reads 선언 | `tool_used` + `tool: Bash` + `input_match`(`daedalus-bb read <Class>`) | 모델이 CLI 대신 Read 도구로 읽어도 규약 위반이 아니다(CLI는 "있으면 우선"이지 강제가 아니다 — WP-BB2 fail-open) |
| 블랙보드 스키마 적합성 | `tool_used` Bash `daedalus-bb validate` 또는 `trace` 타깃 regex | 그레이더는 셸을 실행하지 못하므로 "validate를 돌렸는가"까지만 — 통과 여부는 trace 로그 형상(공식 미기재)에 의존한다. v1 스켈레톤에서 제외 권고(D7) |

대리 검증은 **기본 생성에 넣되 파일 안에 근거와 한계를 주석으로 남긴다** —
지우는 것도, 강화하는 것도 사람이 파일을 보고 판단할 수 있어야 한다(원칙 2).

##### 3-3. 유도 불가 — 명시적 제외

| 항목 | 왜 불가한가 |
|---|---|
| 가드 판정의 참/거짓(어느 갈래를 **타야 하는가**) | 시나리오(입력)가 결정한다 — 그래프에는 없다. 프롬프트 본문이 사람 몫인 이유 그 자체 |
| FSM 내부 상태 도달(스킬 내부 절차의 어느 단계인가) | 에이전트 세션은 내부 상태를 노출하지 않는다(black box) — 조사에서 명시 확인 |
| 훅 발화 여부(Pre/PostToolUse가 실제로 돌았는가) | `trace` 타깃으로 가능**할 수도** 있으나 공식 미기재 — 추측 스펙에 생성물을 박지 않는다(배치 스펙의 "스펙을 추측으로 박으면 A4가 막으려는 드리프트를 자초한다") |
| 블랙보드 필드 **값**의 의미적 정확성 | 스키마는 형상만 안다. `llm` 그레이더 자리(criteria TODO)만 만들어 두고 기준은 사람이 채운다 |
| 에이전트 내부 작업 과정 | 위임 이후는 별도 컨텍스트 — 관측 창구가 없다 |
| 낙관적 잠금(A6)·병렬 쓰기 생존 | 단일 세션 평가로는 경쟁 조건을 재현할 수 없다 — CLI 단위 테스트의 영역 |

#### 4. 산출 형상

##### 4-1. 케이스 단위 = transfer_on 갈래 1개

```
<프로젝트 폴더>/evals/
  <스킬>--<이벤트-slug>/          # 갈래 케이스 (배치 스킬 × 출력 이벤트)
    prompt.md                     # 사람 소유 — 없을 때만 생성(TODO 본문)
    case.yaml                     # 자동 소유 — scaffold_script(진행 파일 시드)
    graders/
      auto-invoke.md              # 자동 소유 — 후속 인보크(§3-1/3-2)
      auto-progress.md            # 자동 소유 — 진행 파일 regex
      auto-bb-<class-slug>.md     # 자동 소유 — writes 클래스당 file_exists
      <아무 이름>.md              # 사람 소유 — auto- 접두가 아니면 불가침
  <스킬>--terminal/               # 터미널 배치 케이스 (outgoing 0개 배치)
    ...                           # auto-progress가 current=done을 단언
```

- 갈래당 케이스 1개로 쪼개는 이유(스킬당 1개 + 그레이더 여러 개가 아니라):
  케이스의 pass/fail이 곧 **갈래 커버리지 표**가 되고, `--case "<스킬>--*"`
  글롭 필터로 스킬 단위 재실행이 성립한다. 한 케이스에 갈래 여럿을 넣으면
  한 프롬프트가 여러 갈래를 동시에 타야 해서 시나리오 작성이 불가능해진다.
- 케이스 이름 slug: A5 §4-1 관례 재사용 — 소문자화, `[a-z0-9]` 외 → `-`,
  중복 `-` 접기, 앞뒤 트림. 빈 결과(한글 이벤트 이름)는 `event-N`(N = 그 스킬
  transfer_on 선언 순서), 충돌은 `-2` 접미. 스킬 이름은 이미
  `^[a-z0-9][a-z0-9-]*$` 규약이라 slug가 항등이다.
- 미배치 스킬·에이전트 자체(.md)는 케이스를 만들지 않는다 — 진행 기록도
  "다음 단계"도 배치에만 배출되므로 단언할 규약이 없다. 에이전트 위임은
  **호출자 스킬의 갈래 케이스** 안에서 대리 검증된다(§3-2).

##### 4-2. 파일 내용 골격

`prompt.md`(사람 소유 — 생성은 최초 1회, 이후 불가침):

```markdown
---
name: "<스킬>--<이벤트-slug>"
tags: ["<플러그인>", "<스킬>", "branch-coverage"]
# runs/max_turns/model: 기본값 위임 — 필요 시 사람이 지정
---

TODO: Write a scenario that reaches skill `<스킬>` and drives the
`<이벤트>` branch (<transfer_on description 인용>).
The graders below assert what must be observable *after* the branch fires.
```

`case.yaml`(자동 소유):

```yaml
schema_version: "1.1"
name: "<스킬>--<이벤트-slug>"
context:
  scaffold_script: |
    mkdir -p state
    printf '%s' '{"<플러그인>": {"current": "<스킬>", "completed": [], "note": "", "prev": ""}}' \
      > state/__progress__.json
```

시드가 있으면 프롬프트는 "resume the work"만으로 출발 스킬에서 시작한다 —
WP-RS 재개 프리앰블("`current`가 이 스킬이면 거기서 재개")이 그대로 작동하는
경로다. 선행 단계 전체를 프롬프트로 재현시키는 것보다 결정적이고 싸다(D6).

`graders/auto-invoke.md`(자동 소유, 스킬 타깃 갈래):

```markdown
---
type: tool_used
tool: Skill
input_match: '"skill"\s*:\s*"(?:[\w-]+:)?<후속 스킬>"'
min: 1
---

After taking the `<이벤트>` branch, the workflow must invoke skill
`<후속 스킬>` (transition declared in the Daedalus project graph).
```

`graders/auto-progress.md`(자동 소유):

```markdown
---
type: regex
pattern: '"prev":\s*"<출발 스킬>"'
match: contains
target: { source: file, path: "state/__progress__.json" }
---

The progress record convention (Daedalus WP-RS/WP-IC) requires `prev` to
hold the departing skill after this branch fires.
```

##### 4-3. 생성 경로 — 컴파일이 아니라 별도 액션

- **구현 위치:** `compiler/evals.py`(신규, 순수 함수 — Qt·파일시스템 무접근).
  `plan_eval_skeleton(project) → list[(상대 경로, 텍스트, owner)]`(owner =
  auto/human). 파일 쓰기는 호출자(MCP 도구·GUI 메뉴)가 한다 — `workspace.py`/
  `wiring.py`와 같은 배치(순수 계산과 IO의 분리).
- **호출부:** MCP 도구 `generate_eval_skeleton`(프로젝트 폴더 `evals/`에 기록,
  결과로 생성/갱신/보존 목록 반환) + GUI 도구 메뉴 항목. 미저장 프로젝트
  (`_current_path` None)는 files/와 같은 정책으로 거부.
- **정본은 프로젝트 폴더 `evals/`다** — files/·skill-files/와 같은 가족:
  파일시스템이 단일 진실, Save As의 `SessionIO.carry_files_dir`가 동반 복사 대상에
  추가, `.ddpj` 패키지에 자연 포함(폴더가 곧 프로젝트 — WP-PK).
- **컴파일 통합은 복사뿐이다(MARKETPLACE, D2):** `compile_project`가 files/
  복사와 같은 관례로 `<out>/evals/`에 정렬 순회 복사 — 산출 플러그인 폴더를
  target으로 주면 `--eval-dir` 없이 기본 위치에서 발견된다. 유도 로직은
  컴파일 경로에 넣지 않는다(원칙 3).
- **LOCAL은 복사하지 않는다(D3):** out_dir가 사용자의 작업 폴더라 `evals/`를
  쓰면 오염이고, LOCAL엔 plugin.json도 없어 eval target 개념이 성립하지
  않는다. 실행은 `claude plugin eval --eval-dir <프로젝트>/evals` 형태로
  프로젝트 폴더를 직접 가리킨다(실행 연동 자체가 후속 범위다).

##### 4-4. 결정성 규칙

1. **순회 순서 고정:** 케이스는 (스킬 이름순, 갈래는 transfer_on 선언 순),
   그레이더는 고정 이름, 블랙보드 클래스는 이름순. 집합 순회 금지.
2. **생성 판정은 모델만 본다** — 파일시스템·시각·환경 무접근(순수 함수).
   기존 파일 보존 판정(있으면 건너뜀)은 호출자의 IO 계층에서 한다.
3. **같은 모델 → 같은 계획.** `plan_eval_skeleton`은 두 번 불러 같은
   (경로, 텍스트) 목록을 내야 한다 — 테스트로 고정.
4. **LF·UTF-8(BOM 없음)** — 컴파일 산출과 같은 계약.

#### 5. 사람/자동의 소유권 경계

| 소유 | 파일 | 재생성 시 |
|---|---|---|
| 사람 | `prompt.md`, `graders/`의 `auto-` 접두 아닌 파일 | **불가침** — 존재하면 절대 덮지 않는다 |
| 자동 | `case.yaml`, `graders/auto-*.md` | 항상 재생성(그래프가 정본). 그래프에서 사라진 갈래의 케이스 디렉토리는 **auto 파일만 삭제**하고, 사람 파일이 남아 있으면 디렉토리를 지우지 않고 고아 경고를 낸다 |

- 경계가 **파일 이름으로 드러난다** — 어느 파일을 고쳐도 되는지 열어 보지
  않고도 안다. 마커 주석 방식(CLAUDE.md 구역 병합류)을 쓰지 않는 이유:
  eval 파일은 통째로 사람이 다듬는 물건이라 "파일 안 일부 구역"이 아니라
  "파일 전체"가 소유 단위여야 하고, 사람이 auto 파일을 손보고 싶으면
  `auto-` 접두를 떼고 이름을 바꾸면 된다(그 순간 소유권이 넘어간다).
- 자동 그레이더가 틀렸을 때의 복구 경로 둘 다 성립: ① 이름을 바꿔 소유권을
  가져간다(재생성이 같은 이름의 auto 파일을 또 만들면 자기 것이 이긴다 —
  판사에겐 그레이더가 하나 더 보일 뿐이므로 고아 auto 파일 경고로 짚는다)
  ② 그래프를 고치고 재생성한다(그래프가 틀린 경우 — 이쪽이 정도).

#### 6. 검증·기존 표면과의 상호작용

- **새 Validator 규칙은 이 배치에서 만들지 않는다.** evals/는 산출 규약이
  아니라 개발 보조물이고, 검증기는 파일시스템 무접근 순수성을 유지한다.
  고아 케이스(그래프에서 사라진 갈래) 경고는 `generate_eval_skeleton` 결과와
  GUI 다이얼로그가 보고한다 — `dangling_file_ref`가 컴파일러 소관인 것과
  같은 배치.
- **`compile_output_path_conflict` 게이트:** MARKETPLACE 복사(D2 채택 시)는
  `<out>/evals/`가 기존 계획 경로(skills/·agents/·files/·schemas/·hooks/·
  `.claude-plugin/`)와 애초에 겹치지 않지만, files/ 복사와 같은 관례로 계획
  집합에 합류시켜 게이트를 공유한다(A5 §5-4와 같은 이유 — 새 게이트를 만들지
  않는다).
- **A5-lite 토큰 리포트와 무관** — evals/는 컨텍스트에 실리지 않으므로 토큰
  계기판 대상이 아니다.

#### 7. 스펙 드리프트 방어 (A4 관례 연계)

1. **조사 스냅샷 벤더링:** 이 설계가 의존하는 스펙 표면(§0 목록 — 디렉토리
   규약·프론트매터 키·그레이더 타입/필드·idiom regex)을
   `docs/specs/claude-plugin-eval-<날짜>.md`로 저장소에 벤더링한다(구현 시점에
   재조사해 갱신 — A4의 SchemaStore 스냅샷과 같은 지위, 날짜 기록).
2. **생성물의 스펙 결합면을 한 곳에 모은다:** 프론트매터 키 문자열·그레이더
   타입 이름·idiom regex는 `compiler/evals.py`의 모듈 상수로만 존재하게 한다 —
   스펙이 바뀌면 고칠 곳이 하나다.
3. **테스트는 네트워크 무접근:** 생성 텍스트의 형상(키 집합·타입 이름)을
   벤더링 스냅샷 문서와의 문자열 일치로 고정한다 — `daedalus-bb` CLI 지시
   드리프트를 `test_blackboard_section.py`가 파서와의 문자열 일치로 막는 것과
   같은 수법.
4. **실행 스모크는 후속 범위다.** 이 환경에서 early access 게이트가 닫혀 있어
   (`"currently in early access"`) 실행 검증이 불가능하다 — 배치 스펙도 "실행
   연동(CI 등)은 후속"으로 못 박았다. 스켈레톤이 실제 러너에서 로드되는지는
   게이트가 열린 뒤 확인 항목으로 남긴다(§9).
5. **최소 표면만 쓴다:** 프론트매터는 필수 필드(`name`) + 안정적 이득이 있는
   것(tags, scaffold_script)만. `env`·`ablation`·`history_file` 등 고급 표면은
   생성물에 넣지 않는다 — 결합면이 좁을수록 드리프트 피해가 작다.

#### 8. 사용자 확정이 필요한 결정

| # | 결정 | 선택지 | 설계자 권고 |
|---|---|---|---|
| D1 | 스켈레톤 유도의 진입점 | ⓐ 컴파일 플래그 ⓑ 프로젝트 속성 토글(컴파일에 합류) ⓒ 별도 액션(MCP 도구 + GUI 메뉴) | **ⓒ** — 컴파일은 결정적 산출 계약이고 스켈레톤은 "없을 때만 만드는" scaffold라 성격이 다르다(원칙 3). ⓐ/ⓑ는 사람 소유 파일의 보존 판정을 컴파일에 끌어들여 "같은 모델 → 같은 산출"을 깬다 |
| D2 | MARKETPLACE 산출에 `evals/` 복사 | ⓐ 복사(기본 위치에서 발견) ⓑ 복사 안 함(`--eval-dir`로 실행) | **ⓐ** — target을 산출 폴더로 주면 추가 플래그 없이 돌고, files/ 복사 관례를 그대로 재사용한다. 배포 패키징에서 빼고 싶다는 요구가 실재하면 그때 토글을 단다 |
| D3 | LOCAL 빌드에서의 취급 | ⓐ 산출 안 함(프로젝트 폴더 정본만) ⓑ `<out>/daedalus-evals/<플러그인>/`로 반출 | **ⓐ** — LOCAL out은 사용자 작업 폴더라 개발 보조물 반출은 오염이고, eval target(plugin.json) 개념도 없다. 실행은 `--eval-dir`로 프로젝트 폴더를 직접 가리킨다 |
| D4 | 케이스 단위 | ⓐ 갈래당 1케이스 ⓑ 스킬당 1케이스(그레이더 병렬) | **ⓐ** — pass/fail 표가 곧 갈래 커버리지가 되고, 한 프롬프트가 한 갈래만 타면 되므로 시나리오 작성이 성립한다(§4-1) |
| D5 | 블랙보드 단언의 강도 | ⓐ `file_exists`만 ⓑ + required 필드당 존재 regex ⓒ + `llm` 스키마 적합성 판사 | **ⓑ** — ⓐ는 빈 파일도 통과하고, ⓒ는 결정적 검사를 주관 판사에 맡겨 노이즈만 는다. required 필드 regex는 스키마에서 결정적으로 유도된다. 값의 의미 판정은 사람 소유 `llm` 그레이더 자리로 남긴다(§3-3) |
| D6 | `scaffold_script`로 진행 파일 시드 | ⓐ 시드(출발 스킬에서 재개) ⓑ 시드 없이 프롬프트가 처음부터 유도 | **ⓐ** — 중간 갈래 케이스가 선행 단계 전체의 재현에 의존하면 비결정·고비용이고, WP-RS 재개 규약을 그대로 쓰는 것이라 별도 발명이 없다. 진입점(첫 배치) 케이스는 시드 없이 생성한다 |
| D7 | `daedalus-bb validate` 실행 단언 포함 | ⓐ v1 제외 ⓑ `tool_used` Bash 대리 ⓒ trace regex | **ⓐ** — CLI 사용은 강제가 아니라 "있으면 우선"(fail-open)이라 미실행이 규약 위반이 아니고, trace 형상은 공식 미기재다. 스키마 적합성의 결정적 부분은 D5-ⓑ가 담당한다 |
| D8 | 에이전트 위임 대리 그레이더(`tool_used` Task) 포함 | ⓐ 포함 + fragile 주석 ⓑ 제외(사람이 필요 시 추가) | **ⓐ** — 위임 갈래에 그레이더가 하나도 없으면 케이스가 빈 껍데기가 된다. 주석에 근거·한계를 남겨 사람이 지우거나 강화할 수 있게 한다(§3-2) |
| D9 | 고아 케이스(그래프에서 사라진 갈래) 처리 | ⓐ auto 파일만 삭제 + 사람 파일 남으면 경고 ⓑ 디렉토리째 삭제 ⓒ 건드리지 않고 경고만 | **ⓐ** — 사람이 쓴 시나리오를 지우는 것은 "내가 쓴 게 사라졌다"(WP-WD와 같은 결)이고, ⓒ는 죽은 auto 그레이더가 스위트를 영구 빨강으로 만든다 |

#### 9. 구현 순서 (확정 후)

1. `docs/specs/claude-plugin-eval-<날짜>.md` — 스펙 스냅샷 벤더링(§7-1,
   구현 시점 재조사 포함).
2. `compiler/evals.py` — `plan_eval_skeleton(project)` 순수 함수 + 스펙 결합면
   상수. 테스트는 문자열 비교(케이스 목록·그레이더 텍스트·결정성 2회 호출
   동일·slug 충돌·한글 이벤트 이름 `event-N`).
3. MCP `generate_eval_skeleton` + GUI 메뉴 — IO 계층(소유권 판정·고아 보고).
   미저장 거부, 결과 보고 형식.
4. `project_compiler.py` — D2 채택 시 MARKETPLACE `<out>/evals/` 복사(계획
   집합 합류, `_copy_files_tree` 재사용).
5. Save As 동반(`SessionIO.carry_files_dir`에 evals/ 추가) + `.ddpj` 자연 포함 확인.
6. (early access 게이트 개방 후) 실 러너 로드 스모크 — 후속 배치.

#### 10. 하지 않는 것

- **실행 연동(CI·`claude plugin eval` 호출 자동화).** 배치 스펙이 후속으로
  못 박았고, 게이트가 닫혀 있어 검증 불가능하다.
- **훅 발화 단언.** trace 형상이 공식 미기재다(§3-3) — 스펙이 문서화되면
  그때 auto 그레이더 후보로 재검토.
- **프롬프트 시나리오 자동 생성(LLM 합성).** 생성이 비결정적이 되고, 틀린
  시나리오는 틀린 그레이더보다 해롭다(통과가 거짓 안심을 준다).
- **결과(aggregate-result.json) 파싱·리포트 UI.** 실행 연동과 함께 후속.
- **미배치 스킬·에이전트 단독 케이스.** 단언할 산출 규약이 없다(§4-1).

### 1-3. WP-LK — 스토어 빌드 + 링크 (2026-09-02)

#### 기본 전제 (사용자 확정 2026-09-04)

**배포 전이므로 후방 호환은 신경 쓰지 않고 견고함에 집중한다.** "MARKETPLACE 산출은
현행과 바이트 동일"이라는 하위 호환 게이트도 이 전제 아래서는 제약이 아니다 — 지킬
대상(배포된 사용자)이 없다.

#### 제안 원문 (사용자)

ddls 빌드 시, 프로젝트 로컬 플러그인이고 같은 드라이브인 경우, uv 방식처럼 특정 폴더에 빌드한 후 필요
폴더를 링크하는 방식으로 변경 가능한가. (`.claude/settings.local.json`·`.mcp.json` 등은 링크 대상이 아님 —
없으면 생성, 있으면 편집이고 프로젝트마다 다를 수 있어서 링크 안 됨)

#### 실측 결과 (2026-09-02)

##### 링크 대상 분류 — LOCAL 빌드 산출 경로별

| 경로 | 성격 | 링크 가능성 |
|------|------|------------|
| `.claude/skills/<스킬>/` | 스킬당 폴더 (SKILL.md + skill-files) | 폴더 → junction |
| `.claude/agents/<에이전트>.md` | **개별 파일** | junction 불가 — 하드링크/심링크 |
| `files/`, `schemas/`, `hooks/scripts/` | 폴더 | junction |
| `.mcp.json`, `.claude/settings.local.json` | 병합 편집 | **링크 대상 아님** |

##### 링크 실측 (이 머신)

`dir symlink` / `file symlink` / `junction(mklink /J)` / `hardlink` **4종 전부 성공**.
다만 symlink는 개발자 모드·관리자 권한이 필요해 다른 머신에서 실패할 수 있다.
junction(폴더)·하드링크(파일)는 **무권한이지만 같은 볼륨 전용** — 사용자가 짚은
"같은 드라이브" 조건이 정확히 이 제약이다.

##### 작업 폴더 → ddls 프로젝트 역매핑 (사용자 질문 Q2)

**현재 존재하지 않는다.** `~/.daedalus/mcp-endpoint.json`에 `project` 필드가 있고
실제 값이 들어 있으나(`.../UePluginMaker/.daedalus.json`), ① 앱이 떠 있을 때만
기록되고 ② **현재 앱에 열린 프로젝트 하나**만 가리킨다. "이 작업 폴더가 어느
프로젝트에서 빌드됐는가"의 역방향 매핑이 아니다.

#### WP-LK — 스토어 빌드 + 링크

**흐름:** 항상 `~/.daedalus/builds/<프로젝트>-<경로해시>/`에 전량 빌드 → 같은
볼륨이면 링크, 아니면 복사 + 안내 출력(uv 관례).

**링크 방식:** 폴더 junction / 에이전트 `.md` 하드링크. 둘 다 무권한·같은 볼륨이라
조건이 일치한다.

**링크 단위는 폴더 통째가 아니라 항목별이다.** `.claude/skills/`를 통째로 링크하면
그 프로젝트가 손으로 만든 Daedalus 무관 스킬이 사라진다.

**매니페스트 `.claude/.daedalus-links.json`:** 이번 빌드가 만든 항목 목록 + 소스
프로젝트 경로 + 스토어 경로.

- **관리 항목만 갈아끼우고 나머지는 불가침.**
- 매니페스트에 있는데 이번 빌드에 없는 항목만 제거 → **현행 스테일 잔존 결함이
  해소된다**(지금은 `_copy_files_tree(clear_first=False)`라 삭제된 스킬이 작업
  폴더에 영구히 남는다 — 사용자 파일 삭제 위험 때문에 의도적으로 감수 중이었다).
- 소스 프로젝트 경로를 함께 적으면 위 Q2의 역매핑이 생긴다(지금은 쓰지 않지만
  문은 열어 둔다).

##### 분해 (규칙 2)

| # | 범위 | 파일 |
|---|---|---|
| 1 | `compiler/linking.py` 신설 — 볼륨 판정·링크/복사·매니페스트·스테일 정리 | 신규 1 + 테스트 |
| 2 | `project_compiler.py` LOCAL 경로를 스토어 경유로 | 1 + 테스트 |
| 3 | 프로젝트 속성 토글 + 앱 배선 | 3 + 테스트 |
| 4 | `docs/design/workspace-and-build-target.md` 갱신 | 1 |

`wiring.py`와 같은 결의 순수 stdlib 모듈로 만든다(`project_compiler.py`는 이미 1,000줄을 넘어
여기에 링크 레이어를 더하면 위생 상한에 닿는다).

---

#### 손 편집 전파 대비 — `local_edit_detected` 감지 (권고)

링크 방식이 만드는 실제 함정은 메타 스킬 부재가 아니다:

> 사용자가 `.claude/skills/foo/SKILL.md`를 손으로 고치면 junction이라 **스토어 원본이
> 바뀌고**, 그 프로젝트를 링크한 **다른 모든 작업 폴더에 즉시 전파된다.** 그리고 다음
> 빌드에서 조용히 되돌아간다.

고칠 때 경고가 없고 증상이 엉뚱한 작업 폴더에서 나타나므로 안내문으로 막히지 않는다.

- 매니페스트에 관리 항목별 **해시**를 적는다.
- 다음 빌드에서 해시가 다르면 `local_edit_detected` 경고 — 무엇이 빌드 밖에서
  바뀌었는지 짚고 덮어쓸지 묻는다.

메타 스킬보다 싸고 정확하며 실제 실패를 잡는다. 안내 문구가 필요하면 매니페스트 안
`_note` 필드 + 컴파일 결과 출력이면 충분하다.

#### 확정된 결정 (사용자 응답)

| # | 결정 | 값 |
|------|------|-----|
| D1 | 다른 드라이브 폴백 | 홈에 빌드 후 **복사** + 안내 출력 (uv 관례) |
| D2 | 에이전트 `.md` 링크 | **하드링크** |

#### 제안된 기본값 (미승인)

| # | 항목 | 제안 | 근거 |
|---|------|------|------|
| P1 | 링크 방식 토글 | 기본 **켬** | 폴백이 항상 있어 실패하지 않는다 |

#### 잔존 의문 — 착수 전 확정 필요

| # | 의문 | 왜 중요한가 |
|---|------|------------|
| U2 | **junction 삭제 사고** | `shutil.rmtree`가 junction을 따라 들어가 **스토어 원본을 지우는** 고전적 사고가 있다. 정리 코드가 반드시 링크를 링크로 인식하고 끊기만 해야 한다. 실측 검증 필요. |
| U3 | **git·백업·zip 도구** | 링크를 실체 복제하거나 순환할 수 있다. `.gitignore` 안내가 필요한지, 아니면 링크 위치를 바꿔야 하는지. |
| U4 | **작업 폴더를 옮기면?** | junction은 절대 경로를 담는다. 이동 시 깨진 링크가 남고, 재빌드해야 복구된다. 감지·안내가 필요한가. |
| U5 | **스토어 GC** | 프로젝트를 지우거나 옮기면 스토어가 고아로 남는다. 정리 명령·정책이 필요한가. |
| U6 | **`${CLAUDE_PROJECT_DIR}` 참조** | 본문이 `${CLAUDE_PROJECT_DIR}/files/...`를 가리키고 `files/`가 링크면, CC는 작업 폴더 경로로 해석해 링크를 타고 스토어에 닿는다 — 정상으로 보이나 실측 확인 필요. |
| U8 | **기존 프로젝트 마이그레이션** | 이미 복사 방식으로 설치된 작업 폴더를 링크 방식으로 전환할 때, 기존 실체 폴더를 지우고 링크로 바꿔야 한다. 사용자 편집분이 섞여 있으면? |
| U7 | **이름 충돌** | 사람이 만든 `.claude/skills/foo`와 관리 항목 이름이 겹치면 링크가 덮어쓰는가, 거부하는가. |

## 2. 결정 대기 — 제안 단계

- **fork 스킬 후속** (fork 2종·fork 에이전트 종류는 2026-09-17 구현 완료 — 정본은
  `docs/design/plugin-model.md` "fork 스킬 2종 + fork 에이전트"). 남은 항목은 둘뿐이다:
  ① 랩핑 스킬 실행 에이전트를 fork 방식으로 합치기 — 보류(실행 에이전트는 생성물이라 fork 에이전트 후보 세 종류에 들지
  않고, 2026-09-12 확정 "model/effort는 실행 에이전트로"와 부딪힌다). fork 도그푸딩 뒤 다시 본다.
  ② 외부 플러그인 에이전트가 그 플러그인에 실제로 있는지는 검증하지 않는다(검증기는 파일시스템 무접근 —
  카탈로그 주입 인자가 필요). MCP·피커는 카탈로그로 거른다. 내장 `statusline-setup`이 후보에 없는 것은
  사용자 확정(세 이름만)이라 항목이 아니다.
  **해소됨(2026-09-17/18):** 전환 후 편집 탭이 스스로 다시 구성되지 않던 문제는
  `view/commands/surface_commands.resync_bracket`이 전환 매크로 양 끝에서 프론트매터 폼·레지스트리를
  다시 그리면서 사라졌다(undo에도 걸린다).
- **참조 용도 랩핑 스킬이 스킬 노드에 링크된 경우** — 외부 스킬은 서브에이전트에서만 쓴다는 원칙(2026-09-12)의
  예외로 둘지(현행: 메인 컨텍스트 consult 지시), 상담용 서브에이전트를 합성할지.
- **statusLine 스크립트 도구** — `statusLine`은 LOCAL 전용이다(플러그인 루트 `settings.json`의 허용 키는
  `agent`/`subagentStatusLine`뿐). 스크립트 본문을 모델에 두고 산출 + settings 베이크, MCP는 입력 JSON 스키마 조회 +
  모의 입력 실행 미리보기. 확인 필요: statusLine 명령에 `${CLAUDE_PROJECT_DIR}`가 주어지는지(문서 없음 — 실측),
  사용자 개인 statusLine을 덮는 단일 슬롯 문제(경고). 같은 김에 마켓 빌드의 **플러그인 `settings.json` 기본값
  배출**(`agent`·`subagentStatusLine`)도 미지원이다.
- **외부 플러그인 에이전트 노드** — fork 스킬의 `agent:`로 외부 에이전트를 이미 쓸 수 있다(`플러그인:이름`). 노드가 여전히 필요한지부터 재검토한다. 필요하다면: 감쌀 수 없으므로 입력만 있는 노드(에이전트 호출 포트로만 진입, 나가는 전이
  금지). 동기 호출(기본)과 백그라운드 실행 옵션, 카탈로그 `agents/*.md` 탐색, 사용 선언(`external_plugins`) 배선
  재사용. 외부 에이전트는 우리 블랙보드를 모르므로 호출 포트 description이 유일한 입력 통로다.
- **프로젝트 속성 다이얼로그가 CommandStack을 거치지 않는다** (2026-09-13 발견) — `project_properties.py`가
  `project.build_target` 등을 직접 대입한다. undo가 안 되고 notify가 없어, 빌드 타깃을 바꿔도 LOCAL 전용 탭
  표시·에이전트 편집기 잠금이 다음 갱신 전까지 옛 상태로 남을 수 있다. MCP `set_project_properties`와 같은 커맨드 경로로 합친다.
- **2026-09-13 전체 점검 결과 — 미처리분** (전이 스킬 호출 불가·YAML 이스케이프는 같은 날 수정됨).
  서브에이전트 점검 + 주요 항목 직접 재확인. 번호는 우선순위.
  1. **undo 공백이 넓다 (설계 원칙 3 위반, 직접 확인)** — CommandStack을 거치지 않는 편집:
     편집기 프론트매터 필드 전부·설명·when_to_use(`frontmatter_panel._write_field`/`_on_optional_toggled`/
     `_save_desc` — MCP `set_component_field` 등은 SetAttrCmd라 표면마다 undo 여부가 다르다), 훅 패널 전체
     (`hook_panel.py` hook_library/handlers 직접 append·pop), 출력 포트 카드 추가·삭제(`transfer_on_panel.py:252,257`),
     작업 폴더 설정(`workspace_settings_panel.py:148`), 규칙 추가·이름·paths·삭제(**GUI `workspace_editor.py`와 MCP
     `mcp/tools/workspace.py:136-197` 둘 다**). 훅·규칙 CRUD는 GUI와 MCP가 따로 구현돼 원칙 1도 위반 —
     `view/actions/hooks.py`·`rules.py`로 합치고 명령 경유로.
  2. **흐름이 조용히 끊기는 그래프 (경고 없음)** — ① 선이 없는 출력 포트로 끝나면 Next Steps에 갈래가 없고 Finishing Up도
     없어 진행 기록이 멈춘다 ② 중간 스킬에 `disable_model_invocation=True`면 앞 단계가 부를 수 없다
     (`mid_chain_user_invocable`은 user_invocable만 본다) ③ 가드 없는 한 포트 → 두 타깃(병렬 의미 없음), 전부 가드인데
     else 없음 ④ 빈 노드(skill_ref 없음)로 가는 선은 지시 없이 끝난다 ⑤ 마지막이 에이전트면 `current done`이 영영 안 남는다
     ⑥ 에이전트→에이전트→스킬 선은 산출 어디에도 없다.
  3. **블랙보드 클래스·필드 이름 중복** — GUI는 중복을 막지 않고 검증 규칙도 없다. `compile_schemas_json`이 키로 덮어써
     스키마 하나가 사라진다(대소문자만 다른 이름은 Windows/macOS 파일 충돌). `duplicate_blackboard_class/field` 에러 필요.
  4. **에이전트 설정과 산출 지시의 모순** — **워크플로 에이전트**의 `background: true`는 보고로 분기가 불가능한데
     무경고다(fork는 2026-09-17부터 종류가 값을 정하므로 이 항목의 대상이 아니다 — 비동기 fork는 보고 규약과
     `current` 인계 3단 규약을 함께 낸다),
     `Agent` 도구 없는데 호출 포트(위임 지시가 나가지만 혼자 처리), `Bash` 없는데 블랙보드 CLI 지시,
     `tools: []`(체크만 하고 비움)는 키가 생략돼 **전 도구 상속**, 에이전트 `skills`에 프리로드되지 않는 스킬(전이 스킬·
     disable-model 선언형·참조 용도/비활성 랩핑)이 들어가도 무경고.
  5. **빈 컴포넌트 무경고** — 설명·본문·when_to_use가 빈 스킬도 통과·산출되고, 캔버스에 없는 빈 스킬도 설치된다.
     빈 출력 포트 설명은 Next Steps에 설명 없는 갈래를 만든다.
  6. **MARKETPLACE 빌드는 MCP 서버 정의를 싣지 않는데 경고가 없다** — `missing_mcp_server_def`는 LOCAL 배선에서만 나온다.
  7. ~~**Entry Context가 진행 파일을 직접 읽으라고 지시한다**~~ — **해소(2026-09-17, WP-FK2 C3)**. 도입 5문장이
     한 문장(`Check \`prev\` and the branch in \`note\` …`)으로 줄면서 파일 경로 언급이 사라졌고, 읽는 법은
     워크플로 가이드 4절이 `daedalus-bb … progress read`로 통일해 말한다.
  8. **위생** — 안 쓰는 import: `edge_item.py` Qt, `ref_edge_item.py` QRectF (2026-09-18 pyflakes 실측 — 이 둘뿐이다)
     + `scene.py`의 `Command` 중복 임포트(:31 모듈 수준 ↔ :503 함수 지역 — 지역 쪽이 잉여)
     (재-export 파사드 `emit/__init__`·`deser.py`·`markdown_editor.py`는 의도적).
     **해소됨:** `registry_panel`의 죽은 `AgentDefinition` import(WP-E), `validation.md`의 규칙 수·누락 행·
     믹스인 수(WP-B에서 갱신), `architecture.md`의 app.py 줄 수(§7 표가 실측값을 갖는다).
  9. **dogfood 프로젝트(`project/daedalus_cc_plugin`)** — 빈 fork 스킬 `sdfsdf`·`graph-design` 동봉 쓰레기 파일 2개 삭제
     확인 대기, `session-wrap` when_to_use·done 설명 빈 값, `tooling-scout` writes 선언 누락(본문은 GraphDraft 기록),
     `env-configurator`·`tooling-scout` model·maxTurns·MCP 확인 훅 미지정, 오래된 본문(`daedalus-model` 5종·옛 state 경로,
     `graph-design` 종류 목록, `blackboard-cli` progress 누락·옛 경로, `plugin-compile` settings 파일 고정 설명),
     `guard-blackboard-schema`가 진행 파일 Read를 막음 vs Entry Context, `permissions.deny state/**`로 CLI 부재 시 대비책
     불가, `log-tool-usage` 훅 상시 실행 부담. 앱의 plugin-verify fork 전환·verify-analyst 추가는 미저장.
     **2026-09-17 이후 추가**: 이 파일을 열면 fork 2종 마이그레이션(`migrate_fork_split`)이 구 `fork_skill`을
     동기 fork로 옮기고 참조된 미배치 에이전트를 fork 에이전트로 재분류한다 — 미배치 fork에는 경고가 뜨며,
     비동기가 맞는 단계는 종류를 바꿔야 한다. 저장은 사용자 몫이라 여기서는 건드리지 않는다.
- **GUI 블랙보드 편집이 undo되지 않는다** (2026-09-13, 블랙보드 안내서 작성 중 확인) — 🗂 블랙보드 탭과 속성 패널의
  reads/writes 입력이 모델에 직접 기록한다(설계 원칙 3 위반. MCP 블랙보드 도구는 CommandStack 경유). 또 GUI 탭의
  클래스 이름 변경과 MCP `set_blackboard_fields`의 필드 이름 변경은 노드 reads/writes 참조를 옛 이름에 남긴다 —
  MCP `update_blackboard_class`의 이름 변경만 참조까지 갱신한다. 판정·갱신을 한 함수로 합친다.
- **안내 문서 작성 중 발견한 코드 불일치** (2026-09-13, `docs/guide/` 작성 서브에이전트 보고 — 미검증 항목 포함):
  ① `missing_mcp_server_def` 메시지가 "프로젝트 속성"에서 서버 정의를 추가하라고 하지만 그 GUI 칸이 없다(MCP
  `set_mcp_server_def`만 있음 — GUI 패리티 공백). ② MCP `set_component_field`/`set_component_hooks`가 마켓플레이스
  빌드에서 무시되는 에이전트 필드(hooks·mcpServers·permissionMode)를 받는다 — GUI는 잠근다(경고는 있음).
  ③ `wiring.py`·`project_compiler.py` 머리말·`props.set_mcp_server_def` docstring이 설정 파일을 `settings.local.json`
  고정으로 설명한다(실제는 컴파일 시 선택, 기본 settings.json). `enums.BuildTarget` docstring의 "설치 스크립트 동봉"은 퇴역.
  ④ 📖 참조 스킬을 **스킬** 노드에 링크해도 그 SKILL.md에 아무것도 합류하지 않는다(에이전트 노드 링크만 skills에 반영) —
  제품 공백인지 확인.
- **컴포넌트 도입문 2차 호이스트 (WP-FK2 C3 후속)** — 공통 안내 파일(`guides/<플러그인>/workflow.md`·
  `blackboard.md`)로 옮긴 것은 워크플로 개념·진행 기록·재개 규칙·진입 맥락 읽는 법·fork 보고 양식·블랙보드
  CLI·규칙이다. **남은 도입문 J~S는 이번 범위 밖**으로 뒀다 — 각 1~2문장이고 컴포넌트 고유 정보(포트 이름·
  호출자 목록·외부 스킬 이름)와 한 문장 안에서 엮여 있어, 떼려면 문장을 쪼개야 한다. 후보:
  `## Invocation Contract`·`## Delegation`·`## Exits`·`## Output Events`·`## Next Steps`·
  `## Reference: Tool Shelf`·`## Background Skills`·랩핑 실행 에이전트 본문(`emit/wrapped.py`).
  착수 전제: 토큰 리포트로 실측 절감폭을 재고(지금 가이드 둘은 ≈1,800토큰 — workflow 1,400 / blackboard 400), 고유 정보와 일반형이 한 문장에
  섞이지 않게 문구를 먼저 다시 쓴다.
- **MCP `get_project`의 축약 기본값** — 지금은 `sections` 생략 시 전체를 돌려준다. 축약 구획을 기본으로 바꿀지.
- **"빈 툴 추가"** (사용자 메모 2026-09-13, 원문 그대로 — 뜻을 확인하고 착수한다). 후보 해석
  둘: ① `tool_shelf`에 빈 `UserDefinedTool`을 만드는 편집 표면(지금 도구 선반은 모델에만 있고
  GUI·MCP 어디에도 생성·편집 도구가 없다 — 카탈로그 후보 조회 `list_tool_candidates`만 있다)
  ② 캔버스의 빈 노드처럼 **자리만 잡아 두는** 도구 항목(나중에 채울 자리). 어느 쪽이든 지금은
  도구 선반 편집이 통째로 비어 있다는 것이 사실이므로, 확인 후 그 표면을 함께 설계한다.

## 3. 컴파일러 Tier 2 — 도구·스크립트 실행

현재 `ToolExecution`/`ToolEvaluation`은 절차 서술 문구와 tool_shelf 참조 단락으로만 나간다. 실행 코드를 만드는 것이
Tier 2다. 출발점은 2026-05 조사(ClaudeManager가 만든 plain 셸 스크립트를 플러그인 안에서 부르는 방식)이고, 그중
**이미 구현된 것**(SKILL.md 컴파일, 사용자 호출 진입점, 훅 배출, SessionStart 진행 훅, 서브에이전트, 블랙보드 JSON
영속화)은 뺐다.

- **실행 래퍼 (L1)** — `ToolExecution(shell)` 노드를 본문 지시로 컴파일할 때 호출 contract를 주입한다: 스크립트
  경로(`${ROOT}` 계열 토큰), 인자 이스케이프·shell 분기(pwsh/bash), cwd 지정, 출력 캡처(`--output-format
  stream-json`이면 마지막 `result` 추출)와 출력 변수 저장, `success_condition` 판정. `ToolEvaluation`도 같은 contract.
- **체크리스트 합성 (L2)** — 직렬로 이어진 상태 체인을 TodoWrite 체크리스트로 합성해 순차 실행 강제력을 높이는 안.
- **외부 오케스트레이터 (L5)** — FSM을 런타임 JSON으로 내보내고 오케스트레이터 스크립트가 상태를 돌며 셸 액션과
  `claude -p` 단일 step 호출을 섞는 안. 결정론·Guard(Expression 평가)·병렬 Region을 보존하지만 세션 부트스트랩
  반복 비용과 디버깅 부담이 있다. 착수 전 측정 필요.
- **재진입 가드** — 스크립트가 다시 `claude -p`를 부르면 같은 플러그인의 훅이 재발동할 수 있다. 래퍼에
  `DAEDALUS_REENTRY_GUARD` 같은 환경 변수 가드를 자동 삽입하고, 훅 matcher가 스크립트의 Edit/Write를 다시 트리거하는
  경로를 정적으로 짚는 검증.
- **MCP 서버 실행 코드** — `MCPExecution`/`MCPEvaluation`의 실행 산출.
- **CC CLI 연동** — 기존 Claude Code CLI 도구를 플러그인 안에 명시해 쓰는 방식.
- 미해결 질문: 스크립트가 직접 `claude -p`를 부르는 경로와 컴파일 산출이 부르는 경로의 환경·세션 격리 차이, 훅
  stdout/stderr가 모델에 노출되는 정확한 표면(`additionalContext`).

## 4. 보류 (개시 미정)

- **B2 기존 플러그인 임포트(역방향 파서)** — 손으로 쓴 SKILL.md/agent .md를 모델로 들이기. 가치는 인정되나 파서
  품질 리스크. 착수 시 설계부터.
- ~~**블랙보드 단락 중복**~~ — **해소(2026-09-17, WP-FK2 C3)**. LOCAL 전용 `.claude/rules/` 이관안 대신
  **두 타깃 공통** `guides/<플러그인>/blackboard.md`로 빼고 각 산출에는 포인터 1줄만 남겼다
  (`compiler.md` 정책 21번). 워크플로 개념·진행 기록·재개 규칙도 같은 방식으로 `workflow.md`에 모였다.
- **Region 확장** — 리전별 우선순위, 취소 정책, 동기화 포인트.

## 5. 기능 잔여

- **랩핑 스킬의 실행 서브에이전트 산출에 가이드 포인터가 없다 (D8 — 2026-09-19 실측, WP-6이 봉인)**.
  랩핑 스킬은 파일을 둘 낸다(SKILL.md + `agents/<이름>.md` 실행 서브에이전트). 앞의 것은 절 표를
  거치면서 공통 안내 파일 포인터(`guides/<플러그인>/workflow.md`·`blackboard.md` 1줄)를 받지만,
  뒤의 것(`compiler/emit/wrapped.compile_wrapped_runner`)은 표를 거치지 않는 **손수 조립기**라
  포인터가 붙지 않는다. 실행 서브에이전트도 워크플로 안에서 도는 컨텍스트이므로 포인터를 받는
  것이 맞지만, WP-6은 **동작 불변 리팩토링**이라 고치면 산출 바이트가 바뀐다 —
  `WrappedEmitter.render`가 `RUNNER_PAYLOAD` 행에서 종전 함수를 축자 호출하는 것으로 **봉인**했다
  (`docs/design/compiler.md` WP-6 절). 고치는 대신 **WP-10(WrappedSkill 퇴역)에서 조립기가 클래스와
  함께 사라지는 것**이 계획이다. 그 전에 고치려면 골든(`tests/data/golden/*.sha256`)을 같은
  커밋에서 재생성해야 한다.
- **`config.model` 키 부재가 `None`으로 로드된다 (D10 — 2026-09-19 실측, WP-4가 보존)**.
  `ComponentConfig.model`의 선언 기본값은 `ModelType.INHERIT`인데, 저장 파일에 `model` 키가
  없으면 `None`이 들어온다(종전 `_deser_config`의 `_to_enum(ModelType, None, None)`, 오늘은
  `FieldSpec("model", …, missing=None)`). 두 값은 프론트매터 배출에서 같은 결과를 내지만
  (둘 다 키를 내지 않는다) 모델 상태로서는 다르고, `supports_model_effort`/MCP 조회가 읽는
  값도 다르다. **고치면 저장 파일 해석이 바뀐다**(오래된 파일의 `model`이 INHERIT가 된다) —
  그래서 WP-4는 부재 의미론을 선언으로 **보존**하고 고치지 않았다. 고칠지는 사용자 확정
  대상이고, 바꾸는 순간 `tests/model/plugin/test_serialize_symmetry.py`의
  `test_model_missing_key_loads_as_none_not_the_declared_default`가 이유를 찍고 실패한다.
- **스킬 훅 정정의 남은 일** (정정 자체는 2026-09-13 완료 — `docs/design/hooks.md` "스킬 훅").
  ① `project/daedalus_cc_plugin`의 `graph-orient`(check-daedalus-mcp)·`graph-state`
  (guard-blackboard-schema, validate-on-save) 훅 참조를 틀린 경고에 따라 지웠다. 세 훅 모두 전역으로
  켜져 있어 지금 동작은 같지만, "그 스킬이 도는 동안만"이라는 뜻을 되살릴지 **사용자 확인**.
  ② 같은 훅이 전역으로도 켜져 있고 스킬에서도 참조될 때 두 번 실행되는지(중복 제거 여부) **미실측** —
  되살리기 전에 확인해야 한다.
- **에이전트 내부 FSM 잔재가 산출에 남는다** (2026-09-13 실측 — `project/daedalus_cc_plugin`의
  `graph-surgeon`). 내부 FSM은 WP-AF로 퇴역해 **GUI 탭도 MCP 도구도 없는데**, 컴파일러는 구버전
  설계 보존을 위해 실질 상태가 있으면 `## Internal Workflow` 단락을 여전히 배출한다. 즉 지울
  수단이 없는 채로 산출에만 나온다. 권고는 **컴파일러가 무시하게 하고 마이그레이션이 legacy
  상태를 정리**하는 쪽(퇴역 개념의 잔재 제거 — 편집 표면을 다시 여는 것은 방향이 거꾸로다).
- **WP-WR 2단계 잔여** — 에디터 소스 콤보·본문 미리보기, `dangling_wrapped_source`(카탈로그 실존 검사 — 소스 부재는
  게이트 에러가 아니라 경고, 호출자 주입), `wrapped_source_has_workflow`(소스 본문에 우리 자동 헤딩이 보이면 이중
  지시 경고), 소스 스킬이 `disable-model-invocation: true`면 실행 에이전트에 주입도 직접 인보크도 안 된다는 경고.
- **종료 경로 크래시 — WP-E에서 미룬 항목 (재현 조건 미기록)** — WP-E 리뷰에서 창을 닫는 중의
  크래시가 언급됐지만 재현 조건이 커밋 메시지에도 설계 문서에도 남지 않았다. **코드가 보여 주는
  사실만** 적는다: `ProjectViewModel`의 리스너 등록이 창 수명과 짝이 맞지 않는다.
  ① `MainWindow`는 `_on_project_vm_changed` · `_mark_dirty`(structure·content 양쪽) ·
  `_update_statusbar`를 등록만 하고 `closeEvent`에서 떼지 않는다.
  ② `closeEvent`는 `FsmScene.close()`(자기 `_rebuild` 리스너 해제)도 부르지 않는다 — 프로젝트
  캔버스는 닫을 수 없는 고정 탭이라 `_close_tab`의 `widget.close()` 경로를 타지 않는다.
  ③ 컴포넌트 탭의 `ComponentEditor`는 `on_notify_fn=self._project_vm.notify`를 그대로 들고 있어
  `deleteLater` 뒤에도 vm을 부를 수 있다(`_on_model_changed` → `call_notify`).
  그래서 창이 닫힌 뒤 `notify()`가 한 번 더 돌면 이미 삭제된 C++ 객체(상태바 라벨·씬 아이템)를
  건드린다. 고치는 방향은 **등록의 짝 맞추기**다 — `closeEvent`에서 `FsmScene.close()`와
  `remove_listener` 3건을 부르고, 탭 편집기를 닫을 때 `_on_notify_fn`을 끊는다. 다만 재현 조건이
  없으므로 **재현 테스트를 먼저 만든다**(헤드리스 스위트는 `confirm_discard_changes` 스텁으로
  닫기 확인을 지나치므로 지금 이 경로를 밟지 않는다).
- **외부 플러그인 참조의 미선언 등급 비대칭 — 경고로 유지한다 (WP-9 리뷰, 2026-09-19 결정)**.
  같은 사실("가리키는 플러그인이 `external_plugins`에 없다 → 배선이 안 나가 런타임에 못 찾는다")을
  fork 스킬은 **에러**(`fork_agent_undeclared_plugin`)로, 컴포넌트의 외부 참조는 **경고**
  (`undeclared_external_plugin`)로 짚는다. WP-9의 외부 플러그인 에이전트도 후자에 합류했다 —
  산출 파일이 없어 배선 없이는 아예 못 쓰는데도 경고다. **그래도 경고로 둔다**: 등급의 단일
  진실은 `model/validation/severity.WARNING_RULES`이고 그것은 **규칙 이름의 집합**이라, 같은
  규칙을 대상 종류(`OUTPUT_LOCATION is NONE`)에 따라 달리 매기려면 규칙 이름을 쪼개야 한다
  (`invalid_component_name`이 메시지 문자열로 등급을 가르는 예외가 이미 있고, 그 방식을 늘리는
  것은 방향이 거꾸로다). 종류별 등급이 필요하다는 사실이 다시 확인되면 규칙을 쪼개는 것이
  올바른 수선이고, 그때는 사용자 확정 대상이다(원칙 10). 오늘 상태: 경고 1건 + 컴파일 성공.
- **위임 이름 접두 비대칭 (WP-9 리뷰에서 재확인, 2026-09-19)**. 마켓 빌드에서 fork 스킬
  프론트매터의 `agent:`는 `agent_invocation_name`이 `<프로젝트>:<이름>`으로 내는데, 같은 빌드의
  위임 산문("## Next Steps"·"## Delegation")은 `delegation_target_name`이 내는 **맨 이름**이다
  (`delegate to agent \`worker\``). 종전부터 그랬고 골든이 고정한다. 둘 중 어느 쪽이 CC가 실제로
  찾는 이름인지 **실측이 없다** — 산문은 프론트매터 키가 아니라 사람·모델이 읽는 지시라 맨
  이름으로도 동작할 수 있다(원칙 8: 규격은 근거를 남긴다). 실측 후 한쪽으로 맞추면 골든이
  바뀌므로 같은 커밋에서 재생성한다. `docs/design/compiler.md` 정책 19-b가 이 비대칭을 명시한다.
- **외부 에이전트 원본 파일 열기 (WP-9 리뷰)**. `wrap_catalog.resolve_skill_file`은 플러그인의
  `skills/<이름>/SKILL.md`만 해소한다 — 정본이 외부인 **에이전트**의 원본(`agents/<이름>.md`
  추정)은 못 찾는다. 그래서 편집기의 "원본 열기" 버튼은 `can_resolve_source()`(버킷 판정)가
  거짓인 컴포넌트에서 **감춰진다**(누를 때마다 "찾지 못했습니다"만 내놓는 버튼은 조용한
  실패다). 카탈로그는 이미 `CataloguedAgent`로 플러그인 에이전트를 발견하므로 파일 경로
  해소만 더하면 되지만, 외부 플러그인의 에이전트 파일 배치를 **실측하지 않았다**(원칙 8).
- **컴파일 미리보기 비모달화** — 지금은 모달(`view/actions/preview.py`의 `exec()`)이라 편집하며 나란히 못 본다. 랩핑
  스킬의 실행 에이전트 산출도 미리보기에 아직 없다.
- **참조 하이라이트** — 2초 뒤 `clearSelection()`이 사용자 선택까지 지운다(`canvas/context_menus.py`). 별도 이펙트
  아이템으로 교체 후보.
- **호출 계약 줄 길이** — 포트 설명 + transfer 설명 + 전제 지시가 한 줄이라 항목 많은 에이전트에서 길다.
- **도구/MCP 카탈로그 편집 UI** — 지금은 로더(`catalogue_loader`)와 폴더 열기뿐.
- **전역 훅 직접 편집 UI** — 읽기 전용 표시 + 프로젝트로 복사 + 폴더 열기까지.
- **`view/editors/body_documents.py`의 `BodyDocumentRegistry.sync_from_model` 배선** — 호출자가 없다.
  `docs/design/editor.md:80`이 지정한 **유일한 인가 경로**(모델 body가 에디터 밖에서 바뀐 경우의 갱신
  수단)인데, 오늘은 모든 쓰기가 `document_for`의 `QTextDocument`를 통과하므로 그런 경로 자체가 없다.
  **배선 조건**: `component.body`를 `document_for` 없이 직접 쓰는 첫 경로(마이그레이션·임포트가 열려
  있는 컴포넌트의 본문을 건드리는 순간)가 생기면 **그 자리에서** 호출한다. 그 전에 지우면 첫 외부
  변경 경로에서 조용한 staleness 버그가 난다(스캔 게이트에는 `tests/test_dead_code.py`의 ALLOWLIST에
  `test-seam`으로 등재돼 있다).

## 6. 알려진 제약 (WP-LK 매니페스트가 생기면 정리 가능)

- 컴파일은 파일을 지우지 않는다 — 삭제한 규칙·스킬의 옛 산출이 작업 폴더에 남는다
  (`_copy_files_tree(clear_first=False)` — 사용자 파일 삭제 위험을 피한 의도적 감수).
- `.claude/CLAUDE.md` 표식을 사람이 지우면 다음 빌드가 구역을 새로 덧붙여 내용이 중복된다.

## 7. 코드 위생 — 800줄 초과 (1,200 상한은 테스트가 강제)

| 파일 | 줄 (2026-09-19 실측) |
|------|-----|
| `view/app.py` | 1,102 |
| `view/canvas/scene.py` | 992 |
| `view/widgets/markdown/editor.py` | 928 |
| `cli/blackboard.py` | 851 |

- **`view/app.py` 분해 후보 (2026-09-18 리뷰)** — WP-FK2에서 `rebuild_component_frontmatter`가
  붙어 1,102줄이 됐다(1,200 상한까지 98줄). 봉합선은 **탭·편집기 수명주기**다 —
  `_open_component` · `_close_tab` · `_sync_tab_titles` · `rebuild_component_frontmatter` ·
  `open_component_ports`를 `view/tabs.py`(가칭)로 옮기면 한 덩어리로 빠진다(이동만·동작 불변,
  WP-RF 관례). WP-FK2가 끝난 2026-09-19에도 1,102줄 그대로다 — **`app.py`에 다음 기능을 넣기
  전에 먼저 쪼갠다.**
  `compiler/project_compiler.py`는 WP-C의 `plan.py` 분해로 676줄이 되어 목록에서 빠졌다.
- **`view/canvas/scene.py` 분해 후보 (2026-09-19 리뷰)** — 992줄로 800줄 권고를 넘었고 1,200
  상한까지 208줄이다. 한 파일이 세 책임을 겹쳐 든다(스멜 ①). 봉합선:
  ① **드롭 수용** — `drop_skill` · `drop_wrapped_source` · `_ask_wrapped_usage` ·
  `_place_wrapped_fixing_usage` · `drop_reference_skill`(레지스트리에서 들어오는 입구,
  용도 질문 모달이 붙어 테스트 봉합선이기도 하다).
  ② **배치·삭제 커맨드 조립** — `_create_state` · `_delete_state` · `_delete_transition` ·
  `_create_and_assign_transfer_skill` · 참조 노드/링크 생성·삭제(전부 CommandStack 경유라
  씬 그리기와 섞일 이유가 없다).
  ③ **엣지 라우팅·드래그** — `update_edges_for_node` · 경유점(`handle_edge_double_clicked` ·
  `remove_waypoint` · `clear_waypoints`) · 드래그 release 단일 진입점(`handle_items_moved` ·
  `snapshot_drag_positions`) · 전이/참조 링크 드래그 3종.
  컨텍스트 메뉴는 이미 `canvas/context_menus.py`로 빠져 있어 얇은 위임만 남았다 — 같은 관례로
  옮기면 된다(이동만·동작 불변, 재-export 파사드, 기존 테스트 무수정). **`scene.py`에 다음
  기능을 넣기 전에 먼저 쪼갠다** — `app.py`와 같은 게이트다.

- **FSM 계층의 남은 구조 순회 `isinstance` 53건 (WP-11 이후, 2026-09-19 실측)** — 래칫 ③의 기준선이다.
  걷은 것은 **종류를 묻는** 사다리 넷(상태 서술·훅 핸들러 폼·의사 상태·Tool 직렬화)이고, 남은 53은
  성격이 다르다: `walk.iter_states`·`machine_rules`·`ser`가 **합성 상태를 재귀로 내려가거나**
  FSM 값 객체를 저장 dict로 펴는 자리다. 폴리모픽 메서드로 옮기려면 `model/fsm/**`가 검증 어휘·
  컴파일러 어휘를 알아야 해서 경계 계약(fsm은 Claude 무관·최하위)을 깬다. 줄이려면 방문자
  (visitor) 도입이 선행돼야 하고, 그것은 **사용자 확정 대상**이다(설계 변경).
- **legacy `_describe_agent_fsm` 삭제 검토** — 에이전트 내부 FSM은 WP-AF에서 퇴역했고, 이 함수는
  구버전 파일의 실질 상태를 서술하는 잔재다. 삭제하면 그 산출이 사라지므로(구버전 프로젝트의
  설계가 본문에서 증발) **마이그레이션으로 본문에 흡수한 뒤** 지워야 한다 — 사용자 확정 대상.
  WP-11은 이 변형을 합치지 않고 별도 `singledispatch`로 두어 산출 바이트를 보존했다.

## 8. 테스트

- **클립보드 의존 테스트** — `tests/view/editors/test_hook_panel.py` 복사 테스트와
  `tests/view/test_mcp_info_dialog.py::test_copy_button_puts_snippet_on_clipboard`는 다른 프로세스가 Windows 클립보드를
  잡고 있으면 실패한다(코드 변경 없이 재현). 복사할 텍스트를 반환값으로 검증하고 클립보드 쓰기는 얇은 어댑터로
  분리하는 쪽이 낫다.
- **`daedalus-bb progress` 동시 쓰기 테스트 없음** — 낙관적 잠금을 재사용만 했다.
  `tests/cli/test_blackboard_concurrency.py`와 같은 모양으로 추가할 가치가 있다.
