# MCP 설명

Daedalus를 켜면 MCP 서버가 같이 뜹니다. 이 서버 덕분에 Claude Code가 **지금 열려 있는 프로젝트를 사람과 함께 편집**할 수 있습니다.

조회만 하는 API가 아닙니다. 옆자리 동료와 한 화면을 같이 보며 작업한다고 생각하면 됩니다.

- Claude가 노드를 만들면 캔버스에 **바로** 나타납니다.
- Claude의 편집은 **내 undo 스택**에 들어갑니다. `Ctrl+Z` 한 번이면 되돌아가고, 히스토리에도 내 편집과 똑같이 남습니다.
- Claude는 **내가 지금 뭘 선택하고 있는지** 알 수 있습니다. "이거 고쳐줘"라고만 해도 됩니다.

> 스킬·에이전트·캔버스 같은 기본 개념은 [개념 설명](01-concept.md)을 먼저 보세요.

---

## 1. 켜고 연결하기

### 서버는 앱이 알아서 띄웁니다

앱을 실행하면 서버가 자동으로 시작됩니다. 따로 할 일은 없습니다.

| 항목 | 값 |
|------|-----|
| 주소 | `http://127.0.0.1:8787/mcp` (내 컴퓨터에서만 접속 가능) |
| 방식 | Streamable HTTP |
| 기본 포트 | `8787`. 사용 중이면 위로 20개(8787~8806)까지 훑어 빈 포트를 씁니다 |
| 실제 접속 정보 기록 | `~/.daedalus/mcp-endpoint.json` (포트·주소·열린 프로젝트 경로) |

상태 표시줄에 `MCP 서버 대기 중 — http://127.0.0.1:8787/mcp` 같은 문구가 보이면 준비된 것입니다.

명령줄 옵션:

```bash
daedalus --mcp-port 8790   # 이 포트만 씁니다. 사용 중이면 다른 포트로 물러나지 않고 실패합니다
daedalus --no-mcp          # 서버를 띄우지 않습니다
```

### Claude Code를 붙이는 두 가지 방법

**방법 A — 메뉴 한 번 (가장 쉬움)**

도구 메뉴 → **"Claude Code 실행"**. 프로젝트 폴더에서 새 콘솔로 `claude`를 띄우고, 그 폴더의 `.mcp.json`과 `.claude/settings.local.json`에 daedalus 서버 항목을 넣어 줍니다. 기존 항목은 그대로 두고 추가만 합니다.

- 프로젝트를 **한 번은 저장**해야 합니다. 시작 폴더가 정해져야 하기 때문입니다.
- 이미 있는 JSON 파일이 깨져 있으면 손대지 않고 상태 표시줄로 알려 줍니다.

**방법 B — 직접 등록**

도구 메뉴 → **"MCP 서버 정보..."** 에서 주소와 스니펫을 복사해 `.mcp.json`에 넣습니다.

```json
{
  "mcpServers": {
    "daedalus": { "type": "http", "url": "http://127.0.0.1:8787/mcp" }
  }
}
```

### 알아 두면 좋은 점

- **순서가 자유롭습니다.** HTTP 방식이라 앱을 먼저 켜 두고 Claude Code가 나중에 붙어도 됩니다.
- **앱을 껐다 켰으면** Claude Code에서 `/mcp`로 다시 연결하세요. 앱을 닫으면 서버도 같이 내려갑니다.
- **창을 여러 개 띄우면** `.mcp.json`이 고정 포트를 가리키므로 **먼저 켜진 창**이 협업 대상이 됩니다. 창마다 다른 Claude Code 세션을 붙이려면 `--mcp-port`로 포트를 각각 정하고, 각 세션의 `.mcp.json`도 그 포트로 맞추세요.

---

## 2. 함께 쓸 때의 요령

### 먼저 "무엇을 보고 있는지" 확인

| 도구 | 하는 일 |
|------|---------|
| `get_selection` | 내가 지금 선택한 노드. "이거"가 무엇인지 여기서 알아냅니다 |
| `get_history` | 내가 방금 한 편집 |
| `focus_node` / `select_nodes` | Claude가 "왼쪽 아래 노드요" 대신 **직접 선택해서** 보여 줍니다 |

