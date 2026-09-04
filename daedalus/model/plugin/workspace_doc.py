# daedalus/model/plugin/workspace_doc.py
"""작업 폴더 문서 — `.claude/CLAUDE.md`와 `.claude/rules/*.md` (WP-WD).

**편집만 제공한다**(사용자 확정 D7). 생성 로직도, 자동 합성도 없다 — 사람이 ddls
프로젝트에서 쓴 마크다운이 LOCAL 빌드 때 작업 폴더로 나갈 뿐이다.

배치는 `PluginProject`가 두 필드로 나눠 갖는다:

- `claude_md: WorkspaceDoc | None` — `.claude/CLAUDE.md`의 이 플러그인 **구역**.
  최대 하나라는 불변식을 검증 규칙이 아니라 **구조로** 지킨다.
- `rules: list[WorkspaceDoc]` — `.claude/rules/<name>.md`. 파일 하나가 문서 하나라
  이름이 곧 파일명이고, 그래서 컴포넌트와 같은 이름 규약을 받는다.

`name`의 뜻이 둘 사이에서 다르다는 점만 주의한다 — 규칙에서는 **파일명**이고,
CLAUDE.md에서는 구역 안 맨 앞에 놓이는 **H1 제목**이다(D9).

`paths:` 프론트매터를 필드로 두지 않는 이유: body가 그대로 나가므로 필요한 사람은
본문 맨 위에 직접 쓰면 된다. 모델에 필드를 하나 더 만들면 "편집만"이라는 범위가
슬금슬금 넓어진다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class WorkspaceDoc:
    """작업 폴더로 나가는 마크다운 문서 하나.

    값 동등성(기본 dataclass)이고 `id`는 비교에서 빠진다 — Skill/AgentDefinition과
    같은 관례다. `id`가 필요한 이유는 본문 undo 스택(`BodyDocumentRegistry`)이
    편집 중인 문서를 이름이 아니라 안정 식별자로 잡아야 하기 때문이다. 이름으로
    잡으면 이름을 바꾸는 순간 편집 이력이 끊긴다.
    """

    name: str
    body: str = ""
    id: str = field(default_factory=lambda: uuid4().hex, compare=False, kw_only=True)

    def has_content(self) -> bool:
        """배출할 내용이 있는가 — 공백뿐이면 없는 것으로 본다."""
        return bool(self.body.strip())
