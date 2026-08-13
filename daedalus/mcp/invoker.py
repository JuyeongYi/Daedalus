"""워커 스레드 → Qt 메인 스레드 마샬링 (WP-MCP).

MCP 도구 핸들러는 uvicorn 워커 스레드에서 실행되는데, 거기서 위젯이나 뷰모델을
직접 만지면 Qt가 깨진다(GUI 객체는 생성된 스레드에서만 다뤄야 한다). 이 모듈은
호출을 큐 연결로 메인 스레드에 넘기고 결과가 나올 때까지 기다리는 통로다.

``QMetaObject.invokeMethod``의 BlockingQueuedConnection 대신 시그널 + ``Event``를
쓴다 — PySide6에서 임의 반환값을 되받으려면 인자 타입 등록이 필요해 번거롭고,
예외를 호출자에게 그대로 전달하기도 어렵다.
"""
from __future__ import annotations

import threading
from typing import Any, Callable

from PySide6.QtCore import QObject, Qt, Signal

DEFAULT_TIMEOUT = 15.0
"""메인 스레드 응답 대기 상한(초). 모달 다이얼로그 등으로 이벤트 루프가 막혀 있으면
영원히 기다리는 대신 오류로 끝낸다 — CC 쪽이 무한정 붙잡혀 있지 않도록."""


class _Call:
    __slots__ = ("fn", "result", "error", "done")

    def __init__(self, fn: Callable[[], Any]) -> None:
        self.fn = fn
        self.result: Any = None
        self.error: BaseException | None = None
        self.done = threading.Event()


class MainThreadInvoker(QObject):
    """메인 스레드에서 생성해야 한다 — 그래야 큐 연결이 메인 스레드로 배달된다."""

    _requested = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._requested.connect(self._run, Qt.ConnectionType.QueuedConnection)

    def call(self, fn: Callable[[], Any], timeout: float = DEFAULT_TIMEOUT) -> Any:
        """fn을 메인 스레드에서 실행하고 결과를 돌려준다.

        fn이 던진 예외는 호출 스레드에서 그대로 다시 던져진다 — MCP 도구가
        오류 메시지를 정상적으로 만들 수 있도록.
        """
        call = _Call(fn)
        self._requested.emit(call)
        if not call.done.wait(timeout):
            raise TimeoutError(
                f"Daedalus 메인 스레드가 {timeout}초 안에 응답하지 않았습니다 "
                "(모달 다이얼로그가 열려 있는지 확인하세요)."
            )
        if call.error is not None:
            raise call.error
        return call.result

    def _run(self, call: _Call) -> None:
        try:
            call.result = call.fn()
        except BaseException as exc:  # noqa: BLE001 — 호출자에게 그대로 전달
            call.error = exc
        finally:
            call.done.set()
