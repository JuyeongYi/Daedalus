# daedalus/view/editors/hook_handler_form.py
"""훅 핸들러 하나의 편집 폼 — 타입별 필드 구성·저장 (WP-11, `hook_panel.py`에서 분리).

**왜 갈랐는가.** ① `hook_panel.py`가 859줄이라 코드 위생 경계(~800)를 넘어
있었고, 폼은 패널의 목록·헤드 편집과 책임이 다르다. ② 타입별 필드 구성과
저장이 **같은 다섯 분기를 두 벌** 갖고 있었다 — 핸들러 종류를 하나 더하면 두
사다리를 다 고쳐야 하고, 한쪽만 고치면 "폼에는 보이는데 저장되지 않는"
조용한 실패가 된다(원칙 5).

그래서 두 사다리를 `functools.singledispatch` 두 벌로 바꿨다. 핸들러 종류를
더할 때 등록을 빠뜨리면 **기저 폴백**(공통 필드만 있는 폼 / 공통 필드만 저장)이
돌고 조용히 넘어가는 대신, `tests/view/editors/test_hook_handler_form.py`가
`HOOK_HANDLER_TYPES`의 모든 종류에 등록이 있는지를 양방향으로 고정한다 —
모델의 종류 표가 곧 폼의 종류 표다.

`from __future__ import annotations` 아래라 등록은 `@f.register(Cls)` **명시
인자**다(문자열 주석 기반 등록은 실패한다).
"""
from __future__ import annotations

from functools import singledispatch
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.plugin.hook import (
    AgentHook,
    CommandHook,
    HookHandler,
    HookShell,
    HttpHook,
    McpToolHook,
    PromptHook,
)
from daedalus.model.plugin.variables import ROOT_TOKEN


# ─────────────────────── 타입별 필드 구성 (폼 → 위젯) ───────────────────────


@singledispatch
def build_type_fields(handler: HookHandler, form: "_HandlerForm", lay: QFormLayout) -> None:
    """핸들러 종류 고유 필드를 폼에 붙인다. 폴백은 **공통 필드만**.

    폴백이 조용하지 않은 이유: 등록 누락은 패널이 아니라 테스트가 잡는다
    (모듈 docstring). 런타임에서 터뜨리면 알 수 없는 종류가 든 프로젝트를
    아예 열 수 없게 된다 — 깨진 파일은 경고로 알리고 편집은 계속한다.
    """
    return None


@build_type_fields.register(CommandHook)
def _(handler: CommandHook, form: "_HandlerForm", lay: QFormLayout) -> None:
    # 커맨드는 아무리 짧아도 파일로 나간다(WP-HS) — 여기 쓴 내용이
    # hooks/scripts/<이름>으로 저장되고 hooks.json에는 경로만 남는다.
    form._script = QPlainTextEdit(handler.script)
    form._script.setMinimumHeight(120)
    form._script.textChanged.connect(form._save)
    lay.addRow("스크립트 *", form._script)

    form._script_name = QLineEdit(handler.script_name)
    form._script_name.setPlaceholderText("파일명(확장자 제외) — 비우면 훅 이름")
    form._script_name.textChanged.connect(form._save)
    lay.addRow("파일명", form._script_name)

    form._script_ref = QLabel()
    form._script_ref.setStyleSheet("color: #888;")
    # 줄바꿈을 켜면 좁은 패널에서 두 줄이 되는데 QFormLayout 행 높이가
    # 한 줄 기준이라 아래쪽이 잘린다. 한 줄로 두고 긴 부분은 툴팁에 넘긴다.
    form._script_ref.setWordWrap(False)
    form._script_ref.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
    )
    lay.addRow("경로", form._script_ref)

    form._args = QLineEdit(" ".join(handler.args))
    form._args.setPlaceholderText("args — 공백 구분 (exec 형태로 넘길 때만)")
    form._args.textChanged.connect(form._save)
    lay.addRow("args", form._args)

    form._shell = QComboBox()
    for shell in HookShell:
        form._shell.addItem(shell.value or "(기본)", shell)
    form._shell.setCurrentIndex(list(HookShell).index(handler.shell))
    form._shell.currentIndexChanged.connect(form._save)
    lay.addRow("shell", form._shell)

    form._run_async = QCheckBox("async — 블로킹하지 않고 실행")
    form._run_async.setChecked(handler.run_async)
    form._run_async.toggled.connect(form._save)
    lay.addRow("", form._run_async)

    form._async_rewake = QCheckBox("asyncRewake — 종료 코드 2로 깨우기")
    form._async_rewake.setChecked(handler.async_rewake)
    form._async_rewake.toggled.connect(form._save)
    lay.addRow("", form._async_rewake)


