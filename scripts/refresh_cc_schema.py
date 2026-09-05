#!/usr/bin/env python
"""벤더링된 CC 설정 스키마 스냅샷 갱신 (A4 — 스펙 드리프트 감시).

`tests/fixtures/specs/claude-code-settings.json`은 SchemaStore의
`claude-code-settings.json`을 그대로 떠 둔 것이고, 우리 훅 모델
(`HookEvent` / `NO_MATCHER_EVENTS` / 핸들러 `to_json` 키)이 그것과 어긋나지
않는지를 `tests/model/plugin/test_spec_drift.py`가 대조한다.

테스트는 네트워크에 나가지 않는다 — 상류를 받아오는 것은 **이 스크립트뿐**이다.
그래서 갱신이 곧 사람이 보는 리뷰 지점이 된다.

    python scripts/refresh_cc_schema.py            # 구조 diff만 출력 (파일 불변)
    python scripts/refresh_cc_schema.py --write    # 스냅샷 덮어쓰기
    python scripts/refresh_cc_schema.py --url URL  # 다른 출처 지정

종료 코드: 0 = 차이 없음 / 1 = 차이 있음(--write면 갱신 완료) / 2 = 오류.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_URL = "https://json.schemastore.org/claude-code-settings.json"
SNAPSHOT = (
    Path(__file__).resolve().parent.parent
    / "tests" / "fixtures" / "specs" / "claude-code-settings.json"
)

# 상류 description이 "matcher를 받지 않는다"고 말하는 표현들.
# test_spec_drift.py와 같은 문구 목록이어야 한다(양쪽이 같은 판정을 해야
# 스크립트의 diff가 테스트의 실패와 일치한다).
NO_MATCHER_PHRASES = (
    "does not support matchers",
    "matchers are ignored",
    "no matchers",
)


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
        return response.read()


def hook_events(schema: dict[str, Any]) -> list[str]:
    return list(schema["properties"]["hooks"]["properties"].keys())


def no_matcher_events(schema: dict[str, Any]) -> set[str]:
    props = schema["properties"]["hooks"]["properties"]
    return {
        name
        for name, node in props.items()
        if any(p in node.get("description", "").lower() for p in NO_MATCHER_PHRASES)
    }


def handler_variants(schema: dict[str, Any]) -> dict[str, set[str]]:
    """`$defs.hookCommand`의 변종 → 허용 속성 집합 (`type` const가 키)."""
    out: dict[str, set[str]] = {}
    for variant in schema["$defs"]["hookCommand"]["anyOf"]:
        props = variant.get("properties", {})
        type_node = props.get("type", {})
        tag = type_node.get("const")
        if tag is None:
            enum = type_node.get("enum") or []
            tag = enum[0] if enum else "?"
        out[tag] = set(props.keys())
    return out


def _report_set(label: str, old: set[str], new: set[str]) -> bool:
    added, removed = sorted(new - old), sorted(old - new)
    if not added and not removed:
        print(f"  {label}: 변화 없음 ({len(new)}개)")
        return False
    print(f"  {label}:")
    for name in added:
        print(f"    + {name}")
    for name in removed:
        print(f"    - {name}")
    return True


def diff(old: dict[str, Any], new: dict[str, Any]) -> bool:
    """우리 코드에 영향이 가는 축만 추려 출력. 차이가 있으면 True."""
    changed = False

    print("훅 이벤트 (properties.hooks):")
    old_events, new_events = hook_events(old), hook_events(new)
    changed |= _report_set("키 집합", set(old_events), set(new_events))
    if set(old_events) == set(new_events) and old_events != new_events:
        print("  ! 선언 순서가 바뀌었다 — hooks.json 이벤트 키 순서가 따라간다")
        changed = True

    print("matcher 미지원 이벤트:")
    changed |= _report_set("집합", no_matcher_events(old), no_matcher_events(new))

    print("핸들러 변종 ($defs.hookCommand):")
    old_v, new_v = handler_variants(old), handler_variants(new)
    changed |= _report_set("타입", set(old_v), set(new_v))
    for tag in sorted(set(old_v) & set(new_v)):
        changed |= _report_set(f"{tag} 속성", old_v[tag], new_v[tag])

    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--write", action="store_true", help="스냅샷을 덮어쓴다")
    args = parser.parse_args(argv)

    try:
        raw = fetch(args.url)
    except Exception as exc:  # noqa: BLE001 — 네트워크 실패는 사용법 오류로 보고
        print(f"다운로드 실패: {exc}", file=sys.stderr)
        return 2

    try:
        new = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"받은 내용이 JSON이 아니다: {exc}", file=sys.stderr)
        return 2

    old = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    changed = diff(old, new)

    if args.write:
        # 받은 원본 바이트를 그대로 쓴다 — 재직렬화하면 상류와의 `git diff`가
        # 무의미해진다(키 순서·들여쓰기가 우리 것으로 바뀐다).
        SNAPSHOT.write_bytes(raw)
        print(f"\n갱신: {SNAPSHOT} ({len(raw):,} B)")
        print("→ tests/fixtures/specs/README.md의 날짜·해시를 같이 고치고,")
        print("  python -m pytest tests/model/plugin/test_spec_drift.py -v 를 돌려라.")
    elif changed:
        print("\n(파일은 건드리지 않았다 — 반영하려면 --write)")
    else:
        print("\n스냅샷이 상류와 같다.")

    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
