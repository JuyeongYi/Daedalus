# Daedalus 개선 보고서 — 51건 확정 발견 종합

> 2026-06-11 멀티에이전트 감사(분석 7차원 → 적대적 검증 → 종합, 에이전트 64개). 56건 발견 중 51건 검증 통과, 5건 기각.

**기준:** 이 도구의 핵심 가치는 "에디터에서 설계한 FSM 모델 → SKILL.md / agent .md 컴파일"이다. 우선순위는 이 파이프라인의 실현을 앞당기는 순서로 매겼다. 51건을 중복 병합하여 16개 항목으로 정리했다.

**현재 상태 진단:** 모델 레이어는 견고하다(293개 테스트, 1.4초 통과). 그러나 ① 에디터에서 편집한 내용 상당수가 모델에 도달하지 못하고(write-back 부재, 에이전트 그래프 미동기화), ② 모델이 파일로 나갈 준비가 안 되어 있으며(직렬화·ID·프론트매터 키 매핑 부재), ③ Validator가 사용자에게 한 번도 보이지 않는다. 즉 "설계 → 모델 → 파일" 파이프라인의 세 연결 고리가 모두 끊어져 있다.

---

## 1순위: 지금 바로 (편집 결과가 모델에 남게 만들기 + 저비용 정합성 수정)

### 1-1. 에이전트 그래프의 상태/전이가 `agent.fsm`에 동기화되지 않음 — 탭 재오픈 시 설계 소실 ★최우선
- **근거:** `daedalus/view/commands/state_commands.py:26-30`(VM 리스트만 변경), `daedalus/view/canvas/scene.py:214-234`(Transition 생성 후 `fsm.transitions` 미추가), `daedalus/view/editors/agent_editor.py:166-203`(`_load_agent_fsm`은 모델에서만 복원). 대조: `exit_point_commands.py:24-31`은 `fsm.states`를 올바르게 변경.
- **증상:** 캔버스에 드롭한 스킬 노드와 전이가 모델에 없어 탭을 닫았다 열면 전부 사라진다. 역으로 `_migrate_fsm`이 모델에 직접 넣은 기본 전이를 UI에서 삭제해도 모델에 남아 재오픈 시 부활한다.
- **실행 방안:** `CreateStateCmd`/`DeleteStateCmd`/`CreateTransitionCmd`/`DeleteTransitionCmd`에 `fsm: StateMachine | None = None` 파라미터를 추가하고 execute/undo에서 `fsm.states`/`fsm.transitions`를 함께 변경. `FsmScene`에 `_target_fsm` 속성을 두어 `AgentFsmScene`만 동기화 활성화. 회귀 테스트: drop + 전이 생성 → `agent.fsm`에 존재 → 재로드 시 복원 확인.

### 1-2. SKILL_FIELD_MATRIX 프론트매터 패널에 저장(write-back) 로직 전무 + when_to_use 로드 버그
- **근거:** `daedalus/view/editors/skill_editor.py:114-143`(위젯 생성만, connect 없음; 저장 핸들러는 103/111행의 name/desc뿐), `:184`(`_get_current(config, None, field)` — component 자리에 None을 넘겨 when_to_use가 로드조차 안 됨, `:140`과 비대칭).
- **증상:** model/effort/allowed_tools/context/agent/shell 등 컴파일의 핵심 입력값을 UI에서 바꿔도 config에 반영되지 않고 패널 재생성 시 소실.
- **실행 방안:** `_get_current`의 attr_map(161-173행)을 모듈 상수로 추출해 로드/저장 공유. 위젯을 `self._field_widgets: dict[SkillField, QWidget]`에 보관하고 타입별 시그널(QComboBox→currentTextChanged, QCheckBox→toggled, TagInput→tags_changed) 연결, `_OptionalRow.toggled` 해제 시 None/[] 클리어. `_apply_value` 시그니처에 component 추가(184행 수정). enum 필드는 `Enum(value)` 역변환.

