# 벤더링된 CC 규격 스냅샷 (A4 — 스펙 드리프트 감시)

이 폴더는 **Claude Code 규격의 외부 정본을 저장소 안에 고정한 스냅샷**이다.
`daedalus/model/plugin/hook.py`의 `HookEvent` 31종·`NO_MATCHER_EVENTS`·핸들러
`to_json` 키는 전부 이 규격을 손으로 옮겨 적은 것이고, 상류가 바뀌어도 아무 신호가
나지 않는 것이 이 프로젝트의 최대 유지 부채였다. **틀린 emit은 도구가 없는 것보다
나쁘다 — 조용히 실패하기 때문이다.** 스냅샷과 코드를 대조하는 테스트
(`tests/model/plugin/test_spec_drift.py`)가 그 침묵을 깬다.

## 파일

| 파일 | 출처 | 받은 날짜 |
|------|------|-----------|
| `claude-code-settings.json` | <https://json.schemastore.org/claude-code-settings.json> | 2026-09-06 |

- 받은 그대로의 **원본 바이트**다(가공·발췌 없음). 크기 230,217 B, LF 줄바꿈,
  받은 시점 sha256 `6d4a6e3c7adedffce8079ccaef0a4bab5f5718b054421b4475c788a0ae4bedfe`.
  이 해시는 출처 기록용이지 테스트 단언이 아니다 — git이 체크아웃 시 줄바꿈을
  정규화하면 바이트가 달라질 수 있고, 대조는 **파싱된 구조**로 한다.
- 이 스키마가 정본인 이유: CC 공식 문서에는 훅의 전체 형식이 나오지 않는다
  (`hook.py` 모듈 docstring 참조).

## 테스트는 네트워크에 나가지 않는다

`test_spec_drift.py`는 이 폴더의 파일만 읽는다. 오프라인에서도 초록이어야 하고,
상류가 바뀌었다고 CI가 저절로 빨개지지도 않는다 — 빨개지는 시점은 **사람이
스냅샷을 갱신했을 때**다. 그게 요점이다: 갱신이 곧 리뷰 지점이 된다.

## 갱신 절차

```bash
# 1) 상류와 무엇이 달라졌는지만 본다 (파일은 건드리지 않는다)
python scripts/refresh_cc_schema.py

# 2) 확인했으면 스냅샷을 덮어쓴다
python scripts/refresh_cc_schema.py --write

# 3) 대조 테스트를 돌려 코드가 새 규격과 어긋나는지 본다
python -m pytest tests/model/plugin/test_spec_drift.py -v
```

`--write` 없이 돌리면 상류를 받아 현재 스냅샷과 **구조 diff**만 출력한다:
훅 이벤트 키의 추가/삭제/순서 변경, matcher 미지원 집합의 변화,
`$defs.hookCommand` 각 변종의 속성 변화. `git diff`로 원본 diff를 보는 것과
함께 쓰라 — 스크립트 쪽은 "우리 코드에 영향이 가는 축"만 추려 보여 준다.

3단계에서 실패가 나오면 그것이 **진짜 드리프트**다. 테스트를 느슨하게 고치지 말고
`hook.py`(그리고 필요하면 `view/widgets/lifecycle_picker.py`의 `_LAYOUT`,
컴파일러의 훅 배출)를 새 규격에 맞춰라. 위 표의 날짜도 같은 커밋에서 갱신한다.
