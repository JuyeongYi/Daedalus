# daedalus/cli/core.py
"""블랙보드 코어 — 스키마 검증·코어션·원자적 쓰기·낙관적 잠금 (WP-BM).

**출력 채널이 없다.** 모든 함수는 값을 돌려주고 실패는 :class:`BlackboardError`로
낸다 — 진단 문장은 예외의 ``message``/``detail``에 담긴다. 진행 상황처럼
성공 경로에서도 알려야 하는 문장은 호출자가 넘긴 ``on_note`` 콜백으로 나간다.
그래서 같은 코어를 stdio MCP 서버(:mod:`daedalus.cli.mcp_server`)가 그대로
재사용한다 — 서버는 예외를 ``{"ok": false, "error": {...}}`` 결과로 옮기기만 한다.

검증의 단일 진실은 **컴파일 산출 ``schemas/<플러그인>.json`` 파일 자체**다.
코어는 플러그인이 설치된 작업 폴더에서 돌고, 그곳에는 Daedalus 모델도 프로젝트
파일도 없다 — 있는 것은 산출된 스키마뿐이다. 그래서 이 모듈은
``daedalus.model``을 임포트하지 않으며(순수 stdlib), 검증기는 산출 스키마가
실제로 만들어내는 형상(``type``/``properties``/``required``/``items``/
``uniqueItems``)만 다루는 최소 구현이다. 범용 JSON Schema 구현이 아니다.

오류 kind는 셋이고, 종전 CLI의 exit code와 1:1이다:
``not_found``(3 — 대상 상태 파일 없음) / ``usage``(2 — 사용법·스키마·IO 오류) /
``rejected``(1 — 검증 실패, 낙관적 잠금 재시도 소진).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

#: 상태 파일 트리의 루트. 실제 블랙보드 상태는 `state/<플러그인>/`로 갈라지고
#: (WP-NS), 진행 파일만 이 루트에 하나로 남는다(D13).
DEFAULT_STATE_ROOT = "state"

#: 스키마 밖 규약 파일(WP-RS 진행 상태) — 전 클래스 순회의 대상이 아니다.
PROGRESS_FILENAME = "__progress__.json"
PROGRESS_CLASS = "__progress__"

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2
EXIT_NO_FILE = 3

#: 오류 kind — 값이 그대로 MCP 결과의 `error.kind`가 된다.
KIND_NOT_FOUND = "not_found"
KIND_USAGE = "usage"
KIND_REJECTED = "rejected"

#: kind → 종전 CLI exit code. 이 표가 두 표면의 계약을 하나로 묶는다.
KIND_TO_EXIT: dict[str, int] = {
    KIND_NOT_FOUND: EXIT_NO_FILE,
    KIND_USAGE: EXIT_USAGE,
    KIND_REJECTED: EXIT_INVALID,
}

# write의 낙관적 잠금 재시도 횟수. 충돌은 "남이 방금 썼다"는 뜻이므로 다시
# 읽어 적용하면 대개 한 번에 끝난다 — 무한 재시도는 살아 있는 락 경쟁에서
# 프로세스가 돌아오지 않게 만들 뿐이라 상한을 둔다.
_WRITE_MAX_ATTEMPTS = 3

#: 성공 경로의 진단 문장을 받는 콜백. 없으면 문장은 버려진다.
NoteFn = Callable[[str], None]


class BlackboardError(Exception):
    """코어가 내는 단 하나의 실패 — kind가 원인의 종류를 말한다.

    ``detail``은 사람이 줄 단위로 읽을 부가 정보(검증 위반 목록 등)다. 문자열
    한 줄에 욱여넣지 않는 이유는 소비자가 둘이기 때문이다 — CLI는 stderr에
    줄로 풀고, MCP 서버는 결과 JSON의 배열로 낸다.
    """

    def __init__(self, kind: str, message: str, detail: list[str] | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.detail = list(detail) if detail else []

    @property
    def code(self) -> int:
        """종전 CLI exit code — kind와 1:1."""
        return KIND_TO_EXIT[self.kind]


def usage_error(message: str, detail: list[str] | None = None) -> BlackboardError:
    return BlackboardError(KIND_USAGE, message, detail)


def not_found_error(message: str) -> BlackboardError:
    return BlackboardError(KIND_NOT_FOUND, message)


def rejected_error(message: str, detail: list[str] | None = None) -> BlackboardError:
    return BlackboardError(KIND_REJECTED, message, detail)


def _emit_note(on_note: NoteFn | None, message: str) -> None:
    if on_note is not None:
        on_note(message)


# ─────────────────────────── 스키마 로딩·조회 ───────────────────────────


def load_schemas(path: Path) -> dict[str, dict]:
    """schemas.json → {클래스명: 스키마 object}. 형식이 어긋나면 usage 오류."""
    if not path.is_file():
        raise usage_error(
            f"스키마 파일이 없다: {path.as_posix()}\n"
            "--schemas 로 경로를 지정하거나 플러그인을 다시 컴파일하라."
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - 권한 등 환경 의존
        raise usage_error(f"스키마 파일을 읽을 수 없다: {path.as_posix()}: {exc}") from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise usage_error(f"스키마 JSON 파싱 실패: {path.as_posix()}: {exc}") from exc
    if not isinstance(data, dict):
        raise usage_error(f"스키마 최상위가 JSON 객체가 아니다: {path.as_posix()}")
    for name, schema in data.items():
        if not isinstance(schema, dict):
            raise usage_error(f"스키마 항목 '{name}'이 JSON 객체가 아니다: {path.as_posix()}")
    return data


def _class_names(schemas: dict[str, dict]) -> list[str]:
    return list(schemas.keys())


def class_schema(schemas: dict[str, dict], name: str) -> dict:
    if name in schemas:
        return schemas[name]
    available = ", ".join(_class_names(schemas)) or "(없음)"
    raise usage_error(f"클래스 '{name}'이 스키마에 없다. 가용 클래스: {available}")


def _properties(schema: dict) -> dict[str, dict]:
    props = schema.get("properties")
    if not isinstance(props, dict):
        return {}
    return {k: v for k, v in props.items() if isinstance(v, dict)}


def _required_names(schema: dict) -> list[str]:
    req = schema.get("required")
    if not isinstance(req, list):
        return []
    return [name for name in req if isinstance(name, str)]


def field_schema(schema: dict, cls: str, field: str) -> dict:
    props = _properties(schema)
    if field in props:
        return props[field]
    available = ", ".join(props) or "(없음)"
    raise usage_error(f"필드 '{field}'가 클래스 '{cls}'에 없다. 가용 필드: {available}")


# ─────────────────────────── 타입 형상 ───────────────────────────


def _json_type(prop: dict) -> str:
    """선언 타입 문자열. 무제약(ANY)이면 빈 문자열."""
    declared = prop.get("type")
    return declared if isinstance(declared, str) else ""


def _is_collection(prop: dict) -> bool:
    return _json_type(prop) == "array"


def _items_schema(prop: dict) -> dict:
    items = prop.get("items")
    return items if isinstance(items, dict) else {}


def _unique_items(prop: dict) -> bool:
    return bool(prop.get("uniqueItems"))


def _collection_kind(prop: dict) -> str:
    if not _is_collection(prop):
        return "none"
    return "set" if _unique_items(prop) else "list"


_ZERO_VALUES: dict[str, Any] = {
    "string": "",
    "integer": 0,
    "number": 0.0,
    "boolean": False,
    "array": [],
    "object": {},
}


def _zero_value(prop: dict) -> Any:
    """required 필드의 초기값 — 타입별 제로값. 무제약 타입은 None."""
    declared = _json_type(prop)
    zero = _ZERO_VALUES.get(declared)
    if isinstance(zero, (list, dict)):
        return type(zero)()
    return zero


def _initial_value(prop: dict) -> Any:
    """required 필드의 초기값 — 선언 타입에 맞는 ``default``가 있으면 그 값.

    스키마의 ``default``는 설계자가 적어 둔 초기값이므로 제로값보다 우선한다
    (default ``true``인 boolean이 ``false``로 초기화되면 설계와 어긋난다).
    다만 **타입이 보장되지 않는다** — 편집기가 default 셀을 자유 텍스트로
    받으므로 boolean 필드에 문자열 ``"true"``가 실려 나올 수 있고, 그대로 쓰면
    ``init``이 자기가 만든 객체의 검증에 걸려 실패한다. 그래서 선언 타입에
    맞을 때만 쓰고, 어긋나면 조용히 제로값으로 물러난다(초기화를 아예 못 하게
    막는 것보다 낫다 — 어긋난 default는 ``list``의 출력으로 드러난다).
    """
    if "default" in prop:
        candidate = prop["default"]
        if not _check_shape(candidate, prop):
            return _zero_value(prop)
        if isinstance(candidate, (list, dict)):
            return json.loads(json.dumps(candidate))  # 스키마 쪽 객체와 공유 금지
        return candidate
    return _zero_value(prop)


def initial_object(schema: dict) -> dict:
    """스키마 기반 초기 객체 — required만(타입에 맞는 default, 없으면 제로값), 비required는 생략."""
    props = _properties(schema)
    obj: dict[str, Any] = {}
    for name in _required_names(schema):
        prop = props.get(name)
        if prop is None:
            continue
        obj[name] = _initial_value(prop)
    return obj


# ─────────────────────────── 값 코어션 ───────────────────────────

_TRUE_WORDS = ("true", "1", "yes", "y", "on")
_FALSE_WORDS = ("false", "0", "no", "n", "off")


def coerce_scalar(raw: str, prop: dict, where: str) -> Any:
    """문자열 → 스키마 스칼라 타입 값."""
    declared = _json_type(prop)
    text = raw.strip()
    if declared == "string":
        return raw
    if declared == "integer":
        try:
            return int(text, 10)
        except ValueError:
            raise usage_error(f"{where}: 정수가 아니다: {raw!r}") from None
    if declared == "number":
        try:
            return float(text)
        except ValueError:
            raise usage_error(f"{where}: 수가 아니다: {raw!r}") from None
    if declared == "boolean":
        low = text.lower()
        if low in _TRUE_WORDS:
            return True
        if low in _FALSE_WORDS:
            return False
        raise usage_error(
            f"{where}: 불리언이 아니다: {raw!r} "
            f"(허용: {'/'.join(_TRUE_WORDS)} · {'/'.join(_FALSE_WORDS)})"
        )
    if declared == "object":
        try:
            value = json.loads(raw)
        except ValueError:
            raise usage_error(f"{where}: JSON 객체가 아니다: {raw!r}") from None
        if not isinstance(value, dict):
            raise usage_error(f"{where}: JSON 객체가 아니다: {raw!r}")
        return value
    if declared == "array":
        return coerce_array(raw, prop, where)
    # 무제약(ANY): JSON으로 읽히면 그 값, 아니면 문자열 그대로.
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def coerce_array(raw: str, prop: dict, where: str) -> list:
    """컬렉션 필드의 통째 대입 값 — JSON 배열 문자열. set이면 중복 제거."""
    try:
        value = json.loads(raw)
    except ValueError:
        raise usage_error(
            f"{where}: 컬렉션 필드의 --set 값은 JSON 배열이어야 한다 "
            f"(예: --set {where.rsplit('.', 1)[-1]}='[\"a\",\"b\"]'): {raw!r}"
        ) from None
    if not isinstance(value, list):
        raise usage_error(f"{where}: 컬렉션 필드의 --set 값은 JSON 배열이어야 한다: {raw!r}")
    if _unique_items(prop):
        return _dedupe(value)
    return value


def coerce_value(raw: Any, prop: dict, where: str) -> Any:
    """입력 값 하나 → 스키마 타입 값 (문자열이면 코어션, 아니면 JSON 타입 그대로).

    CLI는 값을 언제나 문자열로 받았지만 MCP 도구는 JSON 타입을 그대로 받는다
    (``{"count": 3}``). 그래서 판정을 하나로 둔다: **문자열이면** 종전 코어션
    규칙을 그대로 적용하고, 그 밖의 JSON 값은 손대지 않는다. 손대지 않은
    값의 타입이 스키마와 어긋나면 쓰기 직전 검증 게이트가 잡는다(원칙 5 —
    조용히 고치지 않는다).

    예외는 ``string`` 필드다 — 문자열 값은 코어션 대상이 아니라 그대로다.
    """
    if isinstance(raw, str):
        return coerce_scalar(raw, prop, where)
    if isinstance(raw, list) and _unique_items(prop):
        return _dedupe(raw)
    return raw


def _dedupe(values: list) -> list:
    """순서 보존 중복 제거 — 원소가 unhashable일 수 있어 선형 비교."""
    out: list = []
    for value in values:
        if not any(value == seen and type(value) is type(seen) for seen in out):
            out.append(value)
    return out


# ─────────────────────────── 검증 ───────────────────────────


def _type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "null"


def _check_value(value: Any, prop: dict, path: str, out: list[str]) -> None:
    declared = _json_type(prop)
    if not declared:
        return
    if declared == "array":
        if not isinstance(value, list):
            out.append(f"{path}: array 이어야 한다 (실제: {_type_name(value)})")
            return
        items = _items_schema(prop)
        if items:
            for index, element in enumerate(value):
                _check_value(element, items, f"{path}[{index}]", out)
        if _unique_items(prop) and len(_dedupe(value)) != len(value):
            out.append(f"{path}: uniqueItems 위반 — 중복 원소가 있다")
        return
    if declared == "boolean":
        ok = isinstance(value, bool)
    elif declared == "integer":
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif declared == "number":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif declared == "string":
        ok = isinstance(value, str)
    elif declared == "object":
        ok = isinstance(value, dict)
    else:  # 산출 스키마가 만들지 않는 타입 — 검사하지 않는다.
        return
    if not ok:
        out.append(f"{path}: {declared} 이어야 한다 (실제: {_type_name(value)})")


def _check_shape(value: Any, prop: dict) -> bool:
    """값이 속성 스키마 형상에 맞는가 (메시지 없이 참/거짓만)."""
    problems: list[str] = []
    _check_value(value, prop, "", problems)
    return not problems


def validate_object(obj: Any, schema: dict, cls: str) -> list[str]:
    """객체 하나의 위반 목록 (빈 목록 = 통과)."""
    if not isinstance(obj, dict):
        return [f"{cls}: 최상위가 JSON 객체가 아니다 (실제: {_type_name(obj)})"]
    out: list[str] = []
    props = _properties(schema)
    for name in _required_names(schema):
        if name not in obj:
            out.append(f"{cls}.{name}: 필수 필드가 없다")
    for name, value in obj.items():
        prop = props.get(name)
        if prop is None:
            # 스키마에 없는 키는 허용(JSON Schema 기본) — 쓰기 경로로는 들어올 수 없다.
            continue
        _check_value(value, prop, f"{cls}.{name}", out)
    return out


# ─────────────────────────── 상태 파일 IO ───────────────────────────


def state_path(state_dir: Path, cls: str) -> Path:
    return state_dir / f"{cls}.json"


def read_state(path: Path) -> Any:
    """상태 파일 파싱. 없으면 not_found, 깨졌으면 usage."""
    if not path.is_file():
        raise not_found_error(f"상태 파일이 없다: {path.as_posix()}")
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - 권한 등 환경 의존
        raise usage_error(f"상태 파일을 읽을 수 없다: {path.as_posix()}: {exc}") from exc
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise usage_error(f"상태 파일 JSON 파싱 실패: {path.as_posix()}: {exc}") from exc


def read_raw(path: Path) -> str | None:
    """상태 파일의 원문. 없으면 None (낙관적 잠금의 비교 기준).

    mtime이 아니라 **내용**을 비교한다. Windows의 mtime 해상도(파일시스템에 따라
    수십 ms~2초)로는 빠른 연속 쓰기를 구분하지 못해, 남의 쓰기를 못 본 채
    덮어쓰는 경우가 생긴다.
    """
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:  # pragma: no cover - 권한 등 환경 의존
        raise usage_error(f"상태 파일을 읽을 수 없다: {path.as_posix()}: {exc}") from exc


def write_state_checked(path: Path, obj: Any, expected_raw: str | None) -> bool:
    """디스크 내용이 `expected_raw` 그대로일 때만 쓴다 (낙관적 잠금). 달랐으면 False.

    읽기-수정-쓰기 사이에 다른 프로세스가 쓴 것을 덮지 않기 위한 낙관적 잠금이다
    (병렬 서브에이전트가 같은 클래스를 갱신하는 시나리오에서 lost update가 났다).

    **완전한 상호배제는 아니다.** 비교와 `os.replace` 사이에도 남이 끼어들 수
    있는 창은 남는다 — 그것까지 막으려면 파일 잠금이 필요한데, 크래시로 남은
    잠금 파일을 깨는 휴리스틱이 그 자체로 새 고장을 만든다. 창이 마이크로초
    수준으로 좁아지는 것이 실질적인 이득이고, 잃는 것은 없다.
    """
    if read_raw(path) != expected_raw:
        return False
    write_state(path, obj)
    return True


def write_state(path: Path, obj: Any) -> None:
    """원자적 쓰기 — 임시 파일에 완전히 쓴 뒤 os.replace.

    검증 실패 경로는 여기까지 오지 않으므로 원본은 그대로 남는다. 쓰기 도중
    죽어도 반쯤 쓰인 상태 파일이 남지 않는다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    handle, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


