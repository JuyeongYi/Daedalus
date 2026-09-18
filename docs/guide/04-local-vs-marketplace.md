# 로컬 플러그인과 마켓플레이스 플러그인의 차이

Daedalus 프로젝트는 컴파일할 때 **빌드 타깃**을 하나 고릅니다. 타깃은 둘입니다.

| 화면에 보이는 이름 | 이 문서에서 부르는 이름 | 한 줄 요약 |
|---|---|---|
| 마켓플레이스 플러그인 | 마켓플레이스 | 배포용 플러그인 폴더를 만든다 |
| 프로젝트 설치 (.claude/ 반입) | 로컬 | 작업 폴더에 바로 설치한다 |

같은 프로젝트라도 타깃에 따라 나오는 파일, 동작하는 기능, 뜨는 경고가 달라집니다.
이 문서는 그 차이와 고르는 법, 바꾸는 법을 설명합니다.

> 로컬 타깃의 화면 이름이 "로컬 플러그인"이 아니라 "프로젝트 설치"인 데는 이유가 있습니다.
> 로컬 산출물은 Claude Code가 **플러그인으로 보지 않습니다**. `.claude/` 밑에 직접 둔 스킬·에이전트로 봅니다.
> 그래서 플러그인에 걸리는 제약이 로컬에는 걸리지 않습니다(아래 "Claude Code가 무시하는 설정" 참고).

## 한눈에 비교

| | 마켓플레이스 | 로컬 |
|---|---|---|
| 컴파일 대상 폴더 | 출력 폴더(여기에 플러그인이 만들어짐) | 설치할 **작업 폴더** |
| 설치 | 만든 플러그인을 Claude Code에 따로 설치 | 컴파일이 곧 설치 — 따로 할 일 없음 |
| `plugin.json` | 만든다 | 만들지 않는다 |
| 스킬 위치 | `skills/<이름>/SKILL.md` | `.claude/skills/<이름>/SKILL.md` |
| 에이전트 위치 | `agents/<이름>.md` | `.claude/agents/<이름>.md` |
| 공통 안내 파일 | `guides/<플러그인>/workflow.md`·`blackboard.md` | 같은 경로(작업 폴더 기준) |
| 훅 등록 | `hooks/hooks.json` | 설정 파일(`.claude/settings.json` 등)의 `hooks`에 병합 |
| 본문의 `${ROOT}` | `${CLAUDE_PLUGIN_ROOT}` | `${CLAUDE_PROJECT_DIR}` |
| fork 스킬의 에이전트 이름 | `플러그인:이름` | `이름` |
| 에이전트 `hooks`·`mcpServers`·`permissionMode` | Claude Code가 무시 → 편집 잠금 | 동작 |
| MCP 서버 배선 | 하지 않음(필요 환경으로 안내만) | `.mcp.json`에 병합하고 켠다 |
| 외부 플러그인 | `plugin.json`의 `dependencies` | 설정의 `enabledPlugins` |
| CLAUDE.md·규칙·작업 폴더 설정 | 나가지 않음 | 나감 |

## 마켓플레이스 빌드가 만드는 것

컴파일(Ctrl+B)하면 "컴파일 출력 폴더"를 묻습니다. 그 폴더가 곧 플러그인 하나가 됩니다.

```
<출력 폴더>/
  .claude-plugin/plugin.json     ← 플러그인 매니페스트 (항상 생성)
  skills/<스킬>/SKILL.md
  agents/<에이전트>.md           ← 워크플로 에이전트·fork 에이전트 둘 다
  guides/<플러그인>/workflow.md   ← 공통 안내 파일 (가리키는 컴포넌트가 있을 때)
  guides/<플러그인>/blackboard.md
  hooks/hooks.json               ← 훅이 있을 때
  hooks/scripts/<훅>.sh
  schemas/<플러그인>.json         ← 블랙보드 클래스가 있을 때
  files/                         ← 공용 파일이 있을 때
```

- `plugin.json`에는 프로젝트 이름·설명·버전이 들어갑니다. 프로젝트 이름이 **플러그인 식별자**가 되므로
  소문자·숫자·하이픈 규약(`^[a-z0-9][a-z0-9-]*$`)을 지켜야 컴파일됩니다.
- 이 폴더를 마켓플레이스에 올리거나 Claude Code에 플러그인으로 설치해서 씁니다.
  여러 사람, 여러 작업 폴더에 나눠 주기 좋습니다.
- 다시 컴파일하면 `files/`는 비우고 새로 복사합니다. 출력 폴더는 Daedalus 전용이라는 전제입니다.

## 로컬 빌드가 만드는 것

컴파일하면 "설치 대상 작업 폴더"를 묻습니다. 이어서 설정을 어느 파일에 넣을지 한 번 더 묻습니다.

