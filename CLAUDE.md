# Daedalus

FSM 기반 Claude Code 플러그인 하네스 엔지니어링 도구.
스킬(Skill)과 에이전트(Agent) 컴포넌트를 FSM + Blackboard 모델로 설계하고, 컴파일러 패턴으로 플러그인 파일을 생성한다.

## 개발 환경

```bash
pip install -e ".[dev]"      # 개발 의존성 설치
python -m pytest tests/ -v   # 전체 테스트
python -m pytest tests/model/fsm/ -v      # FSM 코어만
python -m pytest tests/model/plugin/ -v  # 플러그인 레이어만
```

pytest는 `python -m pytest`로 실행한다 (`pytest` 직접 실행 시 command not found).

## 아키텍처

**컴파일러 패턴:** 순수 모델(model/) → 컴파일러(compiler/) → 플러그인 파일

현재 구현 범위: **model/ + view/ + compiler/** (FSM 코어 + 플러그인 메타데이터 + PySide6 에디터 + SKILL.md/agent .md 생성).

**경계 계약 (WP-RF-2, B안 — 물리 이동 없음):** core = `model/` + `compiler/` + `mcp/endpoint.py` + `cli/`.
core는 Qt 바인딩(PySide6/PyQt6/shiboken6)·GUI 레이어(`daedalus.view`)·MCP SDK(`mcp`)·`uvicorn`을
임포트할 수 없다 — `tests/test_import_contracts.py`가 **소스 AST 기준**으로 강제한다(런타임 임포트 차단만으로는
함수 안 지연 임포트를 놓친다. 접두 매칭은 점 단위 — `daedalus.mcp`는 SDK `mcp`와 다르다). `mcp/tools/`는
core가 아니라 **GUI 어댑터**(MainWindow·VM·커맨드 스택 결합 표면 — 각 믹스인 모듈 docstring 명시)이고,
`mcp/invoker.py`의 Qt 의존과 `mcp/service.py`의 SDK/uvicorn 의존은 의도된 설계다. view→compiler 방향
임포트는 정상(컴파일러 패턴의 방향과 일치).

```
daedalus/
├── model/
│   ├── fsm/          # 순수 FSM 개념 (Claude 무관)
│   │   ├── event.py        # 이벤트 계층 (StateEvent, CompletionEvent, BlackboardTrigger)
│   │   ├── variable.py     # Variable + VariableScope/FieldType/ConflictResolution
│   │   ├── strategy.py     # EvaluationStrategy 계열 (Guard용) + ExecutionStrategy 계열 (Action용)
│   │   ├── guard.py        # Guard(evaluation: EvaluationStrategy)
│   │   ├── action.py       # Action(name, execution, output_variable)
│   │   ├── state.py        # State(ABC, reads/writes: list[str] 블랙보드 접근 선언 — WP-BB, "Class"/"Class.field" 문자열 참조), SimpleState, CompositeState, ParallelState, Region
│   │   ├── pseudo.py       # ChoiceState, TerminateState, EntryPoint, ExitPoint
│   │   ├── transition.py   # Transition + TransitionType
│   │   ├── join.py         # JoinStrategy (병렬 조인 전략 — 순수 FSM 개념. 정본 위치, 필요한 곳이 직수입)
│   │   ├── blackboard.py   # Blackboard, DynamicClass, DynamicField(FieldType 사용), FIELD_TYPE_TO_JSON_SCHEMA, BLACKBOARD_FIELD_TYPES(WP-BT — 블랙보드 필드 허용 타입 4종)
│   │   ├── section.py      # Section(자유 콘텐츠 계층 — 이제 v1 sections 트리 마이그레이션 입력으로만 쓰임),
│   │   │                   #   EventDef(transfer_on 출력 이벤트/에이전트 출력 포트 정의 — name/color/description),
│   │   │                   #   render_markdown(v1 sections→body 마이그레이션 헬퍼 — serialize._migrate_v1이 사용)
│   │   └── machine.py      # StateMachine
│   ├── plugin/       # Claude 플러그인 메타데이터
│   │   ├── enums.py        # ModelType, EffortLevel, SkillContext, PermissionMode, AgentField, FieldEmit, BuildTarget(WP-TG) 등
│   │   ├── policy.py       # ExecutionPolicy (병렬 서브에이전트). JoinStrategy는 fsm/join.py에서 직수입 (re-export 없음 — RF-1b)
│   │   ├── config.py       # ComponentConfig(ABC), SkillConfig(ABC), ProceduralSkillConfig,
│   │   │                   # DeclarativeSkillConfig, TransferSkillConfig, ReferenceSkillConfig, AgentConfig
│   │   ├── base.py         # PluginComponent(ABC), WorkflowComponent(ABC)
│   │   ├── skill.py        # Skill(ABC), ProceduralSkill, DeclarativeSkill, TransferSkill, ReferenceSkill
│   │   ├── agent.py        # AgentDefinition
│   │   ├── tool.py         # Tool(ABC) + BuiltinTool/MCPTool/UserDefinedTool (tool_shelf 도구 단일 진실)
│   │   ├── hook.py         # HookDef + HookEvent(CC 9종) (hook_library 훅 단일 진실)
│   │   ├── hook_presets.py # BUILTIN_HOOK_PRESETS (복사용 훅 템플릿) + preset_copy(핸들러까지 깊은 복사)
│   │   ├── variables.py    # 본문 경로 변수(WP-RT) — ${ROOT} 타깃 중립 토큰, 타깃별 확장 매핑, 구버전 마이그레이션
│   │   └── field_matrix.py # FieldRule(emit 포함), SKILL_FIELD_MATRIX, AGENT_FIELD_MATRIX (스킬/에이전트 유형별 프론트매터 필드 규칙)
│   ├── project.py           # PluginProject (최상위 컨테이너, name+description+version — plugin.json 매니페스트 소스), ReferencePlacement, tool_shelf, hook_library, blackboard(최상위), graph(워크플로 백킹 머신)+graph_layout+edge_layout(WP-ER 엣지 웨이포인트, 키: Transition.id), emit_progress_hook(WP-RS SessionStart 진행 상태 훅 토글, 기본 True), build_target(WP-TG 빌드 타깃 — MARKETPLACE/LOCAL, 기본 MARKETPLACE), mcp_server_defs(WP-MW — 이름→.mcp.json 서버 객체, LOCAL 설치 배선 소스)
│   │                       # + rename_component(project, component, new_name) — 이름 변경 + 문자열 참조 3종 일괄 갱신 (Qt 무관)
│   │                       # + remove_component(project, component) → list[str] — 모델 정리 (graph placement, skill_ref None화 등)
│   ├── package.py           # 프로젝트 패키지(WP-PK) — 폴더가 곧 프로젝트. PROJECT_FILENAME(".daedalus.json")/ARCHIVE_SUFFIX(".ddpj"),
│   │                       #   resolve_project_file(저장 대상)/find_project_file(열 대상)/project_dir/display_name,
│   │                       #   pack(결정적 zip)/unpack(zip slip 방어). Qt 무관 순수 stdlib.
│   ├── outline.py           # 본문 아웃라인(WP-BO) — body 마크다운의 파생 인덱스. parse_outline(fence-aware 헤딩 파서)/
│   │                       #   find_section(제목·"## 제목" 레벨 지정·"부모 > 자식" 경로, 0개·복수 매칭 ValueError)/
│   │                       #   section_text/char_span/replacement_text/replace_section(비교체 구간 바이트 보존). Qt 무관 순수 stdlib.
│   ├── serialize.py         # serialize_project/deserialize_project (모델↔JSON dict, 안정 ID 기반, format 2)
│   │                       # + _migrate_v1(v1→v2 단방향 마이그레이션 집약 — RF-1b, "안정 ID + 직렬화" 항목 참조)
│   └── validation/          # 모델 검증 (Qt·파일시스템 무관). 구 validation.py를 WP-RF-3d로 패키지 분해(이동만·동작 불변)
│       ├── __init__.py     #   재-export 파사드 + `Validator(_MachineRules, _ProjectRules)` 합성 — 분해 전 모듈의 모든 속성
│       │                   #   (public + 테스트가 쓰는 _헬퍼)과 `Validator._check_*` 이름 전부 보존(기존 임포트 무수정 동작)
│       ├── severity.py     #   ValidationError(rule/message/source/subject/path + is_warning) + WARNING_RULES(경고 등급 단일 진실)
│       ├── machine_rules.py#   머신 수준 규칙 18종(_MachineRules 믹스인 — validate/_validate_machine 재귀 + _STATE_ACTION_FIELDS)
│       │                   #   + SKIPPABLE_RULES(skip_rules 허용 이름)
│       └── project_rules.py#   프로젝트 수준 규칙 18종(_ProjectRules 믹스인 — validate_project) + CC_BUILTIN_TOOLS
│                           #   + _strip_markdown_code(본문 검사 시 코드 스팬 제외)
├── compiler/         # 순수 모델 → 플러그인 파일 (Qt 무관)
│   ├── emit/               # model → SKILL.md/agent .md/hooks.json 텍스트 (결정적, LF). 구 emit.py를 WP-RF-3a로 패키지 분해(이동만·동작 불변)
│   │   ├── __init__.py     #   재-export 파사드 — 분해 전 emit.py의 모든 속성(public + 테스트가 쓰는 _헬퍼) 그대로 제공,
│   │   │                   #   기존 `from daedalus.compiler.emit import …` 임포트 전부 무수정 동작(test_emit_facade.py가 고정)
│   │   ├── common.py       #   공용 헬퍼 — _enum_value/_config_default/_MISSING/_body_block/_join_blocks/_build_target/_is_local_build/_graph_placements(_any)
│   │   ├── frontmatter.py  #   YAML 표기(_yaml_scalar/_yaml_list/_yaml_block_lines) + 스킬 프론트매터(_frontmatter_lines_skill)·_compose_description
│   │   ├── sections.py     #   공용 단락 — 가드/트리거·FSM 절차 서술(_describe_fsm)·요구 환경 MCP(referenced_mcp_servers)·블랙보드(_blackboard_section)·tool_shelf
│   │   ├── skill.py        #   SKILL.md 조립 — 다음 단계·작업 재개(WP-RS)·진입 맥락(WP-IC) + compile_skill
│   │   ├── agent.py        #   에이전트 .md 조립 — 프론트매터(skills 합류·LOCAL hooks/mcpServers)·호출 계약·출구 + compile_agent
│   │   ├── hooks.py        #   compile_hooks_json/compile_hook_scripts (진행 상태 합성 훅 포함)
│   │   └── manifest.py     #   compile_plugin_manifest/compile_schemas_json + 경로 변수 확장(expand_root_token/substitute_local_file_refs)
│   ├── project_compiler.py # compile_project(project, out_dir, files_dir=None) → CompileResult (검증 게이트 + 파일 쓰기)
│   │                       # files_dir(WP-FR, 선택): 실존 디렉토리면 <out>/files/ 정렬 순회 복사(_copy_files_tree, 심볼릭 링크 미추종) +
│   │                       #   dangling_file_ref 스캔(_scan_dangling_file_refs). 생략 시 기존 산출 완전 불변(하위 호환).
│   │                       # LOCAL 빌드는 컴파일이 곧 설치(WP-MW) — .claude/ 반입 + _wire_local_install(컴파일 정책 15번 참조).
│   └── wiring.py           # wire_workspace(target, server_entries, hooks_map) → WireResult (WP-MW) — 작업 폴더의 .mcp.json
│                           #   mcpServers + .claude/settings.local.json enabledMcpjsonServers/hooks 병합. 추가/갱신만·멱등·
│                           #   깨진 JSON 불가침. LOCAL 컴파일과 앱 "Claude Code 실행" 메뉴가 공유하는 단일 진실. 순수 stdlib.
├── mcp/              # 앱 내장 MCP 서버 (WP-MCP) — CC와 협업하는 창구
│   ├── endpoint.py         # 접속 정보(~/.daedalus/mcp-endpoint.json) + 포트 탐색 + .mcp.json 스니펫 (Qt 무관 순수)
│   ├── invoker.py          # MainThreadInvoker — uvicorn 워커 스레드 → Qt 메인 스레드 마샬링(시그널+Event, 타임아웃)
│   ├── tools/              # DaedalusTools — 도구 구현(조회·편집·세션·본문 부분 접근(WP-BO)). 메인 스레드 실행 전제.
│   │   │                   #   **GUI 어댑터**(WP-RF-2) — MainWindow·VM·커맨드 스택 결합 표면, core 경계 계약 대상 아님.
│   │   │                   #   구 단일 모듈 tools.py를 WP-RF-3b로 도메인별 믹스인 패키지로 분해(이동만·동작 불변)
│   │   ├── __init__.py     #   재-export 파사드 + DaedalusTools 합성 클래스(믹스인 8종 상속) — 메서드 이름·시그니처·
│   │   │                   #   docstring 분해 전과 동일(SDK 입력 스키마 원료 — service._wrap의 functools.wraps 경로),
│   │   │                   #   기존 `from daedalus.mcp.tools import DaedalusTools` 무수정 동작(test_tools_facade.py가 고정)
│   │   ├── _base.py        #   _BaseTools — 공통 헬퍼(_project/_vm/_find_component/_find_state_vm/_scope/_reject_duplicate_name)
│   │   ├── query.py        #   조회(get_project/get_selection/get_component/validate_project/compile_preview) + undo 스택(undo/redo/get_history)
│   │   ├── session.py      #   세션(save_project/open_project/export_package/list_recent_projects)
│   │   ├── canvas.py       #   캔버스 구조(place/create_state/move/rename/delete/connect/disconnect/set_transition/참조 노드)
│   │   ├── ports.py        #   포트(set_transfer_on/add_agent_call/remove_agent_call)
│   │   ├── blackboard.py   #   블랙보드(create_blackboard_class/set_state_access)
│   │   ├── hooks.py        #   훅 라이브러리(create/update/delete_hook/set_component_hooks/list_hook_events/hook_frontmatter_preview)
│   │   ├── body.py         #   본문(set_component_body/get_body_outline/get_body_section/set_body_section — WP-BU/WP-BO 경로)
│   │   └── props.py        #   생성·속성(create_skill/create_agent/rename_component/description/when_to_use/field/project_properties/set_mcp_server_def)
│   └── service.py          # DaedalusMCPService — MCPServer 구성(_server_factory가 mcp 1.x/2.x 흡수) + uvicorn 데몬 스레드 수명주기
├── cli/              # 블랙보드 CLI(daedalus-bb) 자리 (WP-RF-2 신설, 빈 패키지) — C+A 설계: uv tool install로 앱과 함께
│                     #   설치되고, 컴파일 산출의 블랙보드 지시가 이 CLI를 호출. pyproject [project.scripts] 등록은 CLI 구현
│                     #   시점에(실존하지 않는 entry point는 설치를 깨뜨린다). core 경계 소속 — Qt·view·SDK 임포트 금지.
└── view/             # PySide6 기반 노드 에디터
    ├── recent.py           # 최근 프로젝트 목록(WP-RP) — ~/.daedalus/recent.json 읽기/쓰기 (Qt 무관 순수 stdlib).
    │                       #   load/save/push/remove/clear + MAX_RECENT. 기록 실패는 삼킨다(endpoint.py와 같은 정책).
    │                       #   실존 검사는 하지 않는다 — 메뉴를 열 때마다 stat을 때리면 네트워크 드라이브에서 UI가 멈춘다.
    ├── app.py              # 메인 윈도우 **골격** (WP-RF-3e 분해 후 ~960줄) — 탭·독·메뉴 배선 + 컴포넌트 편집 진입 + 그래프 로드/저장.
    │                       #   나머지는 협력 객체 4종에 위임(Mixin 아님 — 상속으로 섞으면 이름 충돌과 self의 정체가 흐려진다):
    │                       #   session_io.py / compile_actions.py / launch_actions.py / validation_actions.py (아래 각 항목).
    │                       #   **협력 객체가 실체이고 MainWindow에는 같은 이름의 한 줄 위임 메서드만 남는다** — 테스트와 MCP 도구가
    │                       #   window._save_to_path(...)처럼 윈도우의 내부 메서드를 직접 부르기 때문이다(tests/view/test_app_collaborators.py가 고정).
    │                       #   **상태(_project/_current_path/_mcp_service/_status_label …)의 단일 진실은 계속 윈도우**이고 협력 객체는
    │                       #   그것을 복제하지 않고 self._w.<attr>로 직접 읽고 쓴다(복제하면 두 곳이 어긋나는 순간 "저장했는데 다른
    │                       #   파일이 열린다"가 된다). 협력 객체는 위젯 배선보다 **먼저** 생성한다 — _setup_menus가 최근 목록을 채우며
    │                       #   곧바로 _session_io를 부른다. QFileDialog/QInputDialog는 app.py에 임포트를 남긴다(테스트가
    │                       #   `daedalus.view.app.QFileDialog...` 경로로 몽키패치 — 클래스 속성 패치라 협력 객체에도 그대로 걸린다).
    │                       # 메뉴: Ctrl+N "새 프로젝트"(기본 이름 "new-plugin", 빌드 타깃 선택 다이얼로그 — WP-TG, 취소 시 생성 취소),
    │                       #   F7 "프로젝트 검증", Ctrl+B "컴파일", 파일→"프로젝트 속성...", 도구→"MCP 서버 정보..."/"Claude Code 실행".
    │                       # 컴포넌트 이름 변경: _FrontmatterPanel.renamed → _on_component_renamed (중복 거부 + rename_component 호출 + 탭 타이틀 동기화)
    │                       # 컴포넌트 삭제: 레지스트리 우클릭 → _on_delete_component (확인 다이얼로그 + remove_component + 탭 닫기 + notify)
    │                       # 탭 구조(WP-BB/WP-HK): 인덱스 0=프로젝트 FSM 캔버스, 1=블랙보드 편집(BlackboardPanel), 2=훅 라이브러리(HookLibraryPanel)
    │                       #   — 상주·닫기 불가 고정 3개. _close_tab이 세 인덱스 모두 거부, load_project의 탭 정리 루프는 인덱스 3부터 닫는다.
    │                       #   set_project가 blackboard_panel.set_project(project) + tag_input.set_blackboard_candidate_provider(...)를 배선.
    │                       # 파일 독(WP-FR): _setup_docks가 FilePanel을 "플러그인 파일 (공용)" 독으로 배치하고
    │                       #   markdown_editor.set_files_root_provider(lambda: self._file_panel.files_root())를 등록.
    ├── session_io.py       # SessionIO(window) — 저장/열기/최근 목록/패키지(.ddpj) (WP-RF-3e에서 app.py로부터 추출).
    │                       # 프로젝트 패키지(WP-PK): 열기/저장이 **폴더** 단위. open_project_dialog(폴더 선택)/open_file_dialog(구버전 파일 직접)/
    │                       #   save_project_as(폴더 선택 — 형식이 새 형식으로 바뀌는 유일한 지점)/export_package_dialog/import_package_dialog.
    │                       #   save_to_path가 package.resolve_project_file로 폴더→정본 파일 해석 + 없는 폴더 생성 + carry_files_dir(다른 폴더로
    │                       #   저장 시 files/·skill-files/ 동반 복사). open_path는 package.find_project_file로 폴더→파일 해석.
    │                       #   window._current_path는 계속 **파일**을 가리킨다.
    │                       # sync_files_root(_current_path 기준 project_dir/files 재계산 + MCP 접속 정보 갱신)를 save_to_path/open_path/
    │                       #   new_project 끝에서 호출 — _current_path가 바뀌는 지점이 여기 하나로 모여 배선 지점도 하나다.
    │                       # 최근 프로젝트(WP-RP): File→"최근 프로젝트" 서브메뉴(window._recent_menu). remember_recent(open_path/save_to_path
    │                       #   성공 경로에서 호출)가 recent.push + rebuild_recent_menu. 항목 클릭 → open_recent(사라진 파일은 그 자리에서
    │                       #   목록에서 제거), "목록 지우기" → clear_recent. 라벨은 **모듈 수준 순수 함수** recent_label(&1 파일명 — 상위폴더,
    │                       #   & escape; MainWindow._recent_label이 staticmethod로 재노출 — 테스트가 클래스에서 직접 호출한다), 툴팁=전체 경로.
    │                       # 프로젝트 생성/속성: new_project(빈 프로젝트 + 빌드 타깃 프롬프트)/prompt_build_target/edit_project_properties
    │                       #   → ProjectPropertiesDialog(name/description/version + emit_progress_hook 체크박스, 이름 규약 미강제).
    │                       #   project_has_content("새 프로젝트" 확인과 MCP open_project의 저장 강제가 공유하는 단일 판정).
    ├── compile_actions.py  # CompileActions(window) — Ctrl+B 컴파일 (WP-RF-3e에서 추출).
    │                       #   compile_project_dialog: 출력 폴더 선택(LOCAL이면 "설치 대상 작업 폴더" — WP-MW) + _current_path 기준
    │                       #   files_dir/skill_files_dir를 compile_project에 전달(미저장이면 None). 에러면 window._show_validation_dock().
    │                       #   known_server_defs: 앱이 스스로 아는 daedalus 서버 정의(서버 미기동이면 기본 포트) — extra_server_defs로 주입.
    ├── launch_actions.py   # LaunchActions(window) — MCP 서버 수명주기 + Claude Code 실행 (WP-RF-3e에서 추출).
    │                       #   start_mcp_service(port)(__main__.main만 호출 — 테스트가 MainWindow를 수십 개 만들어 자동 기동은 포트 충돌)/
    │                       #   stop_mcp_service(MainWindow.closeEvent가 호출)/show_mcp_info(정보 전부 본문 즉시 표시 — Show Details 없음)/
    │                       #   launch_claude_code(프로젝트 저장 폴더에서 새 콘솔로 claude 실행. 미저장·서버 미기동이면 상태바 안내 후 중단)/
    │                       #   ensure_daedalus_mcp_json(wiring.wire_workspace로 daedalus 서버를 .mcp.json/settings.local.json에 배선).
    ├── validation_actions.py  # ValidationActions(window) — F7 검증 + 결과 항목 → 노드 포커스 (WP-RF-3e에서 추출).
    │                       #   run_validation(Validator.validate_project → ValidationPanel + dock 표시)/show_validation_dock(컴파일 경로와 공용)/
    │                       #   find_validation_dock/on_validation_item_activated → focus_in_project_canvas | focus_in_agent_tab.
    │                       #   탭 인덱스 상수(_FSM_TAB_INDEX)는 app.py 소유라 **메서드 안에서 지역 임포트**한다(최상단이면 순환 임포트).
    ├── canvas/             # GraphicsView/Scene, NodeItem, EdgeItem, RefNodeItem, RefEdgeItem, sync(VM→모델 동기화 — Qt 무관)
    │                       # 엣지 리루트(WP-ER): TransitionEdgeItem.update_path가 TransitionViewModel.waypoints(경유점)를 경유하는
    │                       #   구간별 베지어 곡선을 그린다. 선택 시 자식 WaypointHandleItem(작은 원)을 표시 — 더블클릭/컨텍스트 메뉴로
    │                       #   추가(nearest_segment_index), 드래그 이동, 우클릭/Delete로 제거. FsmScene/AgentFsmScene 공용.
    │                       # node_badges: badges_for(component)(뱃지 로직) + state_access_badges(state)(WP-BB — State.reads/writes → ✏쓰기/📖읽기
    │                       #   뱃지, 선언 있을 때만 렌더). NodeItem.paint가 badges_for(ref)+state_access_badges(model)를 합류해 렌더.
    │                       # 입력 포트(WP-IP/RF-1b): 노드당 1개 고정 — input_port_scene_pos()(인자 없음)가 그 한 점을 돌려주고
    │                       #   들어오는 모든 전이가 자연히 수렴한다(입력 포트 선언·도착 포트 지정은 개념째 삭제).
    │                       # draggable.py(WP-DM): DraggableItemMixin — 드래그 이동 가능 아이템 3종(StateNodeItem/ReferenceNodeItem/
    │                       #   WaypointHandleItem)의 공통 수명주기. 서브클래스는 mousePressEvent에서 begin_drag(), mouseReleaseEvent에서
    │                       #   end_drag()를 호출하고 vm_position()/make_move_command()를 구현한다(ABC 아님 — Qt 메타클래스와 충돌.
    │                       #   믹스인을 QGraphicsItem 앞에 둔다). 상세는 "캔버스 드래그 이동" 항목 참조.
    ├── commands/           # Undo/Redo 커맨드 (state, transition — Add/Move/Remove/ClearWaypointsCmd(WP-ER) 포함, exit_point,
    │                       #   component — Create/RenameComponentCmd(WP-CE 1차). 삭제는 remove_component의 정리 범위가 넓어 미커맨드화,
    │                       #   attr — SetAttrCmd/AppendToListCmd/RemoveFromListCmd(WP-CE 범용 폼 편집. 편집마다 클래스를 만들지 않고
    │                       #     "속성 하나 바꾸기"+"리스트 넣고 빼기" 둘로 환원한다. SetAttrCmd는 최초 execute에서만 old를 잡는다 —
    │                       #     redo가 old를 덮으면 undo가 깨진다. 값은 복사하지 않으므로 호출자가 새 객체를 넘겨야 한다))
    ├── editors/            # 속성 편집기 (skill, agent, hook, body, body_documents, component, variable_loader, catalogue_loader, field_widgets, project_properties, blackboard_editor)
    │                       # catalogue_loader: 도구/MCP 카탈로그 로더(WP-TM) — ~/.daedalus/catalogue/*.json(글로벌) + <프로젝트>/.daedalus/catalogue/*.json(프로젝트, 이름 충돌 시 우선)
    │                       #   병합. 파일 1개=항목 1개(CatalogueEntry: name=파일명 stem, description, tools="tool" 키, mcp="mcp" 키). expanded_mcp()가 mcp 항목을
    │                       #   mcp__<entry.name>__<도구>로 확장(이미 mcp__ 접두면 그대로). candidate_strings(entries, project)가 CC_BUILTIN_TOOLS(정렬)+카탈로그 tool/expanded_mcp+
    │                       #   프로젝트 에이전트 Agent(이름)을 합성(중복 제거)해 TagInput 자동완성 후보를 만든다. 파싱 실패/스키마 불일치 파일은 stderr 경고 후 스킵.
    │                       # body: SectionContentPanel = MarkdownToolbar + SearchBar(찾기/바꾸기 바, WP-MD3, 기본 숨김) + QStackedWidget(0=MarkdownEditor 편집,
    │                       #   1=QTextBrowser 프리뷰 — setMarkdown 1회 렌더) + TocPanel(TOC 사이드바, WP-MD3, 기본 숨김, 폭 180px) 가로 배치.
    │                       #   MarkdownEditor.search_requested → search_bar.open(prefill), MarkdownToolbar.toc_toggled → toc_panel 표시/숨김.
    │                       #   show_body(component)가 편집 모드로 리셋 + 찾기 바 닫힘 + TOC 즉시 재파싱(refresh() — blockSignals로 억제된
    │                       #   textChanged를 TOC가 못 받으므로 명시 호출), 프리뷰 중 편집 버튼·변수 삽입·TOC 토글 잠금 + 찾기 바 닫힘.
    │                       # WP-SB: 수동 섹션 트리 편집(SectionTree/BreadcrumbNav, find_path/section_depth/MAX_DEPTH)은 마크다운 에디터로 대체되어 제거 —
    │                       #   component_editor.ComponentEditor는 좌(FrontmatterPanel) | 중(SectionContentPanel, component.body 단일 편집) | 우(옵션) 2~3분할로 단순화
    │                       # blackboard_editor.py(WP-BB): BlackboardPanel(QWidget) — 프로젝트 최상위 블랙보드(class_definitions) 편집 상주 탭. 좌: 클래스
    │                       #   목록(＋/삭제/더블클릭 이름변경), 우: description(QLineEdit) + 필드 테이블(name/FieldType/CollectionType/required/default,
    │                       #   ＋필드/필드 삭제). 편집은 project.blackboard.class_definitions를 직접 갱신 + notify(structure 채널 — undo 커맨드화 범위
    │                       #   밖, hook_editor 폼 정책과 동일). blackboard_candidate_strings(project)가 "클래스"+"클래스.필드" 후보 문자열을 만든다.
    ├── panels/             # TreePanel, PropertyPanel, RegistryPanel, HistoryPanel, ValidationPanel (F7 검증 결과), FilePanel(WP-FR)
    │                       # RegistryPanel: component_delete_requested 시그널 + _RegistrySection 우클릭 "삭제" 컨텍스트 메뉴.
    │                       #   종류별 섹션은 QTabWidget 탭(WP-SF 배치 개편 — 이모지 라벨+툴팁)
    │                       # FilePanel(WP-FR/WP-SF): _FileTreeBase(트리+안내+생성+새로고침+"탐색기" 버튼) 기반 전역 files/ 독("플러그인 파일 (공용)",
    │                       #   레지스트리 아래 세로 스택). set_project_dir(path|None) — 저장/열기/새 프로젝트 시 app이 호출. files_root()/skill_files_root()가
    │                       #   실존 시에만 경로 문자열 반환(드롭 provider 단일 진실). SkillFilesPanel(WP-SF): 스킬 에디터 우측 — skill-files/<스킬>/ 트리,
    │                       #   set_project_dir_provider/get_project_dir 모듈 provider로 프로젝트 폴더 조회(에디터마다 생겨 직접 배선 불가)
    │                       # PropertyPanel.show_state(WP-BB): reads/writes TagInput 2개 — get_blackboard_candidates()로 자동완성 후보(호출 시점
    │                       #   스냅샷, get_tool_candidates와 동일 정책), tags_changed → state.reads/writes 직접 기록(커맨드화 범위 밖) + notify. 프로젝트
    │                       #   캔버스 placement와 에이전트 FSM 상태(agent_editor 그래프 탭에 임베드된 PropertyPanel) 양쪽에서 동일하게 편집 가능.
    ├── viewmodel/          # ProjectViewModel(notify structure/content 채널), StateViewModel (모델↔뷰 중간 계층)
    └── widgets/            # ComboWidgets, TagInput, PresetPicker, markdown/(마크다운 에디터 패키지 — WP-RF-3c로 구 단일 모듈 markdown_editor.py를 분해.
                            #   markdown_editor.py 모듈 경로는 **재-export 파사드**로 유지되어 기존 임포트가 무수정 동작한다. 구획:
                            #     syntax.py      — MARKDOWN_PALETTE·폰트 상수·정규식 전부(_FENCE_*_RE/_HEADING_*_RE/_TASK_RE/… )·_make_format·_detect_line_marker.
                            #                      **모듈 간 공유 상수의 단일 진실**(복제 금지) — model/outline.py의 펜스 정규식이 이 파일을 미러한다.
                            #     highlighter.py — MarkdownHighlighter(블록 상태 _STATE_NONE/_STATE_CODE_FENCE로 코드 펜스 추적)
                            #     providers.py   — files/·skill-files/ 루트 provider 4함수 + _file_ref_token/_skill_file_ref_token(드롭 참조 토큰 계산).
                            #                      provider 전역은 여기가 단일 진실 — 파사드는 함수만 재-export한다(가변 전역 복사는 스테일).
                            #     slash.py       — SlashItem/SLASH_CATALOG/_SlashMenu (`/` 오버레이)
                            #     editor.py      — MarkdownEditor + 단축키 판정표(_HEADING_DIGIT_*/_MARKER_SHORTCUT_*)·_heading_digit_from_event/_line_marker_from_event
                            #     toolbar.py     — MarkdownToolbar / search.py — SearchBar / toc.py — TocEntry+TocPanel
                            #   MarkdownHighlighter+MarkdownEditor — 하이브리드 마크다운 하이라이팅·편집, SectionContentPanel 본문에 통합
                            #   + `/` 슬래시 메뉴(_SlashMenu — 에디터 viewport 자식 오버레이, Qt.Popup 아님) + MarkdownToolbar(서식 버튼 행 + toc_toggled/preview_toggled 시그널))
                            #   찾기/바꾸기 + TOC(WP-MD3, 마크다운 에디터 마일스톤 마감): SearchBar(QLineEdit 검색·바꾸기 + 이전/다음 + Aa 대소문자
                            #   토글 + 일치 수 라벨 — 평문 부분 문자열 매칭, QTextDocument.find 미사용. search_next/prev는 랩어라운드, replace_current는
                            #   치환 후 다음 일치로 이동, replace_all은 beginEditBlock/endEditBlock로 1 undo 단위. MarkdownEditor.search_requested
                            #   (Ctrl+F, 선택 텍스트 프리필)로 열리고 Esc(eventFilter)로 닫히며 닫을 때 ExtraSelections를 지운다) +
                            #   TocPanel(QTreeWidget — ATX 헤딩을 레벨별로 계층화, 코드 펜스 내부는 MarkdownHighlighter._STATE_CODE_FENCE
                            #   블록 상태로 판별해 제외. textChanged마다 300ms 디바운스(QTimer) 후 재파싱, 구조 불변 시 트리 재구성 생략.
                            #   클릭 시 setTextCursor+centerCursor로 점프. refresh()로 디바운스 우회 즉시 재파싱 — 문서 전환용)
                            #   TagInput(WP-TM): set_candidates(list[str])로 QCompleter(부분 일치·대소문자 무시) 부착. 모듈 수준
                            #   set_tool_candidate_provider/get_tool_candidates(HookPresetPicker의 set_hook_name_provider 패턴)로 동적 후보 주입 —
                            #   app.py의 set_project가 프로젝트 로드 시 catalogue_loader.candidate_strings(...)를 등록. skill_editor._FrontmatterPanel이
                            #   ALLOWED_TOOLS/TOOLS/DISALLOWED_TOOLS 필드 생성 시 후보를 부착(_wire_tool_candidates) — PATHS/SKILLS/MCP_SERVERS는 제외
                            #   set_blackboard_candidate_provider/get_blackboard_candidates(WP-BB, 동일 provider 패턴)는 State.reads/writes TagInput
                            #   (PropertyPanel)의 "클래스"/"클래스.필드" 후보 — app.py의 set_project가 blackboard_candidate_strings(project)를 등록.
                            #   파일 드롭 치환(WP-FR): markdown/providers.py의 set_files_root_provider/get_files_root(동일 provider 패턴) — MarkdownEditor.
                            #   dragEnterEvent/dragMoveEvent/dropEvent가 mime의 file URL 중 현재 files/ 루트 하위인 것만 _file_ref_token으로
                            #   변환해 드롭 지점에 삽입(복수 파일=줄바꿈 구분). files 밖·비파일 mime은 super()로 흘려 기존 QPlainTextEdit
                            #   기본 드롭(텍스트 드래그 등)을 보존한다. app.py의 _setup_docks가 등록.
                            #   코드 인용 + 단축키 확장(WP-MK): MarkdownEditor.toggle_inline_code()(`toggle_wrap("`", "`")` 재사용)/
                            #   toggle_code_block()(줄 단위 — 선택은 줄 경계로 확장, 이미 펜스면 벗김, 선택 없고 빈 줄이면 빈 펜스
                            #   3줄+가운데 커서, 그 외엔 현재 줄을 펜스로 감쌈. 언어 태그 없음(v1). 1 undo 단위) 공개 API 추가.
                            #   `_dispatch_key` 단축키: Ctrl+`(인라인 코드) / Ctrl+Shift+C(코드 블록) / Ctrl+1~6(헤딩 레벨) /
                            #   Ctrl+0(본문 복귀) / Ctrl+Shift+8(불릿) / Ctrl+Shift+7(번호) / Ctrl+Shift+9(체크리스트) /
                            #   Ctrl+Shift+.(인용). 숫자·기호 조합은 event.key()가 플랫폼별로 다르게 올 수 있어 모듈 수준 순수 함수
                            #   `_heading_digit_from_event`/`_line_marker_from_event`가 event.key()/event.text() 양쪽을 판정(폴백).
                            #   MarkdownToolbar에 `<>`(인라인 코드)/`{}`(코드 블록) 버튼 추가(B/I/S 뒤, 구분선), 기존 버튼 프리뷰 비활성화
                            #   정책(_edit_buttons)에 자동 편입. SLASH_CATALOG에 "인라인 코드" 항목(` `` `, cursor_back=1) 추가.
