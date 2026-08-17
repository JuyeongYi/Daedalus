# daedalus/view/panels/file_panel.py
"""파일 패널 2종 — 전역 files/ 독 + 스킬별 skill-files/ 에디터 패널 (WP-FR/WP-SF).

전역과 스킬별은 **동시에 떠 있는 별개 표면**이다(사용자 확정 — 콤보 전환이
아니라): 독의 ``FilePanel``은 공용 ``<dir>/files``(플러그인 루트로 통째 복사,
``${ROOT}/files/…`` 참조)를, 스킬 에디터 우측의 ``SkillFilesPanel``은 그 스킬
전용 ``<dir>/skill-files/<스킬>/``(SKILL.md 옆으로 복사,
``${CLAUDE_SKILL_DIR}/…`` 참조)을 보여준다. 둘 다 "익스플로러로 열기" 버튼을
가진다. 드래그 소스는 ``QFileSystemModel``의 기본 mime(file URL) 그대로 —
``MarkdownEditor``의 드롭 처리가 루트별로 맞는 토큰을 만든다.

``SkillFilesPanel``은 에디터마다 생기므로 app이 인스턴스에 직접 배선할 수 없다
— 모듈 수준 ``set_project_dir_provider``(TagInput 후보 provider와 같은 패턴)로
현재 프로젝트 폴더를 조회한다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from daedalus.compiler.project_compiler import SKILL_FILES_DIRNAME

_PROJECT_DIR_PROVIDER: Callable[[], str | None] | None = None


def set_project_dir_provider(provider: Callable[[], str | None] | None) -> None:
    """현재 프로젝트 폴더 제공자를 등록한다 (SkillFilesPanel이 조회)."""
    global _PROJECT_DIR_PROVIDER
    _PROJECT_DIR_PROVIDER = provider


def get_project_dir() -> str | None:
    """등록된 제공자에서 현재 프로젝트 폴더를 가져온다 (미저장이면 None)."""
    if _PROJECT_DIR_PROVIDER is not None:
        return _PROJECT_DIR_PROVIDER()
    return None


def _open_in_explorer(path: str) -> None:
    """OS 파일 탐색기로 폴더를 연다 (Windows 탐색기/맥 Finder 공통)."""
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


class _FileTreeBase(QWidget):
    """파일 트리 패널 공통 뼈대 — 트리 바인딩 / 안내 / 생성 / 탐색기 열기.

    서브클래스는 ``_root_path()``(대상 폴더, 프로젝트 미설정이면 None)와
    ``_title()``만 구현한다.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model: QFileSystemModel | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        header = QHBoxLayout()
        self._title_label = QLabel()
        self._title_label.setStyleSheet("font-weight: bold;")
        header.addWidget(self._title_label, 1)
        self._explorer_btn = QPushButton("탐색기")
        self._explorer_btn.setToolTip("이 폴더를 OS 파일 탐색기로 연다")
        self._explorer_btn.clicked.connect(self._open_explorer)
        header.addWidget(self._explorer_btn)
        self._refresh_btn = QPushButton("새로고침")
        self._refresh_btn.setToolTip("파일시스템 변경 반영 (루트 생성 직후 등)")
        self._refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self._refresh_btn)
        lay.addLayout(header)

        self._info_label = QLabel()
        self._info_label.setWordWrap(True)
        lay.addWidget(self._info_label)

        self._create_btn = QPushButton()
        self._create_btn.clicked.connect(self._create_root_folder)
        lay.addWidget(self._create_btn)

        self._tree = QTreeView()
        self._tree.setDragEnabled(True)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self._tree.setHeaderHidden(False)
        lay.addWidget(self._tree, 1)

    # --- 서브클래스 구현 ---

    def _root_path(self) -> Path | None:
        raise NotImplementedError

    def _title(self) -> str:
        raise NotImplementedError

    # --- 공통 동작 ---

    def existing_root(self) -> str | None:
        """루트 경로 — 실존할 때만 반환."""
        root = self._root_path()
        return str(root) if root is not None and root.is_dir() else None

    def refresh(self) -> None:
        """파일시스템 변경을 반영한다 — QFileSystemModel은 자동 감시하지만 루트
        생성 직후에는 재바인딩이 필요하다."""
        self._title_label.setText(self._title())
        root = self.existing_root()
        if root is None:
            self._model = None
            self._tree.setModel(None)
            self._refresh_visibility(active=False)
            return
        model = QFileSystemModel()
        model.setRootPath(root)
        self._tree.setModel(model)
        self._tree.setRootIndex(model.index(root))
        for col in range(1, model.columnCount()):
            self._tree.hideColumn(col)
        self._model = model
        self._refresh_visibility(active=True)

    def _create_root_folder(self) -> None:
        root = self._root_path()
        if root is None:
            return
        root.mkdir(parents=True, exist_ok=True)
        self.refresh()

    def _open_explorer(self) -> None:
        root = self.existing_root()
        if root is not None:
            _open_in_explorer(root)

    def _refresh_visibility(self, *, active: bool) -> None:
        root = self._root_path()
        has_project = root is not None
        name = root.name if root is not None else ""
        if not has_project:
            self._info_label.setText("프로젝트를 저장하면 파일 폴더를 사용할 수 있습니다.")
        elif not active:
            self._info_label.setText(f"{name}/ 폴더가 없습니다. 아래 버튼으로 만드세요.")
        self._create_btn.setText(f"{name or '파일'} 폴더 만들기")
        self._info_label.setVisible(not active)
        self._create_btn.setVisible(has_project and not active)
        self._explorer_btn.setEnabled(active)
        self._tree.setVisible(active)


