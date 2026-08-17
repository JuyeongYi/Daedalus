# daedalus/compiler/
"""순수 모델 → 플러그인 파일 컴파일러 (Qt 무관).

컴파일러 패턴의 종착점: model/ 의 순수 객체를 CC 플러그인 규약의
SKILL.md / agent .md 텍스트로 변환하고 파일로 쓴다.

공개 API:
    compile_project(project, out_dir) -> CompileResult   # 게이트 + 파일 쓰기
    compile_skill(skill, *, project=None) -> str               # SKILL.md 텍스트
    compile_agent(agent, project=None) -> str                  # agent .md 텍스트
    compile_hooks_json(project) -> str | None                  # hooks/hooks.json 텍스트
"""
from __future__ import annotations

from daedalus.compiler.emit import compile_agent, compile_hooks_json, compile_skill
from daedalus.compiler.project_compiler import (
    CompileResult,
    compile_project,
)

__all__ = [
    "CompileResult",
    "compile_project",
    "compile_skill",
    "compile_agent",
    "compile_hooks_json",
]
