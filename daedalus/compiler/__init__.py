# daedalus/compiler/
"""순수 모델 → 플러그인 파일 컴파일러 (PyQt 무관).

컴파일러 패턴의 종착점: model/ 의 순수 객체를 CC 플러그인 규약의
SKILL.md / agent .md 텍스트로 변환한다.

공개 API:
    compile_skill(skill, *, local=False, project=None) -> str  # SKILL.md 텍스트
    compile_agent(agent, project=None) -> str                  # agent .md 텍스트
"""
from __future__ import annotations

from daedalus.compiler.emit import compile_agent, compile_skill

__all__ = [
    "compile_skill",
    "compile_agent",
]
