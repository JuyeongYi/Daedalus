# AgentAgora Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 독립 에이전트 간 공유 상태 저장소인 AgentAgora MCP 서버를 구현한다.

**Architecture:** FastMCP 기반 Streamable HTTPS 서버. 스키마 기반 closed 모드로 `.agentagora/schemas.json`에서 JSON Schema를 로드하고, 스키마별 데이터 파일로 영속화. 모든 쓰기는 asyncio.Queue로 순차 처리.

**Tech Stack:** Python 3.12+, mcp (FastMCP), cryptography, jsonschema, uvicorn, pytest

**Spec:** `docs/superpowers/specs/2026-04-17-blackboard-mcp-server-design.md`

**Project root:** Daedalus 와 독립된 별도 저장소. `uv tool install .` 로 설치 가능.

---

## File Structure

```
agent-agora/
├── pyproject.toml               # 패키지 설정, [project.scripts] 엔트리포인트
├── src/
│   └── agent_agora/
│       ├── __init__.py          # 버전 정보
│       ├── __main__.py          # CLI 엔트리포인트 (argparse + 서버 기동)
│       ├── schema.py            # SchemaRegistry: schemas.json 로드 + JSON Schema 검증
│       ├── store.py             # AgoraStore: 인메모리 저장소 + JSON 직렬화 + 쓰기 큐
│       ├── server.py            # FastMCP 서버 + 6개 도구 핸들러
│       └── certs.py             # 자체 서명 인증서 생성/관리
└── tests/
    ├── conftest.py              # 공용 fixture (tmp .agentagora 디렉토리)
    ├── test_schema.py           # SchemaRegistry 단위 테스트
    ├── test_store.py            # AgoraStore 단위 테스트
    ├── test_certs.py            # 인증서 생성 테스트
    └── test_server.py           # MCP 도구 핸들러 통합 테스트
```

---

### Task 1: 프로젝트 스캐폴딩

**Files:**
- Create: `agent-agora/pyproject.toml`
- Create: `agent-agora/src/agent_agora/__init__.py`
- Create: `agent-agora/tests/__init__.py`

- [ ] **Step 1: 프로젝트 디렉토리 생성**

```bash
mkdir -p agent-agora/src/agent_agora
mkdir -p agent-agora/tests
```

- [ ] **Step 2: pyproject.toml 작성**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "agent-agora"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "mcp>=1.0",
    "cryptography>=42",
    "jsonschema>=4.20",
    "uvicorn>=0.30",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24"]

[project.scripts]
agent-agora = "agent_agora.__main__:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 3: __init__.py 작성**

```python
# src/agent_agora/__init__.py
__version__ = "0.1.0"
```

```python
# tests/__init__.py
```

- [ ] **Step 4: 개발 모드 설치 및 확인**

```bash
cd agent-agora
pip install -e ".[dev]"
python -c "import agent_agora; print(agent_agora.__version__)"
```

Expected: `0.1.0`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/ tests/
git commit -m "feat: project scaffolding for AgentAgora MCP server"
```

---

### Task 2: SchemaRegistry — 스키마 로드 및 검증

**Files:**
- Create: `agent-agora/src/agent_agora/schema.py`
- Create: `agent-agora/tests/test_schema.py`
- Create: `agent-agora/tests/conftest.py`

- [ ] **Step 1: conftest.py — 공용 fixture 작성**

```python
# tests/conftest.py
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def agora_dir(tmp_path: Path) -> Path:
    """임시 .agentagora 디렉토리를 생성하고 반환한다."""
    d = tmp_path / ".agentagora"
    d.mkdir()
    return d


@pytest.fixture
def sample_schemas() -> dict:
    """테스트용 스키마 정의."""
    return {
        "finding": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "line": {"type": "integer"},
                "severity": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["file", "line", "severity"],
        },
        "status": {
            "type": "string",
            "enum": ["pending", "in_progress", "complete"],
        },
    }


@pytest.fixture
def agora_dir_with_schemas(agora_dir: Path, sample_schemas: dict) -> Path:
    """schemas.json이 포함된 .agentagora 디렉토리."""
    (agora_dir / "schemas.json").write_text(json.dumps(sample_schemas))
    return agora_dir
```

- [ ] **Step 2: 실패하는 테스트 작성**

```python
# tests/test_schema.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_agora.schema import SchemaRegistry


