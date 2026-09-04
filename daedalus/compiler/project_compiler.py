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
컴파일을 거부한다(조용한 덮어쓰기 방지).

컴파일 게이트(정책 8 + 강화 2종):
  - Validator.validate_project의 에러(is_warning=False) 1건 이상 → 거부.
  - 산출 파일/디렉토리 이름이 되는 컴포넌트(스킬·에이전트)의
    이름이 `^[a-z0-9][a-z0-9-]*$` 불일치 → 컴파일 에러로 승격해 거부.
    (F7 검증기에서는 경고 등급 유지 — 편집 중에는 경고가 맞다. 게이트만 엄격.)
  - 산출 경로 충돌 → 거부 + 충돌 경로/원인 컴포넌트 보고.
경고는 통과(결과에 동봉).
"""
from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from daedalus.compiler.emit import (
    compile_agent,
    compile_hook_scripts,
    compile_hooks_json,
    compile_plugin_manifest,
    compile_schemas_json,
    compile_skill,
    expand_root_token,
    referenced_mcp_servers,
)
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.hook import HOOK_SCRIPT_DIR
from daedalus.model.plugin.skill import Skill
from daedalus.model.validation import ValidationError, Validator

# CC 플러그인 산출물 이름 규약 — Validator._COMPONENT_NAME_RE와 동일 패턴.
# 검증기에서는 경고(편집 중)지만 컴파일 게이트에서는 에러로 승격한다.
_OUTPUT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

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
})

# 스킬별 동봉 파일 소스 디렉토리명 (WP-SF) — <프로젝트 폴더>/skill-files/<스킬 산출
# 디렉토리명>/… 이 그 스킬의 SKILL.md **옆으로** 복사된다. 공용 files/와 분리한
# 이유: files/는 통째로 <out>/files/로 가는 규칙이라, 섞으면 스킬 파일이 양쪽에
# 이중 산출된다. 참조 토큰은 `${CLAUDE_SKILL_DIR}/<상대경로>` — CC 공식 변수로
# 마켓플레이스/로컬 동일 동작이라 ${ROOT} 같은 타깃 중립화가 필요 없다.
SKILL_FILES_DIRNAME = "skill-files"

# 본문의 스킬 파일 참조 토큰 스캔 패턴 — _FILE_REF_*와 동일한 두 형태.
_SKILL_FILE_REF_ANGLE_RE = re.compile(r"<\$\{CLAUDE_SKILL_DIR\}/([^>]+)>")
_SKILL_FILE_REF_BARE_RE = re.compile(r"\$\{CLAUDE_SKILL_DIR\}/([^\s)\]`\"'<>,;]+)")


@dataclass
class CompileResult:
    """컴파일 결과.

    written: 실제로 쓴 파일 경로 목록.
    errors: 컴파일을 거부시킨 에러(검증 에러 + 컴파일 게이트 에러). 비어 있으면 성공.
    warnings: 통과한 경고(결과에 동봉).
    skipped: (이유, 컴포넌트 이름) 목록 — 거부 시 쓰지 못한 항목 등.
    copied_files: files_dir 트리 복사로 실제 복사된 파일 경로 목록 (WP-FR).
        files_dir 미지정이거나 실존하지 않으면 빈 리스트.
    """
    written: list[Path] = field(default_factory=list)
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    copied_files: list[Path] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _skill_dir_name(skill_name: str) -> str:
    return skill_name


@dataclass
class _PlannedOutput:
    """쓰기 전 계획된 산출물 1건."""
    rel_path: PurePosixPath          # out_dir 기준 상대 경로 (충돌 키)
    label: str                       # 사람이 읽는 원인 컴포넌트 표지
    subject: object                  # 노드 점프용 모델 객체
    kind: str                        # "skill" | "agent" | "hook_script" | …
    component: object                # 컴파일 대상 (skill/agent)
    script_name: str = ""            # hook_script일 때 파일명 (WP-HS)
    src_path: Path | None = None     # skill_file일 때 복사 원본 (WP-SF)


def _is_local_build(project) -> bool:
    """project.build_target이 LOCAL이면 True (구버전 파일/속성 부재 → MARKETPLACE, WP-TG)."""
    return getattr(project, "build_target", BuildTarget.MARKETPLACE) is BuildTarget.LOCAL


def _hook_script_bodies(project, resolved_hooks=None) -> dict[str, str]:
    """훅 스크립트 파일명 → 내용 (WP-HS). 계획과 쓰기가 같은 원본을 본다."""
    return dict(compile_hook_scripts(project, resolved_hooks))


def _plan_outputs(
    project, skill_files_dir: Path | None = None, resolved_hooks=None,
) -> tuple[list[_PlannedOutput], list[ValidationError], list[ValidationError]]:
    """파일 쓰기 전에 전체 산출 경로 집합을 계산하고 게이트 에러를 수집한다.

    에러 2종:
      compile_invalid_component_name — 산출 이름 규약 불일치 (게이트에서 에러 승격)
      compile_output_path_conflict   — 동일 산출 경로 중복 (조용한 덮어쓰기 방지)

    skill_files_dir(WP-SF, 선택): 스킬별 동봉 파일 트리. 하위 폴더 이름이 스킬
    산출 디렉토리명과 일치하면 그 파일들이 SKILL.md 옆으로 가는 복사 계획으로
    합류한다 — 계획 집합에 넣기 때문에 SKILL.md를 덮는 파일이 있으면 기존
    `compile_output_path_conflict` 게이트가 잡는다. 일치하는 스킬이 없는 하위
    폴더는 `unknown_skill_files_dir` 경고(세 번째 반환값).
    """
    plan: list[_PlannedOutput] = []
    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []
    is_local = _is_local_build(project)
    # LOCAL은 컴파일이 곧 설치 — 스킬/에이전트가 CC가 실제로 읽는 <작업 폴더>/.claude/
    # 밑으로 바로 나간다. files/·schemas/·hooks/scripts/는 루트 그대로다(본문의
    # ${CLAUDE_PROJECT_DIR}/… 참조가 그 위치를 가리킨다).
    cc_prefix = PurePosixPath(".claude") if is_local else PurePosixPath(".")

    def check_name(name: str, label: str, subject: object) -> None:
        if not _OUTPUT_NAME_RE.match(name or ""):
            errors.append(ValidationError(
                rule="compile_invalid_component_name",
                message=(
                    f"{label}의 이름 '{name}'이 규약 '^[a-z0-9][a-z0-9-]*$'에 맞지 "
                    f"않습니다. 컴파일 시에는 이름 규약이 필수입니다 — 산출 "
                    f"파일/디렉토리 이름이 되므로 CC 플러그인 로더가 받지 않는 "
                    f"산출물이 생깁니다."
                ),
                source=name,
                subject=subject,
            ))

    # 프로젝트 이름 — 마켓플레이스 빌드에서 plugin.json의 name(플러그인 식별자)이
    # 되므로 컴포넌트와 동일 규약을 컴파일 게이트에서 에러로 강제한다. 로컬 빌드도
    # 같은 규약을 적용한다(타깃을 오가며 새 에러가 튀지 않도록 — 산출 이름·문서
    # 제목에 그대로 쓰인다).
    if not _OUTPUT_NAME_RE.match(project.name or ""):
        errors.append(ValidationError(
            rule="compile_invalid_component_name",
            message=(
                f"프로젝트 '{project.name}'의 이름이 규약 '^[a-z0-9][a-z0-9-]*$'에 "
                f"맞지 않습니다. 컴파일 시에는 이름 규약이 필수입니다 — 마켓플레이스 "
                f"빌드에서는 plugin.json의 name(플러그인 식별자)이 되어 CC 플러그인 "
                f"로더가 받지 않는 산출물이 생깁니다. 파일 → 프로젝트 속성…에서 "
                f"이름을 변경하세요."
            ),
            source=project.name,
            subject=project,
        ))

    # 스킬 산출 디렉토리명 → 컴포넌트 (WP-SF skill-files 매칭용)
    skill_dirs: dict[str, object] = {}

    # 전역 스킬
    for skill in project.skills:
        if not isinstance(skill, Skill):
            continue
        label = f"스킬 '{skill.name}'"
        check_name(skill.name, label, skill)
        skill_dirs[_skill_dir_name(skill.name)] = skill
        plan.append(_PlannedOutput(
            rel_path=cc_prefix / "skills" / _skill_dir_name(skill.name) / "SKILL.md",
            label=label,
            subject=skill,
            kind="skill",
            component=skill,
        ))

    # 에이전트
    for agent in project.agents:
        label = f"에이전트 '{agent.name}'"
        check_name(agent.name, label, agent)
        plan.append(_PlannedOutput(
            rel_path=cc_prefix / "agents" / f"{agent.name}.md",
            label=label,
            subject=agent,
            kind="agent",
            component=agent,
        ))

    # 스킬별 동봉 파일 (WP-SF) — 하위 폴더명이 스킬 산출 디렉토리명과 일치할 때만
    # SKILL.md 옆으로 가는 복사 계획에 합류한다. 계획 집합 합류가 곧 충돌 방어다 —
    # 'SKILL.md'라는 이름의 동봉 파일은 아래 경로 충돌 검사가 에러로 거부한다.
    if skill_files_dir is not None and skill_files_dir.is_dir():
        for sub in sorted(skill_files_dir.iterdir(), key=lambda p: p.name):
            if _is_link_like(sub):
                continue
            if not sub.is_dir():
                warnings.append(ValidationError(
                    rule="unknown_skill_files_dir",
                    message=(
                        f"{SKILL_FILES_DIRNAME}/ 바로 밑의 파일 '{sub.name}'은 어느 "
                        f"스킬 소속인지 알 수 없어 복사하지 않았습니다 — "
                        f"{SKILL_FILES_DIRNAME}/<스킬 이름>/ 하위에 두세요."
                    ),
                    source=sub.name,
                    subject=project,
                ))
                continue
            component = skill_dirs.get(sub.name)
            if component is None:
                warnings.append(ValidationError(
                    rule="unknown_skill_files_dir",
                    message=(
                        f"{SKILL_FILES_DIRNAME}/{sub.name}/과 이름이 일치하는 스킬이 "
                        f"없어 복사하지 않았습니다 — 폴더 이름은 스킬 이름과 같아야 "
                        f"합니다(스킬 이름 변경 뒤에 남은 옛 폴더일 수 있습니다)."
                    ),
                    source=sub.name,
                    subject=project,
                ))
                continue
            for src in _iter_tree_files(sub):
                rel_parts = src.relative_to(sub).parts
                plan.append(_PlannedOutput(
                    rel_path=cc_prefix / "skills" / sub.name / PurePosixPath(*rel_parts),
                    label=f"스킬 파일 '{sub.name}/{'/'.join(rel_parts)}'",
                    subject=component,
                    kind="skill_file",
                    component=component,
                    src_path=src,
                ))

    # hooks.json (SETTINGS) — 프로젝트가 참조하는 훅이 있을 때만 계획에 합류.
    # LOCAL은 hooks/hooks.json 파일을 만들지 않는다 — 컴파일이 곧 설치이므로 훅은
    # <out>/.claude/settings.local.json의 hooks 섹션에 병합된다(compile_project의
    # 병합 단계, WP-MW). 훅 스크립트 파일은 양쪽 타깃 모두 hooks/scripts/로 나간다
    # (LOCAL의 커맨드가 ${CLAUDE_PROJECT_DIR}/hooks/scripts/…를 가리킨다).
    hooks_text = compile_hooks_json(project, resolved_hooks)
    if hooks_text is not None:
        if not is_local:
            plan.append(_PlannedOutput(
                rel_path=PurePosixPath("hooks") / "hooks.json",
                label="hooks.json (lifecycle hooks)",
                subject=project,
                kind="hooks_json",
                component=project,
            ))
        # 훅 스크립트 — 커맨드는 아무리 짧아도 파일로 나가고 hooks.json에는
        # 루트 기반 경로만 남는다 (WP-HS).
        for filename, _body in compile_hook_scripts(project, resolved_hooks):
            plan.append(_PlannedOutput(
                rel_path=PurePosixPath(HOOK_SCRIPT_DIR) / filename,
                label=f"훅 스크립트 {filename}",
                subject=project,
                kind="hook_script",
                component=project,
                script_name=filename,
            ))

    # 블랙보드 스키마 — 정의가 있을 때만 계획에 합류. 파일 이름이 **프로젝트
    # 이름**인 이유는 WP-NS다: 이전의 고정 경로 'schemas/schemas.json'은 한 작업
    # 폴더에 ddls 플러그인이 둘 깔리면 나중 것이 앞의 것을 조용히 덮어썼다(경로
    # 충돌 게이트는 한 번의 컴파일 안에서만 도므로 잡지 못한다). 이름은 컴파일
    # 게이트가 '^[a-z0-9][a-z0-9-]*$'를 강제하므로 파일명으로 안전하다.
    # 작업 폴더 문서 — LOCAL 전용(WP-WD). 마켓플레이스 플러그인은 설치 대상 작업
    # 폴더의 .claude/에 쓸 수 없으므로 계획에 넣지 않는다(경고는 Validator 소관).
    # 규칙 이름은 파일명이 되므로 컴포넌트와 같은 이름 게이트를 통과해야 한다.
    if is_local:
        for doc in getattr(project, "rules", None) or []:
            if not doc.has_content():
                continue  # 배출할 내용이 없으면 빈 파일을 만들지 않는다
            check_name(doc.name, f"규칙 문서 '{doc.name}'", doc)
            plan.append(_PlannedOutput(
                rel_path=cc_prefix / "rules" / f"{doc.name}.md",
                label=f"rules/{doc.name}.md (workspace rule)",
                subject=doc,
                kind="workspace_rule",
                component=doc,
            ))

    schemas_text = compile_schemas_json(project)
    if schemas_text is not None:
        plan.append(_PlannedOutput(
            rel_path=PurePosixPath("schemas") / f"{project.name}.json",
            label=f"schemas/{project.name}.json (blackboard class definitions)",
            subject=project,
            kind="schemas_json",
            component=project,
        ))

    # plugin.json (플러그인 매니페스트) — MARKETPLACE 빌드에서만 생성한다
    # (매니페스트 없이는 산출 디렉토리를 CC 플러그인으로 설치할 수 없다).
    # LOCAL 빌드는 컴파일이 곧 설치라 매니페스트도 설치 스크립트도 없다 (WP-MW —
    # 이전의 INSTALL.md/install.ps1/install.sh 동봉은 폐기됐다).
    if not is_local:
        plan.append(_PlannedOutput(
            rel_path=PurePosixPath(".claude-plugin") / "plugin.json",
            label="plugin.json (플러그인 매니페스트)",
            subject=project,
            kind="plugin_manifest",
            component=project,
        ))

    # 산출 경로 충돌 검사 — 첫 점유자와 이후 충돌자를 모두 보고
    seen: dict[PurePosixPath, _PlannedOutput] = {}
    for item in plan:
        first = seen.get(item.rel_path)
        if first is not None:
            errors.append(ValidationError(
                rule="compile_output_path_conflict",
                message=(
                    f"산출 경로 '{item.rel_path}'가 충돌합니다: {first.label} ↔ "
                    f"{item.label}. 그대로 진행하면 뒤의 쓰기가 앞의 산출물을 "
                    f"조용히 덮어씁니다 — 컴포넌트 이름을 조정하세요."
                ),
                source=str(item.rel_path),
                subject=item.subject,
            ))
        else:
            seen[item.rel_path] = item

    return plan, errors, warnings


def _iter_tree_files(root: Path) -> list[Path]:
    """root 트리의 파일을 정렬 순회로 열거한다 (WP-SF — 복사 계획용).

    ``_copy_files_tree``와 같은 규칙: 심볼릭 링크/정션은 디렉토리든 파일이든
    제외한다(따라가면 트리 밖 내용이 산출물로 샌다).
    """
    files: list[Path] = []
    for walk_root, dirnames, filenames in os.walk(root, followlinks=False):
        root_path = Path(walk_root)
        dirnames[:] = sorted(d for d in dirnames if not _is_link_like(root_path / d))
        for filename in sorted(filenames):
            src = root_path / filename
            if not _is_link_like(src):
                files.append(src)
    return files


def _copy_files_tree(
    src_dir: Path, dst_dir: Path, clear_first: bool = True,
) -> list[Path]:
    """src_dir 트리를 dst_dir로 정렬 순회 복사한다 (결정적 로그).

    심볼릭 링크는 따라가지 않는다 — 디렉토리는 재귀하지 않고, 파일은 복사하지
    않는다. 기존 dst_dir는 복사 전 삭제한다(스테일 잔존 방지 — out 디렉토리
    전체가 아니라 files/ 하위만 지운다).

    반환: 실제로 복사된 파일의 dst_dir 기준 경로 목록 (정렬 순서, 디렉토리
    자체는 포함하지 않음).
    """
    # clear_first=False(LOCAL — out_dir가 사용자의 작업 폴더)는 기존 dst_dir를
    # 지우지 않고 덮어쓰기 복사만 한다. 사용자 파일 삭제 위험 > 스테일 잔존.
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
        for dirname in dirnames:
            (dst_dir / rel_root / dirname).mkdir(parents=True, exist_ok=True)
        for filename in sorted(filenames):
            src_file = root_path / filename
            if _is_link_like(src_file):
                continue
            dst_file = dst_dir / rel_root / filename
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            copied.append(dst_file)
    return copied


def _is_link_like(path: Path) -> bool:
    """심볼릭 링크 또는 Windows 정션이면 True — files/ 복사에서 제외 대상."""
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    return bool(isjunction and isjunction(path))


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
    project, out_dir: Path | str, files_dir: Path | str | None = None,
    extra_server_defs: dict[str, dict] | None = None,
    skill_files_dir: Path | str | None = None,
    resolved_hooks: dict | None = None,
) -> CompileResult:
    """프로젝트를 out_dir에 컴파일한다.

    게이트: 검증 에러 + 게이트 강화 에러(이름 규약·경로 충돌)가 1건이라도 있으면
    파일을 쓰지 않고 거부한다. 경고만 있으면 통과시키고 warnings에 동봉한다.

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
    out_dir = Path(out_dir)
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

    result = CompileResult(errors=errors, warnings=warnings)
    if errors:
        # 거부 — 무엇이 막혔는지 skipped에 기록 (산출 계획 전체)
        for item in plan:
            result.skipped.append(("compile_gate_error", item.label))
        return result

    for item in plan:
        if item.kind == "skill_file" and item.src_path is not None:
            # 스킬별 동봉 파일 (WP-SF) — 텍스트 산출이 아니라 복사다.
            dst = out_dir / item.rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.src_path, dst)
            result.copied_files.append(dst)
            continue
        if item.kind == "skill":
            text = compile_skill(item.component, project=project)
        elif item.kind == "agent":
            text = compile_agent(item.component, project=project,
                                 resolved_hooks=resolved_hooks)
        elif item.kind == "hooks_json":
            text = compile_hooks_json(project, resolved_hooks) or ""
        elif item.kind == "hook_script":
            text = _hook_script_bodies(project, resolved_hooks).get(item.script_name, "")
        elif item.kind == "workspace_rule":
            # 본문 그대로 — 편집만 제공한다(WP-WD/D7). 프론트매터가 필요하면
            # 사용자가 본문 맨 위에 직접 쓴다.
            text = item.component.body.strip("\n") + "\n"
        elif item.kind == "schemas_json":
            text = compile_schemas_json(project) or ""
        elif item.kind == "plugin_manifest":
            text = compile_plugin_manifest(project)
        else:
            raise ValueError(f"알 수 없는 산출 계획 kind: {item.kind!r}")

        # 타깃 중립 토큰 ${ROOT}를 빌드 타깃에 맞는 CC 변수로 확장한다(WP-RT).
        # 본문 정본은 어느 타깃에도 기울지 않고, 여기서만 갈라진다.
        if item.kind in ("skill", "agent"):
            text = expand_root_token(text, project)

        path = out_dir / item.rel_path
        _write_text(path, text)
        result.written.append(path)

    if files_dir is not None:
        files_dir_path = Path(files_dir)
        if files_dir_path.is_dir():
            # LOCAL의 out_dir는 사용자의 작업 폴더다 — 기존 <out>/files/를 지우면
            # 사용자 파일을 지울 수 있으므로 덮어쓰기 복사만 한다(스테일 잔존은
            # 감수). MARKETPLACE 스테이징 디렉토리는 종전대로 삭제 후 복사.
            result.copied_files = _copy_files_tree(
                files_dir_path, out_dir / "files",
                clear_first=not _is_local_build(project),
            )
        result.warnings.extend(_scan_dangling_file_refs(project, files_dir_path))

    if skill_files_path is not None:
        result.warnings.extend(
            _scan_dangling_skill_file_refs(project, skill_files_path)
        )

    if _is_local_build(project):
        _wire_local_install(
            project, out_dir, result, extra_server_defs, resolved_hooks,
        )
        _merge_claude_md_region(project, out_dir, result)

    return result


