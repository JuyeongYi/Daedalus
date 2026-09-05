# daedalus/model/plugin/variables.py
"""본문 경로 변수 (WP-RT) — 순수 모델 (Qt 무관, stdlib만).

**왜 중립 토큰인가.** CC의 경로 변수는 빌드 타깃마다 다르다:
`${CLAUDE_PLUGIN_ROOT}`는 플러그인 스킬에서만 치환되고, 프로젝트 설치(.claude/
반입) 빌드에서는 리터럴로 남는다. 반대로 `${CLAUDE_PROJECT_DIR}`은 어디서나
치환된다.

이전에는 본문 정본을 마켓플레이스 형태(`${CLAUDE_PLUGIN_ROOT}/files/`)로 저장하고
프로젝트 설치 빌드에서만 치환했다. 그러면 정본이 한쪽 타깃에 편향되고, **보이는
것과 나가는 것이 달라진다** — 사용자는 본문에서 `${CLAUDE_PLUGIN_ROOT}`를 보는데
실제 산출은 다른 변수를 쓴다. 검증도 "files/ 참조만 예외"라는 특례를 안게 된다.

그래서 정본은 타깃 중립 토큰 `${ROOT}` 하나를 쓰고, 컴파일 시점에 타깃에 맞는 CC
변수로 확장한다. 정본은 어느 타깃에도 기울지 않고, 타깃을 바꾸면 산출만 따라간다.
"""
from __future__ import annotations

from daedalus.model.plugin.enums import BuildTarget

ROOT_TOKEN = "${ROOT}"
"""본문에 쓰는 타깃 중립 루트 토큰. 컴파일 시 타깃별 CC 변수로 확장된다."""

FILES_PREFIX = f"{ROOT_TOKEN}/files/"
"""동봉 파일 참조 접두. 파일 드롭이 이 형태로 토큰을 넣는다."""

# 타깃별 확장 결과.
#   MARKETPLACE — 플러그인 설치 디렉토리. files/는 플러그인 안에 복사된다.
#   LOCAL       — 프로젝트 루트. 컴파일이 곧 설치라(WP-MW) files/를 대상 작업
#                 폴더에 바로 복사하고, ${CLAUDE_PROJECT_DIR}은 플러그인 여부와
#                 무관하게 치환된다(v2.1.196+).
ROOT_EXPANSION: dict[BuildTarget, str] = {
    BuildTarget.MARKETPLACE: "${CLAUDE_PLUGIN_ROOT}",
    BuildTarget.LOCAL: "${CLAUDE_PROJECT_DIR}",
}

# CC가 **플러그인 스킬에서만 치환하는** 변수 (공식 skills 문서의 치환 표).
# 본문에 직접 쓰면 프로젝트 설치 빌드에서 리터럴로 남으므로 ${ROOT}를 쓰게 한다.
PLUGIN_ONLY_VARIABLES: tuple[str, ...] = (
    "${CLAUDE_PLUGIN_ROOT}",
    "${CLAUDE_PLUGIN_DATA}",
)

# CC가 **스킬 본문에서만 치환하는** 변수 (공식 skills 문서의 치환 표). 에이전트
# .md와 작업 폴더 문서(.claude/CLAUDE.md 구역·.claude/rules/)에 쓰면 치환되지 않고
# 리터럴 문자열로 산출에 나간다 — `skill_only_variable_in_body` 경고의 단일 진실이며,
# 변수 삽입 팝업의 컨텍스트 필터(view/editors/variable_loader의 `_SKILL_ONLY`)와
# 같은 매트릭스를 모델 쪽에서 표현한 것이다.
#
# - `$ARGUMENTS`는 `$ARGUMENTS[N]`(인덱스 접근)의 접두이기도 하므로 부분 문자열
#   검사 하나가 둘 다 잡는다.
# - `$N`(=`$ARGUMENTS[N]` 단축형)은 **의도적으로 제외한다** — `$1`/`$2`는 셸 위치
#   인수 표기와 구분할 수 없어, 본문이 인용한 셸 스니펫마다 고칠 수 없는 경고가 뜬다.
SKILL_ONLY_VARIABLES: tuple[str, ...] = (
    "$ARGUMENTS",
    "${CLAUDE_SESSION_ID}",
    "${CLAUDE_SKILL_DIR}",
)

# 구버전 본문(WP-RT 이전)의 files/ 참조 — 로드 시 ${ROOT}/files/로 변환한다.
_LEGACY_FILES_PREFIX = "${CLAUDE_PLUGIN_ROOT}/files/"


def expand_root(text: str, build_target: BuildTarget) -> str:
    """산출 텍스트의 ``${ROOT}``를 빌드 타깃에 맞는 CC 변수로 확장한다.

    컴파일 시점에만 쓴다 — 저장 정본은 항상 ``${ROOT}`` 형태다.
    """
    replacement = ROOT_EXPANSION.get(build_target, ROOT_EXPANSION[BuildTarget.MARKETPLACE])
    return text.replace(ROOT_TOKEN, replacement)


def migrate_legacy_file_refs(text: str) -> str:
    """구버전 본문의 ``${CLAUDE_PLUGIN_ROOT}/files/`` → ``${ROOT}/files/``.

    로드(역직렬화) 시점의 단방향 마이그레이션이다. **files/ 참조만** 바꾼다 —
    그 외 용도의 `${CLAUDE_PLUGIN_ROOT}`는 사용자가 의도해서 쓴 것일 수 있고,
    무엇을 의도했는지 알 수 없으므로 건드리지 않고 검증 경고에 맡긴다.
    """
    return text.replace(_LEGACY_FILES_PREFIX, FILES_PREFIX)


def file_ref_token(posix_relpath: str) -> str:
    """동봉 파일 상대경로 → 본문에 넣을 참조 토큰."""
    return f"{FILES_PREFIX}{posix_relpath}"
