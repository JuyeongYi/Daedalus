# daedalus/compiler/token_report.py
"""토큰 비용 리포트 (A5-lite) — 산출 텍스트의 컨텍스트 비용 계기판.

**목적:** 컴파일러가 만드는 자동 단락(작업 재개·진입 맥락·블랙보드 지시 …)은
**모든 스킬에 반복해서** 실리고, 그 토큰은 곧 사용료다(A12 산출 영어화의 논리).
얼마나 실리고 있는지 숫자로 보이지 않으면 점진 공개(A5)의 착수 근거도 없다.

**성격:** 리포트는 **결과 객체와 UI 표시 전용**이다 — 산출 파일 텍스트는 이
모듈의 존재 여부와 무관하게 바이트 단위로 불변이고, 임계 초과 고지도 검증
규칙이 아니다(`WARNING_RULES`에 등록하지 않는다. `ValidationError`도 만들지
않는다 — 컴파일을 막지도, 검증 패널을 채우지도 않는 **정보성 한 줄**이다).

**추정은 휴리스틱이다.** 외부 토크나이저 의존성을 추가하지 않는다(설치 환경마다
결과가 달라지고, 정밀도가 이 계기판의 목적에 필요하지도 않다). 두 구간으로
나눈 문자수 근사를 쓴다:

  - ASCII 4자 ≈ 1토큰 — 영어 산문의 통상 비율.
  - 비ASCII 1.5자 ≈ 1토큰 — 한글·CJK·이모지는 BPE에서 훨씬 조밀하게 쪼개진다.
    산출의 자동 단락은 영어지만 사용자 값(body/description)은 한국어일 수 있어,
    한 구간으로 뭉뚱그리면 그 부분을 3배 가까이 과소평가한다.

오차 ±20% 수준의 자릿수 감각용이다 — "이 스킬이 2천인가 2만인가"를 가리는 데는
충분하고, 그 이상의 정밀도가 필요한 판단은 이 리포트로 하지 않는다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

# 스킬 하나(SKILL.md)의 산출 텍스트 임계 — 넘으면 정보성 고지 1줄.
#
# 근거: SKILL.md는 그 스킬이 걸릴 때마다 **통째로** 컨텍스트에 들어가고, 배치된
# 스킬은 자동 단락(재개·진입 맥락·다음 단계·블랙보드)을 항상 함께 싣는다.
# Anthropic의 스킬 저작 지침이 SKILL.md를 500줄 안쪽으로 유지하라고 권고하는데,
# 마크다운 산문 500줄 ≈ 20,000자 ≈ 5,000토큰이다. 즉 이 값은 새 규범을 만드는
# 것이 아니라 이미 있는 권고를 토큰으로 환산한 것이다. 넘었다고 틀린 것은
# 아니므로 등급은 정보성이고, 대응책(점진 공개 — 본문 일부를 스킬 디렉토리
# 보조 파일로 내리기)을 문구에 함께 적는다.
DEFAULT_FILE_TOKEN_THRESHOLD = 5000

_ASCII_CHARS_PER_TOKEN = 4.0
_WIDE_CHARS_PER_TOKEN = 1.5


class TokenKind(StrEnum):
    """항목 1건이 토큰 계기판에서 **어떻게 세어지는가** (WP-5).

    종전에는 이 판정이 `CONTEXT_KINDS`라는 kind 문자열 집합이었다 — 계획
    kind의 사본을 토큰 리포트가 따로 들고 있었고, 개명하면 리포트만 조용히
    산출을 못 알아봤다(임계 대상에서 빠지고 고지 줄이 사라진다). 이제 판정은
    산출 계획이 선언하고(`PlannedOutput.token_kind`) 리포트는 그 선언을
    읽기만 한다 — 리포트는 kind 문자열을 **비교하지 않는다**.

    CONTEXT — 모델 컨텍스트에 산문으로 실린다. 파일당 임계 판정 대상.
    TOTAL_ONLY — CC가 설정으로 읽을 뿐 대화 컨텍스트에 실리지 않는다
        (hooks.json/schemas.json/plugin.json). 총합에는 넣되 임계로 재지 않는다.
    NONE — 계상하지 않는다(복사 산출 등).
    """
    CONTEXT = "context"
    TOTAL_ONLY = "total"
    NONE = "none"


def estimate_tokens(text: str) -> int:
    """문자수 기반 토큰 추정 (외부 토크나이저 의존 없음).

    ASCII 4자 ≈ 1토큰, 비ASCII 1.5자 ≈ 1토큰으로 근사한 뒤 올림한다.
    빈 문자열은 0.
    """
    if not text:
        return 0
    wide = sum(1 for ch in text if not ch.isascii())
    narrow = len(text) - wide
    return math.ceil(narrow / _ASCII_CHARS_PER_TOKEN + wide / _WIDE_CHARS_PER_TOKEN)


@dataclass(frozen=True)
class TokenEstimate:
    """산출 파일 1건의 추정치.

    path: out_dir 기준 POSIX 상대 경로 (미리보기 등 파일이 없는 경로에서는
        컴포넌트 이름 등 사람이 읽을 표지여도 된다).
    kind: 산출 계획의 kind ("skill" | "agent" | "hooks_json" | …).
    """
    path: str
    kind: str
    chars: int
    tokens: int
    #: 계상 방식 — 산출 계획이 선언한다(`PlannedOutput.token_kind`).
    token_kind: TokenKind = TokenKind.NONE
    #: 공통 안내 파일인가 — notice()의 "추가로 실린다" 줄 대상.
    is_guide: bool = False

    # 임계 판정은 **리포트가 한다**(`TokenReport.over_threshold`) — 항목이
    # 스스로 판정하면 모듈 상수를 보게 되어 리포트의 `threshold` 필드와
    # 진실이 둘이 된다. 항목 단위 판정 property는 그래서 두지 않는다.


@dataclass
class TokenReport:
    """컴파일 1회의 토큰 비용 리포트."""
    entries: list[TokenEstimate] = field(default_factory=list)
    threshold: int = DEFAULT_FILE_TOKEN_THRESHOLD

    def add(
        self, path: str, kind: str, text: str, *,
        token_kind: TokenKind, is_guide: bool = False,
    ) -> TokenEstimate:
        """항목 1건을 계상한다.

        `token_kind`는 **호출자가 명시한다**(기본값 없음) — 쓰기 루프는 계획
        행의 선언(`PlannedOutput.token_kind`)을, 미리보기는 컨텍스트 산출임을
        스스로 안다. 기본값을 두면 새 호출자가 조용히 틀린 구간에 들어간다.
        """
        entry = TokenEstimate(
            path=path, kind=kind, chars=len(text or ""),
            tokens=estimate_tokens(text or ""),
            token_kind=token_kind, is_guide=is_guide,
        )
        self.entries.append(entry)
        return entry

    @property
    def total_tokens(self) -> int:
        return sum(e.tokens for e in self.entries)

    @property
    def total_chars(self) -> int:
        return sum(e.chars for e in self.entries)

    def over_threshold(self) -> list[TokenEstimate]:
        """임계를 넘은 컨텍스트 산출물 — 토큰 내림차순."""
        hits = [
            e for e in self.entries
            if e.token_kind is TokenKind.CONTEXT and e.tokens > self.threshold
        ]
        return sorted(hits, key=lambda e: (-e.tokens, e.path))

    def notice(self) -> str | None:
        """정보성 고지 — 임계 초과 문단 + 공통 안내 파일 한 줄. 없으면 None.

        가이드 줄은 **임계 초과와 무관하게** 나온다. 가이드는 실측 ~1,800토큰이라
        임계(5,000)를 넘을 일이 없는데, 초과 문단에 붙여만 두면 정상적인
        프로젝트에서는 영영 보이지 않는다 — 그러면 "포인터를 받은 컴포넌트마다
        추가로 실린다"는 사실을 말하는 자리가 산출 어디에도 없다.

        다만 이 문자열이 곧 모달 조건은 아니다 — 매 컴파일마다 창이 뜨면
        계기판이 아니라 방해다. GUI(`view/compile_actions.show_token_notice`)는
        `over_threshold()`로 띄울지 정하고, 이 문자열은 그때의 본문과 MCP 응답
        (`compile_preview`의 `token_notice`)에 실린다.
        """
        parts: list[str] = []
        hits = self.over_threshold()
        if hits:
            head = ", ".join(f"{e.path} ≈{e.tokens:,}" for e in hits[:3])
            more = f" 외 {len(hits) - 3}건" if len(hits) > 3 else ""
            parts.append(
                f"토큰 비용: 산출 {len(hits)}건이 파일당 임계 {self.threshold:,}토큰을 "
                f"넘습니다 ({head}{more}). 스킬 본문은 걸릴 때마다 통째로 컨텍스트에 "
                f"실립니다 — 큰 절을 skill-files/로 내려 필요할 때만 읽게 하는 것을 "
                f"검토하세요."
            )
        guides = sum(e.tokens for e in self.entries if e.is_guide)
        if guides:
            parts.append(
                f"공통 안내 파일 ≈{guides:,}토큰은 포인터를 받은 컴포넌트가 "
                f"실행될 때마다 추가로 실립니다."
            )
        return "\n".join(parts) or None

    def summary(self) -> str:
        """상태바 한 조각용 요약."""
        return f"≈{self.total_tokens:,}토큰"

    # 직렬화(`to_dict`)는 두지 않는다 — 소비자가 실제로 생기기 전에 만든 응답
    # 형상은 아무도 쓰지 않은 채 낡는다(MCP `compile_preview`는 파일 1건의
    # 수치만 직접 싣는다). 리포트 전체를 응답에 실을 도구가 생기면 그 호출
    # 지점에서 필요한 모양대로 만든다.