# ─────────────────────────── 경로 유도 ───────────────────────────


def plugin_name(schemas_path: Path) -> str:
    """스키마 파일 이름이 곧 플러그인 이름이다 (WP-NS 명명 규약 `schemas/<이름>.json`)."""
    return schemas_path.stem


def resolve_state_dir(state_dir: str | None, schemas_path: Path) -> Path:
    """`--state-dir` 유도 — 명시하지 않으면 `state/<스키마 stem>`.

    인자 **하나**가 스키마와 상태 위치를 모두 결정하게 만드는 장치다(D10). 따로
    받으면 `--state-dir` 누락이 **조용히** 네임스페이스 밖에 쓰는 사고가 된다 —
    검증까지 통과하므로 아무도 눈치채지 못한다(`--schemas` 누락은 파일이 없어
    시끄럽게 실패한다).

    스키마가 절대경로여도(마켓플레이스 빌드의 `${CLAUDE_PLUGIN_ROOT}/…`) **stem만**
    쓰므로 상태는 항상 작업 폴더 상대로 남는다 — 상태까지 플러그인 디렉토리로
    따라가면 작업 폴더마다 달라야 할 데이터가 섞인다.
    """
    if state_dir:
        return Path(state_dir)
    return Path(DEFAULT_STATE_ROOT) / plugin_name(schemas_path)


