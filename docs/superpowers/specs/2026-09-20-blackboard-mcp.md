# 블랙보드 stdio MCP 서버 — CLI 1:1 대응 후 CLI 폐기 (WP-BM, 2026-09-20)

## 0. 사용자 확정 결정 (2026-09-20)

1. `daedalus-bb`를 **stdio MCP 서버**로 만든다. 도구는 현행 CLI 명령과 **1:1**로 대응한다.
2. 그 뒤 **CLI(argparse 진입)는 폐기**한다 — 모델이 접하는 표면은 MCP 하나다. 코어(검증·원자적
   쓰기·낙관적 잠금·코어션·진행 파일)는 그대로 재사용한다.
3. 이점의 실체: 노드의 reads/writes 선언이 **프론트매터 권한**(`allowed-tools`/`tools`)으로 번역된다.
   캔버스 📖/✏ 뱃지와 산출 권한이 같은 사실을 말한다(원칙 1). 셸 따옴표·exit code 해석 계층이
   산출 문서에서 사라진다.
4. 종전 결정 C+A(2026-08-17, uv 동봉 CLI + 컴파일 지시)는 **C를 MCP 서버로 바꾸는 것**으로
   갱신된다 — 설치 경로(`uv tool install`로 앱과 함께)는 그대로다.

## 1. 현행 사실 (구현자는 먼저 읽는다)

- CLI: `daedalus/cli/blackboard.py`(851줄 — **800줄 초과, 기능을 더하기 전에 쪼갠다**),
  `daedalus/cli/progress.py`(175줄). 계약 정본: `docs/design/blackboard.md` "블랙보드 CLI" 절
  (명령 7개: `list`/`read`/`init`/`write`/`validate`/`progress read`/`progress set`, 전역 `--schemas`(필수)·
  `--state-dir`, exit 0/1/2/3, stdout JSON·stderr 진단, 낙관적 잠금 재시도, 코어션 규칙, 초기 객체 규칙).
- **임포트 계약**: `daedalus/cli/**`는 `daedalus.model`을 임포트하지 않는다(순수 stdlib —
  `tests/test_import_contracts.py`가 AST로 강제). `mcp` SDK 임포트는 허용한다(모델이 아니다).
  설치 대상 폴더에는 산출 `schemas/<플러그인>.json`뿐이다.
- 앱 내장 MCP 서버(`daedalus/mcp/service.py`)의 `_server_factory`가 mcp 1.x(`FastMCP`)/2.x(`MCPServer`)를
  흡수한다 — 같은 팩토리 관례를 쓴다(복제하지 말고 공용 위치로 옮겨 공유: `daedalus/mcp_compat.py`
  같은 **모델 무의존** 모듈).
