# AgentAgora — Blackboard MCP Server Design

독립 에이전트(Claude, Codex 등)가 공통으로 참조 가능한 런타임 상태 저장소.
Streamable HTTPS 기반 MCP 서버로, localhost에서만 접속 가능.

## 핵심 개념

- **서버 인스턴스 = 세션** — 워크플로우마다 서버를 기동하고, 참여 에이전트에게 포트 번호를 공유하여 같은 상태를 공유한다.
- **스키마 기반 Closed 모드** — 서버 시작 시 `.agentagora/schemas.json`에서 스키마를 로드. 미등록 스키마에 대한 쓰기는 전부 거부.
- **스키마 → 키 → 값** — 스키마는 타입 정의, 키는 그 타입의 인스턴스, 값은 스키마에 대해 검증된 JSON 데이터.
- **인메모리 + 파일 백업** — 읽기는 메모리에서 즉시 반환. 쓰기 시 해당 스키마의 JSON 파일로 동시 직렬화. 서버 재시작 시 파일에서 복구.
- **Enqueue 방식** — 모든 쓰기(set, append, delete)는 큐를 통해 순차 처리. 동시 쓰기 충돌 없음.

## Daedalus와의 관계

```
[Daedalus 에디터]
  │ Blackboard UI에서 DynamicClass/Variable 스키마 정의
  ↓
[Compiler]
  │ .agentagora/schemas.json 생성
  │ 스킬 본문에 "agora/set {schema, key, value}" 지시문 생성
  │ MCP 서버 연결 설정 생성
  ↓
[AgentAgora MCP Server]   ← 이 문서의 대상
  │ .agentagora/ 폴더에서 스키마 로드 + 데이터 파일 관리
  ↓
[에이전트들] Claude, Codex 등이 MCP 도구로 read/write
```

- Daedalus의 Blackboard UI는 설계 시점 스키마 정의 도구.
- Compiler가 스키마 파일을 생성하고 스킬에 사용 지시문을 삽입.
- 이 MCP 서버는 스키마를 로드하여 값을 검증하는 런타임 저장소.

## 데이터 디렉토리 구조

작업 디렉토리의 `.agentagora/` 폴더가 서버의 데이터 루트.

```
project/
└── .agentagora/
    ├── schemas.json           # 스키마 정의 (서버 시작 시 로드, 런타임 불변)
    ├── finding.json           # "finding" 스키마의 키-값 데이터
    ├── review_status.json     # "review_status" 스키마의 키-값 데이터
    └── ...                    # 스키마당 하나씩 자동 생성
```

- 서버 시작 시 `schemas.json` 로드 + 기존 `<schema_name>.json` 파일들 복구.
- 쓰기 시 해당 스키마 파일만 직렬화 — 다른 스키마 데이터에 영향 없음.
- **예약어:** 스키마 이름으로 `schemas` 사용 불가 (`schemas.json`과 충돌 방지).

### schemas.json 예시

```json
{
  "finding": {
    "type": "object",
    "properties": {
      "file": { "type": "string" },
      "line": { "type": "integer" },
      "severity": { "type": "string", "enum": ["low", "medium", "high"] },
      "message": { "type": "string" }
    },
    "required": ["file", "line", "severity"]
  },
  "review_status": {
    "type": "string",
    "enum": ["pending", "in_progress", "complete"]
  }
}
```

### 데이터 파일 예시 (finding.json)

```json
{
  "auth_findings": [
    {"file": "src/auth.py", "line": 42, "severity": "high", "message": "SQL injection"}
  ],
  "api_findings": [
    {"file": "src/api.py", "line": 10, "severity": "medium", "message": "Missing validation"}
  ]
}
```

## 서버 아키텍처

### 전송

- **프로토콜:** MCP over Streamable HTTPS
- **바인딩:** `127.0.0.1` (localhost only)
- **포트:** 기동 시 지정 (CLI 인수로 오버라이드 가능)

### 인증서

- 자체 서명 인증서 자동 생성 (`cryptography` 라이브러리)
- 서버 첫 시작 시 생성, 이후 재사용
- 저장 위치: `~/.agent-agora/certs/`
- 클라이언트는 자체 서명 인증서 신뢰 설정 또는 검증 스킵 필요

