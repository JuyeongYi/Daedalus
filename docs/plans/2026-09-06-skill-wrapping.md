# 스킬 랩핑 (WP-WR) — 다른 플러그인 스킬의 절차 재사용

2026-09-06 사용자 발안 + D1~D4 확정. **1단계 구현 완료(2026-09-06)** —
모델·직렬화·매트릭스·emit·의존성 배선·검증 2종·에디터 잠금·레지스트리/뱃지·
MCP kind 허용(tests/compiler/test_wrapped_skill.py 13건). **2단계 1차 완료(2026-09-06)** — D2 카탈로그
발견(`model/plugin/wrap_catalog.py` + `~/.daedalus/plugin_roots.json`), GUI
"랩핑 스킬 카탈로그" 창(플러그인별 트리·생성·✔), MCP 4종
(list_wrappable_skills/list_plugin_roots/add_plugin_root/remove_plugin_root) +
create_skill(source=), 빌드 배선 보증 테스트(마켓 dependencies·로컬
enabledPlugins·settings 파일 선택·멱등·dry-run·out_dir 없는 dry-run의 bare
경고). 잔여: 에디터 소스 콤보·미리보기, dangling_wrapped_source,
wrapped_source_has_workflow.

## 동기

재사용 축의 완성: declarative(지식 공유)·reference(문서 공유)는 있는데 **절차
재사용**이 없다 — 남의 플러그인 스킬을 쓰려면 본문을 복사해 포크하는 수밖에
없고 원본과 조용히 드리프트한다. 랩핑은 "본문의 정본은 저쪽, 워크플로
위치·배선은 우리 것"으로 가른다.

## 스펙 (사용자 확정)

새 스킬 종류 **WrappedSkill** (5번째):

- `source`: 외부 스킬 참조 — **편집 가능한 것은 프론트매터와 연결(그래프
  배선·transfer_on)뿐, 본문은 수정 불가**(읽기 전용 — 소스가 정본).
- **D1 = 런타임 참조 (최종 확정 2026-09-06)**: 컴파일 산출 본문 = 우리
  그래프 유도 단락 + "skill `<source>`를 따르라" 지시. 소스 스킬은 **자기
  플러그인에서** 로드·실행되므로 경로 변수(${CLAUDE_PLUGIN_ROOT} 등)가 소스
  자신의 경로로 풀린다 — 긁어오기안의 변수 오동작(구 D5)이 소멸해 이쪽으로
  재확정. 프론트매터도 각자 자기 것이 적용되는 자연 의미론(구 D3의 "맨 앞만"
  전제 불필요).
- **의존성 배선 (사용자 확정)**: 플러그인 의존성 선언은 **마켓플레이스
  플러그인에서만 유효**하다 — 그 전제로:
  - MARKETPLACE 빌드: 소스 플러그인을 **plugin.json 매니페스트에 의존성으로
    추가**(compile_plugin_manifest 확장 — 정확한 키는 구현 시 공식 스펙
    확인 필수, A4 관례: 추측 emit 금지).
  - LOCAL·MARKETPLACE 공통: **settings에 `enabledPlugins` 추가** — LOCAL은
    WP-WS 베이크(wire_workspace 깊은 병합 — 리스트 union이라 기존 기계 그대로)
    로 직접 기입하고, MARKETPLACE는 설정 파일을 쓸 수 없으므로 요구 환경
    단락에 활성화 안내를 명시한다.
- **D2 = 카탈로그 방식**: 소스 발견은 등록된 루트에서. `~/.claude` 내 설치
  플러그인 폴더, 마켓플레이스 폴더 등 **플러그인 루트 경로들을 카탈로그에
  등록**해 두면(도구/MCP 카탈로그 관례 — 전역 + 프로젝트, 파일 스킵 시 stderr)
  발견기가 각 루트의 스킬(SKILL.md)을 훑어 후보 목록을 만든다. 에디터
  콤보/MCP가 이 후보에서 source를 고른다. 등록 파일 형식·위치는 구현 결정
  (기존 `~/.daedalus/catalogue/` 확장 vs 별도 파일 — 관례 우선).
- **D3 = 덮어쓰기(승계 없음)**: 랩퍼의 프론트매터는 백지에서 시작하는 우리
  소유다 — 소스 값 자동 승계 없음. 런타임 참조라 각 스킬이 자기 프론트매터로
  동작한다(랩퍼가 제어하는 것은 랩퍼 노드 자신) — 이 의미론을 에디터 안내에
  명시한다.
- **D4 = 경고**: 소스 부재(카탈로그에서 해소 불가)는 컴파일 게이트 에러가
  아니라 **경고**(`dangling_wrapped_source` — 파일시스템 판정이라 컴파일러
  emit, `dangling_file_ref` 관례·`_EXTERNALLY_EMITTED_RULES` 등재).

