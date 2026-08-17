"""블랙보드 CLI(``daedalus-bb``)가 들어올 자리 (WP-RF-2 신설, 아직 빈 패키지).

C+A 설계: ``uv tool install``로 앱과 CLI가 **함께 설치**되는 단일 배포를
전제로 하고, 컴파일 산출(스킬/에이전트 본문의 블랙보드 지시)이 런타임에 이
CLI를 호출해 work 폴더의 ``state/`` 파일을 읽고 쓴다.

pyproject의 ``[project.scripts]``에는 아직 등록하지 않는다 — 실존하지 않는
entry point는 설치를 깨뜨린다. CLI 구현 시점에 ``daedalus-bb``를 등록한다.

이 패키지는 core 경계에 속한다: PySide6·daedalus.view·MCP SDK(mcp)·uvicorn
임포트 금지 (tests/test_import_contracts.py가 AST 기준으로 강제).
"""