class FilePanel(_FileTreeBase):
    """전역 files/ 트리 독 패널. app.py가 독 위젯 "파일"로 배치한다."""

    def __init__(self, parent: QWidget | None = None) -> None:
        self._project_dir: Path | None = None
        super().__init__(parent)
        self._refresh_visibility(active=False)

    def set_project_dir(self, project_dir: str | Path | None) -> None:
        """프로젝트 저장 파일이 있는 디렉토리를 설정한다 (app이 저장/열기/새 프로젝트
        시 ``_current_path`` 기준으로 호출)."""
        self._project_dir = Path(project_dir) if project_dir else None
        self.refresh()

    def files_root(self) -> str | None:
        """공용 files/ 루트 경로 — 실존할 때만 반환(드롭 provider의 단일 진실)."""
        return self.existing_root()

    def skill_files_root(self) -> str | None:
        """skill-files/ 루트 경로 — 실존할 때만 반환 (WP-SF 드롭 provider)."""
        if self._project_dir is None:
            return None
        root = self._project_dir / SKILL_FILES_DIRNAME
        return str(root) if root.is_dir() else None

    def _root_path(self) -> Path | None:
        return self._project_dir / "files" if self._project_dir is not None else None

    def _title(self) -> str:
        return "공용 files/"


class SkillFilesPanel(_FileTreeBase):
    """스킬 하나의 skill-files/<스킬>/ 트리 — 스킬 에디터 우측 패널 (WP-SF).

    전역 독과 **동시에** 떠 있다. 프로젝트 폴더는 모듈 provider로 조회하므로
    에디터가 열릴 때마다 새로 만들어도 배선이 필요 없다.
    """

    # ComponentEditor 우측 수직 스플리터에서의 선호 비율 — 파일 트리는 포트
    # 카드 목록(Transfer On/Agent Call)보다 세로 공간이 더 필요하다.
    right_stretch = 3

    def __init__(self, component: object, parent: QWidget | None = None) -> None:
        self._component = component  # name을 매번 읽는다 — rename 추적
        super().__init__(parent)
        self.refresh()

    def _root_path(self) -> Path | None:
        project_dir = get_project_dir()
        if not project_dir:
            return None
        name = str(getattr(self._component, "name", "") or "")
        if not name:
            return None
        return Path(project_dir) / SKILL_FILES_DIRNAME / name

    def _title(self) -> str:
        name = getattr(self._component, "name", "")
        return f"📁 스킬 파일 ({SKILL_FILES_DIRNAME}/{name}/)"

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        # 탭 전환으로 다시 보일 때 rename/외부 변경을 따라잡는다 — 파일시스템
        # 감시는 QFileSystemModel이 하지만 루트 경로 자체의 변화는 못 본다.
        super().showEvent(event)
        self.refresh()