class TestSchemaRegistryLoad:
    def test_load_from_valid_dir(self, agora_dir_with_schemas: Path) -> None:
        reg = SchemaRegistry.load(agora_dir_with_schemas)
        assert reg.names() == {"finding", "status"}

    def test_missing_schemas_json(self, agora_dir: Path) -> None:
        with pytest.raises(FileNotFoundError):
            SchemaRegistry.load(agora_dir)

    def test_empty_schemas_json(self, agora_dir: Path) -> None:
        (agora_dir / "schemas.json").write_text("{}")
        with pytest.raises(ValueError, match="empty"):
            SchemaRegistry.load(agora_dir)

    def test_reserved_name_schemas(self, agora_dir: Path) -> None:
        schemas = {"schemas": {"type": "string"}}
        (agora_dir / "schemas.json").write_text(json.dumps(schemas))
        with pytest.raises(ValueError, match="reserved"):
            SchemaRegistry.load(agora_dir)


class TestSchemaRegistryValidation:
    def test_validate_valid_value(self, agora_dir_with_schemas: Path) -> None:
        reg = SchemaRegistry.load(agora_dir_with_schemas)
        reg.validate("finding", {"file": "a.py", "line": 1, "severity": "high"})

    def test_validate_invalid_value(self, agora_dir_with_schemas: Path) -> None:
        reg = SchemaRegistry.load(agora_dir_with_schemas)
        with pytest.raises(ValueError):
            reg.validate("finding", {"file": "a.py"})  # missing required fields

    def test_validate_unknown_schema(self, agora_dir_with_schemas: Path) -> None:
        reg = SchemaRegistry.load(agora_dir_with_schemas)
        with pytest.raises(KeyError):
            reg.validate("nonexistent", "value")

    def test_has_schema(self, agora_dir_with_schemas: Path) -> None:
        reg = SchemaRegistry.load(agora_dir_with_schemas)
        assert reg.has("finding") is True
        assert reg.has("nonexistent") is False

    def test_validate_items_for_array_schema(self, agora_dir: Path) -> None:
        schemas = {
            "findings_list": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"file": {"type": "string"}},
                    "required": ["file"],
                },
            }
        }
        (agora_dir / "schemas.json").write_text(json.dumps(schemas))
        reg = SchemaRegistry.load(agora_dir)
        # validate_item은 array 스키마의 items 정의로 단일 항목을 검증
        reg.validate_item("findings_list", {"file": "a.py"})

    def test_validate_item_non_array_schema(self, agora_dir_with_schemas: Path) -> None:
        reg = SchemaRegistry.load(agora_dir_with_schemas)
        with pytest.raises(TypeError, match="not an array"):
            reg.validate_item("status", "value")
```

- [ ] **Step 3: 테스트 실행하여 실패 확인**

```bash
python -m pytest tests/test_schema.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'agent_agora.schema'`

- [ ] **Step 4: SchemaRegistry 구현**

```python
# src/agent_agora/schema.py
from __future__ import annotations

import json
from pathlib import Path

import jsonschema


class SchemaRegistry:
    """schemas.json에서 로드된 JSON Schema 레지스트리."""

    _RESERVED_NAMES = frozenset({"schemas"})

    def __init__(self, schemas: dict[str, dict]) -> None:
        self._schemas = schemas

    @classmethod
    def load(cls, agora_dir: Path) -> SchemaRegistry:
        schemas_path = agora_dir / "schemas.json"
        if not schemas_path.exists():
            raise FileNotFoundError(f"schemas.json not found in {agora_dir}")

        schemas = json.loads(schemas_path.read_text(encoding="utf-8"))

        if not schemas:
            raise ValueError("schemas.json is empty")

        for name in schemas:
            if name in cls._RESERVED_NAMES:
                raise ValueError(f"Schema name '{name}' is reserved")

        return cls(schemas)

    def names(self) -> set[str]:
        return set(self._schemas.keys())

    def has(self, name: str) -> bool:
        return name in self._schemas

    def get_schema(self, name: str) -> dict:
        if name not in self._schemas:
            raise KeyError(f"Unknown schema: '{name}'")
        return self._schemas[name]

    def validate(self, schema_name: str, value: object) -> None:
        schema = self.get_schema(schema_name)
        try:
            jsonschema.validate(instance=value, schema=schema)
        except jsonschema.ValidationError as e:
            raise ValueError(str(e.message)) from e

    def validate_item(self, schema_name: str, item: object) -> None:
        schema = self.get_schema(schema_name)
        if schema.get("type") != "array":
            raise TypeError(f"Schema '{schema_name}' is not an array schema")
        items_schema = schema.get("items", {})
        try:
            jsonschema.validate(instance=item, schema=items_schema)
        except jsonschema.ValidationError as e:
            raise ValueError(str(e.message)) from e
```

- [ ] **Step 5: 테스트 실행하여 통과 확인**

```bash
python -m pytest tests/test_schema.py -v
```

Expected: 8 passed

- [ ] **Step 6: Commit**

```bash
git add src/agent_agora/schema.py tests/conftest.py tests/test_schema.py
git commit -m "feat: SchemaRegistry — load schemas.json and validate values"
```

---

### Task 3: AgoraStore — 인메모리 저장소 + JSON 직렬화

**Files:**
- Create: `agent-agora/src/agent_agora/store.py`
- Create: `agent-agora/tests/test_store.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_store.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_agora.schema import SchemaRegistry
from agent_agora.store import AgoraStore


