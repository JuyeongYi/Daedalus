# daedalus/view/editors/hook_panel.py
"""훅 라이브러리 상주 탭 (WP-HK).

예전에는 도구 메뉴의 모달 다이얼로그였고, 훅 하나가 커맨드 하나였다. CC 스키마
확인 결과 훅은 **이벤트 31종 × 핸들러 5종**이고 그룹 하나에 핸들러가 여럿
붙는 3단 구조라, 모달 폼으로는 다룰 수 없어 프로젝트 FSM·블랙보드와 같은
상주 탭으로 옮겼다.

편집은 모델 직접 기록 + notify(structure 채널)다 — 블랙보드 패널과 같은 정책
(undo 커맨드화 범위 밖). MCP 경로(create_hook/update_hook)는 커맨드를 거친다.
"""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.plugin.hook import (
    HOOK_HANDLER_LABELS,
    HOOK_HANDLER_TYPES,
    MATCHER_EVENTS,
    UNDOCUMENTED_EVENTS,
    AgentHook,
    CommandHook,
    HookDef,
    HookEvent,
    HookShell,
    HttpHook,
    McpToolHook,
    PromptHook,
)
from daedalus.model.plugin.hook_presets import BUILTIN_HOOK_PRESETS, preset_copy


def event_label(event: HookEvent) -> str:
    """콤보에 보일 이벤트 문구 — matcher 미지원/미문서화를 함께 알린다."""
    suffix = []
    if event not in MATCHER_EVENTS:
        suffix.append("matcher 없음")
    if event in UNDOCUMENTED_EVENTS:
        suffix.append("미문서화")
    return f"{event.value}  ({', '.join(suffix)})" if suffix else event.value