### 1-3. Undo/Redo가 `_active_stack`을 무시 — 에이전트 탭에서 Ctrl+Z가 보이지 않는 프로젝트 FSM을 되돌림
- **근거:** `daedalus/view/app.py:347-353`(`_undo`/`_redo`가 `self._project_vm.command_stack` 하드코딩), `:336-337`(`_update_undo_redo`도 동일), 대조 `:288-321`(`_on_tab_changed`는 `_active_stack`을 올바르게 교체 — 비대칭).
- **실행 방안:** 세 메서드를 `self._active_stack` 기준으로 변경하고, `_on_tab_changed`에서 `self._active_notify`(프로젝트면 `_project_vm.notify`, 에이전트면 `widget._graph_vm.notify`)를 함께 저장해 undo/redo 후 호출. `_script_panel.set_stack`도 비프로젝트 분기에서 갱신(app.py:301은 프로젝트 분기에만 있음).

### 1-4. `CompositeState.sub_machine = None`이 타입 선언과 모순 + Validator 크래시
- **근거:** `daedalus/model/fsm/state.py:56`(`sub_machine: StateMachine = None` — Region(:50)은 required인 것과 대조), `daedalus/model/validation.py:40, 73`(None 가드 없이 `.states` 접근 → `CompositeState(name='x')` 단독 검증 시 AttributeError 재현 확인됨).
- **실행 방안:** Python 3.12 프로젝트이므로 `sub_machine: StateMachine = field(kw_only=True)`로 변경 — 다중 상속 필드 순서 제약을 우회하면서 생성 시점에 필수 강제, 기존 테스트(전부 keyword 전달)와 호환. 에디터의 단계적 구성이 필요해지면 그때 `| None` + `composite_missing_sub_machine` 검증 규칙으로 전환.

### 1-5. 모델 dataclass `eq=False` 통일 — 값-동등성/identity/id() 3종 혼용 제거
- **근거:** `daedalus/model/validation.py:48`(`not in` — 값 비교), `:150`(`is`), `:172`(`id(ref)`); `state.py:16-17`(eq 기본값). 실해: 동명 복제 객체가 initial/final 검사를 통과(false negative), `exit_point_commands.py:28-29`의 `remove`/`index`가 `__eq__` 기반이라 엉뚱한 객체 제거 가능, CompositeState `==`는 sub_machine 깊은 비교로 순환 시 RecursionError 위험.
- **실행 방안:** State/Transition/StateMachine/Region/Section에 `@dataclass(eq=False)` 지정 — viewmodel 레이어(`state_vm.py:9` 등)가 이미 채택한 관례와 일치하고, `__hash__` 복원으로 CLAUDE.md의 "unhashable" 제약도 해소. 멤버십/remove/index는 identity로 자동 전환. 테스트 영향은 `test_machine.py:33`(빈 리스트 비교) 1곳뿐.

### 1-6. 문서·저장소 위생 일괄 정리 (30분 내 완료 가능)
- **근거:** CLAUDE.md:10 "테스트 102개"(실제 293개), CLAUDE.md/README "Validator 규칙 7개"(실제 9개 — `no_duplicate_skill_ref` validation.py:162, `transfer_on_not_empty` :186 누락), TransferSkill(skill.py:65)/ReferenceSkill(:82) 양 문서 미기재, 미추적 `planner.ps1`(타 계정 경로 하드코딩 + `--dangerously-skip-permissions`)/`test_claude.ps1`, 데드 코드 `decl_skill_editor.py`(참조 0건), `model/fsm/__init__.py`에 section.py 누락.
- **실행 방안:** 테스트 수는 숫자 자체를 제거("전체 테스트"), 규칙 표에 2행 추가, 4종 스킬 체계 반영. `test_claude.ps1` 삭제, `planner.ps1` 저장소 밖 이동 + `.gitignore`에 파일명 추가. `decl_skill_editor.py` 삭제. `fsm/__init__.py`에 `from daedalus.model.fsm.section import *` 추가.

---

