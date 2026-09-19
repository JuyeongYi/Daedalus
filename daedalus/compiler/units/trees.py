# daedalus/compiler/units/trees.py
"""복사 산출 단위 — 스킬별 동봉 파일과 공용 files/ 트리 (WP-5, 이동만).

두 단위의 차이는 **계획에 오르는 단위**다. `SkillFilesUnit`은 파일 하나가
계획 행 하나라 경로 충돌 게이트를 그대로 받는다(SKILL.md를 덮는 동봉 파일은
에러다). `FilesTreeUnit`은 트리 하나가 행 하나라 "경로 하나 = 산출 하나"를
만족하지 않는다 — `exclusive=False`로 게이트와 `skipped` 보고 밖에 둔다
(종전에도 계획 밖이라 검사를 받지 않았다. 형상 불변).
"""
from __future__ import annotations

from pathlib import PurePosixPath

from daedalus.compiler import plan_kinds
from daedalus.compiler.units.base import CopyUnit, OutputMode, PlannedOutput
from daedalus.compiler.units.paths import (
    SKILL_FILES_DIRNAME,
    _is_link_like,
    _iter_tree_files,
    _skill_dir_name,
)
from daedalus.model.validation import ValidationError


class SkillFilesUnit(CopyUnit):
    """스킬별 동봉 파일 (WP-SF).

    하위 폴더명이 스킬 산출 디렉토리명과 일치할 때만 SKILL.md 옆으로 가는 복사
    계획에 합류한다. 계획 집합 합류가 곧 충돌 방어다 — 'SKILL.md'라는 이름의
    동봉 파일은 경로 충돌 검사가 에러로 거부한다. 일치하는 스킬이 없는 하위
    폴더는 `unknown_skill_files_dir` 경고.
    """

    id = plan_kinds.SKILL_FILE

    def plan(self, ctx, gate) -> list[PlannedOutput]:
        skill_files_dir = ctx.skill_files_dir
        if skill_files_dir is None or not skill_files_dir.is_dir():
            return []
        project = ctx.project
        # 스킬 산출 디렉토리명 → 컴포넌트. 계획에 오른 스킬(= 산출 파일을 내는
        # 스킬)만 대상이다 — `ComponentUnit`이 쓰는 판정과 같은 메서드다.
        skill_dirs: dict[str, object] = {
            _skill_dir_name(skill.name): skill
            for skill in (getattr(project, "skills", None) or [])
            if skill.emits_output()
        }
        out: list[PlannedOutput] = []
        for sub in sorted(skill_files_dir.iterdir(), key=lambda p: p.name):
            if _is_link_like(sub):
                continue
            if not sub.is_dir():
                gate.warn(ValidationError(
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
                gate.warn(ValidationError(
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
                out.append(PlannedOutput(
                    rel_path=ctx.cc_prefix / "skills" / sub.name / PurePosixPath(*rel_parts),
                    label=f"스킬 파일 '{sub.name}/{'/'.join(rel_parts)}'",
                    subject=component,
                    kind=plan_kinds.SKILL_FILE,
                    component=component,
                    src_path=src,
                    mode=OutputMode.COPY_FILE,
                ))
        return out

    def emit(self, planned, ctx, sink) -> None:
        # 스킬별 동봉 파일 (WP-SF) — 텍스트 산출이 아니라 복사다.
        if planned.src_path is None:  # pragma: no cover - 계획이 항상 채운다
            return
        sink.copy_file(planned, planned.src_path)


class FilesTreeUnit(CopyUnit):
    """공용 파일 트리 (WP-FR) — `<out>/files/`."""

    id = plan_kinds.FILES_TREE

    def plan(self, ctx, gate) -> list[PlannedOutput]:
        files_dir = ctx.files_dir
        if files_dir is None or not files_dir.is_dir():
            return []
        return [PlannedOutput(
            rel_path=PurePosixPath("files"),
            label="files/ (공용 파일 트리)",
            subject=ctx.project,
            kind=plan_kinds.FILES_TREE,
            component=ctx.project,
            mode=OutputMode.COPY_TREE,
            exclusive=False,
        )]

    def emit(self, planned, ctx, sink) -> None:
        # LOCAL의 out_dir는 사용자의 작업 폴더다 — 기존 <out>/files/를 지우면
        # 사용자 파일을 지울 수 있으므로 덮어쓰기 복사만 한다(스테일 잔존은
        # 감수). MARKETPLACE 스테이징 디렉토리는 종전대로 삭제 후 복사.
        sink.copy_tree(planned, ctx.files_dir, clear_first=not ctx.is_local)
