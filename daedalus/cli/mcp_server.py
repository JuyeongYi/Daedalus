# daedalus/cli/mcp_server.py
"""블랙보드 stdio MCP 서버 (``daedalus-bb``) — WP-BM.

컴파일 산출(스킬·에이전트)이 런타임에 블랙보드를 읽고 쓰는 **유일한 표면**이다.
종전에는 같은 코어를 CLI로 감쌌지만, 도구로 내면 노드의 reads/writes 선언이
그대로 **프론트매터 권한**(스킬 `allowed-tools`, 에이전트 `tools`)으로 번역된다 —
캔버스의 📖/✏ 뱃지와 산출 권한이 같은 사실을 말하고, 셸 따옴표·exit code 해석
계층이 산출 문서에서 사라진다.

도구는 7개이고 코어 함수와 1:1이다. **실패는 예외가 아니라 결과로 낸다** —
``{"ok": false, "error": {"kind": ..., "message": ..., "detail": [...]}}``.
kind는 셋뿐이다(`not_found`/`usage`/`rejected`). 소비자가 모델이므로 종전 CLI가
stderr로 내던 진단은 ``message``에 합친다.

진입 인자는 CLI와 같다: ``daedalus-bb --schemas PATH [--state-dir DIR]``.
**스키마 파일은 기동 시점에 읽지 않는다** — 읽으면 스키마가 없는 작업 폴더에서
서버가 통째로 죽어 모델이 "도구가 없다"는 것 말고는 아무 이유도 듣지 못한다.
각 도구 호출이 그때 읽고, 실패는 그 호출의 ``usage`` 결과가 된다(원칙 5).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from daedalus.cli import core, progress as progress_mod
from daedalus.cli.core import BlackboardError

#: 서버 이름 접두 — 실제 이름은 `bb-<플러그인>`이다(컴파일러가 같은 규약으로
#: `.mcp.json`을 낸다). 한 작업 폴더에 Daedalus 플러그인이 여럿이면 스키마와
#: 상태 폴더가 다르므로 서버도 각각이다.
SERVER_NAME_PREFIX = "bb-"

_INSTRUCTIONS = (
    "Blackboard state for this Daedalus plugin: the JSON files under the "
    "working folder's state directory, validated against the plugin's schema. "
    "Read before you write; every write is validated and atomic. On failure a "
    "tool returns {\"ok\": false, \"error\": {...}} instead of raising."
)


def server_name(plugin: str) -> str:
    return f"{SERVER_NAME_PREFIX}{plugin}"


def _error_result(exc: BlackboardError) -> dict[str, Any]:
    """코어 실패 → 도구 결과. 모델이 읽는 값이므로 예외로 끊지 않는다."""
    error: dict[str, Any] = {"kind": exc.kind, "message": exc.message}
    if exc.detail:
        error["detail"] = exc.detail
    return {"ok": False, "error": error}


class BlackboardTools:
    """도구 7개의 핸들러 — 테스트가 **직접** 부르는 표면이다.

    상태를 갖는 것은 경로 둘뿐이다(스키마 파일·상태 폴더). 스키마는 호출마다
    다시 읽는다 — 서버가 세션 내내 살아 있는 동안 플러그인이 재컴파일될 수
    있고, 낡은 스키마로 검증하면 방금 만든 클래스를 "없다"고 거절한다.

    메서드 이름에 `tool_` 접두가 붙는 이유는 **도구가 아닌 이름과 섞이지
    않게** 하기 위해서다: 노출 이름(`validate`)을 그대로 메서드로 쓰면 저장소
    어딘가의 동명 심볼과 구분되지 않아, 데드코드 스캐너처럼 이름으로 참조를
    세는 게이트가 무관한 심볼을 조용히 살린다. 노출 이름은 `TOOLS` 표가 정한다.
    """

    def __init__(self, schemas_path: Path, state_dir: Path) -> None:
        self.schemas_path = schemas_path
        self.state_dir = state_dir

    @property
    def plugin(self) -> str:
        return core.plugin_name(self.schemas_path)

    def _schemas(self) -> dict[str, dict]:
        return core.load_schemas(self.schemas_path)

    # ── 도구 ──

    def tool_list(self) -> dict[str, Any]:
        """List the blackboard classes and their fields."""
        try:
            return core.list_classes(self._schemas(), self.state_dir, self.schemas_path)
        except BlackboardError as exc:
            return _error_result(exc)

    def tool_read(self, cls: str, field: str | None = None) -> Any:
        """Read a state file, or one field of it."""
        try:
            value = core.read_value(self._schemas(), self.state_dir, cls, field)
        except BlackboardError as exc:
            return _error_result(exc)
        if field is None:
            return value
        return {"field": field, "value": value}

    def tool_init(self, cls: str, force: bool = False) -> Any:
        """Create the state file for a class from its schema."""
        try:
            return core.init_class(self._schemas(), self.state_dir, cls, force)
        except BlackboardError as exc:
            return _error_result(exc)

    def tool_write(
        self,
        cls: str,
        set: dict[str, Any] | None = None,  # noqa: A002 — 도구 파라미터 이름이다
        append: dict[str, Any] | None = None,
        remove: dict[str, Any] | None = None,
    ) -> Any:
        """Write fields of a state file; returns the object after writing."""
        try:
            return core.write_class(
                self._schemas(),
                self.state_dir,
                cls,
                sets=set,
                appends=append,
                removes=remove,
            )
        except BlackboardError as exc:
            return _error_result(exc)

    def tool_validate(self, classes: list[str] | None = None) -> dict[str, Any]:
        """Validate state files against the schema."""
        try:
            return core.validate_classes(self._schemas(), self.state_dir, classes)
        except BlackboardError as exc:
            return _error_result(exc)

    def tool_progress_read(self) -> Any:
        """Read this plugin's workflow progress entry."""
        try:
            return progress_mod.read_entry(self.state_dir, self.plugin)
        except BlackboardError as exc:
            return _error_result(exc)

    def tool_progress_set(
        self,
        current: str | None = None,
        completed: list[str] | None = None,
        note: str | None = None,
        prev: str | None = None,
    ) -> Any:
        """Update this plugin's workflow progress entry."""
        try:
            return progress_mod.set_entry(
                self.state_dir,
                self.plugin,
                current=current,
                completed=completed,
                note=note,
                prev=prev,
            )
        except BlackboardError as exc:
            return _error_result(exc)


