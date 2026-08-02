# daedalus/view/panels/file_panel.py
"""파일 독 패널 — 프로젝트 옆 files/ 트리 뷰 (WP-FR).

files/ 소스 위치는 프로젝트 저장 파일 옆(``<dir>/files``)이다. 미저장
프로젝트(``project_dir`` 미설정)는 기능이 비활성화되어 안내만 표시한다.
드래그 소스는 ``QFileSystemModel``의 기본 mime(file URL)을 그대로 쓴다 —
``MarkdownEditor``의 드롭 처리(WP-FR Part B)가 이를 소비한다.
"""
from __future__ import annotations

from pathlib import Path

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


class FilePanel(QWidget):
    """files/ 트리 뷰 + 안내/새로고침. app.py가 독 위젯으로 배치한다."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_dir: Path | None = None
        self._model: QFileSystemModel | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        header = QHBoxLayout()
        header.addStretch(1)
        self._refresh_btn = QPushButton("새로고침")
        self._refresh_btn.setToolTip("파일시스템 변경 반영 (루트 생성 직후 등)")
        self._refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self._refresh_btn)
        lay.addLayout(header)

        self._info_label = QLabel()
        self._info_label.setWordWrap(True)
        lay.addWidget(self._info_label)

        self._create_btn = QPushButton("files 폴더 만들기")
        self._create_btn.clicked.connect(self._create_files_folder)
        lay.addWidget(self._create_btn)

        self._tree = QTreeView()
        self._tree.setDragEnabled(True)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self._tree.setHeaderHidden(False)
        lay.addWidget(self._tree, 1)

        self._refresh_visibility(active=False)

    # --- 공개 API ---

    def set_project_dir(self, project_dir: str | Path | None) -> None:
        """프로젝트 저장 파일이 있는 디렉토리를 설정한다 (app이 저장/열기/새 프로젝트
        시 ``_current_path`` 기준으로 호출)."""
        self._project_dir = Path(project_dir) if project_dir else None
        self.refresh()

    def files_root(self) -> str | None:
        """현재 files/ 루트 경로 — 실존할 때만 반환(provider가 조회하는 단일 진실)."""
        if self._project_dir is None:
            return None
        root = self._project_dir / "files"
        return str(root) if root.is_dir() else None

    def refresh(self) -> None:
        """파일시스템 변경을 반영한다 — QFileSystemModel은 자동 감시하지만 루트
        생성 직후에는 재바인딩이 필요하다."""
        root = self.files_root()
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

    # --- 내부 ---

    def _create_files_folder(self) -> None:
        if self._project_dir is None:
            return
        (self._project_dir / "files").mkdir(parents=True, exist_ok=True)
        self.refresh()

    def _refresh_visibility(self, *, active: bool) -> None:
        has_project = self._project_dir is not None
        if not has_project:
            self._info_label.setText("프로젝트를 저장하면 files/ 폴더를 사용할 수 있습니다.")
        elif not active:
            self._info_label.setText("files/ 폴더가 없습니다. 아래 버튼으로 만드세요.")
        self._info_label.setVisible(not active)
        self._create_btn.setVisible(has_project and not active)
        self._tree.setVisible(active)
