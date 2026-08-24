# daedalus/view/compile_actions.py
"""컴파일 액션 — Ctrl+B 출력 폴더 선택 + 컴파일 실행 (WP-RF-3e).

`MainWindow`의 협력 객체다(Mixin 아님). 상태는 window에 있고 이 객체는
`self._w.<attr>`로 직접 읽고 쓴다 — 복제하지 않는다.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QFileDialog

from daedalus.model import package
from daedalus.model.plugin.enums import BuildTarget

if TYPE_CHECKING:  # pragma: no cover - 타입 전용
    from daedalus.view.app import MainWindow


class CompileActions:
    """컴파일 메뉴 동작을 담당하는 MainWindow 협력 객체."""

    def __init__(self, window: MainWindow) -> None:
        self._w = window

    def compile_project_dialog(self) -> None:
        """Ctrl+B — 출력 폴더 선택 후 프로젝트를 컴파일한다.

        에러가 있으면 ValidationPanel을 갱신하고 거부 메시지를 상태바에 표시한다.
        """
        w = self._w
        if w._project is None:
            w._status_label.setText("컴파일: 프로젝트가 없습니다.")
            return

        # LOCAL은 컴파일이 곧 설치 — 고르는 것은 스테이징 폴더가 아니라 플러그인을
        # 반입할 **작업 폴더**다(WP-MW). 시작 위치는 현재 프로젝트 저장 폴더.
        is_local = getattr(w._project, "build_target", None) is BuildTarget.LOCAL
        title = (
            "설치 대상 작업 폴더 선택 (.claude/ 밑에 반입됩니다)"
            if is_local else "컴파일 출력 폴더 선택"
        )
        start = str(package.project_dir(w._current_path)) if w._current_path else ""
        out_dir = QFileDialog.getExistingDirectory(w, title, start)
        if not out_dir:
            return

        from daedalus.compiler import compile_project

        from daedalus.compiler.project_compiler import SKILL_FILES_DIRNAME

        project_dir = Path(w._current_path).parent if w._current_path else None
        files_dir = project_dir / "files" if project_dir else None
        skill_files_dir = project_dir / SKILL_FILES_DIRNAME if project_dir else None
        result = compile_project(
            w._project, out_dir, files_dir=files_dir,
            # 앱이 이미 아는 서버 정의(자기 자신의 daedalus 서버)를 주입한다 —
            # 아는 것을 사용자에게 등록시키지 않는다(WP-MW).
            extra_server_defs=self.known_server_defs(),
            skill_files_dir=skill_files_dir,
            # 전역 훅(~/.daedalus/hooks/)까지 해소해서 넘긴다 — 컴파일러는
            # 파일시스템을 읽지 않으므로 여기가 주입 지점이다 (A1).
            resolved_hooks=w.resolved_hooks(),
        )
        if not result.ok:
            # 에러 — 검증 패널에 동봉(경고 포함) 표시
            w._validation_panel.set_errors(result.errors + result.warnings)
            w._show_validation_dock()
            w._status_label.setText(
                f"컴파일 거부: 에러 {len(result.errors)}건 (F7로 확인)"
            )
            return

        warn = len(result.warnings)
        warn_str = f" / 경고 {warn}건" if warn else ""
        copied_str = f" / files {len(result.copied_files)}개 복사" if result.copied_files else ""
        w._status_label.setText(
            f"컴파일 완료: {len(result.written)}파일 생성{copied_str}{warn_str} → {out_dir}"
        )
        if warn:
            # F7 검증 흐름과 동일하게 dock도 표시 — 경고를 상태바 문구로만
            # 인지하게 두지 않는다.
            w._validation_panel.set_errors(result.warnings)
            w._show_validation_dock()

    def known_server_defs(self) -> dict[str, dict]:
        """앱이 스스로 아는 MCP 서버 정의 — 지금은 자기 자신(daedalus)뿐.

        서버가 떠 있으면 실제 포트를, 아니면 기본 포트를 쓴다 — MCP를 끄고
        컴파일해도 배선은 나가야 설치 후 앱을 켰을 때 바로 붙는다.
        """
        from daedalus.mcp import endpoint

        url = getattr(self._w._mcp_service, "url", None) or endpoint.url_for(
            endpoint.DEFAULT_PORT
        )
        return {"daedalus": {"type": "http", "url": url}}