## 2순위: 컴파일러 구현 전 (컴파일 입력의 무결성과 출력 규약 확보)

### 2-1. field_matrix의 model→view 의존 역전 + 프론트매터 키 매핑 신설 ★컴파일러 첫 선행 작업
- **근거:** `daedalus/model/plugin/field_matrix.py:7-17`(PyQt6 + view.widgets 직접 import — 재확인 완료), `:29`(`widget: type[QWidget]`); README.md:41 "순수 도메인 모델 (PyQt 무관)"과 모순. `enums.py:69-84`의 SkillField가 전부 snake_case인데 실제 SKILL.md 키는 kebab-case — 변환 코드가 저장소에 0건. 부수 불일치: `:111,128` `fixed_value="fork"`(raw 문자열, `SkillContext.FORK` enum 존재), `:40` MODEL default "sonnet" vs `config.py:22` `ModelType.INHERIT`.
- **실행 방안:** ① FieldRule에서 widget 제거(또는 `WidgetKind` enum으로 대체)하고 view 측 `FIELD_WIDGETS: dict[SkillField, type[QWidget]]`로 매핑 이전 — 위젯 선택이 스킬 kind와 무관하므로 1차원 dict로 충분. ② SkillField에 `frontmatter_key` property 추가: WHEN_TO_USE는 None(프론트매터 직출 금지 — description/본문 합류 정책 명문화), 나머지는 `value.replace("_", "-")`(14개 필드 전부 이 규칙으로 정확히 매핑됨을 확인). ③ fixed_value를 enum으로, MODEL default 단일 진실 결정. ④ PyQt6 차단 후 `daedalus.model` import를 검증하는 import-순수성 테스트 추가.

### 2-2. 안정 ID 부여 + 프로젝트 저장/로드 직렬화 계층
- **근거:** daedalus/ 전체에 to_dict/from_dict/asdict/json.dump 0건(grep 확인), `transition.py:25-26`(State 객체 직접 참조), `state.py:39`(skill_ref 객체 참조), `blackboard.py:36`(parent 참조), `agent.py:34`(graph_layout이 state.name 키 — 이름 변경 시 레이아웃 유실). `view/app.py`에 저장/열기 경로 자체가 없어 **에디터 작업물이 세션 종료 시 전부 소실**되는데 CLAUDE.md '미구현 예정'에도 없는 비인지 갭.
- **실행 방안:** ① State/Transition/Skill/AgentDefinition/Variable에 `id: str = field(default_factory=lambda: uuid4().hex)`(다중 상속 필드 순서 검토 후, 필요 시 kw_only). ② `model/serialize.py` 신설 — 소유 객체는 인라인, 참조(source/target, skill_ref, parent)는 ID 문자열로 평탄화, 역직렬화는 2-pass(생성→참조 해소). 기존 `kind` property를 다형 태그로 재활용. ③ graph_layout/_open_tabs/vm_map의 name 키를 id 키로 전환. ④ 라운드트립(참조 공유 보존) 테스트. 참고: 컴파일러 자체는 단방향 순회라 이 작업에 강결합되지 않으나, 저장 없는 설계 도구는 실사용이 불가능하므로 컴파일러 전 필수.

### 2-3. 프로젝트 수준 검증 + Validator 규칙 보강
- **근거:** `validation.py:21-23`(`validate(sm)`만 존재 — PluginProject 수준 규칙 0개). 누락 규칙: 이름 유일성·slug 형식(컴파일 시 디렉토리명 충돌), dangling 문자열 참조(`config.py:45` agent, `:69` skills, `project.py:13` skill_name), 전이 endpoint 멤버십(initial/final은 검사하면서 비대칭), 중복 state.name(`property_panel.py:61-64` rename이 무검사라 실발생 가능), 도달 불가능 상태, data_map key의 source.outputs 존재 검사(`:105`는 values만 검사 — 오타 key가 필수 input 누락을 은폐), trigger↔EventDef 이름 매칭(`scene.py:218`이 문자열 복사로만 결합, EventDef rename 시 고아 전이).
- **실행 방안:** `Validator.validate_project(project)` 신설 — `duplicate_component_name`, `invalid_component_name`(`^[a-z0-9][a-z0-9-]*$`), `dangling_reference`. 머신 수준에 `_check_transition_endpoints`, `_check_duplicate_state_names`, `_check_unreachable_states`(경고), `invalid_data_map_source`, `trigger_matches_source_event` 추가. ValidationError에 `subject: object`와 `path: tuple[str, ...]`을 추가해 중첩 위치 추적(현재 :38-43 재귀가 경로 미전달) 및 향후 노드 점프 지원.

