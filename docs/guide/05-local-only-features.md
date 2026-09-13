# 로컬 플러그인에서만 가능한 기능

Daedalus 프로젝트는 빌드 타깃이 둘입니다. **마켓플레이스 플러그인**과 **로컬 플러그인**(화면 표시는
"프로젝트 설치 (.claude/ 반입)")입니다. 두 방식이 무엇이 다른지는
[로컬 vs 마켓플레이스](04-local-vs-marketplace.md)에서 설명합니다. 이 문서는 **로컬로 빌드해야만
동작하는 기능**(또는 로컬에서만 제대로 동작하는 기능)을 하나씩 짚습니다.

## 먼저: 로컬로 바꾸는 법

- 새 프로젝트를 만들 때(Ctrl+N) 다이얼로그에서 빌드 타깃을 고릅니다.
- 이미 만든 프로젝트는 **파일 → 프로젝트 속성…** 의 "빌드 타깃"에서 바꿉니다.
- MCP로는 `new_project(build_target="local")` 또는 `set_project_properties(build_target="local")`를 씁니다.

타깃은 언제든 다시 바꿀 수 있습니다. 로컬 전용 내용을 써 두고 마켓플레이스로 바꿔도 내용은
사라지지 않고, 산출에만 빠집니다(경고로 알려 줍니다).

## 한눈에 보기

| 기능 | 로컬에서 생기는 것 | 마켓플레이스에서는 |
|------|-------------------|-------------------|
| 에이전트 `hooks`·`mcpServers`·`permissionMode` | 에이전트 `.md` 프론트매터에 실려 실제로 동작 | CC가 무시함 → 편집기에서 잠김 |
| MCP 서버 자동 배선 | `.mcp.json` 병합 + 설정 파일에 서버 활성화 | 배선 안 함 |
| 훅 등록 | `.claude/settings*.json`의 `hooks`에 병합 | `hooks/hooks.json` 파일로 산출 |
| 작업 폴더 CLAUDE.md | `.claude/CLAUDE.md`에 플러그인 구역 | 산출 안 함 |
| 규칙(rules) | `.claude/rules/<이름>.md` | 산출 안 함 |
| 작업 폴더 설정 | `.claude/settings*.json`에 병합 | 산출 안 함 |

---

## 1. 에이전트의 hooks / mcpServers / permissionMode

**무엇인가.** 에이전트에게만 거는 훅, 에이전트가 쓸 MCP 서버 목록, 권한 모드(예: `acceptEdits`)입니다.

**왜 로컬에서만 되나.** Claude Code는 보안상 **플러그인에 들어 있는 서브에이전트의 이 세 필드를
무시합니다**(공식 sub-agents 문서). 파일에 적혀 있어도 아무 일도 일어나지 않습니다. 로컬 빌드는
에이전트를 플러그인이 아니라 작업 폴더의 `.claude/agents/`에 직접 넣기 때문에 제약을 받지 않습니다.
사실 이것이 로컬 타깃이 생긴 가장 큰 이유입니다.

**Daedalus에서 설정하기.**
- GUI: 에이전트 편집 탭(🤖 에이전트 이름)의 프론트매터 행 `hooks` / `mcp_servers` / `permission_mode`.
  마켓플레이스 프로젝트에서는 이 행이 **잠겨 있고**, 툴팁에 이유가 나옵니다.
- `mcp_servers` 입력칸의 후보는 프로젝트에 등록한 MCP 서버 정의와, 사용 선언한 외부 플러그인이
  제공하는 서버에서 옵니다.
- MCP: `set_component_hooks(name, hooks=[...])`, `set_component_field(name, "mcp_servers", [...])`,
  `set_component_field(name, "permission_mode", "acceptEdits")`.

**컴파일하면.** `.claude/agents/<에이전트>.md` 프론트매터에 들어갑니다.
- `hooks`는 settings.json의 `hooks`와 같은 3단 구조(이벤트 → matcher 그룹 → 명령)로 나갑니다.
- `mcpServers`는 서버 이름 목록입니다. `mcp_servers`에 적은 이름과 `tools`의 `mcp__<서버>__…`에서
  뽑은 이름을 합칩니다.
- 마켓플레이스 빌드에서 에이전트 본문에 붙던 "요구 환경" 안내 단락은 로컬에서는 나오지 않습니다.
  프론트매터가 대신 말하기 때문입니다.

