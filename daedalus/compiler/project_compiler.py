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
컴파일을 거부한다(조용한 덮어쓰기 방지). **그 계산은 ``compiler/plan.py``가 한다**
(WP-FK2 C0 분해, 이동만) — 이 모듈은 쓰기·복사·JSON 병합·LOCAL 설치 배선을 맡고,
계획 쪽 이름은 전부 재-export한다.

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

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from daedalus.compiler.emit import (
    _is_local_build,
    compile_agent,
    compile_hook_scripts,
    compile_hooks_json,
    compile_plugin_manifest,
    compile_schemas_json,
    compile_skill,
    expand_root_token,
    referenced_mcp_servers,
)
from daedalus.compiler.emit.manifest import external_plugin_ids
from daedalus.compiler.emit.wrapped import compile_wrapped_runner
# 산출 계획은 compiler/plan.py로 분해했다(WP-FK2 C0, 이동만). 여기서 재-export해
# 기존 임포트 경로(`from ...project_compiler import SKILL_FILES_DIRNAME` 등)를 지킨다.
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
from daedalus.compiler.workspace import (
    merge_claude_md,
    render_rule,
)
from daedalus.model.plugin.skill import Skill
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




def _hook_script_bodies(project, resolved_hooks=None) -> dict[str, str]:
    """훅 스크립트 파일명 → 내용 (WP-HS). 계획과 쓰기가 같은 원본을 본다."""
    return dict(compile_hook_scripts(project, resolved_hooks))








def _copy_files_tree(
    src_dir: Path, dst_dir: Path, clear_first: bool = True,
    dry_run: bool = False,
) -> list[Path]:
    """src_dir 트리를 dst_dir로 정렬 순회 복사한다 (결정적 로그).

    심볼릭 링크는 따라가지 않는다 — 디렉토리는 재귀하지 않고, 파일은 복사하지
    않는다. 기존 dst_dir는 복사 전 삭제한다(스테일 잔존 방지 — out 디렉토리
    전체가 아니라 files/ 하위만 지운다).

    dry_run(G3)이면 **순회만 하고 아무것도 만들거나 지우지 않는다** — 반환
    목록은 동일하다(같은 순회 코드가 계획과 실행을 함께 만든다. 열거를 따로
    구현하면 두 목록이 언젠가 어긋난다).

    반환: 실제로 복사된 파일의 dst_dir 기준 경로 목록 (정렬 순서, 디렉토리
    자체는 포함하지 않음).
    """
    # clear_first=False(LOCAL — out_dir가 사용자의 작업 폴더)는 기존 dst_dir를
    # 지우지 않고 덮어쓰기 복사만 한다. 사용자 파일 삭제 위험 > 스테일 잔존.
    if not dry_run:
        if clear_first and dst_dir.exists():
            shutil.rmtree(dst_dir)
        dst_dir.mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []
    for root, dirnames, filenames in os.walk(src_dir, followlinks=False):
        root_path = Path(root)
        rel_root = root_path.relative_to(src_dir)
        # in-place 정렬 + 심볼릭 링크 디렉토리 제외 — os.walk가 다음 순회에서
        # 이 리스트를 그대로 재사용하므로 순회 순서·재귀 범위를 동시에 제어한다.
        # Windows 디렉토리 정션(junction)은 is_symlink()가 False다 — 거르지
        # 않으면 files/ 밖 내용이 산출물로 새고, 자기 참조 정션은 폭주 재귀가
        # 된다(리뷰 실측). isjunction은 Python 3.12 표준.
        dirnames[:] = sorted(
            d for d in dirnames if not _is_link_like(root_path / d)
        )
        if not dry_run:
            for dirname in dirnames:
                (dst_dir / rel_root / dirname).mkdir(parents=True, exist_ok=True)
        for filename in sorted(filenames):
            src_file = root_path / filename
            if _is_link_like(src_file):
                continue
            dst_file = dst_dir / rel_root / filename
            if not dry_run:
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
            copied.append(dst_file)
    return copied




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
        scan(f"스킬 '{skill.name}'", skill, getattr(skill, "body", ""))
    for agent in project.agents:
        scan(f"에이전트 '{agent.name}'", agent, getattr(agent, "body", ""))
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
        if isinstance(skill, Skill):
            scan(
                f"스킬 '{skill.name}'", skill,
                getattr(skill, "body", ""), _skill_dir_name(skill.name),
            )
    return warnings


