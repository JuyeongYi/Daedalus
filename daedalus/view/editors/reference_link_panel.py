# daedalus/view/editors/reference_link_panel.py
"""참조 스킬의 링크 관리 패널 (A9-7).

구 ``skill_editor.py``(1,172줄)에서 이동했다(WP-RF 관례 — 이동만·동작 불변).
``skill_editor`` 모듈은 재-export 파사드로 남아 기존 임포트 경로가 그대로 동작한다.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class _ReferenceLinkPanel(QWidget):
    """참조 스킬의 링크 관리 — 캔버스 우클릭 "링크 추가"의 에디터 쪽 짝 (A9-7).

    캔버스에서 드래그로 잇는 것과 **같은 커맨드 경로**(`create_reference_link`)를
    탄다 — 여기서 링크를 따로 만들면 모델 sync 배선이 복제되고, 두 경로가
    어긋나는 순간 저장된 `reference_placements`가 화면과 달라진다.
    """

    def __init__(self, skill, project_vm, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QListWidget

        self._skill = skill
        self._project_vm = project_vm

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(QLabel("🔗 링크된 노드"))
        self._list = QListWidget()
        lay.addWidget(self._list, 1)

        self._add_btn = QPushButton("＋ 링크 추가…")
        self._add_btn.clicked.connect(self._on_add)
        lay.addWidget(self._add_btn)

        self._note = QLabel("이 참조 스킬이 캔버스에 배치되어야 링크할 수 있습니다.")
        self._note.setWordWrap(True)
        self._note.setStyleSheet("color: #888888;")
        lay.addWidget(self._note)
        self.refresh()

    def refresh(self) -> None:
        from daedalus.view.actions.references import linked_state_vms, reference_vms_for

        placements = reference_vms_for(self._project_vm, self._skill)
        self._list.clear()
        for ref_vm in placements:
            for state_vm in linked_state_vms(self._project_vm, ref_vm):
                self._list.addItem(state_vm.model.name)
        placed = bool(placements)
        self._add_btn.setEnabled(placed)
        self._note.setVisible(not placed)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.refresh()
        super().showEvent(event)

    def _on_add(self) -> None:
        """후보를 물어보고 **공유 함수**에 넘긴다 — 로직은 여기 없다."""
        from PySide6.QtWidgets import QInputDialog

        from daedalus.view.actions.references import (
            add_reference_link,
            linkable_state_vms,
            reference_vms_for,
        )

        placements = reference_vms_for(self._project_vm, self._skill)
        if not placements:
            return
        # 같은 스킬이 여러 번 놓였으면 첫 인스턴스에 건다 — 어느 인스턴스인지
        # 고르게 하는 것은 캔버스가 이미 하는 일이고(그 노드를 우클릭한다),
        # 에디터에서까지 물으면 질문이 둘로 늘어난다.
        ref_vm = placements[0]
        candidates = linkable_state_vms(self._project_vm, ref_vm)
        if not candidates:
            return
        names = [vm.model.name for vm in candidates]
        chosen, ok = QInputDialog.getItem(
            self, "링크 추가", "연결할 노드:", names, 0, False,
        )
        if not ok or not chosen:
            return
        state_vm = next(vm for vm in candidates if vm.model.name == chosen)
        scene = self._project_scene()
        if scene is not None:
            add_reference_link(scene, ref_vm, state_vm)
            self.refresh()

    def _project_scene(self):
        """이 프로젝트의 캔버스 씬. 없으면 None.

        참조 링크 생성은 **씬의 sync 함수**를 거쳐야 한다(모델
        `reference_placements` 재구성) — 그래서 커맨드를 직접 만들지 않고 씬을
        찾아 `create_reference_link`에 넘긴다. 씬은 위젯 트리의 자식이 아니므로
        findChildren으로는 못 찾는다(QGraphicsScene은 부모 없이 생성된다) —
        창이 들고 있는 것을 그대로 쓴다.
        """
        scene = getattr(self.window(), "_fsm_scene", None)
        if scene is None:
            return None
        # 다른 창의 씬을 잡지 않도록 뷰모델 일치를 확인한다.
        return scene if getattr(scene, "_project_vm", None) is self._project_vm else None
