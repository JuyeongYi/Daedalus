"""블랙보드 런타임 표면 (``daedalus-bb``) — WP-RF-2 신설, WP-BB1·WP-BM 구현.

C+A 설계: ``uv tool install``로 앱과 이 실행 파일이 **함께 설치**되는 단일 배포를
전제로 하고, 컴파일 산출(스킬/에이전트 본문의 블랙보드 지시)이 런타임에 work
폴더의 ``state/`` 파일을 읽고 쓴다.

- :mod:`daedalus.cli.core` — 판정의 실체(스키마 로드·검증·코어션·원자적 쓰기·
  낙관적 잠금). 출력 채널이 없고 실패는 ``BlackboardError``다.
- :mod:`daedalus.cli.progress` — 진행 상태 파일(``state/__progress__.json``),
  같은 규약.
- :mod:`daedalus.cli.mcp_server` — **모델이 접하는 유일한 표면**. stdio MCP
  서버이고 도구 7개가 코어 함수와 1:1이다. pyproject의 ``[project.scripts]``가
  ``daedalus-bb``를 여기로 건다.

종전 argparse CLI(``blackboard.py``)는 WP-BM에서 폐기됐다 — 같은 조작을 두
표면이 제공하면 산출 문서가 어느 쪽을 가리킬지 정해야 하고, 셸 따옴표·exit
code 해석 계층이 그대로 남는다. 패키지 이름 ``cli``는 유지한다(임포트 계약
테스트가 그 경로를 본다). 개명은 ``docs/backlog.md`` 항목이다.

이 패키지는 core 경계에 속한다: PySide6·daedalus.view·MCP SDK(mcp)·uvicorn
임포트 금지 (tests/test_import_contracts.py가 AST 기준으로 강제). SDK 버전
흡수는 :mod:`daedalus.mcp_compat`(core 밖) 한 곳에 모여 있어 이 제약이
MCP 서버를 내면서도 그대로 산다. CLI는 여기에 더해 **daedalus.model도
임포트하지 않는다** — 설치 대상 프로젝트에서 도는 코드에게 검증의 단일
진실은 컴파일 산출물 ``schemas/<플러그인>.json`` 뿐이다.
"""
