"""블랙보드 CLI (``daedalus-bb``) — WP-RF-2 신설, WP-BB1 구현.

C+A 설계: ``uv tool install``로 앱과 CLI가 **함께 설치**되는 단일 배포를
전제로 하고, 컴파일 산출(스킬/에이전트 본문의 블랙보드 지시)이 런타임에 이
CLI를 호출해 work 폴더의 ``state/`` 파일을 읽고 쓴다.

구현은 :mod:`daedalus.cli.blackboard`이고 pyproject의 ``[project.scripts]``에
``daedalus-bb = "daedalus.cli.blackboard:main"``으로 등록돼 있다.

이 패키지는 core 경계에 속한다: PySide6·daedalus.view·MCP SDK(mcp)·uvicorn
임포트 금지 (tests/test_import_contracts.py가 AST 기준으로 강제). CLI는 여기에
더해 **daedalus.model도 임포트하지 않는다** — 설치 대상 프로젝트에서 도는
CLI에게 검증의 단일 진실은 컴파일 산출물 ``schemas/schemas.json`` 뿐이다.
"""