### 쓰기 큐

모든 쓰기 연산(set, append, delete)은 큐에 enqueue되어 순차 처리.

```
에이전트 A: agora/set →┐
에이전트 B: agora/set →┤→ [큐] → 순차 처리 → 메모리 반영 + 파일 직렬화
에이전트 C: agora/append →┘
```

- 동시 쓰기 충돌이 구조적으로 불가능.
- 읽기(get, list, info)는 큐를 거치지 않고 메모리에서 즉시 반환.
- 도구별 `wait` 파라미터로 동기/비동기 응답 선택 가능.

### 저장소 경로

```
write: 큐에서 꺼냄 → 스키마 검증 → 메모리 dict 업데이트 → <schema_name>.json 덮어쓰기
read:  메모리 dict에서 즉시 반환
start: schemas.json 로드 → 각 <schema_name>.json 존재하면 메모리 복구
```

## MCP 도구 정의

6개의 고정 도구.

### `agora/info`

서버 메타 정보를 반환한다.

```json
{
  "name": "agora/info",
  "description": "Return AgentAgora server metadata: data directory path, port, registered schemas, uptime.",
  "inputSchema": {
    "type": "object",
    "properties": {}
  }
}
```

**응답 예시:**

```json
{
  "path": "C:/Users/Jooyo/source/MyProject/.agentagora",
  "port": 8420,
  "schemas": ["finding", "review_status"],
  "uptime": 3600
}
```

### `agora/set`

스키마의 키에 값을 저장한다. 기존 키가 있으면 덮어쓴다. 값은 스키마에 대해 검증된다.

```json
{
  "name": "agora/set",
  "description": "Store a value under a schema key. Value is validated against the registered JSON Schema. Overwrites if key exists.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "schema": { "type": "string", "description": "Registered schema name" },
      "key": { "type": "string", "description": "Storage key within the schema" },
      "value": { "description": "JSON value, validated against the schema" },
      "wait": { "type": "boolean", "description": "Wait for write to complete", "default": true }
    },
    "required": ["schema", "key", "value"]
  }
}
```

**동작:** 스키마 존재 확인 → 값 스키마 검증 → 큐에 enqueue → (wait=true면 처리 완료 대기) → 응답.

**에러:**
- 미등록 스키마 → 거부
- 스키마 검증 실패 → 거부 (검증 오류 메시지 포함)

### `agora/get`

스키마의 키 값을 반환한다.

```json
{
  "name": "agora/get",
  "description": "Retrieve a value by schema and key.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "schema": { "type": "string", "description": "Registered schema name" },
      "key": { "type": "string", "description": "Storage key within the schema" }
    },
    "required": ["schema", "key"]
  }
}
```

**동작:** 메모리에서 즉시 조회 → 값 반환. 키 없으면 `null` 반환.

**에러:**
- 미등록 스키마 → 거부

### `agora/append`

리스트 타입 값에 항목을 추가한다.

```json
{
  "name": "agora/append",
  "description": "Append an item to a list value. The existing value must be an array. The appended item is validated against the schema's items definition.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "schema": { "type": "string", "description": "Registered schema name" },
      "key": { "type": "string", "description": "Storage key within the schema" },
      "value": { "description": "Item to append (validated against schema items)" },
      "wait": { "type": "boolean", "description": "Wait for write to complete", "default": false }
    },
    "required": ["schema", "key", "value"]
  }
}
```

**동작:** 스키마 존재 확인 → 기존 값이 리스트인지 확인 → 항목 스키마 검증 → 큐에 enqueue → 응답.

**에러:**
- 미등록 스키마 → 거부
- 기존 값이 리스트가 아님 → 거부
- 키가 없으면 → 새 리스트 `[value]`로 생성
- 항목 스키마 검증 실패 → 거부

### `agora/delete`

스키마의 키를 삭제한다. 스키마 정의는 유지된다.

```json
{
  "name": "agora/delete",
  "description": "Remove a key from a schema. The schema definition is preserved.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "schema": { "type": "string", "description": "Registered schema name" },
      "key": { "type": "string", "description": "Storage key to remove" },
      "wait": { "type": "boolean", "description": "Wait for write to complete", "default": true }
    },
    "required": ["schema", "key"]
  }
}
```

