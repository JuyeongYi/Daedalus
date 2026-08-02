# WP-RS — 작업 재개: 플러그인 FSM 진행 상태 저장

## 배경

컴파일된 플러그인은 데이터 상태(블랙보드 `state/<Class>.json`)는 저장하지만
**진행 상태(플러그인 워크플로 위치)**는 저장하지 않아 세션이 끊기면 재개가 불가능
하다. 사용자 확정 설계: 저장 단위는 **플러그인 FSM(프로젝트 그래프)의 위치**다 —
각 스킬 내부 FSM 상태가 아니다.

## 규약: `state/__progress__.json`

```json
{
  "plugin": "<plugin name>",
  "current": "<배치 스킬/에이전트 이름>",
  "completed": ["<이름>", ...],
  "note": "재개 세션이 맥락 없이 읽어도 이어갈 수 있는 한 줄",
  "updated": "<ISO8601>"
}
```

- 단일 파일 (한 작업 프로젝트에 한 흐름 가정). `plugin` 필드로 타 플러그인 잔재 감지.
- 예약 이름 `__progress__` — 블랙보드 DynamicClass와 충돌 불가(이름 규약상 사용자
  클래스는 `__` 접두를 쓰지 않음 — 컴파일 게이트/검증에 강제까지는 불요, 문서만).

## Part A — compiler: 배출 단락 3종 (emit.py)

전부 결정적 문구. `compile_skill(skill, project=...)`에서 **프로젝트 그래프에
배치된 전역 ProceduralSkill**에만 배출 (placement 판정은 기존 "다음 단계" 단락과
동일한 skill_ref identity 로직 재사용).

1. **재개 프리앰블** — 본문(body) 블록 *앞*, 프론트매터 직후:
   ```
   ## 작업 재개
   시작 전에 `state/__progress__.json`을 확인하라.
   - `current`가 이 스킬(`<이름>`)이면: `note`를 참고해 중단 지점부터 이어서 진행하라.
   - `current`가 다른 스킬이면: 워크플로 위치가 그쪽이다 — 진행을 멈추고 사용자에게 확인하라.
   - 파일이 없으면: `{"plugin": "<플러그인>", "current": "<이름>", "completed": [], ...}`로 생성하고 진행하라.
   ```
2. **"다음 단계" 단락에 갱신 규칙 합류** — 기존 단락 끝에 1줄:
   ```
   전이 시 `state/__progress__.json`을 갱신하라 — 이 스킬을 `completed`에 추가하고
   `current`를 다음 대상으로, `note`에 인계 한 줄을 남겨라.
   ```
   (에이전트 위임 배치도 기존 규약대로 호출자 스킬 쪽에서 갱신 — 에이전트 .md 무변경.)
3. **터미널 배치**(outgoing 0개): "다음 단계" 대신:
   ```
   ## 작업 완료
   이 스킬이 워크플로의 마지막 단계다. 완료 시 `state/__progress__.json`의
   `current`를 `"done"`으로 바꾸고 `note`에 결과 요약을 남겨라.
   ```

**TransferSkill**: 본문 끝에 1단락 — "이 전이 스킬 실행 중에는
`state/__progress__.json`의 `note`에 전이 맥락을 기록하라" (전이 도중 중단 대비).

미배치 스킬·에이전트 .md·로컬 스킬: 배출 없음.

## Part B — SessionStart 훅 (기본 포함 + 토글)

1. `PluginProject`에 `emit_progress_hook: bool = True` 필드 (직렬화 왕복 포함,
   구버전 키 부재 → True).
2. ProjectPropertiesDialog에 체크박스 "세션 시작 시 진행 상태 자동 주입 (SessionStart 훅)".
3. 컴파일: True이고 **프로젝트 그래프에 placement가 1개 이상**이면 hooks.json에
   SessionStart 훅 합류:
   ```json
   {"type": "command", "command": "cat state/__progress__.json 2>/dev/null || true"}
   ```
   (기존 compile_hooks_json 경로에 합성 훅으로 합류 — hook_library 오염 금지,
   컴파일 시점 합성. 같은 이벤트에 사용자 훅이 있으면 공존.)
   placement 0개면 훅 미배출(재개 개념 없음).

## Part C — 테스트

1. 배치 스킬 SKILL.md: 프리앰블 존재·이름 삽입, 다음 단계 갱신 규칙, 터미널 완료 단락.
2. 미배치 스킬/에이전트 .md/로컬 스킬: 단락 부재.
3. TransferSkill note 단락.
4. hooks.json: 기본 SessionStart 합류 / emit_progress_hook=False 미배출 /
   placement 0개 미배출 / 사용자 SessionStart 훅과 공존.
5. 직렬화: emit_progress_hook 왕복 + 구버전 기본값 True.
6. 결정성: 같은 프로젝트 2회 컴파일 바이트 동일.

## 비목표

- 스킬 내부 FSM 상태 저장 (사용자 확정 — 하지 않는다)
- 진행 파일 스키마의 JSON Schema 배출(schemas.json 합류) — v1 문서 규약만
- 병행 워크플로(스킬별 진행 파일)

## 작업 관례

- 브랜치 `wp-rs` (이미 생성돼 있으면 체크아웃만). master 직접 작업 금지.
- 테스트는 반드시 `python -m pytest tests/ -q` (pytest 직접 실행 불가).
- Pyright 진단은 스테일이 잦다 — 런타임 테스트로 판정.
- 커밋은 Part 단위 이상, 메시지는 한국어. push 금지.
- Qt 바인딩은 PySide6.
- CLAUDE.md 갱신: 컴파일 정책에 작업 재개 단락(프리앰블/갱신 규칙/터미널/훅) 반영.
