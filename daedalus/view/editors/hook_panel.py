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
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
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
    mcp_matcher_matches_nothing,
)
from daedalus.model.plugin.hook_presets import BUILTIN_HOOK_PRESETS, preset_copy
from daedalus.model.plugin.variables import ROOT_TOKEN


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

    def __init__(
        self,
        handler: Any,
        on_changed: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        # 부모를 반드시 받는다: 부모 없는 QWidget은 **최상위 윈도우**라, 레이아웃에
        # 붙기 전 한 프레임 동안 빈 창이 깜빡인다(핸들러를 전환할 때마다 보였다).
        super().__init__(parent)
        self._handler = handler
        self._on_changed = on_changed
        self._loading = True

        # QFormLayout을 위젯에 직접 걸면 남는 세로 공간이 행들에 균등 배분돼
        # 한 줄짜리 입력이 제멋대로 늘어난다. VBox로 감싸고 끝에 스트레치를 둬서
        # 폼은 자기 크기만 쓰고 남는 공간은 스트레치가 흡수하게 한다.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        lay = QFormLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        outer.addLayout(lay)

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

        outer.addStretch()
        self._loading = False

    def set_script_ref(self, text: str) -> None:
        """command 훅의 스크립트 산출 경로 미리보기를 갱신한다 (WP-HS).

        `${ROOT}/` 접두는 모든 훅에서 같아서 폭만 먹는다 — 떼고 보여주고 전체
        경로는 툴팁에 남긴다. 사용자가 실제로 알고 싶은 것은 파일명이다.
        """
        label = getattr(self, "_script_ref", None)
        if label is None:
            return
        prefix = f"{ROOT_TOKEN}/"
        short = text[len(prefix):] if text.startswith(prefix) else text
        label.setText(short)
        label.setToolTip(text)

    # ── 타입별 필드 ──

    def _build_type_fields(self, lay: QFormLayout) -> None:
        h = self._handler
        self._fields: dict[str, QWidget] = {}

        if isinstance(h, CommandHook):
            # 커맨드는 아무리 짧아도 파일로 나간다(WP-HS) — 여기 쓴 내용이
            # hooks/scripts/<이름>으로 저장되고 hooks.json에는 경로만 남는다.
            self._script = QPlainTextEdit(h.script)
            self._script.setMinimumHeight(120)
            self._script.textChanged.connect(self._save)
            lay.addRow("스크립트 *", self._script)

            self._script_name = QLineEdit(h.script_name)
            self._script_name.setPlaceholderText("파일명(확장자 제외) — 비우면 훅 이름")
            self._script_name.textChanged.connect(self._save)
            lay.addRow("파일명", self._script_name)

            self._script_ref = QLabel()
            self._script_ref.setStyleSheet("color: #888;")
            # 줄바꿈을 켜면 좁은 패널에서 두 줄이 되는데 QFormLayout 행 높이가
            # 한 줄 기준이라 아래쪽이 잘린다. 한 줄로 두고 긴 부분은 툴팁에 넘긴다.
            self._script_ref.setWordWrap(False)
            self._script_ref.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            lay.addRow("경로", self._script_ref)

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
            h.script = self._script.toPlainText()
            h.script_name = self._script_name.text()
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
        # 목록 행 → (훅, 전역 여부) (A1). 프로젝트 훅이 앞, 전역 훅이 뒤.
        # 전역 훅은 읽기 전용이라 편집 위젯을 잠그고 "프로젝트로 복사"만 연다.
        self._entries: list[tuple[HookDef, bool]] = []

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

        self._remove_btn = QPushButton("삭제")
        self._remove_btn.clicked.connect(self._delete_hook)
        row.addWidget(self._remove_btn)
        lay.addLayout(row)

        # 전역 훅은 여기서 고치지 않는다 — 프로젝트로 복사한 뒤 그 사본을 고친다.
        # 전역 파일을 앱에서 직접 편집하게 하면 다른 프로젝트가 조용히 함께
        # 바뀐다(어느 프로젝트에서 고쳤는지 나중에 알 길이 없다).
        self._copy_to_project_btn = QPushButton("프로젝트로 복사")
        self._copy_to_project_btn.setToolTip(
            "선택한 전역 훅(🌐)을 이 프로젝트의 라이브러리로 복사한다 — 사본은 편집할 수 있고 "
            "같은 이름이면 컴파일에서 전역을 덮는다"
        )
        self._copy_to_project_btn.clicked.connect(self._copy_global_to_project)
        lay.addWidget(self._copy_to_project_btn)
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
        # 이벤트가 31종이라 콤보만으로는 "이게 언제 도는 건데?"를 알 수 없다 —
        # 라이프사이클 다이어그램에서 고를 수 있게 한다 (A10).
        event_row = QHBoxLayout()
        event_row.addWidget(self._event, 1)
        self._lifecycle_btn = QPushButton("라이프사이클에서 선택…")
        self._lifecycle_btn.setToolTip(
            "CC 훅 라이프사이클 다이어그램에서 이벤트를 고른다"
        )
        self._lifecycle_btn.clicked.connect(self._pick_event_from_lifecycle)
        event_row.addWidget(self._lifecycle_btn)
        event_widget = QWidget()
        event_widget.setLayout(event_row)
        form.addRow("event *", event_widget)

        self._matcher = QLineEdit()
        self._matcher.setPlaceholderText(
            "matcher — 이벤트별 패턴. MCP 도구는 mcp__<서버>__<도구>, 서버 전체는 mcp__<서버>__.*"
        )
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
        # CC 스키마의 hookMatcher.hooks는 배열이다 — 한 훅이 여러 개를 순서대로
        # 실행할 수 있고, 타입이 섞여도 된다(커맨드 실행 후 에이전트 검증 등).
        box = QGroupBox("핸들러 — 이 훅이 실행할 것 (여러 개 가능, 위에서부터 순서대로)")
        self._handlers_box = box
        lay = QVBoxLayout(box)

        # 조작 줄이 맨 위 — 목록보다 아래에 있으면 무엇을 추가하는 버튼인지
        # 눈이 한 번 더 훑어야 한다. 툴바는 위에 둔다.
        row = QHBoxLayout()
        self._handler_type = QComboBox()
        for kind, label in HOOK_HANDLER_LABELS:
            self._handler_type.addItem(label, kind)
        row.addWidget(self._handler_type, 1)

        self._handler_add_btn = QPushButton("＋ 추가")
        self._handler_add_btn.clicked.connect(self._add_handler)
        row.addWidget(self._handler_add_btn)

        self._handler_remove_btn = QPushButton("삭제")
        self._handler_remove_btn.clicked.connect(self._delete_handler)
        row.addWidget(self._handler_remove_btn)
        lay.addLayout(row)

        self._handler_list = QListWidget()
        self._handler_list.setFixedHeight(96)
        self._handler_list.currentRowChanged.connect(self._on_handler_row_changed)
        lay.addWidget(self._handler_list)

        self._handler_form_holder = QVBoxLayout()
        lay.addLayout(self._handler_form_holder)

        # 명시적 스페이서가 남는 세로 공간을 흡수한다. 빈 QVBoxLayout에 stretch를
        # 줘 봐야 소용없다 — sizeHint가 0이라 여분을 나눌 대상으로 잡히지 않고,
        # 남는 공간이 위 위젯들에 흩어진다(툴바와 목록이 따로 떠 보였다).
        lay.addStretch(1)
        self._handler_form: _HandlerForm | None = None
        return box

    # ── 프로젝트 바인딩 ──

    def set_project(self, project: Any) -> None:
        self._project = project
        self._reload_list()
        self._set_enabled(project is not None)

    def _library(self) -> list[HookDef]:
        return getattr(self._project, "hook_library", None) or []

    def _global_hooks(self) -> list[HookDef]:
        """이 프로젝트가 이름으로 쓸 수 있는 전역 훅 중 **가려지지 않은** 것 (A1).

        프로젝트에 동명 훅이 있으면 그쪽이 이기므로(컴파일·검증과 같은 규칙)
        전역 쪽은 목록에서 뺀다 — 둘 다 보이면 어느 것이 실제로 쓰이는지
        화면만 봐서는 알 수 없다.
        """
        from daedalus.model.plugin.hook_store import load_global_hooks

        shadowed = {h.name for h in self._library()}
        return [h for h in load_global_hooks() if h.name not in shadowed]

    def _set_enabled(self, on: bool, *, read_only: bool = False) -> None:
        """편집 위젯 활성화. read_only면 값은 보이되 고칠 수 없다 (전역 훅, A1)."""
        editable = on and not read_only
        for w in (self._name, self._description, self._event, self._matcher):
            w.setEnabled(editable)
        self._remove_btn.setEnabled(editable)
        self._handler_add_btn.setEnabled(editable)
        self._handler_remove_btn.setEnabled(editable)
        self._copy_to_project_btn.setEnabled(on and read_only)

    def _notify(self) -> None:
        if self._on_notify_fn is not None:
            self._self_notify = True
            try:
                self._on_notify_fn()
            finally:
                self._self_notify = False

    def refresh_external(self) -> None:
        """바깥(MCP 등)에서 hook_library가 바뀌었을 때 목록을 다시 그린다.

        이 패널은 자기 편집만 알았다 — MCP `create_hook`이 라이브러리에 훅을
        넣어도 목록에 나타나지 않았다(사용자 보고). 자기 편집이 발화한 notify가
        되돌아온 경우는 건너뛴다: 그때 목록을 다시 그리면 사용자가 타이핑 중인
        폼의 선택이 리셋된다.
        """
        if getattr(self, "_self_notify", False):
            return
        current = self._list.currentRow()
        self._reload_list(select=current if current >= 0 else None)

    # ── 목록 ──

    def _reload_list(self, select: int | None = None) -> None:
        self._loading = True
        self._list.clear()
        # 프로젝트 훅이 앞, 전역 훅이 뒤 (A1). 프로젝트 훅의 행 번호가
        # hook_library 인덱스와 일치해야 기존 추가/선택 경로가 그대로 동작한다.
        self._entries = [(h, False) for h in self._library()]
        if self._project is not None:
            self._entries += [(h, True) for h in self._global_hooks()]
        for hook, is_global in self._entries:
            item = QListWidgetItem(self._hook_label(hook, is_global))
            if is_global:
                item.setForeground(QColor("#888888"))
                item.setToolTip("전역 훅 (~/.daedalus/hooks/) — 읽기 전용")
            self._list.addItem(item)
        self._loading = False

        count = self._list.count()
        if count == 0:
            self._show_hook(None)
            return
        row = select if select is not None else 0
        self._list.setCurrentRow(max(0, min(row, count - 1)))

    @staticmethod
    def _hook_label(hook: HookDef, is_global: bool = False) -> str:
        label = f"{hook.name or '(이름 없음)'}  ·  {hook.event.value}"
        if not hook.handlers:
            label += "  ⚠"
        return f"🌐 {label}" if is_global else label

    def _current_hook(self) -> HookDef | None:
        row = self._list.currentRow()
        return self._entries[row][0] if 0 <= row < len(self._entries) else None

    def _current_is_global(self) -> bool:
        """선택된 것이 전역 훅인가 — 편집을 막는 판정의 단일 진실 (A1)."""
        row = self._list.currentRow()
        return bool(0 <= row < len(self._entries) and self._entries[row][1])

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
            self._set_enabled(hook is not None, read_only=self._current_is_global())
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
            # MCP 도구 매칭의 함정: 서버 이름까지만 쓰면 정규식이 아니라 정확한
            # 문자열로 비교돼 아무것도 맞지 않는다(CC hooks#match-mcp-tools).
            if mcp_matcher_matches_nothing(hook.matcher):
                self._matcher_note.setText(
                    f"⚠ '{hook.matcher.strip()}'는 어떤 MCP 도구와도 맞지 않습니다 — "
                    f"'{hook.matcher.strip()}__.*'처럼 도구 부분을 붙이세요."
                )
            else:
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
        if hook is None or self._loading or self._current_is_global():
            return
        hook.name = self._name.text()
        hook.description = self._description.text()
        hook.event = self._event.currentData()
        hook.matcher = self._matcher.text()
        self._sync_matcher_state(hook)
        self._sync_script_ref()  # 훅 이름이 스크립트 파일명이 된다
        self._refresh_current_label()
        self._notify()

    def _refresh_current_label(self) -> None:
        hook = self._current_hook()
        item = self._list.currentItem()
        if hook is None or item is None:
            return
        item.setText(self._hook_label(hook, self._current_is_global()))

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
        if hook is None or self._current_is_global():
            return
        # 인덱스가 아니라 identity로 지운다 — 목록에는 전역 훅도 섞여 있다.
        library = self._project.hook_library
        row = next((i for i, h in enumerate(library) if h is hook), -1)
        if row < 0:
            return
        library.pop(row)
        self._reload_list(select=min(row, len(self._library()) - 1))
        self._notify()

    def _pick_event_from_lifecycle(self) -> None:
        """라이프사이클 다이얼로그를 열고 결과를 콤보에 반영한다 (A10).

        여기는 **호출부일 뿐**이다 — 다이얼로그는 재사용 위젯이고, 이벤트를
        고르는 다른 표면이 생기면 같은 것을 쓴다. 콤보에 반영하면 기존
        `currentIndexChanged` → `_save_head` 경로가 그대로 돌아, 이 버튼만
        모델 쓰기를 따로 하지 않는다.
        """
        from daedalus.view.widgets.lifecycle_picker import HookLifecycleDialog

        hook = self._current_hook()
        if hook is None or self._current_is_global():
            return
        # parent는 패널이 아니라 **최상위 창** — 깊이 중첩된 위젯을 부모로 주면
        # 일부 플랫폼에서 다이얼로그가 메인 창 뒤에 열려 "버튼을 눌렀더니
        # 멈춤"으로 보인다(모달 대기 + 다이얼로그 비가시, 사용자 보고).
        dialog = HookLifecycleDialog(hook.event, parent=self.window())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        chosen = dialog.selected
        if chosen is not None:
            self._event.setCurrentIndex(list(HookEvent).index(chosen))

    def _copy_global_to_project(self) -> None:
        """선택한 전역 훅을 이 프로젝트 라이브러리로 복사한다 (A1).

        **이름을 그대로 유지한다** — 복사의 목적이 "이 프로젝트에서는 이 훅을
        이렇게 쓴다"이고, 동명 프로젝트 훅이 전역을 덮는 것이 병합 규칙이므로
        참조하는 컴포넌트를 손댈 필요가 없다(이름을 바꾸면 참조가 전역을 계속
        가리켜, 고친 사본이 아무 데도 쓰이지 않는 일이 생긴다).

        복사는 `preset_copy`와 같은 이유로 **깊은 복사**다 — 얕게 복사하면 이
        프로젝트에서 고친 핸들러가 다음번 전역 로드 결과를 오염시킨다.
        """
        hook = self._current_hook()
        if self._project is None or hook is None or not self._current_is_global():
            return
        copy = preset_copy(hook)
        copy.name = hook.name  # preset_copy는 이름을 보존하지만 의도를 명시한다
        self._project.hook_library.append(copy)
        self._reload_list(select=len(self._library()) - 1)
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
            # setParent(None)하면 한 프레임 동안 최상위 윈도우가 돼서 빈 "python"
            # 창이 깜빡인다(사용자 보고) — hide()로 즉시 숨긴 뒤 deleteLater로
            # 이벤트 루프 복귀 후 삭제한다. 레이아웃에서 빼는 것은 hide가 처리.
            self._handler_form.hide()
            self._handler_form.deleteLater()
            self._handler_form = None
        if handler is None:
            return
        self._handler_form = _HandlerForm(
            handler, self._on_handler_changed, self._handlers_box,
        )
        self._handler_form_holder.addWidget(self._handler_form)
        self._sync_script_ref()

    def _sync_script_ref(self) -> None:
        """스크립트가 어느 경로로 나갈지 보여준다 (WP-HS).

        파일명은 훅 이름·shell·같은 훅의 command 핸들러 수에 따라 달라지므로,
        결과를 직접 보여주지 않으면 사용자가 예측할 수 없다.
        """
        form, hook = self._handler_form, self._current_hook()
        if form is None or hook is None:
            return
        row = self._handler_list.currentRow()
        form.set_script_ref(hook.script_refs().get(row, ""))

    def _on_handler_changed(self) -> None:
        row = self._handler_list.currentRow()
        handler = self._current_handler()
        item = self._handler_list.item(row)
        if handler is not None and item is not None:
            item.setText(f"{handler.kind}  ·  {handler.summary()}")
        self._sync_script_ref()
        self._refresh_current_label()
        self._notify()

    def _add_handler(self) -> None:
        hook = self._current_hook()
        if hook is None or self._current_is_global():
            return
        cls = HOOK_HANDLER_TYPES[self._handler_type.currentData()]
        hook.handlers.append(cls())
        self._reload_handlers(select=len(hook.handlers) - 1)
        self._refresh_current_label()
        self._notify()

    def _delete_handler(self) -> None:
        hook = self._current_hook()
        row = self._handler_list.currentRow()
        if hook is None or self._current_is_global():
            return
        if not (0 <= row < len(hook.handlers)):
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
