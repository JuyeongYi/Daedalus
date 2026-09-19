# daedalus/compiler/project_compiler.py
"""프로젝트 컴파일 — 게이트 + 파일 쓰기 (순수 stdlib, Qt 무관).

CC 플러그인 출력 구조 (project.build_target == MARKETPLACE, 기본):
    <out>/.claude-plugin/plugin.json            # 플러그인 매니페스트 (항상 생성)
    <out>/skills/<skill-name>/SKILL.md          # 스킬 4종
    <out>/agents/<agent-name>.md                # 에이전트

LOCAL 빌드(WP-TG/WP-MW) — **컴파일이 곧 설치**다. out_dir는 스테이징이 아니라
대상 **작업 폴더**이고, 산출물이 CC가 실제로 읽는 위치에 바로 놓인다:
    <out>/.claude/skills/<skill-name>/SKILL.md    # CC 프로젝트 스킬 위치
    <out>/.claude/agents/<agent-name>.md          # CC 프로젝트 에이전트 위치
    <out>/files/, <out>/schemas/, <out>/hooks/scripts/  # 본문이 ${CLAUDE_PROJECT_DIR}/…로 참조
    <out>/.mcp.json                    # mcpServers 병합 (mcp_server_defs 소스, 생성/수정)
    <out>/.claude/settings.local.json  # enabledMcpjsonServers + hooks 병합 (생성/수정)
plugin.json·hooks/hooks.json·설치 스크립트는 만들지 않는다 — 별도 설치 단계가
없기 때문이다. JSON 병합은 추가만 한다(기존 항목 보존, 같은 이름 서버는 갱신,
동일 hooks 그룹은 중복 삽입하지 않아 재컴파일이 멱등). ``${ROOT}``는
``${CLAUDE_PROJECT_DIR}``로 확장된다(본문 저장 정본은 불변).

compile_project는 파일 쓰기 전에 전체 산출 경로 집합을 계산하고, 중복이 있으면
컴파일을 거부한다(조용한 덮어쓰기 방지). **계획도 쓰기도 이 모듈이 하지 않는다**
(WP-5, 이동만): 산출 종류 하나가 ``compiler/units/``의 `CompileUnit` 하나이고,
이 모듈에 남은 것은 **게이트와 두 단계 루프**다 —

  ① `Phase.WRITE` — 산출 파일 쓰기·복사 (계획 순서)
  ② 드라이버가 소유한 진단 스캔 2건 (dangling_file_ref/dangling_skill_file_ref)
  ③ `Phase.INSTALL` — LOCAL 설치 배선 + `.claude/CLAUDE.md` 구역

계획 쪽 이름(`SKILL_FILES_DIRNAME` 등)은 종전대로 전부 재-export한다.

컴파일 게이트(정책 8 + 강화 2종):
  - Validator.validate_project의 에러(is_warning=False) 1건 이상 → 거부.
  - 산출 파일/디렉토리 이름이 되는 컴포넌트(스킬·에이전트)의
    이름이 `^[a-z0-9][a-z0-9-]*$` 불일치 → 컴파일 에러로 승격해 거부.
    (F7 검증기에서는 경고 등급 유지 — 편집 중에는 경고가 맞다. 게이트만 엄격.)
  - 산출 경로 충돌 → 거부 + 충돌 경로/원인 컴포넌트 보고.
  - 서로 다른 훅이 같은 스크립트 파일명으로 슬러그되면 → 거부(duplicate_hook_script).
경고는 통과(결과에 동봉).

dry-run(G3): ``compile_project(..., dry_run=True)``는 **파일을 하나도 쓰지
않는다** — 텍스트 생성·계획·스캔·LOCAL 병합 판정을 전부 돌리고 쓰기/복사/병합만
생략한다. 컴파일러가 emit하는 경고(dangling_file_ref, unknown_skill_files_dir,
dangling_skill_file_ref, missing_mcp_server_def, unmergeable_settings_json,
unmergeable_claude_md, rule_body_frontmatter)는 Validator에 나오지 않아 실제
컴파일 전에는 보이지 않았다 — MCP `compile_check`가 이 경로로 그것을 보여준다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# 산출 계획은 compiler/plan.py → compiler/units/로 분해했다(WP-FK2 C0 · WP-5,
# 이동만). 여기서 재-export해 기존 임포트 경로
# (`from ...project_compiler import SKILL_FILES_DIRNAME` 등)를 지킨다.
from daedalus.compiler.plan import (  # noqa: F401 — 재-export 파사드
    SKILL_FILES_DIRNAME,
    _OUTPUT_NAME_RE,
    _hook_script_name_conflicts,
    _is_link_like,
    _iter_tree_files,
    _plan_outputs,
    _PlannedOutput,
    _skill_dir_name,
)
from daedalus.compiler.token_report import TokenReport
from daedalus.compiler.units.base import Phase
from daedalus.compiler.units.context import CompileContext
from daedalus.compiler.units.registry import PLANNER, unit_for
from daedalus.compiler.units.sink import OutputSink
from daedalus.model.plugin.roles import Bucket
from daedalus.model.validation import ValidationError, Validator


# 스킬/에이전트 body에서 파일 참조 토큰을 스캔하는 패턴 — MarkdownEditor의
# 드롭 삽입(view/widgets/markdown/providers.py `_file_ref_token`)이 만드는 형식과
# 동일: 타깃 중립 ``${ROOT}/files/<상대경로>`` (WP-RT).
#
# 두 형태를 모두 인식한다:
#   1. `<${ROOT}/files/공백 있는 경로>` — 꺾쇠로 감싼 형태(드롭이 공백 경로에
#      붙인다). 닫는 꺾쇠까지가 경로 — 공백에서 끊지 않는다.
#   2. `${ROOT}/files/경로` — 맨 형태. 공백·마크다운 구분자(`)]`"'<>,;`)에서
#      끊고, 문장 종결 마침표는 뒤에서 트림한다.
#
# 스캔은 ${ROOT} 확장 **전** 본문(정본)을 대상으로 하므로 여기서 타깃을 알 필요가
# 없다 — 구버전 토큰은 로드 시 이미 ${ROOT}로 변환되어 있다.
_FILE_REF_ANGLE_RE = re.compile(r"<\$\{ROOT\}/files/([^>]+)>")
_FILE_REF_BARE_RE = re.compile(r"\$\{ROOT\}/files/([^\s)\]`\"'<>,;]+)")

# 컴파일 게이트 전용 rule 분류 표 (등급 의도의 단일 진실).
# 이 rule들은 validation.py의 WARNING_RULES에 없으므로 is_warning이 자동으로
# False(에러)가 된다 — 게이트 rule은 전부 에러 등급이 의도다. 새 게이트 rule을
# 추가할 때 반드시 이 집합에도 등록하라 (테스트가 발급 rule ⊆ 이 집합을 고정).
COMPILER_ERROR_RULES: frozenset[str] = frozenset({
    "compile_invalid_component_name",
    "compile_output_path_conflict",
    "duplicate_hook_script",
})


# 본문의 스킬 파일 참조 토큰 스캔 패턴 — _FILE_REF_*와 동일한 두 형태.
_SKILL_FILE_REF_ANGLE_RE = re.compile(r"<\$\{CLAUDE_SKILL_DIR\}/([^>]+)>")
_SKILL_FILE_REF_BARE_RE = re.compile(r"\$\{CLAUDE_SKILL_DIR\}/([^\s)\]`\"'<>,;]+)")


@dataclass
class CompileResult:
    """컴파일 결과.

    written: 실제로 쓴 파일 경로 목록. **dry_run이면 "쓰였을" 경로**다
        (파일은 하나도 만들어지지 않는다).
    errors: 컴파일을 거부시킨 에러(검증 에러 + 컴파일 게이트 에러). 비어 있으면 성공.
    warnings: 통과한 경고(결과에 동봉).
    skipped: (이유, 컴포넌트 이름) 목록 — 거부 시 쓰지 못한 항목 등.
    copied_files: 트리 복사로 실제 복사된 파일 경로 목록 — 공용 files/(WP-FR)와
        스킬별 skill-files/(WP-SF)를 **함께** 담는다. 소스 디렉토리가
        미지정이거나 실존하지 않으면 빈 리스트. dry_run이면 복사됐을 경로.
    dry_run: 이 결과가 검사 전용 실행(G3)이면 True — 디스크는 불변이다.
    token_report: 산출 텍스트의 토큰 추정 리포트 (A5-lite). 게이트에 막혀
        아무것도 쓰지 않았으면 비어 있다. **표시 전용**이다 — 산출 파일
        텍스트는 이 리포트의 유무와 무관하게 불변이고, 임계 초과 고지는
        검증 규칙이 아니라 정보성 문구다(`token_report.notice()`).
    """
    written: list[Path] = field(default_factory=list)
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    copied_files: list[Path] = field(default_factory=list)
    token_report: TokenReport = field(default_factory=TokenReport)
    dry_run: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors


#: 본문이 토큰의 **형식을 설명할 때** 쓰는 자리표시자 — 실제 파일 이름이 아니다.
#: 스킬 저작 지침은 "`${ROOT}/files/...` 토큰을 쓴다"처럼 쓰기 마련이라, 이것을
#: 참조로 세면 문서를 쓸 때마다 없는 파일 경고가 난다(실사고 2026-09-07:
#: graph-author·graph-tools 본문이 매 컴파일 오탐을 냈다).
#: 코드 표기(백틱) 전체를 스캔에서 빼지 않는 이유는 그 반대가 더 나쁘기
#: 때문이다 — 진짜 파일 참조도 보통 인라인 코드로 쓰므로 대부분을 놓친다.
#: `<이름>` 꼴은 여기서 다루지 않는다 — 맨 형태 정규식이 `<`를 경로 문자에서
#: 제외해 애초에 매치되지 않는다(그 분기를 두면 도달 불가한 죽은 코드가 된다).
_PLACEHOLDER_REF_RE = re.compile(r"^[.…]*$")


def _is_placeholder_ref(rel: str) -> bool:
    """참조가 아니라 자리표시자인가 — 빈 값이거나 점·말줄임표뿐."""
    return bool(_PLACEHOLDER_REF_RE.match(rel))


def _scan_dangling_file_refs(project, files_dir: Path) -> list[ValidationError]:
    """스킬/에이전트 body에서 파일 참조 토큰을 스캔해 files_dir에
    실존하지 않는 참조를 `dangling_file_ref` 경고로 반환한다.

    Validator가 아닌 컴파일러 소관이다 — 검증기는 파일시스템 무접근 순수성을
    유지한다.
    """
    warnings: list[ValidationError] = []

    def _iter_refs(body: str):
        """꺾쇠 형태를 먼저 소비하고, 남은 텍스트에서 맨 형태를 찾는다."""
        text = body or ""
        for match in _FILE_REF_ANGLE_RE.finditer(text):
            yield match.group(1)
        stripped = _FILE_REF_ANGLE_RE.sub("", text)
        for match in _FILE_REF_BARE_RE.finditer(stripped):
            # 문장 종결 마침표는 경로가 아니다 (Windows는 후행 점을 무시해
            # 가려지지만 리눅스 컴파일에서는 오탐이 된다)
            yield match.group(1).rstrip(".")

    def scan(label: str, subject: object, body: str) -> None:
        for rel in _iter_refs(body):
            if _is_placeholder_ref(rel):
                continue  # 토큰 형식 설명 — 참조가 아니다
            candidate = files_dir.joinpath(*rel.split("/"))
            if candidate.exists():
                continue
            warnings.append(ValidationError(
                rule="dangling_file_ref",
                message=(
                    f"{label}의 본문이 참조하는 파일이 files/ 아래에 없습니다: "
                    f"${{ROOT}}/files/{rel}"
                ),
                source=rel,
                subject=subject,
            ))

    for skill in project.skills:
        scan(f"스킬 '{skill.name}'", skill, skill.body)
    for agent in project.agents:
        scan(f"에이전트 '{agent.name}'", agent, agent.body)
    return warnings


def _scan_dangling_skill_file_refs(
    project, skill_files_dir: Path,
) -> list[ValidationError]:
    """스킬 body의 `${CLAUDE_SKILL_DIR}/…` 참조를 스캔해 그 스킬의 skill-files
    폴더에 실존하지 않는 참조를 `dangling_skill_file_ref` 경고로 반환한다 (WP-SF).

    검사 기준은 **그 스킬 자신의** 폴더다 — 스킬 A의 파일을 스킬 B 본문에서
    참조하는 실수(런타임에 B의 SKILL_DIR에는 그 파일이 없다)도 여기서 잡힌다.
    에이전트 본문의 이 토큰은 Validator의 `skill_dir_token_in_agent`가 짚는다
    (파일시스템 무접근 검사라 검증기 소관).
    """
    warnings: list[ValidationError] = []

    def _iter_refs(body: str):
        text = body or ""
        for match in _SKILL_FILE_REF_ANGLE_RE.finditer(text):
            yield match.group(1)
        stripped = _SKILL_FILE_REF_ANGLE_RE.sub("", text)
        for match in _SKILL_FILE_REF_BARE_RE.finditer(stripped):
            yield match.group(1).rstrip(".")

    def scan(label: str, subject: object, body: str, dir_name: str) -> None:
        skill_root = skill_files_dir / dir_name
        for rel in _iter_refs(body):
            if _is_placeholder_ref(rel):
                continue  # 토큰 형식 설명 — 참조가 아니다
            candidate = skill_root.joinpath(*rel.split("/"))
            if candidate.exists():
                continue
            warnings.append(ValidationError(
                rule="dangling_skill_file_ref",
                message=(
                    f"{label}의 본문이 참조하는 파일이 "
                    f"{SKILL_FILES_DIRNAME}/{dir_name}/ 아래에 없습니다: "
                    f"${{CLAUDE_SKILL_DIR}}/{rel} — 다른 스킬의 파일을 참조했다면 "
                    f"그 파일은 이 스킬의 SKILL_DIR에 실리지 않습니다."
                ),
                source=rel,
                subject=subject,
            ))

    for skill in project.skills:
        # 버킷이 곧 타입 가드다(Q31) — **산출 판정이 아니다**: 참조 용도·비활성
        # 랩퍼도 본문을 갖고, 그 본문의 깨진 `${CLAUDE_SKILL_DIR}` 참조는
        # 여전히 짚어야 한다(`emits_output()`으로 걸면 경고가 조용히 사라진다).
        if skill.BUCKET is Bucket.SKILLS:
            scan(
                f"스킬 '{skill.name}'", skill,
                skill.body, _skill_dir_name(skill.name),
            )
    return warnings


def compile_project(
    project, out_dir: Path | str | None = None,
    files_dir: Path | str | None = None,
    extra_server_defs: dict[str, dict] | None = None,
    skill_files_dir: Path | str | None = None,
    resolved_hooks: dict | None = None,
    dry_run: bool = False,
    settings_filename: str = "settings.json",
    provided_server_names: set[str] | frozenset[str] | None = None,
) -> CompileResult:
    """프로젝트를 out_dir에 컴파일한다.

    settings_filename(WP-WS, LOCAL 전용): `.claude/` 밑 설정 산출 파일 —
    "settings.json"(기본, 공유) 또는 "settings.local.json"(개인). 빌드 시
    호출자가 고른다(GUI 컴파일 다이얼로그 / MCP compile_check 파라미터).

    provided_server_names(WP-WR): 사용 선언된 외부 플러그인이 자기 `.mcp.json`
    으로 **제공하는** MCP 서버 이름들 — 호출 환경(앱)이 카탈로그를 훑어
    주입한다(컴파일러는 파일시스템을 읽지 않는다 — resolved_hooks와 같은
    경계). 여기 든 이름은 프로젝트에 정의가 없어도 `missing_mcp_server_def`
    경고를 내지 않는다: 플러그인 활성화가 그 서버를 함께 가져오므로 이
    프로젝트가 .mcp.json에 배선할 것이 없다.

    게이트: 검증 에러 + 게이트 강화 에러(이름 규약·경로 충돌)가 1건이라도 있으면
    파일을 쓰지 않고 거부한다. 경고만 있으면 통과시키고 warnings에 동봉한다.

    dry_run(G3, 선택): **파일을 하나도 쓰지 않는다** — 산출 텍스트 생성·계획
    수립·경로 스캔·LOCAL 병합 판정은 전부 그대로 돌리고 쓰기·복사·병합만
    생략한다. 그래서 컴파일러가 emit하는 경고(`dangling_file_ref`/
    `unknown_skill_files_dir`/`dangling_skill_file_ref`/`missing_mcp_server_def`/
    `unmergeable_settings_json`/`unmergeable_claude_md`/`rule_body_frontmatter`)를
    실제 컴파일과 같은 판정으로 미리 볼 수 있다 — 이 경고들은
    `Validator.validate_project`에 나오지 않아 컴파일 전에는 보이지 않았다.
    `written`/`copied_files`는 "쓰였을/복사됐을" 경로 목록이 된다.

    **out_dir는 dry_run일 때만 생략할 수 있다.** 생략하면 계획 경로가 상대
    경로가 되고, 대상 폴더를 읽어야 판정하는 경고(`unmergeable_settings_json`/
    `unmergeable_claude_md`)는 판정 자체를 건너뛴다 — files_dir/skill_files_dir
    미지정 시 그 스캔을 생략하는 것과 같은 None 규약이다.

    files_dir(WP-FR, 선택): 실존 디렉토리면 <out_dir>/files/로 트리 복사하고
    (게이트 통과 시에만), 스킬/에이전트 body의 파일 참조 토큰을 스캔해 실존하지
    않는 참조를 `dangling_file_ref` 경고로 추가한다(files_dir가 None이면 스캔
    생략 — 기존 산출물/문자열 불변, 하위 호환).

    extra_server_defs(WP-MW, 선택): 호출 환경이 아는 MCP 서버 정의(이름 → .mcp.json
    객체). LOCAL 설치 배선에서 `project.mcp_server_defs`의 **빈 자리를 채운다**
    (프로젝트에 명시된 정의가 항상 우선). Daedalus 앱이 자기 자신의 daedalus
    서버 접속 정보를 여기로 주입한다 — 앱이 이미 아는 것을 사용자에게 등록시키지
    않기 위해서다. 컴파일러는 환경을 추측하지 않으므로 파라미터로 받는다(결정성).

    skill_files_dir(WP-SF, 선택): 스킬별 동봉 파일 루트(`skill-files/`). 하위
    `<스킬 이름>/…`이 그 스킬 SKILL.md 옆으로 복사되고, 본문의
    `${CLAUDE_SKILL_DIR}/…` 참조 중 실존하지 않는 것은 `dangling_skill_file_ref`
    경고. 생략 시 복사·스캔 모두 생략 — 기존 산출 완전 불변(하위 호환).

    resolved_hooks(A1, 선택): 이름 → HookDef로 **해소된** 훅 사전(전역
    `~/.daedalus/hooks/` ← 프로젝트 `hook_library` 순). 컴파일러는 파일시스템에서
    훅을 읽지 않는다 — 읽으면 "이 프로젝트를 컴파일한 결과"가 컴파일한 사람의
    홈 디렉토리에 따라 달라지는 것이 코드에서 보이지 않게 된다. 그래서 호출자
    (앱/MCP)가 `model.plugin.hook_store.resolve_hooks(project)`로 만들어 주입한다.
    이 값이 주어지면 `dangling_hook_ref` 판정도 그 이름 집합을 기준으로 한다.
    생략 시 `project.hook_library`만 본다 — 기존 산출 완전 불변(하위 호환).
    """
    if out_dir is None and not dry_run:
        raise ValueError(
            "out_dir가 필요합니다 — 생략은 dry_run=True(검사 전용)에서만 "
            "가능합니다."
        )
    ctx = CompileContext.build(
        project, out_dir=out_dir, files_dir=files_dir,
        skill_files_dir=skill_files_dir, resolved_hooks=resolved_hooks,
        extra_server_defs=extra_server_defs,
        provided_server_names=provided_server_names,
        settings_filename=settings_filename, dry_run=dry_run,
    )
    known_hook_names = (
        frozenset(resolved_hooks) if resolved_hooks is not None else None
    )
    all_findings = Validator.validate_project(
        project, known_hook_names=known_hook_names,
    )
    errors = [e for e in all_findings if not e.is_warning]
    warnings = [e for e in all_findings if e.is_warning]

    # 파일 쓰기 전에 산출 계획 수립 — 이름 규약 + 경로 충돌 게이트
    plan, gate_errors, plan_warnings = PLANNER.plan(ctx)
    errors = errors + gate_errors
    warnings = warnings + plan_warnings

    result = CompileResult(errors=errors, warnings=warnings, dry_run=dry_run)
    if errors:
        # 거부 — 무엇이 막혔는지 skipped에 기록 (산출 계획 전체). 트리 복사·병합
        # 행(`exclusive=False`)은 종전에도 계획 밖이라 여기 실리지 않았다 —
        # MCP `compile_check` 응답 형상 불변.
        for item in plan:
            if item.exclusive:
                result.skipped.append(("compile_gate_error", item.label))
        return result

    sink = OutputSink(result, ctx)
    # ① 산출 파일 쓰기·복사 — 계획 순서 그대로.
    for item in plan:
        if item.phase is Phase.WRITE:
            unit_for(item).emit(item, ctx, sink)

    # ② 진단 스캔 — 산출이 아니라 드라이버가 소유한다(파일시스템을 읽는 판정).
    if ctx.files_dir is not None:
        result.warnings.extend(_scan_dangling_file_refs(project, ctx.files_dir))

    if ctx.skill_files_dir is not None:
        result.warnings.extend(
            _scan_dangling_skill_file_refs(project, ctx.skill_files_dir)
        )

    # ③ LOCAL 설치 배선 + CLAUDE.md 구역 — 사용자 파일 병합은 스캔 뒤다.
    for item in plan:
        if item.phase is Phase.INSTALL:
            unit_for(item).emit(item, ctx, sink)

    return result
