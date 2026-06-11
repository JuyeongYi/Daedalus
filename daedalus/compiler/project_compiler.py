# daedalus/compiler/project_compiler.py
"""프로젝트 컴파일 — 게이트 + 파일 쓰기 (순수 stdlib, PyQt 무관).

CC 플러그인 출력 구조:
    <out>/skills/<skill-name>/SKILL.md          # 전역 스킬 4종
    <out>/skills/<agent-name>--<skill-name>/SKILL.md   # 에이전트 로컬 스킬
    <out>/agents/<agent-name>.md                # 에이전트

컴파일 게이트(정책 8): Validator.validate_project의 에러(is_warning=False)가
1건이라도 있으면 컴파일 거부 — 파일을 쓰지 않고 errors를 반환한다. 경고는 통과.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from daedalus.compiler.emit import compile_agent, compile_skill
from daedalus.model.plugin.skill import Skill
from daedalus.model.validation import ValidationError, Validator


@dataclass
class CompileResult:
    """컴파일 결과.

    written: 실제로 쓴 파일 경로 목록.
    errors: 컴파일을 거부시킨 검증 에러(is_warning=False). 비어 있으면 성공.
    warnings: 통과한 경고(결과에 동봉).
    skipped: (이유, 컴포넌트 이름) 목록 — 거부 시 쓰지 못한 항목 등.
    """
    written: list[Path] = field(default_factory=list)
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _skill_dir_name(skill_name: str) -> str:
    return skill_name


def _local_skill_dir_name(agent_name: str, skill_name: str) -> str:
    """에이전트 로컬 스킬 디렉토리명 — '<agent>--<skill>' (충돌 없는 규칙)."""
    return f"{agent_name}--{skill_name}"


def _write_text(path: Path, text: str) -> None:
    """LF 줄바꿈 + UTF-8(BOM 없음)으로 쓴다 (결정적)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="" → 파이썬이 \n을 변환하지 않음(LF 그대로). text는 emit에서 LF 보장.
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def compile_project(project, out_dir: Path | str) -> CompileResult:
    """프로젝트를 out_dir에 컴파일한다.

    게이트: validate_project 에러 1건 이상이면 파일을 쓰지 않고 거부한다.
    경고만 있으면 통과시키고 warnings에 동봉한다.
    """
    out_dir = Path(out_dir)
    all_findings = Validator.validate_project(project)
    errors = [e for e in all_findings if not e.is_warning]
    warnings = [e for e in all_findings if e.is_warning]

    result = CompileResult(errors=errors, warnings=warnings)
    if errors:
        # 거부 — 무엇이 막혔는지 skipped에 기록
        for skill in project.skills:
            result.skipped.append(("validation_error", skill.name))
        for agent in project.agents:
            result.skipped.append(("validation_error", agent.name))
        return result

    skills_root = out_dir / "skills"
    agents_root = out_dir / "agents"

    # 전역 스킬
    for skill in project.skills:
        if not isinstance(skill, Skill):
            continue
        text = compile_skill(skill, project=project)
        path = skills_root / _skill_dir_name(skill.name) / "SKILL.md"
        _write_text(path, text)
        result.written.append(path)

    # 에이전트 + 로컬 스킬
    for agent in project.agents:
        text = compile_agent(agent, project=project)
        path = agents_root / f"{agent.name}.md"
        _write_text(path, text)
        result.written.append(path)

        for local_skill in agent.skills:
            local_text = compile_skill(local_skill, local=True, project=project)
            local_path = (
                skills_root
                / _local_skill_dir_name(agent.name, local_skill.name)
                / "SKILL.md"
            )
            _write_text(local_path, local_text)
            result.written.append(local_path)

    return result
