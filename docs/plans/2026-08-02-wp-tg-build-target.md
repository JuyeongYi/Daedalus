# WP-TG — 빌드 타깃 (마켓플레이스 플러그인 / 로컬 플러그인)

## 배경·확정 설계 (사용자 결정)

MCP를 쓰는 에이전트는 CC 정책상 플러그인 배포가 불가능해(`mcpServers` 등
프론트매터 미지원) 사람들이 파일 복사로 우회한다. 에이전트별 타입 대신 **프로젝트
수준 빌드 타깃**으로 가른다(로컬 에이전트 타입안은 폐기 — 이 설계가 상위 개념).

- **프로젝트 생성 시(Ctrl+N) 둘 중 하나를 고르게 한다**. 이후 프로젝트 속성에서
  변경 가능. **직렬화에 저장**.
- LOCAL 빌드는 **복사까지 해주는 설치 스크립트를 동봉**한다.

## Part A — 모델·직렬화

1. `model/plugin/enums.py`에 `BuildTarget(Enum)`: `MARKETPLACE = "marketplace"`,
   `LOCAL = "local"`.
2. `PluginProject.build_target: BuildTarget = BuildTarget.MARKETPLACE`.
3. serialize: `.value` 왕복, 구버전 키 부재 → MARKETPLACE(경고 없음).

## Part B — UI

1. **신규 프로젝트 흐름**(`app._new_project`): 이름 입력 전(또는 직후)에 타깃
   선택 — QInputDialog.getItem("빌드 타깃", ["마켓플레이스 플러그인", "로컬
   플러그인"]) 또는 동급 다이얼로그. 취소 시 프로젝트 생성 취소.
2. `ProjectPropertiesDialog`에 빌드 타깃 콤보(변경 가능, `apply_to` 반영).
3. 타이틀/상태 표기는 선택(비목표 아님, 여유 있으면).

## Part C — 컴파일

**MARKETPLACE (기본)**: 현행과 **바이트 동일** — 하위 호환 게이트(기존 테스트
전부 무수정 통과 + 구버전 파일 로드 산출 불변).

**LOCAL**: 프로젝트 `.claude/` 반입형 —

1. `plugin.json` **미생성** (`.claude-plugin/` 디렉토리 자체 없음).
2. `skills/`/`agents/`/`files/`/`hooks/hooks.json`은 동일 레이아웃으로 배출.
3. **파일 참조 치환**: 스킬·에이전트 본문 배출 시
   `${CLAUDE_PLUGIN_ROOT}/files/` → `${CLAUDE_PROJECT_DIR}/files/` 문자열 치환
   (본문 저장 정본은 마켓플레이스 형태 하나 — WP-FR 재작업 없음).
4. **INSTALL.md 생성**: 산출 구조 설명 + 설치 스크립트 사용법 + hooks 수동 병합
   안내(settings.json의 hooks 섹션 — 자동 병합은 하지 않음, 파괴 위험).
5. **설치 스크립트 동봉** (복사까지 — 사용자 확정): `install.ps1`(PowerShell)과
   `install.sh`(POSIX) 두 벌을 컴파일러가 결정적 텍스트로 생성. 동작:
   - 인자: 대상 프로젝트 경로 (필수, 미지정 시 사용법 출력 후 종료)
   - `skills/*` → `<대상>/.claude/skills/`, `agents/*.md` → `<대상>/.claude/agents/`,
     `files/*` → `<대상>/files/` 복사(디렉토리 생성 포함, 기존 파일은 덮어씀을
     명시적으로 경고 후 진행 — `-Force`/`cp -r`)
   - hooks/hooks.json은 복사하지 않고 "settings.json에 수동 병합" 안내 출력
6. LOCAL에서 에이전트 프론트매터의 MCP 제약 해제는 **검증 규칙 차원**(Part D) —
   v1 배출 자체는 현행 필드 규칙 그대로(mcpServers 인라인 정의 배출은 서버 정의
   소스가 필요해 후속 — 카탈로그 서버 정의 부활과 함께).

## Part D — 검증 (타깃 인지, WARNING_RULES 등재)

1. `mcp_agent_in_marketplace_build` — build_target=MARKETPLACE인데 에이전트
   `config.tools`에 `mcp__` 도구가 있거나 `mcp_servers` 선언이 있으면 경고:
   "CC는 플러그인 배포 에이전트의 MCP 사용을 지원하지 않는다 — 로컬 플러그인
   빌드로 전환하거나 제거하라." (LOCAL이면 무경고 — "얘만 쓸 수 있게".)
2. `plugin_root_in_local_build` — build_target=LOCAL인데 본문에
   `${CLAUDE_PLUGIN_ROOT}`가 **files/ 참조 이외 용도**로 남아 있으면 경고
   (files/ 참조는 컴파일이 자동 치환하므로 제외).

## Part E — 테스트

1. 직렬화: build_target 왕복 + 구버전 부재 → MARKETPLACE.
2. UI: 신규 프로젝트 타깃 선택 반영(다이얼로그 몽키패치), 속성 다이얼로그 변경.
3. 컴파일 MARKETPLACE: 기존 산출 바이트 불변(하위 호환 게이트).
4. 컴파일 LOCAL: plugin.json 부재, INSTALL.md·install.ps1·install.sh 존재·결정적,
   파일 참조 치환(`${CLAUDE_PROJECT_DIR}/files/...`), hooks.json 존재.
5. 설치 스크립트 내용: 대상 경로 인자 처리·복사 명령·hooks 안내 문구 포함
   (실행 테스트는 tmp_path에서 ps1은 스킵 가능 — 텍스트 검증 위주, sh 실행은
   bash 가용 시).
6. 검증 규칙 2종: 발화/비발화 각 타깃에서 + severity 등재.
7. `python -m pytest tests/ -q` 전체 통과 (회귀 0).

## 비목표

- 로컬 에이전트 타입(폐기), mcpServers 인라인 정의 배출(후속 — 카탈로그 서버 정의)
- settings.json hooks 자동 병합
- 제3의 타깃 추가 (enum 확장 여지만 남김)

## 작업 관례

- 브랜치 `wp-tg`. master 직접 작업 금지. `python -m pytest tests/ -q`.
- Pyright 스테일 — 런타임 판정. 커밋 한국어, push 금지. PySide6, QTest ASCII.
- CLAUDE.md 갱신: build_target(모델·직렬화·생성 흐름), 컴파일 정책에 LOCAL 절,
  검증 규칙 표 2종 추가.