### 2-4. Validator의 view 통합 — 사용자가 검증 결과를 볼 수 있게
- **근거:** daedalus/view/ 전체에서 Validator/validation 참조 0건(grep 확인). 9개 규칙이 테스트에서만 살아있고, 설계 도구인데 설계 시점 피드백이 전무.
- **실행 방안:** 단기 — 메뉴/툴바 '검증' 액션(F7)에서 전 FSM에 `Validator.validate()` 실행, 상태바 요약 + `ValidationPanel` 신설(source 클릭 시 노드 포커스). 중기 — 커맨드 실행/undo 후 디바운스 백그라운드 검증으로 노드 경고 배지. 컴파일러 게이트로 동일 Validator 재사용.

### 2-5. AGENT_FIELD_MATRIX 신설 + AgentConfig의 프론트매터/런타임 필드 분리
- **근거:** `config.py:64-79` — 프론트매터 성격(tools/permission_mode/skills/color)과 호출 시점 파라미터(max_turns/background/isolation/initial_prompt — 전부 소스 내 사용처 0건)가 혼재, `mcp_servers: list[dict[str, Any]]` 무스키마. `field_matrix.py:138-145`에 "agent" 키가 없어 AgentEditor 프론트매터 패널이 name/description만 렌더링(현재 동작 버그). `enums.py:30-36` PermissionMode.AUTO/DONT_ASK는 실제 CC 모드 집합과 미검증. 세션 문서(`docs/continue/2026-04-17-tool-architecture-session.md:173-179`)가 보류 과제로 자인.
- **실행 방안:** `FieldEmit` enum(FRONTMATTER/BODY/INVOCATION/SETTINGS)을 FieldRule에 추가하고 AGENT_FIELD_MATRIX 정의 — 에디터 빈 패널 버그 해소와 컴파일러의 배출 위치 기준 확보를 동시에. initial_prompt는 `AgentDefinition.sections`로 일원화(또는 INVOCATION으로 격리), mcp_servers는 최소 스키마 dataclass 또는 프리셋 이름 참조로 교체, PermissionMode 무효값 정리.

### 2-6. Tool Tier 1 구현 + 로드맵 4-8과 UserDefinedTool 단일화 결정
- **근거:** `strategy.py:32-40, 101-108`(ToolEvaluation/ToolExecution의 tool/command/success_condition 전부 `str = ""` — 컴파일 해석 규약 부재), `project.py:20-24`(tool_shelf 없음), 툴 관련 검증 규칙 0개. 로드맵 4-8(`feature-roadmap.md:193` "새로운 상태/스킬 유형 필요")과 툴 세션 결정 D(UserDefinedTool)가 동일 개념을 이중 모델링 — 두 문서가 상호 참조 없음.
- **실행 방안:** ① 단일화 결정 먼저: UserDefinedTool을 단일 진실로, 4-8은 `ToolExecution(tool=<name>)`을 on_entry로 갖는 SimpleState 프리셋(view 레이어)으로 재정의하고 로드맵 문구 수정. ② `model/plugin/tool.py`(Tool ABC + Builtin/MCP/UserDefined, `kind` 패턴 준수), `PluginProject.tool_shelf`, 세션 문서의 검증 규칙 6개 추가. ③ 컴파일러 v0 범위 문서에 "Tool/MCP 전략 컴파일은 Tier 2 선행 또는 v1 제외"를 명시적으로 기록.