@pytest.fixture
def registry(agora_dir_with_schemas: Path) -> SchemaRegistry:
    return SchemaRegistry.load(agora_dir_with_schemas)


@pytest.fixture
def store(agora_dir_with_schemas: Path, registry: SchemaRegistry) -> AgoraStore:
    return AgoraStore(agora_dir_with_schemas, registry)


class TestStoreSetGet:
    def test_set_and_get(self, store: AgoraStore) -> None:
        store.set("finding", "f1", {"file": "a.py", "line": 1, "severity": "low"})
        result = store.get("finding", "f1")
        assert result == {"file": "a.py", "line": 1, "severity": "low"}

    def test_get_missing_key(self, store: AgoraStore) -> None:
        result = store.get("finding", "nonexistent")
        assert result is None

    def test_set_overwrites(self, store: AgoraStore) -> None:
        store.set("status", "review", "pending")
        store.set("status", "review", "complete")
        assert store.get("status", "review") == "complete"

    def test_set_unknown_schema_raises(self, store: AgoraStore) -> None:
        with pytest.raises(KeyError):
            store.set("unknown", "k", "v")

    def test_set_invalid_value_raises(self, store: AgoraStore) -> None:
        with pytest.raises(ValueError):
            store.set("finding", "f1", {"file": "a.py"})  # missing required

    def test_get_unknown_schema_raises(self, store: AgoraStore) -> None:
        with pytest.raises(KeyError):
            store.get("unknown", "k")


class TestStoreAppend:
    def test_append_creates_list(self, agora_dir: Path) -> None:
        schemas = {
            "items": {
                "type": "array",
                "items": {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]},
            }
        }
        (agora_dir / "schemas.json").write_text(json.dumps(schemas))
        reg = SchemaRegistry.load(agora_dir)
        s = AgoraStore(agora_dir, reg)
        s.append("items", "list1", {"n": 1})
        assert s.get("items", "list1") == [{"n": 1}]

    def test_append_adds_to_existing(self, agora_dir: Path) -> None:
        schemas = {
            "items": {
                "type": "array",
                "items": {"type": "integer"},
            }
        }
        (agora_dir / "schemas.json").write_text(json.dumps(schemas))
        reg = SchemaRegistry.load(agora_dir)
        s = AgoraStore(agora_dir, reg)
        s.append("items", "nums", 1)
        s.append("items", "nums", 2)
        assert s.get("items", "nums") == [1, 2]

    def test_append_non_array_raises(self, store: AgoraStore) -> None:
        store.set("status", "review", "pending")
        with pytest.raises(TypeError):
            store.append("status", "review", "more")

    def test_append_invalid_item_raises(self, agora_dir: Path) -> None:
        schemas = {
            "items": {
                "type": "array",
                "items": {"type": "integer"},
            }
        }
        (agora_dir / "schemas.json").write_text(json.dumps(schemas))
        reg = SchemaRegistry.load(agora_dir)
        s = AgoraStore(agora_dir, reg)
        with pytest.raises(ValueError):
            s.append("items", "nums", "not_an_int")


class TestStoreDelete:
    def test_delete_existing(self, store: AgoraStore) -> None:
        store.set("status", "review", "pending")
        store.delete("status", "review")
        assert store.get("status", "review") is None

    def test_delete_missing_key_no_error(self, store: AgoraStore) -> None:
        store.delete("status", "nonexistent")  # should not raise


class TestStoreList:
    def test_list_schemas(self, store: AgoraStore) -> None:
        result = store.list_schemas()
        assert result == {"finding", "status"}

    def test_list_keys_empty(self, store: AgoraStore) -> None:
        assert store.list_keys("finding") == []

    def test_list_keys_with_data(self, store: AgoraStore) -> None:
        store.set("finding", "a", {"file": "a.py", "line": 1, "severity": "low"})
        store.set("finding", "b", {"file": "b.py", "line": 2, "severity": "high"})
        assert sorted(store.list_keys("finding")) == ["a", "b"]