- 컴파일러의 CLI 지시 자리: `compiler/emit/guides.py`(워크플로 가이드·블랙보드 가이드 — "## The daedalus-bb
  CLI" 절, `State CLI:` 포인터 줄, `command -v` 폴백), `compiler/emit/skill_sections.py::_progress_cli`
  (다음 단계 진행 명령), `compiler/emit/fork.py`(fork "## Report"의 진행 명령·비동기 인계 문구),
  `_async_fork_handoff_note`(grep으로 위치 확인). 정책 정본: `docs/design/compiler.md` 10·12·20·21번.
- `.mcp.json` 배출: LOCAL은 `compiler/units/install.py` + `compiler/wiring.py`(작업 폴더 `.mcp.json`
  `mcpServers` 병합, `settings.json`의 `enableAllProjectMcpServers`/허용 목록 처리 여부 확인), MARKETPLACE는
  플러그인 루트 `.mcp.json`(현행 산출에 있는지 확인 — 없으면 `plugin.json` 규격에 맞춰 추가.
  플러그인 `.mcp.json`은 `${CLAUDE_PLUGIN_ROOT}` 치환을 지원한다 — 공식 문서 확인 날짜를 설계 문서에 남긴다).
- 프론트매터: 스킬 `allowed-tools`(SKILL.md — **권한 부여**, 다른 도구를 막지 않는다), 에이전트 `tools`
  (**제한 목록**, `None`=전부 상속), `mcpServers`(LOCAL 전용 — `agent_sections._agent_mcp_server_names`가
  `mcp__<서버>__<도구>` 접두에서 서버 이름을 유도). 노드별 reads/writes는 `graph` 배치의 state access
  (`skill_sections._blackboard_section`이 읽는 것과 같은 곳).
- 훅: 컴파일러가 내는 `hooks/scripts/__progress__.sh`(SessionStart, `cat state/__progress__.json`)는 CLI를
  쓰지 않는다. 도그푸드 프로젝트의 `validate-on-save`/`guard-blackboard-schema` 훅은 **사용자 파일**이라
  건드리지 않는다(`project/daedalus_cc_plugin/` 금지).
- 문서: `docs/design/blackboard.md`, `docs/design/compiler.md`, `docs/design/architecture.md`(모듈 지도),
  `docs/guide/01-concept.md`·`03-blackboard.md`·`06-mcp.md`, `docs/backlog.md`.

## 2. 단계 0 — 실측 (착수 전, 결과를 `docs/design/blackboard.md`에 날짜와 함께 기록)

마켓플레이스 빌드에서 플러그인 `.mcp.json`의 서버 도구가 **서브에이전트/fork에도 보이는지**를
`claude -p`로 잰다(스크래치패드에 최소 플러그인: `.claude-plugin/plugin.json` + `.mcp.json` +
`agents/probe.md`(tools에 그 MCP 도구) + `skills/fkprobe/SKILL.md`(`context: fork`, `agent: probe`) —
`claude --plugin-dir <경로> -p "/fkprobe"` 또는 로컬 마켓 등록. 서브에이전트 전사
`~/.claude/projects/<cwd>/<세션>/subagents/*.jsonl`에서 도구 호출 성공 여부로 판정). 안 보이면 설계
문서에 한계로 적고, fork 산출에는 "메인 대화가 대신 기록한다" 규약을 유지한다.

## 3. 단계 1 — 서버 (커밋 1)

- **코어 분리**: `daedalus/cli/blackboard.py`를 `core.py`(스키마 로드·검증·초기 객체·코어션·
  `write_state_checked`·읽기 — **출력 없이 값을 돌려주고 실패는 예외로**: `BlackboardError(kind, message,
  detail)`, kind ∈ `not_found`(exit 3)·`usage`(2)·`rejected`(1: 검증 실패·잠금 소진), `progress.py`도 같은
  규약)와 얇은 진입점으로 나눈다(이동만·동작 불변, 기존 `tests/cli/` 무수정 통과).
- **서버**: `daedalus/cli/mcp_server.py`. 진입 `daedalus-bb --schemas PATH [--state-dir DIR]`(전역 옵션
  그대로) → stdio. 도구 7개, CLI와 1:1:

  | 도구 | 입력 | 결과 |
  |---|---|---|
  | `list` | — | `{"classes": {...}}` (CLI `list`와 같은 JSON) |
  | `read` | `cls`, `field?` | 파일 전체 또는 `{"field": ..., "value": ...}` |
  | `init` | `cls`, `force=false` | 만든 객체 |
  | `write` | `cls`, `set?: object`, `append?: object(field→값 또는 배열)`, `remove?: object` | 쓴 뒤 객체. 값은 JSON 타입 그대로 받되 문자열이면 CLI 코어션 규칙 적용 |
  | `validate` | `classes?: list` | `{"ok": bool, "violations": [...]}` (실패해도 결과로) |
  | `progress_read` | — | 진행 항목 |
  | `progress_set` | `current?`, `completed?: list`, `note?`, `prev?` | 갱신된 항목 |

  실패는 **예외가 아니라 결과**로 낸다: `{"ok": false, "error": {"kind": "not_found"|"usage"|"rejected",
  "message": ..., "detail": ...}}` — exit code 3/2/1과 1:1. 모델이 읽는 값이므로 stderr 진단은 `message`에
  합친다. 도구 description은 영어(원칙 6)이고 **짧게**(스키마는 세션마다 컨텍스트에 실린다).
- 서버 이름 규약: `bb-<플러그인>`(도구 이름 `mcp__bb-<플러그인>__read` …). 한 작업 폴더에 Daedalus
  플러그인이 여럿이면 서버도 각각이다(스키마·상태 폴더가 다르다).
- 테스트: 핸들러 함수를 **직접** 호출하는 단위 테스트(CLI 테스트와 같은 시나리오 — 1:1 매핑 표를 파라미터화),
  stdio 왕복 스모크 1건(mcp 클라이언트로 `list` 한 번), 오류 kind ↔ 옛 exit code 대응 표 테스트.

## 4. 단계 2 — 컴파일러 (커밋 2)

- **`.mcp.json`**: 두 타깃 모두 `bb-<플러그인>` 항목 — `command: "daedalus-bb"`, `args: ["--schemas",
  "<스키마 경로>"]`. LOCAL은 작업 폴더 기준 상대 경로(`schemas/<플러그인>.json`), MARKETPLACE는
  `${CLAUDE_PLUGIN_ROOT}/schemas/<플러그인>.json`. `mcp_server_defs`와 같은 병합 경로(사용자 정의와 이름
  충돌 시 경고 `bb_server_name_taken`).
- **프론트매터 권한 유도** (단일 진실 함수 하나: `compiler/emit/blackboard_tools.py::bb_tools_for(node|component,
  project) -> list[str]`): reads가 있으면 `read`·`list`, writes가 있으면 `init`·`write`·`validate`,
  배치된 단계(진행 기록 소유자)는 `progress_read`·`progress_set`. 스킬은 `allowed-tools`에 **합류**(기존 목록
  + 유도, 중복 제거). 워크플로 에이전트는 `tools`가 목록일 때만 합류(`None`이면 전부 상속이라 건드리지
  않는다), LOCAL이면 `mcpServers`에 `bb-<플러그인>` 합류(기존 유도 함수에 자연 합류). fork 스킬은 도구를
  늘리지 못하므로 그 **fork 에이전트**(`ForkAgent`)의 `tools`에 합류한다 — 외부 fork 에이전트는 산출 파일이
  없어 못 한다(설계 문서에 한계 기록, 검증 경고 `bb_tools_unreachable` 1건: 블랙보드를 쓰는 fork 스킬의
  기반이 외부 fork 에이전트일 때).
- **산출 문구 교체**: `State CLI:` 줄 → `Blackboard tools: mcp__bb-<플러그인>__* (server bb-<플러그인>)`;
  진행 명령(`_progress_cli`·fork "## Report"·비동기 인계) → `progress_set` 도구 호출 서술
  (`call progress_set with completed=[...], current=..., prev=..., note="..."`); 가이드 "## The daedalus-bb CLI"
  → "## Blackboard tools"(도구 7개 표, 오류 kind 의미, **도구가 없을 때** 폴백: 서버가 안 떠 있다고 사용자에게
  알리고 상태 파일을 손으로 고치지 말라 — 종전 `command -v` 폴백 문구는 폐기). 문구는 영어(원칙 6,
  `tests/compiler/test_output_language.py`).
- 골든 재생성(`python -m tests.data.golden.regen`), 프론트매터 유도 테스트(reads만/writes/배치/fork 기반 ForkAgent/
  외부 fork 기반 경고/에이전트 tools None 보존), `.mcp.json` 두 타깃 테스트.

## 5. 단계 3 — CLI 폐기 (커밋 3)

- argparse 진입·`_cmd_*`·서브파서 삭제. `daedalus-bb` 콘솔 스크립트는 **서버 진입점**이 된다. 코어는
  `daedalus/cli/core.py`에 남는다(패키지 이름 `cli`는 유지 — 임포트 계약 테스트가 그 경로를 본다.
  개명은 별도 항목으로 backlog에).
- CLI 전용 테스트(파싱·exit code·stdout/stderr 채널)는 삭제하고, 시나리오는 단계 1의 핸들러 테스트가 이미
  덮는다(덮지 않는 것이 있으면 옮긴다 — 삭제만 하지 않는다).
- 문서: `blackboard.md`의 CLI 절을 MCP 절로 교체(1:1 표, 오류 kind, 권한 유도 규칙, 실측 기록),
  `compiler.md` 정책, `architecture.md` 모듈 지도, `guide/01`·`03`·`06`, `backlog.md`(CLI 관련 항목 정리 +
  "도그푸드 프로젝트의 CLI 호출 훅 2개는 사용자가 정리" 메모). 퇴역 개념은 흔적 없이(원칙 7).

## 6. 공통 규약

- `python -m pytest tests/ -q`(pytest 직접 실행 불가). 시작·끝 전체 통과. 계획만 쓰고 멈추지 말고 끝까지 구현.
  Pyright 스테일 경고 무시, 런타임으로 검증.
- 코드 위생: 800줄 초과 파일은 먼저 쪼갠다(1,200줄 상한 테스트). 판정·유도 함수는 한 곳. 조용한 실패 금지.
- **`project/daedalus_cc_plugin/`·실행 중 Daedalus 앱·MCP 서버는 건드리지 않는다.** 임시 파일은 스크래치패드에만.
- 커밋: 워크트리 브랜치에 **3개**(서버 / 컴파일러 / CLI 폐기), 한국어, 끝에
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` /
  `Claude-Session: https://claude.ai/code/session_01Rc2KHE3Vg6mDkkvLaKNpW4`. **push 금지.** 워크트리 삭제 금지.
