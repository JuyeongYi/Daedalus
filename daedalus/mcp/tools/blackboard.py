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
    """블랙보드 (WP-CE) — 클래스 CRUD + 필드 편집 + reads/writes 선언."""

    # ------------------------------------------------------------------
    # 공용 헬퍼
    # ------------------------------------------------------------------

    def _find_blackboard_class(self, name: str) -> Any:
        for cls in self._project.blackboard.class_definitions:
            if cls.name == name:
                return cls
        known = (
            ", ".join(c.name for c in self._project.blackboard.class_definitions) or "(없음)"
        )
        raise ValueError(f"'{name}' 블랙보드 클래스가 없습니다. 현재: {known}")

    @staticmethod
    def _build_blackboard_fields(fields: list[dict[str, Any]] | None) -> list[Any]:
        """필드 스펙(dict) 목록 → DynamicField 목록. 생성·교체가 공유하는 검증.

        타입은 스칼라 4종(string/int/float/bool)만, 컨테이너 형상은 collection
        (none/list/set)이 전담한다(WP-BT). 한 곳에서만 판정해야 도구에 따라
        통과하는 값이 달라지지 않는다.
        """
        from daedalus.model.fsm.blackboard import (
            BLACKBOARD_FIELD_TYPES,
            CollectionType,
            DynamicField,
        )
        from daedalus.model.fsm.variable import FieldType

        allowed = {t.value: t for t in BLACKBOARD_FIELD_TYPES}
        built: list[Any] = []
        seen: set[str] = set()
        for spec in fields or []:
            fname = spec.get("name")
            if not fname:
                raise ValueError("각 필드에는 name이 필요합니다.")
            if fname in seen:
                raise ValueError(f"필드 '{fname}'이 중복됩니다.")
            seen.add(fname)
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
        return built

    @staticmethod
    def _field_summary(fld: Any) -> dict[str, Any]:
        return {
            "name": fld.name,
            "type": getattr(fld.field_type, "value", str(fld.field_type)),
            "collection": getattr(fld.collection, "value", str(fld.collection)),
            "required": bool(fld.required),
            "default": fld.default,
        }

    def _class_detail(self, cls: Any) -> dict[str, Any]:
        return {
            "name": cls.name,
            "description": getattr(cls, "description", ""),
            "fields": [self._field_summary(f) for f in cls.fields],
        }

    def _refresh_blackboard_ui(self) -> None:
        """블랙보드 패널을 모델과 다시 맞춘다 — 선택은 보존한다.

        `HookTools._refresh_hook_ui`와 같은 자리다. `set_project`를 부르면 목록이
        0행으로 리셋되므로 패널의 외부 변경 진입점(`refresh_external`)을 쓴다.
        """
        panel = getattr(self._window, "_blackboard_panel", None)
        if panel is not None:
            panel.refresh_external()

    # ------------------------------------------------------------------
    # 클래스
    # ------------------------------------------------------------------

    def create_blackboard_class(
        self, name: str, description: str = "", fields: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """프로젝트 블랙보드에 공유 상태 클래스를 만든다.

        fields: [{"name": "frame_ms", "type": "float", "required": true,
                  "collection": "none", "default": null}, ...]
        타입은 string/int/float/bool 4종만 허용된다 — 컨테이너 형상은 collection
        (none/list/set)이 전담한다("문자열 목록" = string × list).
        """
        from daedalus.model.fsm.blackboard import DynamicClass
        from daedalus.view.commands.attr_commands import AppendToListCmd

        blackboard = self._project.blackboard
        if any(c.name == name for c in blackboard.class_definitions):
            raise ValueError(f"블랙보드에 '{name}' 클래스가 이미 있습니다.")

        built = self._build_blackboard_fields(fields)
        cls = DynamicClass(name=name, description=description, fields=built)
        self._vm.execute(
            AppendToListCmd(
                blackboard.class_definitions,
                cls,
                label=f"블랙보드 클래스 '{name}' 생성",
                script=f'create_blackboard_class("{name}", fields={[f.name for f in built]})',
            )
        )
        self._refresh_blackboard_ui()
        return {"created": name, "fields": [f.name for f in built]}

    def update_blackboard_class(
        self,
        name: str,
        new_name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """블랙보드 클래스의 이름·설명을 고친다. 필드는 set_blackboard_fields.

        None은 "건드리지 않음"이고 description에 ""를 주면 지워진다.
        **개명하면 상태 reads/writes의 `"Class"`/`"Class.field"` 참조가 함께
        갱신된다**(rename_component가 문자열 참조를 따라가는 것과 같은 관례) —
        갱신된 노드는 결과의 `updated_references`에 담긴다. 전체가 1 undo 단위다.
        """
        from daedalus.model.project import blackboard_rename_ref_updates
        from daedalus.view.commands.attr_commands import SetAttrCmd
        from daedalus.view.commands.base import MacroCommand

        cls = self._find_blackboard_class(name)
        before = self._class_detail(cls)
        cmds: list[Any] = []
        updated_refs: list[dict[str, Any]] = []

        if new_name is not None and new_name != name:
            if not new_name.strip():
                raise ValueError("클래스 이름은 비울 수 없습니다.")
            if any(
                c.name == new_name for c in self._project.blackboard.class_definitions
            ):
                raise ValueError(f"블랙보드에 '{new_name}' 클래스가 이미 있습니다.")
            cmds.append(
                SetAttrCmd(
                    cls, "name", new_name,
                    label=f"블랙보드 클래스 '{name}' → '{new_name}'",
                    script=f'update_blackboard_class("{name}", new_name="{new_name}")',
                )
            )
            for state, attr, renamed in blackboard_rename_ref_updates(
                self._project, name, new_name
            ):
                cmds.append(
                    SetAttrCmd(
                        state, attr, renamed,
                        label=f"'{getattr(state, 'name', '?')}' {attr} 참조 갱신",
                        script=f'update_blackboard_class("{name}", new_name="{new_name}")',
                    )
                )
                updated_refs.append(
                    {"node": getattr(state, "name", "?"), "attr": attr, "value": renamed}
                )

        if description is not None and description != getattr(cls, "description", ""):
            cmds.append(
                SetAttrCmd(
                    cls, "description", description,
                    label=f"블랙보드 클래스 '{name}' 설명 변경",
                    script=f'update_blackboard_class("{name}", description=...)',
                )
            )

        if not cmds:
            return {"changed": [], **before}
        self._vm.execute(
            cmds[0]
            if len(cmds) == 1
            else MacroCommand(children=cmds, description=f"블랙보드 클래스 '{name}' 변경")
        )
        self._refresh_blackboard_ui()
        return {
            "before": before,
            "updated_references": updated_refs,
            **self._class_detail(cls),
        }

    def delete_blackboard_class(self, name: str) -> dict[str, Any]:
        """블랙보드에서 클래스 정의를 지운다.

        이 클래스를 reads/writes로 가리키는 노드의 선언은 **건드리지 않는다**
        (delete_hook·delete_component와 같은 정책 — 지우면 undo로 클래스가
        돌아와도 참조는 돌아오지 않는다). 결과의 `still_referenced_by`를 보고
        set_state_access로 정리하라. 남은 참조는 `dangling_blackboard_ref`
        경고가 이어서 짚는다.
        """
        from daedalus.model.project import blackboard_class_referrers
        from daedalus.view.commands.attr_commands import RemoveFromListCmd

        cls = self._find_blackboard_class(name)
        referenced = blackboard_class_referrers(self._project, name)
        self._vm.execute(
            RemoveFromListCmd(
                self._project.blackboard.class_definitions,
                cls,
                label=f"블랙보드 클래스 '{name}' 삭제",
                script=f'delete_blackboard_class("{name}")',
            )
        )
        self._refresh_blackboard_ui()
        return {"deleted": name, "still_referenced_by": referenced}

    # ------------------------------------------------------------------
    # 필드
    # ------------------------------------------------------------------

    def set_blackboard_fields(
        self, name: str, fields: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """클래스의 필드 목록을 **통째로 교체**한다(set_transfer_on과 같은 관례).

        fields 형식은 create_blackboard_class와 같다. 지금 목록을 보려면
        get_project의 blackboard_classes 또는 이 도구의 결과를 쓰라.

        교체이므로 **빠진 필드는 삭제**된다 — 필드 이름을 바꾸는 것도 여기서는
        "지우고 새로 넣기"라 `"Class.field"` 참조를 따라가지 않는다(어느 것이
        개명이고 어느 것이 삭제인지 목록만으로는 알 수 없다). 사라진 필드를
        가리키던 노드는 결과의 `dropped_field_references`에 담기고,
        `dangling_blackboard_ref` 경고가 이어서 짚는다.
        """
        from daedalus.model.project import blackboard_class_referrers
        from daedalus.view.commands.attr_commands import SetAttrCmd

        cls = self._find_blackboard_class(name)
        before = self._class_detail(cls)
        built = self._build_blackboard_fields(fields)

        kept = {f.name for f in built}
        dropped = [f.name for f in cls.fields if f.name not in kept]
        dropped_refs = [
            {"field": f"{name}.{fname}", "nodes": nodes}
            for fname in dropped
            if (nodes := blackboard_class_referrers(self._project, f"{name}.{fname}"))
        ]

        self._vm.execute(
            SetAttrCmd(
                cls, "fields", built,
                label=f"블랙보드 클래스 '{name}' 필드 {len(built)}개 설정",
                script=f'set_blackboard_fields("{name}", {[f.name for f in built]})',
            )
        )
        self._refresh_blackboard_ui()
        return {
            "before": before,
            "dropped_fields": dropped,
            "dropped_field_references": dropped_refs,
            **self._class_detail(cls),
        }

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