- `.claude/settings.json` — 공유용(저장소에 커밋되는 설정). 기본값입니다.
- `.claude/settings.local.json` — 개인용(커밋하지 않는 설정).

```
<작업 폴더>/
  .claude/skills/<스킬>/SKILL.md
  .claude/agents/<에이전트>.md
  guides/<플러그인>/workflow.md   ← 공통 안내 파일 (`.claude/` 밖입니다)
  guides/<플러그인>/blackboard.md
  .claude/settings.json          ← (또는 settings.local.json) 훅·MCP·설정 병합
  .claude/rules/<규칙>.md         ← 규칙 문서가 있을 때
  .claude/CLAUDE.md              ← 이 플러그인 구역만 갱신
  .mcp.json                      ← 쓰는 MCP 서버 병합
  hooks/scripts/<훅>.sh
  schemas/<플러그인>.json
  files/
```

- `plugin.json`, `hooks/hooks.json`, 설치 스크립트는 **만들지 않습니다**. Claude Code가 읽는 자리에 바로 놓기 때문입니다.
- 작업 폴더에는 사용자가 원래 가진 파일이 있으니, 병합은 **추가하거나 갱신만** 합니다.
  - 내가 손으로 넣은 설정 키는 지우지 않습니다.
  - 같은 훅 묶음을 두 번 넣지 않습니다. 몇 번을 다시 컴파일해도 결과가 같습니다.
  - `files/`는 지우지 않고 덮어쓰기만 합니다.
- 기존 JSON이 깨져 있으면 손대지 않고 `unmergeable_settings_json` 경고만 냅니다.
  `CLAUDE.md`의 구역 표식이 깨져 있으면 역시 손대지 않고 `unmergeable_claude_md` 경고를 냅니다.
- 컴파일은 파일을 쓰기만 합니다. 프로젝트에서 스킬을 지워도 전에 설치된 파일은 작업 폴더에 남습니다.

## 이름과 경로가 달라지는 곳

### 경로 변수 `${ROOT}`

본문에서 공용 파일을 가리킬 때는 `${ROOT}/files/…`처럼 `${ROOT}`를 씁니다. 파일을 본문에 끌어다 놓으면 이 형태로 들어갑니다.
컴파일할 때 타깃에 맞게 바뀝니다.

| 본문에 쓴 것 | 마켓플레이스 산출 | 로컬 산출 |
|---|---|---|
| `${ROOT}/files/guide.md` | `${CLAUDE_PLUGIN_ROOT}/files/guide.md` | `${CLAUDE_PROJECT_DIR}/files/guide.md` |

그래서 타깃을 바꿔도 본문은 고칠 필요가 없습니다.
반대로 본문에 `${CLAUDE_PLUGIN_ROOT}`를 **직접** 쓰면 로컬에서는 치환되지 않고 글자 그대로 남습니다.
로컬 타깃에서 이런 본문이 있으면 `plugin_root_in_local_build` 경고가 뜹니다(`${CLAUDE_PLUGIN_DATA}`도 같음).
백틱으로 감싼 코드 부분은 검사하지 않습니다.

### fork 스킬의 에이전트 이름

fork 스킬이 프로젝트 안의 **fork 에이전트**를 쓰면, 프론트매터 `agent:` 값이 타깃마다 다르게 나갑니다.

- 마켓플레이스: `agent: my-plugin:researcher` — 플러그인 에이전트는 이 형식으로만 찾힙니다.
- 로컬: `agent: researcher`

Claude Code는 이름이 안 맞으면 조용히 `general-purpose`로 실행합니다. 이 변환은 컴파일러가 알아서 하니 직접 적지 마세요.
내장 에이전트(`general-purpose`·`Explore`·`Plan`)와 외부 플러그인 에이전트는 저장된 이름 그대로 나갑니다.

### 상태·진행 파일

블랙보드 상태 파일(`state/<플러그인>/<클래스>.json`)과 진행 기록(`state/__progress__.json`)은 **두 타깃 모두**
Claude Code를 실행한 작업 폴더 기준으로 만들어집니다. 이 부분은 차이가 없습니다.
블랙보드 스키마 `schemas/<플러그인>.json`은 `${ROOT}` 밑에 있으므로 마켓플레이스에서는 플러그인 폴더, 로컬에서는 작업 폴더에 있습니다.

## Claude Code가 무시하는 설정

Claude Code는 보안상 **플러그인에 든 서브에이전트**의 다음 세 프론트매터를 무시합니다.

- `hooks`
- `mcpServers`
- `permissionMode`

파일에 적혀 있어도 아무 일도 일어나지 않습니다. "권한을 막아 뒀는데 실제로는 안 막힌" 상태가 되는 거죠.
그래서 마켓플레이스 타깃에서는 Daedalus가 세 겹으로 막습니다.

