# daedalus/model/validation/project_rules/body_variables.py
"""본문 경로·인수 변수 규칙 (이동만 — 동작 불변).

plugin_root_in_local_build / skill_dir_token_in_agent. 셋 다 본문 문자열을
훑으며, 코드로 표시된 부분(``_strip_markdown_code``)은 검사하지 않는다.
"""
from __future__ import annotations

from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.validation.project_rules.text import _strip_markdown_code
from daedalus.model.validation.severity import ValidationError


class _BodyVariableRules:
    """본문 변수 규칙 모음 (_ProjectRules 믹스인)."""

    @staticmethod
    def _check_plugin_root_in_local_build(project) -> list[ValidationError]:
        """plugin_root_in_local_build — build_target=LOCAL인데 스킬/에이전트
        본문에 **플러그인 전용 변수**가 남아 있으면 경고.

        CC는 `${CLAUDE_PLUGIN_ROOT}`와 `${CLAUDE_PLUGIN_DATA}`를 **플러그인
        스킬에서만 치환한다**(공식 skills 문서의 치환 표). 프로젝트 설치 빌드는
        플러그인이 아니므로 이 변수들이 리터럴 문자열 그대로 남는다.

        WP-RT 이후 files/ 참조는 타깃 중립 ``${ROOT}/files/``를 쓰므로 files/
        예외 처리는 없다 — 본문에 CC 원시 플러그인 변수가 보이면 그대로 문제다.

        단 **코드로 표시된 부분은 검사하지 않는다**(백틱 인라인 코드, 코드 펜스).
        규격을 설명하는 문서 스킬은 이 변수 이름을 언급할 수밖에 없는데, 그것을
        "죽은 경로"로 짚으면 고칠 수 없는 경고가 영구히 남는다. 실제 경로로 쓰는
        경우는 `${ROOT}`를 쓰는 것이 규약이므로 이 좁힘으로 잃는 것이 없다.
        """
        from daedalus.model.plugin.variables import PLUGIN_ONLY_VARIABLES

        build_target = getattr(project, "build_target", BuildTarget.MARKETPLACE)
        if build_target is not BuildTarget.LOCAL:
            return []
        errors: list[ValidationError] = []

        def _scan(label: str, subject: object, body: str, path: tuple[str, ...]) -> None:
            remaining = _strip_markdown_code(body or "")
            for var in PLUGIN_ONLY_VARIABLES:
                if var in remaining:
                    errors.append(ValidationError(
                        rule="plugin_root_in_local_build",
                        message=(
                            f"{label}의 본문에 '{var}'가 남아 있습니다 — 이 변수는 "
                            f"플러그인 스킬에서만 치환되므로, 프로젝트 설치 빌드에서는 "
                            f"문자열 그대로 남습니다. "
                            f"'${{CLAUDE_PROJECT_DIR}}'나 '${{CLAUDE_SKILL_DIR}}'를 쓰세요."
                        ),
                        source=label,
                        subject=subject,
                        path=path,
                    ))

        for skill in getattr(project, "skills", []):
            _scan(
                f"스킬 '{skill.name}'", skill, getattr(skill, "body", ""),
                (f"skill:{skill.name}",),
            )
        for agent in getattr(project, "agents", []):
            _scan(
                f"에이전트 '{agent.name}'", agent, getattr(agent, "body", ""),
                (f"agent:{agent.name}",),
            )
        return errors

    @staticmethod
    def _check_skill_dir_token_in_agent(project) -> list[ValidationError]:
        """skill_dir_token_in_agent — 에이전트 본문에 `${CLAUDE_SKILL_DIR}`가
        있으면 경고 (WP-SF).

        CC의 이 변수는 **스킬 전용**이다(공식 skills 문서의 치환 표 — 에이전트는
        단일 .md라 자기 디렉토리 개념 자체가 없다). 에이전트 .md에 남으면
        치환되지 않고 리터럴 문자열로 남는다. 파일을 주려면 스킬에 실어
        에이전트 skills 프론트매터로 전달하거나(WP-AS 자동 합류), 공용 files/를
        `${ROOT}/files/…`로 참조하라.

        코드로 표시된 부분(백틱·펜스)은 검사하지 않는다 —
        `plugin_root_in_local_build`와 같은 이유(규격 설명 문서의 언급까지
        짚으면 고칠 수 없는 경고가 남는다). 빌드 타깃 무관 — 양쪽 다 안 된다.
        """
        token = "${CLAUDE_SKILL_DIR}"
        errors: list[ValidationError] = []
        for agent in getattr(project, "agents", []):
            remaining = _strip_markdown_code(getattr(agent, "body", "") or "")
            if token in remaining:
                errors.append(ValidationError(
                    rule="skill_dir_token_in_agent",
                    message=(
                        f"에이전트 '{agent.name}'의 본문에 '{token}'가 있습니다 — "
                        f"이 변수는 스킬에서만 치환됩니다(에이전트는 전용 디렉토리가 "
                        f"없습니다). 파일은 스킬에 동봉해 skills 프론트매터로 "
                        f"전달하거나 공용 files/를 '${{ROOT}}/files/…'로 참조하세요."
                    ),
                    source=agent.name,
                    subject=agent,
                    path=(f"agent:{agent.name}",),
                ))
        return errors
