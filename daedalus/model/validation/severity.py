# daedalus/model/validation/severity.py
"""검증 결과 1건(ValidationError)과 등급(WARNING_RULES) — 규칙 검사와 무관한 값 계층.

WP-RF-3d: 구 단일 모듈 ``model/validation.py``에서 그대로 옮겨 왔다(이동만, 동작 불변).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidationError:
    """검증 결과 1건.

    subject: 문제의 모델 객체 (노드 점프용). compare=False이므로 UI에서는
      값 비교가 아니라 ``error.subject is node.model`` 같은 identity 비교로
      조회해야 한다.
    path: 중첩 위치. validate_project는 루트를 ``("skill:<이름>",)`` 또는
      ``("agent:<이름>",)``으로 주입하고, 재귀는 ``"agent:<이름>"``(CompositeState)
      / ``"region:<이름>"``(Region)을 누적한다.
    """
    rule: str
    message: str
    source: str = ""
    subject: object | None = field(default=None, compare=False, repr=False)
    path: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_warning(self) -> bool:
        """규칙이 경고 등급이면 True, 에러 등급이면 False.

        invalid_component_name은 빈 이름(에러)과 규약 불일치(경고)가 같은 rule 이름을
        공유한다 — 빈 이름 메시지는 "이름이 비어 있습니다"로 특정하여 에러로 분류.
        """
        if self.rule == "invalid_component_name":
            return "비어 있습니다" not in self.message
        return self.rule in WARNING_RULES


# 경고 등급 규칙 집합 (모델 단일 진실 — view에서 rule 이름 하드코딩 금지).
# invalid_component_name은 is_warning property에서 메시지 내용으로 세분화.
WARNING_RULES: frozenset[str] = frozenset({
    # 머신 수준 경고
    "missing_required_input",
    "pseudo_state_hooks",
    "completion_event_on_composite",
    "duplicate_state_name",
    "unreachable_state",
    "invalid_data_map_source",
    "trigger_unknown_event",
    # WP-M FSM 의미론 경고
    "choice_completeness_missing_else",
    "parallel_join_count",
    # 프로젝트 수준 경고
    "dangling_string_reference",
    "wrapped_source_missing",  # WP-WR
    "wrapped_usage_conflict",  # WP-WR — 용도 고정 ↔ 배치 어긋남
    "unused_external_plugin",  # WP-WR — 선언했는데 어떤 랩핑 스킬도 참조 안 함
    "undeclared_external_plugin",  # WP-WR — 랩핑 소스가 미선언 플러그인을 가리킴
    "external_plugin_no_marketplace",  # WP-WR — 컴파일러 emit (bare 선언은 enabledPlugins 불가)
    "invalid_component_name",  # 빈 이름 제외는 is_warning에서 처리
    # 도구(tool_shelf) 경고
    "dangling_tool_ref",
    "empty_tool_definition",
    # 훅(hook_library) 경고
    "dangling_hook_ref",
    "empty_hook_command",
    "hook_matcher_without_tool_event",
    "hook_matcher_matches_nothing",
    # A6 — 훅을 만들고 부착을 잊으면 아무 일도 일어나지 않는다(프로젝트 훅만).
    # 블랙보드(blackboard) 경고 — WP-BB
    "dangling_blackboard_ref",
    "orphan_blackboard_field",
    "invalid_blackboard_field_type",
    # 파일 참조(files/) 경고 — WP-FR. 검사 로직은 Validator가 아니라
    # compiler/project_compiler.py 소관(검증기는 파일시스템 무접근 순수성
    # 유지)이지만, is_warning 판정 일관성을 위해 여기 등록한다.
    "dangling_file_ref",
    # WP-WD — 작업 폴더 문서(.claude/CLAUDE.md·.claude/rules/). 이름 규약은
    # 컴포넌트와 같은 관례로 편집 중에는 경고이고 컴파일 게이트가 에러로 승격한다.
    # duplicate_rule_name은 서로 덮어쓰므로 에러 등급(여기 등재하지 않는다).
    "invalid_rule_name",
    "workspace_doc_in_marketplace_build",
    "workspace_settings_in_marketplace_build",  # WP-WS
    # 빌드 타깃(build_target) 경고 — WP-TG
    "mcp_agent_in_marketplace_build",
    "plugin_root_in_local_build",
    # WP-LA — 플러그인 서브에이전트가 무시하는 프론트매터 필드
    "unsupported_agent_field_in_marketplace_build",
    # WP-MW — LOCAL 직접 설치 배선 경고. 검사·발급은 compiler/project_compiler.py
    # 소관(dangling_file_ref와 동일 정책 — 검증기는 파일시스템 무접근).
    "missing_mcp_server_def",
    "unmergeable_settings_json",
    # WP-WD — .claude/CLAUDE.md 구역 병합 실패(손상된 표식). 파일을 건드리지 않고
    # 경고만 낸다 — 구역의 끝을 추측하면 사용자 내용을 지운다. emit은 컴파일러 소관.
    "unmergeable_claude_md",
    # A13 — 규칙의 paths 필드와 본문 수기 프론트매터가 겹쳐 `---` 블록이 둘 나간다.
    # 본문은 건드리지 않고 경고만 낸다(자동 병합 금지). emit은 컴파일러 소관.
    "rule_body_frontmatter",
    # WP-SF — 스킬별 동봉 파일(skill-files/) 경고. dangling/unknown 2종은
    # compiler/project_compiler.py 소관(파일시스템 검사), 에이전트 토큰 검사는
    # 본문 문자열만 보므로 검증기 소관.
    "dangling_skill_file_ref",
    "unknown_skill_files_dir",
    "skill_dir_token_in_agent",
    # A6 — 스킬 전용 변수($ARGUMENTS/${CLAUDE_SESSION_ID}/${CLAUDE_SKILL_DIR})가
    # 에이전트·작업 폴더 문서 본문에 있으면 치환되지 않고 리터럴로 나간다.
    # (에이전트의 ${CLAUDE_SKILL_DIR}는 skill_dir_token_in_agent 전담 — 중복 방지)
    "skill_only_variable_in_body",
    # A3 — user-invocable은 진입점으로 기능할 노드만 true여야 한다
    "mid_chain_user_invocable",
})