### 2-7. 커맨드 시스템 빈틈 일괄 봉합 (저장/컴파일 전 데이터 정합 확보)
- **근거(병합 5건):** 참조 노드/링크 4종 조작이 커맨드 우회 + 이동 시 `_sync_refs_to_model` 미호출로 모델 좌표 스테일(`scene.py:525-571`, `ref_node_item.py:143-146`) — 저장 구현 즉시 표면화될 정합성 버그. AgentFsmScene transfer skill이 `_agent_skills.append`를 커맨드 밖에서 수행해 undo 시 고아 잔류(`scene.py:711-715` vs 베이스 `:462-468`). 노드+엣지 동시 삭제 시 중복 DeleteTransitionCmd → undo 시 전이 중복 복원(`scene.py:637-651`, `project_vm.py:58-59` 가드 없는 append). 다중 선택 드래그 스냅백(`node_item.py:387-390`, `scene.py:104-105`). 탭 닫기에서 `widget.close()`/`deleteLater()` 미호출로 정리 경로 데드 코드화(`app.py:277-286` — 재확인 완료, `agent_editor.py:302-305`).
- **실행 방안:** `commands/reference_commands.py` 신설(Create/Delete/Move Ref 커맨드, execute/undo에서 `_sync_refs_to_model` 동반). `AddSkillToListCmd`로 일반화해 베이스/에이전트 경로 통일. keyPressEvent를 단일 MacroCommand로 수집(노드 삭제에 딸린 전이는 엣지 커맨드에서 제외) + `add_transition_vm`에 중복 가드. `handle_node_moved`를 다중 선택 인지형으로(release 시점 vm이 old 좌표 보유 → selectedItems 순회로 MacroCommand). `_close_tab`에 `widget.close(); widget.deleteLater()` 추가.

### 2-8. 본문 표현 단일화: `content` vs `sections` 이중화 제거
- **근거:** `skill.py:53, 88-91`(DeclarativeSkill/ReferenceSkill만 content+sections 동시 보유 — Procedural/Transfer는 sections만). 모든 에디터는 Section.content만 편집하므로 content는 UI 도달 불가 사장 필드. 사용처는 `__main__.py:56`과 테스트 2곳뿐.
- **실행 방안:** content 필드 삭제, 호출부 3곳을 `sections=[Section(...)]`로 전환, Skill ABC docstring에 "본문의 단일 진실 공급원은 sections" 명시. 프리앰블 필요 시 컴파일러 출력 규칙으로 처리.

---

## 3순위: 장기 (표현력 확장과 구조 개선)

### 3-1. FSM 의미론 정밀화 — INTERNAL/custom_events 정본화, ChoiceState else, ParallelState join
- **근거:** `transition.py:16-26`(INTERNAL인데 source≠target 가능한 모순 인스턴스 허용, INTERNAL은 enum 테스트 외 사용처 0건인 데드 enum), `state.py:26`(custom_events와 의미 중복), `pseudo.py:8-14`(ChoiceState에 else/priority 표현 수단 없음 — 로드맵이 "if/else 분기 노드"로 명시한 것과 괴리), `strategy.py:69`(and/or만, not 부재), `state.py:63-70` + `event.py:30-31`(ParallelState 조인이 all 고정 — `policy.py:8-19`의 JoinStrategy와 미연결).
- **실행 방안:** ① `transition_type_consistency` 규칙(INTERNAL/SELF는 `source is target` 필수) + custom_events를 hook_fields(validation.py:122-126)에 추가. INTERNAL은 제거하거나 "guard 필요 시 INTERNAL, 단순 반응은 custom_events" 역할 분리를 문서화. ② "무가드 전이 = else" 관례 채택 + `choice_completeness` 규칙(outgoing 0개 에러, 무가드 2개 이상 에러, 0개 경고) — LLM이 해석하는 산출물의 결정성 확보. ③ JoinStrategy를 model/fsm으로 내리고(plugin에서 re-export) `ParallelState.join`/`join_count` 추가, CompletionEvent docstring 갱신.