```

## 핵심 개념

### 스킬과 에이전트

| 종류 | 본질 | FSM 관계 |
|------|------|---------|
| ProceduralSkill | 작업 지침 | 자체 FSM을 가진 독립 워크플로우 |
| DeclarativeSkill | 배경 지식 | FSM 없음 |
| TransferSkill | 전이 시 실행되는 보조 지침 | 자체 FSM 보유 |
| ReferenceSkill | 참조 문서 | FSM 없음, 참조 노드로 복수 배치 |
| AgentDefinition | 별도 컨텍스트의 작업자 | **내부 FSM 퇴역(WP-AF)** — 절차는 본문, 결과 분기는 transfer_on |

### 에이전트 — 본문 + 출력 포트 (WP-AF, 내부 FSM 퇴역)

- **왜 퇴역했나:** Daedalus FSM은 런타임 엔진이 없다 — 내부 FSM은 컴파일되면 에이전트 .md 안의
  번호 목록 텍스트가 될 뿐이고, 같은 지시는 본문 산문이 동일한 효력을 낸다. 형식화 비용(그래프
  탭·별도 CommandStack·로컬 스킬 기계장치)에 걸맞은 대가가 없었다(사용자 확정. 도그푸딩에서
  손실·버그 대부분이 이 표면에서 났고, 실사용 세션은 에이전트를 내부 FSM 없이 본문만으로 만들었다).
- **살아남은 조각 = 출력 포트.** 프로젝트 그래프가 에이전트의 결과로 분기한다(과거 ExitPoint 이름이
  전이 trigger). `AgentDefinition.transfer_on: list[EventDef]`로 이관 — 스킬과 동일 필드·동일 편집
  패널(_TransferOnPanel)·동일 캔버스 포트 렌더. `output_events`/`output_event_defs`는 transfer_on을
  **단일 진실**로 읽는다 (legacy ExitPoint 폴백은 RF-1b에서 삭제 — v1 파일은 로드 시 마이그레이션).
- **마이그레이션:** v1 파일(transfer_on 키 부재)은 `serialize._migrate_v1`이 내부 FSM ExitPoint의
  이름·색을 승계한다(단방향, 경고 없음). fsm 필드 자체는 WorkflowComponent 계약상 남는다 — 신규
  에이전트는 EntryPoint 하나짜리 빈 기계(`app._make_agent_fsm`) + 기본 출력 포트 `done`.
- **로컬 스킬 퇴역 완결 (WP-RF-1c):** `AgentDefinition.skills` 필드째 삭제. 에이전트에게 줄
  지식은 전역 스킬로 — 컴파일이 skills 프론트매터에 자동 합류시킨다(WP-AS: 전역 DeclarativeSkill
  전부 + 그 에이전트 placement에 링크된 ReferenceSkill + config.skills 수동 선언 순, 중복 제거.
  `emit._agent_skills_list`). v1 파일의 로컬 스킬은 로드 시 **전역 스킬로 승격**된다
  (`_promote_local_skills` — `_migrate_v1` 1-b 단계가 호출. 이름 충돌 시 `<agent>--<name>`으로
  개명하고 그마저 충돌하면 `-2` 접미로 유일화, 개명 시 소유 에이전트 config.skills 참조도 치환,
  승격마다 경고 1건, id 보존이라 에이전트 FSM 전이의 transfer skill_ref도 그대로 해소. 블랙보드
  parent 재배선·본문 마이그레이션은 전역 스킬과 완전히 같은 경로). **RF-1b 시점 코드가 저장한
  format 2 파일에도 인라인 로컬 스킬이 남아 있을 수 있어**, `deserialize_project`는 format 2에서도
  에이전트 dict에 `skills` 키가 있으면 같은 승격을 태운다(경고 없는 드롭 방지).
- **호출 계약 = 그래프 유도 (WP-CT):** 수동 계약 카드(caller_contracts 편집·자동 생성)는 퇴역 —
  호출 정보를 양쪽(호출자 포트 + 에이전트 카드)에 적게 하던 중복이었다. **호출자가 무엇을 넘기는지는
  호출자의 call_agents 포트 description에 적는다.** 에이전트 .md의 "## 호출 계약"은
  `emit._call_contract_section(agent, project)`이 프로젝트 그래프의 incoming 호출 전이에서 유도한다
  (호출자·포트·description·가드, 호출자 이름순). caller_contracts 필드는 RF-1b에서 삭제 —
  v1 파일의 카드는 로드 시 조용히 드롭된다(`_migrate_v1`).
- **에이전트 편집기:** AgentEditor = ComponentEditor + 출력 포트 패널 — 스킬 편집기와
  같은 레벨(그래프/컨텐츠 탭 구조 제거, 별도 그래프 VM 없음 — undo는 프로젝트 스택).
- **MCP:** 도구의 `agent` 스코프 파라미터는 WP-RF-1c에서 시그니처째 제거됐다(스키마 노출 기준 —
  캔버스 편집의 대상은 프로젝트 그래프 하나뿐이다). `set_transfer_on(에이전트 이름)`으로 출력
  포트 편집. `create_agent`는 기본 포트 done으로 시작.
- **컴파일:** "## 내부 워크플로"는 legacy FSM에 실질 상태(SimpleState 등)가 있을 때만 배출.
  "## 출구"는 transfer_on 기반(`_agent_outputs_section` — 완료 보고 첫 줄에 출구 명시 지시 + description 병기).

### CompositeState (순수 FSM 개념)

- `sub_machine: StateMachine`을 포함하는 UML composite state — fsm/ 레이어의 순수 개념으로 존치
  (Region과 함께). **에이전트 개념과의 대응은 WP-AF로 끊어졌다** — 에이전트는 더 이상 내부 FSM으로
  설계하지 않는다.

### Region = 병렬 실행 트랙

- `ParallelState` 내 독립 실행 단위
- `sub_machine: StateMachine`을 포함 — 각 Region은 자신만의 FSM을 가짐
- 향후 리전별 우선순위, 취소 정책, 동기화 포인트 등 확장 가능
- **조인 전략:** `ParallelState.join: JoinStrategy = ALL` + `join_count: int | None`. ALL=전 Region, ANY=하나, N_OF=`join_count`개 완료 시 join. `JoinStrategy`는 순수 FSM 개념이라 `model/fsm/join.py`가 정본이며 필요한 곳이 직수입한다(RF-1b에서 policy.py re-export 삭제 — `ExecutionPolicy`도 동일 enum 사용).

### Blackboard = 컨텍스트 간 공유 장치

- **역할:** 서로 다른 컨텍스트 간에 외부 데이터를 통해 맥락을 공유하는 장치
- 동일 컨텍스트 내에서는 불필요 — 이미 같은 맥락을 공유
- 스코핑: 최상위 `Blackboard(parent=None)`, 하위 `Blackboard(parent=부모.blackboard)`
- **최상위 블랙보드:** `PluginProject.blackboard`(default_factory) — schemas.json의 소스(DynamicClass 단일 진실). 에이전트/스킬 FSM의 `blackboard.parent`는 **생성 경로의 책임**으로 이 객체에 배선한다 (app.py `_register_component`, **그리고 `deserialize_project` — 역직렬화도 생성 경로**: 스킬/에이전트 FSM→프로젝트 블랙보드로 재연결되어 parent 스코핑이 저장/로드를 견딘다. v1 파일의 에이전트 로컬 스킬은 `_migrate_v1`이 전역 승격하므로 같은 경로를 탄다 — WP-RF-1c). 마이그레이션 없음 — 메모리 내 기존 객체는 강제하지 않는다. 직렬화는 parent를 ID로 평탄화하지 않고 **소유 구조로 재연결**(`_deser_machine`의 `parent_bb` 전달).
- **DynamicClass → JSON Schema 매핑:** `blackboard.py`의 `FIELD_TYPE_TO_JSON_SCHEMA` 정본(STRING→string, INT→integer, FLOAT→number, BOOL→boolean, LIST→array, JSON→object, ANY→{}). CollectionType은 array로 래핑(LIST→items, SET→items+uniqueItems). 컴파일러 `compile_schemas_json(project)`가 프로젝트 블랙보드 class_definitions를 `<out>/schemas/schemas.json`으로(정의 없으면 None).
- **블랙보드 편집 UI (WP-BB):** 모달이 아니라 `view/editors/blackboard_editor.BlackboardPanel`이 MainWindow의 상주
  최상위 탭(인덱스 1, Project FSM(0)과 동급, 항상 존재·닫기 불가)으로 프로젝트 최상위 블랙보드
  `class_definitions`를 편집한다 — 좌: 클래스 목록(추가/삭제/이름변경), 우: description + 필드
  테이블. 편집은 모델 직접 기록 + notify(structure 채널)로, 훅 라이브러리 다이얼로그와 동일하게
  undo 커맨드화 범위 밖이다.

### 상태 접근 선언 (reads/writes) — WP-BB

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
  reads 있으면 📖("블랙보드 읽기: …") 뱃지(둘 다 선언되면 둘 다 렌더). `NodeItem.paint`가 기존
  컴포넌트 뱃지(`badges_for`)에 합류시킨다 — 선언이 있을 때만 노출되어 노이즈가 없다.
- **컴파일러 구체화:** FSM 절차 단락(`_describe_fsm`/`_describe_agent_fsm`)의 상태 항목에
  `(읽기: \`A.x\`, \`B\` / 쓰기: \`A.y\`)` 접미사가 이름순 정렬로 합류한다(선언 없으면 문구
  생략). 블랙보드 단락(`_blackboard_section(project, component)`)은 component(스킬/에이전트)
  자체 FSM(재귀) + 프로젝트 그래프 placement의 reads/writes 합집합(`_component_access_union`)을
  구해, 비어있지 않으면 "이 스킬/에이전트가 읽는 것/쓰는 것"을 명시하고 파일 목록을 관련
  클래스만으로 좁힌다. 합집합이 비면(또는 component 미지정) 기존 전 클래스 일반 안내 그대로
  — 하위 호환, 접근 선언 0개 프로젝트의 산출 문자열은 불변이다.
- **검증:** `dangling_blackboard_ref`(reads/writes 참조가 블랙보드에 실존하는지, 재귀 +
  프로젝트 그래프 포함)/`orphan_blackboard_field`(어떤 상태도 참조하지 않는 필드 경고 — 클래스
  전체 참조는 그 필드 전부 커버로 간주, 프로젝트 전체에 접근 선언이 하나도 없으면 스킵) 2종.
  둘 다 프로젝트 수준 경고 규칙(아래 Validator 규칙 표 참조).

### FSM + Blackboard 하이브리드

- **로컬 데이터:** Transition.data_map으로 상태 간 명시적 전달 (`{src_output: tgt_input}`)
- **공유 데이터:** Blackboard.variables (Variable.scope = BLACKBOARD)
- **동적 상태 파일:** Blackboard.class_definitions (DynamicClass) — 설계 시 정의, 런타임에 work 폴더 state/에 생성

### 본문(body) / Section / EventDef

- **본문의 단일 진실은 `body: str`(단일 마크다운 문자열)** — `ProceduralSkill`/`DeclarativeSkill`/`TransferSkill`/`ReferenceSkill`/`AgentDefinition` 전부 동일 필드(WP-SB, 기본값 `""`). 마크다운 에디터(WP-MD1/MD2/MD3, **완료** — 코어 위젯+오버레이 UX+찾기/바꾸기+TOC)가 헤딩·리스트·슬래시 메뉴를 네이티브로 다루면서 수동 섹션 트리 편집의 존재 의의가 사라져 단일 텍스트로 통일했다.
- `Section`(`model/fsm/section.py`)은 자유 콘텐츠 계층(H1–H6, `children: list[Section]` 재귀 트리)으로, 이제 **v1 sections 트리 마이그레이션의 입력**으로만 쓰인다(RF-1b — 계약 카드 용도(caller_contracts)는 필드째 삭제, `commands/section_commands.py`도 함께 제거). 모듈이 남는 이유는 아래 `render_markdown`과 `EventDef`가 여기 살기 때문이다.
- `render_markdown(sections, depth=1) -> str`(section.py): v1(sections 트리) 파일을 로드할 때 `body`로 평탄화하는 단방향 마이그레이션 헬퍼. `serialize._migrate_v1`이 `body` 키 부재 + `sections` 키 존재 시에만 호출한다(경고 없음 — 정상 마이그레이션 경로).
- `EventDef`: TransferOn 스킬의 출력 이벤트 정의. 노드 출력 포트에 대응 (`name`, `color`, `description`)

### 본문 부분 접근 (WP-BO) — 파생 인덱스, 저장 불변

- **저장의 단일 진실은 `body: str` 그대로다**(사용자 확정, A안). 저장을 헤딩 트리로 바꾸면 마크다운↔트리
  무손실 왕복 파서가 필요해지는데("저장했더니 본문이 미묘하게 달라짐" 류 버그가 최악), 구조는 항상
  **파생으로만** 만든다. 필요 시 확장 경로: B안(인텍스트 헤딩 속성 `{#id key=val}` — 저장은 여전히 텍스트),
  C안(섹션 일급 객체화 — 섹션 공유 요구가 실재할 때만).
- `model/outline.py`: `parse_outline(body)`(ATX 헤딩, 코드 펜스 제외 — 펜스 정규식은 view
  `widgets/markdown/syntax.py`의 `_FENCE_OPEN/CLOSE_RE` **미러**, 어긋나면 TOC와 섹션 집기가
  달라진다. 하이라이터·에디터도 같은 syntax.py 상수를 임포트하므로 정본은 그 한 곳이다),
  `find_section`(제목/`"## 제목"` 레벨 지정/`"부모 > 자식"` 경로 — 0개·복수 매칭은 ValueError, 조용히
  하나를 고르지 않는다), `section_text`/`char_span`/`replacement_text`/`replace_section`. 텍스트 연산은
  전부 `split("\n")` 기반이라 비교체 구간이 바이트 그대로 보존된다. `replace_section`과 QTextCursor
  경로(char_span+replacement_text)는 `replacement_text`를 공유해 결과가 같다(테스트 고정).
- **MCP 도구 3종(부분 접근):** `get_body_outline`(구조만 — 본문 전송 없음)/`get_body_section`/
  `set_body_section`(섹션 교체 — `set_component_body`와 같은 문서 경로(WP-BU)라 undo 가능, text에
  자기 헤딩 줄을 포함해야 섹션으로 남는다). 읽기는 `BodyDocumentRegistry.peek`(열린 문서가 있으면
  그쪽이 진실이되, 읽기가 문서를 **만들지는 않는다**)를 쓴다.
- **후속 예정:** 컴파일 분할(점진 공개 — 큰 본문의 섹션을 스킬 디렉토리 보조 파일로 산출.
  `${CLAUDE_SKILL_DIR}`가 공식 변수이고 스킬 디렉토리 상대 참조가 CC 공식 패턴임을 확인, 2026-08.
  에이전트는 단일 .md라 전용 폴더 없음 — 대상 아님), 스킬별 파일 탭(files-per-skill).

### 입력 포트 퇴역 (WP-IP) — 인터페이스 선언은 값을 만드는 쪽에만

- **원칙(사용자 확정):** 함수(도착 노드)가 자기 입력 경로를 알 필요가 없다 — 호출하는 쪽이 맞춘다.
  (출처, 트리거)가 이미 경로를 특정하므로 `entry_paths`(입력 포트 선언)와 `Transition.target_port`는
  **퇴역**했다. 계약 카드 퇴역(WP-CT)과 같은 원칙이다: 갈래의 의미는 출발 스킬이 자기 `transfer_on`
  description에 적고, 경로별 대응은 도착 스킬 본문에 쓴다. 실증: unreal-profiler 실사용 세션이 쓴
  target_port 6개 전부가 (출처, 트리거) 쌍으로 특정되는 정보의 이름표 중복이었다.
- **호출 시 정보가 담긴다(컴파일):** ① 출발 스킬 "## 다음 단계" 항목에 그 갈래의 transfer_on
  description 병기("— <desc>"). ② `_PROGRESS_UPDATE_NOTE`가 `note`에 **어느 갈래(출력 이벤트
  이름)**를 기록하도록 지시 — 도착 스킬은 (`prev`, `note`의 갈래)로 진입 경로를 판별한다.
  ③ 도착 스킬 "## 진입 맥락"은 그래프에서만 유도(포트 그룹 헤딩 없음, 출처 이름순 항목 + 출처의
  transfer_on description 병기).
- **잔재 처리:** 모델 필드(`entry_paths`/`target_port`)는 RF-1b에서 **삭제**됐다 — v1 파일의 해당
  키는 로드 시 조용히 드롭된다(`_migrate_v1`, 퇴역 개념이라 경고 불필요). 렌더는 입력 포트 항상
  1개(`input_port_scene_pos()` 인자 없음), 검증의 `dangling_target_port` 규칙도 삭제. 편집 UI
  ("⇤ 입력 경로" 패널) 제거. MCP는 `set_entry_paths` 도구 자체를 제거했고 `set_transition`/
  `connect_states`에서 target_port 파라미터도 사라졌다(조회 출력에서도 제외).

### PluginProject.graph = 워크플로 백킹 머신

- **역할:** 프로젝트 캔버스(탭 0)의 노드/전이를 담는 정식 `StateMachine`. 각 캔버스 노드는 "정식 FSM 상태"이며 백킹 머신에 들어가 **직렬화·컴파일·검증의 단일 진실**이 된다 (캔버스 VM은 그 투영). 이전에는 fsm=None 경로로 도메인 모델에 들어가지 않아 저장/컴파일에서 누락됐다.
- **기본값:** `default_factory=_make_project_graph` — `EntryPoint(name="start")`를 `initial_state`로 갖는 빈 머신(states 포함). `StateMachine.initial_state`는 required 유지(Optional 완화 없음), 직렬화 포맷도 불변.
- **EntryPoint 격하 (WP-EP):** CC 플러그인에는 단일 진입점이 없다 — user_invocable 스킬은 전부 `/skill`로 독립 시작 가능하고 모델 자동 인보크도 있어, FSM 관념의 "시작점"이 성립하지 않는다. 따라서 **프로젝트 캔버스(탭 0)는 EntryPoint와 그에 닿는 전이를 그리지 않는다** — `app._load_project_graph`가 `graph.states`에서 EntryPoint 인스턴스를 스킵하고(VM 미생성), EntryPoint에 닿는 전이도 VM이 없어 자연히 렌더되지 않는다(구버전 파일의 시작 전이도 경고 없이 조용히 숨는다). 모델은 불변 — `project.graph.initial_state`는 여전히 EntryPoint이고 구버전 파일의 시작 전이도 저장 왕복 시 보존된다. `FsmScene`의 EntryPoint 삭제-방어 코드(`_delete_state`/컨텍스트 메뉴/keyPress)는 `AgentFsmScene`과 공용이라 그대로 두지만, 프로젝트 캔버스에서는 VM이 없어 자연히 죽은 경로가 된다. **에이전트 FSM의 EntryPoint/ExitPoint(agent_editor, AgentFsmScene)는 이 격하와 무관** — 에이전트는 별도 컨텍스트의 실재하는 단일 진입점이다.
- **placement:** 배치된 스킬/에이전트는 `SimpleState(skill_ref=...)`로 그래프에 들어간다 (에이전트도 SimpleState로, CompositeState 승격 없음). `FsmScene.set_project`가 `_target_fsm = project.graph`로 배선해 Create/Delete/Transition 커맨드가 그래프에 동기화된다 (undo/redo 일관). `AgentFsmScene`은 `_target_fsm`을 에이전트 FSM으로 별도 설정.
- **graph_layout:** `dict[str, list[float]]` — 키는 **state.id** (AgentDefinition.graph_layout과 동일 규약, 이름 변경 안전). 저장 직전 `app._save_graph_layout`이 VM 좌표를 기록, 로드 시 `app._load_project_graph`가 graph+graph_layout으로 캔버스 VM을 재구성(`agent_editor._load_agent_fsm` 미러링). EntryPoint는 캔버스 VM이 없으므로 `graph_layout`에도 그 키가 기록되지 않는다(WP-EP).
- **블랙보드 배선:** `project.graph.blackboard.parent = project.blackboard` — `PluginProject.__post_init__`(생성 경로)과 `deserialize_project`(역직렬화 생성 경로) 양쪽에서 보장.

### BuildTarget = 빌드 타깃 (마켓플레이스 / 로컬 플러그인) (WP-TG)

- **배경:** MCP를 쓰는 에이전트는 CC 정책상 마켓플레이스 플러그인으로 배포할 수 없다(`mcpServers` 등 프론트매터 미지원) — 사람들이 파일 복사로 우회하는 문제를 프로젝트 수준 빌드 타깃으로 해결한다(로컬 에이전트 타입안은 폐기, 이 설계가 상위 개념).
- **모델:** `model/plugin/enums.py`의 `BuildTarget(Enum)`: `MARKETPLACE`(기본) / `LOCAL`. `PluginProject.build_target: BuildTarget = BuildTarget.MARKETPLACE`.
- **직렬화:** `.value` 왕복. 구버전 파일(키 부재)·미지 값은 `MARKETPLACE`로 조용히 폴백(경고 없음) — 하위 호환 게이트.
- **생성 흐름:** `app._new_project`(Ctrl+N)가 이름 결정 전에 `QInputDialog.getItem`으로 "마켓플레이스 플러그인"/"로컬 플러그인"을 고르게 한다(`_prompt_build_target`). 취소하면 새 프로젝트 생성 자체가 취소된다(기존 프로젝트 유지). 표시 문구·enum 매핑은 `view/editors/project_properties.py`의 `BUILD_TARGET_LABELS`가 단일 진실(app.py가 재사용). `ProjectPropertiesDialog`에도 콤보로 노출해 생성 후 변경 가능.
- **컴파일:** MARKETPLACE는 현행과 바이트 동일(하위 호환 게이트) — `plugin.json` 생성. LOCAL은 **컴파일이 곧 설치**(WP-MW) — out_dir가 대상 작업 폴더이고 산출이 `.claude/` 밑으로 바로 나간다. 상세는 컴파일 정책 15번 항목 참조.
- **검증:** `mcp_agent_in_marketplace_build`/`plugin_root_in_local_build` — Validator 프로젝트 수준 규칙 표 참조.

### 연결선 리루트 — 엣지 웨이포인트 (WP-ER)

- **역할:** 루프 전이 등 노드를 가로질러 그려지는 엣지를 사용자가 손으로 정리할 수 있도록 경유점(waypoint)을 추가·드래그·제거하는 기능. 자동 라우팅(장애물 회피 등)은 비목표 — v1은 수동 경유점만.
- **저장 모델:** `PluginProject.edge_layout`/`AgentDefinition.edge_layout: dict[str, list[list[float]]]` — 키는 **Transition.id**(graph_layout의 state.id 규약과 동일), 값은 `[x, y]` 목록(소스→타깃 순서). 웨이포인트는 뷰 관심사이므로 fsm 모델(Transition)에는 넣지 않는다. `remove_component`가 배치 삭제 시 연결 전이와 함께 `edge_layout`의 해당 키도 정리한다(graph_layout 정리와 동일 위치).
- **뷰 모델:** `TransitionViewModel.waypoints: list[tuple[float, float]]`(기본 빈 리스트, 뷰 전용). 저장 직전 `app._save_graph_layout`/`agent_editor._save_graph_layout`이 `transition_vms`를 순회해 `project.edge_layout`/`agent.edge_layout`에 기록하고, 로드 시 `app._load_project_graph`/`agent_editor._load_agent_fsm`이 `edge_layout.get(trans.id, [])`로 `TransitionViewModel(waypoints=...)`를 복원한다(graph_layout과 완전히 동일한 저장/복원 시점 미러링).
- **렌더 (`edge_item.py`):** `TransitionEdgeItem.update_path`가 `_route_points()`(소스 포트 → waypoints → 타깃 포트)를 구해 각 구간을 기존과 동일한 베지어 곡선(`_add_curve_segment`)으로 잇는다. 각 구간의 끝점이 정확히 경유점이므로 경로가 그 점을 통과함이 보장된다. 경유점이 없으면 구간이 하나뿐이라 기존 렌더와 완전히 동일(하위 호환 — 회귀 판정은 `test_edge_paint.py`/`test_input_ports.py`/`test_scene_rebuild.py` 무수정 통과). 화살촉은 기존 로직 그대로 `_ARROW_SPACING` 간격으로 **경로 전체에 반복 배치**되고(마지막 구간 전용이 아님 — master와 동일), 라벨도 기존 위치 로직 그대로다.
- **상호작용:** 엣지 더블클릭 또는 컨텍스트 메뉴 "경유점 추가" → `edge.nearest_segment_index(scene_pos)`(구간별 곡선을 샘플링해 최근접 구간 판정) 위치에 삽입. 자식 `WaypointHandleItem`(작은 원, 선택 엣지 색 `#88aaff`)은 **항상 표시**하고 엣지 비선택 시 흐리게만 그린다(`_sync_handles`, opacity `_HANDLE_IDLE_OPACITY`) — `setVisible(False)`로 숨기면 Qt가 마우스 그랩·선택 가능성까지 잃어 드래그가 죽고, 이를 우회하려 `mousePressEvent`에서 super를 건너뛰면 Qt가 드래그 기준 좌표를 기록하지 못해 다음 이동이 화면 왼쪽 위로 튄다(사용자 보고 2건이 같은 뿌리) — 엣지는 절대 이동하지 않으므로(pos()가 항상 원점) 자식 로컬 좌표가 곧 씬 좌표다. 핸들은 Qt 기본 `ItemIsMovable`로 드래그되고 `itemChange(ItemPositionHasChanged)`가 실시간 미리보기(`edge.update_waypoint_preview`, undo 없음)를 반영하며, release 시 `scene.handle_items_moved`(WP-DM 이전에는 `handle_waypoint_moved`)가 undo 가능한 커맨드를 커밋한다(노드 드래그 관례와 동일 결). **핸들의 좌클릭 press/release는 `super()`를 반드시 호출한다** — Qt가 거기서 드래그 기준 좌표를 기록하므로 우회하면 다음 이동이 스테일 오프셋으로 계산돼 아이템이 화면 왼쪽 위로 튄다(사용자 보고). 단일 클릭 선택 규칙이 엣지 선택을 해제해도, 핸들을 항상 표시하는 위 정책 덕에 마우스 그랩이 유지되므로 수동 선택 조작은 필요 없다(초기 구현은 super를 건너뛰고 선택을 직접 조작했으나, 그게 바로 좌상단 튐의 원인이었다 — `c3d7f39`에서 폐기). 핸들 우클릭 "경유점 제거" 또는 핸들 선택 후 Delete(씬 Delete 처리는 선택에 핸들이 있으면 **경유점만 제거하고 엣지/노드 삭제 분기를 건너뛴다** — 한 키에 전이까지 지워지는 것 방지), 엣지 컨텍스트 메뉴 "경유점 모두 제거"(직선 복원)도 제공.
- **undo:** `AddWaypointCmd`/`MoveWaypointCmd`/`RemoveWaypointCmd`/`ClearWaypointsCmd`(`view/commands/transition_commands.py`) — `MoveStateCmd`와 동일한 관례로 `TransitionViewModel.waypoints`를 직접 변경(모델 sync_fn 불필요, 저장 시점에만 project.edge_layout으로 평탄화). `FsmScene`(프로젝트 캔버스)과 `AgentFsmScene`(에이전트 캔버스) 양쪽에서 동일하게 동작 — 오버라이드 불필요.

### 캔버스 드래그 이동 (WP-DM)

- **문제:** 이동 가능 아이템 3종(`StateNodeItem`/`ReferenceNodeItem`/`WaypointHandleItem`)에
  공통 베이스가 없어 드래그 로직이 세 번 중복 구현됐고, 다중 선택 처리는 `StateNodeItem`
  경로에만 있었다. 러버밴드 다중 선택 도입 후 증상이 드러났다.
- **고장 메커니즘(실측):** 드래그 *도중*에는 Qt가 선택된 이동 가능 아이템을 전부 정상적으로
  함께 옮긴다(상태·레퍼런스 노드는 `mouseMoveEvent`에서 `super()`를 호출하고, 웨이포인트
  핸들은 아예 오버라이드하지 않아 Qt 기본 구현이 그대로 움직인다) — **이 단계는 버그가 아니다.**
  진짜 고장은 release *이후*다. release 이벤트는 잡은(grabbed) 아이템 하나에만 배달되므로
  구 핸들러는 그 하나만 커맨드화해 vm을 갱신하고, 이어지는 `execute()` → notify →
  `_rebuild()`의 `item.setPos(vm.x, vm.y)`가 **커맨드를 못 받은 passenger 아이템을 원좌표로
  스냅백**시킨다. 무엇을 잡았느냐에 따라 튕기는 대상이 달라진다.
  → **검증은 반드시 release 완료 후 vm 좌표로** 해야 한다. 드래그 도중이나 화면 좌표
  (`item.pos()`)로 단언하면 고장이 있어도 통과한다.
- **해결:** `DraggableItemMixin`(`canvas/draggable.py`) 공통 수명주기 +
  `FsmScene.handle_items_moved(grabbed, old, new)` 단일 진입점 — 선택된 모든 draggable을 모아
  하나의 `MacroCommand`로 묶는다. **씬에 아이템 타입 분기를 두지 않는다** — 커맨드 생성
  지식은 각 아이템의 `make_move_command()`에 있고 씬은 수집·묶기만 한다. 기존
  `handle_node_moved`/`handle_ref_node_moved`/`handle_waypoint_moved`는 시그니처를 유지한
  위임 래퍼로 존치(호출부·테스트 호환). `AgentFsmScene`은 오버라이드 없이 그대로 상속.
- **press 시점 스냅샷(`snapshot_drag_positions`)이 필요한 이유:** `WaypointHandleItem`은
  `itemChange`에서 pos() 변경마다 `transition_vm.waypoints`를 실시간 미리보기 갱신한다
  (`update_waypoint_preview`). Qt의 그룹 드래그는 passenger에게도 `itemChange`를 실시간으로
  쏘므로, release 시점에 `vm_position()`을 다시 읽으면 **이미 새 값**이라 `old == new`로
  오판되어 커맨드가 만들어지지 않고 **undo 불가능한 변경이 조용히 커밋**된다. 그래서
  `begin_drag()`가 press 시점에 선택된 모든 draggable의 vm 좌표를 미리 떠 두고,
  `handle_items_moved`가 passenger의 old를 그 스냅샷에서 우선 조회한다(없으면
  `vm_position()` 폴백 — press를 안 거친 직접 호출 경로 호환). 이동 없이 끝난 클릭은
  `clear_drag_positions()`로 스냅샷을 닫는다.
- **회귀 금지:** `WaypointHandleItem`의 `mousePressEvent`/`mouseReleaseEvent`에서 `super()`
  호출을 제거하면 Qt가 드래그 기준 좌표를 기록하지 못해 다음 드래그가 좌상단으로 튄다
  (WP-ER에서 겪은 버그). 핸들 `setVisible(False)`도 금지(마우스 그랩 소실).

### 본문 undo 스택 (WP-BU)

- **스택이 둘이라는 것이 설계다.** 캔버스 구조 편집은 `CommandStack`(Ctrl+Z, HistoryPanel,
  스크립트 리스너)이고, 컴포넌트 **본문(body)은 그와 분리된 자체 undo 스택**을 갖는다. 본문
  타이핑이 노드 이동·전이 생성과 한 스택에 섞이면 Ctrl+Z가 무엇을 되돌릴지 예측할 수 없다 —
  포커스가 에디터면 그 문서의 undo가, 캔버스면 CommandStack의 undo가 동작하는 것이 기대 동작이다.
- **고장:** `SectionContentPanel.show_body`가 `setPlainText`로 내용만 갈아끼웠다. 이 호출은
  문서의 undo 이력을 지우므로, 다른 컴포넌트를 잠깐 열었다 돌아오면 본문 되돌리기 이력이
  통째로 사라져 있었다(탭을 닫아도 소실).
- **해결:** `editors/body_documents.py`의 `BodyDocumentRegistry`(모듈 전역 `registry()`)가
  컴포넌트 **id별로 `QTextDocument`를 보관**하고, `show_body`가 `MarkdownEditor.attach_document`로
  문서를 통째로 교체한다. 각 문서가 자기 undo 스택을 들고 있으므로 탭을 옮겨다녀도 이력이 유지된다.
  `document_for`는 문서가 이미 있으면 **모델과 비교하지 않고 그대로 돌려준다** — 모델을 다시
  밀어넣으면 이력이 날아가기 때문. 모델이 외부 경로로 바뀐 경우에만 `sync_from_model`을 쓴다
  (이때는 이력 초기화가 의도된 동작).
- **문서가 편집 중 진실이고 모델은 미러다.** `textChanged` → `_save_body`가 `component.body`를
  계속 따라가며, undo/redo도 `textChanged`를 발생시키므로 되돌린 내용이 모델에 자동 반영된다.
- **Qt 함정 2종(둘 다 실측):** ① 맨 `QTextDocument()`는 `QPlainTextEdit`이 거부한다
  ("Document set does not support QPlainTextDocumentLayout") — 생성 시
  `doc.setDocumentLayout(QPlainTextDocumentLayout(doc))`가 필수. ② `QSyntaxHighlighter`는 생성 시
  넘긴 **문서를 부모로 삼기 때문에**, 문서를 교체하면 이전 문서와 함께 파괴된다
  ("Internal C++ object (MarkdownHighlighter) already deleted"). `MarkdownEditor.__init__`이
  `self._highlighter.setParent(self)`로 부모를 에디터로 옮겨 두는 이유다.
- **수명주기 배선:** `app.set_project`가 `registry().clear()`(프로젝트 전환),
  `app._on_delete_component`가 `discard(component)`.
- **검증 함정:** 왕복 없이 undo만 확인하면 고장이 있어도 통과한다 — 반드시 **다른 컴포넌트로
  전환했다 복귀한 뒤** undo를 검증해야 한다(`tests/view/editors/test_body_documents.py`).
  타이핑 시뮬레이션도 `setPlainText`가 아니라 `QTextCursor.insertText`여야 한다(전자는 undo 스택을 지운다).

### 앱 내장 MCP 서버 (WP-MCP)

- **성격:** "CC가 쓰는 도구 모음"이 아니라 **사람이 GUI에서 작업하는 중에 CC가 같은 프로젝트를
  함께 보고 함께 만지는 통로**다. 그래서 CC는 사용자의 현재 선택을 알 수 있고(`get_selection`),
  CC의 편집은 사용자의 undo 스택에 들어가며, 스크립트 리스너에 사람 편집과 같은 형식으로 남는다.
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
  저장 경로가 바뀌면 `_sync_files_root`가 접속 정보의 project 필드도 갱신한다(배선 지점 1개 유지).
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
- **`set_component_description`은 아직 undo되지 않는다** — 프론트매터 편집 전반이 WP-CE에서
  커맨드화될 때 함께 옮겨간다. 도구 docstring에 그 사실을 적어 두었다.
- **포트·분기 의미론(WP-CE):** `set_transfer_on`(출력 포트)/`set_transition`(기존 전이의
  trigger·guard)/`connect_states`의 trigger·guard 인자.
  **구조(노드+선)만 만들면 분기가 표현되지 않는다** — 여러 갈래로 나가는 노드는
  transfer_on에 갈래를 선언하고 각 전이에 trigger를 물려야 캔버스 포트가 갈라지고 라벨이 보인다.
  `set_transition`은 None=건드리지 않음, ""=지움 규약이다.
- **블랙보드(WP-CE):** `create_blackboard_class`(스칼라 4종 + collection none/list/set 검증)/
  `set_state_access`(노드의 reads/writes 선언 → 캔버스 뱃지 + 컴파일 산출 구체화).
- **에이전트 호출은 캔버스와 같은 규칙을 강제한다(WP-CE).** 초기 구현은 스킬→에이전트를 그냥
  직결시켰는데, 캔버스는 그걸 **막는다**(`FsmScene`: 에이전트 노드 입력은 call_agent 포트에서만,
  call_agent 포트는 에이전트로만). 같은 조작인데 경로에 따라 결과가 달라지면 협업 도구로 실격이라
  `connect_states`가 동일 규칙을 검사한다. 포트는 `add_agent_call(skill, event)`로 먼저 만든다.
  (계약 카드 자동 생성은 WP-CT로 퇴역 — 호출 계약은 컴파일이 그래프에서 유도한다.)
- **에이전트 스코프(WP-RF-1c):** 도구의 `agent` 파라미터는 **시그니처째 제거**됐다(스키마 노출
  기준). 캔버스 편집(`_scope`)의 대상은 프로젝트 그래프 하나뿐이고,
  `_find_component(name)`은 전역 스킬/에이전트만 찾는다 — v1 파일의 로컬 스킬은 로드 시 전역
  승격되므로 별도 접근 경로가 필요 없다.
- **훅 라이브러리(WP-CE 4차):** `create_hook`/`update_hook`/`delete_hook`(라이브러리 = 정의의
  단일 진실) + `set_component_hooks`(스킬/에이전트가 이름으로 참조). GUI 훅 다이얼로그는 모델에
  직접 쓰지만 MCP 경로는 `AppendToListCmd`/`RemoveFromListCmd`/`SetAttrCmd`를 거쳐 undo된다.
  `update_hook`은 빈 문자열/None = 건드리지 않음, matcher·description은 ""로 지움, timeout은 0이
  지정 없음이다. **삭제는 참조를 건드리지 않는다**(GUI와 같은 정책) — 남은 참조는
  `dangling_hook_ref` 경고로 드러나므로 결과의 `still_referenced_by`로 보고한다.
  `set_component_hooks`는 라이브러리에 없는 이름을 **거부**한다(오타가 컴파일까지 조용히 흘러가
  경고로만 드러나는 것을 막는다). `config.hooks`의 선언 기본값은 `{}`가 아니라 `None`이라,
  undo는 빈 dict가 아니라 None으로 되돌아간다.
- **참조 노드 배치(WP-CE 4차):** `place_reference`/`link_reference`/`unlink_reference`/
  `unplace_reference`. 참조 노드는 상태가 아니라 **여러 상태가 공유하는 문서**라 같은 스킬을
  여러 번 놓을 수 있어(그래서 `place_component`와 별도 도구다) 이름 + `index`로 지목한다.
  구현은 `FsmScene.drop_reference_skill`/`create_reference_link`/`delete_reference_node`를
  그대로 호출한다 — 캔버스와 같은 커맨드·같은 `_sync_refs_to_model` 경로다. 프로젝트 캔버스
  전용(`agent` 인자 없음).
- **프로젝트 속성(WP-CE 4차):** `set_project_properties(name/description/version/build_target)` —
  빈 값은 건드리지 않고, 여러 필드를 한 번에 주면 `MacroCommand`로 1 undo 단위가 된다.
  `set_component_description`도 이때 커맨드화됐고(이전에는 이 편집만 Ctrl+Z가 듣지 않았다)
  `set_component_when_to_use`가 함께 붙었다.
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
- **세션(저장/열기):** `save_project`/`open_project`/`export_package`/`list_recent_projects`.
  경로는 **폴더**를 받는다(WP-PK — 구버전 파일도 열린다). **저장이 여는 절차
  안에 있다** — 편집 중인 내용은 메모리에만 있어 여는 순간 사라지므로, 잃을 것이 있으면
  (`MainWindow.project_has_content()` — "새 프로젝트" 확인 다이얼로그와 같은 판정) 먼저 저장하고
  **저장할 수 없으면 열지 않는다**. 한 번도 저장한 적 없으면 `save_current_as`로 경로를 받아야
  하고, 버리려면 `save_current=False`를 명시해야 한다. 이를 위해 `MainWindow._save_to_path`/
  `open_path`가 `bool`을 돌려준다(GUI 경로는 상태바 문구로 결과를 말하므로 무시한다 — 반환값은
  성공을 전제로 다음 단계를 진행하는 호출자를 위한 것이다). 저장은 파일 쓰기라 undo 대상이 아니다.
- **아직 노출하지 않은 편집:** 컴포넌트 삭제(아래). 커맨드를 만들기만 하면 `TOOL_NAMES`에 이름을
  더해 노출된다.
- **컴포넌트 삭제는 의도적으로 빠져 있다:** `remove_component`가 그래프 placement·skill_ref
  None화·graph_layout·edge_layout까지 훑어 정리하므로, 되돌리려면 그 정리 내역 전부를
  기록·복원해야 한다. 부분 복원 커맨드는 없느니만 못하므로 WP-CE 본편으로 미뤘다(GUI 삭제는 종전대로 동작).
- **연결 방법:** 도구 메뉴 → "MCP 서버 정보..."가 접속 주소와 `.mcp.json` 스니펫
  (`{"mcpServers": {"daedalus": {"type": "http", "url": "http://127.0.0.1:8787/mcp"}}}`)을 보여준다.

### 안정 ID + 직렬화 (serialize.py)

- **안정 ID:** `State`(베이스)/`Transition`/`StateMachine`/`Region`/`Variable`/`Skill`(베이스)/`AgentDefinition`에 `id: str = field(default_factory=lambda: uuid4().hex, kw_only=True)`. kw_only로 다중 상속 필드 순서 제약을 회피한다. eq=False 클래스는 identity 동등성/해시를 유지(id는 `__eq__`/`__hash__` 무관)하고, 값 동등성 클래스(Variable/Skill/Agent)는 `compare=False`로 값 비교에서 제외한다.
- **직렬화 원칙:** `serialize_project`/`deserialize_project`는 JSON 호환 dict(`"format": 2` 버전 키)를 만든다. **소유 객체는 인라인, 참조는 ID 문자열로 평탄화**한다 — Transition.source/target(state id), SimpleState.skill_ref·Transition.skill_ref(component id), StateMachine.initial_state/final_states(state id). 다형성은 `kind` property를 태그로 재사용. enum은 `.value`↔타입 복원. 역직렬화는 2-pass(객체 생성+id 레지스트리 → 참조 해소)이고 dangling id는 None+경고. `Blackboard.parent`는 ID가 아니라 sub_machine 소유 구조로 재연결한다. serialize.py는 순수 모델(Qt 무관).
- **포맷 v2 + `_migrate_v1` (RF-1b):** `serialize_project`는 항상 `"format": 2`를 쓴다. `deserialize_project`는 format 1(또는 키 부재 구버전)을 받으면 **`_migrate_v1` 한 함수로 집약된 단방향 마이그레이션**을 태운 뒤 v2로 읽는다(왕복 보존 없음 — 열면 v2로 저장된다). 미지의 상위 format은 명시 에러. `_migrate_v1`이 다루는 축(입력 dict는 deepcopy로 불변): ① delegations 드롭(경고 — WP-RF-1a. 위임을 가리키던 placement skill_ref는 dangling 경고와 함께 None으로 정리) ①-b 에이전트 로컬 스킬 → **전역 스킬 승격**(WP-RF-1c, `_promote_local_skills` — 이름 충돌(전역 스킬·에이전트·먼저 승격된 스킬) 시 `<agent>--<name>` 개명 + 재충돌 시 `-2` 접미 유일화 + 개명 시 소유 에이전트 config.skills 참조 치환, 승격마다 경고 1건, id 보존이라 transfer skill_ref 해소 유지. 승격 dict는 data["skills"]에 합류해 이후 단계·역직렬화에서 전역 스킬과 같은 경로. **format 2 파일도 에이전트 dict에 `skills` 키가 있으면 같은 승격을 탄다** — RF-1b 시점 코드가 저장한 v2 파일의 인라인 로컬 스킬이 경고 없이 드롭되는 것 방지) ② sections 트리→body 평탄화(render_markdown) + `${CLAUDE_PLUGIN_ROOT}/files/`→`${ROOT}/files/` 치환(WP-RT) ③ 퇴역 키 조용히 드롭 — entry_paths/caller_contracts/전이의 target_port(WP-IP/WP-CT, 경고 불필요) ④ 에이전트 transfer_on 부재 시 내부 FSM ExitPoint 이름·색 승계(WP-AF) ⑤ 구버전 훅(커맨드 하나짜리)을 handlers 목록으로 감싸기 + 핸들러 command→script(WP-HK/WP-HS) ⑥ `field_type: "number"`→`"float"`(FieldType.NUMBER 퇴역). 픽스처 고정은 `tests/model/test_migrate_v1.py`(v2 왕복 항등 포함).
- **프로젝트 그래프 직렬화:** `serialize_project`는 `graph`(`_ser_machine` 재사용)와 `graph_layout`을 왕복한다. 그래프 placement의 skill_ref는 component id로 평탄화되고, 역직렬화 시 pass1에서 등록된 skills/agents를 pass2가 해소한다(그래프 `_deser_machine`은 pass1에서 호출). 하위 호환: `"graph"` 키 부재(구버전 파일) → `_make_project_graph()`로 빈 그래프 생성(경고 없음). graph.blackboard.parent는 역직렬화 시 프로젝트 블랙보드로 재연결.
- `AgentDefinition.graph_layout`/`PluginProject.graph_layout`의 키는 state.name이 아니라 **state.id**다 (이름 변경 시 레이아웃 유실 방지).

### SKILL_FIELD_MATRIX

스킬 유형(procedural, declarative, transfer, reference)별로 프론트매터 필드의 `FieldRule`을 정의하는 매트릭스.

```python
@dataclass
class FieldRule:
    visibility: FieldVisibility   # REQUIRED / OPTIONAL / DEFAULT / FIXED
    fixed_value: Any = None       # FIXED일 때 컴파일러가 강제할 출력값 (enum)
    default_value: Any = None     # 위젯 초기 표시용 (단일 진실은 config 선언 기본값)
    emit: FieldEmit = FieldEmit.FRONTMATTER  # 컴파일러 배출 위치 (FRONTMATTER/BODY/INVOCATION/SETTINGS)
```

`field_matrix.py`는 순수 모델(Qt 무관)이다. 편집 위젯 매핑은 view 측 `daedalus/view/editors/field_widgets.py`의 `FIELD_WIDGETS: dict[SkillField, type[QWidget]]`(1차원, kind 무관)과 `AGENT_FIELD_WIDGETS: dict[AgentField, type[QWidget]]`로 분리되어 있다. 프론트매터 키는 `SkillField.frontmatter_key` property가 제공한다 (kebab-case, `WHEN_TO_USE`는 None — description/본문 합류는 컴파일러 정책). `AgentField.frontmatter_key`는 **camelCase**(`permissionMode`/`disallowedTools`/`maxTurns`/`mcpServers`, WP-LA에서 확정) — 스킬 프론트매터의 kebab-case와 **규약이 다르므로 한쪽을 보고 다른 쪽을 유추하면 안 된다**. 이전에는 케이싱 미확정이라 kebab-case를 잠정값으로 썼는데, 그 키들은 CC가 인식하지 못해 조용히 무시된다(CC 공식 sub-agents 문서 필드 표 기준, 2026-08 확인). FIXED 필드는 편집기 비노출이며 `fixed_value`는 컴파일러 출력 시 강제(config에 미기록). `AGENT_FIELD_MATRIX`는 에이전트 전용 1차원 매트릭스.

### FieldType (통합 타입)

```python
class FieldType(Enum):
    STRING = "string"   # Variable / DynamicField 공용
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    LIST = "list"
    JSON = "json"
    ANY = "any"
```

- `VariableType`과 `DynamicFieldType`을 통합한 단일 열거형
- `Variable.field_type: FieldType`, `DynamicField.field_type: FieldType`
- **블랙보드 필드는 스칼라 4종만**(WP-BT, 사용자 확정): `BLACKBOARD_FIELD_TYPES = (STRING, INT, FLOAT, BOOL)` — 컨테이너 형상은 CollectionType(none/list/set)이 전담한다("문자열 목록" = STRING × LIST). 편집기 콤보는 이 4종만 노출(legacy 값은 "(legacy)" 표시 유지), `invalid_blackboard_field_type` 경고가 구버전 필드를 짚는다. Variable은 종전 그대로 전 멤버 사용 가능.
- 구 `NUMBER` 멤버는 RF-1b에서 **삭제** — v1 파일의 `"number"`는 로드 시 `FLOAT`으로 마이그레이션된다(`_migrate_v1`). 매핑 정본은 `blackboard.py`의 `FIELD_TYPE_TO_JSON_SCHEMA`(INT→integer, FLOAT→number).

### ComponentConfig 계층

```
ComponentConfig(ABC)          # model, effort, hooks 공통 필드
├── SkillConfig(ABC)          # argument_hint, allowed_tools, paths
│   ├── ProceduralSkillConfig # disable_model_invocation, context, agent, shell 등
│   ├── DeclarativeSkillConfig
│   ├── TransferSkillConfig
│   └── ReferenceSkillConfig
└── AgentConfig               # tools, permission_mode, skills, isolation 등
```

### CompletionEvent

세 가지 완료를 통합적으로 표현:
- SimpleState 작업 완료 → 부모 FSM에 완료 신호
- CompositeState sub_machine이 final_state 도달 → 부모 FSM에 완료 신호
- ParallelState는 `ParallelState.join` 전략에 따라 완료 (ALL=전 Region, ANY=하나, N_OF=join_count개) → 부모 FSM에 완료 신호

`Transition.trigger = CompletionEvent(name="done")` 으로 설정.

### Validator 규칙 (재귀 적용)

**모듈 배치(WP-RF-3d):** `model/validation/`은 패키지다 — `severity.py`(ValidationError·WARNING_RULES) /
`machine_rules.py`(`_MachineRules` 믹스인 — 머신 수준 규칙 + `validate`/`_validate_machine` + SKIPPABLE_RULES) /
`project_rules.py`(`_ProjectRules` 믹스인 — `validate_project` + CC_BUILTIN_TOOLS + `_strip_markdown_code`).
`Validator`는 `__init__.py`가 두 믹스인을 상속해 합성한 클래스이며, `__init__`이 재-export 파사드라
`from daedalus.model.validation import …`와 `Validator._check_*` 이름이 분해 전과 동일하게 동작한다.
새 규칙은 해당 그룹 모듈에 `_check_*` staticmethod로 추가하고 오케스트레이터(`_validate_machine` /
`validate_project`)에 한 줄 등록한다 — 등급 지정을 빼먹으면 `tests/model/test_validation_severity.py`가
깨진다(패키지 **전 모듈** 소스를 합쳐 `rule=` 리터럴을 introspect한다 — 열거는
`pkgutil.walk_packages` **재귀**라, 이후 규칙을 하위 *패키지*로 한 겹 더 나눠도
커버리지가 따라간다. 비재귀 `iter_modules`였다면 중첩 모듈의 등급 미분류가 조용히
통과한다 — A/B 스모크로 실측 확인).

`ValidationError` 필드: `rule`, `message`, `source`(기존) + `subject: object | None`(문제 객체, 향후 노드 점프용 — `compare=False`이므로 identity 비교로 조회) + `path: tuple[str, ...]`(중첩 경로, 예: `("agent:Writer", "region:r1")`). 기본값이 있어 기존 생성자 호환. `validate_project`는 최상위 FSM 오류에 root path(`"skill:<이름>"`/`"agent:<이름>"`)를 주입한다.

`ValidationError.is_warning` property — 규칙이 경고 등급이면 True, 에러 등급이면 False. `WARNING_RULES: frozenset[str]` 모듈 상수가 경고 등급 규칙 집합을 단일 진실로 보유 (view에서 rule 이름 하드코딩 금지). `invalid_component_name`은 빈 이름=에러/불일치=경고를 `is_warning`에서 메시지 내용으로 세분화한다.

#### 머신 수준 (18규칙명)

| 규칙 | 설명 |
|------|------|
| `initial_state_in_states` | `sm.initial_state ∈ sm.states` (identity 기준) |
| `final_states_in_states` | `sm.final_states ⊆ sm.states` |
| `no_nested_agent` | CompositeState 안에 CompositeState 불가 |
| `no_agent_to_agent` | Agent → Agent 직접 전이 불가 (Skill 경유 필수) |
| `missing_required_input` | LOCAL scope 필수 input이 data_map에 없으면 경고 |
| `pseudo_state_hooks` | 의사 상태에 lifecycle 훅 설정 시 경고 |
| `completion_event_on_composite` | Composite/ParallelState 출발 전이에 CompletionEvent 없으면 경고 |
| `no_duplicate_skill_ref` | 동일 스킬/에이전트의 중복 배치 금지 |
| `transfer_on_not_empty` | ProceduralSkill/Agent transfer_on 최소 1개 (ExitPoint 폴백은 RF-1b에서 삭제 — transfer_on 단일 진실) |
| `transition_endpoint_not_in_states` | Transition.source/target이 sm.states에 없으면 에러 (initial/final 비대칭 해소) |
| `duplicate_state_name` | 동일 머신 내 동명 상태 경고 (컴파일/직렬화 혼동 방지) |
| `unreachable_state` | initial_state + 모든 EntryPoint에서 전이 그래프로 도달 불가 상태 경고 (스킬/에이전트 FSM 대상. 프로젝트 그래프 자체는 WP-EP로 스킵 — 아래 "프로젝트 그래프 검증" 참조) |
| `invalid_data_map_source` | Transition.data_map의 key가 source.outputs에 없으면 경고 (pseudo 상태 스킵) |
| `trigger_unknown_event` | CompletionEvent trigger.name이 source 출력 이벤트 집합에 없으면 경고 (EventDef rename 고아 전이 검출) |
| `transition_type_consistency` | INTERNAL/SELF 타입인데 `source is not target`이면 에러 |
| `choice_completeness` | ChoiceState outgoing 0개=에러, 무가드 2개 이상=에러(else 중복/비결정) |
| `choice_completeness_missing_else` | ChoiceState 무가드(else) 전이 0개=경고 (LLM 해석 결정성 저하) |
| `parallel_join_count` | ParallelState join=N_OF인데 join_count가 None이거나 region 수 초과 시 경고 |

**INTERNAL vs custom_events 역할 분리:** INTERNAL = 상태 비이탈 + guard/action 있는 반응(entry/exit 미발화, `source is target` 필수). 단순 반응(guard·data_map 없이 액션만)은 `State.custom_events`로 표현한다. 의사 상태(Choice/Terminate/Entry/Exit)에는 lifecycle 훅뿐 아니라 custom_events도 `pseudo_state_hooks` 경고 대상이다.

**ChoiceState else 관례:** ChoiceState outgoing 중 **무가드 전이 = else 분기**. 가드 전이를 선언 순서로 평가하고 모두 실패하면 유일한 무가드 전이로 진행. 컴파일러 절차 서술은 무가드 전이를 `[else]`로, ParallelState는 join 전략 문구로 출력한다.

재귀: CompositeState.sub_machine과 Region.sub_machine 내부도 동일하게 검증. 재귀 시 `path`에 `"agent:<이름>"` 또는 `"region:<이름>"`이 누적된다.

**skip_rules (WP-EP):** `Validator.validate`/`_validate_machine`은 `skip_rules: frozenset[str] = frozenset()` 파라미터를 받아 이름이 속한 규칙 검사를 생략한다(기본값 빈 집합이라 기존 호출 전부 하위 호환). 재귀 호출(sub_machine/Region)에는 **전파하지 않는다** — 호출부가 지정한 그 머신 자체에만 적용된다.

**프로젝트 그래프 검증:** `validate_project`는 `project.graph`도 머신 규칙으로 검증하며 root path는 `("project",)`다. 단 그래프에 placement(EntryPoint 외 노드)가 0개면 검증을 스킵(`_graph_has_placements`) — 빈 캔버스 경고 폭주 방지. `transfer_on_not_empty` 같은 컴포넌트 수준 규칙은 머신 검증에 없으므로 무관. **`unreachable_state`는 `skip_rules={"unreachable_state"}`로 스킵된다(WP-EP)** — CC 플러그인 의미론상 프로젝트 그래프의 모든 배치는 user_invocable 스킬 등으로 독립 시작 가능해 "EntryPoint에서 도달 불가"가 성립하지 않는다. skip_rules는 재귀에 전파되지 않으므로 에이전트 sub_machine 내부의 `unreachable_state`는 기존대로 검사된다.

#### 프로젝트 수준 (18종)

`Validator.validate_project(project)` — 전체 FSM 검증 후 추가:

| 규칙 | 설명 |
|------|------|
| `duplicate_component_name` | skills/agents 전체에서 동명 컴포넌트 에러 (컴파일 디렉토리 충돌) |
| `invalid_component_name` | 이름이 `^[a-z0-9][a-z0-9-]*$` 불일치 시 경고, 빈 이름은 에러 |
| `dangling_string_reference` | `ProceduralSkillConfig.agent`, `AgentConfig.skills`, `reference_placements.skill_name`의 문자열 참조 실존 검사 (스킬 이름은 전역 skills 기준) |
| `duplicate_tool_name` | `tool_shelf` 내 동명 Tool 에러 (이름 참조 모호) |
| `empty_tool_definition` | UserDefinedTool 본문(body) 빈 값 / MCPTool server·tool_name 빈 값 경고 |
| `dangling_tool_ref` | FSM의 ToolEvaluation/ToolExecution.tool이 `tool_shelf ∪ CC_BUILTIN_TOOLS`에 없으면 경고 (빈 문자열은 스킵). 참조 수집은 상태 훅·custom_events·전이 가드/액션 체인 + Composite 중첩 + sub_machine/Region 재귀 |
| `duplicate_hook_name` | `hook_library` 내 동명 HookDef 에러 (이름 참조 모호) |
| `empty_hook_command` | HookDef.command 빈 값 경고 |
| `hook_matcher_without_tool_event` | matcher가 있는데 event가 Pre/PostToolUse가 아니면 경고 (matcher는 도구 이벤트 전용) |
| `dangling_hook_ref` | config.hooks 키가 hook_library에 없으면 경고 (스킬·에이전트 전부 검사) |
| `hook_matcher_matches_nothing` | MCP matcher가 서버 이름까지만이면 어떤 도구와도 맞지 않으므로 경고 (정규식이 아니라 정확한 문자열 비교 — `server__.*`를 쓰라고 안내, WP-HS) |
| `dangling_blackboard_ref` | State.reads/writes의 `"Class"`/`"Class.field"` 문자열 참조가 프로젝트 최상위 블랙보드 class_definitions에 없으면 경고 (재귀 — sub_machine/Region + 프로젝트 그래프 포함, 빈 문자열은 스킵) |
| `orphan_blackboard_field` | 블랙보드 필드 중 어떤 상태의 reads/writes에도 등장하지 않으면 경고 (클래스 전체 참조는 그 필드 전부 커버로 간주, 프로젝트 전체에 접근 선언이 하나도 없으면 스킵 — 경고 폭주 방지) |
| `invalid_blackboard_field_type` | 블랙보드 필드 타입이 허용 집합(BLACKBOARD_FIELD_TYPES — 스칼라 4종) 밖이면 경고 (컨테이너 형상은 CollectionType 전담, WP-BT) |
| `mcp_agent_in_marketplace_build` | `project.build_target == MARKETPLACE`인데 에이전트 config.tools에 `mcp__` 도구가 있거나 mcp_servers 선언이 있으면 경고 (CC는 플러그인 배포 에이전트의 MCP 사용을 미지원 — LOCAL 빌드면 무경고, WP-TG) |
| `unsupported_agent_field_in_marketplace_build` | MARKETPLACE 빌드인데 에이전트가 `hooks` 또는 기본값 아닌 `permissionMode`를 쓰면 경고 (CC가 보안상 무시 — MCP는 위 규칙이 전담, WP-LA) |
| `plugin_root_in_local_build` | `project.build_target == LOCAL`인데 스킬/에이전트 본문에 files/ 참조 이외 용도의 `${CLAUDE_PLUGIN_ROOT}`가 남아 있으면 경고 (files/ 참조는 컴파일이 자동 치환하므로 제외, WP-TG) |
| `skill_dir_token_in_agent` | 에이전트 본문에 `${CLAUDE_SKILL_DIR}`가 있으면 경고 — 이 변수는 스킬 전용이라 에이전트 .md에서 치환되지 않는다 (코드 표기 제외, 빌드 타깃 무관, WP-SF) |

도구 모델(`tool.py`): `Tool(PluginComponent, ABC)` 단일 진실 + `BuiltinTool`/`MCPTool`/`UserDefinedTool`. shelf = 프로젝트(`PluginProject.tool_shelf`) 소유, FSM은 `Tool.name` 문자열로 참조(fsm/는 plugin 무관 — 객체 참조 금지, Validator가 실존 검증). `CC_BUILTIN_TOOLS`는 `validation/project_rules.py` 모듈 frozenset이다(파사드 재-export로 `daedalus.model.validation`에서도 임포트 가능 — Read/Write/Edit/Bash/Glob/Grep/WebFetch/WebSearch/Agent/Task/TodoWrite/NotebookEdit/SlashCommand/PowerShell).

블랙보드 접근 선언 검증(`dangling_blackboard_ref`/`orphan_blackboard_field`, WP-BB): 상태
reads/writes 순회는 `Validator._scan_state_access(sm, visit)` 공용 헬퍼(CompositeState.sub_machine/
ParallelState.region 재귀)를 쓰며, project.skills(fsm)/project.agents(fsm)/project.graph
세 축을 모두 검사한다.

### 훅 (HookDef / hook_library)

**규격 정본은 SchemaStore의 `claude-code-settings.json`이다**(2026-08 확인) — 공식 문서에는 훅의 전체 형식이 나오지 않는다. `$defs.hookMatcher` / `$defs.hookCommand` / `properties.hooks`를 보라.

CC의 구조는 **3단**이다: 이벤트 → 그룹(matcher + 핸들러 목록) → 핸들러. `HookDef` 하나가 **그룹 하나**에 대응하고 `handlers: list[HookHandler]`가 그 안의 핸들러다(WP-HK 이전에는 훅 하나가 커맨드 하나였다).

- **이벤트 31종**(`HookEvent`) — 스키마 `properties.hooks`의 키 전체. matcher를 받지 않는 8종은 `NO_MATCHER_EVENTS`(스키마 description이 "does not support matchers"라고 명시한 것들), 여집합이 `MATCHER_EVENTS`(구 `TOOL_MATCH_EVENTS` 별칭은 RF-1b에서 삭제). 공식 문서에 없는 2종은 `UNDOCUMENTED_EVENTS`.
- **핸들러 5종**(`HookHandler` ABC + `CommandHook`/`PromptHook`/`AgentHook`/`HttpHook`/`McpToolHook`) — 공통 속성은 timeout / `condition`(→`if`, 예약어라 필드명이 다르다) / `status_message`(→`statusMessage`). command는 args·shell(`HookShell`)·`run_async`(→`async`)·`async_rewake`, prompt는 model·`continue_on_block`, http는 headers·`allowed_env_vars`, mcp_tool은 server·tool·`tool_input`(→`input`). `kind`가 CC `type` 값이자 다형성 태그이고, `to_json()`이 CC 스키마 객체를 만든다(빈 값 키 생략 — 결정적). `HOOK_HANDLER_TYPES`/`HOOK_HANDLER_LABELS`가 태그↔클래스↔표시문구의 단일 진실.
- `HookDef.to_json()`은 **matcher를 그 이벤트가 받을 때만** 배출한다 — 무시되는 키를 내보내면 설정한 사람은 걸린 줄 알지만 아무 일도 일어나지 않는다.
- `ComponentConfig.hooks: dict`는 **이름 참조**다 — 키=hook_library의 HookDef.name, 값=오버라이드(빈 dict면 정의 그대로). 선언 기본값은 `{}`가 아니라 `None`.
- `hook_presets.py`의 `BUILTIN_HOOK_PRESETS`는 복사해 출발점으로 쓰는 템플릿이며 `preset_copy`가 **핸들러까지 깊은 복사**한다(얕게 복사하면 한 프로젝트의 수정이 다른 쪽에 샌다). command 외 타입(prompt/agent)의 출발점도 포함한다.
- **컴파일러**: 참조된 훅을 모아 `<out>/hooks/hooks.json` 생성(이벤트 키=HookEvent 선언 순서, 같은 이벤트 복수 훅=라이브러리 순서, 핸들러 0개인 훅은 배출 안 함). 스킬 프론트매터에는 `hooks: [이름, …]` 목록만. 프로젝트 설치 빌드의 에이전트는 프론트매터에 훅 본체가 나간다(WP-LA, 컴파일 정책 16번).
- **직렬화**: 핸들러는 `kind` 태그로 다형성 왕복. v1 파일(`handlers` 키 없이 `command`/`timeout`)은 `_migrate_v1`이 `CommandHook` 하나로 감싼다(경고 없음). 미지 `kind`는 건너뛴다 — 미래 버전 파일을 열어도 죽지 않는다.
- **검증**: `empty_hook_command`는 핸들러 0개 또는 핸들러의 필수 값이 빈 경우다. 무엇이 필수인지는 타입마다 다르므로 `handler.summary()`가 `"("`로 시작하는지로 판정한다 — 타입이 늘어도 규칙이 따라간다. `hook_matcher_without_tool_event`는 이름만 예전 그대로이고 판정은 `MATCHER_EVENTS` 기준이다.
- **UI**: `editors/hook_panel.HookLibraryPanel` — **상주 탭(인덱스 2)**. 모달 다이얼로그(`hook_editor.HookLibraryDialog`)는 3단 구조를 담을 수 없어 제거됐다(도구 메뉴 항목도 함께 — 탭이 늘 보이므로 지름길이 중복이다). 좌: 훅 목록(핸들러 없으면 ⚠). 우: 이벤트 콤보(matcher 미지원/미문서화를 문구에 표시) + matcher(받지 않는 이벤트면 잠금 + 이유 표시) + 핸들러 목록·폼(`_HandlerForm` — 타입이 바뀌면 통째로 다시 만든다). **"서브에이전트 프론트매터로 복사" / "hooks.json으로 복사"** 버튼이 이 프로젝트 밖의 파일에 붙여넣을 텍스트를 클립보드에 넣는다. `widgets/preset_picker`의 `set_hook_name_provider`로 HookPresetPicker가 hook_library 이름을 동적 표시하는 것은 그대로.
- **MCP**: `create_hook`/`update_hook`은 `handlers=[{...}]`로 CC 스키마 그대로 받는다(`command=` 인자는 커맨드 훅 하나를 만드는 지름길). 그 타입에 없는 속성은 **거부**한다 — 조용히 무시되면 왜 안 먹는지 알 수 없다. `list_hook_events`가 이벤트 31종과 matcher 지원 여부를, `hook_frontmatter_preview`가 서브에이전트 프론트매터 YAML을 돌려준다.

### 프로젝트 패키지 — 폴더가 곧 프로젝트 (WP-PK)

이미 절반은 그랬다. `files/`가 저장 파일 옆에 있고 `_sync_files_root`가 `parent`로 루트를 잡으니 프로젝트의 단위는 사실상 폴더였다. 다만 강제되지 않아 **같은 폴더의 `.daedalus.json` 둘이 `files/`를 말없이 공유하는 구멍**이 있었다. 폴더 = 프로젝트로 못 박으면 그 구멍은 정의상 사라진다.

- **`_current_path`는 여전히 안쪽 파일을 가리킨다.** 사용자에게 보이는 단위만 폴더로 바뀌고 저장 대상은 파일 그대로다 — 덕분에 `Path(_current_path).parent`로 계산하는 곳(FilePanel 루트·컴파일 `files_dir`·MCP 접속 정보·카탈로그 project_dir)이 **한 줄도 안 바뀌고**, 구버전 파일도 같은 코드 경로를 탄다. 이것이 이 변경의 파급을 작게 만든 유일한 결정이다.
- **`resolve_project_file`(저장 대상) vs `find_project_file`(열 대상)이 다르다.** 저장은 구버전 파일에 덮어쓸 때 그 이름을 유지하고(Ctrl+S가 형식을 말없이 갈아치우지 않는다 — 형식이 바뀌는 지점은 폴더를 고르는 "다른 이름으로 저장" 하나뿐), 열기는 폴더 안에서 정본을 찾고 없으면 구버전 `<이름>.daedalus.json` **하나**를 받아들인다(여럿이면 거절 — 조용히 하나를 고르면 나머지를 편집 중이라 착각하게 된다).
- **아직 없는 경로는 `is_dir()`로 판정할 수 없다.** 새 폴더에 저장하는 것이 정상 경로이므로 확장자로 가른다 — `.json`으로 끝나면 파일, 아니면 폴더. 이 판정이 없으면 "새 폴더에 저장"이 확장자 없는 파일 하나를 만들고 끝난다(테스트가 잡은 실제 버그).
- **Save As가 `files/`를 데려간다**(`_carry_files_dir`). 폴더가 곧 프로젝트인데 동봉 파일이 옛 폴더에 남으면 반쪽짜리다 — 컴파일하면 파일이 빠지고 `dangling_file_ref`로야 뒤늦게 드러난다. 목적지에 이미 `files/`가 있으면 건드리지 않는다(덮어쓰기보다 아무것도 안 하는 편이 낫다).
- **`.ddpj` = 프로젝트 폴더를 묶은 zip.** 폴더 **내용**이 아카이브 루트에 놓인다(푸는 쪽이 목적지를 정하므로 폴더 이름을 한 겹 더 넣으면 중첩만 깊어진다). 압축은 결정적(항목 정렬 + 고정 타임스탬프 `(1980,1,1,0,0,0)`)이고, 푸는 쪽은 목적지가 비어 있어야 하며 zip slip(절대 경로·`..`)을 **쓰기 전에** 검사한다(절반 푼 폴더를 남기지 않는다). 압축 안에서 직접 편집하지는 않는다 — `files/` 드래그·컴파일·저장이 전부 특수 경로가 되어 득보다 실이 크다.
- **UI:** File → "폴더 열기"(Ctrl+O) / "파일에서 열기…"(구버전 직접 지정) / "패키지로 내보내기… (.ddpj)" / "패키지 가져오기…". 창 제목·최근 목록은 `display_name`(새 형식이면 폴더 이름 — 파일 이름이 전부 `.daedalus.json`이라 그대로 보이면 구분이 안 된다).
- **MCP:** `open_project`/`save_project`가 폴더를 받고, `export_package`가 **먼저 저장한 뒤** 묶는다(`open_project`와 같은 이유 — 메모리에만 있는 편집을 빼놓고 묶으면 받는 쪽은 그것이 최신인 줄 안다). `open_project`는 열 수 없는 경로면 **저장하기 전에** 거절한다(헛저장은 혼란만 남긴다).

### 파일 참조 (files/) — WP-FR

플러그인에 동봉할 파일(템플릿·체크리스트·데이터)을 프로젝트 옆 `files/` 폴더에 두면 트리로 보이고, 컴파일 시 산출물 하위로 그대로 복사되고, 마크다운 에디터에 드래그하면 참조 경로로 치환된다. 별도 모델 계층은 없다 — files/의 단일 진실은 파일시스템 자체이고, 프로젝트 저장 경로(`_current_path`)가 유일한 배선 지점이다.

- **소스 위치:** 프로젝트 저장 파일 옆(`<dir>/my.daedalus.json` + `<dir>/files/A/c.txt`). 미저장 프로젝트(`_current_path`가 None)는 기능이 비활성화되어 안내만 표시한다.
- **산출 위치:** `<out>/files/A/c.txt` — 구조 그대로 복사.
- **참조 토큰(확정):** `${CLAUDE_PLUGIN_ROOT}/files/A/c.txt` — CC 공식 문서(plugins-reference §Environment variables)가 스킬/에이전트 본문 어디서나 치환됨을 명시한다(`$PLUGIN_DIR`는 표준에 없음). 경로 구분자는 POSIX(`/`)로 정규화한다.
- **FilePanel(view/panels/file_panel.py):** `QTreeView` + `QFileSystemModel`(root = `<project_dir>/files`). files/ 부재 시 안내 라벨 + "files 폴더 만들기" 버튼, 새로고침 버튼(루트 생성 직후 재바인딩용). `app.py`가 독 위젯 "파일"로 배치하고 `_sync_files_root`(저장/열기/새 프로젝트 등 `_current_path` 변경 지점마다 호출)로 `set_project_dir`을 갱신한다. 드래그 소스는 `QFileSystemModel` 기본 mime(file URL) 그대로 사용.
- **드롭 치환(widgets/markdown/editor.py + widgets/markdown/providers.py):** `MarkdownEditor.dragEnterEvent`/`dragMoveEvent`/`dropEvent`(editor.py)가 mime의 file URL 중 현재 files/ 루트 하위인 것만 `_file_ref_token`(providers.py)으로 변환해 드롭 지점에 삽입(복수 파일이면 줄바꿈 구분). files 밖 파일·비파일 mime(일반 텍스트 드래그 등)은 토큰 후보가 없으므로 그대로 `super()`로 흘러 기존 QPlainTextEdit 기본 드롭 동작을 보존한다. 루트 주입은 TagInput의 도구/블랙보드 후보와 동일한 provider 패턴 — `set_files_root_provider(callable)`/`get_files_root()`(providers.py의 모듈 전역이 단일 진실. app은 파사드 경로 `widgets.markdown_editor`에서 임포트해 `_sync_files_root`에서 `lambda: self._file_panel.files_root()`로 등록한다 — 전역 자체는 파사드로 복사되지 않으므로 반드시 이 함수들을 거쳐야 한다).
- **컴파일 복사(compiler/project_compiler.py):** `compile_project(project, out_dir, files_dir=None)` — files_dir가 실존 디렉토리면 게이트 통과 후(에러 시엔 복사도 스킵) `<out>/files/`로 정렬 순회 복사(`_copy_files_tree`, 결정적, 심볼릭 링크 미추종 — 디렉토리는 재귀 안 함·파일은 복사 안 함)한다. 기존 `<out>/files/`는 복사 전 삭제(out 전체가 아니라 files/만 — 스테일 잔존 방지). `CompileResult.copied_files`에 복사된 파일 경로 목록을 담는다. files_dir 생략(None) 시 기존 산출 파일/문자열이 완전히 불변이라 하위 호환이며, 헤드리스 `compile_project` 직접 호출부는 변경 없이 그대로 동작한다. `app._compile_project_dialog`가 `_current_path` 기준 `<project_dir>/files`를 전달.
- **dangling_file_ref 경고:** `_scan_dangling_file_refs`가 files_dir 지정 시(None이면 스캔 생략) 스킬/에이전트 body에서 `${CLAUDE_PLUGIN_ROOT}/files/<경로>` 패턴을 스캔해 files_dir에 실존하지 않는 참조를 `dangling_file_ref` 경고로 `CompileResult.warnings`에 추가한다(게이트 차단 아님). Validator가 아니라 컴파일러 소관 — 검증기는 파일시스템 무접근 순수성을 유지한다. `is_warning` 판정 일관성을 위해 rule 이름은 `validation/severity.py`의 `WARNING_RULES`에도 등록했다(실제 emit은 project_compiler.py — `tests/model/test_validation_severity.py`의 소스 introspection 완전성 테스트는 `_EXTERNALLY_EMITTED_RULES`로 이 예외를 명시).

### 스킬별 동봉 파일 (skill-files/) — WP-SF

스킬 하나에만 딸린 파일(참조 문서·스크립트)을 `<프로젝트 폴더>/skill-files/<스킬 이름>/`에 두면 컴파일 시
그 스킬의 **SKILL.md 옆으로** 복사되고, 본문은 `${CLAUDE_SKILL_DIR}/<상대경로>`로 참조한다. 근거(2026-08
공식 문서 확인): `${CLAUDE_SKILL_DIR}`는 CC 공식 변수(마켓플레이스/로컬 동일 동작 — `${ROOT}` 같은 타깃
중립화 불필요)이고, 스킬 디렉토리 보조 파일 + 상대 참조가 공식 progressive-disclosure 패턴이다.
**에이전트는 대상이 아니다** — 단일 .md라 전용 디렉토리·변수가 없다. 에이전트에 파일을 주려면 스킬에 실어
skills 프론트매터로 전달하거나(WP-AS 자동 합류 — declarative 전역/링크된 reference) 공용 `files/`를 쓴다.
WP-FR과 동일하게 모델 계층 없음 — 파일시스템이 단일 진실.

- **컴파일(project_compiler.py):** `compile_project(..., skill_files_dir=None)` — 하위 폴더명이 스킬 산출
  디렉토리명(=스킬 이름)과 일치할 때만 복사 계획(`kind="skill_file"`,
  `_iter_tree_files` 정렬 순회·링크 제외)에 합류한다. **계획 집합 합류가 곧 충돌 방어** — 'SKILL.md'라는
  이름의 동봉 파일은 기존 `compile_output_path_conflict` 게이트가 에러로 거부한다. LOCAL은 `.claude/skills/`
  밑으로 간다(cc_prefix 공유). 복사 결과는 `CompileResult.copied_files`. 생략 시 산출 완전 불변(하위 호환).
- **경고 3종:** `unknown_skill_files_dir`(스킬과 이름이 안 맞는 하위 폴더/루트 직속 파일 — rename 잔재 검출),
  `dangling_skill_file_ref`(본문 `${CLAUDE_SKILL_DIR}/…` 참조가 **그 스킬 자신의** 폴더에 없음 — 다른 스킬
  파일을 참조하는 실수도 잡힌다. 이상 2종은 컴파일러 emit, `_EXTERNALLY_EMITTED_RULES` 등록),
  `skill_dir_token_in_agent`(에이전트 본문의 이 토큰은 치환되지 않는다 — Validator 소관, 코드 표기 제외
  `_strip_markdown_code`, 빌드 타깃 무관).
- **UI(사용자 확정 — 전역과 스킬별은 동시에 떠 있는 별개 표면, 콤보 전환 아님):** 독의 `FilePanel`은
  공용 files/ 전용("플러그인 파일 (공용)"), 스킬별은 **스킬 에디터 우측 `SkillFilesPanel`**(전역 스킬만 —
  로컬은 산출 디렉토리명이 달라 제외). 공통 뼈대는 `_FileTreeBase`(트리 바인딩/안내/폴더 만들기/새로고침 +
  **"탐색기" 버튼** — `QDesktopServices.openUrl`로 OS 탐색기 열기, 루트 실존 시에만 활성).
  `SkillFilesPanel`은 에디터마다 생기므로 모듈 provider `set_project_dir_provider`/`get_project_dir`로
  프로젝트 폴더를 조회하고(component.name은 매번 읽어 rename 추적, showEvent마다 refresh),
  `FilePanel.files_root()`/`skill_files_root()`는 드롭 provider용으로 유지.
- **배치 개편(사용자 확정):** RegistryPanel의 종류별 섹션 세로 스택 → **QTabWidget 탭**(이모지 라벨 +
  전체 이름 툴팁). 파일 독은 레지스트리 **아래** 세로 스택(`splitDockWidget(..., Vertical)`) — 좌측 열이 좁아져
  에디터가 가로 공간을 가져간다. 탭 페이지는 비활성 시 항상 hidden이므로 노출 판정 테스트는 탭 가시성 기준.
- **드롭 치환:** `_skill_file_ref_token` — skill-files/<스킬>/ 하위 파일이면 `${CLAUDE_SKILL_DIR}/<스킬 폴더
  안 상대경로>`(첫 조각인 스킬 폴더명은 토큰에서 제거 — 런타임 SKILL_DIR가 그 폴더다). 루트 직속 파일은
  None(기본 드롭으로). `MarkdownEditor._token_for_path`가 files→skill-files 순으로 시도,
  `set_skill_files_root_provider`/`get_skill_files_root` provider는 files와 동일 패턴.
- **Save As 동반:** `_carry_files_dir`가 files/와 skill-files/ 둘 다 데려간다(목적지에 있으면 불가침).
- **후속(컴파일 분할):** 큰 본문의 섹션을 스킬 디렉토리 보조 파일로 산출하는 점진 공개 — WP-BO 아웃라인
  파서가 분할 지점, 이 WP가 파일 위치를 제공한다.

### 전략 패턴 (Guard / Action 공통)

```
EvaluationStrategy(ABC)        ExecutionStrategy(ABC)
├── LLMEvaluation              ├── LLMExecution
├── ToolEvaluation             ├── ToolExecution
├── MCPEvaluation              ├── MCPExecution
├── ExpressionEvaluation       └── CompositeExecution
└── CompositeEvaluation
```

## 구현 시 주의사항

### ABC + dataclass

`@dataclass class Foo(ABC):`만으로는 인스턴스화가 막히지 않는다.
반드시 `@abstractmethod`가 하나 이상 있어야 TypeError 발생.
이 프로젝트에서는 모든 ABC 클래스에 `@property @abstractmethod kind(self) -> str`를 추가한다.

### dataclass 다중 상속 필드 순서

`ProceduralSkill(Skill, WorkflowComponent)` 같은 다중 상속 dataclass에서
부모의 required 필드(default 없음)보다 앞에 default 필드가 오면 Python 에러가 난다.

**해결:** 자식 클래스에서 부모 필드를 `field(default=None)`으로 오버라이드하지 않는다.
`fsm`은 required로 유지하고, 테스트에서는 항상 keyword 인수로 전달한다.

MRO 기반 필드 순서 (ProceduralSkill 예시):
```
fsm (WorkflowComponent, required)
name, description (PluginComponent, required)
config (ProceduralSkill, default_factory)
```

### dataclass 동등성 정책

FSM 모델 클래스(State 계열·pseudo 4종·Transition·StateMachine·Region·Section)는
`@dataclass(eq=False)` — identity 동등성 + hashable. 서브클래스에 `@dataclass`를
다시 적용할 때 `eq=False`를 빠뜨리면 `__eq__` 재생성 + unhashable로 되돌아가므로 주의.

plugin 레이어(Skill, AgentDefinition 등)와 값 객체(EventDef, Variable 등)는 기본
dataclass(값 동등성, unhashable) 유지 — 컬렉션 멤버십에는 list/`id()` 사용.

### notify 채널 (structure / content)

`ProjectViewModel.notify(scope=...)`와 `add_listener(listener, scope=...)`는 두 채널을
구분한다. **structure**(기본값)는 상태/전이/참조의 추가·삭제·이동 등 구조 변경으로,
캔버스 `_rebuild`·레지스트리·트리·상태바 같은 무거운 리스너가 구독한다. **content**는
섹션 content/title·description·when_to_use 같은 텍스트 키스트로크로, structure 리스너를
깨우지 않아 타이핑마다 재구성이 도는 것을 막는다(채널은 서로 격리 — 교차 호출 없음).
에디터는 임의의 `Callable[[], None]`을 `on_notify_fn`으로 받으므로, `call_notify(fn, scope)`
헬퍼가 시그니처를 검사해 scope를 받는 콜백에만 채널을 전달한다(상위 호환). 텍스트 편집
패널은 위젯 재생성으로 편집 중 위젯이 파괴되지 않도록 in-place 동기화 원칙을 따른다.

## 컴파일러 (compiler/)

`compile_project(project, out_dir, files_dir=None) → CompileResult`. 순수 stdlib(Qt 무관, import 순수성 테스트로 고정).

**출력 구조 (CC 플러그인 규약, `project.build_target == MARKETPLACE` — 기본):**
- `<out>/.claude-plugin/plugin.json` — 플러그인 매니페스트 (MARKETPLACE에서 항상 생성 — 이게 없으면 산출 디렉토리를 CC 플러그인으로 설치할 수 없다)
- `<out>/skills/<skill-name>/SKILL.md` — 스킬 4종 전부 (Declarative/Reference도 SKILL.md)
- `<out>/agents/<agent-name>.md` — 에이전트

**`build_target == LOCAL`(WP-TG/WP-MW)일 때 — 컴파일이 곧 설치:** out_dir는 스테이징이 아니라 대상 **작업 폴더**다. `<out>/.claude/skills/`·`<out>/.claude/agents/`(CC가 실제로 읽는 위치), `<out>/files/`·`<out>/schemas/`·`<out>/hooks/scripts/`(본문의 `${CLAUDE_PROJECT_DIR}/…` 참조 대상), `<out>/.mcp.json`·`<out>/.claude/settings.local.json`(생성/병합). `plugin.json`·`hooks/hooks.json`·설치 스크립트는 만들지 않는다. 상세는 컴파일 정책 15번 항목 참조.

**컴파일 정책 (확정):**
1. **프론트매터**: 해당 kind 매트릭스에서 `emit==FRONTMATTER`인 필드만. 키는 `frontmatter_key`(kebab-case).
   FIXED는 `fixed_value` 강제 출력. `model==INHERIT`는 키 생략. OPTIONAL 값이 config 선언 기본값과 같으면 생략(잡음 제거).
   enum은 `.value`, bool은 `true`/`false`, 리스트는 flow-style `[a, b]`.
2. **when_to_use**: description과 합류 — `<description> Use when <when_to_use>` (description이 `.!?`로 끝나면 공백, 아니면 `. `로 연결).
3. **본문**: `body`(단일 마크다운 문자열)를 앞뒤 개행만 정리해 그대로 배출(공백뿐이면 블록 생략, WP-SB).
4. **ProceduralSkill FSM → 절차 단락**: initial_state부터 전이 BFS 순서로 번호 매긴 상태 목록(시작/종료 표지),
   각 SimpleState skill_ref는 "skill 이름 사용", CompositeState는 "에이전트 X에 위임", 전이별 트리거/가드 조건 + transfer_on 출력 이벤트.
   **상태 접근 선언(WP-BB):** State.reads/writes가 있으면 상태 항목 끝에 `(읽기: \`A.x\`, \`B\` / 쓰기: \`A.y\`)`
   접미사가 합류한다(reads/writes 각각 이름순 정렬, 선언 없으면 문구 생략 — 하위 호환).
5. (삭제됨 — WP-RF-1a) 위임(delegation) 노드 산출은 개념 퇴역과 함께 제거됐다. 위임 지시는 스킬 본문에 서술한다. (번호는 뒤 항목들의 교차 참조 보존을 위해 유지.)
6. **tool_shelf**: 참조 문서 단락으로만(실행 코드 생성은 Tier 2).
6-b. **다음 단계 (project.graph 기반)**: `compile_skill(skill, project=...)`이 `project.graph`에서 그 스킬 placement(skill_ref identity 일치)의 outgoing 전이를 모아 SKILL.md 본문 끝에 **"## 다음 단계"** 단락을 배출한다(버그 2 — 인보크/전이 문구 누락 해소). 형식: 스킬 타깃은 `- [<조건>] → \`<skill>\` 스킬을 인보크하라`, 에이전트 타깃은 `에이전트 \`X\`에게 위임하라` + **그 에이전트 placement의 outgoing을 한 단계 인라인**("위임 완료 후: [조건] → \`C\` 스킬을 인보크하라" — 에이전트는 별도 컨텍스트라 자기 .md에 호출자 지침을 담을 수 없으므로 호출자 스킬 쪽에 후속 지시를 둔다). 조건은 `_transition_condition`(트리거+가드) 재사용, 무가드·무트리거 전이는 "무조건". outgoing 0개면 단락 생략. **에이전트 .md에는 다음 단계 단락 없음**(스킬 + project 인수 있을 때만). EntryPoint outgoing(시작 스킬)은 v1에서 스킬별 단락에 영향 없음.
7. **에이전트**: `emit==FRONTMATTER`만 프론트매터, INVOCATION(max_turns/background/isolation)은 "호출 파라미터" 본문 단락,
   SETTINGS(hooks/mcp_servers)는 **MARKETPLACE 빌드에서만** "요구 환경" 언급으로 나간다. `config.tools`의 `mcp__<server>__` 접두에서
   추출한 서버 이름(WP-TM, 11번 항목과 동일 규칙)도 `mcp_servers` 선언과 합쳐(중복 제거·이름순) 같은 "MCP 서버 연결" 줄에 담는다 — 별도 단락을 추가하지 않는다.
   **LOCAL 빌드는 이 둘을 프론트매터로 실제 배출한다(WP-LA, 16번 항목)** — 그때는 "요구 환경" 단락을 내지 않는다(같은 사실을 두 번 말하는 데다 "설정 파일을 생성하지 않음" 문구가 거짓이 된다).
8. **컴파일 게이트**: `Validator.validate_project`의 에러(`is_warning=False`) 1건이라도 있으면 거부(파일 미생성, errors 반환). 경고는 통과(warnings 동봉).
   게이트 강화 2종(파일 쓰기 전 산출 계획 단계): ① 산출 이름이 되는 컴포넌트(스킬·에이전트) **및 프로젝트 이름**의 이름이
   `^[a-z0-9][a-z0-9-]*$` 불일치면 `compile_invalid_component_name` **에러로 승격** 거부 (F7 검증기에서는 경고 등급 유지 — 편집 중에는 경고가 맞다). 프로젝트 이름은 plugin.json의 `name`(플러그인 식별자)이 되므로 동일 규약을 적용한다.
   ② 전체 산출 경로 집합에 중복이 있으면 `compile_output_path_conflict` 에러로 거부 + 충돌 경로/원인 컴포넌트 보고 (조용한 덮어쓰기 방지).
9. **plugin.json 매니페스트**: `compile_plugin_manifest(project)`가 `project.name`/`description`/`version`으로 `.claude-plugin/plugin.json`을 무조건 생성한다. 키 순서 `name`→`description`(빈 문자열이면 키 생략)→`version`.
10. **블랙보드 사용 지침 단락**: 프로젝트 최상위 블랙보드에 `class_definitions`가 1개 이상이면, `ProceduralSkill`의 tool_shelf 단락 뒤·"다음 단계" 단락 앞, 그리고 에이전트 `.md` 본문 마지막에 `_blackboard_section(project, component)`이 "## 공유 상태 (블랙보드)" 단락(`state/<ClassName>.json` 파일 목록 + 읽기-수정-쓰기 규칙)을 배출한다. 정의가 0개면 단락 생략.
    **접근 선언 기반 구체화(WP-BB):** component(스킬/에이전트)가 주어지고 그 자체 FSM(재귀) + 프로젝트 그래프
    placement의 reads/writes 합집합(`_component_access_union`)이 비어있지 않으면, "이 스킬/에이전트가 읽는
    것/쓰는 것" 문구를 추가하고 파일 목록을 관련 클래스만으로 좁힌다. 합집합이 비면(또는 component 미지정)
    기존 전 클래스 일반 안내 그대로 — 하위 호환, 접근 선언 0개 프로젝트의 산출 문자열은 불변이다.
11. **요구 환경 자동 언급 (WP-TM)**: `_mcp_servers_from_tools(tools)`가 도구 문자열 목록에서 `mcp__<server>__` 접두의 서버 이름 집합을 추출한다(이름순 정렬 — 결정적). 스킬은 `skill.config.allowed_tools`를 스캔해 서버가 있으면(local 여부·project 인수 여부와 무관) "다음 단계" 단락 앞에 신규 "## 요구 환경" 단락(`_mcp_requirement_section_skill`)을 배출한다(없으면 단락 생략). 에이전트는 `config.tools`에서 추출한 서버를 기존 SETTINGS "요구 환경" 단락(`_settings_note_agent`, 7번 항목)의 `mcp_servers` 선언과 합쳐 하나의 "MCP 서버 연결" 줄로 병합한다(중복 없음).
12. **작업 재개 (WP-RS)** — 저장 단위는 **플러그인 FSM(프로젝트 그래프 배치)의 위치**다(스킬 내부 FSM 상태는 다루지 않음 — 사용자 확정 설계). 규약 파일 `state/__progress__.json`(`plugin`/`current`/`completed`/`note`/`prev`/`updated` — `prev`는 WP-IC에서 추가된 직전 출처 스킬 이름 필드).
    - **재개 프리앰블**: 프로젝트 그래프에 배치된 `ProceduralSkill`/`DeclarativeSkill`(미배치·에이전트 .md 제외)에 한해, `_resume_preamble_section`이 프론트매터 직후·본문 앞에 "## 작업 재개" 단락(현재 스킬 이름 삽입 + 파일 없을 때 생성 규칙, JSON 예시에 `"prev": ""` 포함)을 배출한다. Declarative 포함 이유: 배치되면 "다음 단계"를 받으므로 갱신 규칙이 빠지면 진행 사슬이 끊긴다. placement 판정은 "다음 단계"(6-b번 항목)와 동일한 `_graph_placements`(skill_ref identity) 로직을 공유한다.
    - **다음 단계 갱신 규칙**: 배치 스킬의 "다음 단계" 단락 끝에 `_PROGRESS_UPDATE_NOTE`(완료 시 `completed`/`current`/`note`/`updated` 갱신 + `prev`에 자신(이 스킬 이름)을 기록[WP-IC] + 에이전트 위임 전이는 2단 갱신: 위임 직전 에이전트 이름, 완료 후 후속 스킬로 — 이때도 `prev`는 위임한 스킬 이름)이 합류한다.
    - **터미널 배치**: **placement의 실제 outgoing 전이가 0개**인 배치는 "다음 단계" 대신 `_progress_terminal_section`이 "## 작업 완료" 단락(자신을 `completed`에 추가 + `current`를 `"done"`으로)을 배출한다. 판정은 "다음 단계 문구 생성 실패"가 아니다 — outgoing 타깃이 빈 상태(skill_ref=None)뿐이라 문구가 안 나와도 터미널이 아니며 이때는 아무 단락도 배출하지 않는다.
    - **TransferSkill**: **project에 placement가 1개 이상**일 때 본문 끝에 "## 진행 기록" 헤딩 + `_TRANSFER_PROGRESS_NOTE`(전이 중 note 기록 지시)를 배출한다(진행 파일이 존재하지 않는 프로젝트에서의 고아 지시 방지).
    - **SessionStart 훅 합성**: `PluginProject.emit_progress_hook: bool = True`(직렬화 왕복, 구버전 키 부재 시 기본 True)이고 프로젝트 그래프에 placement가 1개 이상이면, `compile_hooks_json`이 `hook_library`를 오염시키지 않고 컴파일 시점에 SessionStart 이벤트에 진행 상태 주입 커맨드(`cat state/__progress__.json 2>/dev/null || true`)를 합성해 합류시킨다(사용자 정의 SessionStart 훅 뒤에 이어붙어 공존). `emit_progress_hook=False`이거나 placement가 0개면 합성 훅 미배출. 토글은 프로젝트 속성 다이얼로그의 "세션 시작 시 진행 상태 자동 주입 (SessionStart 훅)" 체크박스. 합성 커맨드는 POSIX 셸 전제(`cat`/`||`) — 비POSIX 환경에서는 토글로 끄는 것이 대응책(훅 프리셋과 동일한 전제).
13. **진입 맥락 + 호출 계약 (WP-IC/WP-IP/WP-CT)**: 배치된 전역 `ProceduralSkill`/`DeclarativeSkill`에서 incoming 전이가 1개 이상이면, `_entry_context_section`이 "## 작업 재개" 프리앰블 뒤·본문 앞에 "## 진입 맥락" 단락을 배출한다("`state/__progress__.json`의 `prev`를 확인하고 아래에서 해당 출처 항목을 따르라" 도입 + 출처 이름순 항목["- `<출처>`에서 [조건]로 진입" + 출처의 transfer_on description 병기, 전이 스킬(TransferSkill) 지침 수행 문구·에이전트 출처의 "위임 완료 후" 문구 합류] — 포트 그룹 헤딩 없음, 그래프에서만 유도(WP-IP)). incoming 0개 배치·미배치·로컬은 산출 변화 없음. `compile_agent`의 "## 호출 계약"은 `_call_contract_section`이 프로젝트 그래프의 incoming 호출 전이에서 유도한다(WP-CT — 수동 카드 없음).
14. **files/ 복사 + dangling_file_ref 경고 (WP-FR)**: `files_dir`가 실존 디렉토리면(게이트 통과 시에만) `_copy_files_tree`가 `<out>/files/`로 정렬 순회 복사한다(결정적, 심볼릭 링크 미추종 — 디렉토리는 재귀 안 함·파일은 복사 안 함). 기존 `<out>/files/`는 복사 전 삭제(out 전체가 아니라 files/만). 복사된 파일 경로는 `CompileResult.copied_files`에 담긴다. `files_dir`가 주어지면(실존 여부 무관) `_scan_dangling_file_refs`가 스킬·에이전트 body에서 `${CLAUDE_PLUGIN_ROOT}/files/<경로>` 참조 토큰을 스캔해 files_dir에 실존하지 않으면 `dangling_file_ref` 경고를 `CompileResult.warnings`에 추가한다(게이트 차단 아님). `files_dir` 생략(None) 시 복사·스캔 모두 생략되어 기존 산출 파일/문자열이 완전히 불변(하위 호환).
15. **빌드 타깃 — LOCAL 빌드 (WP-TG)**: `project.build_target`(기본 `MARKETPLACE`)에 따라 `_plan_outputs`의 산출 계획이 갈린다.
    - **MARKETPLACE**(기본): 현행과 **바이트 동일** — 하위 호환 게이트(기존 산출 문자열/파일 전부 불변).
    - **LOCAL — 컴파일이 곧 설치 (WP-MW)**: out_dir가 대상 작업 폴더다. 스킬/에이전트는 `.claude/skills/`·`.claude/agents/`(CC가 실제로 읽는 위치)로 나가고, `plugin.json`과 이전의 `INSTALL.md`/`install.ps1`/`install.sh` 동봉은 폐기됐다(별도 설치 단계가 없다). `hooks/hooks.json` 파일도 만들지 않는다 — 훅은 `.claude/settings.local.json`의 `hooks` 섹션에 병합된다(훅 스크립트 파일은 양쪽 타깃 모두 `hooks/scripts/`로 — LOCAL 커맨드가 `${CLAUDE_PROJECT_DIR}/hooks/scripts/…`를 가리킨다). MCP 배선: `referenced_mcp_servers(project)`(스킬 allowed_tools ∪ 에이전트 tools/mcp_servers, 이름순) ∩ `project.mcp_server_defs` 정의를 `<out>/.mcp.json`의 `mcpServers`에 병합하고 그 이름을 `.claude/settings.local.json`의 `enabledMcpjsonServers`에 올린다. 정의 조회는 `project.mcp_server_defs` 우선 + `compile_project(..., extra_server_defs=)`(호출 환경 주입 — 앱이 `_known_server_defs()`로 자기 자신의 daedalus 서버를 넣는다. 서버 미기동이면 기본 포트) 폴백. 참조되지만 정의 없는 서버는 `missing_mcp_server_def` 경고, 깨진 기존 JSON은 건드리지 않고 `unmergeable_settings_json` 경고(수기 설정 보호). 병합은 추가/갱신만·동일 훅 그룹 중복 삽입 없음 — **재컴파일 멱등**. 병합 구현은 `compiler/wiring.py`의 `wire_workspace`가 단일 진실("Claude Code 실행" 메뉴와 공유). files/ 복사는 LOCAL에서 기존 `<out>/files/`를 **삭제하지 않고** 덮어쓰기만 한다(`_copy_files_tree(clear_first=False)` — 사용자 작업 폴더의 파일 삭제 위험 > 스테일 잔존). `${ROOT}` 확장·이름 규약 게이트·`schemas/schemas.json` 산출 조건은 기존 그대로.

16. **LOCAL 에이전트 프론트매터 — hooks / mcpServers (WP-LA)**: CC는 **보안상 플러그인 서브에이전트의
    `hooks`/`mcpServers`/`permissionMode` 프론트매터를 무시한다**(공식 sub-agents 문서 명시). 즉 이 셋은
    `.claude/agents/`로 반입되는 LOCAL 빌드에서만 실제로 동작하며, 그것이 로컬 타깃을 고르는 이유다.
    - `_local_settings_frontmatter_lines(agent, project)`가 **LOCAL일 때만** 프론트매터에 `hooks`/`mcpServers`를
      덧붙인다(`compile_agent`가 `_frontmatter_lines_agent` 뒤에 이어 붙임). `project`가 없으면 MARKETPLACE
      취급이라 기존 호출부 산출은 불변(하위 호환).
    - `hooks` 값은 **settings.json의 hooks와 동일한 3단 중첩 구조**(이벤트 → 그룹[matcher + hooks] → 커맨드
      엔트리)다. `_agent_hook_groups`가 `compile_hooks_json`과 같은 규칙으로 만든다(matcher는 Pre/PostToolUse
      전용, timeout은 있을 때만, 이벤트 키 순서 = `HookEvent` 선언 순서, 같은 이벤트 복수 훅 = 라이브러리 순서).
      라이브러리에 없는 이름은 조용히 빠진다(`dangling_hook_ref`가 따로 짚는다). flow-style로는 표현할 수 없어
      `_yaml_block_lines`(제한된 블록 YAML 렌더러 — dict/list/스칼라만, 스칼라 표기는 `_yaml_scalar` 재사용)를 쓴다.
    - `mcpServers`는 **이름 참조 리스트**다(`- github`). 목록은 `_agent_mcp_server_names` = `config.mcp_servers`
      선언 ∪ `config.tools`의 `mcp__<server>__` 추출(이름순) — "요구 환경" 단락과 같은 합집합 규칙이라 본문과
      프론트매터가 서로 다른 목록을 말하지 않는다. 인라인 서버 정의는 모델에 서버 설정 자체가 없어 범위 밖.
    - `permissionMode`는 매트릭스가 이미 프론트매터로 내보내므로 별도 처리하지 않는다. 대신 마켓플레이스에서
      무시된다는 사실은 `unsupported_agent_field_in_marketplace_build` 경고가 알린다(MCP는
      `mcp_agent_in_marketplace_build`가 이미 짚으므로 이 규칙은 hooks·permissionMode만 본다 — 경고 중복 방지).

출력은 결정적(같은 모델 → 같은 텍스트), LF 줄바꿈, UTF-8(BOM 없음). 텍스트 생성(`compile_skill`/`compile_agent`)은 파일시스템과 분리되어 문자열 단위 테스트 가능.

## 미구현 예정

- `compiler/` Tier 2: ToolExecution/ToolEvaluation 실행 래퍼(인자 이스케이프·shell 분기·success_condition), MCP 서버 실행 코드
- `hooks.json` / `.mcp.json` 설정 파일 생성 (WP-HOOK)
- CLI: 기존 Claude Code CLI 툴 연동 (플러그인 내 명시)
