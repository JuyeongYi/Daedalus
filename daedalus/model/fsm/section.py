from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
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
