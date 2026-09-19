# daedalus/compiler/plan.py
"""산출 계획 — 파일을 쓰기 전에 "무엇이 어디로 나가는가"를 전부 계산한다.

``project_compiler.py``에서 이동만 했다(WP-FK2 C0, 동작 불변). 쓰기·복사·병합은
그대로 ``project_compiler``에 남고, 여기는 **계획과 계획 단계의 게이트**만 담는다:

  - `_PlannedOutput` — 계획된 산출물 1건(상대 경로가 충돌 키).
  - `_plan_outputs` — 전역 스킬·에이전트·스킬 파일·훅·스키마·작업 폴더 문서·
    매니페스트의 산출 경로 집합 + 이름 규약/경로 충돌/훅 스크립트 이름 게이트.
경로·이름 규약과 트리 열거 규칙(`_OUTPUT_NAME_RE`/`SKILL_FILES_DIRNAME`/
`_skill_dir_name`/`_hook_script_name_conflicts`/`_iter_tree_files`/`_is_link_like`)은
**`compiler/units/paths.py`로 옮겼다**(WP-5, 이동만) — 계획과 실제 쓰기가 같은
규칙을 봐야 하는 것들이고, 앞으로 산출 단위들이 함께 쓴다. 여기서 **같은 객체**를
재-export하므로(복제가 아니다) 계획과 쓰기의 판정은 하나다.

``project_compiler``가 전부 재-export하므로 기존 임포트 경로
(`from daedalus.compiler.project_compiler import SKILL_FILES_DIRNAME` 등)는
무수정으로 동작한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from daedalus.compiler.emit import (
    _is_local_build,
    compile_hook_scripts,
    compile_hooks_json,
    compile_schemas_json,
    emits_output_file,
)
from daedalus.compiler.emit.guides import (
    BLACKBOARD_GUIDE_KIND,
    WORKFLOW_GUIDE_KIND,
    blackboard_guide_referenced,
    guide_rel_path,
    workflow_guide_referenced,
)
from daedalus.compiler.emit.wrapped import needs_runner_agent
from daedalus.compiler.units.paths import (  # noqa: F401 — 재-export 파사드
    SKILL_FILES_DIRNAME,
    _hook_script_name_conflicts,
    _is_link_like,
    _iter_tree_files,
    _OUTPUT_NAME_RE,
    _skill_dir_name,
)
from daedalus.compiler.workspace import has_manual_frontmatter
from daedalus.model.plugin.hook import HOOK_SCRIPT_DIR
from daedalus.model.validation import ValidationError



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


def _plan_outputs(
    project, skill_files_dir: Path | None = None, resolved_hooks=None,
) -> tuple[list[_PlannedOutput], list[ValidationError], list[ValidationError]]:
    """파일 쓰기 전에 전체 산출 경로 집합을 계산하고 게이트 에러를 수집한다.

    에러 3종:
      compile_invalid_component_name — 산출 이름 규약 불일치 (게이트에서 에러 승격)
      compile_output_path_conflict   — 동일 산출 경로 중복 (조용한 덮어쓰기 방지)
      duplicate_hook_script          — 서로 다른 훅이 같은 스크립트 파일명으로
                                       슬러그됨 (조용한 드롭 방지, WP-HS)

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
        # 산출 파일 보유 판정의 실체는 컴포넌트의 `emits_output()` 하나다
        # (원칙 1 — `emits_output_file`은 그 한 줄 파사드다). 참조 용도 wrapped와
        # 비활성 랩핑 스킬이 여기서 빠진다(둘 다 WP-WR 사용자 확정 2026-09-07).
        # `emit/guides.py`의 포인터 판정이 같은 함수를 쓰므로 "계획에 오른 집합"과
        # "포인터 판정 대상 집합"이 어긋날 수 없다.
        if not emits_output_file(skill):
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
        # state 용도 랩핑 스킬의 실행 서브에이전트 (WP-WR, 사용자 확정
        # 2026-09-12 — 외부 플러그인 스킬은 서브에이전트에서만 쓴다). 이름이
        # 랩퍼와 같아 사용자 에이전트와는 duplicate_component_name이 이미 막는다.
        if needs_runner_agent(skill):
            plan.append(_PlannedOutput(
                rel_path=cc_prefix / "agents" / f"{skill.name}.md",
                label=f"랩핑 스킬 '{skill.name}'의 실행 서브에이전트",
                subject=skill,
                kind="wrapped_runner",
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
        errors.extend(_hook_script_name_conflicts(project, resolved_hooks))
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
            # paths 필드와 본문 수기 프론트매터가 겹치면 `---` 블록이 둘 나간다.
            # 본문은 건드리지 않는다 — 합치려면 사용자의 키를 해석해야 하고,
            # 조용한 변형은 "내가 쓴 게 사라졌다"로 돌아온다(A13).
            if doc.paths and has_manual_frontmatter(doc.body or ""):
                warnings.append(ValidationError(
                    rule="rule_body_frontmatter",
                    message=(
                        f"규칙 '{doc.name}'의 본문이 '---'로 시작하는데 paths 필드도 "
                        f"설정돼 있습니다 — 프론트매터가 두 번 배출되어 뒤의 것이 "
                        f"본문으로 읽힙니다. 본문의 프론트매터를 지우고 그 내용을 "
                        f"paths 필드로 옮기세요."
                    ),
                    source=f"rules/{doc.name}.md",
                    subject=doc,
                ))
            plan.append(_PlannedOutput(
                rel_path=cc_prefix / "rules" / f"{doc.name}.md",
                label=f"rules/{doc.name}.md (workspace rule)",
                subject=doc,
                kind="workspace_rule",
                component=doc,
            ))

    # 공통 안내 파일 (WP-FK2 C3) — 루트 직하 guides/<플러그인>/. **포인터가 하나도
    # 나가지 않으면 계획에 넣지 않는다**: 아무도 읽지 않는 파일이 산출에 남으면
    # "이건 뭐냐"가 되고, 토큰 리포트도 쓰이지 않는 비용을 센다.
    for kind, what in (
        (WORKFLOW_GUIDE_KIND, "shared workflow guide"),
        (BLACKBOARD_GUIDE_KIND, "shared blackboard guide"),
    ):
        referenced = (
            workflow_guide_referenced if kind == WORKFLOW_GUIDE_KIND
            else blackboard_guide_referenced
        )
        if not referenced(project):
            continue
        rel = guide_rel_path(project, kind)
        plan.append(_PlannedOutput(
            rel_path=PurePosixPath(rel),
            label=f"{rel} ({what})",
            subject=project,
            kind=kind,
            component=project,
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
