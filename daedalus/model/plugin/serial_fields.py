# daedalus/model/plugin/serial_fields.py
"""설정 직렬화의 **필드 선언 어휘** — `FieldSpec` + 코덱 (REFACTOR_SPEC §2-c).

`ComponentConfig` 계열이 "나는 어떤 키를 어떤 모양으로 저장하는가"를 스스로
선언하게 하는 값 객체 묶음이다. 선언 없이 손으로 쓴 사다리였을 때는 필드를
하나 더해 놓고 직렬화 분기를 잊으면 그 필드가 **조용히 사라졌다**(저장 →
로드에서 기본값으로 되돌아온다. M8 👻). 선언이 한 줄이면
`tests/model/plugin/test_serialize_symmetry.py`가 `fields(cls)`와 대조해 그
자리에서 실패한다.

**세 가지가 각각 따로다** — 하나로 뭉치면 오늘의 동작이 깨진다:

1. **인코딩**(모델 값 → JSON 값) · **디코딩**(JSON 값 → 모델 값). 둘은 대칭이
   아니다: `usage`는 그대로 나가지만 들어올 때는 `str(raw or "")`를 거친다.
   손상된 저장 파일의 `null`을 모델 타입으로 끌어올리는 쪽은 읽기뿐이다.
2. **키 부재값**(`FieldSpec.missing`). dataclass 기본값과 **다를 수 있다** —
   `model`은 키가 없으면 `None`이고(선언 기본값은 `ModelType.INHERIT`),
   `usage`는 키가 없으면 `"state"`다(선언 기본값은 `""`). 전자는 오늘의 결함
   이지만(backlog D10) 고치는 것은 저장 파일 해석을 바꾸는 별도 결정이라,
   여기서는 **보존**한다. `_USE_DEFAULT`면 dataclass 기본값(팩토리 포함)이
   쓰인다 — 즉 그 키를 아예 생성자에 넘기지 않는다.
3. **값이 있을 때의 디코딩**. `missing` 값은 디코더를 **거치지 않는다** —
   부재값은 이미 모델 타입이다.

`_to_enum`/`_enum_val`/`_enum_opt`는 여기가 단일 진실이다. 직렬화 패키지
(`serialize/ser.py`·`deser_fsm.py`)가 이 이름을 그대로 수입해 쓴다 — 모델이
아래, 직렬화가 위다(반대 방향이면 `model.plugin` → `model.serialize` 순환).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


# ───────────────────────── enum 헬퍼 ─────────────────────────

def _to_enum(enum_cls: Any, val: Any, default: Any = None) -> Any:
    """JSON 값 → enum. 모르는 값·None은 `default`(조용한 폴백이 계약이다).

    저장 파일의 enum 값은 사용자가 손으로 고칠 수 있고, 퇴역한 값이 남아 있을
    수도 있다. 여기서 터지면 프로젝트가 통째로 열리지 않는다 — 깨진 사용자
    파일은 건드리지 않는다(원칙 5의 "깨진 파일은 경고만").
    """
    if val is None:
        return default
    try:
        return enum_cls(val)
    except ValueError:
        return default


def _enum_val(e: Any) -> Any:
    """enum 이면 .value, 아니면 그대로 (model: ModelType | str 처럼 union 대응)."""
    return e.value if hasattr(e, "value") and not isinstance(e, str) else e


def _enum_opt(e: Any) -> Any:
    return None if e is None else _enum_val(e)


# ───────────────────────── 코덱 ─────────────────────────

class Codec(Protocol):
    """값 한 개의 인코딩/디코딩 쌍. **구현체는 상속하지 않는다**(구조적 타입).

    상속을 요구하면 코덱 하나를 더할 때마다 기저를 수입해야 하고, `Protocol`을
    상속한 클래스는 `test_dead_code`의 외부 기저 면제에 걸려 메서드 감시가
    잠든다. 구조적 타입이면 둘 다 없다.
    """

    def encode(self, value: Any) -> Any:
        """모델 값 → JSON 호환 값."""
        ...

    def decode(self, raw: Any) -> Any:
        """JSON 값 → 모델 값 (키가 **있을 때만** 불린다)."""
        ...


@dataclass(frozen=True)
class _Raw:
    """날것 그대로 — 양방향 항등. tri-state(`None`/`True`/`False`) 보존용이다."""

    def encode(self, value: Any) -> Any:
        return value

    def decode(self, raw: Any) -> Any:
        return raw


@dataclass(frozen=True)
class _ListCopy:
    """목록 복사 — 모델과 저장 dict가 같은 리스트 객체를 공유하지 않게 한다."""

    def encode(self, value: Any) -> Any:
        return list(value)

    def decode(self, raw: Any) -> Any:
        return list(raw)


@dataclass(frozen=True)
class _Str:
    """읽을 때만 문자열로 — `null`이 든 저장 파일도 빈 문자열로 받는다."""

    def encode(self, value: Any) -> Any:
        return value

    def decode(self, raw: Any) -> Any:
        return str(raw or "")


@dataclass(frozen=True)
class _StrOrDefault:
    """빈 값(``None``·``""``)이면 기본 문자열로 — "비워 두면 기본"이 계약인 필드."""

    default: str

    def encode(self, value: Any) -> Any:
        return value

    def decode(self, raw: Any) -> Any:
        return raw or self.default


@dataclass(frozen=True)
class _Enum:
    """필수 enum — 인코딩은 `.value`, 디코딩 실패는 `default`."""

    enum_cls: Any
    default: Any

    def encode(self, value: Any) -> Any:
        return value.value

    def decode(self, raw: Any) -> Any:
        return _to_enum(self.enum_cls, raw, self.default)


@dataclass(frozen=True)
class _EnumOpt:
    """선택 enum — `None`이 정상 값이고 미지 값도 `None`으로 떨어진다."""

    enum_cls: Any

    def encode(self, value: Any) -> Any:
        return _enum_opt(value)

    def decode(self, raw: Any) -> Any:
        return _to_enum(self.enum_cls, raw)


@dataclass(frozen=True)
class _EnumOrStr:
    """enum **또는** 문자열 — 미지 값을 enum으로 못 올려도 **원문을 보존**한다.

    `model`이 이것이다: 우리가 모르는 모델 이름(새 CC 모델·별칭)을 사용자가
    적어 두면 그대로 왕복해야 한다. `_EnumOpt`였다면 저장 → 로드 한 번에
    사용자의 값이 사라진다.
    """

    enum_cls: Any

    def encode(self, value: Any) -> Any:
        return _enum_val(value)

    def decode(self, raw: Any) -> Any:
        return _to_enum(self.enum_cls, raw, raw)


#: 날것 통과 (tri-state·dict·임의 JSON 값).
RAW: Codec = _Raw()
#: 목록 복사.
LIST: Codec = _ListCopy()
#: 읽을 때 문자열 강제.
STR: Codec = _Str()
def STR_OR_DEFAULT(default: str) -> Codec:
    """빈 값이면 `default`로 읽는 문자열 코덱."""
    return _StrOrDefault(default)


def ENUM(enum_cls: Any, default: Any) -> Codec:
    """필수 enum 코덱 — 미지 값은 `default`."""
    return _Enum(enum_cls, default)


def ENUM_OPT(enum_cls: Any) -> Codec:
    """선택 enum 코덱 — 미지 값·부재는 `None`."""
    return _EnumOpt(enum_cls)


def ENUM_OR_STR(enum_cls: Any) -> Codec:
    """enum 또는 원문 문자열 코덱."""
    return _EnumOrStr(enum_cls)


# ───────────────────────── 필드 선언 ─────────────────────────

class _UseDefault:
    """`FieldSpec.missing`의 센티널 타입 — "dataclass 기본값을 쓴다".

    `None`을 센티널로 쓸 수 없다: `model`의 부재값이 **실제로** `None`이라
    "부재값이 None이다"와 "부재값을 안 적었다"가 구분돼야 한다.
    """

    def __repr__(self) -> str:  # pragma: no cover — 진단용
        return "<USE_DEFAULT>"


#: `FieldSpec.missing`의 기본 센티널.
_USE_DEFAULT = _UseDefault()


@dataclass(frozen=True)
class FieldSpec:
    """설정 필드 한 개의 직렬화 계약 — 이름 · 코덱 · 키 부재값."""

    name: str
    codec: Codec
    missing: Any = _USE_DEFAULT

    def read(self, d: dict) -> tuple[bool, Any]:
        """저장 dict에서 이 필드의 값을 꺼낸다 → (생성자에 넘길까, 값).

        "넘기지 않는다"가 곧 dataclass 기본값이다 — 기본값을 여기서 복제하면
        선언과 두 벌이 되고, `default_factory`(빈 리스트)는 복제하는 순간
        **모든 인스턴스가 같은 리스트를 공유**하는 고전적 함정이 된다.
        """
        if self.name in d:
            return True, self.codec.decode(d[self.name])
        if self.missing is _USE_DEFAULT:
            return False, None
        return True, self.missing
