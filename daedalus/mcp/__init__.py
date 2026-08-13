"""앱 내장 MCP 서버 (WP-MCP) — Claude Code와의 협업 창구.

Daedalus GUI가 켜지면 함께 뜨는 Streamable HTTP MCP 서버다. 다른 MCP 서버와
결이 다른 점: **CC가 쓰는 도구 모음이 아니라, 사람이 GUI에서 작업하는 중에 CC가
같은 프로젝트를 함께 보고 함께 만지는 통로**다. 그래서

- CC는 사용자가 지금 무엇을 선택하고 있는지(`get_selection`) 알 수 있고,
- CC의 편집은 사용자의 undo 스택에 들어가 Ctrl+Z로 되돌릴 수 있으며,
- 스크립트 리스너에 CC가 한 일이 사람 편집과 같은 형식으로 남는다.

모듈 구성:

- ``endpoint``  — 접속 정보 파일(``~/.daedalus/mcp-endpoint.json``). Qt 무관.
- ``invoker``   — 워커 스레드 → Qt 메인 스레드 마샬링. Qt 의존.
- ``tools``     — 도구 구현. MainWindow/모델을 다룬다.
- ``service``   — MCPServer 구성 + uvicorn 스레드 수명주기.
"""