**주의점.**
- 에이전트 훅은 훅의 "사용" 스위치(`enabled`)를 보지 않습니다. 전역으로는 꺼 두고 특정 에이전트
  안에서만 켜는 용도가 정상이기 때문입니다.
- 프론트매터의 `Stop` 훅은 실행할 때 `SubagentStop`으로 바뀝니다. 직접 `SubagentStop`을 걸기보다
  `Stop`으로 두는 편이 낫습니다.
- 마켓플레이스 프로젝트에 값이 이미 들어 있으면 경고가 뜹니다.
  `mcp_agent_in_marketplace_build`(MCP 사용), `unsupported_agent_field_in_marketplace_build`
  (hooks·기본값이 아닌 permissionMode).
- MCP 도구는 마켓플레이스 프로젝트에서도 값을 받아 줍니다. 대신 위 경고가 뜹니다.

## 2. MCP 서버 자동 배선

**무엇인가.** 스킬·에이전트가 쓰는 MCP 서버를 컴파일할 때 작업 폴더에 등록하고 켜 주는 기능입니다.
Claude Code를 열면 따로 설정할 필요 없이 서버가 붙어 있습니다.

**왜 로컬에서만 되나.** 로컬 빌드는 **컴파일이 곧 설치**라서 작업 폴더의 `.mcp.json`과 설정 파일을
직접 고칠 수 있습니다. 마켓플레이스 플러그인은 설치될 작업 폴더를 알 수도, 거기 쓸 수도 없습니다.

**Daedalus에서 설정하기.**
- 컴포넌트에서는 이름으로만 참조합니다. 스킬의 `allowed_tools`나 에이전트의 `tools`에
  `mcp__<서버>__<도구>`를 넣거나, 에이전트 `mcp_servers`에 서버 이름을 넣습니다.
- 서버를 **어떻게 띄우는지(정의)** 는 MCP `set_mcp_server_def(name, config)`로 등록합니다.
  예: `{"type": "http", "url": "http://127.0.0.1:8787/mcp"}` 또는
  `{"command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"]}`.
  `config`를 비우면 정의가 지워집니다. 등록된 정의는 `get_project`에서 볼 수 있습니다.
- `daedalus` 서버(이 앱 자신)는 정의를 적지 않아도 앱이 채워 줍니다.

**컴파일하면.**
- `<작업 폴더>/.mcp.json`의 `mcpServers`에 **참조된 서버 중 정의가 있는 것**만 들어갑니다.
- 설정 파일(아래 7절에서 고르는 `.claude/settings.json` 또는 `settings.local.json`)의
  `enabledMcpjsonServers`에 그 이름이 추가됩니다.

**주의점.**
- 참조는 있는데 정의가 없으면 `missing_mcp_server_def` 경고가 뜨고 그 서버는 배선되지 않습니다.
  사용 선언한 외부 플러그인이 제공하는 서버는 그 플러그인이 알아서 띄우므로 이 경고에서 빠집니다.
- 기존 `.mcp.json`이나 설정 파일이 올바른 JSON이 아니면 **건드리지 않고**
  `unmergeable_settings_json` 경고만 냅니다. 파일을 고친 뒤 다시 컴파일하세요.
- 병합은 추가·갱신만 합니다. 같은 이름의 서버는 새 정의로 바뀌고, 직접 적어 둔 다른 서버는 그대로
  남습니다. 정의를 지워도 이미 들어간 항목은 지워지지 않습니다.
- 지금은 GUI에 서버 정의 편집 화면이 없어 MCP 도구로만 등록할 수 있습니다.

## 3. 훅을 작업 폴더 설정에 병합

**무엇인가.** 프로젝트 훅 라이브러리(🪝 훅 탭)의 훅을 작업 폴더의 설정 파일에 등록하는 것입니다.

**왜 로컬에서 다르게 나가나.** 훅 자체는 두 타깃 모두 나갑니다. 차이는 **어디에 등록되느냐**입니다.
마켓플레이스는 플러그인 안의 `hooks/hooks.json`에 담기고, 로컬은 플러그인 파일이 없으므로 작업
폴더 설정 파일의 `hooks`에 바로 들어갑니다. 이미 쓰고 있는 설정 파일과 같은 곳이라 다른 설정과 함께
관리됩니다.

**Daedalus에서 설정하기.**
- GUI: 🪝 훅 탭에서 훅을 만들고 편집합니다.
- MCP: `create_hook`, `update_hook`, `delete_hook`, 전역 훅 복사는 `copy_global_hook`.