def _build_prompt_fields(handler: Any, form: "_HandlerForm", lay: QFormLayout) -> None:
    """prompt/model 두 줄 — PromptHook·AgentHook 공통(둘은 형제다)."""
    form._prompt = QPlainTextEdit(handler.prompt)
    form._prompt.setFixedHeight(72)
    form._prompt.textChanged.connect(form._save)
    lay.addRow("prompt *", form._prompt)

    form._model = QLineEdit(handler.model)
    form._model.setPlaceholderText("model — 비우면 빠른 모델")
    form._model.textChanged.connect(form._save)
    lay.addRow("model", form._model)


@build_type_fields.register(AgentHook)
def _(handler: AgentHook, form: "_HandlerForm", lay: QFormLayout) -> None:
    _build_prompt_fields(handler, form, lay)


@build_type_fields.register(PromptHook)
def _(handler: PromptHook, form: "_HandlerForm", lay: QFormLayout) -> None:
    _build_prompt_fields(handler, form, lay)

    form._continue_on_block = QCheckBox("continueOnBlock — 차단돼도 계속")
    form._continue_on_block.setChecked(handler.continue_on_block)
    form._continue_on_block.toggled.connect(form._save)
    lay.addRow("", form._continue_on_block)


@build_type_fields.register(HttpHook)
def _(handler: HttpHook, form: "_HandlerForm", lay: QFormLayout) -> None:
    form._url = QLineEdit(handler.url)
    form._url.setPlaceholderText("https://...")
    form._url.textChanged.connect(form._save)
    lay.addRow("url *", form._url)

    form._headers = QPlainTextEdit(
        "\n".join(f"{k}: {v}" for k, v in handler.headers.items())
    )
    form._headers.setFixedHeight(56)
    form._headers.setPlaceholderText("한 줄에 하나: Name: value")
    form._headers.textChanged.connect(form._save)
    lay.addRow("headers", form._headers)

    form._env = QLineEdit(" ".join(handler.allowed_env_vars))
    form._env.setPlaceholderText("allowedEnvVars — 공백 구분")
    form._env.textChanged.connect(form._save)
    lay.addRow("allowedEnvVars", form._env)


@build_type_fields.register(McpToolHook)
def _(handler: McpToolHook, form: "_HandlerForm", lay: QFormLayout) -> None:
    form._server = QLineEdit(handler.server)
    form._server.textChanged.connect(form._save)
    lay.addRow("server *", form._server)

    form._tool = QLineEdit(handler.tool)
    form._tool.textChanged.connect(form._save)
    lay.addRow("tool *", form._tool)

    form._input = QPlainTextEdit(
        "\n".join(f"{k}: {v}" for k, v in handler.tool_input.items())
    )
    form._input.setFixedHeight(56)
    form._input.setPlaceholderText("input — 한 줄에 하나: key: value")
    form._input.textChanged.connect(form._save)
    lay.addRow("input", form._input)


# ─────────────────────── 타입별 저장 (위젯 → 모델) ───────────────────────


@singledispatch
def save_type_fields(handler: HookHandler, form: "_HandlerForm") -> None:
    """폼의 종류 고유 위젯 값을 핸들러에 기록한다. 폴백은 **아무것도 하지 않는다**.

    구성(`build_type_fields`)과 짝이다 — 구성이 위젯을 만들지 않았으면 저장할
    것도 없다. 짝이 맞는지는 테스트가 종류 표와 대조해 고정한다.
    """
    return None


@save_type_fields.register(CommandHook)
def _(handler: CommandHook, form: "_HandlerForm") -> None:
    handler.script = form._script.toPlainText()
    handler.script_name = form._script_name.text()
    handler.args = form._args.text().split()
    handler.shell = form._shell.currentData()
    handler.run_async = form._run_async.isChecked()
    handler.async_rewake = form._async_rewake.isChecked()


def _save_prompt_fields(handler: Any, form: "_HandlerForm") -> None:
    handler.prompt = form._prompt.toPlainText()
    handler.model = form._model.text()


@save_type_fields.register(AgentHook)
def _(handler: AgentHook, form: "_HandlerForm") -> None:
    _save_prompt_fields(handler, form)


@save_type_fields.register(PromptHook)
def _(handler: PromptHook, form: "_HandlerForm") -> None:
    _save_prompt_fields(handler, form)
    handler.continue_on_block = form._continue_on_block.isChecked()


@save_type_fields.register(HttpHook)
def _(handler: HttpHook, form: "_HandlerForm") -> None:
    handler.url = form._url.text()
    handler.headers = form._parse_pairs(form._headers.toPlainText())
    handler.allowed_env_vars = form._env.text().split()


@save_type_fields.register(McpToolHook)
def _(handler: McpToolHook, form: "_HandlerForm") -> None:
    handler.server = form._server.text()
    handler.tool = form._tool.text()
    handler.tool_input = form._parse_pairs(form._input.toPlainText())


# ─────────────────────────────── 폼 위젯 ───────────────────────────────


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

        build_type_fields(handler, self, lay)

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

        save_type_fields(h, self)

        self._on_changed()
