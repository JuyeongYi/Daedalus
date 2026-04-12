# daedalus/view/editors/variable_loader.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass
class VariableEntry:
    name: str
    description: str
    source: Literal["builtin", "global", "project"]


_BUILTIN: list[VariableEntry] = [
    VariableEntry("$ARGUMENTS", "스킬 호출 시 전달된 전체 인수", "builtin"),
    VariableEntry("$ARGUMENTS[0]", "첫 번째 인수 (N은 임의 숫자)", "builtin"),
    VariableEntry("$N", "$ARGUMENTS[N] 단축형", "builtin"),
    VariableEntry("${CLAUDE_SESSION_ID}", "현재 세션 ID", "builtin"),
    VariableEntry("${CLAUDE_SKILL_DIR}", "스킬 SKILL.md 파일의 디렉토리 경로", "builtin"),
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
