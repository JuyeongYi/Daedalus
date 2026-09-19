# 외부 플러그인 컴포넌트 등록 — 역할 고정 (WP-EX, 2026-09-19)

## 0. 사용자 확정 결정 (2026-09-19)

1. **외부 플러그인 에이전트**는 프로젝트에 **fork 실행 기반** 또는 **그래프 노드** 둘 중 하나로
   등록한 뒤 **고정**한다(역할 전환 없음, 같은 source를 두 역할로 등록 불가).
2. **외부 플러그인 스킬**의 사용 경로는 하나다 — **프로젝트 fork 에이전트의 `skills:` 프론트매터**.
   (참조 노드·단계 감싸기·선언형 취급 없음.) 실측 근거: `docs/design/plugin-model.md` 실측 표
   "fork 에이전트 `skills:`의 외부 플러그인 스킬" 행(CC 2.1.278, 2026-09-19).
3. 등록 표면은 **레지스트리 도크의 탭**이되 **에이전트 탭과 스킬 탭을 나눈다**.
4. 빌드는 사용 선언(`project.external_plugins`)으로부터 MARKETPLACE `plugin.json dependencies` /
   LOCAL `settings.json enabledPlugins`를 낸다 — **이미 구현돼 있다**(`compiler/emit/manifest.py
   external_plugin_ids`, `compiler/units/install.py`). 등록이 선언과 어긋나지 않도록 **등록 시 그
   플러그인을 자동으로 사용 선언**한다(같은 undo 단위).

## 1. 현행 사실 (구현자는 아래 파일을 먼저 읽는다)

- 설계 문서: `docs/design/agents.md`(외부 플러그인 에이전트·카탈로그 절), `docs/design/plugin-model.md`
  (종류 표·능력 선언 표·매트릭스·fork 절), `docs/design/validation.md`, `docs/design/mcp-server.md`,
  `docs/MCP.md`, `docs/guide/02-registry.md`, `docs/guide/06-mcp.md`. `docs/backlog.md`는 미구현만.
- 종류 등록 지점은 `daedalus/model/plugin/kinds.py`의 `COMPONENT_CLASSES` 하나. 파생 표면(매트릭스·
  kind_ui·직렬화·MCP 어휘·팔레트)은 `tests/test_kind_registry_parity.py`·
  `tests/model/plugin/test_capability_surface.py::EXPECTED_DECLARATIONS`·
  `tests/model/plugin/test_registry_discovery.py`·`tests/test_kind_literals.py`(리터럴 래칫)·
  `tests/test_polymorphism_ratchet.py`가 고정한다. 새 종류는 이 테스트들이 요구하는 자리를 **전부** 채운다.
- `ExternalAgent`(`daedalus/model/plugin/agent.py`, kind `external_agent`): 그래프 노드, `OUTPUT_LOCATION=NONE`,
  `BODY_SOURCE=EXTERNAL`, config는 `ExternalAgentConfig`(`source`뿐, `ComponentConfig` 직속).
  `external_source`/`external_plugin_refs()`가 검증(`_check_external_sources`/`_check_external_plugins`,
  `naming.py`)에 합류한다.
- `ForkAgent`(kind `fork_agent`): `IS_FORK_BASE=True`, 산출 `agents/<이름>.md`.
- fork 스킬 `agent` 후보의 단일 진실: `daedalus/view/actions/fork_skill.fork_agent_choices` —
  내장(`config.BUILTIN_FORK_AGENTS`) → **사용 선언 플러그인의 에이전트 `플러그인:이름` 문자열**
  (`wrap_catalog.used_plugin_agents`) → 프로젝트 `IS_FORK_BASE` 에이전트. `validate_fork_agent`가
  편집기 피커·MCP `create_skill(fork_agent=)`·`set_component_field(agent)`에서 공용.
- fork 검증: `daedalus/model/validation/project_rules/fork.py::_check_fork_agents`
  (`fork_agent_missing`/`fork_agent_undeclared_plugin`/`fork_agent_wrong_kind`/`fork_model_overrides_agent`).
  `fork_project_agent(skill, project)`가 이름→프로젝트 에이전트.