class TestStorePersistence:
    def test_set_writes_file(self, agora_dir_with_schemas: Path, store: AgoraStore) -> None:
        store.set("status", "review", "pending")
        data_file = agora_dir_with_schemas / "status.json"
        assert data_file.exists()
        data = json.loads(data_file.read_text())
        assert data == {"review": "pending"}

    def test_restore_from_files(self, agora_dir_with_schemas: Path, registry: SchemaRegistry) -> None:
        # 기존 데이터 파일 생성
        data = {"f1": {"file": "a.py", "line": 1, "severity": "low"}}
        (agora_dir_with_schemas / "finding.json").write_text(json.dumps(data))
        # 새 store가 복구하는지 확인
        store2 = AgoraStore(agora_dir_with_schemas, registry)
        assert store2.get("finding", "f1") == {"file": "a.py", "line": 1, "severity": "low"}

    def test_delete_updates_file(self, agora_dir_with_schemas: Path, store: AgoraStore) -> None:
        store.set("status", "a", "pending")
        store.set("status", "b", "complete")
        store.delete("status", "a")
        data = json.loads((agora_dir_with_schemas / "status.json").read_text())
        assert data == {"b": "complete"}
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

```bash
python -m pytest tests/test_store.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'agent_agora.store'`

- [ ] **Step 3: AgoraStore 구현**

```python
# src/agent_agora/store.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_agora.schema import SchemaRegistry


class AgoraStore:
    """인메모리 저장소 + 스키마별 JSON 파일 직렬화."""

    def __init__(self, agora_dir: Path, registry: SchemaRegistry) -> None:
        self._dir = agora_dir
        self._registry = registry
        # schema_name -> {key -> value}
        self._data: dict[str, dict[str, Any]] = {name: {} for name in registry.names()}
        self._restore()

    def _restore(self) -> None:
        for name in self._registry.names():
            path = self._dir / f"{name}.json"
            if path.exists():
                self._data[name] = json.loads(path.read_text(encoding="utf-8"))

    def _persist(self, schema_name: str) -> None:
        path = self._dir / f"{schema_name}.json"
        path.write_text(json.dumps(self._data[schema_name], ensure_ascii=False, indent=2), encoding="utf-8")

    def _require_schema(self, schema_name: str) -> None:
        if not self._registry.has(schema_name):
            raise KeyError(f"Unknown schema: '{schema_name}'")

    def set(self, schema_name: str, key: str, value: Any) -> None:
        self._require_schema(schema_name)
        self._registry.validate(schema_name, value)
        self._data[schema_name][key] = value
        self._persist(schema_name)

    def get(self, schema_name: str, key: str) -> Any | None:
        self._require_schema(schema_name)
        return self._data[schema_name].get(key)

    def append(self, schema_name: str, key: str, item: Any) -> None:
        self._require_schema(schema_name)
        self._registry.validate_item(schema_name, item)
        bucket = self._data[schema_name]
        if key not in bucket:
            bucket[key] = [item]
        else:
            existing = bucket[key]
            if not isinstance(existing, list):
                raise TypeError(f"Value for '{schema_name}/{key}' is not a list")
            existing.append(item)
        self._persist(schema_name)

    def delete(self, schema_name: str, key: str) -> None:
        self._require_schema(schema_name)
        self._data[schema_name].pop(key, None)
        self._persist(schema_name)

    def list_schemas(self) -> set[str]:
        return self._registry.names()

    def list_keys(self, schema_name: str) -> list[str]:
        self._require_schema(schema_name)
        return list(self._data[schema_name].keys())
```

- [ ] **Step 4: 테스트 실행하여 통과 확인**

```bash
python -m pytest tests/test_store.py -v
```

Expected: 16 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent_agora/store.py tests/test_store.py
git commit -m "feat: AgoraStore — in-memory store with JSON persistence per schema"
```

---

### Task 4: 자체 서명 인증서 생성

**Files:**
- Create: `agent-agora/src/agent_agora/certs.py`
- Create: `agent-agora/tests/test_certs.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_certs.py
from __future__ import annotations

from pathlib import Path

from agent_agora.certs import ensure_certs


class TestCerts:
    def test_creates_cert_and_key(self, tmp_path: Path) -> None:
        cert_path, key_path = ensure_certs(tmp_path)
        assert cert_path.exists()
        assert key_path.exists()
        assert cert_path.suffix == ".pem"
        assert key_path.suffix == ".pem"

    def test_reuses_existing_certs(self, tmp_path: Path) -> None:
        cert1, key1 = ensure_certs(tmp_path)
        content1 = cert1.read_bytes()
        cert2, key2 = ensure_certs(tmp_path)
        # 같은 파일을 재사용해야 함
        assert cert1 == cert2
        assert cert1.read_bytes() == content1

    def test_cert_is_valid_pem(self, tmp_path: Path) -> None:
        cert_path, _ = ensure_certs(tmp_path)
        content = cert_path.read_text()
        assert "BEGIN CERTIFICATE" in content
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

```bash
python -m pytest tests/test_certs.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: certs 모듈 구현**

```python
# src/agent_agora/certs.py
from __future__ import annotations

import datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def ensure_certs(cert_dir: Path) -> tuple[Path, Path]:
    """인증서가 없으면 자체 서명 인증서를 생성하고, 있으면 재사용한다."""
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / "cert.pem"
    key_path = cert_dir / "key.pem"

    if cert_path.exists() and key_path.exists():
        return cert_path, key_path

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "AgentAgora localhost"),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    return cert_path, key_path
```

**주의:** 파일 상단에 `import ipaddress` 추가 필요.

```python
# src/agent_agora/certs.py 파일 상단에 추가
import ipaddress
```

- [ ] **Step 4: 테스트 실행하여 통과 확인**

```bash
python -m pytest tests/test_certs.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent_agora/certs.py tests/test_certs.py
git commit -m "feat: self-signed certificate generation for localhost HTTPS"
```

---

### Task 5: 쓰기 큐 (AsyncWriteQueue)

**Files:**
- Modify: `agent-agora/src/agent_agora/store.py`
- Create: `agent-agora/tests/test_queue.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_queue.py
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agent_agora.schema import SchemaRegistry
from agent_agora.store import AgoraStore, AsyncWriteQueue


@pytest.fixture
def registry(agora_dir_with_schemas: Path) -> SchemaRegistry:
    return SchemaRegistry.load(agora_dir_with_schemas)


@pytest.fixture
def store(agora_dir_with_schemas: Path, registry: SchemaRegistry) -> AgoraStore:
    return AgoraStore(agora_dir_with_schemas, registry)


class TestAsyncWriteQueue:
    async def test_set_via_queue(self, store: AgoraStore) -> None:
        queue = AsyncWriteQueue(store)
        async with queue:
            await queue.submit_set("status", "review", "pending", wait=True)
        assert store.get("status", "review") == "pending"

    async def test_append_via_queue(self, agora_dir: Path) -> None:
        schemas = {"nums": {"type": "array", "items": {"type": "integer"}}}
        (agora_dir / "schemas.json").write_text(json.dumps(schemas))
        reg = SchemaRegistry.load(agora_dir)
        s = AgoraStore(agora_dir, reg)
        queue = AsyncWriteQueue(s)
        async with queue:
            await queue.submit_append("nums", "list1", 1, wait=True)
            await queue.submit_append("nums", "list1", 2, wait=True)
        assert s.get("nums", "list1") == [1, 2]

    async def test_delete_via_queue(self, store: AgoraStore) -> None:
        store.set("status", "review", "pending")
        queue = AsyncWriteQueue(store)
        async with queue:
            await queue.submit_delete("status", "review", wait=True)
        assert store.get("status", "review") is None

    async def test_no_wait_returns_immediately(self, store: AgoraStore) -> None:
        queue = AsyncWriteQueue(store)
        async with queue:
            # wait=False면 큐에 넣고 즉시 반환
            await queue.submit_set("status", "review", "pending", wait=False)
            # 큐 처리 전에도 반환됨 — 잠시 대기 후 확인
            await asyncio.sleep(0.05)
        assert store.get("status", "review") == "pending"

    async def test_sequential_ordering(self, store: AgoraStore) -> None:
        queue = AsyncWriteQueue(store)
        async with queue:
            await queue.submit_set("status", "review", "pending", wait=True)
            await queue.submit_set("status", "review", "in_progress", wait=True)
            await queue.submit_set("status", "review", "complete", wait=True)
        assert store.get("status", "review") == "complete"

    async def test_validation_error_propagated(self, store: AgoraStore) -> None:
        queue = AsyncWriteQueue(store)
        async with queue:
            with pytest.raises(ValueError):
                await queue.submit_set("finding", "f1", {"file": "a.py"}, wait=True)
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

```bash
python -m pytest tests/test_queue.py -v
```

Expected: FAIL — `ImportError: cannot import name 'AsyncWriteQueue'`

- [ ] **Step 3: AsyncWriteQueue 구현**

`store.py` 하단에 추가:

