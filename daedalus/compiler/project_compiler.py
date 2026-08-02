# daedalus/compiler/project_compiler.py
"""프로젝트 컴파일 — 게이트 + 파일 쓰기 (순수 stdlib, Qt 무관).

CC 플러그인 출력 구조:
    <out>/.claude-plugin/plugin.json            # 플러그인 매니페스트 (항상 생성)
    <out>/skills/<skill-name>/SKILL.md          # 전역 스킬 4종
    <out>/skills/<agent-name>--<skill-name>/SKILL.md   # 에이전트 로컬 스킬
    <out>/agents/<agent-name>.md                # 에이전트

로컬 스킬의 '--' 결합은 충돌 무결하지 **않다** — 이름 규약이 연속 하이픈을
허용하므로 (agent 'a--b', skill 'c')와 (agent 'a', skill 'b--c')가 같은
디렉토리를 산출할 수 있다. 따라서 compile_project는 파일 쓰기 전에 전체 산출
경로 집합을 계산하고, 중복이 있으면 컴파일을 거부한다(조용한 덮어쓰기 방지).

컴파일 게이트(정책 8 + 강화 2종):
  - Validator.validate_project의 에러(is_warning=False) 1건 이상 → 거부.
  - 산출 파일/디렉토리 이름이 되는 컴포넌트(전역 스킬·에이전트·로컬 스킬)의
    이름이 `^[a-z0-9][a-z0-9-]*$` 불일치 → 컴파일 에러로 승격해 거부.
    (F7 검증기에서는 경고 등급 유지 — 편집 중에는 경고가 맞다. 게이트만 엄격.)
  - 산출 경로 충돌 → 거부 + 충돌 경로/원인 컴포넌트 보고.
경고는 통과(결과에 동봉).
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from daedalus.compiler.emit import (
    compile_agent,
    compile_hooks_json,
    compile_plugin_manifest,
    compile_schemas_json,
    compile_skill,
)
from daedalus.model.plugin.skill import Skill
from daedalus.model.validation import ValidationError, Validator

# CC 플러그인 산출물 이름 규약 — Validator._COMPONENT_NAME_RE와 동일 패턴.
# 검증기에서는 경고(편집 중)지만 컴파일 게이트에서는 에러로 승격한다.
_OUTPUT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# 스킬/에이전트 body에서 파일 참조 토큰을 스캔하는 패턴 — MarkdownEditor의
# 드롭 삽입(view/widgets/markdown_editor.py `_file_ref_token`)이 만드는 형식과
# 동일: ``${CLAUDE_PLUGIN_ROOT}/files/<상대경로>``. 공백·마크다운 구분자
# (`)]`"'<>`)에서 경로가 끊긴다고 보수적으로 가정한다.
_FILE_REF_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/files/([^\s)\]`\"'<>]+)")

# 컴파일 게이트 전용 rule 분류 표 (등급 의도의 단일 진실).
# 이 rule들은 validation.py의 WARNING_RULES에 없으므로 is_warning이 자동으로
# False(에러)가 된다 — 게이트 rule은 전부 에러 등급이 의도다. 새 게이트 rule을
# 추가할 때 반드시 이 집합에도 등록하라 (테스트가 발급 rule ⊆ 이 집합을 고정).
COMPILER_ERROR_RULES: frozenset[str] = frozenset({
    "compile_invalid_component_name",
    "compile_output_path_conflict",
})


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


def _local_skill_dir_name(agent_name: str, skill_name: str) -> str:
    """에이전트 로컬 스킬 디렉토리명 — '<agent>--<skill>'.

    주의: 이 결합은 충돌 무결하지 않다(모듈 docstring 참조). 충돌은
    _plan_outputs의 사전 경로 집합 검사로 잡아 컴파일을 거부한다.
    """
    return f"{agent_name}--{skill_name}"


@dataclass
class _PlannedOutput:
    """쓰기 전 계획된 산출물 1건."""
    rel_path: PurePosixPath          # out_dir 기준 상대 경로 (충돌 키)
    label: str                       # 사람이 읽는 원인 컴포넌트 표지
    subject: object                  # 노드 점프용 모델 객체
    kind: str                        # "skill" | "agent" | "local_skill"
    component: object                # 컴파일 대상 (skill/agent)
    agent: object | None = None      # local_skill일 때 소유 에이전트


def _plan_outputs(project) -> tuple[list[_PlannedOutput], list[ValidationError]]:
    """파일 쓰기 전에 전체 산출 경로 집합을 계산하고 게이트 에러를 수집한다.

    에러 2종:
      compile_invalid_component_name — 산출 이름 규약 불일치 (게이트에서 에러 승격)
      compile_output_path_conflict   — 동일 산출 경로 중복 (조용한 덮어쓰기 방지)
    """
    plan: list[_PlannedOutput] = []
    errors: list[ValidationError] = []

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

    # 프로젝트 이름 — plugin.json의 name(플러그인 식별자)이 되므로 컴포넌트와
    # 동일 규약을 컴파일 게이트에서 에러로 강제한다.
    if not _OUTPUT_NAME_RE.match(project.name or ""):
        errors.append(ValidationError(
            rule="compile_invalid_component_name",
            message=(
                f"프로젝트 '{project.name}'의 이름이 규약 '^[a-z0-9][a-z0-9-]*$'에 "
                f"맞지 않습니다. 컴파일 시에는 이름 규약이 필수입니다 — "
                f"plugin.json의 name(플러그인 식별자)이 되므로 CC 플러그인 로더가 "
                f"받지 않는 산출물이 생깁니다. 파일 → 프로젝트 속성…에서 이름을 "
                f"변경하세요."
            ),
            source=project.name,
            subject=project,
        ))

    # 전역 스킬
    for skill in project.skills:
        if not isinstance(skill, Skill):
            continue
        label = f"스킬 '{skill.name}'"
        check_name(skill.name, label, skill)
        plan.append(_PlannedOutput(
            rel_path=PurePosixPath("skills") / _skill_dir_name(skill.name) / "SKILL.md",
            label=label,
            subject=skill,
            kind="skill",
            component=skill,
        ))

    # 에이전트 + 로컬 스킬
    for agent in project.agents:
        label = f"에이전트 '{agent.name}'"
        check_name(agent.name, label, agent)
        plan.append(_PlannedOutput(
            rel_path=PurePosixPath("agents") / f"{agent.name}.md",
            label=label,
            subject=agent,
            kind="agent",
            component=agent,
        ))
        for local_skill in agent.skills:
            local_label = f"에이전트 '{agent.name}'의 로컬 스킬 '{local_skill.name}'"
            check_name(local_skill.name, local_label, local_skill)
            plan.append(_PlannedOutput(
                rel_path=(
                    PurePosixPath("skills")
                    / _local_skill_dir_name(agent.name, local_skill.name)
                    / "SKILL.md"
                ),
                label=local_label,
                subject=local_skill,
                kind="local_skill",
                component=local_skill,
                agent=agent,
            ))

    # hooks.json (SETTINGS) — 프로젝트가 참조하는 훅이 있을 때만 계획에 합류.
    # 고정 경로 'hooks/hooks.json'이라 컴포넌트 산출(skills/·agents/)과 충돌할 수
    # 없지만, 경로 집합·결정성 일관성을 위해 plan에 포함한다.
    hooks_text = compile_hooks_json(project)
    if hooks_text is not None:
        plan.append(_PlannedOutput(
            rel_path=PurePosixPath("hooks") / "hooks.json",
            label="hooks.json (lifecycle hooks)",
            subject=project,
            kind="hooks_json",
            component=project,
        ))

    # schemas.json (블랙보드 class_definitions) — 정의가 있을 때만 계획에 합류.
    # 고정 경로 'schemas/schemas.json'이라 컴포넌트 산출(skills/·agents/)과 충돌
    # 불가하지만, 경로 집합·결정성 일관성을 위해 plan에 포함한다.
    schemas_text = compile_schemas_json(project)
    if schemas_text is not None:
        plan.append(_PlannedOutput(
            rel_path=PurePosixPath("schemas") / "schemas.json",
            label="schemas.json (blackboard class definitions)",
            subject=project,
            kind="schemas_json",
            component=project,
        ))

    # plugin.json (플러그인 매니페스트) — 무조건 계획에 합류(매니페스트 없이는
    # 산출 디렉토리를 CC 플러그인으로 설치할 수 없다).
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

    return plan, errors


def _copy_files_tree(src_dir: Path, dst_dir: Path) -> list[Path]:
    """src_dir 트리를 dst_dir로 정렬 순회 복사한다 (결정적 로그).

    심볼릭 링크는 따라가지 않는다 — 디렉토리는 재귀하지 않고, 파일은 복사하지
    않는다. 기존 dst_dir는 복사 전 삭제한다(스테일 잔존 방지 — out 디렉토리
    전체가 아니라 files/ 하위만 지운다).

    반환: 실제로 복사된 파일의 dst_dir 기준 경로 목록 (정렬 순서, 디렉토리
    자체는 포함하지 않음).
    """
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []
    for root, dirnames, filenames in os.walk(src_dir, followlinks=False):
        root_path = Path(root)
        rel_root = root_path.relative_to(src_dir)
        # in-place 정렬 + 심볼릭 링크 디렉토리 제외 — os.walk가 다음 순회에서
        # 이 리스트를 그대로 재사용하므로 순회 순서·재귀 범위를 동시에 제어한다.
        dirnames[:] = sorted(d for d in dirnames if not (root_path / d).is_symlink())
        for dirname in dirnames:
            (dst_dir / rel_root / dirname).mkdir(parents=True, exist_ok=True)
        for filename in sorted(filenames):
            src_file = root_path / filename
            if src_file.is_symlink():
                continue
            dst_file = dst_dir / rel_root / filename
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            copied.append(dst_file)
    return copied


def _scan_dangling_file_refs(project, files_dir: Path) -> list[ValidationError]:
    """스킬/에이전트(로컬 스킬 포함) body에서 파일 참조 토큰을 스캔해 files_dir에
    실존하지 않는 참조를 `dangling_file_ref` 경고로 반환한다.

    Validator가 아닌 컴파일러 소관이다 — 검증기는 파일시스템 무접근 순수성을
    유지한다.
    """
    warnings: list[ValidationError] = []

    def scan(label: str, subject: object, body: str) -> None:
        for match in _FILE_REF_RE.finditer(body or ""):
            rel = match.group(1)
            candidate = files_dir.joinpath(*rel.split("/"))
            if candidate.exists():
                continue
            warnings.append(ValidationError(
                rule="dangling_file_ref",
                message=(
                    f"{label}의 본문이 참조하는 파일이 files/ 아래에 없습니다: "
                    f"${{CLAUDE_PLUGIN_ROOT}}/files/{rel}"
                ),
                source=rel,
                subject=subject,
            ))

    for skill in project.skills:
        scan(f"스킬 '{skill.name}'", skill, getattr(skill, "body", ""))
    for agent in project.agents:
        scan(f"에이전트 '{agent.name}'", agent, getattr(agent, "body", ""))
        for local_skill in agent.skills:
            scan(
                f"에이전트 '{agent.name}'의 로컬 스킬 '{local_skill.name}'",
                local_skill,
                getattr(local_skill, "body", ""),
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
) -> CompileResult:
    """프로젝트를 out_dir에 컴파일한다.

    게이트: 검증 에러 + 게이트 강화 에러(이름 규약·경로 충돌)가 1건이라도 있으면
    파일을 쓰지 않고 거부한다. 경고만 있으면 통과시키고 warnings에 동봉한다.

    files_dir(WP-FR, 선택): 실존 디렉토리면 <out_dir>/files/로 트리 복사하고
    (게이트 통과 시에만), 스킬/에이전트 body의 파일 참조 토큰을 스캔해 실존하지
    않는 참조를 `dangling_file_ref` 경고로 추가한다(files_dir가 None이면 스캔
    생략 — 기존 산출물/문자열 불변, 하위 호환).
    """
    out_dir = Path(out_dir)
    all_findings = Validator.validate_project(project)
    errors = [e for e in all_findings if not e.is_warning]
    warnings = [e for e in all_findings if e.is_warning]

    # 파일 쓰기 전에 산출 계획 수립 — 이름 규약 + 경로 충돌 게이트
    plan, gate_errors = _plan_outputs(project)
    errors = errors + gate_errors

    result = CompileResult(errors=errors, warnings=warnings)
    if errors:
        # 거부 — 무엇이 막혔는지 skipped에 기록 (산출 계획 전체 = 로컬 스킬 포함)
        for item in plan:
            result.skipped.append(("compile_gate_error", item.label))
        return result

    for item in plan:
        if item.kind == "skill":
            text = compile_skill(item.component, project=project)
        elif item.kind == "agent":
            text = compile_agent(item.component, project=project)
        elif item.kind == "hooks_json":
            text = compile_hooks_json(project) or ""
        elif item.kind == "schemas_json":
            text = compile_schemas_json(project) or ""
        elif item.kind == "plugin_manifest":
            text = compile_plugin_manifest(project)
        else:  # local_skill
            text = compile_skill(item.component, local=True, project=project)
        path = out_dir / item.rel_path
        _write_text(path, text)
        result.written.append(path)

    if files_dir is not None:
        files_dir_path = Path(files_dir)
        if files_dir_path.is_dir():
            result.copied_files = _copy_files_tree(files_dir_path, out_dir / "files")
        result.warnings.extend(_scan_dangling_file_refs(project, files_dir_path))

    return result
