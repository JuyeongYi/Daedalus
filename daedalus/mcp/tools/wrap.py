# daedalus/mcp/tools/wrap.py
"""랩핑 카탈로그 도구 (WP-WR 2단계, D2) — GUI "랩핑 스킬 카탈로그" 창의 MCP 짝.

**계층: GUI 어댑터다 (WP-RF-2 명시)** — 발견·루트 등록의 실체는
`model/plugin/wrap_catalog`이고(창과 같은 모듈 — 표면마다 다른 카탈로그를 보면
안 된다), 여기는 그 결과를 MCP 응답 형태로 만드는 어댑터다.

루트 등록은 프로젝트 편집이 아니라 홈 설정 파일(~/.daedalus/plugin_roots.json)
쓰기라 **undo 대상이 아니다**(save_project 관례). 랩핑 스킬 생성 자체는
`create_skill(kind="wrapped", source=...)`가 맡는다(props.py — undo 가능).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ._base import _BaseTools


class WrapTools(_BaseTools):
    """랩핑 가능한 스킬 카탈로그 조회 + 플러그인 루트 등록."""

    def list_wrappable_skills(self) -> dict[str, Any]:
        """등록된 플러그인 루트에서 랩핑 가능한 스킬을 **플러그인별로** 나열한다.

        각 스킬의 `source`(`플러그인[@마켓]:스킬`)를
        `create_skill(kind="wrapped", source=...)` 또는
        `set_component_field(..., "source", ...)`에 그대로 쓴다.
        `already_wrapped`는 이 프로젝트의 랩핑 스킬이 이미 그 source를 감싸고
        있다는 뜻이다(같은 source의 랩퍼 복수는 정상 — 재사용은 랩퍼 복수로).
        루트가 없으면 `add_plugin_root`로 먼저 등록한다.
        """
        from daedalus.model.plugin import wrap_catalog
        from daedalus.view.editors.wrap_catalog_dialog import project_wrapped_sources

        wrapped = project_wrapped_sources(self._project)
        roots_out: list[dict[str, Any]] = []
        for root, plugins in wrap_catalog.scan_catalog():
            roots_out.append({
                "path": root.path,
                "marketplace": root.marketplace or None,
                "plugins": [
                    {
                        "name": p.name,
                        "description": p.description,
                        "marketplace": p.marketplace or None,
                        "skills": [
                            {
                                "name": s.name,
                                "description": s.description,
                                "source": s.source,
                                "already_wrapped": s.source in wrapped,
                            }
                            for s in p.skills
                        ],
                    }
                    for p in plugins
                ],
            })
        out: dict[str, Any] = {"roots": roots_out}
        if not roots_out:
            out["note"] = (
                "등록된 플러그인 루트가 없습니다 — add_plugin_root(path, "
                "marketplace)로 플러그인들이 들어 있는 폴더를 등록하세요."
            )
        return out

    def list_plugin_roots(self) -> dict[str, Any]:
        """랩핑 카탈로그가 훑는 등록된 플러그인 루트 목록
        (~/.daedalus/plugin_roots.json)."""
        from daedalus.model.plugin import wrap_catalog

        return {"roots": [
            {"path": r.path, "marketplace": r.marketplace or None}
            for r in wrap_catalog.load_plugin_roots()
        ]}

    def add_plugin_root(self, path: str, marketplace: str = "") -> dict[str, Any]:
        """플러그인 루트를 등록한다 — 랩핑 카탈로그의 탐색 대상.

        path는 실존 폴더여야 한다(마켓플레이스 저장소, ~/.claude/plugins 계열,
        플러그인 폴더 자체 전부 가능). marketplace를 비우면 루트의
        `.claude-plugin/marketplace.json` 이름을 자동 감지하고, 그것도 없으면
        bare 소스(`플러그인:스킬`)가 된다 — bare는 LOCAL enabledPlugins 배선이
        불가해 컴파일이 경고한다. 같은 경로를 다시 등록하면 marketplace만
        갱신된다. 프로젝트 편집이 아니라 undo 대상이 아니다.
        """
        if not Path(path).is_dir():
            raise ValueError(f"실존하는 폴더가 아닙니다: {path}")
        from daedalus.model.plugin import wrap_catalog

        roots = wrap_catalog.add_plugin_root(path, marketplace)
        return {
            "added": path,
            "marketplace": marketplace or None,
            "roots": [
                {"path": r.path, "marketplace": r.marketplace or None}
                for r in roots
            ],
        }

    def remove_plugin_root(self, path: str) -> dict[str, Any]:
        """플러그인 루트 등록을 지운다. 등록된 경로는 `list_plugin_roots`로 본다."""
        from daedalus.model.plugin import wrap_catalog

        if not wrap_catalog.remove_plugin_root(path):
            known = ", ".join(r.path for r in wrap_catalog.load_plugin_roots()) or "(없음)"
            raise ValueError(f"등록되지 않은 경로입니다: {path}. 현재 등록: {known}")
        return {"removed": path}