```python
# src/agent_agora/store.py 에 추가

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any


class _Op(Enum):
    SET = "set"
    APPEND = "append"
    DELETE = "delete"


@dataclass
class _WriteRequest:
    op: _Op
    schema_name: str
    key: str
    value: Any = None
    future: asyncio.Future | None = None


class AsyncWriteQueue:
    """비동기 쓰기 큐. 모든 쓰기를 순차 처리한다."""

    def __init__(self, store: AgoraStore) -> None:
        self._store = store
        self._queue: asyncio.Queue[_WriteRequest | None] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    async def __aenter__(self) -> AsyncWriteQueue:
        self._worker_task = asyncio.create_task(self._worker())
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._queue.put(None)  # sentinel to stop worker
        if self._worker_task is not None:
            await self._worker_task

    async def _worker(self) -> None:
        while True:
            req = await self._queue.get()
            if req is None:
                break
            try:
                if req.op == _Op.SET:
                    self._store.set(req.schema_name, req.key, req.value)
                elif req.op == _Op.APPEND:
                    self._store.append(req.schema_name, req.key, req.value)
                elif req.op == _Op.DELETE:
                    self._store.delete(req.schema_name, req.key)
                if req.future is not None:
                    req.future.set_result(None)
            except Exception as e:
                if req.future is not None:
                    req.future.set_exception(e)

    async def _submit(self, op: _Op, schema_name: str, key: str, value: Any, wait: bool) -> None:
        loop = asyncio.get_running_loop()
        future = loop.create_future() if wait else None
        await self._queue.put(_WriteRequest(op, schema_name, key, value, future))
        if future is not None:
            await future

    async def submit_set(self, schema_name: str, key: str, value: Any, *, wait: bool = True) -> None:
        await self._submit(_Op.SET, schema_name, key, value, wait)

    async def submit_append(self, schema_name: str, key: str, item: Any, *, wait: bool = False) -> None:
        await self._submit(_Op.APPEND, schema_name, key, item, wait)

    async def submit_delete(self, schema_name: str, key: str, *, wait: bool = True) -> None:
        await self._submit(_Op.DELETE, schema_name, key, None, wait)
```

- [ ] **Step 4: 테스트 실행하여 통과 확인**

```bash
python -m pytest tests/test_queue.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent_agora/store.py tests/test_queue.py
git commit -m "feat: AsyncWriteQueue — sequential write processing via asyncio queue"
```

---

### Task 6: MCP 서버 + 6개 도구 핸들러

**Files:**
- Create: `agent-agora/src/agent_agora/server.py`
- Create: `agent-agora/tests/test_server.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_server.py
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_agora.schema import SchemaRegistry
from agent_agora.server import create_agora_app
from agent_agora.store import AgoraStore, AsyncWriteQueue


@pytest.fixture
def registry(agora_dir_with_schemas: Path) -> SchemaRegistry:
    return SchemaRegistry.load(agora_dir_with_schemas)


@pytest.fixture
def store(agora_dir_with_schemas: Path, registry: SchemaRegistry) -> AgoraStore:
    return AgoraStore(agora_dir_with_schemas, registry)


@pytest.fixture
def app_parts(agora_dir_with_schemas: Path, store: AgoraStore, registry: SchemaRegistry):
    """create_agora_app가 반환하는 (FastMCP, AsyncWriteQueue) 튜플."""
    return create_agora_app(
        agora_dir=agora_dir_with_schemas,
        store=store,
        registry=registry,
        port=0,
    )


class TestAgoraTools:
    """도구 핸들러를 직접 호출하여 테스트한다."""

    async def test_info(self, app_parts, agora_dir_with_schemas: Path) -> None:
        mcp, queue = app_parts
        async with queue:
            result = await mcp.call_tool("agora/info", {})
            data = json.loads(result[0].text)
            assert data["path"] == str(agora_dir_with_schemas)
            assert set(data["schemas"]) == {"finding", "status"}

    async def test_set_and_get(self, app_parts) -> None:
        mcp, queue = app_parts
        async with queue:
            value = {"file": "a.py", "line": 1, "severity": "low"}
            await mcp.call_tool("agora/set", {"schema": "finding", "key": "f1", "value": value})
            result = await mcp.call_tool("agora/get", {"schema": "finding", "key": "f1"})
            data = json.loads(result[0].text)
            assert data["value"] == value

    async def test_set_invalid_value(self, app_parts) -> None:
        mcp, queue = app_parts
        async with queue:
            result = await mcp.call_tool("agora/set", {"schema": "finding", "key": "f1", "value": {"file": "a.py"}})
            assert result[0].is_error or "error" in result[0].text.lower()

    async def test_set_unknown_schema(self, app_parts) -> None:
        mcp, queue = app_parts
        async with queue:
            result = await mcp.call_tool("agora/set", {"schema": "nope", "key": "k", "value": "v"})
            assert result[0].is_error or "unknown" in result[0].text.lower()

    async def test_get_missing_key(self, app_parts) -> None:
        mcp, queue = app_parts
        async with queue:
            result = await mcp.call_tool("agora/get", {"schema": "finding", "key": "nope"})
            data = json.loads(result[0].text)
            assert data["value"] is None

    async def test_append_and_get(self, app_parts, agora_dir: Path) -> None:
        # append용 array 스키마가 필요하므로 별도 setup
        schemas = {
            "items": {"type": "array", "items": {"type": "integer"}},
            "finding": {"type": "object", "properties": {"file": {"type": "string"}}, "required": ["file"]},
            "status": {"type": "string"},
        }
        (agora_dir / "schemas.json").write_text(json.dumps(schemas))
        reg = SchemaRegistry.load(agora_dir)
        store = AgoraStore(agora_dir, reg)
        mcp, queue = create_agora_app(agora_dir, store, reg, port=0)
        async with queue:
            await mcp.call_tool("agora/append", {"schema": "items", "key": "nums", "value": 1})
            await mcp.call_tool("agora/append", {"schema": "items", "key": "nums", "value": 2, "wait": True})
            result = await mcp.call_tool("agora/get", {"schema": "items", "key": "nums"})
            data = json.loads(result[0].text)
            assert data["value"] == [1, 2]

    async def test_delete(self, app_parts) -> None:
        mcp, queue = app_parts
        async with queue:
            await mcp.call_tool("agora/set", {"schema": "status", "key": "r", "value": "pending"})
            await mcp.call_tool("agora/delete", {"schema": "status", "key": "r"})
            result = await mcp.call_tool("agora/get", {"schema": "status", "key": "r"})
            data = json.loads(result[0].text)
            assert data["value"] is None

    async def test_list_schemas(self, app_parts) -> None:
        mcp, queue = app_parts
        async with queue:
            result = await mcp.call_tool("agora/list", {})
            data = json.loads(result[0].text)
            assert set(data["schemas"]) == {"finding", "status"}

    async def test_list_keys(self, app_parts) -> None:
        mcp, queue = app_parts
        async with queue:
            value = {"file": "a.py", "line": 1, "severity": "low"}
            await mcp.call_tool("agora/set", {"schema": "finding", "key": "f1", "value": value})
            result = await mcp.call_tool("agora/list", {"schema": "finding"})
            data = json.loads(result[0].text)
            assert data["keys"] == ["f1"]
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

```bash
python -m pytest tests/test_server.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: server.py 구현**

