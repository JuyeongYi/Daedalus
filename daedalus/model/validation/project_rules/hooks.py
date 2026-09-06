# daedalus/model/validation/project_rules/hooks.py
"""훅(hook_library) 규칙 + 참조 수집 헬퍼 (이동만 — 동작 불변)."""
from __future__ import annotations

from daedalus.model.validation.severity import ValidationError


class _HookRules:
    """훅(hook_library) 규칙 모음 (_ProjectRules 믹스인)."""

    @staticmethod
    def _collect_hook_refs(project):
        """config.hooks 키(훅 이름 참조)를 (label, name, subject)로 yield.

        스킬/에이전트의 config.hooks를 모두 훑는다.
        """
        for skill in getattr(project, "skills", []):
            cfg = getattr(skill, "config", None)
            hooks = getattr(cfg, "hooks", None)
            if isinstance(hooks, dict):
                for name in hooks:
                    yield (f"skill:{skill.name}", name, skill)
        for agent in getattr(project, "agents", []):
            cfg = getattr(agent, "config", None)
            hooks = getattr(cfg, "hooks", None)
            if isinstance(hooks, dict):
                for name in hooks:
                    yield (f"agent:{agent.name}", name, agent)

    @staticmethod
    def _check_duplicate_hook_name(project) -> list[ValidationError]:
        """duplicate_hook_name — hook_library 내 동명 HookDef 에러."""
        seen: dict[str, object] = {}
        errors: list[ValidationError] = []
        for hook in getattr(project, "hook_library", []):
            if hook.name in seen:
                errors.append(ValidationError(
                    rule="duplicate_hook_name",
                    message=(
                        f"hook_library에 훅 이름 '{hook.name}'이 중복됩니다. "
                        f"이름 참조가 모호해집니다."
                    ),
                    source=hook.name,
                    subject=hook,
                ))
            else:
                seen[hook.name] = hook
        return errors

    @staticmethod
    def _check_empty_hook_command(project) -> list[ValidationError]:
        """empty_hook_command — 훅에 핸들러가 없거나, 핸들러의 필수 값이 비면 경고.

        WP-HK로 훅이 핸들러 목록을 갖게 되면서 "빈 값" 판정이 타입마다 달라졌다
        (command 훅은 command, http 훅은 url, …). 각 핸들러가 무엇이 필수인지
        아는 유일한 곳은 자기 자신이므로 `summary()`가 비었는지로 판정한다 —
        핸들러 타입이 늘어도 이 규칙은 그대로 따라간다.
        """
        errors: list[ValidationError] = []
        for hook in getattr(project, "hook_library", []):
            if not hook.handlers:
                errors.append(ValidationError(
                    rule="empty_hook_command",
                    message=f"훅 '{hook.name}'에 핸들러가 없습니다 — 아무 일도 하지 않습니다.",
                    source=hook.name,
                    subject=hook,
                ))
                continue
            for handler in hook.handlers:
                if handler.summary().startswith("("):  # "(커맨드 없음)" 등
                    errors.append(ValidationError(
                        rule="empty_hook_command",
                        message=(
                            f"훅 '{hook.name}'의 {handler.kind} 핸들러에 "
                            f"필수 값이 비어 있습니다."
                        ),
                        source=hook.name,
                        subject=hook,
                    ))
        return errors

    @staticmethod
    def _check_hook_matcher_event(project) -> list[ValidationError]:
        """hook_matcher_without_tool_event — matcher를 받지 않는 이벤트에 matcher가
        있으면 경고.

        규칙 이름은 예전(도구 이벤트 전용이라고 보던 시절) 그대로 두지만, 판정은
        스키마 기준이다 — CC 이벤트 대부분이 matcher를 받고, 받지 않는 것은
        `NO_MATCHER_EVENTS`에 모아 두었다.
        """
        from daedalus.model.plugin.hook import (
            MATCHER_EVENTS,
            mcp_matcher_matches_nothing,
        )
        errors: list[ValidationError] = []
        for hook in getattr(project, "hook_library", []):
            if not hook.matcher.strip():
                continue
            if hook.event not in MATCHER_EVENTS:
                errors.append(ValidationError(
                    rule="hook_matcher_without_tool_event",
                    message=(
                        f"훅 '{hook.name}'의 matcher '{hook.matcher}'는 "
                        f"event '{hook.event.value}'에서 무시됩니다 — "
                        f"이 이벤트는 matcher를 받지 않습니다."
                    ),
                    source=hook.name,
                    subject=hook,
                ))
            elif mcp_matcher_matches_nothing(hook.matcher):
                errors.append(ValidationError(
                    rule="hook_matcher_matches_nothing",
                    message=(
                        f"훅 '{hook.name}'의 matcher '{hook.matcher}'는 어떤 MCP "
                        f"도구와도 맞지 않습니다 — 서버 이름까지만 쓰면 정규식이 "
                        f"아니라 정확한 문자열로 비교됩니다. 서버 전체를 잡으려면 "
                        f"'{hook.matcher.strip()}__.*'처럼 도구 부분을 붙이세요."
                    ),
                    source=hook.name,
                    subject=hook,
                ))
        return errors

    # (`orphan_hook`은 퇴역했다 — 전제가 틀렸다. 플러그인 훅은 **전역**이라
    #  플러그인이 활성화되면 자동으로 동작하고, 컴포넌트가 `config.hooks`로
    #  참조해야 켜지는 것이 아니다(공식 plugins-reference 확인 2026-09-07).
    #  이제 프로젝트 훅 라이브러리는 참조 여부와 무관하게 배출되므로
    #  "부착하지 않으면 산출에 실리지 않는다"는 안내 자체가 거짓이었다.
    #  전역 훅을 이 프로젝트로 끌어오는 참조 역할은 `config.hooks`에 남아
    #  있고, 없는 이름을 가리키는 것은 `dangling_hook_ref`가 계속 짚는다.)

    @staticmethod
    def _check_dangling_hook_refs(
        project, known_hook_names: frozenset[str] | None = None
    ) -> list[ValidationError]:
        """dangling_hook_ref — config.hooks 키가 알려진 훅 이름에 없으면 경고.

        known_hook_names가 주어지면 그것이 유효 집합이다(전역 훅 포함, A1).
        생략하면 `project.hook_library`만 — validate_project docstring 참조.
        """
        lib_names = (
            set(known_hook_names)
            if known_hook_names is not None
            else {h.name for h in getattr(project, "hook_library", [])}
        )
        errors: list[ValidationError] = []
        for label, name, subject in _HookRules._collect_hook_refs(project):
            if name not in lib_names:
                errors.append(ValidationError(
                    rule="dangling_hook_ref",
                    message=(
                        f"{label}: config.hooks가 참조하는 훅 '{name}'이 "
                        f"훅 라이브러리(프로젝트·전역)에 없습니다."
                    ),
                    source=name,
                    subject=subject,
                    path=(label,),
                ))
        return errors