# ─────────────────────────── 명령 ───────────────────────────


def list_classes(
    schemas: dict[str, dict], state_dir: Path, schemas_path: Path
) -> dict[str, Any]:
    """스키마의 클래스·필드 목록."""
    classes: list[dict[str, Any]] = []
    for name, schema in schemas.items():
        props = _properties(schema)
        required = set(_required_names(schema))
        fields: list[dict[str, Any]] = []
        for field_name, prop in props.items():
            collection = _collection_kind(prop)
            scalar = _items_schema(prop) if collection != "none" else prop
            entry: dict[str, Any] = {
                "name": field_name,
                "type": _json_type(scalar) or "any",
                "collection": collection,
                "required": field_name in required,
            }
            if "default" in prop:
                entry["default"] = prop["default"]
            fields.append(entry)
        item: dict[str, Any] = {"name": name}
        description = schema.get("description")
        if isinstance(description, str) and description:
            item["description"] = description
        item["file"] = state_path(state_dir, name).as_posix()
        item["fields"] = fields
        classes.append(item)
    return {
        "schemas": schemas_path.as_posix(),
        "state_dir": state_dir.as_posix(),
        "classes": classes,
    }


def read_value(
    schemas: dict[str, dict], state_dir: Path, cls: str, field: str | None
) -> Any:
    """상태 파일 전체 또는 필드 값. 필드 오타는 파일 유무보다 **먼저** 판정한다."""
    schema = class_schema(schemas, cls)
    if field is not None:
        field_schema(schema, cls, field)  # 존재 검사 — 없으면 usage
    obj = read_state(state_path(state_dir, cls))
    if field is None:
        return obj
    if not isinstance(obj, dict):
        raise usage_error(f"{cls}: 상태 파일 최상위가 JSON 객체가 아니다")
    return obj.get(field)


