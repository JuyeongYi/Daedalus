# daedalus/view/editors/workspace_editor.py
"""작업 폴더 문서 편집 탭 2종 — `.claude/CLAUDE.md`와 `.claude/rules/` (WP-WD).

진입점: MainWindow 상주 탭(인덱스 3·4, 닫기 불가). 둘을 한 탭에 목록으로 묶지
않고 **각각 최상위 탭**으로 둔 것은 사용자 확정이다 — CLAUDE.md는 하나뿐이고
규칙은 여럿이라 성격이 다르다.

본문 편집기는 스킬 본문과 같은 `SectionContentPanel`을 그대로 쓴다. `WorkspaceDoc`이
`id`와 `body`를 갖고 있으므로 본문 undo 스택(`BodyDocumentRegistry`, WP-BU)도
자동으로 붙는다 — 문서를 옮겨다녀도 되돌리기 이력이 유지된다.

구조 편집(규칙 추가·삭제·이름 변경)은 모델에 직접 기록하고 notify한다 — 블랙보드
패널·훅 패널과 같은 정책이다(undo 커맨드화 범위 밖).
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.workspace_doc import WorkspaceDoc
from daedalus.model.project import PluginProject
from daedalus.view.editors import body_documents
from daedalus.view.editors.body_editor import (
    SectionContentPanel,
    make_variable_popup,
    toggle_variable_popup,
)
from daedalus.view.widgets.tag_input import TagInput


def _is_local(project: PluginProject | None) -> bool:
    if project is None:
        return False
    return getattr(project, "build_target", None) is BuildTarget.LOCAL


class _WorkspaceDocPanelBase(QWidget):
    """두 탭의 공통 뼈대 — 안내 라벨 + 본문 편집기.

    마켓플레이스 빌드에서는 배출되지 않으므로 안내를 띄운다. 편집 자체는 막지
    않는다 — 빌드 타깃은 프로젝트 속성에서 언제든 바뀌고, 그때 쓰던 내용이 사라져
    있으면 곤란하다.
    """

    def __init__(self, on_notify_fn: Callable[..., None] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: PluginProject | None = None
        self._notify = on_notify_fn

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._notice = QLabel("")
        self._notice.setWordWrap(True)
        self._notice.setContentsMargins(10, 6, 10, 6)
        self._notice.setVisible(False)
        self._layout.addWidget(self._notice)

        self._content = SectionContentPanel()
        self._content.content_changed.connect(self._on_content_changed)
        # 변수 삽입 — ComponentEditor와 **같은 배선**이다. 이 연결이 빠져 있던
        # 동안 변수 버튼은 시그널만 쏘고 청취자가 없어 아무 일도 하지 않았다.
        self._var_popup = make_variable_popup(self._content)
        self._content.variable_insert_requested.connect(self._on_variable_insert)

    # --- 공통 ---

    def _on_variable_insert(self) -> None:
        toggle_variable_popup(self._content, self._var_popup)

    def notify(self, scope: str = "structure") -> None:
        if self._notify is not None:
            self._notify(scope)

    def _on_content_changed(self) -> None:
        self.notify("content")

    def _refresh_notice(self) -> None:
        show = self._project is not None and not _is_local(self._project)
        self._notice.setVisible(show)
        if show:
            self._notice.setText(
                "⚠ 빌드 타깃이 <b>마켓플레이스</b>라 이 문서는 배출되지 않습니다 — "
                "플러그인은 설치 대상 작업 폴더의 <code>.claude/</code>에 쓸 수 "
                "없습니다. 파일 → 프로젝트 속성…에서 로컬 플러그인으로 바꾸세요."
            )

    def content_panel(self) -> SectionContentPanel:
        """테스트·호출자가 본문 편집기에 직접 닿는 접근자."""
        return self._content


class ClaudeMdPanel(_WorkspaceDocPanelBase):
    """`.claude/CLAUDE.md`의 이 플러그인 구역 편집 (WP-WD/D9).

    파일 전체가 아니라 **구역**을 편집한다는 점을 화면에서 말해 준다 — 그렇지
    않으면 "내 CLAUDE.md가 통째로 대체되나?"라는 오해를 부른다.
    """

    def __init__(self, on_notify_fn=None, parent: QWidget | None = None) -> None:
        super().__init__(on_notify_fn, parent)

        # 라벨|필드 행은 QFormLayout으로 — 행이 하나뿐이어도 나중에 늘 때
        # 라벨 폭이 자동으로 공유된다(ad-hoc HBox 나열이 계단을 만든다).
        header = QWidget()
        form = QFormLayout(header)
        form.setContentsMargins(10, 6, 10, 6)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._title = QLineEdit()
        self._title.setPlaceholderText("(비우면 프로젝트 이름)")
        self._title.textChanged.connect(self._on_title_changed)
        form.addRow("구역 제목 (H1)", self._title)
        self._layout.addWidget(header)

        hint = QLabel(
            "작업 폴더의 <code>.claude/CLAUDE.md</code> 안에 이 플러그인 전용 구역"
            "(<code>&lt;!-- daedalus:… open/close --&gt;</code>)으로 들어갑니다. "
            "구역 밖의 기존 내용은 건드리지 않습니다."
        )
        hint.setWordWrap(True)
        hint.setContentsMargins(10, 0, 10, 6)
        self._layout.addWidget(hint)
        self._layout.addWidget(self._content, 1)

    def set_project(self, project: PluginProject | None) -> None:
        self._project = project
        self._refresh_notice()
        if project is None:
            self._title.blockSignals(True)
            self._title.clear()
            self._title.blockSignals(False)
            self._content.setEnabled(False)
            return
        self._content.setEnabled(True)
        # 문서가 없으면 지금 만든다. 본문이 비어 있으면 컴파일이 아무것도 내보내지
        # 않으므로(검증도 조용하다) 미리 만들어 두는 편이 UX가 단순하다 — 사용자는
        # "만들기" 버튼을 누를 필요 없이 바로 타이핑한다.
        if project.claude_md is None:
            project.claude_md = WorkspaceDoc(name=project.name)
        self._title.blockSignals(True)
        self._title.setText(project.claude_md.name)
        self._title.blockSignals(False)
        self._content.show_body(project.claude_md)

    def _on_title_changed(self, text: str) -> None:
        if self._project is None or self._project.claude_md is None:
            return
        self._project.claude_md.name = text.strip() or self._project.name
        self.notify("content")


class _RuleTree(QTreeWidget):
    """규칙 목록 트리 — 최상위 행이 규칙, 자식 행이 적용 경로(읽기 전용 표시).

    파일 이름만 보이던 QListWidget을 대체한다(사용자 요청 — "적용 경로도 같이
    보고 싶다"). 표가 아니라 트리인 이유: 목록 폭이 220px라 경로 열은 glob이
    잘려나가고, 자식 행이면 좁은 폭에서도 줄 단위로 읽힌다.

    QListWidget 시절의 행 단위 API(``count``/``currentRow``/``setCurrentRow``/
    ``item``)를 유지한다 — 패널과 테스트가 "규칙 = 행 인덱스"로 계속 말한다.
    경로 자식을 클릭하면 그 규칙(부모)을 선택한 것으로 재매핑한다.
    """

    current_row_changed = Signal(int)
    row_double_clicked = Signal(int)

    _PATH_DIM = QColor(128, 128, 128)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.currentItemChanged.connect(self._on_current_item_changed)
        self.itemDoubleClicked.connect(self._on_double_clicked)

    # --- 목록 구성 ---

    def set_rules(self, docs: list[WorkspaceDoc]) -> None:
        self.blockSignals(True)
        self.clear()
        for doc in docs:
            item = QTreeWidgetItem([doc.name])
            self._fill_paths(item, doc.paths)
            self.addTopLevelItem(item)
            item.setExpanded(True)
        self.blockSignals(False)

    def update_row_paths(self, row: int, paths: list[str]) -> None:
        """현재 편집 중인 규칙의 경로 자식을 제자리 갱신 (전체 재구성 없이)."""
        item = self.topLevelItem(row)
        if item is None:
            return
        self.blockSignals(True)
        self._fill_paths(item, paths)
        item.setExpanded(True)
        self.blockSignals(False)

    def _fill_paths(self, item: QTreeWidgetItem, paths: list[str]) -> None:
        item.takeChildren()
        if paths:
            for p in paths:
                item.addChild(self._path_child(p, italic=False))
        else:
            item.addChild(self._path_child("(항상 로드)", italic=True))

    def _path_child(self, text: str, italic: bool) -> QTreeWidgetItem:
        child = QTreeWidgetItem([text])
        child.setForeground(0, QBrush(self._PATH_DIM))
        font = child.font(0)
        font.setItalic(italic)
        child.setFont(0, font)
        return child

    # --- QListWidget 호환 행 API ---

    def count(self) -> int:
        return self.topLevelItemCount()

    def item(self, row: int) -> QTreeWidgetItem | None:
        return self.topLevelItem(row)

    def currentRow(self) -> int:
        item = self.currentItem()
        if item is None:
            return -1
        if item.parent() is not None:
            item = item.parent()
        return self.indexOfTopLevelItem(item)

    def setCurrentRow(self, row: int) -> None:
        if 0 <= row < self.topLevelItemCount():
            self.setCurrentItem(self.topLevelItem(row))

    # --- 시그널 매핑 ---

    def _on_current_item_changed(self, current, _previous) -> None:
        if current is None:
            self.current_row_changed.emit(-1)
            return
        parent = current.parent()
        if parent is not None:
            # 경로 자식 클릭 = 그 규칙 선택 — 재진입해 부모 경로로 다시 온다.
            self.setCurrentItem(parent)
            return
        self.current_row_changed.emit(self.indexOfTopLevelItem(current))

    def _on_double_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        if item.parent() is None:
            self.row_double_clicked.emit(self.indexOfTopLevelItem(item))


class RulesPanel(_WorkspaceDocPanelBase):
    """`.claude/rules/<이름>.md` 편집 — 파일이 여럿이라 선택 목록을 둔다."""

    def __init__(self, on_notify_fn=None, parent: QWidget | None = None) -> None:
        super().__init__(on_notify_fn, parent)

        split = QWidget()
        row = QHBoxLayout(split)
        row.setContentsMargins(0, 0, 0, 0)

        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(10, 6, 6, 6)
        left_lay.addWidget(QLabel("규칙 파일"))
        self._list = _RuleTree()
        self._list.current_row_changed.connect(self._on_row_changed)
        self._list.row_double_clicked.connect(lambda _row: self._rename_current())
        left_lay.addWidget(self._list, 1)

        buttons = QHBoxLayout()
        self._btn_add = QPushButton("＋ 규칙")
        self._btn_add.clicked.connect(self._add_rule)
        self._btn_del = QPushButton("삭제")
        self._btn_del.clicked.connect(self._delete_current)
        buttons.addWidget(self._btn_add)
        buttons.addWidget(self._btn_del)
        left_lay.addLayout(buttons)
        left.setMaximumWidth(220)
        row.addWidget(left)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        hint = QLabel(
            "파일 하나가 규칙 하나입니다. 적용 경로를 비우면 매 세션 항상 로드됩니다."
        )
        hint.setWordWrap(True)
        hint.setContentsMargins(6, 6, 10, 6)
        right_lay.addWidget(hint)

        # paths 프론트매터(A13) — raw text가 아니라 필드로 편집하고 빌드 때
        # `---\npaths: [...]\n---`로 기입한다.
        # ClaudeMdPanel의 제목 행과 같은 정렬 규칙 — QFormLayout이 라벨 열을 잡는다.
        paths_row = QWidget()
        paths_form = QFormLayout(paths_row)
        paths_form.setContentsMargins(6, 0, 10, 6)
        paths_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        self._paths = TagInput()
        self._paths.setToolTip(
            "glob 패턴 — 예: src/**/*.ts, lib/**, **/test_*.py\n"
            "하나라도 지정하면 그 경로를 다룰 때만 이 규칙이 로드됩니다."
        )
        self._paths.tags_changed.connect(self._on_paths_changed)
        paths_form.addRow("적용 경로 (비우면 항상 로드)", self._paths)
        right_lay.addWidget(paths_row)

        right_lay.addWidget(self._content, 1)
        row.addWidget(right, 1)

        self._layout.addWidget(split, 1)

    # --- 프로젝트 배선 ---

    def set_project(self, project: PluginProject | None) -> None:
        self._project = project
        self._refresh_notice()
        self._rebuild()

    def _rules(self) -> list[WorkspaceDoc]:
        return list(self._project.rules) if self._project is not None else []

    def _rebuild(self, select: int = 0) -> None:
        self._list.set_rules(self._rules())
        rules = self._rules()
        enabled = self._project is not None
        self._btn_add.setEnabled(enabled)
        self._btn_del.setEnabled(enabled and bool(rules))
        if rules:
            self._list.setCurrentRow(min(max(select, 0), len(rules) - 1))
        else:
            self._content.setEnabled(False)
            self._paths.setEnabled(False)
            self._paths.set_tags([])

    def _on_row_changed(self, row: int) -> None:
        rules = self._rules()
        if 0 <= row < len(rules):
            self._content.setEnabled(True)
            self._paths.setEnabled(True)
            # set_tags는 시그널을 쏘지 않는다(add/remove만 쏜다) — 로드가
            # _on_paths_changed를 깨워 빈 목록을 모델에 되쓰는 일은 없다.
            self._paths.set_tags(list(rules[row].paths))
            self._content.show_body(rules[row])
        else:
            self._content.setEnabled(False)
            self._paths.setEnabled(False)
            self._paths.set_tags([])

    def _current_rule(self) -> WorkspaceDoc | None:
        rules = self._rules()
        row = self._list.currentRow()
        return rules[row] if 0 <= row < len(rules) else None

    def _on_paths_changed(self) -> None:
        """paths 편집 → 모델 직접 기록 + notify (구조 편집과 같은 정책)."""
        doc = self._current_rule()
        if doc is None:
            return
        doc.paths = self._paths.get_tags()
        # 목록 트리의 경로 자식도 즉시 따라간다 — 편집과 표시가 어긋나면
        # "저장 안 됐나?"라는 오해를 부른다.
        self._list.update_row_paths(self._list.currentRow(), doc.paths)
        self.notify("content")

    # --- 구조 편집 ---

    def _ask_name(self, title: str, initial: str = "") -> str | None:
        name, ok = QInputDialog.getText(
            self, title, "파일 이름 (.md 제외, 소문자·숫자·하이픈):", text=initial
        )
        if not ok:
            return None
        name = name.strip()
        if not name:
            return None
        if any(doc.name == name for doc in self._rules() if doc.name != initial):
            QMessageBox.warning(
                self, "이름 중복",
                f"'{name}' 규칙이 이미 있습니다 — 이름이 곧 파일명이라 서로 덮어씁니다.",
            )
            return None
        return name

    def _add_rule(self) -> None:
        if self._project is None:
            return
        name = self._ask_name("규칙 추가")
        if name is None:
            return
        self._project.rules.append(WorkspaceDoc(name=name))
        self._rebuild(select=len(self._project.rules) - 1)
        self.notify("structure")

    def _rename_current(self) -> None:
        row = self._list.currentRow()
        rules = self._rules()
        if not (0 <= row < len(rules)):
            return
        name = self._ask_name("규칙 이름 변경", rules[row].name)
        if name is None:
            return
        rules[row].name = name
        self._rebuild(select=row)
        self.notify("structure")

    def _delete_current(self) -> None:
        row = self._list.currentRow()
        rules = self._rules()
        if self._project is None or not (0 <= row < len(rules)):
            return
        doc = rules[row]
        answer = QMessageBox.question(
            self, "규칙 삭제", f"'{doc.name}' 규칙을 삭제할까요?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._project.rules.remove(doc)
        body_documents.registry().discard(doc)
        self._rebuild(select=row)
        self.notify("structure")