선택은 편집이 아니므로 undo에 쌓이지 않습니다. `select_nodes`에 없는 이름이 하나라도 섞이면 아무것도 선택하지 않고 거부합니다.

### 크게 보고, 필요한 곳만 자세히

조회는 **개요 → 전문** 두 단계로 나뉩니다. 매번 전체를 주고받지 않아 빠르고 토큰도 아낍니다.

- 프로젝트: `get_project(sections=["components", "canvas"])`처럼 필요한 구획만 받습니다.
- 긴 본문: `get_body_outline`으로 제목 구조만 보고, `get_body_section` / `set_body_section`으로 한 섹션만 읽고 고칩니다.
- 훅: 프로젝트 개요에는 요약만 있고, 스크립트 본문까지는 `get_hook`으로 봅니다.
- 설정 필드: `get_component`는 기본값과 **다른 값만** 보여 줍니다. 전체 필드와 선택지는 `list_component_fields`.

### 검증은 두 가지를 다 봅니다

| 도구 | 보는 것 |
|------|---------|
| `validate_project` | 모델 검증(구조·참조·설정 규칙). `severity`, `component`로 걸러 받을 수 있음 |
| `compile_check` | 실제 컴파일을 **파일 하나도 쓰지 않고** 미리 돌려 봄. 파일 참조·MCP 서버 정의·작업 폴더 병합 같은 **컴파일러 경고**는 여기서만 나옴 |

둘 다 깨끗해야 컴파일이 통과한다고 볼 수 있습니다. 걸러 받은 결과가 0개여도 `total_*` 개수가 전체 기준이니 함께 확인하세요.

### 저장과 열기

- 편집은 **저장 전까지 메모리에만** 있습니다. 중요한 작업 뒤에는 `save_project`를 부르세요.
- 프로젝트 단위는 **폴더**입니다. `open_project`에는 폴더 경로를 주고, 경로는 `list_recent_projects`로 찾습니다.
- `open_project` / `new_project` / `import_package` / `export_package`는 **현재 프로젝트를 먼저 저장한 뒤** 진행합니다. 저장할 수 없으면 진행하지 않습니다. 한 번도 저장하지 않은 프로젝트는 저장 경로를 줘야 하고, 버리려면 `save_current=False`를 명시해야 합니다.

---

## 3. 무엇을 할 수 있나

도구는 모두 87개입니다. 영역별로 대표 도구만 추렸습니다. 전체 목록은 **[MCP 도구 지도](../MCP.md)** 에 있습니다.

| 영역 | 대표 도구 | 할 수 있는 일 |
|------|-----------|---------------|
| 조회 | `get_project`, `get_selection` | 프로젝트 구조, 내 선택, 히스토리, 검증·컴파일 미리보기 |
| 컴포넌트 | `create_skill`, `convert_skill` | 스킬·에이전트 만들기, 이름 변경, 삭제, 설정 필드, 진입점 프리셋 |
| 캔버스 구조 | `place_component`, `connect_states` | 노드 배치·이동, 전이 연결, 경유점 |
| 포트·분기 | `set_transfer_on`, `add_agent_call` | 갈래 선언, 에이전트 호출 포트 |
| 참조 노드 | `place_reference`, `link_reference` | 참조 문서 배치와 링크 |
| 블랙보드 | `create_blackboard_class`, `set_state_access` | 공유 상태 설계, 노드별 읽기·쓰기 선언 |
| 훅 | `create_hook`, `set_component_hooks` | 훅 라이브러리, 프리셋, 전역 훅 복사 |
| 본문 | `set_component_body`, `set_body_section` | 스킬·에이전트 본문 편집 |
| 작업 폴더 문서·설정 | `set_claude_md`, `create_rule` | `.claude/CLAUDE.md` 구역, 규칙, 설정 베이크 ([LOCAL 전용 기능](05-local-only-features.md)) |
| 외부 플러그인 | `list_wrappable_skills`, `set_external_plugins` | 다른 플러그인 스킬을 감싸 쓰기 |
| 세션 | `save_project`, `open_project` | 저장·열기·새 프로젝트·패키지·템플릿 |
| undo | `undo`, `redo` | 되돌리기·다시 하기 |