```python
# src/agent_agora/server.py
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from mcp.server import FastMCP
from mcp.types import TextContent

from agent_agora.schema import SchemaRegistry
from agent_agora.store import AgoraStore, AsyncWriteQueue


def create_agora_app(
    agora_dir: Path,
    store: AgoraStore,
    registry: SchemaRegistry,
    port: int,
) -> tuple[FastMCP, AsyncWriteQueue]:
    """FastMCP 앱과 AsyncWriteQueue를 생성한다."""

    mcp = FastMCP(
        name="AgentAgora",
        host="127.0.0.1",
        port=port,
    )

    queue = AsyncWriteQueue(store)
    start_time = time.time()

    def _ok(data: dict) -> list[TextContent]:
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

    def _error(msg: str) -> list[TextContent]:
        return [TextContent(type="text", text=json.dumps({"error": msg}), is_error=True)]

    @mcp.tool(name="agora/info")
    async def agora_info() -> list[TextContent]:
        """Return AgentAgora server metadata."""
        return _ok({
            "path": str(agora_dir),
            "port": port,
            "schemas": sorted(registry.names()),
            "uptime": int(time.time() - start_time),
        })

    @mcp.tool(name="agora/set")
    async def agora_set(schema: str, key: str, value: Any, wait: bool = True) -> list[TextContent]:
        """Store a value under a schema key. Validated against JSON Schema."""
        try:
            await queue.submit_set(schema, key, value, wait=wait)
            return _ok({"status": "ok", "schema": schema, "key": key})
        except (KeyError, ValueError, TypeError) as e:
            return _error(str(e))

    @mcp.tool(name="agora/get")
    async def agora_get(schema: str, key: str) -> list[TextContent]:
        """Retrieve a value by schema and key."""
        try:
            result = store.get(schema, key)
            return _ok({"schema": schema, "key": key, "value": result})
        except KeyError as e:
            return _error(str(e))

    @mcp.tool(name="agora/append")
    async def agora_append(schema: str, key: str, value: Any, wait: bool = False) -> list[TextContent]:
        """Append an item to a list value."""
        try:
            await queue.submit_append(schema, key, value, wait=wait)
            return _ok({"status": "ok", "schema": schema, "key": key})
        except (KeyError, ValueError, TypeError) as e:
            return _error(str(e))

    @mcp.tool(name="agora/delete")
    async def agora_delete(schema: str, key: str, wait: bool = True) -> list[TextContent]:
        """Remove a key from a schema."""
        try:
            await queue.submit_delete(schema, key, wait=wait)
            return _ok({"status": "ok", "schema": schema, "key": key})
        except KeyError as e:
            return _error(str(e))

    @mcp.tool(name="agora/list")
    async def agora_list(schema: str | None = None) -> list[TextContent]:
        """List schemas or keys within a schema."""
        if schema is None:
            return _ok({"schemas": sorted(registry.names())})
        try:
            keys = store.list_keys(schema)
            return _ok({"schema": schema, "keys": keys})
        except KeyError as e:
            return _error(str(e))

    return mcp, queue
```