def _merge_claude_md_region(project, out_dir: Path, result: CompileResult) -> None:
    """`.claude/CLAUDE.md`의 이 플러그인 구역을 갱신한다 (WP-WD/D9).

    산출 계획(`_plan_outputs`)에 넣지 않는 이유: 이 파일은 **쓰기 전에 읽어야**
    하고 결과가 기존 내용에 달려 있어, "경로 하나 = 산출 하나"라는 계획의 전제와
    맞지 않는다. `.mcp.json`·`settings.local.json` 병합이 `_wire_local_install`에
    따로 있는 것과 같은 이유다.
    """
    from daedalus.compiler.workspace import merge_claude_md

    doc = getattr(project, "claude_md", None)
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
    _write_text(path, text)
    result.written.append(path)


# ─────────────────────── LOCAL 설치 배선 — JSON 병합 (WP-MW) ───────────────────────


def _wire_local_install(
    project, out_dir: Path, result: CompileResult,
    extra_server_defs: dict[str, dict] | None = None,
    resolved_hooks: dict | None = None,
) -> None:
    """LOCAL 빌드의 설치 배선 — 대상 작업 폴더의 설정 파일을 생성/수정한다.

    병합 자체는 `compiler/wiring.wire_workspace`가 한다("Claude Code 실행"
    메뉴와 공유 — 같은 폴더를 두 경로가 다르게 만지면 안 된다). 여기서는
    무엇을 배선할지(참조 서버 ∩ 정의, 프로젝트 훅)를 정하고, 배선하지 못한
    사실을 경고로 변환한다.

    정의 조회는 프로젝트(`mcp_server_defs`)가 우선이고, 없으면 호출 환경이
    준 `extra_server_defs`(예: Daedalus 앱 자신의 daedalus 서버)로 채운다.
    """
    from daedalus.compiler.wiring import wire_workspace

    defs = dict(extra_server_defs or {})
    defs.update(getattr(project, "mcp_server_defs", None) or {})  # 프로젝트가 우선
    referenced = referenced_mcp_servers(project)
    entries = {name: defs[name] for name in referenced if name in defs}
    for name in referenced:
        if name not in defs:
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

    hooks_text = compile_hooks_json(project, resolved_hooks)
    hooks_map = json.loads(hooks_text).get("hooks", {}) if hooks_text else None

    wired = wire_workspace(out_dir, entries, hooks_map)
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