def init_class(
    schemas: dict[str, dict],
    state_dir: Path,
    cls: str,
    force: bool = False,
    on_note: NoteFn | None = None,
) -> dict:
    """스키마 기반 초기 객체를 만들어 쓴다. 이미 있으면 usage(force면 재생성)."""
    schema = class_schema(schemas, cls)
    path = state_path(state_dir, cls)
    if path.exists() and not force:
        raise usage_error(f"이미 존재한다: {path.as_posix()} (재생성하려면 --force)")
    obj = initial_object(schema)
    violations = validate_object(obj, schema, cls)
    if violations:  # 스키마 자체가 초기 객체를 통과시키지 못하는 경우
        raise rejected_error(
            f"'{cls}'의 초기 객체가 스키마 검증을 통과하지 못해 만들지 않았다.",
            violations,
        )
    write_state(path, obj)
    _emit_note(on_note, f"생성: {path.as_posix()}")
    return obj


def _require_collection(prop: dict, where: str, option: str) -> None:
    if not _is_collection(prop):
        raise usage_error(
            f"{where}: {option}는 컬렉션 필드에만 쓸 수 있다 "
            f"(이 필드는 {_json_type(prop) or 'any'}) — --set 을 쓰라"
        )


def apply_operations(
    obj: dict,
    schema: dict,
    cls: str,
    sets: dict[str, Any],
    appends: dict[str, Any],
    removes: dict[str, Any],
) -> None:
    """set → append → remove 순으로 제자리 적용.

    값은 JSON 타입 그대로 받되 문자열이면 코어션 규칙이 돈다(`coerce_value`).
    `append`의 값이 배열이면 **원소 여럿**을 차례로 덧붙인다 — 스칼라 하나만
    받으면 "여러 개를 더한다"를 표현할 길이 없어 호출이 반복된다.
    """
    for name, raw in sets.items():
        prop = field_schema(schema, cls, name)
        where = f"{cls}.{name}"
        if _is_collection(prop) and isinstance(raw, str):
            obj[name] = coerce_array(raw, prop, where)
        else:
            obj[name] = coerce_value(raw, prop, where)
    for name, raw in appends.items():
        prop = field_schema(schema, cls, name)
        where = f"{cls}.{name}"
        _require_collection(prop, where, "append")
        current = obj.get(name)
        if not isinstance(current, list):
            current = []
        items = raw if isinstance(raw, list) else [raw]
        elements = [coerce_value(item, _items_schema(prop), where) for item in items]
        current = list(current) + elements
        obj[name] = _dedupe(current) if _unique_items(prop) else current
    for name, raw in removes.items():
        prop = field_schema(schema, cls, name)
        where = f"{cls}.{name}"
        _require_collection(prop, where, "remove")
        items = raw if isinstance(raw, list) else [raw]
        elements = [coerce_value(item, _items_schema(prop), where) for item in items]
        current = obj.get(name)
        if not isinstance(current, list):
            # 제거는 없는 것을 만들지 않는다 — 키가 없으면 그대로 없고, 리스트가
            # 아닌 값(스키마 위반)은 손대지 않는다(빈 배열로 덮으면 고장을 조용히
            # 지운다. 그 위반은 아래 검증 게이트가 잡아 쓰기를 막는다).
            continue
        # 원소 단위 제거 — 같은 값이 여러 번 있으면 전부 없앤다
        # ("remove f=v 이후 v는 f에 없다"가 기대 동작이다).
        obj[name] = [
            item
            for item in current
            if not any(item == e and type(item) is type(e) for e in elements)
        ]