- 컴파일 이름 해소: `daedalus/compiler/emit/common.agent_invocation_name`(fork 스킬 `agent:` 값 —
  프로젝트 에이전트면 타깃별 `이름`/`<프로젝트>:<이름>`, 그 외 문자열 그대로),
  `delegation_target_name`(노드 위임 — `external_source` 원문).
- 에이전트 `skills:` 산출: `daedalus/compiler/emit/agent_sections._agent_skills_list`
  (전역 선언형 자동 + 링크된 참조 스킬 + `config.skills` 순, 중복 제거). `config.skills`의 이름 실존 검사는
  `naming.py::_check_dangling_string_references`(`AgentConfigBase.name_refs(Bucket.SKILLS)`).
- 카탈로그: `daedalus/model/plugin/wrap_catalog.py` — `scan_catalog()`, `CataloguedPlugin(plugin_id, name,
  skills[CataloguedSkill(name, description, source="plugin@market:skill")], agents[CataloguedAgent(name,
  description, agent_type="plugin:name")], has_files, files_from, mcp_servers)`, `used_plugin_agents(project)`,
  `used_plugin_mcp_servers(project)`, `project_external_sources(project)`. GUI 창은
  `view/editors/wrap_catalog_dialog.py`(선언 토글 `set_plugin_used` — `SetAttrCmd(project, "external_plugins")`).
- 레지스트리 팔레트: `daedalus/view/panels/registry_panel.py`(229줄) — 섹션 키 = config kind, 탭 순서 =
  레지스트리 순서, 항목 = 프로젝트 컴포넌트. `view/kind_ui.KIND_UI` 한 행이 탭 라벨·아이콘·다이얼로그 제목.
- MCP: `mcp/tools/props.py`(`create_skill`/`create_agent` — 어휘 파생), `mcp/tools/fields.py`
  (`set_component_field` — `agent` 필드는 `validate_fork_agent`), `mcp/tools/external.py`
  (`list_external_plugins`/`set_external_plugins`/…).
- 직렬화: `model/serialize/deser_plugin.py`는 `spec_by_kind`/`spec_by_config_kind`로 종류를 고른다 —
  새 종류는 `SERIALIZED_FIELDS` 선언만으로 왕복해야 한다(`tests/model/test_serialize_component_kinds.py`).
- 골든: `tests/data/golden/corpus.py`(합성 코퍼스) — 산출이 바뀌면 같은 커밋에서 재생성.

## 2. WP-A — 외부 fork 에이전트 종류 (`ExternalForkAgent`)

**모델.** `agent.py`에 `ExternalForkAgent(Agent)` 추가: `KIND="external_fork_agent"`,
`CONFIG_CLS=ExternalForkAgentConfig`. config는 `ExternalAgentConfig`와 같이 `source`뿐이고 `KIND`만 다르다 —
"구체가 구체를 상속하지 않는다" 규칙에 따라 **공통 추상 `ExternalSourceConfig(ComponentConfig, ABC)`**를 두고
두 구체 config가 그것을 상속한다. 선언: `PLACEMENT=NONE`, `OUTPUT_LOCATION=NONE`, `BODY_SOURCE=EXTERNAL`,
`IS_FORK_BASE=True`, `REQUIRES_OUTPUT_PORTS=False`, `DELEGATION_TARGET`은 `Agent` 기본(True) 유지,
`body=""`(왕복 보존용). `external_source`/`external_plugin_refs()`는 `ExternalAgent`와 같은 구현 —
**복제 금지**: 두 클래스가 공유하는 믹스인 한 곳(`Agent` 기저에는 두지 않는다 — ForkAgent·AgentDefinition은
외부 정본이 없다)에 둔다. `COMPONENT_CLASSES`에 등록. `AGENT_FIELD_MATRIX["external_fork_agent"]` =
`external_agent` 표와 동일(`name`/`description`/`source`, 전부 `FieldEmit.NONE`).