- [ ] **Step 4: 테스트 실행하여 통과 확인**

```bash
python -m pytest tests/test_server.py -v
```

Expected: 10 passed

**주의:** FastMCP의 `call_tool` 반환 타입이 실제 SDK와 다를 수 있음. 실행 후 API에 맞게 테스트 코드를 조정할 것. `mcp.call_tool` 대신 도구 함수를 직접 호출하는 방식으로 전환할 수도 있음.

- [ ] **Step 5: Commit**

```bash
git add src/agent_agora/server.py tests/test_server.py
git commit -m "feat: MCP server with 6 agora tools (info, set, get, append, delete, list)"
```

---

### Task 7: CLI 엔트리포인트

**Files:**
- Create: `agent-agora/src/agent_agora/__main__.py`

- [ ] **Step 1: __main__.py 구현**

```python
# src/agent_agora/__main__.py
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="agent-agora",
        description="AgentAgora — shared state MCP server for independent agents",
    )
    parser.add_argument("--port", type=int, default=8420, help="HTTPS port (default: 8420)")
    parser.add_argument("--dir", type=Path, default=Path("."), help="Project directory containing .agentagora/")
    parser.add_argument(
        "--cert-dir",
        type=Path,
        default=Path.home() / ".agent-agora" / "certs",
        help="Certificate storage directory",
    )
    return parser.parse_args(argv)


async def run_server(args: argparse.Namespace) -> None:
    import uvicorn

    from agent_agora.certs import ensure_certs
    from agent_agora.schema import SchemaRegistry
    from agent_agora.server import create_agora_app
    from agent_agora.store import AgoraStore

    agora_dir = args.dir / ".agentagora"
    if not agora_dir.is_dir():
        print(f"Error: .agentagora/ not found in {args.dir.resolve()}", file=sys.stderr)
        sys.exit(1)

    registry = SchemaRegistry.load(agora_dir)
    store = AgoraStore(agora_dir, registry)
    cert_path, key_path = ensure_certs(args.cert_dir)
    mcp, queue = create_agora_app(agora_dir, store, registry, args.port)

    print(f"AgentAgora starting on https://127.0.0.1:{args.port}/mcp")
    print(f"  Data dir : {agora_dir.resolve()}")
    print(f"  Schemas  : {', '.join(sorted(registry.names()))}")
    print(f"  Cert     : {cert_path}")

    starlette_app = mcp.streamable_http_app()
    config = uvicorn.Config(
        starlette_app,
        host="127.0.0.1",
        port=args.port,
        ssl_certfile=str(cert_path),
        ssl_keyfile=str(key_path),
        log_level="info",
    )
    server = uvicorn.Server(config)

    async with queue:
        await server.serve()


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    asyncio.run(run_server(args))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: CLI 도움말 확인**

```bash
python -m agent_agora --help
```

Expected:

```
usage: agent-agora [-h] [--port PORT] [--dir DIR] [--cert-dir CERT_DIR]

AgentAgora — shared state MCP server for independent agents

options:
  -h, --help           show this help message and exit
  --port PORT          HTTPS port (default: 8420)
  --dir DIR            Project directory containing .agentagora/
  --cert-dir CERT_DIR  Certificate storage directory
```

- [ ] **Step 3: 실제 실행 테스트 (수동)**

테스트용 `.agentagora/` 디렉토리를 만들어서 서버가 뜨는지 확인:

```bash
mkdir -p /tmp/test-agora/.agentagora
echo '{"greeting": {"type": "string"}}' > /tmp/test-agora/.agentagora/schemas.json
python -m agent_agora --port 8420 --dir /tmp/test-agora
```

Expected: 서버 시작 로그 출력 후 요청 대기.

- [ ] **Step 4: Commit**

```bash
git add src/agent_agora/__main__.py
git commit -m "feat: CLI entrypoint with argparse, uvicorn HTTPS server startup"
```

---

### Task 8: uv tool install 확인 및 마무리

**Files:**
- Verify: `agent-agora/pyproject.toml`

- [ ] **Step 1: uv tool install 테스트**

```bash
cd agent-agora
uv tool install .
```

Expected: `agent-agora` 명령어가 PATH에 등록됨.

- [ ] **Step 2: 설치된 CLI 실행 확인**

```bash
agent-agora --help
```

Expected: Task 7 Step 2와 동일한 도움말 출력.

- [ ] **Step 3: 전체 테스트 실행**

```bash
cd agent-agora
python -m pytest tests/ -v
```

Expected: 전체 통과 (schema 8 + store 16 + certs 3 + queue 6 + server 10 = 약 43개)

- [ ] **Step 4: 최종 Commit**

```bash
git add -A
git commit -m "chore: verify uv tool install and full test suite"
```
