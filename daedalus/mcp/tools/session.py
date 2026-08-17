# daedalus/mcp/tools/session.py
"""세션 도구 — 저장/열기/패키지 내보내기/최근 프로젝트 (WP-RF-3b).

**계층: GUI 어댑터다 (WP-RF-2 명시).** core(model/compiler)가 아니라
MainWindow·ProjectViewModel·CommandStack·body_documents 등 view 표면에 결합된
코드로, core 경계 계약(tests/test_import_contracts.py)의 대상이 아니다.
모든 메서드는 **Qt 메인 스레드에서 실행되는 것을 전제**로 한다(service가
MainThreadInvoker로 마샬링한다). 편집 도구는 반드시
``ProjectViewModel.execute``(CommandStack)를 거친다 — 사용자가 Ctrl+Z로
되돌릴 수 있어야 한다.

저장이 여는 절차 안에 있다(WP-PK) — 편집 중인 내용은 메모리에만 있어 여는
순간 사라지므로, 잃을 것이 있으면 먼저 저장하고 저장할 수 없으면 열지 않는다.
"""
from __future__ import annotations

import os
from typing import Any

from ._base import _BaseTools


class SessionTools(_BaseTools):
    """세션 (저장 / 열기)."""

    def list_recent_projects(self) -> dict[str, Any]:
        """최근 연 프로젝트 파일 목록 — `open_project`에 넘길 경로를 찾는 통로.

        실존 여부는 검사하지 않는다(사용자의 "최근 프로젝트" 메뉴와 같은 정책 —
        네트워크 드라이브에서 stat이 멈춘다). 사라진 파일은 열 때 걸러진다.
        """
        from daedalus.view import recent

        paths = recent.load()
        return {
            "current": getattr(self._window, "_current_path", None),
            "recent": [
                {"path": p, "name": os.path.basename(p)} for p in paths
            ],
        }

    def save_project(self, path: str = "") -> dict[str, Any]:
        """프로젝트를 파일로 저장한다 — 사람이 Ctrl+S를 누른 것과 같다.

        path를 생략하면 현재 저장 경로에 덮어쓴다. 한 번도 저장한 적 없는
        프로젝트라면 path가 필요하다 — 저장 위치를 임의로 정하지 않는다.
        """
        window = self._window
        project = self._project  # 열린 프로젝트가 없으면 여기서 거절된다
        target = path or getattr(window, "_current_path", None)
        if not target:
            raise ValueError(
                "한 번도 저장한 적 없는 프로젝트입니다. path로 저장 폴더를 지정하세요."
            )
        if not window._save_to_path(target):
            raise RuntimeError(f"저장하지 못했습니다: {self._status_text()}")
        return {"saved_path": window._current_path, "name": project.name}

    def open_project(
        self,
        path: str,
        save_current: bool = True,
        save_current_as: str = "",
    ) -> dict[str, Any]:
        """다른 프로젝트를 연다 — **현재 프로젝트를 먼저 저장한 뒤에**.

        path는 **프로젝트 폴더**(안의 `.daedalus.json`을 연다) 또는 구버전
        `<이름>.daedalus.json` 파일이다.

        편집 중인 내용은 메모리에만 있으므로 여는 순간 사라진다. 그래서 저장이
        이 도구의 절차 안에 들어 있다: 잃을 것이 있으면 먼저 저장하고, 저장할
        수 없으면(경로를 모르거나 쓰기에 실패하면) **열지 않는다**.

        - 한 번도 저장한 적 없는 프로젝트라면 `save_current_as`로 폴더를 주어야 한다.
        - 버려도 되는 내용이면 `save_current=False`로 명시한다.
        - 빈 프로젝트(스킬·에이전트·배치 전무)는 잃을 것이 없으므로 그냥 열린다.
        """
        from daedalus.model import package

        window = self._window
        if not os.path.exists(path):
            raise ValueError(f"경로가 없습니다: {path}")
        try:
            package.find_project_file(path)  # 열 수 없는 경로면 저장 전에 거절한다
        except package.PackageError as exc:
            raise ValueError(str(exc)) from exc

        saved_before: str | None = None
        discarded = False
        if getattr(window, "_project", None) is not None and window.project_has_content():
            if save_current:
                target = save_current_as or getattr(window, "_current_path", None)
                if not target:
                    raise ValueError(
                        "현재 프로젝트를 한 번도 저장한 적이 없어 자동 저장할 수 없습니다. "
                        "save_current_as로 저장 경로를 주거나, 버려도 된다면 "
                        "save_current=False로 호출하세요."
                    )
                if not window._save_to_path(target):
                    raise RuntimeError(
                        f"현재 프로젝트를 저장하지 못해 열지 않았습니다: {self._status_text()}"
                    )
                saved_before = window._current_path
            else:
                discarded = True

        if not window.open_path(path):
            raise RuntimeError(f"열지 못했습니다: {self._status_text()}")
        return {
            "opened": window._current_path,
            "name": self._project.name,
            "saved_before_open": saved_before,
            "discarded_unsaved": discarded,
        }

    def export_package(self, archive_path: str = "") -> dict[str, Any]:
        """현재 프로젝트 폴더를 `.ddpj` 하나로 묶는다 — 통째로 건넬 때 쓴다.

        `open_project`와 같은 이유로 **먼저 저장한 뒤에** 묶는다: 메모리에만 있는
        편집을 빼놓고 묶으면 받는 쪽은 그것이 최신인 줄 안다.

        archive_path를 생략하면 프로젝트 폴더 옆에 폴더 이름으로 만든다.
        """
        from daedalus.model import package

        window = self._window
        project = self._project
        current = getattr(window, "_current_path", None)
        if not current:
            raise ValueError(
                "한 번도 저장한 적 없는 프로젝트입니다. save_project로 먼저 저장하세요."
            )
        if not window._save_to_path(current):
            raise RuntimeError(f"저장하지 못해 묶지 않았습니다: {self._status_text()}")

        current = window._current_path
        source = package.project_dir(current)
        target = archive_path or str(source.parent / package.default_archive_name(current))
        try:
            members = package.pack(source, target)
        except (package.PackageError, OSError) as exc:
            raise RuntimeError(f"묶지 못했습니다: {exc}") from exc
        return {"archive": target, "name": project.name, "files": len(members)}

    def _status_text(self) -> str:
        """상태바 문구 — 실패 원인은 거기에만 남는다(GUI 경로와 같은 출처)."""
        label = getattr(self._window, "_status_label", None)
        return label.text() if label is not None else ""