**컴파일하면.**
- 설정 파일(`.claude/settings.json` 또는 `settings.local.json`)의 `hooks`에 병합됩니다.
  `hooks/hooks.json`은 만들지 않습니다.
- 명령 훅의 스크립트는 `<작업 폴더>/hooks/scripts/<훅 이름>.sh`로 나가고, 명령은
  `${CLAUDE_PROJECT_DIR}/hooks/scripts/…`를 가리킵니다.

**주의점.**
- 프로젝트 훅 라이브러리의 훅은 참조 여부와 상관없이 전부 나갑니다. "사용"을 끈 훅만 빠집니다.
  전역 훅(`~/.daedalus/hooks/`)은 컴포넌트가 참조한 것만 나갑니다.
- 똑같은 훅 그룹은 다시 넣지 않으므로 여러 번 컴파일해도 훅이 불어나지 않습니다. 반대로 훅을
  **고치거나 지우면 예전 항목은 설정 파일에 남습니다**. 필요하면 직접 정리하세요.
- 스킬에 거는 훅(스킬이 활성인 동안만 도는 훅)은 두 타깃 모두 SKILL.md에 실리므로 로컬 전용이
  아닙니다.
- 합성되는 진행 상태 주입 훅(SessionStart)은 POSIX 셸(`cat`)을 전제로 합니다. 필요 없으면 프로젝트
  속성에서 끄세요.

## 4. 작업 폴더 CLAUDE.md 구역

**무엇인가.** 작업 폴더의 `.claude/CLAUDE.md`에 들어가는 지침입니다. 스킬은 필요할 때만 불려
오지만, CLAUDE.md는 **매 세션 항상** 컨텍스트에 실립니다. "이 폴더에서는 늘 이렇게 해라" 같은 내용을
둡니다.

**왜 로컬에서만 되나.** 플러그인은 설치된 작업 폴더의 `.claude/`에 파일을 쓸 수 없습니다.

**Daedalus에서 설정하기.**
- GUI: 📌 CLAUDE.md 탭. 쓴 마크다운이 그대로 나갑니다(자동 생성·합성은 없습니다).
- MCP: `set_claude_md`, 조회는 `list_workspace_docs` / `get_workspace_doc`. 본문 편집도 Ctrl+Z로
  되돌릴 수 있습니다.
- 이 탭(과 5·6절의 탭)은 로컬 프로젝트에서만 보입니다.

**컴파일하면.** `.claude/CLAUDE.md` 안에 이런 **플러그인 구역**이 생깁니다.

```markdown
<!-- daedalus:my-plugin open -->
# my-plugin

...본문...
<!-- daedalus:my-plugin close -->
```

- 파일이 없으면 만들고, 구역이 없으면 파일 끝에 붙이고, 구역이 있으면 **그 자리에서** 바꿉니다.
  구역 밖에 쓴 사람의 내용이나 다른 플러그인의 구역은 건드리지 않습니다.
- 본문이 `# `로 시작하면 제목을 따로 붙이지 않습니다.
- 본문을 비우고 컴파일하면 구역이 지워집니다.
- 표식 주석은 Claude Code가 컨텍스트에 넣기 전에 걷어내므로 토큰을 쓰지 않습니다.

**주의점.**
- 표식이 망가져 있으면(open만 있거나, open이 두 개거나, close가 앞에 있음) 파일을 건드리지 않고
  `unmergeable_claude_md` 경고만 냅니다. 구역의 끝을 추측하면 뒤의 내용을 날릴 수 있어서입니다.
- 매 세션 실리는 만큼 비용이 계속 듭니다. 컴파일 후 토큰 리포트에 이 구역의 크기가 따로 나옵니다.
- 마켓플레이스 프로젝트에 내용이 있으면 `workspace_doc_in_marketplace_build` 경고와 탭 안내가 뜹니다.

## 5. 규칙 (.claude/rules)

**무엇인가.** 파일 하나가 규칙 하나인 지침 문서입니다. `paths:`를 주면 **그 경로의 파일을 다룰 때만**
불려 오고, 비우면 CLAUDE.md처럼 매 세션 실립니다.

**왜 로컬에서만 되나.** CLAUDE.md와 같은 이유입니다. 작업 폴더의 `.claude/`에 써야 합니다.

**Daedalus에서 설정하기.**
- GUI: 📐 규칙 탭. 왼쪽 목록에서 규칙을 고르고, 본문 위의 "적용 경로 (비우면 항상 로드)" 칸에
  glob을 태그로 넣습니다(예: `src/**/*.ts`).