**후보·검증.** `fork_agent_choices`: 내장 → 프로젝트 `IS_FORK_BASE` 에이전트(ForkAgent·ExternalForkAgent,
이름순; 외부는 설명에 "외부 플러그인 fork 에이전트 — <source>"). **`used_plugin_agents` 문자열 후보는
제거**(그 함수 자체는 WP-C 등록 표면이 쓰므로 남긴다). `validate_fork_agent`: 값이 `플러그인:이름`
형식인데 후보에 없으면 "외부 플러그인 에이전트는 먼저 fork 에이전트로 등록하세요(레지스트리 🔌 탭 /
`create_agent(kind="external_fork_agent", source=…)`)"로 거절. `_check_fork_agents`:
`fork_agent_undeclared_plugin` 규칙 **삭제**(외부 참조는 `ExternalForkAgent.external_plugin_refs()`를 통해
`undeclared_external_plugin`이 짚는다 — `severity.WARNING_RULES`·`docs/design/validation.md`·backlog
"미선언 등급 비대칭" 항목을 함께 정리), `fork_agent_missing` 메시지의 "사용 선언한 외부 플러그인
에이전트(플러그인:이름)" 문구를 "등록한 외부 fork 에이전트"로. 새 규칙 **에러** `external_source_role_conflict`:
같은 `external_source`(원문 정확 일치)를 가진 컴포넌트가 2개 이상이면(ExternalAgent×2든 종류 혼합이든)
전부에 에러 — "같은 외부 에이전트를 두 역할로/두 번 등록했다. 하나만 남기라". `unused_fork_agent` 경고는
ExternalForkAgent에도 적용(IS_FORK_BASE 기준이면 자동 — 확인).

**컴파일.** `agent_invocation_name`: `delegated_agent_name()`이 프로젝트 에이전트를 가리키고 그 에이전트의
`external_source`가 `None`이 아니면 **source 원문**을 돌려준다(타깃 무관 — CC는 `플러그인:이름` 정확
일치). source가 비었거나 형식이 깨졌으면 `general-purpose`로 떨어뜨리지 않는다 — 경고
`external_source_missing`이 이미 짚으므로 fork 프론트매터의 `agent:` 줄은 **생략**하고(원문 `""`을 내지
않는다) 테스트로 고정. ExternalForkAgent는 `OUTPUT_LOCATION=NONE`이라 emitter·미리보기·계획에서 자동 제외
(`test_emitters_are_exactly_the_kinds_that_emit_a_file` 등 파생 테스트가 확인). fork 스킬 산출의
"## Report"/위임 산문의 실행 기반 이름은 `agent_invocation_name`을 쓰므로 자동.

**GUI.** `kind_ui.KIND_UI`에 행: `icon="🔌"`, `section_label="🔌 EXTERNAL FORK AGENTS"`, `tab_label="🔌🧩"`,
`node_style=None`, `dialog_title="새 External Fork Agent"`, `editor_factory=_agent_editor`, `tab_prefix="🔌🧩 "`.
(WP-C가 탭을 재편하므로 여기서는 파생 그대로.) 에이전트 편집기는 ExternalAgent와 같이 `_ExternalSourcePanel`
+ 매트릭스 폼(source) — 포트 패널 없음, "🍴 사용하는 fork 스킬" 읽기 전용 패널은 `IS_FORK_BASE` 게이트라
자동. `set_transfer_on`/호출 포트 MCP 도구는 배치 불가 종류를 이미 거절한다 — 테스트로 확인.

**MCP.** `create_agent(kind="external_fork_agent")`는 어휘 파생으로 자동 — **`source` 인자를 `create_agent`에
추가**(`external_agent`·`external_fork_agent`에만 유효, 그 외 종류에 주면 거절; `create_skill(fork_agent=)`의
종류별 인자 거절 선례). `get_component`의 `used_by_fork_skills`는 `IS_FORK_BASE` 기준이면 자동.
`list_component_fields`는 매트릭스 파생.

