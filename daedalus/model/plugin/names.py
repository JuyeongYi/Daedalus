# daedalus/model/plugin/names.py
"""컴포넌트 **이름 짓기** — 임의 문자열 → 이름 규약, 충돌 회피 (WP-C).

외부 정본(`플러그인[@마켓]:이름`)을 컴포넌트로 들여올 때 "무슨 이름으로
태어나는가"를 답하는 자리다. 같은 질문을 두 경로가 묻는다: 구버전 파일
마이그레이션(`serialize/migrate.migrate_external_fork_agents`)과 레지스트리
🔌 탭/MCP의 외부 에이전트 등록(`view/actions/external_registration`). 각자
정규화하면 **같은 외부 에이전트가 경로에 따라 다른 이름으로** 태어난다(원칙 1).

이름 규약은 `^[a-z0-9][a-z0-9-]*$`다(검증 `invalid_component_name`) — 규약을
어긴 이름을 **만들어 주면서** 경고를 새로 내는 일은 없어야 한다.
"""
from __future__ import annotations

import re

_NOT_NAME_CHARS = re.compile(r"[^a-z0-9-]+")
_DASH_RUN = re.compile(r"-{2,}")


def component_name_slug(text: str) -> str:
    """임의 문자열을 컴포넌트 이름 규약(`^[a-z0-9][a-z0-9-]*$`)에 맞춘다.

    소문자화 + 규약 밖 문자(콜론·밑줄·공백·대문자 …)를 `-`로, 연속 `-`는 하나로,
    앞뒤 `-`는 제거. `hookify:Hook_Doctor` → `hook-doctor`.
    """
    slug = _NOT_NAME_CHARS.sub("-", text.lower())
    return _DASH_RUN.sub("-", slug).strip("-")


def free_component_name(taken: set[str], *candidates: str) -> str:
    """이미 쓰이는 이름을 피해 후보 중 첫 자유 이름을 고른다(최후에는 접미 숫자).

    이름이 겹치면 `duplicate_component_name` 에러가 되어 생성이 문제를 **새로**
    만든다 — 그래서 여기서 피한다. 후보 순서가 곧 선호 순서다.
    """
    for candidate in candidates:
        if candidate and candidate not in taken:
            return candidate
    stem = next((c for c in candidates if c), "external-component")
    index = 2
    while f"{stem}-{index}" in taken:
        index += 1
    return f"{stem}-{index}"


def external_ref_name_candidates(source: str) -> tuple[str, ...]:
    """외부 정본 참조 → 선호 순 이름 후보 (`<이름>`, `<플러그인>-<이름>`).

    참조 이름을 그대로 쓰는 것이 1순위이고, 그것이 이미 쓰이면 플러그인 이름을
    앞에 붙여 구분한다(`hookify:doctor` → `doctor` → `hookify-doctor`).
    마켓 표기(`@마켓`)는 이름에 넣지 않는다 — 사람이 부르는 이름이다.
    """
    plugin_id, sep, ref_name = source.partition(":")
    if not sep:
        return (component_name_slug(source),)
    bare_plugin = plugin_id.partition("@")[0].strip()
    ref_name = ref_name.strip()
    return (
        component_name_slug(ref_name),
        component_name_slug(f"{bare_plugin}-{ref_name}"),
    )