def write_class(
    schemas: dict[str, dict],
    state_dir: Path,
    cls: str,
    sets: dict[str, Any] | None = None,
    appends: dict[str, Any] | None = None,
    removes: dict[str, Any] | None = None,
    on_note: NoteFn | None = None,
) -> dict:
    """읽기-수정-쓰기 (검증 통과 시에만 기록). 쓴 뒤의 객체를 돌려준다.

    낙관적 잠금 + 재시도. 남이 그 사이에 썼으면 **다시 읽어 수정을 새 내용
    위에 다시 적용한다** — 병합할 수 없는 충돌이 아니라 잃어버린 갱신을 막는
    것이 목적이므로, 되풀이하면 두 쓰기가 모두 살아남는다.
    """
    schema = class_schema(schemas, cls)
    sets = sets or {}
    appends = appends or {}
    removes = removes or {}
    if not (sets or appends or removes):
        raise usage_error("set / append / remove 중 최소 하나가 필요하다")
    path = state_path(state_dir, cls)

    for attempt in range(1, _WRITE_MAX_ATTEMPTS + 1):
        expected_raw = read_raw(path)
        if expected_raw is None:
            obj: Any = initial_object(schema)
        else:
            obj = read_state(path)
            if not isinstance(obj, dict):
                raise usage_error(
                    f"{cls}: 상태 파일 최상위가 JSON 객체가 아니다: {path.as_posix()}"
                )
            obj = dict(obj)
        apply_operations(obj, schema, cls, sets, appends, removes)
        violations = validate_object(obj, schema, cls)
        if violations:
            raise rejected_error(
                f"쓰지 않았다 — {path.as_posix()}는 그대로다.", violations
            )
        if write_state_checked(path, obj, expected_raw):
            return obj
        _emit_note(
            on_note,
            f"{path.as_posix()}가 읽은 뒤에 바뀌었다 — 다시 읽어 적용한다 "
            f"({attempt}/{_WRITE_MAX_ATTEMPTS}).",
        )

    raise rejected_error(
        f"쓰지 않았다 — {path.as_posix()}를 {_WRITE_MAX_ATTEMPTS}번 시도하는 동안 "
        f"다른 프로세스가 계속 고쳤다. 동시 쓰기를 줄이거나 잠시 뒤 다시 시도하라."
    )