- MCP: `create_rule`, `set_rule_body`, `set_rule_paths`(빈 목록이면 항상 로드), `rename_rule`,
  `delete_rule`.

**컴파일하면.** `.claude/rules/<규칙 이름>.md`가 생깁니다. 경로가 있으면 앞에 프론트매터가 붙습니다.

```markdown
---
paths: ["src/**/*.ts", "lib/**"]
---
<본문>
```

**주의점.**
- 규칙 이름이 곧 파일명입니다. 이름이 겹치면 `duplicate_rule_name` 에러, 이름 규칙(소문자·숫자·`-`)에
  어긋나면 `invalid_rule_name` 경고가 뜨고 컴파일은 거부됩니다.
- "적용 경로"를 채웠는데 본문 맨 위에도 직접 `---` 프론트매터를 적었다면 `rule_body_frontmatter`
  경고가 뜹니다. 본문은 고쳐 주지 않으니 한쪽으로 정리하세요.
- `delete_rule`이나 이름 변경은 **이미 만들어진 파일을 지우지 않습니다**. 작업 폴더에서 직접 지우세요.

## 6. 작업 폴더 설정 베이크

**무엇인가.** `permissions.deny` 같은 Claude Code 설정을 작업 폴더 설정 파일에 넣어 두는 기능입니다.
훅으로 막는 것보다 강한, 선언으로 거는 제약이 필요할 때 씁니다.

**왜 로컬에서만 되나.** 플러그인도 `settings.json`을 실을 수는 있지만, 허용되는 키가 `agent`와
`subagentStatusLine` 둘뿐입니다. `permissions` 같은 키는 적용되지 않습니다(공식 문서 확인 2026-09-07).

**Daedalus에서 설정하기.**
- GUI: ⚙ 설정 탭. Claude Code 설정 스키마를 따라 모든 키를 편집할 수 있습니다. 훅 항목은 없습니다
  (훅은 🪝 훅 탭에서만 다룹니다). 설정 편집 위젯이 설치되지 않았으면 안내 문구만 보입니다.
- MCP: `get_workspace_settings`, `set_workspace_settings(settings)`(통째로 바꿈, `{}`이면 전부 해제,
  `hooks` 키는 거부).

**컴파일하면.** 고른 설정 파일에 **깊은 병합**합니다.
- 객체는 하위 키끼리 합칩니다.
- 목록은 없는 항목만 순서대로 덧붙입니다.
- 값은 프로젝트 값으로 바뀝니다.

**주의점.**
- 추가·갱신만 합니다. 프로젝트에서 항목을 빼도 설정 파일에서는 **지워지지 않습니다**.
- 마켓플레이스 프로젝트에 설정이 있으면 `workspace_settings_in_marketplace_build` 경고와 탭 안내가
  뜹니다.

## 7. 컴파일이 곧 설치

위 기능들이 모두 기대는 공통 동작입니다.

**어떻게 컴파일하나.**
- GUI: **빌드 → 컴파일**(Ctrl+B). 폴더 선택 창의 제목이 "설치 대상 작업 폴더 선택"으로 바뀝니다.
  출력 폴더가 아니라 **플러그인을 넣을 작업 폴더**를 고르는 것입니다.
- 이어서 설정을 어느 파일에 넣을지 묻습니다.
  - `.claude/settings.json` — 공유(저장소에 커밋되는 설정, 기본값)
  - `.claude/settings.local.json` — 개인(커밋 제외)

  훅·MCP 서버 활성화·작업 폴더 설정·외부 플러그인 활성화가 **모두 이 한 파일**로 갑니다.
  여기서 취소하면 컴파일도 취소됩니다.
- MCP에는 실제로 쓰는 컴파일 도구가 없습니다. `compile_check(out_dir, settings_filename)`로 파일을
  쓰지 않고 미리 돌려 경고를 확인하고, 설치는 GUI에서 합니다.

**어디에 무엇이 생기나.**

```text
<작업 폴더>/
├─ .mcp.json                      ← MCP 서버 정의 병합
├─ .claude/
│  ├─ skills/<스킬>/SKILL.md
│  ├─ agents/<에이전트>.md
│  ├─ rules/<규칙>.md
│  ├─ CLAUDE.md                   ← 플러그인 구역만
│  └─ settings.json (또는 settings.local.json)
├─ files/                         ← 공용 동봉 파일
├─ schemas/                       ← 블랙보드 스키마
└─ hooks/scripts/                 ← 훅 스크립트
```

