# daedalus/cli/blackboard.py
"""블랙보드 CLI (``daedalus-bb``) — work 폴더의 ``state/`` 파일 읽기/쓰기/검증.

컴파일 산출(스킬·에이전트 본문의 블랙보드 지시)이 런타임에 이 CLI를 호출한다.
소비자가 LLM이므로 **stdout에 나가는 것은 JSON뿐**이고, 진단·안내는 stderr로 나간다.
성공 경로는 stdout에 JSON 한 덩이를 낸다. 오류 경로(exit 2/3, init·write의 exit 1)는
stdout에 **아무것도 쓰지 않는다** — ``validate``만 예외로, 검증에 실패해도
``{"ok": false, "violations": [...]}``를 stdout에 낸다. 즉 stdout을 무조건
``json.loads``에 먹이지 말고 exit code로 먼저 갈라야 한다.

검증의 단일 진실은 **컴파일 산출물 ``schemas/schemas.json`` 파일 자체**다.
CLI는 설치 대상 프로젝트(플러그인이 깔린 작업 폴더)에서 돌고, 그곳에는
Daedalus 모델도 프로젝트 파일도 없다 — 있는 것은 산출된 스키마뿐이다.
그래서 이 모듈은 ``daedalus.model``을 임포트하지 않으며(순수 stdlib),
검증기는 산출 스키마가 실제로 만들어내는 형상
(``type``/``properties``/``required``/``items``/``uniqueItems``)만 다루는
최소 구현이다. 범용 JSON Schema 구현이 아니다.

exit code: 0 성공 / 1 검증 실패 / 2 사용법·스키마·IO 오류 /
3 대상 상태 파일 없음(``read``, 그리고 클래스를 **명시한** ``validate``).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_STATE_DIR = "state"
DEFAULT_SCHEMAS = "schemas/schemas.json"

#: 스키마 밖 규약 파일(WP-RS 진행 상태) — 전 클래스 순회의 대상이 아니다.
PROGRESS_FILENAME = "__progress__.json"
PROGRESS_CLASS = "__progress__"

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2
EXIT_NO_FILE = 3


class CliError(Exception):
    """사용자에게 stderr로 알리고 정해진 코드로 끝내는 오류."""

    def __init__(self, message: str, code: int = EXIT_USAGE) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


# ─────────────────────────── 스키마 로딩·조회 ───────────────────────────


def load_schemas(path: Path) -> dict[str, dict]:
    """schemas.json → {클래스명: 스키마 object}. 형식이 어긋나면 CliError(2)."""
    if not path.is_file():
        raise CliError(
            f"스키마 파일이 없다: {path.as_posix()}\n"
            "--schemas 로 경로를 지정하거나 플러그인을 다시 컴파일하라."
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - 권한 등 환경 의존
        raise CliError(f"스키마 파일을 읽을 수 없다: {path.as_posix()}: {exc}") from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise CliError(f"스키마 JSON 파싱 실패: {path.as_posix()}: {exc}") from exc
    if not isinstance(data, dict):
        raise CliError(f"스키마 최상위가 JSON 객체가 아니다: {path.as_posix()}")
    for name, schema in data.items():
        if not isinstance(schema, dict):
            raise CliError(f"스키마 항목 '{name}'이 JSON 객체가 아니다: {path.as_posix()}")
    return data


def _class_names(schemas: dict[str, dict]) -> list[str]:
    return list(schemas.keys())


def class_schema(schemas: dict[str, dict], name: str) -> dict:
    if name in schemas:
        return schemas[name]
    available = ", ".join(_class_names(schemas)) or "(없음)"
    raise CliError(f"클래스 '{name}'이 스키마에 없다. 가용 클래스: {available}")


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
    raise CliError(f"필드 '{field}'가 클래스 '{cls}'에 없다. 가용 필드: {available}")


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
    """명령줄 문자열 → 스키마 스칼라 타입 값."""
    declared = _json_type(prop)
    text = raw.strip()
    if declared == "string":
        return raw
    if declared == "integer":
        try:
            return int(text, 10)
        except ValueError:
            raise CliError(f"{where}: 정수가 아니다: {raw!r}") from None
    if declared == "number":
        try:
            return float(text)
        except ValueError:
            raise CliError(f"{where}: 수가 아니다: {raw!r}") from None
    if declared == "boolean":
        low = text.lower()
        if low in _TRUE_WORDS:
            return True
        if low in _FALSE_WORDS:
            return False
        raise CliError(
            f"{where}: 불리언이 아니다: {raw!r} "
            f"(허용: {'/'.join(_TRUE_WORDS)} · {'/'.join(_FALSE_WORDS)})"
        )
    if declared == "object":
        try:
            value = json.loads(raw)
        except ValueError:
            raise CliError(f"{where}: JSON 객체가 아니다: {raw!r}") from None
        if not isinstance(value, dict):
            raise CliError(f"{where}: JSON 객체가 아니다: {raw!r}")
        return value
    if declared == "array":
        return coerce_array(raw, prop, where)
    # 무제약(ANY): JSON으로 읽히면 그 값, 아니면 문자열 그대로.
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def coerce_array(raw: str, prop: dict, where: str) -> list:
    """컬렉션 필드의 ``--set`` 값 — JSON 배열 통째. set이면 중복 제거."""
    try:
        value = json.loads(raw)
    except ValueError:
        raise CliError(
            f"{where}: 컬렉션 필드의 --set 값은 JSON 배열이어야 한다 "
            f"(예: --set {where.rsplit('.', 1)[-1]}='[\"a\",\"b\"]'): {raw!r}"
        ) from None
    if not isinstance(value, list):
        raise CliError(f"{where}: 컬렉션 필드의 --set 값은 JSON 배열이어야 한다: {raw!r}")
    if _unique_items(prop):
        return _dedupe(value)
    return value


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
            # 스키마 밖 키는 허용(JSON Schema 기본) — CLI로는 들어올 수 없다.
            continue
        _check_value(value, prop, f"{cls}.{name}", out)
    return out


# ─────────────────────────── 상태 파일 IO ───────────────────────────


def state_path(state_dir: Path, cls: str) -> Path:
    return state_dir / f"{cls}.json"


def read_state(path: Path) -> Any:
    """상태 파일 파싱. 없으면 CliError(3), 깨졌으면 CliError(2)."""
    if not path.is_file():
        raise CliError(f"상태 파일이 없다: {path.as_posix()}", EXIT_NO_FILE)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - 권한 등 환경 의존
        raise CliError(f"상태 파일을 읽을 수 없다: {path.as_posix()}: {exc}") from exc
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise CliError(f"상태 파일 JSON 파싱 실패: {path.as_posix()}: {exc}") from exc


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


# ─────────────────────────── 출력 ───────────────────────────


def _emit(value: Any) -> None:
    """stdout에 JSON 한 덩이 — 기계 소비자(LLM)를 위한 유일한 출력 채널."""
    sys.stdout.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _note(message: str) -> None:
    sys.stderr.write(message + "\n")


# ─────────────────────────── 명령 ───────────────────────────


def _cmd_list(schemas: dict[str, dict], state_dir: Path, schemas_path: Path) -> int:
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
    _emit(
        {
            "schemas": schemas_path.as_posix(),
            "state_dir": state_dir.as_posix(),
            "classes": classes,
        }
    )
    return EXIT_OK


def _cmd_read(schemas: dict[str, dict], state_dir: Path, cls: str, field: str | None) -> int:
    schema = class_schema(schemas, cls)
    if field is not None:
        field_schema(schema, cls, field)  # 존재 검사 — 없으면 CliError(2)
    obj = read_state(state_path(state_dir, cls))
    if field is None:
        _emit(obj)
        return EXIT_OK
    if not isinstance(obj, dict):
        raise CliError(f"{cls}: 상태 파일 최상위가 JSON 객체가 아니다")
    _emit(obj.get(field))
    return EXIT_OK


def _cmd_init(schemas: dict[str, dict], state_dir: Path, cls: str, force: bool) -> int:
    schema = class_schema(schemas, cls)
    path = state_path(state_dir, cls)
    if path.exists() and not force:
        raise CliError(
            f"이미 존재한다: {path.as_posix()} (재생성하려면 --force)"
        )
    obj = initial_object(schema)
    violations = validate_object(obj, schema, cls)
    if violations:  # 스키마 자체가 초기 객체를 통과시키지 못하는 경우
        _report_violations(violations)
        return EXIT_INVALID
    write_state(path, obj)
    _note(f"생성: {path.as_posix()}")
    _emit(obj)
    return EXIT_OK


def _split_assignment(raw: str, option: str) -> tuple[str, str]:
    if "=" not in raw:
        raise CliError(f"{option} 값은 FIELD=VALUE 형식이어야 한다: {raw!r}")
    name, _, value = raw.partition("=")
    name = name.strip()
    if not name:
        raise CliError(f"{option} 값의 필드 이름이 비었다: {raw!r}")
    return name, value


def _apply_operations(
    obj: dict,
    schema: dict,
    cls: str,
    sets: list[str],
    appends: list[str],
    removes: list[str],
) -> None:
    """--set → --append → --remove 순으로 제자리 적용."""
    for raw in sets:
        name, value = _split_assignment(raw, "--set")
        prop = field_schema(schema, cls, name)
        where = f"{cls}.{name}"
        if _is_collection(prop):
            obj[name] = coerce_array(value, prop, where)
        else:
            obj[name] = coerce_scalar(value, prop, where)
    for raw in appends:
        name, value = _split_assignment(raw, "--append")
        prop = field_schema(schema, cls, name)
        where = f"{cls}.{name}"
        _require_collection(prop, where, "--append")
        current = obj.get(name)
        if not isinstance(current, list):
            current = []
        element = coerce_scalar(value, _items_schema(prop), where)
        current = list(current) + [element]
        obj[name] = _dedupe(current) if _unique_items(prop) else current
    for raw in removes:
        name, value = _split_assignment(raw, "--remove")
        prop = field_schema(schema, cls, name)
        where = f"{cls}.{name}"
        _require_collection(prop, where, "--remove")
        current = obj.get(name)
        if not isinstance(current, list):
            # 제거는 없는 것을 만들지 않는다 — 키가 없으면 그대로 없고, 리스트가
            # 아닌 값(스키마 위반)은 손대지 않는다(빈 배열로 덮으면 고장을 조용히
            # 지운다. 그 위반은 아래 검증 게이트가 잡아 쓰기를 막는다).
            coerce_scalar(value, _items_schema(prop), where)  # 값 형식은 여전히 검사
            continue
        element = coerce_scalar(value, _items_schema(prop), where)
        # 원소 단위 제거 — 같은 값이 여러 번 있으면 전부 없앤다
        # ("--remove f=v 이후 v는 f에 없다"가 기대 동작이다).
        obj[name] = [
            item
            for item in current
            if not (item == element and type(item) is type(element))
        ]


def _require_collection(prop: dict, where: str, option: str) -> None:
    if not _is_collection(prop):
        raise CliError(
            f"{where}: {option}는 컬렉션 필드에만 쓸 수 있다 "
            f"(이 필드는 {_json_type(prop) or 'any'}) — --set 을 쓰라"
        )


def _cmd_write(
    schemas: dict[str, dict],
    state_dir: Path,
    cls: str,
    sets: list[str],
    appends: list[str],
    removes: list[str],
) -> int:
    schema = class_schema(schemas, cls)
    if not (sets or appends or removes):
        raise CliError("--set / --append / --remove 중 최소 하나가 필요하다")
    path = state_path(state_dir, cls)
    if path.is_file():
        obj = read_state(path)
        if not isinstance(obj, dict):
            raise CliError(f"{cls}: 상태 파일 최상위가 JSON 객체가 아니다: {path.as_posix()}")
        obj = dict(obj)
    else:
        obj = initial_object(schema)
    _apply_operations(obj, schema, cls, sets, appends, removes)
    violations = validate_object(obj, schema, cls)
    if violations:
        _report_violations(violations)
        _note(f"쓰지 않았다 — {path.as_posix()}는 그대로다.")
        return EXIT_INVALID
    write_state(path, obj)
    _emit(obj)
    return EXIT_OK


def _report_violations(violations: list[str]) -> None:
    _note("검증 실패:")
    for line in violations:
        _note(f"  - {line}")


def _cmd_validate(schemas: dict[str, dict], state_dir: Path, names: list[str]) -> int:
    """상태 파일 검증.

    이름을 생략한 전 클래스 순회에서 상태 파일 부재는 고장이 아니다(아직
    초기화되지 않았을 뿐) — ``missing``으로 보고하고 exit 0. 반면 **이름을
    명시한** 호출에서 그 파일이 없으면 exit 3(``read``와 같은 뜻)이다. 물어본
    대상이 없다는 것 자체가 대답이고, exit code만 보는 호출자가 "검사했고
    정상"으로 오해하면 안 된다. 위반이 있으면 그쪽이 우선(exit 1).
    """
    if names:
        for name in names:
            class_schema(schemas, name)  # 존재 검사
            if name == PROGRESS_CLASS:
                raise CliError(
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
        except CliError as exc:
            violations.append(f"{name}: {exc.message}")
            checked.append(name)
            continue
        checked.append(name)
        violations.extend(validate_object(obj, schemas[name], name))

    result = {
        "ok": not violations,
        "checked": checked,
        "missing": missing,
        "violations": violations,
    }
    if violations:
        _report_violations(violations)
    if missing:
        _note("상태 파일 없음(검증 생략): " + ", ".join(missing))
        if names:
            _note(
                "지정한 클래스의 상태 파일이 없다 — 먼저 "
                f"'daedalus-bb init {missing[0]}' 로 만들라."
            )
    _emit(result)
    if violations:
        return EXIT_INVALID
    if names and missing:
        return EXIT_NO_FILE
    return EXIT_OK


# ─────────────────────────── 진입점 ───────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="daedalus-bb",
        description="Daedalus 블랙보드 상태 파일(state/) 읽기·쓰기·검증 CLI.",
    )
    parser.add_argument(
        "--state-dir",
        default=DEFAULT_STATE_DIR,
        metavar="DIR",
        help=f"상태 파일 폴더 (기본: {DEFAULT_STATE_DIR})",
    )
    parser.add_argument(
        "--schemas",
        default=DEFAULT_SCHEMAS,
        metavar="PATH",
        help=f"블랙보드 스키마 파일 (기본: {DEFAULT_SCHEMAS})",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>", required=True)

    read_p = sub.add_parser("read", help="상태 파일 전체 또는 필드 값 출력")
    read_p.add_argument("cls", metavar="Class")
    read_p.add_argument("--field", metavar="NAME", default=None)

    init_p = sub.add_parser("init", help="스키마 기반 초기 객체 생성")
    init_p.add_argument("cls", metavar="Class")
    init_p.add_argument("--force", action="store_true", help="이미 있어도 재생성")

    write_p = sub.add_parser("write", help="읽기-수정-쓰기 (검증 통과 시에만 기록)")
    write_p.add_argument("cls", metavar="Class")
    write_p.add_argument(
        "--set", dest="sets", action="append", default=[], metavar="FIELD=VALUE"
    )
    write_p.add_argument(
        "--append", dest="appends", action="append", default=[], metavar="FIELD=VALUE"
    )
    write_p.add_argument(
        "--remove", dest="removes", action="append", default=[], metavar="FIELD=VALUE"
    )

    validate_p = sub.add_parser("validate", help="상태 파일 검증 (생략 시 전 클래스)")
    validate_p.add_argument("classes", nargs="*", metavar="Class")

    sub.add_parser("list", help="스키마의 클래스·필드 목록")
    return parser


def _dispatch(args: argparse.Namespace) -> int:
    schemas_path = Path(args.schemas)
    state_dir = Path(args.state_dir)
    schemas = load_schemas(schemas_path)

    if args.command == "list":
        return _cmd_list(schemas, state_dir, schemas_path)
    if args.command == "read":
        return _cmd_read(schemas, state_dir, args.cls, args.field)
    if args.command == "init":
        return _cmd_init(schemas, state_dir, args.cls, args.force)
    if args.command == "write":
        return _cmd_write(
            schemas, state_dir, args.cls, args.sets, args.appends, args.removes
        )
    if args.command == "validate":
        return _cmd_validate(schemas, state_dir, args.classes)
    raise CliError(f"알 수 없는 명령: {args.command}")  # pragma: no cover


def _force_utf8_streams() -> None:
    """stdout/stderr를 UTF-8로 고정한다.

    Windows에서 파이프로 넘길 때 Python은 로케일 인코딩(cp949 등)을 쓰는데,
    이 CLI의 출력을 읽는 쪽(CC/LLM)은 UTF-8로 읽는다 — 그대로 두면 한국어
    진단 메시지가 깨진 바이트로 전달된다. 테스트의 capsys처럼 reconfigure를
    갖지 않는 스트림도 있으므로 조용히 넘어간다.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):  # pragma: no cover - 환경 의존
            pass


def main(argv: list[str] | None = None) -> int:
    """``daedalus-bb`` 진입점 — 반환값이 그대로 exit code."""
    _force_utf8_streams()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse의 --help(0) / 사용법 오류(2)
        return int(exc.code or 0)
    try:
        return _dispatch(args)
    except CliError as exc:
        _note(exc.message)
        return exc.code
    except OSError as exc:
        _note(f"입출력 오류: {exc}")
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