## 설계 스케치

- 모델: `WrappedSkill(Skill)` + `WrappedSkillConfig` — source(문자열 참조),
  transfer_on 소유(분기는 우리 그래프의 것). body 필드는 항상 빈 값(직렬화
  왕복에서도) — 소스 미리보기는 뷰가 카탈로그에서 읽어 표시만.
- 필드 매트릭스: 새 kind 열. user_invocable 류는 랩퍼 소유(OPTIONAL).
- 에디터: 프론트매터+transfer_on 패널 정상, 본문 패널 읽기 전용(소스 본문
  회색 미리보기 + "본문의 정본은 <source>" 안내). 소스 콤보는 카탈로그 후보.
- 캔버스: 🔗 뱃지 + 소스 툴팁. 배치·전이 규칙은 ProceduralSkill과 동일.
- 컴파일: 프론트매터(우리 것) + 재개/진입 단락 + "Follow skill `<source>`"
  지시(영어 문구는 A12 — 컴파일 생성 텍스트) + 다음 단계/진행 기록 +
  의존성 배선(위 항목). **충돌 검출**: 컴파일 시 소스 본문(카탈로그에서
  읽기 가능)에 우리 자동 헤딩(## Next Steps 등)이 보이면
  `wrapped_source_has_workflow` 경고 — 소스가 자기 워크플로 지시를 가진
  다이달로스 산출이면 우리 그래프 지시와 이중이 된다.
- 검증: `dangling_wrapped_source`(경고) + 소스 이름 형식 검사.
- MCP 패리티(같은 WP): `create_skill(kind="wrapped", source=)`,
  `set_component_field(source=)`, `list_wrappable_skills()`(카탈로그 후보 조회).
- 직렬화: kind 태그 왕복, 구버전 키 부재 하위 호환 게이트.

## 남은 구현 결정

- 카탈로그 등록 파일의 정확한 형식/위치 (기존 catalogue 확장 여부)
- 소스 참조 문자열 규격 (`<플러그인>:<스킬>` 제안)
- plugin.json 의존성 선언의 정확한 키/형식 — 공식 스펙 확인 후 emit(A4 관례)
- `enabledPlugins` 값 형식(플러그인 식별자 규격) — settings 스키마
  (tests/fixtures/specs 스냅샷) 대조

## 재설계 (사용자 확정 2026-09-06 저녁) — 사용 선언 중심

1. 용어: "플러그인 루트" → **마켓플레이스 폴더**. 전역 등록 파일
   `plugin_roots.json` → `external_marketplaces.json`.
2. **사용 선언은 프로젝트 단위**: `PluginProject.external_plugins: list[str]`
   ("이름[@마켓]", 직렬화 왕복). 카탈로그 창의 플러그인 체크박스 = 사용 선언
   (SetAttrCmd — undo). 전역 excluded(제외 목록) 개념은 이것으로 대체·퇴역.
3. **배선의 단일 진실은 선언**: dependencies(MARKETPLACE)/enabledPlugins
   (LOCAL)는 external_plugins에서만 나온다 — 랩핑 스킬 source 스캔 퇴역.
   랩핑 스킬은 워크플로 단계로 놓을 때만 만들면 되고(활성화된 플러그인의
   스킬은 CC가 네이티브 로드), 생성 시 미선언 플러그인은 선언까지 1 undo로
   자동 명시(`actions/creation.create_wrapped_skill` — GUI·MCP 공유).
4. 정합 경고: `unused_external_plugin`(선언·미참조 — 경고만, 배선은 그대로),
   `undeclared_external_plugin`(참조·미선언), `external_plugin_no_marketplace`
   (bare 선언 — 컴파일러 emit). `wrapped_source_no_marketplace`는 퇴역.
5. **외부 플러그인의 동봉 .mcp.json 활용**: 서버 이름을 발견해
   (`CataloguedPlugin.mcp_servers`) 에이전트 mcp_servers 자동완성 후보 +
   LOCAL 컴파일 `provided_server_names` 주입(missing_mcp_server_def 오탐
   억제)에 쓴다. 개별 도구 목록은 미지원이라 tools 후보에는 넣지 않는다.

## 인보크 표기 (교차 확인 2026-09-06)

크로스 플러그인 스킬 지목의 공식 표기는 `/플러그인이름:스킬이름`이고 플러그인
이름에 마켓 표기가 붙지 않는다 — `@마켓`은 설치 식별자로 dependencies(매니페스트)
/enabledPlugins(settings) 전용이다. `_wrapped_procedure_section`이 이 표기를
그대로 배출한다(invoke `/other:code-review`). 근거: 공식 plugins-reference +
settings 문서, 백그라운드 조사 에이전트 보고(dependencies는 {name, version}
객체형·전이적 해소·의존 대상 자동 활성화까지 확인 — 우리는 문자열형만 배출).

