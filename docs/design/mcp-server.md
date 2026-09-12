# 앱 내장 MCP 서버 (WP-MCP)

> CLAUDE.md에서 이관한 설계 기록(2026-09-12, 원문 그대로). 코드와 어긋나면 코드가
> 정본이다 — 발견 즉시 이 문서를 고친다. 색인은 루트 `CLAUDE.md`의 "설계 문서" 절.

## 앱 내장 MCP 서버 (WP-MCP)

- **성격:** "CC가 쓰는 도구 모음"이 아니라 **사람이 GUI에서 작업하는 중에 CC가 같은 프로젝트를
  함께 보고 함께 만지는 통로**다. 그래서 CC는 사용자의 현재 선택을 알 수 있고(`get_selection`),
  CC의 편집은 사용자의 undo 스택에 들어가며, 스크립트 리스너에 사람 편집과 같은 형식으로 남는다.
- **패리티 원칙 (사용자 확정, 2026-09-07 — 상시 적용):** GUI에서 가능한 모든 편집·조회는 MCP로도
  가능해야 한다. **새 GUI 기능을 넣을 때 대응 MCP 도구(또는 기존 도구의 파라미터)를 같은 WP에서
  함께 만든다** — 나중에 채우는 갭이 아니라 기능의 완성 조건이다. 기존 갭 목록은
  MCP 갭 실측 보고(G1~G16 편집 갭 + Q1~Q6 조회 낭비)가 정본이고 패리티 배치로 전량 소거 완료(2026-09-07).
- **조회는 개요 ↔ 전문으로 나눈다 (Q1).** 목록을 주는 도구는 각 항목을 축약본으로 싣고, 전문은
  그 하나를 지목하는 도구가 준다 — `get_body_outline` ↔ `get_body_section`이 그 원형이고,
  `get_project`의 `hook_library`(개요: 이름·이벤트·matcher·핸들러 개수·설명) ↔ `get_hook(name)`
  (전문: 핸들러 CC 스키마 + 스크립트 본문)이 같은 논리다. 개요에 셸 스크립트 전문을 실으면
  프로젝트를 볼 때마다 그 값을 통째로 낸다. 축약본 헬퍼 `_hook_summary`의 소유는 `_base.py`다 —
  `QueryTools`와 `HookTools`가 함께 쓰므로 한쪽 믹스인에 두면 합성 순서에 기대는 호출이 된다.
- **쓸 수 있으면 읽을 수도 있어야 한다 (Q2).** `set_transition(guard=)`으로 가드를 쓸 수는 있는데
  어떤 도구로도 읽을 수 없던 갭을 `get_project`의 전이 요약에 `guard`(컴파일러 `_describe_guard`
  재사용 — 화면·산출·조회가 같은 문구를 말한다)와 `waypoint_count`로 메웠다.