외부 플러그인 도구 중 **`fetch_plugin_skills`만 인터넷에 나갑니다.** 사용자가 그 플러그인을 지목했을 때만 쓰입니다.

---

## 4. 이렇게 씁니다 — 예시

### 예시 1. "이 노드 고쳐줘"

> **나:** (캔버스에서 `review` 노드를 클릭하고) 이거 본문에 체크리스트 섹션 좀 다듬어 줘.

Claude가 하는 일:

1. `get_selection` → 선택된 노드가 `review`임을 확인
2. `get_body_outline("review")` → 섹션 목록 확인
3. `get_body_section` → "체크리스트" 섹션만 읽기
4. `set_body_section` → 그 섹션만 고쳐 쓰기

에디터가 열려 있으면 타이핑하듯 바로 바뀝니다. 마음에 안 들면 본문 에디터에서 `Ctrl+Z`.

### 예시 2. 절차형 스킬을 fork 스킬로 바꾸기

> **나:** `research` 스킬은 서브에이전트에게 통째로 맡기고 싶어. fork로 바꾸고 Explore 에이전트로 돌려 줘.

1. `convert_skill("research", to="fork")` → 이름·본문·설명·포트·전이·배치는 그대로. fork에서 효과가 없는 `allowed_tools`는 버리고 결과의 `dropped`로 알려 줍니다.
2. `set_component_field("research", "agent", "Explore")` → fork 에이전트 지정 (기본값은 `general-purpose`)
3. `focus_node("research")` → 바뀐 노드를 화면에 띄워 보여 줌

전환은 한 번의 undo 단위입니다. 편집기의 전환 버튼, 캔버스 우클릭과 **같은 함수**를 씁니다.

fork 에이전트로 고를 수 있는 것:

- 내장 에이전트: `general-purpose`, `Explore`, `Plan`
- 사용 선언한 외부 플러그인 에이전트 (`플러그인:이름`)
- **캔버스에 배치되지 않은** 프로젝트 에이전트

이름은 대소문자까지 정확히 맞아야 합니다. 틀리면 Claude Code가 조용히 `general-purpose`로 돌려 버리므로 Daedalus가 미리 거부하고 선택지를 알려 줍니다. 처음부터 fork 스킬로 만들 때는 `create_skill(name, kind="fork", fork_agent="Explore")`.

### 예시 3. 분기가 있는 흐름 만들기

> **나:** `triage` 다음에 버그면 `fix`, 질문이면 `answer`로 가게 해 줘.

1. `create_skill` + 좌표(`x`, `y`)로 `fix`, `answer` 생성과 배치를 한 번에 (1 undo)
2. `set_transfer_on("triage", ...)` → `bug`, `question` 갈래 선언
3. `connect_states` → 각 전이에 trigger 연결

노드와 선만 그으면 **분기가 표현되지 않습니다.** 갈래 선언과 trigger까지 해야 캔버스 포트가 갈라지고 라벨이 보입니다. 에이전트로 가는 선은 `add_agent_call`로 만든 호출 포트에서만 나갈 수 있습니다(캔버스와 같은 규칙).

### 예시 4. 컴파일 전에 점검

> **나:** 컴파일해도 되는지 봐 줘.

1. `validate_project(severity="error")` → 에러부터 확인
2. `compile_check()` → 컴파일러 경고와 게이트 판정, 토큰 요약 확인
3. 문제가 있으면 `focus_node`로 해당 노드를 짚어 가며 설명
4. 다 고쳤으면 `save_project`

실제 컴파일은 앱에서 `Ctrl+B`로 합니다. `compile_check`는 `Ctrl+B`와 같은 입력으로 돌기 때문에 결과가 일치합니다.

---

## 5. undo 되는 것과 안 되는 것

| undo 됩니다 | undo 안 됩니다 |
|-------------|----------------|
| 캔버스·컴포넌트·포트·블랙보드·훅 편집 전부 | 저장·열기·새 프로젝트·패키지 (파일 쓰기) |
| 본문 편집 (컴포넌트별 본문 전용 스택) | 선택 (`focus_node`, `select_nodes`) |
| 작업 폴더 문서 본문 | 홈 설정 파일 변경 (마켓플레이스 폴더 등록, 사용자 템플릿 저장·삭제) |
| | `compile_check` (아무것도 바꾸지 않음) |