class _HandlerForm(QWidget):
    """선택된 핸들러 하나의 폼. 타입이 바뀌면 통째로 다시 만든다.

    타입별 필드가 제각각이라 한 폼에 전부 늘어놓으면 무엇이 이 타입에 유효한지
    알 수 없다 — 해당 타입의 필드만 보여준다.
    """

    def __init__(self, handler: Any, on_changed: Callable[[], None]) -> None:
        super().__init__()
        self._handler = handler
        self._on_changed = on_changed
        self._loading = True

        lay = QFormLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self._build_type_fields(lay)

        # --- 공통 (스키마의 다섯 변종 전부가 받는다) ---
        self._timeout = QSpinBox()
        self._timeout.setRange(0, 86400)
        self._timeout.setSpecialValueText("(지정 없음)")
        self._timeout.setValue(handler.timeout or 0)
        self._timeout.valueChanged.connect(self._save)
        lay.addRow("timeout(초)", self._timeout)

        self._condition = QLineEdit(handler.condition)
        self._condition.setPlaceholderText("if — permission-rule 문법 필터 (예: Bash(git *))")
        self._condition.textChanged.connect(self._save)
        lay.addRow("if", self._condition)

        self._status = QLineEdit(handler.status_message)
        self._status.setPlaceholderText("statusMessage — 실행 중 표시할 문구")
        self._status.textChanged.connect(self._save)
        lay.addRow("statusMessage", self._status)

        self._loading = False

    # ── 타입별 필드 ──

    def _build_type_fields(self, lay: QFormLayout) -> None:
        h = self._handler
        self._fields: dict[str, QWidget] = {}

        if isinstance(h, CommandHook):
            self._command = QPlainTextEdit(h.command)
            self._command.setFixedHeight(64)
            self._command.textChanged.connect(self._save)
            lay.addRow("command *", self._command)

            self._args = QLineEdit(" ".join(h.args))
            self._args.setPlaceholderText("args — 공백 구분 (exec 형태로 넘길 때만)")
            self._args.textChanged.connect(self._save)
            lay.addRow("args", self._args)

            self._shell = QComboBox()
            for shell in HookShell:
                self._shell.addItem(shell.value or "(기본)", shell)
            self._shell.setCurrentIndex(list(HookShell).index(h.shell))
            self._shell.currentIndexChanged.connect(self._save)
            lay.addRow("shell", self._shell)

            self._run_async = QCheckBox("async — 블로킹하지 않고 실행")
            self._run_async.setChecked(h.run_async)
            self._run_async.toggled.connect(self._save)
            lay.addRow("", self._run_async)

            self._async_rewake = QCheckBox("asyncRewake — 종료 코드 2로 깨우기")
            self._async_rewake.setChecked(h.async_rewake)
            self._async_rewake.toggled.connect(self._save)
            lay.addRow("", self._async_rewake)

        elif isinstance(h, (PromptHook, AgentHook)):
            self._prompt = QPlainTextEdit(h.prompt)
            self._prompt.setFixedHeight(72)
            self._prompt.textChanged.connect(self._save)
            lay.addRow("prompt *", self._prompt)

            self._model = QLineEdit(h.model)
            self._model.setPlaceholderText("model — 비우면 빠른 모델")
            self._model.textChanged.connect(self._save)
            lay.addRow("model", self._model)

            if isinstance(h, PromptHook):
                self._continue_on_block = QCheckBox("continueOnBlock — 차단돼도 계속")
                self._continue_on_block.setChecked(h.continue_on_block)
                self._continue_on_block.toggled.connect(self._save)
                lay.addRow("", self._continue_on_block)

        elif isinstance(h, HttpHook):
            self._url = QLineEdit(h.url)
            self._url.setPlaceholderText("https://...")
            self._url.textChanged.connect(self._save)
            lay.addRow("url *", self._url)

            self._headers = QPlainTextEdit(
                "\n".join(f"{k}: {v}" for k, v in h.headers.items())
            )
            self._headers.setFixedHeight(56)
            self._headers.setPlaceholderText("한 줄에 하나: Name: value")
            self._headers.textChanged.connect(self._save)
            lay.addRow("headers", self._headers)

            self._env = QLineEdit(" ".join(h.allowed_env_vars))
            self._env.setPlaceholderText("allowedEnvVars — 공백 구분")
            self._env.textChanged.connect(self._save)
            lay.addRow("allowedEnvVars", self._env)

        elif isinstance(h, McpToolHook):
            self._server = QLineEdit(h.server)
            self._server.textChanged.connect(self._save)
            lay.addRow("server *", self._server)

            self._tool = QLineEdit(h.tool)
            self._tool.textChanged.connect(self._save)
            lay.addRow("tool *", self._tool)

            self._input = QPlainTextEdit(
                "\n".join(f"{k}: {v}" for k, v in h.tool_input.items())
            )
            self._input.setFixedHeight(56)
            self._input.setPlaceholderText("input — 한 줄에 하나: key: value")
            self._input.textChanged.connect(self._save)
            lay.addRow("input", self._input)

    # ── 저장 ──

    @staticmethod
    def _parse_pairs(text: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for line in text.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            if key:
                out[key] = value.strip()
        return out

    def _save(self) -> None:
        if self._loading:
            return
        h = self._handler
        tv = self._timeout.value()
        h.timeout = None if tv == 0 else tv
        h.condition = self._condition.text()
        h.status_message = self._status.text()

        if isinstance(h, CommandHook):
            h.command = self._command.toPlainText()
            h.args = self._args.text().split()
            h.shell = self._shell.currentData()
            h.run_async = self._run_async.isChecked()
            h.async_rewake = self._async_rewake.isChecked()
        elif isinstance(h, (PromptHook, AgentHook)):
            h.prompt = self._prompt.toPlainText()
            h.model = self._model.text()
            if isinstance(h, PromptHook):
                h.continue_on_block = self._continue_on_block.isChecked()
        elif isinstance(h, HttpHook):
            h.url = self._url.text()
            h.headers = self._parse_pairs(self._headers.toPlainText())
            h.allowed_env_vars = self._env.text().split()
        elif isinstance(h, McpToolHook):
            h.server = self._server.text()
            h.tool = self._tool.text()
            h.tool_input = self._parse_pairs(self._input.toPlainText())

        self._on_changed()


class HookLibraryPanel(QWidget):
    """프로젝트 훅 라이브러리 편집 상주 탭.

    좌: 훅 목록. 우: 선택 훅의 이벤트/matcher + 핸들러 목록과 폼.
    """

    def __init__(
        self,
        on_notify_fn: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._project: Any = None
        self._on_notify_fn = on_notify_fn
        self._loading = False

        root = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        self._set_enabled(False)

    # ── 구성 ──

    def _build_left(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(QLabel("훅"))

        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_row_changed)
        lay.addWidget(self._list, 1)

        row = QHBoxLayout()
        add = QPushButton("＋")
        add.setToolTip("빈 훅 추가")
        add.clicked.connect(self._add_hook)
        row.addWidget(add)

        preset = QPushButton("프리셋…")
        preset.clicked.connect(self._add_from_preset)
        row.addWidget(preset)

        remove = QPushButton("삭제")
        remove.clicked.connect(self._delete_hook)
        row.addWidget(remove)
        lay.addLayout(row)
        return box

    def _build_right(self) -> QWidget:
        area = QScrollArea()
        area.setWidgetResizable(True)
        inner = QWidget()
        lay = QVBoxLayout(inner)

        form = QFormLayout()
        self._name = QLineEdit()
        self._name.setPlaceholderText("Daedalus 안에서 이 훅을 지목하는 이름")
        self._name.textChanged.connect(self._save_head)
        form.addRow("name *", self._name)

        self._description = QLineEdit()
        self._description.textChanged.connect(self._save_head)
        form.addRow("설명", self._description)

        self._event = QComboBox()
        for event in HookEvent:
            self._event.addItem(event_label(event), event)
        self._event.currentIndexChanged.connect(self._save_head)
        form.addRow("event *", self._event)

        self._matcher = QLineEdit()
        self._matcher.setPlaceholderText("matcher — 이벤트별 패턴 (도구명·에이전트명·파일명 등)")
        self._matcher.textChanged.connect(self._save_head)
        form.addRow("matcher", self._matcher)
        lay.addLayout(form)

        self._matcher_note = QLabel()
        self._matcher_note.setWordWrap(True)
        self._matcher_note.setStyleSheet("color: #cc8844;")
        lay.addWidget(self._matcher_note)

        lay.addWidget(self._build_handlers_box(), 1)

        row = QHBoxLayout()
        copy_fm = QPushButton("서브에이전트 프론트매터로 복사")
        copy_fm.setToolTip(
            "이 훅을 .claude/agents/ 에이전트 파일에 붙여넣을 YAML로 변환해 클립보드에 넣는다"
        )
        copy_fm.clicked.connect(self._copy_frontmatter)
        row.addWidget(copy_fm)

        copy_json = QPushButton("hooks.json으로 복사")
        copy_json.clicked.connect(self._copy_hooks_json)
        row.addWidget(copy_json)
        row.addStretch()
        lay.addLayout(row)

        area.setWidget(inner)
        return area

    def _build_handlers_box(self) -> QWidget:
        box = QGroupBox("핸들러 — 이 훅이 실행할 것")
        lay = QVBoxLayout(box)

        self._handler_list = QListWidget()
        self._handler_list.setFixedHeight(96)
        self._handler_list.currentRowChanged.connect(self._on_handler_row_changed)
        lay.addWidget(self._handler_list)

        row = QHBoxLayout()
        self._handler_type = QComboBox()
        for kind, label in HOOK_HANDLER_LABELS:
            self._handler_type.addItem(label, kind)
        row.addWidget(self._handler_type, 1)

        add = QPushButton("＋ 추가")
        add.clicked.connect(self._add_handler)
        row.addWidget(add)

        remove = QPushButton("삭제")
        remove.clicked.connect(self._delete_handler)
        row.addWidget(remove)
        lay.addLayout(row)

        self._handler_form_holder = QVBoxLayout()
        lay.addLayout(self._handler_form_holder)
        self._handler_form: _HandlerForm | None = None
        return box

    # ── 프로젝트 바인딩 ──

    def set_project(self, project: Any) -> None:
        self._project = project
        self._reload_list()
        self._set_enabled(project is not None)

    def _library(self) -> list[HookDef]:
        return getattr(self._project, "hook_library", None) or []

    def _set_enabled(self, on: bool) -> None:
        for w in (self._name, self._description, self._event, self._matcher):
            w.setEnabled(on)

    def _notify(self) -> None:
        if self._on_notify_fn is not None:
            self._on_notify_fn()

    # ── 목록 ──

    def _reload_list(self, select: int | None = None) -> None:
        self._loading = True
        self._list.clear()
        for hook in self._library():
            label = f"{hook.name or '(이름 없음)'}  ·  {hook.event.value}"
            if not hook.handlers:
                label += "  ⚠"
            self._list.addItem(QListWidgetItem(label))
        self._loading = False

        count = self._list.count()
        if count == 0:
            self._show_hook(None)
            return
        row = select if select is not None else 0
        self._list.setCurrentRow(max(0, min(row, count - 1)))

    def _current_hook(self) -> HookDef | None:
        row = self._list.currentRow()
        library = self._library()
        return library[row] if 0 <= row < len(library) else None

    def _on_row_changed(self, _row: int) -> None:
        if not self._loading:
            self._show_hook(self._current_hook())

    def _show_hook(self, hook: HookDef | None) -> None:
        self._loading = True
        try:
            self._name.setText(hook.name if hook else "")
            self._description.setText(hook.description if hook else "")
            if hook is not None:
                self._event.setCurrentIndex(list(HookEvent).index(hook.event))
            self._matcher.setText(hook.matcher if hook else "")
            self._set_enabled(hook is not None)
            self._sync_matcher_state(hook)
        finally:
            self._loading = False
        self._reload_handlers()

    def _sync_matcher_state(self, hook: HookDef | None) -> None:
        """matcher를 받지 않는 이벤트면 입력을 잠그고 이유를 보인다.

        받지 않는 이벤트에 matcher를 넣어 두면 설정한 사람은 걸린 줄 알지만
        CC는 무시한다 — 그래서 값이 남아 있으면 지우라고 알린다.
        """
        supported = hook is not None and hook.supports_matcher
        self._matcher.setEnabled(bool(supported))
        if hook is None:
            self._matcher_note.setText("")
        elif supported:
            self._matcher_note.setText("")
        elif hook.matcher:
            self._matcher_note.setText(
                f"⚠ {hook.event.value}는 matcher를 받지 않습니다 — "
                f"'{hook.matcher}'는 무시되고 검증 경고가 뜹니다."
            )
        else:
            self._matcher_note.setText(f"{hook.event.value}는 matcher를 받지 않습니다.")

    def _save_head(self) -> None:
        hook = self._current_hook()
        if hook is None or self._loading:
            return
        hook.name = self._name.text()
        hook.description = self._description.text()
        hook.event = self._event.currentData()
        hook.matcher = self._matcher.text()
        self._sync_matcher_state(hook)
        self._refresh_current_label()
        self._notify()

    def _refresh_current_label(self) -> None:
        hook = self._current_hook()
        item = self._list.currentItem()
        if hook is None or item is None:
            return
        label = f"{hook.name or '(이름 없음)'}  ·  {hook.event.value}"
        if not hook.handlers:
            label += "  ⚠"
        item.setText(label)

    def _add_hook(self) -> None:
        if self._project is None:
            return
        hook = HookDef(
            name=self._unique_name("new-hook"),
            description="",
            event=HookEvent.PRE_TOOL_USE,
            handlers=[CommandHook()],
        )
        self._project.hook_library.append(hook)
        self._reload_list(select=len(self._library()) - 1)
        self._notify()

    def _unique_name(self, base: str) -> str:
        existing = {h.name for h in self._library()}
        if base not in existing:
            return base
        i = 2
        while f"{base}-{i}" in existing:
            i += 1
        return f"{base}-{i}"

    def _add_from_preset(self) -> None:
        if self._project is None:
            return
        names = [p.name for p in BUILTIN_HOOK_PRESETS]
        name, ok = QInputDialog.getItem(self, "프리셋에서 추가", "훅 프리셋:", names, 0, False)
        if not ok or not name:
            return
        preset = next((p for p in BUILTIN_HOOK_PRESETS if p.name == name), None)
        if preset is None:
            return
        copy = preset_copy(preset)
        copy.name = self._unique_name(copy.name)
        self._project.hook_library.append(copy)
        self._reload_list(select=len(self._library()) - 1)
        self._notify()

    def _delete_hook(self) -> None:
        hook = self._current_hook()
        if hook is None:
            return
        row = self._list.currentRow()
        self._project.hook_library.pop(row)
        self._reload_list(select=min(row, len(self._library()) - 1))
        self._notify()

    # ── 핸들러 ──

    def _reload_handlers(self, select: int | None = None) -> None:
        hook = self._current_hook()
        self._handler_list.blockSignals(True)
        self._handler_list.clear()
        if hook is not None:
            for handler in hook.handlers:
                self._handler_list.addItem(f"{handler.kind}  ·  {handler.summary()}")
        self._handler_list.blockSignals(False)

        count = self._handler_list.count()
        if count == 0:
            self._show_handler(None)
            return
        row = select if select is not None else 0
        self._handler_list.setCurrentRow(max(0, min(row, count - 1)))
        self._show_handler(self._current_handler())

    def _current_handler(self) -> Any:
        hook = self._current_hook()
        row = self._handler_list.currentRow()
        if hook is None or not (0 <= row < len(hook.handlers)):
            return None
        return hook.handlers[row]

    def _on_handler_row_changed(self, _row: int) -> None:
        self._show_handler(self._current_handler())

    def _show_handler(self, handler: Any) -> None:
        if self._handler_form is not None:
            self._handler_form.setParent(None)
            self._handler_form.deleteLater()
            self._handler_form = None
        if handler is None:
            return
        self._handler_form = _HandlerForm(handler, self._on_handler_changed)
        self._handler_form_holder.addWidget(self._handler_form)

    def _on_handler_changed(self) -> None:
        row = self._handler_list.currentRow()
        handler = self._current_handler()
        item = self._handler_list.item(row)
        if handler is not None and item is not None:
            item.setText(f"{handler.kind}  ·  {handler.summary()}")
        self._refresh_current_label()
        self._notify()

    def _add_handler(self) -> None:
        hook = self._current_hook()
        if hook is None:
            return
        cls = HOOK_HANDLER_TYPES[self._handler_type.currentData()]
        hook.handlers.append(cls())
        self._reload_handlers(select=len(hook.handlers) - 1)
        self._refresh_current_label()
        self._notify()

    def _delete_handler(self) -> None:
        hook = self._current_hook()
        row = self._handler_list.currentRow()
        if hook is None or not (0 <= row < len(hook.handlers)):
            return
        hook.handlers.pop(row)
        self._reload_handlers(select=min(row, len(hook.handlers) - 1))
        self._refresh_current_label()
        self._notify()

    # ── 내보내기 ──

    def _copy_frontmatter(self) -> None:
        """선택 훅을 서브에이전트 프론트매터 YAML로 클립보드에 넣는다.

        프로젝트 설치 빌드는 컴파일이 자동으로 넣지만, 이 프로젝트 밖의
        에이전트 파일에 손으로 붙여넣고 싶을 때 쓴다.
        """
        from daedalus.compiler.emit import _yaml_block_lines

        hook = self._current_hook()
        if hook is None:
            return
        if not hook.handlers:
            QMessageBox.information(self, "복사", "핸들러가 없어 배출할 내용이 없습니다.")
            return
        lines = ["hooks:"] + _yaml_block_lines({hook.event.value: [hook.to_json()]}, 2)
        self._to_clipboard("\n".join(lines) + "\n", "프론트매터 YAML")

    def _copy_hooks_json(self) -> None:
        import json

        hook = self._current_hook()
        if hook is None:
            return
        if not hook.handlers:
            QMessageBox.information(self, "복사", "핸들러가 없어 배출할 내용이 없습니다.")
            return
        text = json.dumps(
            {"hooks": {hook.event.value: [hook.to_json()]}}, ensure_ascii=False, indent=2
        )
        self._to_clipboard(text + "\n", "hooks.json")

    def _to_clipboard(self, text: str, what: str) -> None:
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        QMessageBox.information(self, "복사됨", f"{what}을 클립보드에 복사했습니다.\n\n{text}")
