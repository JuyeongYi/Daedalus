# 앱 내장 MCP 서버 — AI와 함께 편집하기

Daedalus는 GUI를 켜면 MCP 서버를 함께 띄운다. **조회용 API가 아니다** — 사람이 캔버스에서 작업하는 중에 Claude Code가 같은 프로젝트를 함께 만지는 통로다.

거의 모든 기능이 MCP로 노출돼 있어(도구 **86종**), 실제로는 "도구를 호출한다"기보다 **옆자리에 앉은 사람과 같은 파일을 놓고 작업하는 감각**에 가깝다. Claude가 노드를 만들면 화면에 즉시 나타나고, 사용자가 `Ctrl+Z`를 누르면 그 편집이 되돌아간다.

## 왜 그렇게 느껴지는가

세 가지가 그 감각을 만든다.

**① Claude가 사용자의 화면을 안다.**

- `get_selection` — 사용자가 지금 무엇을 선택하고 있는지. 사용자가 "이거 고쳐줘"라고 할 때 그 "이거"를 가리킨다.
- `get_history` — 사용자가 방금 한 편집.
- `focus_node` / `select_nodes` — 말로 "왼쪽 아래 노드요"라고 설명하는 대신 **그것을 선택해 보인다**. 선택은 편집이 아니라 undo에 쌓이지 않는다.

**② 편집이 한 스택을 공유한다.**

MCP 편집은 GUI 편집과 **같은 커맨드 스택**을 거친다. 그래서 사용자가 Ctrl+Z 한 번으로 Claude의 작업을 되돌릴 수 있고, 히스토리 패널에 사람 편집과 같은 형식으로 남는다. "AI가 뭘 했는지 모르겠다"가 구조적으로 생기지 않는다.

**③ 본문 편집도 에디터 안으로 들어간다.**

`set_component_body` / `set_body_section`은 모델에 값을 대입하는 것이 아니라 그 컴포넌트의 `QTextDocument`에 적용된다. 에디터가 열려 있으면 타이핑하듯 반영되고, 본문 전용 undo 스택에 정확히 올라간다.

## 연결

GUI가 켜지면 `127.0.0.1`에 Streamable HTTP로 뜬다.

- 기본 포트 **8787**, 점유돼 있으면 위로 20개까지 훑어 빈 포트를 쓴다
- 실제 포트·주소·열려 있는 프로젝트 경로는 `~/.daedalus/mcp-endpoint.json`에 기록된다
- 도구 메뉴 → **"MCP 서버 정보..."** 가 접속 주소와 `.mcp.json` 스니펫을 보여 준다(복사 버튼 포함)

```json
{
  "mcpServers": {
    "daedalus": { "type": "http", "url": "http://127.0.0.1:8787/mcp" }
  }
}
```

도구 메뉴 → **"Claude Code 실행"** 은 프로젝트 폴더에서 새 콘솔로 `claude`를 띄우면서 위 배선을 자동으로 넣어 준다.

**stdio가 아니라 HTTP인 이유:** stdio는 클라이언트가 서버 프로세스를 실행하는 모델이라 이미 떠 있는 GUI에 나중에 붙을 수 없다. HTTP면 앱이 먼저 켜져 서버를 열어 두고 Claude Code가 원할 때 접속하는 순서가 그대로 성립한다.

여러 창을 띄우면 `.mcp.json`이 고정 포트를 가리키므로 **먼저 켜진 인스턴스**가 협업 대상이 된다. 인스턴스마다 다른 세션을 붙이려면 `daedalus --mcp-port <포트>`로 고정한다(그 포트가 점유돼 있으면 물러나지 않고 실패한다 — 지정한 의미를 지키기 위해서다).

## 도구 지도 (87종)

### 조회 (19)

`get_project` · `get_selection` · `focus_node` · `select_nodes` · `get_component` · `get_body_outline` · `get_body_section` · `get_history` · `validate_project` · `compile_preview` · `compile_check` · `get_hook` · `list_hook_events` · `list_hook_presets` · `hook_frontmatter_preview` · `list_component_fields` · `list_tool_candidates` · `list_recent_projects` · `list_project_templates`

조회는 **개요 ↔ 전문**으로 나뉜다. 목록을 주는 도구는 각 항목을 축약본으로 싣고, 전문은 그 하나를 지목하는 도구가 준다 — `get_body_outline` ↔ `get_body_section`이 원형이고, `get_project`의 훅 개요 ↔ `get_hook`(핸들러 스키마 + 스크립트 본문)이 같은 논리다. 프로젝트를 볼 때마다 셸 스크립트 전문을 통째로 실어 나르지 않기 위해서다.

`get_project(sections=[...])`로 구획만(meta / components / canvas / blackboard / hooks) 받을 수 있고, `validate_project(severity=, component=)`로 걸러 받을 수 있다.

### 편집 — 캔버스와 모델 (41)

| 묶음 | 도구 |
|------|------|
| 컴포넌트 | `create_skill` `create_agent` `convert_skill` `rename_component` `delete_component` `set_component_description` `set_component_when_to_use` `set_component_field` `set_entry_preset` |
| 캔버스 구조 | `place_component` `create_state` `move_state` `rename_state` `delete_state` `connect_states` `disconnect_states` `set_transition` `set_transition_waypoints` |
| 포트·분기 | `set_transfer_on` `add_agent_call` `remove_agent_call` `set_agent_calls` |
| 참조 노드 | `place_reference` `link_reference` `unlink_reference` `unplace_reference` `move_reference` |
| 블랙보드 | `create_blackboard_class` `update_blackboard_class` `delete_blackboard_class` `set_blackboard_fields` `set_state_access` |
| 훅 | `create_hook` `update_hook` `delete_hook` `set_component_hooks` `copy_global_hook` |
| 본문 | `set_component_body` `set_body_section` |
| 프로젝트 | `set_project_properties` `set_mcp_server_def` |