1. **편집기가 잠급니다.** 에이전트 편집기에서 세 필드가 비활성화되고, 툴팁으로 이유를 알려 줍니다.
2. **컴파일러가 내보내지 않습니다.** 세 필드 모두 프론트매터에 쓰지 않습니다.
   대신 훅·MCP 서버가 필요하다는 사실을 에이전트 본문의 `## Requirements` 단락에 적습니다.
3. **검증이 경고합니다.** 이미 값이 들어 있으면 경고가 뜹니다(아래 표).

잠겨도 이미 넣은 값은 지워지지 않습니다. 로컬로 바꾸면 그대로 살아납니다.

로컬 타깃에서는 에이전트가 `.claude/agents/`에 놓이므로 셋 다 동작합니다.
`hooks`와 `mcpServers`가 프론트매터에 실제로 나가고, `## Requirements` 단락은 나가지 않습니다.
**에이전트에 MCP·훅·권한 모드를 걸고 싶다면 로컬이 답입니다.** 로컬 타깃이 존재하는 가장 큰 이유입니다.

참고로 스킬의 `hooks`는 두 타깃 모두에서 나갑니다. 위 제약은 에이전트에만 해당합니다.

## MCP 서버 쓰기

| | 마켓플레이스 | 로컬 |
|---|---|---|
| 스킬 `allowed-tools`에 `mcp__서버__…` | 본문에 필요 환경으로 안내 | 같음 + 서버를 작업 폴더에 배선 |
| 에이전트가 MCP 사용 | 프론트매터에서 빠짐 + 경고 | 프론트매터 `mcpServers`로 나감 |
| `.mcp.json` | 만들지 않음 — 사용자가 알아서 연결 | 참조한 서버 정의를 병합 |
| 서버 켜기 | — | 설정의 `enabledMcpjsonServers`에 이름 추가 |

로컬에서 서버를 배선하려면 프로젝트에 **서버 정의**가 있어야 합니다(MCP `set_mcp_server_def`로 추가).
정의 없이 이름만 참조하면 `missing_mcp_server_def` 경고가 뜨고 그 서버는 배선되지 않습니다.
Daedalus 자신의 MCP 서버는 앱이 정의를 알고 있어 따로 넣지 않아도 채워집니다.

## 외부 플러그인 쓰기

카탈로그에서 "이 플러그인을 쓴다"고 선언하면 컴파일이 자동으로 연결해 줍니다.

- 마켓플레이스: `plugin.json`에 `"dependencies": ["플러그인@마켓"]`. 마켓 표기가 없는 이름도 됩니다(자기 마켓에서 찾음).
- 로컬: 설정 파일에 `"enabledPlugins": {"플러그인@마켓": true}`.
  **로컬은 `플러그인@마켓` 형식이어야 합니다.** 마켓 표기가 없으면 `external_plugin_no_marketplace` 경고와 함께 빠집니다.

## 로컬에서만 되는 것

아래는 작업 폴더에 직접 써야 해서 로컬 타깃에서만 나갑니다. 마켓플레이스 프로젝트에서는 해당 탭이 숨겨집니다.
각 기능의 사용법은 [로컬에서만 되는 기능](05-local-only-features.md)을 보세요.

- **CLAUDE.md** — `.claude/CLAUDE.md` 안에 이 플러그인 구역을 넣습니다. 매 세션 항상 읽힙니다.
- **규칙** — `.claude/rules/<이름>.md`. 적용 경로를 비우면 항상, 채우면 해당 파일을 다룰 때 읽힙니다.
- **작업 폴더 설정** — `permissions.deny` 같은 설정을 설정 파일에 굽습니다.
- **에이전트의 hooks·mcpServers·permissionMode** — 위에서 설명한 것.
- **MCP 서버 자동 배선**과 **외부 플러그인 자동 활성화** — 위에서 설명한 것.

플러그인도 자체 `settings.json`을 실을 수는 있지만, 허용되는 키가 `agent`와 `subagentStatusLine` 둘뿐입니다.
그래서 `permissions` 같은 작업 폴더 설정은 마켓플레이스로 옮길 방법이 없습니다.

## 타깃별 경고

