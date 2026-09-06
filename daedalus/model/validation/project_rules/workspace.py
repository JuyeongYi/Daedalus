# daedalus/model/validation/project_rules/workspace.py
"""작업 폴더 문서(.claude/CLAUDE.md · .claude/rules/) 규칙 (이동만 — 동작 불변) — WP-WD."""
from __future__ import annotations

from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.validation.project_rules.naming import COMPONENT_NAME_RE
from daedalus.model.validation.severity import ValidationError


class _WorkspaceDocRules:
    """작업 폴더 문서 규칙 모음 (_ProjectRules 믹스인)."""

    @staticmethod
    def _check_workspace_docs(project) -> list[ValidationError]:
        """작업 폴더 문서 규칙 3종 (WP-WD).

        - duplicate_rule_name: 같은 이름의 규칙 둘 — 이름이 곧 파일명이라 에러다.
        - invalid_rule_name: 파일명 규약 불일치 — 편집 중에는 경고이고, 컴파일
          게이트가 에러로 승격한다(컴포넌트 이름과 같은 관례).
        - workspace_doc_in_marketplace_build: 마켓플레이스 플러그인은 작업 폴더에
          쓸 수 없어 배출되지 않는다. **내용이 있을 때만** 경고한다 — 빈 문서는
          배출할 것이 없으므로 잃는 것도 없다.
        """
        errors: list[ValidationError] = []
        rules = list(getattr(project, "rules", None) or [])

        seen: dict[str, int] = {}
        for doc in rules:
            seen[doc.name] = seen.get(doc.name, 0) + 1
        for name, count in seen.items():
            if count > 1:
                errors.append(ValidationError(
                    rule="duplicate_rule_name",
                    message=(
                        f"규칙 문서 이름 '{name}'이 {count}번 쓰였습니다. 이름이 곧 "
                        f".claude/rules/<이름>.md 파일명이라 서로 덮어씁니다."
                    ),
                    source=name,
                    subject=project,
                ))

        for doc in rules:
            if not COMPONENT_NAME_RE.match(doc.name or ""):
                errors.append(ValidationError(
                    rule="invalid_rule_name",
                    message=(
                        f"규칙 문서 이름 '{doc.name}'이 규약 "
                        f"'^[a-z0-9][a-z0-9-]*$'에 맞지 않습니다. 이름이 산출 "
                        f"파일명이 됩니다."
                    ),
                    source=doc.name,
                    subject=doc,
                ))

        if getattr(project, "build_target", None) is not BuildTarget.LOCAL:
            claude_md = getattr(project, "claude_md", None)
            filled = [doc for doc in rules if doc.has_content()]
            if claude_md is not None and claude_md.has_content():
                filled = [claude_md] + filled
            if filled:
                errors.append(ValidationError(
                    rule="workspace_doc_in_marketplace_build",
                    message=(
                        f"작업 폴더 문서 {len(filled)}건이 있지만 빌드 타깃이 "
                        f"마켓플레이스라 배출되지 않습니다 — 플러그인은 설치 대상 "
                        f"작업 폴더의 .claude/에 쓸 수 없습니다. 로컬 플러그인으로 "
                        f"바꾸거나 내용을 스킬 본문으로 옮기세요."
                    ),
                    source=project.name,
                    subject=project,
                ))
            # WP-WS — settings 베이크도 작업 폴더 문서와 같은 제약이다:
            # 마켓플레이스 플러그인은 settings.local.json에 쓸 수 없다.
            if getattr(project, "workspace_settings", None):
                errors.append(ValidationError(
                    rule="workspace_settings_in_marketplace_build",
                    message=(
                        "작업 폴더 설정(workspace_settings)이 있지만 빌드 타깃이 "
                        "마켓플레이스라 베이크되지 않습니다 — 플러그인은 설치 대상 "
                        "작업 폴더의 .claude/settings.local.json에 쓸 수 없습니다. "
                        "로컬 플러그인으로 바꾸세요."
                    ),
                    source=project.name,
                    subject=project,
                ))
        return errors
