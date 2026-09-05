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

    @staticmethod
    def _check_skill_only_variables(project) -> list[ValidationError]:
        """skill_only_variable_in_body — 스킬 전용 변수가 에이전트 본문이나 작업
        폴더 문서(.claude/CLAUDE.md 구역·.claude/rules/)에 있으면 경고 (A6).

        `$ARGUMENTS`(`$ARGUMENTS[N]` 포함)·`${CLAUDE_SESSION_ID}`·
        `${CLAUDE_SKILL_DIR}`는 CC가 **스킬 본문에서만** 치환한다(공식 skills
        문서의 치환 표). 다른 표면에 쓰면 리터럴 문자열 그대로 산출에 나가
        런타임에야 드러난다 — 변수 삽입 팝업의 컨텍스트 필터
        (`view/editors/variable_loader.variables_for`)의 검증기 짝이다.

        **`${CLAUDE_SKILL_DIR}`는 에이전트에서만 제외한다** —
        `skill_dir_token_in_agent`(WP-SF)가 이미 그 토큰을 에이전트 본문에서
        짚고, 대안(스킬에 동봉해 skills 프론트매터로 전달)까지 안내하는 전용
        메시지를 갖고 있다. 같은 사실을 두 규칙이 말하면 어느 쪽을 고쳐야
        하는지 흐려지므로, 기존 규칙을 확장하는 대신 이 규칙이 그 조합만
        비운다. 작업 폴더 문서는 기존 규칙의 대상이 아니므로 세 토큰을 모두
        검사한다.

        코드로 표시된 부분(백틱·펜스)은 검사하지 않는다 — 위 두 규칙과 같은
        이유(규격을 설명하는 문서의 언급까지 짚으면 고칠 수 없는 경고가 남는다).
        빌드 타깃 무관 — 어느 타깃에서도 치환되지 않는다.
        """
        from daedalus.model.plugin.variables import SKILL_ONLY_VARIABLES

        errors: list[ValidationError] = []

        def _scan(
            label: str,
            subject: object,
            body: str,
            tokens: tuple[str, ...],
            path: tuple[str, ...],
        ) -> None:
            remaining = _strip_markdown_code(body or "")
            for var in tokens:
                if var in remaining:
                    errors.append(ValidationError(
                        rule="skill_only_variable_in_body",
                        message=(
                            f"{label}의 본문에 '{var}'가 있습니다 — 이 변수는 "
                            f"스킬 본문에서만 치환되므로 여기서는 문자열 그대로 "
                            f"남습니다. 값이 필요하면 스킬에서 받아 넘기세요."
                        ),
                        source=label,
                        subject=subject,
                        path=path,
                    ))

        agent_tokens = tuple(
            v for v in SKILL_ONLY_VARIABLES if v != "${CLAUDE_SKILL_DIR}"
        )
        for agent in getattr(project, "agents", []):
            _scan(
                f"에이전트 '{agent.name}'", agent, getattr(agent, "body", ""),
                agent_tokens, (f"agent:{agent.name}",),
            )

        claude_md = getattr(project, "claude_md", None)
        if claude_md is not None:
            _scan(
                "작업 폴더 문서 'CLAUDE.md'", claude_md,
                getattr(claude_md, "body", ""), SKILL_ONLY_VARIABLES, (),
            )
        for doc in getattr(project, "rules", None) or []:
            _scan(
                f"규칙 문서 '{doc.name}'", doc, getattr(doc, "body", ""),
                SKILL_ONLY_VARIABLES, (),
            )
        return errors
