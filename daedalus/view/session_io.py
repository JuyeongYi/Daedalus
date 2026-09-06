# daedalus/view/session_io.py
"""프로젝트 세션 입출력 — 저장 / 열기 / 최근 목록 / 패키지 (WP-RF-3e).

`MainWindow`의 **협력 객체**다(Mixin 아님 — 상속으로 섞으면 이름 충돌과
`self`의 정체가 흐려진다). 여기가 실체이고 `MainWindow`에는 같은 이름의
한 줄 위임 메서드만 남는다.

**상태의 단일 진실은 계속 window에 있다.** `_current_path`·`_project`·
`_status_label` 같은 값을 이 객체가 복제하지 않고 `self._w.<attr>`로 직접
읽고 쓴다 — 복제하면 두 곳이 어긋나는 순간 "저장했는데 다른 파일이 열린다"
류의 버그가 된다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QInputDialog,
    QMessageBox,
)

from daedalus.model import package
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project
from daedalus.view import recent

if TYPE_CHECKING:  # pragma: no cover - 타입 전용
    from daedalus.view.app import MainWindow


def recent_label(index: int, path: str) -> str:
    """`&1 파일명 — 상위폴더` 형태의 메뉴 라벨.

    파일명만으로는 구분이 안 되는 경우가 흔해(`project.daedalus.json` 등)
    상위 폴더 이름을 함께 보인다. 전체 경로는 툴팁에 있다.

    새 형식(WP-PK)에서는 파일 이름이 `.daedalus.json` 하나뿐이라 그대로
    보이면 전부 같은 이름이 된다 — 그때는 폴더 이름이 곧 이름이고, 상위
    폴더는 그 위 단계가 된다.
    """
    shown = path
    if os.path.basename(path) == package.PROJECT_FILENAME:
        shown = os.path.dirname(path)
    name = os.path.basename(shown)
    parent = os.path.basename(os.path.dirname(shown))
    if parent:
        name = f"{name} — {parent}"
    # 파일명의 &는 니모닉으로 먹히므로 escape
    name = name.replace("&", "&&")
    return f"&{index} {name}" if index < 10 else name


class SessionIO:
    """저장/열기/최근/패키지 동작을 담당하는 MainWindow 협력 객체."""

    def __init__(self, window: MainWindow) -> None:
        self._w = window

    # --- 저장 / 열기 ---

    def sync_files_root(self) -> None:
        """FilePanel의 root를 `_current_path` 기준으로 재설정한다 (WP-FR).

        MCP 접속 정보의 프로젝트 경로도 같이 갱신한다 (WP-MCP) — CC가 지금 어떤
        프로젝트에 붙어 있는지 알 수 있도록. `_current_path`가 바뀌는 지점이
        여기 하나로 모여 있어 배선 지점도 하나로 유지된다.
        """
        w = self._w
        project_dir = Path(w._current_path).parent if w._current_path else None
        w._file_panel.set_project_dir(project_dir)
        service = w._mcp_service
        if service is not None:
            service.update_project_path(w._current_path)  # type: ignore[attr-defined]

    def update_title(self) -> None:
        """창 제목 갱신 — 미저장 변경이 있으면 앞에 `*`를 붙인다 (A7 관례)."""
        w = self._w
        base = "Daedalus — FSM Plugin Designer"
        if w._current_path:
            title = f"{package.display_name(w._current_path)} — {base}"
        else:
            title = base
        if w._dirty:
            title = f"*{title}"
        w.setWindowTitle(title)

    def save_to_path(self, path: str) -> bool:
        """프로젝트를 경로에 쓴다. 성공 여부를 돌려준다.

        반환값은 GUI 경로에서는 무시되지만(상태바 문구가 결과를 말한다) MCP의
        `open_project`처럼 **저장 성공을 전제로 다음 단계를 진행하는** 호출자는
        이 값으로 판정한다 — 실패를 못 보고 열면 그 순간 변경이 사라진다.
        """
        w = self._w
        if w._project is None:
            return False
        # 폴더를 주면 그 안의 정본 파일이 저장 대상이다 (WP-PK). `_current_path`는
        # 계속 **파일**을 가리키므로 parent로 계산하는 곳들이 그대로 동작한다.
        target = str(package.resolve_project_file(path))
        # 저장 직전 캔버스 좌표를 graph_layout에 반영 (버그 1: 좌표 왕복)
        w._save_graph_layout()
        try:
            parent = Path(target).parent
            if not parent.exists():
                parent.mkdir(parents=True, exist_ok=True)
            data = serialize_project(w._project)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except (OSError, TypeError, ValueError) as exc:
            # OSError: IO 실패 / TypeError·ValueError: 직렬화 불가 객체 혼입
            w._status_label.setText(f"저장 실패: {exc}")
            return False
        moved_files = self.carry_files_dir(target)
        template_files, assets_warning = self.carry_template_assets(target)
        moved_files += template_files
        path = target
        w._current_path = path
        # 디스크와 메모리가 일치했다 (A7). update_title 전에 내려야 제목의 `*`가
        # 같은 호출에서 지워진다.
        w._dirty = False
        self.update_title()
        self.sync_files_root()
        self.remember_recent(path)
        note = f" (files/ {moved_files}개 복사)" if moved_files else ""
        if assets_warning:
            note += f" — ⚠ {assets_warning}"
        w._status_label.setText(f"저장됨: {path}{note}")
        return True

    def carry_files_dir(self, new_file: str) -> int:
        """다른 폴더로 저장할 때 `files/`·`skill-files/`를 함께 옮긴다 (WP-PK/WP-SF).

        폴더가 곧 프로젝트이므로, 프로젝트를 다른 폴더에 저장했는데 동봉 파일이
        옛 폴더에 남아 있으면 그건 반쪽짜리 프로젝트다 — 컴파일하면 파일이
        빠지고, `dangling_file_ref` 경고로야 뒤늦게 드러난다.

        목적지에 이미 같은 이름 폴더가 있으면 **건드리지 않는다** — 남의 것을
        덮어쓰는 것보다 아무것도 안 하는 편이 낫다(그 경우는 사용자가 의도한
        배치다).
        """
        w = self._w
        old = w._current_path
        if not old:
            return 0
        return self._copy_side_dirs(Path(old).parent, Path(new_file).parent)

    def _copy_side_dirs(self, source_root: Path, dest_root: Path) -> int:
        """`files/`·`skill-files/`를 source_root → dest_root로 복사 (공용 실체).

        carry_files_dir(다른 폴더로 저장)와 템플릿 동반 복사가 같은 정책을
        공유한다: 같은 폴더·원본 부재·**목적지 실존 시 불가침**.
        """
        import shutil

        from daedalus.compiler.project_compiler import SKILL_FILES_DIRNAME

        w = self._w
        copied = 0
        for dirname in ("files", SKILL_FILES_DIRNAME):
            source = source_root / dirname
            dest = dest_root / dirname
            if not source.is_dir() or dest.exists():
                continue
            if source.resolve() == dest.resolve():
                continue
            try:
                shutil.copytree(source, dest, symlinks=False)
            except (OSError, shutil.Error) as exc:
                w._status_label.setText(f"{dirname}/ 복사 실패: {exc}")
                continue
            copied += sum(1 for p in dest.rglob("*") if p.is_file())
        return copied

    def carry_template_assets(self, new_file: str) -> tuple[int, str | None]:
        """폴더형 템플릿의 동봉 파일을 **첫 저장 시** 프로젝트 폴더로 복사한다.

        템플릿에서 만든 프로젝트는 미저장 상태로 시작해 files/를 놓을 곳이
        없다 — 저장 위치가 정해지는 순간이 복사 시점이다. 원천은 저장 시점까지
        **원본 폴더를 참조**한다(임시 보관보다 단순). 그 사이 템플릿이
        삭제됐으면 경고 후 스킵하고 다시 시도하지 않는다(fail-soft — 반복
        경고는 소음이고, 원본이 사라진 이상 재시도해도 결과가 같다).
        """
        w = self._w
        pending = getattr(w, "_pending_template_assets", None)
        if pending is None:
            return 0, None
        w._pending_template_assets = None
        source_root = Path(pending)
        if not source_root.is_dir():
            # 상태바에 직접 쓰면 save_to_path의 "저장됨" 문구가 곧바로 덮어써
            # 경고가 보이지 않는다 — 반환해 최종 문구에 합류시킨다(협력 객체는
            # 무상태 계약이라 self에 스테이징하지 않는다).
            return 0, "템플릿 동봉 파일 원본이 사라져 files/를 복사하지 못했습니다"
        return self._copy_side_dirs(source_root, Path(new_file).parent), None

    def save_project(self) -> None:
        w = self._w
        if w._current_path:
            self.save_to_path(w._current_path)
        else:
            self.save_project_as()

    def save_project_as(self) -> None:
        """프로젝트 **폴더**를 골라 저장한다 (WP-PK).

        구버전 파일을 열어 두었더라도 여기서 폴더를 고르면 새 형식
        (`<폴더>/.daedalus.json`)으로 옮겨간다 — 그것이 형식을 바꾸는 유일한
        지점이다(Ctrl+S는 열려 있던 형식을 그대로 유지한다).
        """
        w = self._w
        start = str(package.project_dir(w._current_path)) if w._current_path else ""
        directory = QFileDialog.getExistingDirectory(
            w, "프로젝트 폴더 선택 (폴더가 곧 프로젝트입니다)", start,
        )
        if directory:
            self.save_to_path(directory)

    def project_has_content(self) -> bool:
        """잃을 것이 있는 프로젝트인가 — 빈 프로젝트를 덮어쓰는 것은 손실이 아니다.

        "새 프로젝트"의 확인 다이얼로그와 MCP `open_project`의 저장 강제가 같은
        판정을 써야 한다 — 한쪽만 느슨하면 그 경로로만 변경이 사라진다.
        """
        project = self._w._project
        if project is None:
            return False
        return (
            bool(project.skills)
            or bool(project.agents)
            or len(project.graph.states) > 1  # EntryPoint 제외
        )

    def new_project(self) -> None:
        """Ctrl+N — 새 프로젝트 통합 다이얼로그 (출발점 + 빌드 타깃, 사용자 확정).

        한 다이얼로그에서 출발점(빈 프로젝트|템플릿)과 빌드 타깃을 **같이**
        고른다. 템플릿에 저장된 타깃은 여기서 고른 타깃이 항상 이긴다 —
        템플릿 내용은 타깃 중립이고 타깃은 사용자 소유다. 다이얼로그 취소는
        생성 취소(기존 WP-TG 규약 그대로). 현재 프로젝트가 비어 있지
        않으면 먼저 저장 여부를 확인한다.
        """
        from daedalus.model import templates

        w = self._w
        if w._project is not None:
            if w.project_has_content():
                reply = QMessageBox.question(
                    w,
                    "새 프로젝트",
                    "저장하지 않은 변경이 사라질 수 있습니다.\n계속하시겠습니까?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

        choice = self.exec_new_project_dialog()
        if choice is None:
            return  # 취소 — 프로젝트 생성 취소
        template_id, target = choice

        if template_id is None:
            new_proj = PluginProject(name="new-plugin", build_target=target)
            w.load_project(new_proj)
            w._current_path = None
            w._pending_template_assets = None
            self.update_title()
            self.sync_files_root()
            w._status_label.setText("새 프로젝트")
            return

        try:
            entry = templates.find_template(template_id)
            project = templates.load_template(template_id)
        except templates.TemplateError as exc:
            w._status_label.setText(f"템플릿 열기 실패: {exc}")
            return
        # 생성 시 고른 타깃이 템플릿에 저장된 타깃을 이긴다(위 docstring).
        project.build_target = target

        w.load_project(project)
        w._current_path = None
        # 폴더형 템플릿의 files/·skill-files/는 첫 저장 때 딸려 간다
        # (carry_template_assets). 단일 JSON형·내장은 None.
        w._pending_template_assets = entry.source_dir
        # 빈 프로젝트와 달리 잃을 내용이 있고 저장 경로는 아직 없다 —
        # 미저장 변경으로 표시해 닫기 확인(미저장 변경 확인 기능)이 받는다.
        w._mark_dirty()
        self.update_title()
        self.sync_files_root()
        w._status_label.setText(
            f"새 프로젝트 — {template_id} 템플릿 (아직 저장되지 않음)"
        )

    def exec_new_project_dialog(self) -> tuple[str | None, BuildTarget] | None:
        """통합 다이얼로그를 띄우고 (템플릿 id|None, 타깃)을 돌려준다. 취소면 None.

        테스트 봉합선 — 헤드리스에서 모달을 띄우지 않으려면 이 메서드를
        몽키패치한다(구 QInputDialog.getItem 스텁의 후임).
        """
        from daedalus.view.editors.new_project_dialog import NewProjectDialog
        from PySide6.QtWidgets import QDialog

        dlg = NewProjectDialog(self._w)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return dlg.template_id(), dlg.build_target()

    def edit_project_properties(self) -> None:
        """"프로젝트 속성…" — name/description/version 편집.

        이름 규약 검사는 여기서 막지 않는다 — F7 경고 / 컴파일 게이트가 잡는다.
        """
        w = self._w
        if w._project is None:
            return
        from daedalus.view.editors.project_properties import ProjectPropertiesDialog

        dialog = ProjectPropertiesDialog(w._project, parent=w)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            dialog.apply_to(w._project)
            self.update_title()
            w._status_label.setText("프로젝트 속성 변경됨")

    def open_project_dialog(self) -> None:
        """프로젝트 **폴더**를 골라 연다 (WP-PK).

        폴더 안의 정본(`.daedalus.json`)을 열고, 없으면 구버전
        `<이름>.daedalus.json` 하나를 받아들인다 — 기존 프로젝트 폴더도
        그대로 폴더째 열린다.
        """
        w = self._w
        start = str(package.project_dir(w._current_path)) if w._current_path else ""
        directory = QFileDialog.getExistingDirectory(w, "프로젝트 폴더 열기", start)
        if directory:
            w.open_path(directory)

    def open_file_dialog(self) -> None:
        """구버전 `<이름>.daedalus.json`을 파일로 직접 연다.

        한 폴더에 구버전 파일이 여럿이면 폴더 선택으로는 무엇을 여는지 정할 수
        없다 — 그때 쓰는 통로다.
        """
        w = self._w
        path, _ = QFileDialog.getOpenFileName(
            w, "프로젝트 파일 열기", w._current_path or "",
            "Daedalus 프로젝트 (*.daedalus.json *.json)",
        )
        if path:
            w.open_path(path)

    # --- 패키지 (.ddpj) ---

    def export_package_dialog(self) -> None:
        """현재 프로젝트 폴더를 `.ddpj` 하나로 묶는다.

        지금까지 프로젝트를 남에게 주려면 "json이랑 files 폴더를 같이 보내라"고
        해야 했다 — 틀리기 쉬운 안내였다.
        """
        w = self._w
        if not w._current_path:
            QMessageBox.information(
                w, "패키지로 내보내기",
                "먼저 프로젝트를 저장하세요. 묶을 폴더가 정해져야 합니다.",
            )
            return
        source = package.project_dir(w._current_path)
        suggested = str(source.parent / package.default_archive_name(w._current_path))
        target, _ = QFileDialog.getSaveFileName(
            w, "패키지로 내보내기", suggested,
            f"Daedalus 패키지 (*{package.ARCHIVE_SUFFIX})",
        )
        if not target:
            return
        try:
            members = package.pack(source, target)
        except (package.PackageError, OSError) as exc:
            w._status_label.setText(f"내보내기 실패: {exc}")
            return
        w._status_label.setText(f"내보냄: {target} ({len(members)}개 파일)")

    def import_package_dialog(self) -> None:
        """`.ddpj`를 폴더에 풀고 그 프로젝트를 연다.

        압축 안에서 직접 편집하지 않는다 — `files/` 드래그·컴파일·저장이 전부
        특수 경로가 되어 득보다 실이 크다.
        """
        w = self._w
        archive, _ = QFileDialog.getOpenFileName(
            w, "패키지 가져오기", "",
            f"Daedalus 패키지 (*{package.ARCHIVE_SUFFIX})",
        )
        if not archive:
            return
        dest = QFileDialog.getExistingDirectory(
            w, "풀어놓을 폴더 선택 (비어 있어야 합니다)",
            str(Path(archive).parent),
        )
        if not dest:
            return
        try:
            project_file = package.unpack(archive, dest)
        except (package.PackageError, OSError) as exc:
            w._status_label.setText(f"가져오기 실패: {exc}")
            return
        w.open_path(str(project_file))

    # --- 최근 프로젝트 (WP-RP) ---

    def remember_recent(self, path: str) -> None:
        """열기/저장이 성공한 경로를 최근 목록 맨 앞으로 올린다."""
        recent.push(path)
        self.rebuild_recent_menu()

    def rebuild_recent_menu(self) -> None:
        """"최근 프로젝트" 서브메뉴를 목록 파일로부터 다시 만든다."""
        w = self._w
        menu = w._recent_menu
        if menu is None:
            return
        menu.clear()

        paths = recent.load()
        if not paths:
            empty = menu.addAction("(없음)")
            if empty is not None:
                empty.setEnabled(False)
            return

        for index, path in enumerate(paths, start=1):
            action = QAction(recent_label(index, path), w)
            action.setToolTip(path)
            action.setStatusTip(path)
            # 기본 인자로 path를 묶어 둔다 — 늦은 바인딩이면 전부 마지막 경로를 연다
            action.triggered.connect(
                lambda _checked=False, p=path: self.open_recent(p)
            )
            menu.addAction(action)

        menu.addSeparator()
        clear_action = QAction("목록 지우기", w)
        clear_action.triggered.connect(self.clear_recent)
        menu.addAction(clear_action)

    def open_recent(self, path: str) -> None:
        """최근 항목을 연다. 파일이 사라졌으면 목록에서 떨군다."""
        w = self._w
        if not os.path.exists(path):
            recent.remove(path)
            self.rebuild_recent_menu()
            w._status_label.setText(f"파일을 찾을 수 없어 목록에서 제거했습니다: {path}")
            return
        w.open_path(path)

    def clear_recent(self) -> None:
        w = self._w
        recent.clear()
        self.rebuild_recent_menu()
        w._status_label.setText("최근 프로젝트 목록을 비웠습니다")

    def open_path(self, path: str) -> bool:
        """경로에서 프로젝트를 로드한다 (다이얼로그 없이 — 테스트/CLI/MCP 재사용).

        폴더를 주면 그 안의 프로젝트 파일을 찾아 연다 (WP-PK) — 정본
        `.daedalus.json`이 우선, 없으면 구버전 `<이름>.daedalus.json` 하나.

        성공 여부를 돌려준다 — `save_to_path`와 같은 이유다(호출자가 실패를
        구분해야 한다). GUI 경로는 상태바 문구로 결과를 말하므로 무시한다.
        """
        w = self._w
        deser_warnings: list[str] = []
        try:
            path = str(package.find_project_file(path))
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            project = deserialize_project(data, collect_warnings=deser_warnings)
        except (OSError, ValueError, package.PackageError) as exc:
            w._status_label.setText(f"열기 실패: {exc}")
            return False
        w.load_project(project)
        w._current_path = path
        # 다른 프로젝트를 열었으니 템플릿 동반 복사 예약은 무의미하다.
        w._pending_template_assets = None
        self.update_title()
        self.sync_files_root()
        self.remember_recent(path)
        fname = os.path.basename(path)
        if deser_warnings:
            w._status_label.setText(
                f"열림: {fname} (경고 {len(deser_warnings)}건 — F7로 확인)"
            )
        else:
            w._status_label.setText(f"열림: {fname}")
        return True