여러 값을 한꺼번에 바꾸는 도구(생성+배치, 프로젝트 속성 여러 개, 경유점 교체 등)는 **한 번의 `Ctrl+Z`** 로 통째로 되돌아갑니다.

본문 undo는 캔버스 undo와 스택이 다릅니다. 본문을 되돌리려면 본문 에디터에서 `Ctrl+Z`를 누르세요.

---

## 6. GUI와 MCP는 같은 기능을 가집니다

**GUI에서 할 수 있는 편집과 조회는 MCP로도 할 수 있습니다.** 새 GUI 기능이 생기면 대응하는 MCP 도구도 같이 만들어집니다.

또 같은 조작은 어디서 하든 결과가 같습니다. 캔버스 메뉴·에디터 버튼·MCP 도구가 대부분 같은 함수를 부르기 때문입니다. 그래서 캔버스에서 막히는 연결은 MCP에서도 막힙니다.

---

## 7. 한계와 주의할 점

- **앱이 켜져 있어야 합니다.** 서버는 앱의 일부입니다. 앱 없이 파일만 놓고 편집하는 방법은 없습니다.
- **다이얼로그가 떠 있으면 멈춥니다.** 도구는 앱의 메인 스레드에서 실행되므로, 모달 창이 떠 있으면 15초 뒤 시간 초과 오류가 납니다. 창을 닫고 다시 시키세요.
- **로컬 전용입니다.** 항상 `127.0.0.1`에만 열립니다. 다른 컴퓨터에서는 접속할 수 없습니다.
- **저장을 잊지 마세요.** 앱을 그냥 닫으면 저장 안 한 편집은 사라집니다(닫을 때 확인 창이 뜹니다).
- **잘못된 값은 거부됩니다.** 없는 이름, 틀린 선택지, 그 종류에 없는 속성은 조용히 넘어가지 않고 이유와 선택지를 돌려줍니다. Claude가 오류를 받으면 메시지를 읽고 다시 시도하면 됩니다.
- **삭제해도 이름 참조는 남깁니다.** 컴포넌트·훅·블랙보드 클래스를 지우면 다른 곳의 참조는 몰래 지우지 않고 `still_referenced_by`로 알려 줍니다. 남은 참조는 검증 경고로도 보입니다.
- **랩핑 스킬은 삭제 대신 끕니다.** `set_wrapped_enabled(name, false)`를 쓰세요.

---

## 8. Daedalus 전용 도우미 플러그인

저장소의 `project/daedalus_cc_plugin/`은 **Daedalus로 만든, Daedalus를 다루기 위한 플러그인 프로젝트**입니다. 설명은 "Daedalus GUI를 MCP로 함께 조작해 FSM 기반 Claude Code 플러그인을 설계한다"입니다.

- 빌드 타깃은 **LOCAL** 입니다. MCP·훅을 쓰기 때문입니다([LOCAL과 마켓플레이스](04-local-vs-marketplace.md) 참고).
- `graph-orient`(지금 열린 것과 사용자 선택 파악) → `graph-design`(컴포넌트 만들고 배치) → `graph-wire`(포트·트리거 연결) → `graph-state`(블랙보드 설계) → `plugin-verify` / `plugin-compile` 같은 스킬로, 이 문서의 요령을 워크플로로 묶어 둔 것입니다.
- 앱에서 이 폴더를 열어 보면 구성을 그대로 볼 수 있고, 컴파일하면 작업 폴더에 설치됩니다.

필수는 아닙니다. 이 플러그인 없이도 MCP 서버만 연결하면 모든 도구를 쓸 수 있습니다.

---

## 더 보기

- [MCP 도구 지도](../MCP.md) — 87개 도구 전체 목록과 영역별 설명
- [개념 설명](01-concept.md) · [레지스트리](02-registry.md) · [LOCAL과 마켓플레이스](04-local-vs-marketplace.md) · [LOCAL 전용 기능](05-local-only-features.md)