def _write_text(path: Path, text: str) -> None:
    """LF 줄바꿈 + UTF-8(BOM 없음)으로 쓴다 (결정적)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="" → 파이썬이 \n을 변환하지 않음(LF 그대로). text는 emit에서 LF 보장.
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


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
    if out_dir is None:
        if not dry_run:
            raise ValueError(
                "out_dir가 필요합니다 — 생략은 dry_run=True(검사 전용)에서만 "
                "가능합니다."
            )
        out_root: Path | None = None
    else:
        out_root = Path(out_dir)
    skill_files_path = Path(skill_files_dir) if skill_files_dir is not None else None
    known_hook_names = (
        frozenset(resolved_hooks) if resolved_hooks is not None else None
    )
    all_findings = Validator.validate_project(
        project, known_hook_names=known_hook_names,
    )
    errors = [e for e in all_findings if not e.is_warning]
    warnings = [e for e in all_findings if e.is_warning]

    # 파일 쓰기 전에 산출 계획 수립 — 이름 규약 + 경로 충돌 게이트
    plan, gate_errors, plan_warnings = _plan_outputs(
        project, skill_files_dir=skill_files_path, resolved_hooks=resolved_hooks,
    )
    errors = errors + gate_errors
    warnings = warnings + plan_warnings

    result = CompileResult(errors=errors, warnings=warnings, dry_run=dry_run)
    if errors:
        # 거부 — 무엇이 막혔는지 skipped에 기록 (산출 계획 전체)
        for item in plan:
            result.skipped.append(("compile_gate_error", item.label))
        return result

    def _out(rel) -> Path:
        """계획 상대 경로 → 실제 경로. out_dir 생략(dry_run)이면 상대 경로 그대로."""
        return (out_root / rel) if out_root is not None else Path(rel)

    for item in plan:
        if item.kind == "skill_file" and item.src_path is not None:
            # 스킬별 동봉 파일 (WP-SF) — 텍스트 산출이 아니라 복사다.
            dst = _out(item.rel_path)
            if not dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item.src_path, dst)
            result.copied_files.append(dst)
            continue
        if item.kind == "skill":
            text = compile_skill(item.component, project=project,
                                 resolved_hooks=resolved_hooks)
        elif item.kind == "agent":
            text = compile_agent(item.component, project=project,
                                 resolved_hooks=resolved_hooks)
        elif item.kind == "wrapped_runner":
            text = compile_wrapped_runner(item.component)
        elif item.kind == "hooks_json":
            text = compile_hooks_json(project, resolved_hooks) or ""
        elif item.kind == "hook_script":
            text = _hook_script_bodies(project, resolved_hooks).get(item.script_name, "")
        elif item.kind == "workspace_rule":
            # 본문 그대로 + paths 프론트매터(A13). paths가 비면 프론트매터가
            # 아예 나가지 않아 필드 도입 전과 산출이 바이트 단위로 같다.
            text = render_rule(item.component)
        elif item.kind == "schemas_json":
            text = compile_schemas_json(project) or ""
        elif item.kind == "plugin_manifest":
            text = compile_plugin_manifest(project)
        else:
            raise ValueError(f"알 수 없는 산출 계획 kind: {item.kind!r}")

        # 타깃 중립 토큰 ${ROOT}를 빌드 타깃에 맞는 CC 변수로 확장한다(WP-RT).
        # 본문 정본은 어느 타깃에도 기울지 않고, 여기서만 갈라진다.
        if item.kind in ("skill", "agent", "wrapped_runner"):
            text = expand_root_token(text, project)

        path = _out(item.rel_path)
        if not dry_run:
            _write_text(path, text)
        result.written.append(path)
        # 토큰 리포트(A5-lite) — **확장 후 최종 텍스트**를 잰다. 실제로 컨텍스트에
        # 실리는 것이 그것이고, ${ROOT} 확장으로 길이가 달라진다.
        result.token_report.add(str(item.rel_path), item.kind, text)

    if files_dir is not None:
        files_dir_path = Path(files_dir)
        if files_dir_path.is_dir():
            # LOCAL의 out_dir는 사용자의 작업 폴더다 — 기존 <out>/files/를 지우면
            # 사용자 파일을 지울 수 있으므로 덮어쓰기 복사만 한다(스테일 잔존은
            # 감수). MARKETPLACE 스테이징 디렉토리는 종전대로 삭제 후 복사.
            # 스킬별 동봉 파일(WP-SF) 복사분을 덮어쓰지 않고 이어 붙인다 —
            # 대입이면 files/와 skill-files/를 함께 준 컴파일에서 앞의 목록이
            # 통째로 사라져 "복사 N개"가 거짓말이 된다.
            result.copied_files.extend(_copy_files_tree(
                files_dir_path, _out("files"),
                clear_first=not _is_local_build(project),
                dry_run=dry_run,
            ))
        result.warnings.extend(_scan_dangling_file_refs(project, files_dir_path))

    if skill_files_path is not None:
        result.warnings.extend(
            _scan_dangling_skill_file_refs(project, skill_files_path)
        )

    if _is_local_build(project):
        _wire_local_install(
            project, out_root, result, extra_server_defs, resolved_hooks,
            dry_run=dry_run, settings_filename=settings_filename,
            provided_server_names=provided_server_names,
        )
        _merge_claude_md_region(project, out_root, result, dry_run=dry_run)

    return result


def _merge_claude_md_region(
    project, out_dir: Path | None, result: CompileResult, dry_run: bool = False,
) -> None:
    """`.claude/CLAUDE.md`의 이 플러그인 구역을 갱신한다 (WP-WD/D9).

    산출 계획(`_plan_outputs`)에 넣지 않는 이유: 이 파일은 **쓰기 전에 읽어야**
    하고 결과가 기존 내용에 달려 있어, "경로 하나 = 산출 하나"라는 계획의 전제와
    맞지 않는다. `.mcp.json`·`settings.local.json` 병합이 `_wire_local_install`에
    따로 있는 것과 같은 이유다.

    out_dir가 None이면(dry_run에서 대상 폴더를 지정하지 않은 경우) 기존 파일을
    읽을 수 없어 병합 판정 자체가 불가능하다 — 비용만 계상하고 물러난다.
    """
    doc = getattr(project, "claude_md", None)
    if out_dir is None:
        if doc is not None and doc.has_content():
            result.token_report.add(
                ".claude/CLAUDE.md (plugin section)", "claude_md", doc.body or "",
            )
        return
    path = out_dir / ".claude" / "CLAUDE.md"
    existing: str | None = None
    if path.is_file():
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - 권한 등 환경 의존
            result.warnings.append(ValidationError(
                rule="unmergeable_claude_md",
                message=f"'{path}'를 읽을 수 없어 병합하지 않았습니다: {exc}",
                source=str(path), subject=project,
            ))
            return
    elif doc is None or not doc.has_content():
        return  # 쓸 내용도 없고 기존 파일도 없다 — 빈 파일을 만들지 않는다

    text, warning = merge_claude_md(
        existing,
        project.name,
        title=(doc.name if doc is not None and doc.name else project.name),
        body=(doc.body if doc is not None else ""),
    )
    if warning is not None:
        result.warnings.append(ValidationError(
            rule="unmergeable_claude_md",
            message=f"{warning} 표식을 고친 뒤 다시 컴파일하세요: {path}",
            source=str(path), subject=project,
        ))
        return
    if text is None:
        return
    if not dry_run:
        _write_text(path, text)
    result.written.append(path)
    # 토큰 리포트에는 **이 플러그인의 구역 본문만** 싣는다(A5-lite) — 파일 전체는
    # 다른 플러그인·사용자가 쓴 내용까지 포함해서, 이 컴파일이 만든 비용이 아니다.
    # 다만 CLAUDE.md는 매 세션 통째로 실리므로 구역 본문의 비용은 실재한다.
    if doc is not None and doc.has_content():
        result.token_report.add(
            ".claude/CLAUDE.md (plugin section)", "claude_md", doc.body or "",
        )


# ─────────────────────── LOCAL 설치 배선 — JSON 병합 (WP-MW) ───────────────────────


def _wire_local_install(
    project, out_dir: Path | None, result: CompileResult,
    extra_server_defs: dict[str, dict] | None = None,
    resolved_hooks: dict | None = None,
    dry_run: bool = False,
    settings_filename: str = "settings.json",
    provided_server_names: set[str] | frozenset[str] | None = None,
) -> None:
    """LOCAL 빌드의 설치 배선 — 대상 작업 폴더의 설정 파일을 생성/수정한다.

    병합 자체는 `compiler/wiring.wire_workspace`가 한다("Claude Code 실행"
    메뉴와 공유 — 같은 폴더를 두 경로가 다르게 만지면 안 된다). 여기서는
    무엇을 배선할지(참조 서버 ∩ 정의, 프로젝트 훅)를 정하고, 배선하지 못한
    사실을 경고로 변환한다.

    정의 조회는 프로젝트(`mcp_server_defs`)가 우선이고, 없으면 호출 환경이
    준 `extra_server_defs`(예: Daedalus 앱 자신의 daedalus 서버)로 채운다.

    `missing_mcp_server_def` 판정은 **대상 폴더와 무관**하므로 out_dir가
    None이어도(dry_run) 그대로 낸다 — 폴더를 읽어야 하는 것은 병합
    (`unmergeable_settings_json`)뿐이고 그쪽만 건너뛴다.
    """
    from daedalus.compiler.wiring import wire_workspace

    defs = dict(extra_server_defs or {})
    defs.update(getattr(project, "mcp_server_defs", None) or {})  # 프로젝트가 우선
    referenced = referenced_mcp_servers(project)
    entries = {name: defs[name] for name in referenced if name in defs}
    provided = set(provided_server_names or ())
    for name in referenced:
        if name not in defs and name not in provided:
            result.warnings.append(ValidationError(
                rule="missing_mcp_server_def",
                message=(
                    f"MCP 서버 '{name}'가 참조되지만 프로젝트에 서버 정의가 없어 "
                    f".mcp.json에 배선하지 못했습니다. set_mcp_server_def(MCP) 또는 "
                    f"프로젝트 속성에서 정의를 추가하거나, 대상 프로젝트의 "
                    f".mcp.json에 직접 추가하세요."
                ),
                source=name,
                subject=project,
            ))

    # WP-WR — 사용 선언된 외부 플러그인(external_plugins)을 enabledPlugins로
    # 활성화한다. 배선의 단일 진실은 선언이다 — 랩핑 스킬 source를 스캔하지
    # 않는다(사용자 확정. 선언·참조의 어긋남은 검증 경고가 짚는다). 형식은
    # settings 스키마(벤더링 스냅샷) 확인: {"plugin-id@marketplace-id": true}.
    # 마켓 표기가 없는 bare 이름은 enabledPlugins 키가 될 수 없어 경고 후 생략
    # (매니페스트 dependencies와 달리 자기-마켓 해소 규칙이 없다). 이 판정은
    # missing_mcp_server_def처럼 **대상 폴더와 무관**하므로 out_dir 조기 반환
    # 앞에 있어야 한다 — 뒤에 두면 out_dir 없는 compile_check(dry-run)에서
    # 경고가 통째로 사라진다.
    enabled_plugins: dict = {}
    for plugin_id in external_plugin_ids(project):
        if "@" not in plugin_id:
            result.warnings.append(ValidationError(
                rule="external_plugin_no_marketplace",
                message=(
                    f"사용 선언된 외부 플러그인 '{plugin_id}'에 마켓플레이스 "
                    f"표기가 없어 enabledPlugins에 올릴 수 없습니다 — "
                    f"`플러그인@마켓` 형식이면 설치 배선까지 자동입니다."
                ),
                source=plugin_id,
                subject=project,
            ))
            continue
        enabled_plugins[plugin_id] = True

    if out_dir is None:
        return  # 대상 폴더를 모르면 병합 판정 자체가 불가능하다

    hooks_text = compile_hooks_json(project, resolved_hooks)
    hooks_map = json.loads(hooks_text).get("hooks", {}) if hooks_text else None

    baked_settings = dict(project.workspace_settings or {})
    if enabled_plugins:
        merged = dict(baked_settings.get("enabledPlugins") or {})
        merged.update(enabled_plugins)
        baked_settings["enabledPlugins"] = merged

    wired = wire_workspace(
        out_dir, entries, hooks_map, dry_run=dry_run,
        # WP-WS — 프로젝트의 작업 폴더 설정 베이크. hooks 키는 wire_workspace가
        # 무시한다(훅 정본은 hook_library — hooks_map 경로 전담).
        # WP-WR — 랩핑 소스 플러그인의 enabledPlugins 합성 포함(모델 불변).
        extra_settings=baked_settings or None,
        settings_name=settings_filename,
    )
    result.written.extend(wired.written)
    for path in wired.unmergeable:
        result.warnings.append(ValidationError(
            rule="unmergeable_settings_json",
            message=(
                f"'{path}'가 올바른 JSON이 아니어서 병합하지 않았습니다 — 기존 "
                f"내용을 지키기 위해 그대로 두었습니다. 파일을 고친 뒤 다시 "
                f"컴파일하세요."
            ),
            source=str(path),
            subject=project,
        ))
