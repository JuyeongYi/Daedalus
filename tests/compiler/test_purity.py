# tests/compiler/test_purity.py
"""compiler 패키지가 PyQt6 없이 import·동작 가능해야 한다."""
from __future__ import annotations

import subprocess
import sys


def test_compiler_is_pyqt_free():
    code = (
        "import builtins\n"
        "_real = builtins.__import__\n"
        "def _blocked(name, *a, **k):\n"
        "    if name == 'PyQt6' or name.startswith('PyQt6.'):\n"
        "        raise ImportError('PyQt6 import blocked for purity test')\n"
        "    return _real(name, *a, **k)\n"
        "builtins.__import__ = _blocked\n"
        "from daedalus.compiler import compile_project, compile_skill, compile_agent\n"
        "from daedalus.model.fsm.machine import StateMachine\n"
        "from daedalus.model.fsm.state import SimpleState\n"
        "from daedalus.model.plugin.skill import ProceduralSkill\n"
        "s = SimpleState(name='s')\n"
        "sm = StateMachine(name='m', initial_state=s, states=[s], final_states=[s])\n"
        "sk = ProceduralSkill(fsm=sm, name='x', description='d')\n"
        "out = compile_skill(sk)\n"
        "assert out.startswith('---')\n"
        "print('OK')\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, (
        f"PyQt6 차단 하에 compiler import 실패:\n"
        f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    assert "OK" in result.stdout