#: 도구 이름 → 핸들러. **문자열 디스패치가 아니라 선언**이다 — 이름만 적고
#: `getattr`로 찾으면 핸들러가 아무 데서도 참조되지 않는 것으로 보여
#: 데드코드 게이트가 오탐하고, 오타가 기동 시점까지 숨는다.
#: 순서는 읽기 → 쓰기 → 진행으로, 가이드의 도구 표와 같다.
TOOLS: tuple[tuple[str, Any], ...] = (
    ("list", BlackboardTools.tool_list),
    ("read", BlackboardTools.tool_read),
    ("init", BlackboardTools.tool_init),
    ("write", BlackboardTools.tool_write),
    ("validate", BlackboardTools.tool_validate),
    ("progress_read", BlackboardTools.tool_progress_read),
    ("progress_set", BlackboardTools.tool_progress_set),
)

#: 산출(프론트매터 권한·산문)과 서버가 **같은 목록**을 말해야 한다 — 컴파일러가
#: 이 이름을 임포트한다(`compiler/emit/blackboard_tools.py`).
TOOL_NAMES: tuple[str, ...] = tuple(name for name, _ in TOOLS)


def build_server(tools: BlackboardTools) -> Any:
    """도구 7개를 등록한 MCP 서버 인스턴스."""
    from daedalus.mcp_compat import server_factory

    server_cls = server_factory()
    server = server_cls(name=server_name(tools.plugin), instructions=_INSTRUCTIONS)
    for name, func in TOOLS:
        server.add_tool(func.__get__(tools), name=name)
    return server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="daedalus-bb",
        description=(
            "Daedalus 블랙보드 stdio MCP 서버 — 상태 파일(state/) 읽기·쓰기·검증."
        ),
    )
    parser.add_argument(
        "--schemas",
        required=True,
        metavar="PATH",
        help="블랙보드 스키마 파일 (필수) — 예: schemas/<플러그인>.json",
    )
    parser.add_argument(
        "--state-dir",
        default=None,
        metavar="DIR",
        help=(
            f"상태 파일 폴더 "
            f"(기본: {core.DEFAULT_STATE_ROOT}/<--schemas 파일 이름>)"
        ),
    )
    return parser


def tools_from_args(args: argparse.Namespace) -> BlackboardTools:
    schemas_path = Path(args.schemas)
    return BlackboardTools(
        schemas_path, core.resolve_state_dir(args.state_dir, schemas_path)
    )


def _reconfigure_std_streams() -> None:
    """stdout/stderr를 UTF-8로 — Windows 콘솔 기본이 cp949라 한글·`—`가 든
    argparse 도움말·진단이 `UnicodeEncodeError`로 죽는다(옛 CLI `main()`과
    같은 처치, 2026-09-20 머지 검토에서 재발 확인). 프로토콜 채널(stdout)도
    UTF-8이어야 JSON-RPC 본문의 한글이 깨지지 않는다."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    """``daedalus-bb`` 진입점 — stdio로 서버를 돌린다.

    stdio 전송에서 **stdout은 프로토콜 전용 채널**이다. 코어는 출력 채널이
    없으므로 여기서 아무것도 print하지 않는다 — 진단은 stderr로만 나간다.
    """
    _reconfigure_std_streams()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse의 --help(0) / 사용법 오류(2)
        return int(exc.code or 0)
    build_server(tools_from_args(args)).run(transport="stdio")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