**전부 undo 가능하다.**

### 작업 폴더 문서·설정 (10)

`list_workspace_docs` · `get_workspace_doc` · `set_claude_md` · `create_rule` · `set_rule_body` · `set_rule_paths` · `rename_rule` · `delete_rule` · `get_workspace_settings` · `set_workspace_settings`

LOCAL 빌드가 설치 대상 작업 폴더에 남기는 `.claude/CLAUDE.md` 구역과 `.claude/rules/*.md`, 그리고 `.claude/settings*.json`에 베이크할 설정이다.

### 외부 플러그인 카탈로그 (8)

`list_wrappable_skills` · `fetch_plugin_skills` · `list_marketplace_folders` · `add_marketplace_folder` · `remove_marketplace_folder` · `set_external_plugins` · `set_wrapped_usage` · `set_wrapped_enabled`

다른 플러그인의 스킬을 워크플로 단계로 감쌀 때 쓴다. **`fetch_plugin_skills`만 인터넷에 나간다** — 사용자가 그 플러그인을 지목했을 때만이고, 카탈로그를 열거나 새로고침하는 것만으로는 절대 받지 않는다.

### 세션 (7)

`save_project` · `open_project` · `new_project` · `import_package` · `export_package` · `save_as_template` · `delete_user_template`

### undo 스택 (2)

`undo` · `redo`

## 함께 쓸 때의 관례

**작업 전에 사용자가 뭘 보고 있는지 확인한다.** `get_selection`이 그 자리다. 이것 하나로 "어느 노드요?"라는 왕복이 사라진다.

**긴 본문은 통째로 주고받지 않는다.** `get_body_outline`으로 구조만 보고 `get_body_section` / `set_body_section`으로 필요한 섹션만 만진다.

**검증은 두 층이다.** `validate_project`는 모델 검증만 본다. 파일 참조·MCP 서버 정의·작업 폴더 병합 같은 **컴파일러 경고**는 `compile_check`(파일을 하나도 쓰지 않는 예행)로만 나온다. 둘 다 봐야 컴파일이 통과할지 알 수 있다.

**구조만 만들면 분기가 표현되지 않는다.** 노드와 선을 그어도 갈래는 생기지 않는다 — 여러 갈래로 나가는 노드는 `set_transfer_on`으로 갈래를 선언하고 각 전이에 trigger를 물려야 캔버스 포트가 갈라지고 라벨이 보인다. 에이전트로 가는 전이는 `add_agent_call`로 만든 호출 포트에서만 나갈 수 있다(캔버스와 같은 규칙이다 — 같은 조작이 경로에 따라 다른 결과를 내면 안 된다).

**프로젝트의 단위는 폴더다.** `open_project`에는 폴더 경로를 준다(구버전 `<이름>.daedalus.json` 파일도 열린다). 경로는 `list_recent_projects`로 찾는다.

## undo 대상과 비대상

| | |
|---|---|
| **undo 된다** | 캔버스·모델 편집 전부, 본문(전용 스택), 작업 폴더 문서 본문 |
| **undo 안 된다** | 세션(저장·열기·패키지 — 파일 쓰기), 선택(`focus_node`/`select_nodes`), 홈 설정 파일을 만지는 것(마켓플레이스 폴더 등록, 사용자 템플릿 저장·삭제) |

**여는 절차 안에 저장이 있다.** `open_project` / `new_project` / `import_package` / `export_package`는 현재 프로젝트를 **먼저 저장한 뒤** 진행하고, 저장할 수 없으면 진행하지 않는다 — 편집 중인 내용은 메모리에만 있어 여는 순간 사라지기 때문이다. 한 번도 저장한 적 없으면 경로를 받아야 하고, 버리려면 `save_current=False`를 명시해야 한다.

## 패리티 원칙

**GUI에서 가능한 모든 편집·조회는 MCP로도 가능해야 한다.** 새 GUI 기능을 넣을 때 대응 MCP 도구(또는 기존 도구의 파라미터)를 같은 작업에서 함께 만든다 — 나중에 채우는 갭이 아니라 기능의 완성 조건이다.

같은 조작이 표면에 따라 다른 결과를 내지 않는 것도 같은 원칙이다. GUI 버튼과 MCP 도구는 대개 `view/actions/`의 **같은 함수**를 부른다.

## 한계와 함정

- **앱이 떠 있어야 한다.** 서버는 GUI의 일부다. 파일만 놓고 헤드리스로 편집하는 경로는 없다.
- **메인 스레드로 마샬링한다.** uvicorn은 데몬 스레드에서 돌고 도구 핸들러는 Qt 메인 스레드로 넘어가 실행된다. 모달 다이얼로그가 떠 있으면 루프가 막혀 기본 15초 뒤 `TimeoutError`가 난다.
- **바인딩은 항상 `127.0.0.1`이다.** 로컬 전용이라 TLS를 얹지 않는다.
- **편집 결과는 저장 전까지 메모리에만 있다.** 앱을 그냥 닫으면 사라진다(닫을 때 확인 다이얼로그가 뜬다). 중요한 작업 뒤에는 `save_project`를 부른다.

---

설계 근거·결정 이력은 [`../CLAUDE.md`](../CLAUDE.md)의 "앱 내장 MCP 서버 (WP-MCP)" 절이 정본이다.