**문서.** `agents.md`(에이전트 종류를 4종으로, 외부 절에 fork 역할 추가, "역할 고정" 결정 기록),
`plugin-model.md`(종류 표·능력 선언 표·매트릭스 3종→4종·fork 후보 "세 종류" → "내장 + 프로젝트 fork 에이전트
(자체·외부)"), `validation.md`(규칙 표), `mcp-server.md`/`docs/MCP.md`(`create_agent` source 인자),
`docs/guide/02-registry.md`·`06-mcp.md`(후보 문구), `docs/backlog.md`(해소 항목 삭제·잔여 기록).

**테스트.** 위 파생 테스트 전수 + 새 테스트: 종류 선언·직렬화 왕복·후보 목록·`validate_fork_agent` 거절
문구·`external_source_role_conflict`·`agent_invocation_name` 해소·MCP `create_agent(source=)`·`set_component_
field(agent)`가 등록된 외부 fork 에이전트 이름을 받는다·골든 코퍼스에 외부 fork 에이전트를 쓰는 fork 스킬 1건.

## 3. WP-B — 외부 플러그인 스킬을 fork 에이전트 `skills:`로

**참조 형식.** `config.skills` 항목이 `플러그인:스킬`(콜론 포함, `@마켓` 없음 — 실측상 CC가 찾는 이름) 이면
**외부 스킬 참조**다. 판정 함수 하나: `model/plugin/config.is_external_skill_ref(name) -> bool`(콜론 유무).
`AgentConfigBase.name_refs(Bucket.SKILLS)`는 **프로젝트 스킬 참조만** 돌려주도록 외부 참조를 제외한다(그래야
`dangling_string_reference`가 오탐하지 않고 `rename_ref`가 건드리지 않는다). `AgentConfigBase.external_
plugin_refs()`(새 메서드 — 컴포넌트 `external_plugin_refs()`가 config의 것을 합친다: `AgentDefinition`·
`ForkAgent`) → 각 외부 스킬 참조의 플러그인 부분(**bare 이름**)을 돌려준다. `_check_external_plugins`의
매칭은 설치 식별자 정확 일치(`alpha@mkt` ≠ `alpha`)라, bare 이름 참조가 `alpha@mkt` 선언과 맞도록 **선언
쪽을 `partition("@")[0]`로도 비교**한다(fork.py의 `declared` 계산 선례). 선언 없으면
`undeclared_external_plugin` 경고, 선언했는데 아무도 안 쓰면 `unused_external_plugin`(기존).

**산출.** `_agent_skills_list`는 이름을 그대로 내므로 변경 없음 — `플러그인:스킬` 그대로 나간다(골든 1건 추가).
ExternalAgent/ExternalForkAgent는 `skills` 필드가 없다(산출 파일 없음) — 변경 없음.

**GUI.** 에이전트 편집기 `skills` TagInput 후보 제공자(`tag_input`에 `set_skill_candidate_provider`/
`get_skill_candidates` 신설, `app.set_project`에서 등록): 프로젝트 스킬 이름 + **사용 선언한 플러그인의
스킬 `플러그인:스킬`**(단일 진실 `wrap_catalog.used_plugin_skill_refs(project) -> list[str]` — `used_plugin_
agents`와 같은 선언 판정, `CataloguedSkill.source`의 `@마켓`을 뗀 형식. `CataloguedSkill`에 `skill_ref`
property로 그 이름을 둔다). 현재 SKILLS TagInput이 후보 없이 자유 입력이면 후보 연결만 더한다
(`frontmatter_panel._wire_tool_candidates` 선례).

**MCP.** `set_component_field(name, "skills", [...])`가 외부 참조를 받는다 — 선언 안 된 플러그인의 스킬이면
**거절하지 말고** 받되 응답에 `warning: undeclared plugin …`을 싣는다(검증이 짚는다). `list_external_plugins`의
스킬 행에 `skill_ref`(fork 에이전트 `skills`에 넣을 이름)와 `used_by`(그 참조를 가진 에이전트 이름 목록)를
싣는다(패리티: 쓸 수 있는 값은 읽을 수 있어야 한다).

**문서.** `agents.md`("외부 플러그인 스킬 — 사용 경로는 하나" 절, 결정·실측 참조), `plugin-model.md`(실측 표
행은 이미 있음 — 링크만), `validation.md`, `mcp-server.md`/`MCP.md`, `guide/02-registry.md`의 "다른
플러그인의 스킬을 참고 자료로 쓰기" 행을 이 경로로 교체, `backlog.md`.

**테스트.** `name_refs` 제외·`external_plugin_refs` 합류·경고 2종·산출 그대로·후보 제공자·MCP 응답 필드.

## 4. WP-C — 레지스트리 등록 표면 (WP-A·B 머지 후)

- 레지스트리 도크에 **탭 2개**: `🔌 EXTERNAL AGENTS`(ExternalAgent + ExternalForkAgent 두 종류를 **한 탭**에 —
  `KindUI`에 `section_group: str | None` 추가, 같은 그룹은 한 섹션. 파생 테스트 갱신) 와
  `🧷 EXTERNAL SKILLS`(컴포넌트 종류가 아닌 **카탈로그 항목** 섹션).
- 🔌 탭 내용: 위 = 등록된 컴포넌트(기존 항목 — 노드 종류는 드래그 가능), 아래 = **사용 선언한 플러그인의
  미등록 에이전트**(`used_plugin_agents` − `project_external_sources`) 회색 항목, 우클릭/버튼
  "그래프 노드로 등록" · "fork 에이전트로 등록" → `create_and_place`와 같은 커맨드 경로로 컴포넌트 생성
  (이름 기본값 = 에이전트 이름, 충돌 시 `<플러그인>-<이름>`), **플러그인이 미선언이면 같은 MacroCommand 안에서
  `external_plugins`에 추가**. "+" 버튼은 카탈로그 창을 연다.
- 🧷 탭 내용: 사용 선언한 플러그인의 스킬 `플러그인:스킬` 목록, 각 항목에 사용 중인 fork 에이전트 수/이름
  (✔), 우클릭 "fork 에이전트 skills에 추가 ▸ <프로젝트 fork 에이전트들>" → `SetAttrCmd(config, "skills",
  새 리스트)`. "+"는 카탈로그 창.
- 갱신: `external_plugins`·컴포넌트 변경(structure notify)에 다시 그린다.
- MCP 패리티: `list_external_plugins`가 에이전트 행에 `registered_as: "external_agent"|"external_fork_agent"|
  null`을 싣는다. 등록 도구는 `create_agent(kind, source)`로 충분.
- 문서: `editor.md`/`guide/02-registry.md` 갱신, `agents.md` 카탈로그 절.

## 5. 공통 규약

- `python -m pytest tests/ -q`(pytest 직접 실행 불가). 시작·끝에 전체 스위트 통과. 계획 문서만 쓰고 멈추지
  말고 끝까지 구현. Pyright 스테일 경고는 무시하고 런타임으로 검증.
- 코드 위생: ~800줄 초과 파일에 기능을 더하면 먼저 쪼갠다(1,200줄 상한 테스트). 판정 실체는 한 곳(원칙 1),
  MCP 패리티(원칙 2), 편집은 커맨드 경유(원칙 3), 조용한 실패 금지(원칙 5), 퇴역 개념 잔재 금지(원칙 7).
- 문서: `docs/design/`은 구현된 사실만, 미구현은 `docs/backlog.md`. 기능을 바꾼 같은 커밋에서 문서 갱신.
- **`project/daedalus_cc_plugin/`(도그푸드 파일)은 건드리지 않는다** — 사용자가 GUI에서 편집 중이다.
  실행 중인 Daedalus 앱·MCP 서버도 건드리지 않는다.
- 커밋: 한국어, WP 단위, 끝에
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` /
  `Claude-Session: https://claude.ai/code/session_01Rc2KHE3Vg6mDkkvLaKNpW4`. **push 금지.**
- 임시 파일은 스크래치패드에만.
