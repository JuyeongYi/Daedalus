# daedalus/model/serialize/component_fields.py
"""컴포넌트 수준 **표 구동 직렬화 엔진** (REFACTOR_SPEC §2-d).

`_ser_skill`/`_ser_agent`/`_build_component`의 종류별 `isinstance` 사다리를
세 개의 표로 바꾼다:

- `KEY_ORDER[bucket]` — 저장 파일의 **키 순서**. 버킷마다 다르다(스킬은
  `body` 다음이 `config`, 에이전트는 `config` 다음이 `body`). 전역 순서 하나로는
  두 버킷의 바이트를 동시에 맞출 수 없다.
- `DESER_ORDER` — 역직렬화의 **부수효과 순서**. 키 순서와 별개다: `reg.warnings`가
  쌓이는 순서가 곧 사용자가 보는 경고 순서라, 이것이 바뀌면 동작 불변이 아니다.
- `COMPONENT_MISSING` — 키 **부재값**이 dataclass 기본값과 다른 필드.

"이 종류가 어떤 키를 갖는가"는 종류 목록이 아니라 `dataclasses.fields`가
답한다 — 새 종류를 더해도 이 파일은 바뀌지 않는다.

**이 모듈은 형제 모듈을 임포트하지 않는다.** FSM·EventDef·config 코덱을
호출자가 주입한다(`ser.py`는 `_ser_machine`을, `deser_plugin.py`는
`_deser_machine`을 준다). 직접 임포트하면 `ser → component_fields → ser` 순환이
생긴다 — `serialize` 패키지의 단방향 의존은 `test_serialize_facade
.test_dependency_direction_is_acyclic`이 강제한다.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from typing import Any

from daedalus.model.plugin.roles import Bucket

#: 스킬의 저장 키 순서. `when_to_use`가 있고 `body`가 `config` **앞**이다.
SKILL_KEY_ORDER: tuple[str, ...] = (
    "kind", "id", "name", "description", "when_to_use", "body",
    "config", "fsm", "transfer_on", "call_agents",
)

#: 에이전트의 저장 키 순서. `when_to_use`가 없고 `config`가 `body` **앞**이다.
#: (WP-1 D8, 2026-09-19 — execution_policy/reference_placements/graph_layout/
#: edge_layout 4키는 퇴역했다. 구버전 파일의 키는 `migrate._migrate_v1`이 떤다.)
AGENT_KEY_ORDER: tuple[str, ...] = (
    "kind", "id", "name", "description", "config", "body",
    "fsm", "transfer_on", "call_agents",
)

#: 버킷 → 키 순서. 두 튜플의 차이가 곧 "왜 전역 순서 하나로는 안 되는가"다.
KEY_ORDER: Mapping[Bucket, tuple[str, ...]] = {
    Bucket.SKILLS: SKILL_KEY_ORDER,
    Bucket.AGENTS: AGENT_KEY_ORDER,
}

#: **부재 의미론** — 키가 없을 때 dataclass 기본값과 **다른** 값을 쓰는 필드.
#:
#: `transfer_on` 하나다. `StepSkill`/`WrappedSkill`의 선언 기본값은
#: `[EventDef("done")]`인데, 키 없는 저장 파일에 그 값을 쓰면 출력 포트가
#: **발명**되고 `transfer_on_not_empty` 검증이 에러에서 조용한 통과로 뒤집힌다
#: (원칙 5). `call_agents`는 선언 기본값이 이미 빈 목록이라 행이 필요 없다 —
#: 없는 행을 적으면 "여기도 다르다"는 거짓말이 된다.
#: `tests/model/test_component_missing_keys.py`가 이 표를 직접 고정한다.
COMPONENT_MISSING: dict[str, Callable[[], Any]] = {"transfer_on": list}

#: 역직렬화 **부수효과 순서** — FSM 해소(경고)와 config 강등(경고)의 선후를
#: 오늘 그대로 보존한다. 키 순서(`KEY_ORDER`)와 일부러 다르다.
DESER_ORDER: tuple[str, ...] = (
    "name", "description", "fsm", "config", "body", "when_to_use",
    "transfer_on", "call_agents",
)

#: 포트 필드 — 두 방향 모두 `EventDef` 목록 코덱을 탄다.
_PORT_KEYS: frozenset[str] = frozenset({"transfer_on", "call_agents"})


def ser_component(
    component: Any,
    *,
    ser_machine: Callable[[Any], dict],
    ser_eventdef: Callable[[Any], dict],
) -> dict:
    """컴포넌트 → dict. 키는 `KEY_ORDER[BUCKET]` 순서로, **가진 것만** 나간다.

    "가진 것"의 판정은 `dataclasses.fields`다 — fork 에이전트에 `fsm` 키가 나가지
    않는 것도, 전이 스킬에 포트 키가 나가지 않는 것도 종류 목록이 아니라 필드
    선언이 정한다(퇴역 개념의 잔재를 남기지 않는다 — 원칙 7).
    """
    present = {f.name for f in dataclasses.fields(type(component))} | {"kind"}
    out: dict[str, Any] = {}
    for key in KEY_ORDER[type(component).BUCKET]:
        if key not in present:
            continue
        if key == "config":
            out[key] = component.config.to_dict()
        elif key == "fsm":
            out[key] = ser_machine(component.fsm)
        elif key in _PORT_KEYS:
            out[key] = [ser_eventdef(e) for e in getattr(component, key)]
        else:
            out[key] = getattr(component, key)
    return out


def deser_component(
    d: dict,
    spec: Any,
    *,
    deser_machine: Callable[[Any], Any],
    make_config: Callable[[], Any],
    deser_body: Callable[[dict], str],
    deser_eventdef: Callable[[dict], Any],
    new_id: Callable[[], str],
) -> Any:
    """dict → 컴포넌트. 행이 가리키는 클래스의 **필드 유무가 분기다**.

    Args:
        spec: `kinds.KindSpec` — 만들 클래스를 이미 정한 레지스트리 행.
        deser_machine: 원시 fsm dict → `StateMachine`.
        make_config: **이미 파싱된** config를 이 종류의 클래스로 강제해 돌려준다.
            파싱(`_deser_config`)과 강제(`_coerce_config`)가 나뉘어 있는 이유는
            둘 사이에 FSM 해소가 끼어야 경고 순서가 오늘과 같기 때문이다.
        deser_body: 저장 dict → 본문 문자열.
        new_id: id 키가 없을 때 새 안정 id를 만든다.
    """
    cls = spec.component_cls
    field_names = {f.name for f in dataclasses.fields(cls)}
    kwargs: dict[str, Any] = {}
    for key in DESER_ORDER:
        if key not in field_names:
            continue
        if key == "fsm":
            kwargs[key] = deser_machine(d["fsm"])
        elif key == "config":
            kwargs[key] = make_config()
        elif key in _PORT_KEYS:
            if key in d:
                kwargs[key] = [deser_eventdef(e) for e in d[key]]
            elif key in COMPONENT_MISSING:
                kwargs[key] = COMPONENT_MISSING[key]()
        elif key == "body":
            kwargs[key] = deser_body(d)
        else:
            kwargs[key] = d.get(key, "")
    return cls(**kwargs, id=d.get("id") or new_id())