- **`get_component`의 config는 비기본값만 싣는다 (Q3).** 예전에는 `vars(config)`를 통째로
  덤프해 미지정 필드(대개 `None`)까지 매번 실었다 — 무엇이 실제로 손댄 값인지 알려면
  선언 기본값과 일일이 대조해야 했다. 이제 `type(config)()`로 만든 기본 인스턴스와 필드별로
  비교해 **다른 값만** 낸다(선언 기본값과 같으면 생략 — 컴파일러 "OPTIONAL 값이 선언 기본값과
  같으면 생략" 규칙과 같은 논리). 전체 상세(선택지·emit 위치 포함)가 필요하면
  `list_component_fields`를 쓰라 — 그쪽은 여전히 전 필드를 낸다.
- **`get_project`는 구획을 골라 받을 수 있다 (Q4).** `sections=["components", "canvas"]`처럼
  주면 그 구획만 돌아온다 — 구획은 `meta`(이름/설명/버전/빌드타깃/저장경로/진행훅토글/MCP서버
  정의/undo상태)/`components`(skills/agents)/`canvas`(placements/transitions/references)/
  `blackboard`(blackboard_classes)/`hooks`(hook_library + global_hooks). **`sections` 생략 시
  전체**가 돌아온다.
  알 수 없는 구획 이름은 거부.
- **작업 폴더 문서는 존재 신호를 낸다 (Q6).** `meta`의 `workspace_docs`
  (`{claude_md: bool, rules: N}`) — 내용이 아니라 **있다는 사실**만이다(개요 ↔ 전문 분리와
  같은 논리로 내용은 `list_workspace_docs`/`get_workspace_doc`). 신호가 없으면 그 표면이
  있다는 것 자체를 몰라 `.claude/CLAUDE.md` 구역과 규칙이 조용히 잊힌다. `claude_md`는
  **내용이 있는가**로 본다 — 빈 문서는 컴파일이 구역을 제거하므로 있으나 마나다.
- **검증 결과도 걸러 받는다 (Q5).** `validate_project(severity="error"|"warning",
  component="이름")`. 컴포넌트 판정은 캔버스 우클릭 "관련 경고 보기"와 **같은 실체**
  (`view/actions/warnings.findings_for`)라 subject·path 루트·**그래프 placement 노드** 세
  경로를 모두 본다(placement를 빼면 `mid_chain_user_invocable`처럼 subject가 노드인 규칙을
  통째로 놓친다). 개수는 **필터 전후를 둘 다** 낸다 — `error_count`/`warning_count`는 걸러진
  목록 기준이고 `total_*`가 프로젝트 전체다(필터를 걸어 0을 보고 "컴파일이 통과한다"로
  읽으면 안 된다).
- **컴파일 dry-run `compile_check(out_dir=None)` (G3).** `validate_project`는 모델 검증만 본다 —
  컴파일러가 emit하는 경고 7종(`dangling_file_ref`/`unknown_skill_files_dir`/
  `dangling_skill_file_ref`/`missing_mcp_server_def`/`unmergeable_settings_json`/
  `unmergeable_claude_md`/`rule_body_frontmatter`)은 실제 컴파일(GUI Ctrl+B)에서만 나와,
  MCP-우선 저작에서는 영영 보이지 않았다. 이 도구가 `compile_project(..., dry_run=True)`로
  **파일을 하나도 쓰지 않고** 게이트 판정 + 경고 전체 + 토큰 요약을 돌려준다(컴파일 정책 18번).
  주입은 Ctrl+B와 같은 `MainWindow.compile_inputs()`를 쓰므로 결과가 실제 컴파일과 일치한다.
  파일 쓰기가 없으니 **undo 대상이 아니다**(`save_project` 관례).
- **전송이 HTTP인 이유:** stdio는 **클라이언트가 서버 프로세스를 실행하는** 모델이라 이미 떠 있는
  GUI에 나중에 붙을 수 없다. Streamable HTTP면 앱이 먼저 켜져 서버를 열어두고 CC가 원할 때
  접속하는 순서가 그대로 성립한다. 바인딩은 항상 `127.0.0.1` — 로컬 전용이므로 TLS를 얹지 않는다.
- **기동 지점:** `MainWindow.__init__`이 아니라 **`__main__.main`이 `window.start_mcp_service()`를
  호출**한다. 테스트가 MainWindow를 수십 개 만들기 때문에 자동 기동하면 포트가 서로 충돌한다.
  종료는 `MainWindow.closeEvent` → `service.stop()`.
- **명령줄 인자:** `__main__.parse_args(argv) -> (우리 옵션, Qt에 넘길 argv)` — `parse_known_args`로
  우리 옵션만 떼어내고 나머지는 Qt에 그대로 넘긴다(`-style` 같은 Qt 자체 옵션을 막지 않기 위해).
  `--mcp-port PORT`는 **그 포트만** 쓴다(점유 시 다른 포트로 물러나지 않고 실패 — 물러나면 지정한
  의미가 없다. 고정 포트를 가리키는 `.mcp.json`이 엉뚱한 인스턴스에 붙는다). 여러 인스턴스를 각각
  다른 CC 세션에 붙일 때 쓴다. `--no-mcp`는 서버를 띄우지 않는다.
- **포트:** 기본 `8787`(`endpoint.DEFAULT_PORT`). 점유돼 있으면 위로 훑어 비어 있는 포트를 쓰고
  실제 포트를 `~/.daedalus/mcp-endpoint.json`에 기록한다. `.mcp.json`은 정적 파일이라 고정 포트를
  가리키므로, 여러 창을 띄우면 결과적으로 "먼저 켜진 인스턴스"가 협업 대상이 된다(의도된 동작).
  저장 경로가 바뀌면 `SessionIO.sync_files_root`가 접속 정보의 project 필드도 갱신한다(배선 지점 1개 유지).
- **스레드:** uvicorn이 데몬 스레드에서 돌고, 도구 핸들러는 `MainThreadInvoker`(시그널 +
  `threading.Event`)로 Qt 메인 스레드에 넘겨 실행한다. 위젯·뷰모델을 워커 스레드에서 만지면
  Qt가 깨지기 때문. 모달 다이얼로그로 루프가 막히면 무한 대기 대신 `TimeoutError`(기본 15초).
- **SDK 호환:** mcp 2.0에서 `FastMCP`가 `MCPServer`로 대체됐다. `service._server_factory()`가
  import 성공 여부로 클래스를 고른다 — 두 클래스는 여기서 쓰는 표면(`name`/`instructions`
  생성자 인자, `add_tool`, `streamable_http_app`)이 동일하다. **주의: `list_tools`는 1.x에서
  코루틴, 2.x에서 동기 함수다**(테스트의 `_list_tools` 헬퍼가 흡수).
- **도구 래핑:** `service._wrap`이 `functools.wraps`로 감싸므로 원본 시그니처·타입힌트·docstring이
  보존되고 SDK가 그로부터 입력 스키마를 만든다. 래퍼를 `(**kwargs)`로만 노출하면 **도구에 인자가
  없는 것으로 보여 CC가 값을 넘길 방법이 사라진다**(`test_tool_schema_exposes_arguments`가 고정).
- **편집은 전부 CommandStack 경유**(`create_skill`/`create_agent`/`rename_component`/
  `place_component`/`create_state`/`move_state`/`rename_state`/`delete_state`/`connect_states`/
  `disconnect_states`/`undo`/`redo`) — 사용자가 Ctrl+Z로 되돌릴 수 있다. `delete_state`는 연결
  전이까지 `MacroCommand`로 묶어 1 undo 단위. **본문(`set_component_body`)만 예외적으로 컴포넌트의
  QTextDocument에 적용**하는데, 우회가 아니라 본문 전용 undo 스택(WP-BU)에 정확히 올리는 경로다.
- **포트·분기 의미론(WP-CE):** `set_transfer_on`(출력 포트)/`set_transition`(기존 전이의
  trigger·guard)/`connect_states`의 trigger·guard 인자.
  **구조(노드+선)만 만들면 분기가 표현되지 않는다** — 여러 갈래로 나가는 노드는
  transfer_on에 갈래를 선언하고 각 전이에 trigger를 물려야 캔버스 포트가 갈라지고 라벨이 보인다.
  `set_transition`은 None=건드리지 않음, ""=지움 규약이다. `set_agent_calls(skill, events)`(G6)는
  `set_transfer_on`의 call_agents 짝 — 에이전트 호출 포트 **전체**를 한 번에 교체한다(`add_agent_call`/
  `remove_agent_call`은 하나씩 넣고 빼는 지름길로 존치). 포트 description이 호출 계약(WP-CT)의 유일한
  채널이라 여러 포트를 함께 고쳐야 할 때의 실질 결손이었다 — 구현은 `set_transfer_on`과 같은
  `_make_event_defs` + `SetAttrCmd`(새 리스트).
- **진입점 프리셋(G5):** `set_entry_preset(name, preset)` — `preset`은 `entry`/`user_only`/`pure`/
  `default` 4종(`view/actions/entrypoint.EntryPreset`과 매핑). **`apply_entry_preset`을 그대로
  호출한다**(캔버스 우클릭 "진입점 설정"·스킬 에디터 프론트매터 콤보와 같은 실체) — 두 필드가 1 undo
  단위로 함께 바뀌고, 이미 그 프리셋이면 no-op(`changed: False`). FIXED 종류(transfer/reference)·
  에이전트는 `supports_entry_presets`가 거부하며 이유를 말한다(프리셋을 걸어도 컴파일이
  `fixed_value`를 강제해 아무 일도 안 일어나는 상태를 만들지 않기 위해서다).
- **블랙보드(WP-CE + G1·G2 패리티):** `create_blackboard_class`/`update_blackboard_class`(이름·설명,
  None=건드리지 않음)/`delete_blackboard_class`/`set_blackboard_fields`(목록 통째 교체)/
  `set_state_access`(노드의 reads/writes 선언 → 캔버스 뱃지 + 컴파일 산출 구체화). GUI 블랙보드 탭이
  하던 편집이 전부 올라왔고, 패널과 달리 **전부 CommandStack 경유라 undo된다**.
  - **타입 검증은 `_build_blackboard_fields` 하나**다(생성·교체 공용) — 두 벌이면 도구에 따라
    통과하는 값이 달라진다. 스칼라 4종 + collection none/list/set + 필드명 중복 거부.
  - **개명은 참조를 따라가고 삭제는 따라가지 않는다.** 개명은 `rename_component`(문자열 참조 3종
    일괄 갱신)와 같은 관례로 상태 reads/writes의 `"Class"`/`"Class.field"`를 함께 고치고 그 전부가
    1 undo 단위다(이름만 되돌아가면 중간에 참조가 깨진 상태를 거친다). 삭제는 `delete_hook`/
    `delete_component`와 같이 참조를 두고 `still_referenced_by`로 **보고**한다 — 지우면 undo로
    클래스가 돌아와도 참조는 돌아오지 않는 비대칭이 된다. 남은 참조는 `dangling_blackboard_ref`가 짚는다.
  - **필드 교체는 개명을 알 수 없다.** 목록만으로는 "이름 바꿈"과 "지우고 새로 넣음"이 구분되지
    않으므로 `"Class.field"` 참조를 따라가지 않고, 사라진 필드를 가리키던 노드를
    `dropped_field_references`로 보고한다.
  - 판정의 단일 진실은 모델의 `blackboard_rename_ref_updates`/`blackboard_class_referrers`이고
    **GUI 패널의 이름 변경도 같은 함수를 쓴다** — 같은 조작이 표면마다 다른 결과를 내면 안 된다.
  - 화면 반영은 `BlackboardPanel.refresh_external()`(선택 보존)이다. 목록만 다시 그리면 같은 행이
    선택된 채라 `setCurrentRow`가 시그널을 내지 않아 설명·필드 테이블이 스테일로 남으므로,
    목록 재구성 뒤 현재 행을 **명시적으로** 다시 로드한다.
- **에이전트 호출은 캔버스와 같은 규칙을 강제한다(WP-CE).** 초기 구현은 스킬→에이전트를 그냥
  직결시켰는데, 캔버스는 그걸 **막는다**(`FsmScene`: 에이전트 노드 입력은 call_agent 포트에서만,
  call_agent 포트는 에이전트로만). 같은 조작인데 경로에 따라 결과가 달라지면 협업 도구로 실격이라
  `connect_states`가 동일 규칙을 검사한다. 포트는 `add_agent_call(skill, event)`로 먼저 만든다.
  **호출 포트는 에이전트도 가진다**(2026-09-12 — CC 중첩 스폰 허용): 포트 도구 3종은 절차형
  스킬·state 용도 랩핑 스킬·에이전트를 받고, 판정의 단일 진실은
  `PortTools._require_call_port_owner`다. 에이전트가 에이전트를 부르면 깊이·모델 티어 제약을
  검증이 에러로 짚는다(`agent_chain_too_deep`/`agent_calls_higher_model`).
  (계약 카드 자동 생성은 WP-CT로 퇴역 — 호출 계약은 컴파일이 그래프에서 유도한다.)
- **에이전트 스코프(WP-RF-1c):** 도구의 `agent` 파라미터는 **시그니처째 제거**됐다(스키마 노출
  기준). 캔버스 편집(`_scope`)의 대상은 프로젝트 그래프 하나뿐이고,
  `_find_component(name)`은 전역 스킬/에이전트만 찾는다 — v1 파일의 로컬 스킬은 로드 시 전역
  승격되므로 별도 접근 경로가 필요 없다.
- **훅 라이브러리(WP-CE 4차):** `create_hook`/`update_hook`/`delete_hook`(라이브러리 = 정의의
  단일 진실) + `set_component_hooks`(스킬/에이전트가 이름으로 참조). GUI 훅 패널(상주 탭)은 모델에
  직접 쓰지만 MCP 경로는 `AppendToListCmd`/`RemoveFromListCmd`/`SetAttrCmd`를 거쳐 undo된다.
  `update_hook`은 빈 문자열/None = 건드리지 않음, matcher·description은 ""로 지움, timeout은 0이
  지정 없음이다. **삭제는 참조를 건드리지 않는다**(GUI와 같은 정책) — 남은 참조는
  `dangling_hook_ref` 경고로 드러나므로 결과의 `still_referenced_by`로 보고한다.
  `set_component_hooks`는 라이브러리에 없는 이름을 **거부**한다(오타가 컴파일까지 조용히 흘러가
  경고로만 드러나는 것을 막는다). `config.hooks`의 선언 기본값은 `{}`가 아니라 `None`이라,
  undo는 빈 dict가 아니라 None으로 되돌아간다.
  - **전역 훅 조회 + 프로젝트로 복사 (G7).** `get_project`의 `hooks` 구획에 `global_hooks`
    (이 프로젝트에서 가려지지 않은 전역 훅 개요, `_visible_global_hooks` — `HookLibraryPanel.
    _global_hooks`와 같은 판정)가 실린다. `copy_global_hook(name)`이 GUI "프로젝트로 복사"와
    같은 실체 — `preset_copy` 깊은 복사 + **이름 유지**(병합 규칙이 요구: 동명 프로젝트 훅이
    전역을 덮으므로 이름을 바꾸면 참조가 전역을 계속 가리킨다) + `AppendToListCmd`로 undo.
    이미 프로젝트에 같은 이름이 있으면 거부(복사할 이유가 없다 — 이미 그쪽이 이긴다).
  - **훅 프리셋에서 생성 (G8).** `list_hook_presets()`가 `BUILTIN_HOOK_PRESETS` 요약(이름·설명·
    이벤트·matcher·핸들러 타입)을 낸다. `create_hook(name, preset="...")`은 GUI 훅 패널
    "프리셋에서 추가"와 같은 실체(`preset_copy`) — `event`/`handlers`/`matcher`/`description`/
    `command`와는 **함께 줄 수 없다**(프리셋을 그대로 쓰거나 처음부터 직접 만들거나 반쯤 섞으면
    어느 값이 이겼는지 알 수 없다).
- **참조 노드 배치(WP-CE 4차):** `place_reference`/`link_reference`/`unlink_reference`/
  `unplace_reference`. 참조 노드는 상태가 아니라 **여러 상태가 공유하는 문서**라 같은 스킬을
  여러 번 놓을 수 있어(그래서 `place_component`와 별도 도구다) 이름 + `index`로 지목한다.
  구현은 `FsmScene.drop_reference_skill`/`create_reference_link`/`delete_reference_node`를
  그대로 호출한다 — 캔버스와 같은 커맨드·같은 `_sync_refs_to_model` 경로다. 프로젝트 캔버스
  전용(`agent` 인자 없음).
- **프로젝트 속성(WP-CE 4차 + G4):** `set_project_properties(name/description/version/build_target/
  emit_progress_hook)` — 문자열 필드는 빈 값이 건드리지 않음이고, `emit_progress_hook`(bool 필드,
  A8 tri-state가 아니다 — 미지정 상태 자체가 없다)은 그 자리를 `None`이 대신한다(GUI 프로젝트 속성
  다이얼로그의 "세션 시작 시 진행 상태 자동 주입" 체크박스와 같다, WP-RS). 여러 필드를 한 번에 주면
  `MacroCommand`로 1 undo 단위가 된다. `set_component_description`도 이때 커맨드화됐고(이전에는 이
  편집만 Ctrl+Z가 듣지 않았다) `set_component_when_to_use`가 함께 붙었다.
- **MCP 서버 정의(WP-MW):** `set_mcp_server_def(name, config)` — 이름 → `.mcp.json` 서버 객체를
  `project.mcp_server_defs`에 등록/갱신(config=None이면 삭제, 미존재 삭제는 거부). SetAttrCmd에
  **새 dict**를 넘겨 undo 가능(제자리 수정이면 undo가 같은 객체를 가리킨다). LOCAL 컴파일의
  설치 배선(`missing_mcp_server_def` 경고 해소)에 쓰인다. `get_project`가 `mcp_server_defs`를 포함.
- **프론트매터 필드:** `list_component_fields`(필드 목록 + 현재값 + enum 선택지 + emit 위치)와
  `set_component_field`(SetAttrCmd 경유 — undo 가능). 대상 필드 집합은 `SKILL_FIELD_MATRIX`/
  `AGENT_FIELD_MATRIX`에서 뽑으므로 매트릭스가 늘면 도구가 따라간다. 타입 강제는
  `_config_field_types`(`get_type_hints` — `from __future__ import annotations` 탓에 dataclass의
  `f.type`이 문자열이라 그대로 쓸 수 없다) + `_coerce_field_value`가 맡고, 잘못된 enum 값은
  선택지를 나열하며 **거부**한다(조용히 문자열이 들어가면 컴파일 산출이 이상해질 때까지 안 드러난다).
  `hooks`는 `set_component_hooks`로 안내하며 거절한다.
- **카탈로그 후보 조회 (G9):** `list_tool_candidates()` — 읽기 전용. ALLOWED_TOOLS/TOOLS/
  DISALLOWED_TOOLS TagInput이 보여주는 자동완성 목록과 **같은 산출**을 낸다
  (`catalogue_loader.candidate_strings` + `load_catalogue`를 GUI(`app._tool_candidates`)와
  같은 경로 — 저장 경로 기준 프로젝트 폴더 + 전역 `~/.daedalus/catalogue/`로 재사용). 카탈로그에
  무엇이 있는지 몰라 `allowed_tools`에 이름을 짐작으로 적는 것을 막는다.
- **세션(저장/열기/새 프로젝트/패키지):** `save_project`/`open_project`/`new_project`(G11)/
  `import_package`(G12)/`export_package`/`list_recent_projects`/`list_project_templates`(G11).
  경로는 **폴더**를 받는다(WP-PK — 구버전 파일도 열린다). **저장이 여는 절차
  안에 있다** — 편집 중인 내용은 메모리에만 있어 여는 순간 사라지므로, 잃을 것이 있으면
  (`MainWindow.project_has_content()` — "새 프로젝트" 확인 다이얼로그와 같은 판정) 먼저 저장하고
  **저장할 수 없으면 열지 않는다**. 한 번도 저장한 적 없으면 `save_current_as`로 경로를 받아야
  하고, 버리려면 `save_current=False`를 명시해야 한다. 이를 위해 `MainWindow._save_to_path`/
  `open_path`가 `bool`을 돌려준다(GUI 경로는 상태바 문구로 결과를 말하므로 무시한다 — 반환값은
  성공을 전제로 다음 단계를 진행하는 호출자를 위한 것이다). 저장은 파일 쓰기라 undo 대상이 아니다.
  **그 게이트의 실체는 `SessionTools._save_before_switch` 하나**이고 `open_project`와
  `new_project`가 공유한다 — 게이트가 둘로 갈리면 한쪽 경로로만 변경이 사라진다.
  - `new_project(template_id=None, build_target=...)`는 Ctrl+N 통합 다이얼로그와 **동형**이다:
    빈 프로젝트 또는 템플릿에서 시작하고, **여기서 고른 타깃이 템플릿에 저장된 타깃을 이긴다**
    (템플릿 내용은 타깃 중립, 타깃은 사용자 소유). 폴더형 템플릿의 동봉 파일 예약
    (`_pending_template_assets`)까지 GUI와 같으므로 첫 `save_project`에 `files/`가 딸려 온다.
    알 수 없는 템플릿 id는 **저장 전에** 거절한다(헛저장 방지 — 열 수 없는 경로 거절과 같은 순서).
  - `import_package(archive, dest)`는 `package.unpack`(zip slip 방어 내장)으로 푼 뒤
    **`open_project`를 그대로 태운다** — 저장 게이트가 같다. 게이트에 막히면 풀린 폴더는 남는다.
- **생성+배치는 1 undo다 (G14/S1).** `create_skill`/`create_agent`에 `x`·`y`를 **함께** 주면
  `view/actions/creation.create_and_place`를 타 생성과 배치가 한 `MacroCommand`로 묶인다(캔버스
  "여기에 만들기"와 같은 경로). 좌표를 생략하면 만들기만 한다. 같은 배치에서 props의 자체 팩토리
  dict 2벌을 `creation.make_component` 호출로 환원했다 — 기본 출력 포트 `done`이 양쪽에
  하드코딩돼 있어 한쪽만 고치면 어디서 만들었느냐에 따라 다른 에이전트가 됐다.
  `declarative`/`transfer`는 캔버스 노드가 아니므로 좌표를 주면 **거절**한다(조용히 무시하면
  "설정했는데 아무 일도 일어나지 않는" 상태가 된다).
- **transfer 스킬 생성+할당도 1 undo다 (G15).** `set_transition(create_transfer="이름")`이
  캔버스 엣지 메뉴의 "새 Transfer Skill 생성..."과 **같은 두 커맨드**
  (`AddSkillToProjectCmd` → `SetTransitionSkillRefCmd`)를 조립한다 — 씬 메서드는 이름을 모달로
  묻는 부분과 한 몸이라 그대로 부를 수 없다. `transfer`(기존 스킬 지정)와 동시에 줄 수 없다.
- **레이아웃(G13/G10):** `move_reference(name, x, y, index=0)`가 `move_state`의 짝이고
  캔버스 드래그와 같은 `MoveRefCmd`를 쓴다(모델 `reference_placements` 좌표까지 sync).
  `set_transition_waypoints(source, target, points)`는 엣지 경유점(WP-ER)의 **교체 1종**이다 —
  캔버스는 하나씩 추가·드래그하지만 좌표를 한 점씩 넣는 도구는 의미가 없다. 기존
  `ClearWaypointsCmd`+`AddWaypointCmd`를 `MacroCommand`로 묶어 1 undo 단위이고(새 커맨드를
  만들면 캔버스 조작과 되돌림 단위가 어긋난다), 읽기는 전이 요약의 `waypoint_count`다.
- **선택은 편집이 아니다 (G16).** `focus_node(name)`(단독 선택 + 탭 전환 + 센터링 —
  `ValidationActions.focus_in_project_canvas` 재사용)과 `select_nodes(names)`
  (`FsmScene.select_state_vms` — 씬이 아이템을 쥐므로 선택 조작의 실체도 씬에 둔다)는
  `get_selection`의 쓰기 짝이며 **커맨드 스택을 거치지 않는다**. 거치면 Ctrl+Z가 "무엇을
  보고 있었는가"를 되감는 빈 단계로 채워진다. `select_nodes`는 없는 이름이 하나라도 있으면
  **아무것도 선택하지 않고 거부**한다 — 일부만 선택해 놓고 성공을 보고하면 나머지도 선택된
  줄 안다.
- **컴포넌트 삭제(A2):** `delete_component(name)` — `RemoveComponentCmd`를 거쳐 **undo 가능**하고
  GUI 레지스트리 삭제(`MainWindow.delete_component`)와 **같은 커맨드**를 쓴다(조작 경로에 따라
  Ctrl+Z가 듣고 안 듣고가 갈리면 협업 도구로 실격). 상세는 아래 "컴포넌트 삭제 커맨드 (A2)" 참조.
  이름 참조(`AgentConfig.skills`/`ProceduralSkillConfig.agent`)는 정리하지 않고 결과의
  `still_referenced_by`로 **보고**한다 — 지워 버리면 되돌려도 참조가 돌아오지 않는 비대칭이 된다.
  남은 참조는 `dangling_string_reference` 경고가 짚는다. 미노출 편집은 이제 없다.
- **연결 방법:** 도구 메뉴 → "MCP 서버 정보..."가 접속 주소와 `.mcp.json` 스니펫
  (`{"mcpServers": {"daedalus": {"type": "http", "url": "http://127.0.0.1:8787/mcp"}}}`)을 보여준다.