`plugin.json`, `hooks/hooks.json`, 설치 스크립트는 만들지 않습니다.

**주의점.**
- **다시 컴파일해도 안전합니다.** JSON 병합은 같은 입력이면 결과가 같습니다.
- **대신 지우지는 않습니다.** 스킬을 지우거나 이름을 바꿔도 예전 파일은 남습니다. `files/`도 기존
  폴더를 비우지 않고 덮어쓰기만 합니다. 사용자 작업 폴더의 파일을 실수로 지우는 것보다 낡은 파일이
  남는 편이 낫다고 판단했기 때문입니다.
- 본문에서 파일 경로는 `${ROOT}`로 쓰세요. 로컬에서는 `${CLAUDE_PROJECT_DIR}`로 바뀝니다.
  `${CLAUDE_PLUGIN_ROOT}`/`${CLAUDE_PLUGIN_DATA}`는 플러그인에서만 치환돼 로컬에서는 글자 그대로
  남습니다. 본문에 남아 있으면 `plugin_root_in_local_build` 경고가 뜹니다(코드 블록 안은 검사하지
  않음). 로컬 프로젝트의 변수 자동완성에는 `${CLAUDE_PLUGIN_ROOT}`가 나오지 않습니다.

## 로컬에서 달라지는 소소한 것들

로컬 전용 기능은 아니지만 로컬에서 결과가 달라지는 부분입니다.

- **fork 스킬의 `agent:` 이름.** 프로젝트 안의 fork 에이전트를 가리킬 때, 마켓플레이스에서는
  `플러그인:이름`, 로컬에서는 `이름`으로 나갑니다. 자동으로 처리되니 신경 쓸 필요는 없습니다.
- **외부 플러그인 사용 선언.** 두 타깃 모두 자동 배선합니다. 마켓플레이스는 `plugin.json`의
  `dependencies`에, 로컬은 설정 파일의 `enabledPlugins`에 넣습니다. 로컬은 `플러그인@마켓` 형식이어야
  하고, 마켓 표기 없는 이름은 `external_plugin_no_marketplace` 경고와 함께 빠집니다.
  자세한 내용은 [레지스트리](02-registry.md)를 보세요.
- **도구 → Claude Code 실행 메뉴는 로컬 전용이 아닙니다.** 이 메뉴는 Daedalus **프로젝트 폴더**에
  `daedalus` MCP 서버를 배선한 뒤 그 폴더에서 Claude Code를 엽니다(컴파일과 같은 병합 함수를 씁니다).
  AI와 함께 설계하기 위한 기능이며, 빌드 타깃과 상관없이 동작합니다. [MCP 가이드](06-mcp.md) 참고.

## 관련 경고 모음

| 경고 | 언제 뜨나 |
|------|-----------|
| `mcp_agent_in_marketplace_build` | 마켓플레이스인데 에이전트가 MCP를 씀 |
| `unsupported_agent_field_in_marketplace_build` | 마켓플레이스인데 에이전트에 hooks·permissionMode가 있음 |
| `workspace_doc_in_marketplace_build` | 마켓플레이스인데 CLAUDE.md·규칙에 내용이 있음 |
| `workspace_settings_in_marketplace_build` | 마켓플레이스인데 작업 폴더 설정이 있음 |
| `plugin_root_in_local_build` | 로컬인데 본문에 `${CLAUDE_PLUGIN_ROOT}` 등이 남아 있음 |
| `missing_mcp_server_def` | 참조한 MCP 서버의 정의가 없어 배선 못 함 |
| `unmergeable_settings_json` | 기존 `.mcp.json`·설정 파일이 깨져 병합 안 함 |
| `unmergeable_claude_md` | `.claude/CLAUDE.md`의 표식이 망가져 병합 안 함 |
| `rule_body_frontmatter` | 규칙의 적용 경로와 본문 프론트매터가 겹침 |
| `external_plugin_no_marketplace` | 외부 플러그인 선언에 `@마켓`이 없어 활성화 못 함 |

`validate_project`(F7)는 위쪽 다섯 개를, `compile_check`와 실제 컴파일은 아래쪽 컴파일러 경고까지
보여 줍니다.

## 함께 읽기

- [Daedalus 개념](01-concept.md)
- [로컬 vs 마켓플레이스](04-local-vs-marketplace.md)
- [레지스트리](02-registry.md)
- [MCP로 함께 편집하기](06-mcp.md)