def validate_classes(
    schemas: dict[str, dict],
    state_dir: Path,
    names: list[str] | None = None,
    on_note: NoteFn | None = None,
) -> dict[str, Any]:
    """상태 파일 검증 — 위반이 있어도 **결과로** 돌려준다(예외가 아니다).

    이름을 생략한 전 클래스 순회에서 상태 파일 부재는 고장이 아니다(아직
    초기화되지 않았을 뿐) — ``missing``으로 보고한다. 반면 **이름을 명시한**
    호출에서 그 파일이 없으면 `read`와 같은 뜻이다(`validate_code`가 3으로
    옮긴다). 물어본 대상이 없다는 것 자체가 대답이고, 결과만 훑는 호출자가
    "검사했고 정상"으로 오해하면 안 된다.
    """
    names = list(names or [])
    if names:
        for name in names:
            class_schema(schemas, name)  # 존재 검사
            if name == PROGRESS_CLASS:
                raise usage_error(
                    f"'{PROGRESS_CLASS}'는 스키마 밖 규약 파일이라 검증 대상이 아니다"
                )
        targets = list(names)
    else:
        # 스키마 밖 규약 파일(state/__progress__.json)은 순회 대상이 아니다.
        targets = [name for name in _class_names(schemas) if name != PROGRESS_CLASS]

    checked: list[str] = []
    missing: list[str] = []
    violations: list[str] = []
    for name in targets:
        path = state_path(state_dir, name)
        if not path.is_file():
            missing.append(name)
            continue
        try:
            obj = read_state(path)
        except BlackboardError as exc:
            violations.append(f"{name}: {exc.message}")
            checked.append(name)
            continue
        checked.append(name)
        violations.extend(validate_object(obj, schemas[name], name))

    if missing:
        _emit_note(on_note, "상태 파일 없음(검증 생략): " + ", ".join(missing))
        if names:
            _emit_note(
                on_note,
                "지정한 클래스의 상태 파일이 없다 — 먼저 "
                f"init {missing[0]} 로 만들라.",
            )
    return {
        "ok": not violations,
        "checked": checked,
        "missing": missing,
        "violations": violations,
    }


def validate_code(result: dict[str, Any], named: bool) -> int:
    """검증 결과 → 종전 CLI exit code. 위반이 있으면 그쪽이 우선(1)."""
    if result["violations"]:
        return EXIT_INVALID
    if named and result["missing"]:
        return EXIT_NO_FILE
    return EXIT_OK