### 3-2. Blackboard parent 배선 + DynamicClass→JSON Schema 매핑 규약
- **근거:** 프로덕션 코드에서 `parent=` 설정 0건(테스트만) — CLAUDE.md가 핵심 스코핑 메커니즘으로 설명하는 것과 괴리. `project.py:20-24`에 최상위 Blackboard 없음 → schemas.json의 소스가 결정 불가. FieldType의 INT/FLOAT/NUMBER 중복, 'schemas' 예약어 검증 부재.
- **실행 방안:** `PluginProject.blackboard` 추가, sub_machine 블랙보드 생성 시 parent 배선 지점을 viewmodel에 마련, 매핑 표(SET→array+uniqueItems 등)를 설계 문서에 명시, NUMBER deprecate 검토.

### 3-3. view 구조 개선 — scene.py 분해, 커맨드 경유 원칙, notify 채널 분리
- **근거:** scene.py 913줄에 동기화/2종 드래그/컨텍스트 메뉴(305-341 vs 770-805 약 45줄 복붙)/도메인 규칙/직렬화 혼재. 에디터 전반의 비커맨드 직접 변이(skill_editor.py:212-362, body_editor.py:251-256, component_editor.py:166-167)로 History goto와 실상태 괴리. textChanged가 키 입력마다 앱 전역 notify 유발 — 특히 _ContractCard는 타이핑 중 자기 위젯이 deleteLater되는 실사용 버그(`skill_editor.py:391` → `agent_editor.py:312-313`).
- **실행 방안:** 컨텍스트 메뉴 분기를 보호 메서드로 추출(템플릿 메서드 완성), `_make/_find_agent_call_section_cmds`를 Qt 무관 모듈로 이동해 단위 테스트, 텍스트 편집은 coalescing SetTextCommand + focusOut/디바운스 커밋, 구조 편집은 기존 커맨드 재사용, notify에 structure/content 채널 구분. _ContractCard refresh는 in-place 동기화로 즉시 수정.

### 3-4. 테스트 공백 해소
- **근거:** `tests/view/`에 canvas/, panels/ 부재 — FsmScene 직접 테스트 0건, app.py/panels 5종/edge·ref 아이템 미커버.
- **실행 방안:** 기존 qapp 픽스처로 headless 가능한 경로부터: `_rebuild` diff 동기화, `begin/end_transition_drag` 직접 호출, `_sync_input_ports` 정렬, 참조 동기화. 1·2순위 수정 항목마다 회귀 테스트를 동반 추가(undo 중복 복원, 탭 재오픈 복원, write-back 반영 등).

---

## 다음 한 걸음

**1-1(에이전트 그래프 → `agent.fsm` 모델 동기화)부터 착수하라.**

이유: 이 도구의 핵심 가치 사슬은 "캔버스 설계 → 모델 → 컴파일"인데, 현재 첫 번째 화살표가 끊어져 있다. 사용자가 캔버스에서 만든 상태와 전이가 모델 객체(`agent.fsm`)에 아예 존재하지 않으므로, 직렬화(2-2)를 만들어도 저장할 것이 없고 컴파일러(v0)를 만들어도 컴파일할 것이 없다. 즉 1-1은 2순위 전체의 선행 조건이다. 수정 범위도 명확하다 — ExitPoint 커맨드(`exit_point_commands.py:24-31`)라는 검증된 패턴이 같은 코드베이스에 이미 있어, 4개 커맨드에 `fsm` 파라미터를 추가하고 `FsmScene._target_fsm`을 배선하는 작업으로 한정되며 기존 프로젝트 레벨 동작(`_target_fsm=None`)은 그대로 유지된다. 1-3(Undo 스택)과 같은 파일군을 만지므로 묶어서 진행하면 효율적이고, 완료 시점부터 "에디터에서 설계한 것이 모델에 남는다"는 도구의 최소 성립 조건이 충족된다.