| 경고 | 언제 뜨나 | 대처 |
|---|---|---|
| `mcp_agent_in_marketplace_build` | 마켓플레이스인데 에이전트가 MCP 도구나 서버를 씀 | 로컬로 바꾸거나 MCP를 뺀다 |
| `unsupported_agent_field_in_marketplace_build` | 마켓플레이스인데 에이전트에 `hooks`나 기본값 아닌 `permissionMode`가 있음 | 로컬로 바꾸거나 값을 뺀다 |
| `workspace_doc_in_marketplace_build` | 마켓플레이스인데 CLAUDE.md·규칙에 내용이 있음 | 로컬로 바꾸거나 내용을 스킬 본문으로 옮긴다 |
| `workspace_settings_in_marketplace_build` | 마켓플레이스인데 작업 폴더 설정이 있음 | 로컬로 바꾼다 |
| `plugin_root_in_local_build` | 로컬인데 본문에 `${CLAUDE_PLUGIN_ROOT}`·`${CLAUDE_PLUGIN_DATA}`가 있음 | `${ROOT}`로 바꾼다 |
| `missing_mcp_server_def` | 로컬인데 참조한 MCP 서버의 정의가 없음 | 서버 정의를 추가한다 |
| `external_plugin_no_marketplace` | 로컬인데 외부 플러그인에 `@마켓` 표기가 없음 | `플러그인@마켓`으로 선언한다 |
| `unmergeable_settings_json` / `unmergeable_claude_md` | 로컬인데 작업 폴더의 기존 파일이 깨져 있음 | 파일을 고치고 다시 컴파일한다 |

경고는 컴파일을 막지 않습니다. 그래도 대부분 "설정했는데 동작하지 않는다"는 뜻이니 넘기지 마세요.
F7 검증에 안 나오는 컴파일러 경고(`missing_mcp_server_def`, `unmergeable_*` 등)는 MCP `compile_check`로 파일을 쓰지 않고 미리 볼 수 있습니다.

## 어떤 걸 골라야 하나

**로컬을 고르세요 —**

- 에이전트가 MCP 서버를 써야 할 때
- 에이전트에 훅이나 권한 모드(`permissionMode`)를 걸어야 할 때
- 항상 읽히는 지침(CLAUDE.md·규칙)이나 `permissions` 설정이 필요할 때
- 특정 저장소 하나에서 팀이 같이 쓰는 도구일 때(`.claude/`를 커밋해 공유)

**마켓플레이스를 고르세요 —**

- 여러 사람, 여러 작업 폴더에 나눠 줄 때
- 스킬·에이전트 본문과 스킬 훅만으로 충분할 때
- 작업 폴더의 파일을 건드리지 않고 켜고 끌 수 있게 하고 싶을 때

헷갈리면 이렇게 물어보세요. **"에이전트에 MCP·훅·권한 모드가 필요한가? 작업 폴더에 지침이나 설정을 남겨야 하나?"**
하나라도 "예"면 로컬, 모두 "아니오"고 배포할 거라면 마켓플레이스입니다.
새 프로젝트의 기본값은 마켓플레이스입니다.

## 타깃 정하기와 바꾸기

- **처음 만들 때:** 새 프로젝트(Ctrl+N) 창에서 출발점과 함께 빌드 타깃을 고릅니다.
  템플릿에서 시작해도 여기서 고른 타깃이 적용됩니다.
- **나중에 바꿀 때:** 파일 메뉴 → **프로젝트 속성…** → **빌드 타깃** 콤보.
- **MCP로:** `set_project_properties(build_target="local")` 또는 `"marketplace"`. 새로 만들 때는 `new_project(build_target=…)`.

프로젝트 내용은 타깃에 기울지 않게 저장되므로, 바꿔도 **본문이나 설정 값을 고칠 필요가 없습니다.**
바뀌는 것은 다음과 같습니다.

| 마켓플레이스 → 로컬 | 로컬 → 마켓플레이스 |
|---|---|
| CLAUDE.md·규칙·설정 탭이 보인다 | 그 탭들이 숨는다(내용은 남아 있고 경고가 뜬다) |
| 에이전트의 세 필드 잠금이 풀린다 | 세 필드가 잠긴다(값은 남는다) |
| Ctrl+B가 작업 폴더와 설정 파일을 묻는다 | Ctrl+B가 출력 폴더를 묻는다 |
| `${ROOT}` → `${CLAUDE_PROJECT_DIR}` | `${ROOT}` → `${CLAUDE_PLUGIN_ROOT}` |
| fork 에이전트 이름 `플러그인:이름` → `이름` | `이름` → `플러그인:이름` |
| 마켓플레이스용 경고가 사라지고 로컬용 경고가 생길 수 있다 | 그 반대 |

주의할 점 두 가지.

- 이미 컴파일한 결과물은 자동으로 지워지지 않습니다. 로컬로 설치했다가 마켓플레이스로 바꿨다면,
  작업 폴더의 `.claude/skills/` 등에 남은 파일은 직접 정리하세요. 같은 스킬이 두 곳에서 잡힐 수 있습니다.
- 에이전트 편집 탭을 열어 둔 채 타깃을 바꿨다면, 탭을 닫았다 다시 열어야 잠금 상태가 새로 반영됩니다.

## 함께 읽기

- [Daedalus 개념](01-concept.md)
- [레지스트리](02-registry.md)
- [로컬에서만 되는 기능](05-local-only-features.md)
- [MCP로 Daedalus 다루기](06-mcp.md)
