# daedalus/view/panels/file_panel.py
"""파일 독 패널 — 프로젝트 옆 files/·skill-files/ 트리 뷰 (WP-FR/WP-SF).

소스 위치는 프로젝트 저장 파일 옆이다: 공용 ``<dir>/files``(플러그인 루트로
통째 복사, ``${ROOT}/files/…`` 참조)와 스킬별 ``<dir>/skill-files/<스킬>/``
(그 스킬 SKILL.md 옆으로 복사, ``${CLAUDE_SKILL_DIR}/…`` 참조). 상단 콤보로
루트를 전환한다. 미저장 프로젝트(``project_dir`` 미설정)는 기능이 비활성화되어
안내만 표시한다. 드래그 소스는 ``QFileSystemModel``의 기본 mime(file URL)을
그대로 쓴다 — ``MarkdownEditor``의 드롭 처리가 이를 소비한다.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from daedalus.compiler.project_compiler import SKILL_FILES_DIRNAME

# 콤보 인덱스 순서 = 이 튜플 순서 (라벨, 디렉토리명)
_ROOTS: tuple[tuple[str, str], ...] = (
    ("공용 (files/)", "files"),
    (f"스킬별 ({SKILL_FILES_DIRNAME}/)", SKILL_FILES_DIRNAME),
)


class FilePanel(QWidget):
    """files/·skill-files/ 트리 뷰 + 안내/새로고침. app.py가 독 위젯으로 배치한다."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_dir: Path | None = None
        self._model: QFileSystemModel | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        header = QHBoxLayout()
        self._root_combo = QComboBox()
        for label, _dirname in _ROOTS:
            self._root_combo.addItem(label)
        self._root_combo.setToolTip(
            "공용: 플러그인 루트 files/로 복사 (${ROOT}/files/… 참조)\n"
            f"스킬별: {SKILL_FILES_DIRNAME}/<스킬 이름>/이 그 스킬 SKILL.md 옆으로 "
            "복사 (${CLAUDE_SKILL_DIR}/… 참조)"
        )
        self._root_combo.currentIndexChanged.connect(lambda _i: self.refresh())
        header.addWidget(self._root_combo, 1)
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

        self._refresh_visibility(active=False)

    # --- 공개 API ---

    def set_project_dir(self, project_dir: str | Path | None) -> None:
        """프로젝트 저장 파일이 있는 디렉토리를 설정한다 (app이 저장/열기/새 프로젝트
        시 ``_current_path`` 기준으로 호출)."""
        self._project_dir = Path(project_dir) if project_dir else None
        self.refresh()

    def files_root(self) -> str | None:
        """공용 files/ 루트 경로 — 실존할 때만 반환(provider가 조회하는 단일 진실)."""
        return self._existing_root("files")

    def skill_files_root(self) -> str | None:
        """skill-files/ 루트 경로 — 실존할 때만 반환 (WP-SF provider)."""
        return self._existing_root(SKILL_FILES_DIRNAME)

    def refresh(self) -> None:
        """파일시스템 변경을 반영한다 — QFileSystemModel은 자동 감시하지만 루트
        생성 직후에는 재바인딩이 필요하다."""
        root = self._existing_root(self._current_dirname())
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

    def _current_dirname(self) -> str:
        return _ROOTS[self._root_combo.currentIndex()][1]

    def _existing_root(self, dirname: str) -> str | None:
        if self._project_dir is None:
            return None
        root = self._project_dir / dirname
        return str(root) if root.is_dir() else None

    def _create_root_folder(self) -> None:
        if self._project_dir is None:
            return
        (self._project_dir / self._current_dirname()).mkdir(parents=True, exist_ok=True)
        self.refresh()

    def _refresh_visibility(self, *, active: bool) -> None:
        has_project = self._project_dir is not None
        dirname = self._current_dirname()
        if not has_project:
            self._info_label.setText(
                f"프로젝트를 저장하면 {dirname}/ 폴더를 사용할 수 있습니다."
            )
        elif not active:
            hint = (
                "" if dirname == "files"
                else " 하위에 <스킬 이름>/ 폴더를 만들어 파일을 넣으세요."
            )
            self._info_label.setText(
                f"{dirname}/ 폴더가 없습니다. 아래 버튼으로 만드세요.{hint}"
            )
        self._create_btn.setText(f"{dirname} 폴더 만들기")
        self._info_label.setVisible(not active)
        self._create_btn.setVisible(has_project and not active)
        self._tree.setVisible(active)
