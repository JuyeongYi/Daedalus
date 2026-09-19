# tests/model/plugin/test_registry_discovery.py
"""레지스트리 등록 누락 감시 — pkgutil 발견 (REFACTOR_SPEC §8, WP-3).

`COMPONENT_CLASSES`는 손으로 쓰는 튜플이다(`__init_subclass__` 자동 등록을
기각한 이유는 `kinds.py` docstring에 있다). 손으로 쓰는 표의 유일한 위험은
**빠뜨림**이고, 빠뜨리면 그 종류는 예외 없이 사라진다 — 팔레트에 안 보이고,
MCP가 "알 수 없는 종류"로 거절하고, 저장 파일에서 읽히지 않는다(👻).

그래서 `daedalus.model.plugin` 패키지를 통째로 임포트해 `Skill`/`Agent`의 **구체**
서브클래스를 전부 찾아내고, 그 집합이 등록 튜플과 같은지 본다. 새 종류 파일을
만들고 튜플에 올리는 것을 잊으면 여기서 이름을 찍고 실패한다.

뿌리를 `PluginComponent`가 아니라 두 버킷 기저로 잡는 이유: `PluginComponent`는
스킬·에이전트보다 **넓다**. `Tool`·`HookDef`도 거기서 name/description/kind를
물려받지만 종류 행(`KIND`/`BUCKET`)을 선언하지 않는다 — 레지스트리의 대상이
아니고, 그 사실 자체를 아래 테스트가 못 박는다.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest

import daedalus.model.plugin as plugin_pkg
from daedalus.model.plugin.agent import Agent
from daedalus.model.plugin.config import ComponentConfig
from daedalus.model.plugin.hook import HookDef
from daedalus.model.plugin.kinds import COMPONENT_CLASSES, KIND_REGISTRY, spec_for
from daedalus.model.plugin.skill import Skill
from daedalus.model.plugin.tool import Tool


def _import_every_plugin_module() -> None:
    """plugin 패키지의 모든 모듈을 임포트한다 — 미임포트 모듈의 클래스는 안 보인다."""
    for info in pkgutil.walk_packages(
        plugin_pkg.__path__, prefix=plugin_pkg.__name__ + "."
    ):
        importlib.import_module(info.name)


def _concrete_subclasses(base: type) -> set[type]:
    found: set[type] = set()
    stack = [base]
    while stack:
        for sub in stack.pop().__subclasses__():
            if sub in found:
                continue
            found.add(sub)
            stack.append(sub)
    return {c for c in found if not inspect.isabstract(c)}


def test_every_concrete_component_class_is_registered():
    """구체 스킬·에이전트 클래스 집합 == `COMPONENT_CLASSES`."""
    _import_every_plugin_module()
    discovered = _concrete_subclasses(Skill) | _concrete_subclasses(Agent)
    assert discovered == set(COMPONENT_CLASSES), (
        "등록 누락/과잉: "
        f"{sorted(c.__name__ for c in discovered ^ set(COMPONENT_CLASSES))}"
    )


def test_every_registered_config_class_is_concrete_and_used_once():
    """등록된 config 클래스는 전부 구체이고 **한 종류만** 쓴다."""
    _import_every_plugin_module()
    config_classes = [s.config_cls for s in KIND_REGISTRY.values()]
    assert len(set(config_classes)) == len(config_classes)
    for cfg in config_classes:
        assert issubclass(cfg, ComponentConfig)
        assert not inspect.isabstract(cfg), cfg.__name__


def test_discovery_actually_walks_the_package():
    """스캐너가 조용히 0을 세지 않는지 — 패키지에는 모듈이 여럿 있다."""
    modules = list(
        pkgutil.walk_packages(plugin_pkg.__path__, prefix=plugin_pkg.__name__ + ".")
    )
    assert len(modules) >= 10
    assert any(m.name.endswith(".kinds") for m in modules)


def test_tools_and_hooks_are_not_kind_registry_subjects():
    """`PluginComponent`를 공유하는 이웃(도구·훅)은 종류 행의 대상이 **아니다**.

    상속만으로 레지스트리 대상을 가리면 `Tool`이 스킬 팔레트에 나타나거나
    `bucket_of`가 도구를 `project.skills`에 밀어 넣는다. 거절은 조용하지 않게
    `TypeError`다(원칙 5).
    """
    _import_every_plugin_module()
    for cls in _concrete_subclasses(Tool) | {HookDef}:
        assert not hasattr(cls, "KIND"), cls.__name__
    with pytest.raises(TypeError, match="스킬·에이전트"):
        spec_for(HookDef(name="h", description=""))
