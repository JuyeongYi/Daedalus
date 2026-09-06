# daedalus/view/editors/workspace_settings_panel.py
"""작업 폴더 settings 편집 상주 탭 (WP-WS) — LOCAL 빌드 전용.

편집기 실체는 external/ 서브모듈의 QClaudeCodeSettingEditorWidget(스키마 구동 —
settings.json 전 키 자동 생성)이고, 이 모듈은 그것을 Daedalus 모델
(`PluginProject.workspace_settings`)에 배선하는 어댑터다.

- **훅 카테고리는 제외한다**(사용자 확정) — 훅의 정본은 Daedalus hook_library다.
  위젯 생성 플래그(`Category.ALL & ~Category.HOOKS`)로 편집을 막고, 모델
  저장 시에도 `hooks` 키를 방어적으로 걷어낸다(위젯의 passthrough 보존이
  진실 이원화를 만들지 않게).
- 편집은 모델 직접 기록 + notify("content") — 블랙보드/훅 패널과 같은 정책
  (undo 커맨드화 범위 밖). MCP `set_workspace_settings`는 SetAttrCmd 경유.
- 탭 자체가 LOCAL일 때만 보인다(app._refresh_target_dependent_tabs) — 그래도
  마켓 프로젝트를 로드한 채 남아 있을 수 있어 안내 라벨을 유지한다.
- 위젯 패키지가 설치돼 있지 않으면(서브모듈 미초기화) 앱이 죽는 대신 안내
  라벨만 보이는 자리 표시자가 된다.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.project import PluginProject


def strip_hooks(settings: dict) -> dict:
    """settings dict에서 hooks 키를 걷어낸다 — 훅 정본은 hook_library다."""
    return {k: v for k, v in settings.items() if k != "hooks"}


class WorkspaceSettingsPanel(QWidget):
    """상주 탭 — QClaudeCodeSettingEditorWidget ↔ project.workspace_settings."""

    def __init__(self, on_notify_fn: Callable[..., None] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: PluginProject | None = None
        self._notify = on_notify_fn
        self._loading = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._notice = QLabel("")
        self._notice.setWordWrap(True)
        self._notice.setContentsMargins(10, 6, 10, 6)
        self._notice.setVisible(False)
        lay.addWidget(self._notice)

        # 편집 위젯은 **지연 생성**이다 — 스키마 구동 전 키 UI 구축이 무겁고
        # (수백 행), 이 패널은 모든 MainWindow에 상주 탭으로 실리므로 즉시
        # 만들면 창을 수십 개 만드는 테스트 스위트가 수십 배 느려진다(실측 —
        # 전체 스위트 60초 → 타임아웃). 탭이 실제로 보이는 첫 순간
        # (showEvent) 또는 ensure_editor() 명시 호출 때 만든다.
        self._lay = lay
        self._editor = None
        self._editor_attempted = False

    def ensure_editor(self):
        """편집 위젯을 (아직이면) 만들어 배선하고 돌려준다. 미설치면 None."""
        if self._editor is not None or self._editor_attempted:
            return self._editor
        self._editor_attempted = True
        self._editor = self._make_editor()
        if self._editor is None:
            placeholder = QLabel(
                "설정 편집 위젯을 불러올 수 없습니다 — external/ 서브모듈을 "
                "초기화하고 설치하세요:\n"
                "git submodule update --init\n"
                "pip install -e external/QClaudeCodeSettingEditorWidget"
            )
            placeholder.setWordWrap(True)
            placeholder.setContentsMargins(10, 10, 10, 10)
            self._lay.addWidget(placeholder, 1)
            return None
        self._editor.settingChanged.connect(self._on_setting_changed)
        self._lay.addWidget(self._editor, 1)
        self._load_into_editor()
        return self._editor

    def showEvent(self, event) -> None:  # noqa: N802 — Qt 오버라이드
        super().showEvent(event)
        self.ensure_editor()

    @staticmethod
    def _make_editor():
        """위젯 생성 — 훅 카테고리 제외(사용자 확정). 미설치면 None."""
        try:
            from qclaudecodesettingeditorwidget import (
                QClaudeCodeSettingEditorWidget,
            )
            from qclaudecodesettingeditorwidget.categories import Category
        except ImportError:
            return None
        return QClaudeCodeSettingEditorWidget(
            categories=Category.ALL & ~Category.HOOKS, language="ko",
        )

    # --- 프로젝트 배선 ---

    def set_project(self, project: PluginProject | None) -> None:
        self._project = project
        self._refresh_notice()
        self._load_into_editor()

    def _load_into_editor(self) -> None:
        """모델 → 위젯 로드. 위젯이 아직 없으면(지연 생성 전) 아무것도 안 한다 —
        ensure_editor()가 만들 때 다시 부른다."""
        if self._editor is None:
            return
        project = self._project
        self._loading = True
        try:
            self._editor.setSettings(
                dict(project.workspace_settings) if project is not None else {}
            )
        finally:
            self._loading = False

    def refresh_external(self) -> None:
        """MCP 등 외부 경로가 모델을 바꿨을 때 화면을 모델로 다시 맞춘다."""
        self.set_project(self._project)

    def _refresh_notice(self) -> None:
        show = (
            self._project is not None
            and getattr(self._project, "build_target", None)
            is not BuildTarget.LOCAL
        )
        self._notice.setVisible(show)
        if show:
            self._notice.setText(
                "⚠ 빌드 타깃이 <b>마켓플레이스</b>라 이 설정은 베이크되지 "
                "않습니다 — 플러그인은 설치 대상 작업 폴더의 "
                "<code>.claude/settings.local.json</code>에 쓸 수 없습니다. "
                "파일 → 프로젝트 속성…에서 로컬 플러그인으로 바꾸세요."
            )

    # --- 편집 → 모델 ---

    def _on_setting_changed(self) -> None:
        if self._loading or self._project is None or self._editor is None:
            return
        self._project.workspace_settings = strip_hooks(self._editor.settings())
        if self._notify is not None:
            self._notify("content")

    def current_settings(self) -> dict:
        """테스트·호출자용 — 화면의 현재 설정(훅 제외). 위젯 미생성이면 모델 값."""
        if self._editor is None:
            return dict(self._project.workspace_settings) if self._project else {}
        return strip_hooks(self._editor.settings())
