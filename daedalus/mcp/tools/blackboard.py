# daedalus/mcp/tools/blackboard.py
"""블랙보드 도구 — 공유 상태 클래스 정의와 노드 접근 선언 (WP-RF-3b).

**계층: GUI 어댑터다 (WP-RF-2 명시).** core(model/compiler)가 아니라
MainWindow·ProjectViewModel·CommandStack·body_documents 등 view 표면에 결합된
코드로, core 경계 계약(tests/test_import_contracts.py)의 대상이 아니다.
모든 메서드는 **Qt 메인 스레드에서 실행되는 것을 전제**로 한다(service가
MainThreadInvoker로 마샬링한다). 편집 도구는 반드시
``ProjectViewModel.execute``(CommandStack)를 거친다 — 사용자가 Ctrl+Z로
되돌릴 수 있어야 한다.
"""
from __future__ import annotations

from typing import Any

from ._base import _BaseTools


class BlackboardTools(_BaseTools):
    """블랙보드 (WP-CE) — 클래스 생성 + reads/writes 선언."""

    def create_blackboard_class(
        self, name: str, description: str = "", fields: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """프로젝트 블랙보드에 공유 상태 클래스를 만든다.

        fields: [{"name": "frame_ms", "type": "float", "required": true,
                  "collection": "none", "default": null}, ...]
        타입은 string/int/float/bool 4종만 허용된다 — 컨테이너 형상은 collection
        (none/list/set)이 전담한다("문자열 목록" = string × list).
        """
        from daedalus.model.fsm.blackboard import (
            BLACKBOARD_FIELD_TYPES,
            CollectionType,
            DynamicClass,
            DynamicField,
        )
        from daedalus.model.fsm.variable import FieldType
        from daedalus.view.commands.attr_commands import AppendToListCmd

        blackboard = self._project.blackboard
        if any(c.name == name for c in blackboard.class_definitions):
            raise ValueError(f"블랙보드에 '{name}' 클래스가 이미 있습니다.")

        allowed = {t.value: t for t in BLACKBOARD_FIELD_TYPES}
        built: list[Any] = []
        for spec in fields or []:
            fname = spec.get("name")
            if not fname:
                raise ValueError("각 필드에는 name이 필요합니다.")
            raw_type = str(spec.get("type", "string")).lower()
            if raw_type not in allowed:
                raise ValueError(
                    f"필드 '{fname}'의 타입 '{raw_type}'은 블랙보드에서 쓸 수 없습니다. "
                    f"사용 가능: {', '.join(sorted(allowed))}"
                )
            raw_coll = str(spec.get("collection", "none")).lower()
            try:
                collection = CollectionType(raw_coll)
            except ValueError:
                raise ValueError(
                    f"필드 '{fname}'의 collection '{raw_coll}'이 올바르지 않습니다. "
                    "사용 가능: none, list, set"
                ) from None
            built.append(
                DynamicField(
                    name=fname,
                    field_type=FieldType(allowed[raw_type].value),
                    collection=collection,
                    default=spec.get("default"),
                    required=bool(spec.get("required", False)),
                )
            )

        cls = DynamicClass(name=name, description=description, fields=built)
        self._vm.execute(
            AppendToListCmd(
                blackboard.class_definitions,
                cls,
                label=f"블랙보드 클래스 '{name}' 생성",
                script=f'create_blackboard_class("{name}", fields={[f.name for f in built]})',
            )
        )
        self._window._blackboard_panel.set_project(self._project)
        return {"created": name, "fields": [f.name for f in built]}

    def set_state_access(
        self,
        node: str,
        reads: list[str] | None = None,
        writes: list[str] | None = None,
    ) -> dict[str, Any]:
        """캔버스 노드가 읽고 쓰는 블랙보드 경로를 선언한다.

        "클래스" 또는 "클래스.필드" 문자열을 쓴다. 선언하면 캔버스에 📖/✏ 뱃지가
        붙고, 컴파일된 SKILL.md의 절차·블랙보드 단락이 그 클래스로 좁혀진다.
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd
        from daedalus.view.commands.base import MacroCommand

        vm, _ = self._scope()
        svm = self._find_state_vm(node, vm)
        cmds: list[Any] = []
        if reads is not None:
            cmds.append(
                SetAttrCmd(
                    svm.model,
                    "reads",
                    list(reads),
                    label=f"'{node}' 읽기 선언",
                    script=f'set_state_access("{node}", reads={list(reads)})',
                )
            )
        if writes is not None:
            cmds.append(
                SetAttrCmd(
                    svm.model,
                    "writes",
                    list(writes),
                    label=f"'{node}' 쓰기 선언",
                    script=f'set_state_access("{node}", writes={list(writes)})',
                )
            )
        if not cmds:
            return {"node": node, "changed": []}
        vm.execute(
            cmds[0]
            if len(cmds) == 1
            else MacroCommand(children=cmds, description=f"'{node}' 블랙보드 접근 선언")
        )
        return {"node": node, "reads": reads, "writes": writes}
