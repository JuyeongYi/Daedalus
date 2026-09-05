# daedalus/view/editors/variable_loader.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from daedalus.model.plugin.enums import BuildTarget

# 변수 삽입 팝업의 컨텍스트 — 어디의 본문을 편집하고 있는가.
#   "skill":     SKILL.md 4종 — CC가 스킬 본문에서 모든 변수를 치환한다(풀 지원)
#   "agent":     에이전트 .md — 루트 변수 2종만 인식(스킬 전용 변수는 치환 안 됨,
#                skill_dir_token_in_agent 경고의 시각적 짝)
#   "workspace": .claude/CLAUDE.md 구역·.claude/rules/ — 에이전트와 같은 루트만
VariableContext = Literal["skill", "agent", "workspace"]

_ALL_CONTEXTS: tuple[str, ...] = ("skill", "agent", "workspace")


@dataclass
class VariableEntry:
    name: str
    description: str
    source: Literal["builtin", "global", "project"]
    # 이 변수가 유효한 편집 컨텍스트. 사용자 정의(global/project) 변수는 기본
    # 전 컨텍스트 — 자기 토큰의 유효 범위는 자기가 안다.
    contexts: tuple[str, ...] = _ALL_CONTEXTS
    # LOCAL 빌드에서도 쓸 수 있는가 — ${CLAUDE_PLUGIN_ROOT}는 로컬 설치에
    # 플러그인 디렉토리 자체가 없어 False.
    local_ok: bool = True


_SKILL_ONLY: tuple[str, ...] = ("skill",)

_BUILTIN: list[VariableEntry] = [
    VariableEntry("$ARGUMENTS", "스킬 호출 시 전달된 전체 인수", "builtin",
                  contexts=_SKILL_ONLY),
    VariableEntry("$ARGUMENTS[0]", "첫 번째 인수 (N은 임의 숫자)", "builtin",
                  contexts=_SKILL_ONLY),
    VariableEntry("$N", "$ARGUMENTS[N] 단축형", "builtin", contexts=_SKILL_ONLY),
    VariableEntry("${CLAUDE_SESSION_ID}", "현재 세션 ID", "builtin",
                  contexts=_SKILL_ONLY),
    VariableEntry("${CLAUDE_SKILL_DIR}", "스킬 SKILL.md 파일의 디렉토리 경로",
                  "builtin", contexts=_SKILL_ONLY),
    VariableEntry("${CLAUDE_PLUGIN_ROOT}", "플러그인 설치 루트 (마켓플레이스 전용)",
                  "builtin", local_ok=False),
    VariableEntry("${CLAUDE_PROJECT_DIR}", "작업 폴더(프로젝트) 루트", "builtin"),
]


# 현재 프로젝트의 빌드 타깃 제공자 — app.set_project가 등록한다. 에디터가
# 컴포넌트 탭마다 생겨 직접 배선할 수 없는 사정이 SkillFilesPanel의
# set_project_dir_provider와 같다. 팝업을 열 때마다 조회하므로 프로젝트
# 속성에서 타깃을 바꾸면 다음 열기부터 반영된다(생성 시점 고정이면 스테일).
_BUILD_TARGET_PROVIDER = None  # Callable[[], BuildTarget | None] | None


def set_build_target_provider(provider) -> None:
    global _BUILD_TARGET_PROVIDER
    _BUILD_TARGET_PROVIDER = provider


def get_build_target() -> BuildTarget | None:
    if _BUILD_TARGET_PROVIDER is not None:
        return _BUILD_TARGET_PROVIDER()
    return None


def variables_for(
    context: VariableContext,
    build_target: BuildTarget | None = None,
    project_dir: Path | None = None,
) -> list[VariableEntry]:
    """편집 컨텍스트·빌드 타깃에 유효한 변수만 걸러 반환 (사용자 확정 매트릭스).

    한 목록을 모든 표면이 공유하면 에이전트/규칙 본문에 스킬 전용 변수를,
    로컬 플러그인에 ${CLAUDE_PLUGIN_ROOT}를 넣을 수 있게 되는데 — 둘 다
    치환되지 않은 채 산출로 흘러가 런타임에야 드러난다.
    """
    is_local = build_target is BuildTarget.LOCAL
    return [
        v for v in load_variables(project_dir)
        if context in v.contexts and (v.local_ok or not is_local)
    ]


def load_variables(project_dir: Path | None = None) -> list[VariableEntry]:
    """기본 제공 + 글로벌 + 프로젝트 변수를 병합해 반환.

    우선순위 낮음 → 높음: builtin < global < project
    파일 없으면 해당 레벨은 빈 목록.
    """
    result: list[VariableEntry] = list(_BUILTIN)

    global_file = Path.home() / ".daedalus" / "variables.yaml"
    result.extend(_load_yaml(global_file, "global"))

    if project_dir is not None:
        project_file = project_dir / ".daedalus" / "variables.yaml"
        result.extend(_load_yaml(project_file, "project"))

    return result


def _load_yaml(
    path: Path,
    source: Literal["global", "project"],
) -> list[VariableEntry]:
    if not path.exists():
        return []
    try:
        import yaml  # type: ignore[import-untyped]
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, list):
            return []
        return [
            VariableEntry(
                name=item.get("name", ""),
                description=item.get("description", ""),
                source=source,
            )
            for item in data
            if isinstance(item, dict) and item.get("name")
        ]
    except Exception:
        return []
