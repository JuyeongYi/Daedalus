# daedalus/model/validation/project_rules/text.py
"""본문 문자열을 훑는 규칙들이 공유하는 마크다운 전처리 (이동만 — 동작 불변).

``_strip_markdown_code``는 파사드(``project_rules``)와 패키지 파사드
(``daedalus.model.validation``)에서 그대로 재-export된다.
"""
from __future__ import annotations

import re

_CODE_FENCE_RE = re.compile(r"```.*?(?:```|\Z)", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def _strip_markdown_code(text: str) -> str:
    """마크다운 본문에서 코드로 표시된 부분을 지운다.

    본문을 문자열로 훑는 규칙이 **문서가 무언가를 설명하려고 인용한 것**까지
    실사용으로 오인하지 않게 한다. 코드 펜스를 먼저 지우는 순서가 중요하다 —
    펜스 안의 백틱이 인라인 코드로 잘못 짝지어지는 것을 막는다.
    """
    return _INLINE_CODE_RE.sub("", _CODE_FENCE_RE.sub("", text))