**동작:** 큐에 enqueue → 메모리에서 삭제 → 파일 직렬화 → 응답. 키 없어도 에러 아님.

### `agora/list`

등록된 스키마 목록 또는 특정 스키마의 키 목록을 반환한다.

```json
{
  "name": "agora/list",
  "description": "List registered schemas, or list keys within a specific schema.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "schema": { "type": "string", "description": "Schema name. If omitted, returns all schema names." }
    }
  }
}
```

**응답 예시 (스키마 생략):**
```json
{ "schemas": ["finding", "review_status"] }
```

**응답 예시 (스키마 지정):**
```json
{ "schema": "finding", "keys": ["auth_findings", "api_findings"] }
```

## 서버 CLI

```bash
# .agentagora/ 가 있는 디렉토리에서 실행
agent-agora --port 8420

# 작업 디렉토리 지정
agent-agora --port 8420 --dir /path/to/project
```

### CLI 인수

| 인수 | 기본값 | 설명 |
|------|--------|------|
| `--port` | 자동 할당 | HTTPS 포트 번호 |
| `--dir` | `.` (현재 디렉토리) | `.agentagora/` 폴더를 찾을 작업 디렉토리 |
| `--cert-dir` | `~/.agent-agora/certs/` | 인증서 저장 디렉토리 |

### 시작 절차

1. `--dir`에서 `.agentagora/` 폴더 탐색 → 없으면 에러 종료
2. `.agentagora/schemas.json` 로드 → 없거나 비어있으면 에러 종료
3. 스키마 이름 검증 (`schemas` 예약어 검사)
4. 각 `<schema_name>.json` 존재하면 메모리 복구
5. 인증서 로드 또는 자동 생성
6. HTTPS 서버 시작, 포트 번호 stdout 출력

## 프로젝트 구조

Daedalus와 독립된 별도 패키지.

```
agent-agora/
├── pyproject.toml
├── src/
│   └── agent_agora/
│       ├── __init__.py
│       ├── __main__.py      # CLI 엔트리포인트
│       ├── server.py         # MCP 서버 + 도구 핸들러
│       ├── store.py          # 인메모리 저장소 + JSON 직렬화 + 쓰기 큐
│       ├── schema.py         # 스키마 로드 + JSON Schema 검증
│       └── certs.py          # 자체 서명 인증서 생성/관리
└── tests/
    ├── test_store.py
    ├── test_schema.py
    ├── test_server.py
    └── test_certs.py
```

### 의존성

```toml
[project]
name = "agent-agora"
requires-python = ">=3.12"
dependencies = [
    "mcp>=1.0",              # MCP Python SDK
    "cryptography>=42",       # 자체 서명 인증서 생성
    "jsonschema>=4.20",       # JSON Schema 검증
]

[project.scripts]
agent-agora = "agent_agora.__main__:main"
```

## 에이전트 연결 예시

Compiler가 생성할 MCP 서버 설정:

```json
{
  "mcpServers": {
    "agent-agora": {
      "url": "https://127.0.0.1:8420/mcp",
      "transport": "streamable-http"
    }
  }
}
```

에이전트(스킬 본문)에서의 사용:

```markdown
## AgentAgora 연결

이 워크플로우는 `https://127.0.0.1:8420`의 AgentAgora 서버를 사용합니다.

- 서버 정보: `agora/info {}`
- 분석 결과 저장: `agora/set {schema: "finding", key: "auth_findings", value: [...]}`
- 결과 읽기: `agora/get {schema: "finding", key: "auth_findings"}`
- 결과 추가: `agora/append {schema: "finding", key: "auth_findings", value: {...}}`
- 키 삭제: `agora/delete {schema: "finding", key: "auth_findings"}`
- 목록 확인: `agora/list {schema: "finding"}`
```

## 미결 사항

- **인증서 신뢰:** 클라이언트별 자체 서명 인증서 신뢰 설정 방법 (Claude Code, Codex 등)
- **TTL / 만료:** 키별 자동 만료 필요 여부
- **대용량 값:** value 크기 제한 필요 여부
