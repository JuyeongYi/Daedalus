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

        saved_before, discarded = self._save_before_switch(
            save_current, save_current_as, "열지 않았습니다"
        )

        if not window.open_path(path):
            raise RuntimeError(f"열지 못했습니다: {self._status_text()}")
        return {
            "opened": window._current_path,
            "name": self._project.name,
            "saved_before_open": saved_before,
            "discarded_unsaved": discarded,
        }

    def _save_before_switch(
        self, save_current: bool, save_current_as: str, refusal: str
    ) -> tuple[str | None, bool]:
        """현재 프로젝트를 버리기 전의 저장 게이트 — 열기/새 프로젝트 공용 실체.

        판정은 `MainWindow.project_has_content()`("새 프로젝트" 확인 다이얼로그와
        같은 판정)이고, 저장할 수 없으면 **예외를 던져 다음 단계로 넘어가지
        않는다** — 미저장 소실 사고가 났던 그 지점이다. 게이트가 둘로 갈리면
        한쪽 경로로만 변경이 사라지므로 `open_project`와 `new_project`가 이
        함수를 공유한다.

        돌려주는 것은 (저장한 경로|None, 버렸는가).
        """
        window = self._window
        if getattr(window, "_project", None) is None or not window.project_has_content():
            return None, False
        if not save_current:
            return None, True
        target = save_current_as or getattr(window, "_current_path", None)
        if not target:
            raise ValueError(
                "현재 프로젝트를 한 번도 저장한 적이 없어 자동 저장할 수 없습니다. "
                "save_current_as로 저장 경로를 주거나, 버려도 된다면 "
                "save_current=False로 호출하세요."
            )
        if not window._save_to_path(target):
            raise RuntimeError(
                f"현재 프로젝트를 저장하지 못해 {refusal}: {self._status_text()}"
            )
        return window._current_path, False

    def list_project_templates(self) -> dict[str, Any]:
        """새 프로젝트의 출발점 목록 (G11) — Ctrl+N 다이얼로그가 보여주는 것과 같다.

        내장 3종 + 사용자 템플릿(`~/.daedalus/templates/`)이며 동명 id는 사용자가
        이긴다. `builtin`은 패키지 동봉 여부, `has_files`는 폴더형 템플릿이라
        `files/`·`skill-files/`가 **첫 저장 때 딸려 오는지**다.
        """
        from daedalus.model import templates

        return {
            "templates": [
                {
                    "id": t.id,
                    "title": t.title,
                    "summary": t.summary,
                    "builtin": t.file is None,
                    "has_files": t.source_dir is not None,
                }
                for t in templates.list_templates()
            ]
        }

    def new_project(
        self,
        template_id: str | None = None,
        build_target: str = "marketplace",
        save_current: bool = True,
        save_current_as: str = "",
    ) -> dict[str, Any]:
        """새 프로젝트를 시작한다 (G11) — Ctrl+N 통합 다이얼로그와 동형.

        template_id: 생략(None)이면 빈 프로젝트(이름 `new-plugin`), 주면 그
        템플릿에서 시작한다(`list_project_templates`가 id를 준다).
        build_target: marketplace / local. **여기서 고른 타깃이 템플릿에 저장된
        타깃을 항상 이긴다** — 템플릿 내용은 타깃 중립이고 타깃은 사용자 소유다.

        `open_project`와 **같은 저장 게이트**를 지난다: 새 프로젝트를 만드는
        순간 현재 편집 내용은 메모리에서 사라지므로, 잃을 것이 있으면 먼저
        저장하고 저장할 수 없으면 만들지 않는다. 저장 경로가 없으면
        `save_current_as`를 주거나 `save_current=False`로 버릴 것을 명시한다.

        만들어진 프로젝트는 **저장되지 않은 상태**다(`save_project(path)`로
        저장한다). 폴더형 템플릿의 동봉 파일은 그 첫 저장 때 딸려 간다.
        """
        from daedalus.model import templates
        from daedalus.model.plugin.enums import BuildTarget
        from daedalus.model.project import PluginProject

        window = self._window
        try:
            target = BuildTarget(str(build_target).lower())
        except ValueError:
            allowed = ", ".join(t.value for t in BuildTarget)
            raise ValueError(
                f"알 수 없는 빌드 타깃 '{build_target}'. 사용 가능: {allowed}"
            ) from None

        # 템플릿 해소는 **저장 전에** 한다 — 알 수 없는 id로 헛저장을 시키지
        # 않는다(open_project가 열 수 없는 경로를 저장 전에 거절하는 것과 같다).
        entry = None
        project = None
        if template_id:
            try:
                entry = templates.find_template(template_id)
                project = templates.load_template(template_id)
            except templates.TemplateError as exc:
                raise ValueError(str(exc)) from exc

        saved_before, discarded = self._save_before_switch(
            save_current, save_current_as, "새 프로젝트를 만들지 않았습니다"
        )

        if project is None:
            project = PluginProject(name="new-plugin", build_target=target)
        else:
            project.build_target = target

        window.load_project(project)
        window._current_path = None
        # 폴더형 템플릿의 files/·skill-files/는 첫 저장 때 딸려 간다.
        window._pending_template_assets = entry.source_dir if entry is not None else None
        if entry is not None:
            # 빈 프로젝트와 달리 잃을 내용이 있고 저장 경로는 아직 없다.
            window._mark_dirty()
        window._update_title()
        window._sync_files_root()
        window._status_label.setText(
            f"새 프로젝트 — {template_id} 템플릿 (아직 저장되지 않음)"
            if template_id
            else "새 프로젝트"
        )
        return {
            "name": project.name,
            "template": template_id or None,
            "build_target": project.build_target.value,
            "saved_before": saved_before,
            "discarded_unsaved": discarded,
        }

    def import_package(
        self,
        archive_path: str,
        dest_dir: str,
        save_current: bool = True,
        save_current_as: str = "",
    ) -> dict[str, Any]:
        """`.ddpj` 패키지를 폴더에 풀고 그 프로젝트를 연다 (G12) — export_package의 짝.

        dest_dir는 **새로 만들거나 비어 있어야 한다** — 기존 폴더에 덮어 풀면
        무엇이 남은 것이고 무엇이 온 것인지 구분할 수 없다. 압축 안에서 직접
        편집하지는 않는다(`files/` 드래그·컴파일·저장이 전부 특수 경로가 된다).

        푼 **다음** `open_project`를 그대로 태우므로 저장 게이트도 똑같다 —
        현재 프로젝트를 저장할 수 없으면 열지 않는다. 그때 풀린 폴더는 남으므로
        저장 문제를 해결한 뒤 `open_project`로 열면 된다.
        """
        from daedalus.model import package

        if not os.path.isfile(archive_path):
            raise ValueError(f"패키지 파일이 없습니다: {archive_path}")
        try:
            project_file = package.unpack(archive_path, dest_dir)
        except (package.PackageError, OSError) as exc:
            raise ValueError(f"가져오지 못했습니다: {exc}") from exc
        result = self.open_project(
            str(project_file),
            save_current=save_current,
            save_current_as=save_current_as,
        )
        return {"imported": str(project_file), "dest": dest_dir, **result}

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
