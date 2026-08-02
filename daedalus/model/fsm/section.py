from __future__ import annotations

from dataclasses import dataclass, field

# render_markdown은 마이그레이션 전용 헬퍼 — 패키지 스타 재수출에서 제외
# (직접 경로 import는 가능: from daedalus.model.fsm.section import render_markdown)
__all__ = ["Section", "EventDef"]


@dataclass(eq=False)
class Section:
    """자유 콘텐츠 섹션 (H1–H6 계층)."""
    title: str
    content: str = ""
    children: list[Section] = field(default_factory=list)


@dataclass
class EventDef:
    """TransferOn 출력 이벤트 정의."""
    name: str
    color: str = "#4488ff"   # 노드 출력 포트 색상 (CSS hex)
    description: str = ""


def render_markdown(sections: list[Section], depth: int = 1) -> str:
    """섹션 트리를 단일 마크다운 문자열로 평탄화한다 (WP-SB 구버전 마이그레이션용).

    구 컴파일러(``compiler/emit.py``)의 ``_render_sections`` 블록 생성 로직을
    그대로 이관한 것 — 빈 content 처리·헤딩 깊이·블록 join 규약(빈 줄 하나로
    구분)까지 동일해야 동일성 게이트(구버전 파일 컴파일 산출 = 신규 파이프라인
    산출)를 통과한다. depth=1 → H1(#).
    """
    blocks: list[str] = []
    for sec in sections:
        hashes = "#" * min(depth, 6)
        blocks.append(f"{hashes} {sec.title}".rstrip())
        content = (sec.content or "").strip("\n")
        if content.strip():
            blocks.append(content)
        if sec.children:
            blocks.append(render_markdown(sec.children, depth + 1))
    return "\n\n".join(blocks)
