# daedalus/mcp/tools/wrap.py
"""외부 플러그인 카탈로그 도구 (WP-WR, D2) — GUI "외부 플러그인 카탈로그" 창의
MCP 짝.

**계층: GUI 어댑터다 (WP-RF-2 명시)** — 발견·마켓플레이스 폴더 등록의 실체는
`model/plugin/wrap_catalog`(전역), **사용 선언은 프로젝트 모델**
(`PluginProject.external_plugins`)이고 창과 같은 실체를 부른다(패리티 —
표면마다 다른 카탈로그·선언을 보면 안 된다).

마켓플레이스 폴더 등록은 프로젝트 편집이 아니라 홈 설정 파일
(~/.daedalus/external_marketplaces.json) 쓰기라 **undo 대상이 아니고**,
사용 선언(`set_external_plugins`)은 프로젝트 편집이라 **undo 가능**하다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ._base import _BaseTools


class WrapTools(_BaseTools):
    """외부 플러그인 카탈로그 조회 + 마켓플레이스 폴더 등록 + 사용 선언."""

    def list_wrappable_skills(self) -> dict[str, Any]:
        """등록된 마켓플레이스 폴더에서 외부 플러그인·스킬을 나열한다.

        플러그인의 `plugin_id`(`이름[@마켓]`)를 `set_external_plugins`에 넣으면
        "이 프로젝트에서 사용" 선언이 되고 빌드가 dependencies(MARKETPLACE)/
        enabledPlugins(LOCAL)를 자동 배선한다 — 사용 선언만으로 그 플러그인의
        스킬을 쓸 수 있다(활성화되면 CC가 네이티브로 로드한다). `used`가 그
        선언 여부다.

        스킬의 `source`는 그 스킬을 **워크플로 단계로** 감쌀 때만 필요하다 —
        `create_skill(kind="wrapped", source=...)`(미선언 플러그인이면 선언까지
        1 undo). `already_wrapped`는 이 프로젝트에 이미 그 source를 감싼 랩핑
        스킬이 있다는 뜻이다(복수 랩퍼는 정상). `mcp_servers`는 그 플러그인이
        `.mcp.json`으로 제공하는 MCP 서버 이름들 — 에이전트 `mcp_servers`
        필드에 그대로 쓸 수 있다(개별 도구 목록은 지원하지 않는다).
        폴더가 없으면 `add_marketplace_folder`로 먼저 등록한다.
        """
        from daedalus.model.plugin import wrap_catalog
        from daedalus.view.editors.wrap_catalog_dialog import project_wrapped_sources

        project = self._project
        wrapped = project_wrapped_sources(project)
        declared = set(getattr(project, "external_plugins", None) or [])
        folders_out: list[dict[str, Any]] = []
        for folder, plugins in wrap_catalog.scan_catalog():
            folders_out.append({
                "path": folder.path,
                "marketplace": folder.marketplace or None,
                "plugins": [
                    {
                        "name": p.name,
                        "plugin_id": p.plugin_id,
                        "description": p.description,
                        "used": p.plugin_id in declared,
                        "mcp_servers": list(p.mcp_servers),
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
        out: dict[str, Any] = {
            "marketplace_folders": folders_out,
            "external_plugins": list(
                getattr(project, "external_plugins", None) or []
            ),
        }
        if not folders_out:
            out["note"] = (
                "등록된 마켓플레이스 폴더가 없습니다 — add_marketplace_folder"
                "(path, marketplace)로 플러그인들이 들어 있는 폴더를 등록하세요."
            )
        return out

    def list_marketplace_folders(self) -> dict[str, Any]:
        """등록된 외부 마켓플레이스 폴더 목록
        (~/.daedalus/external_marketplaces.json)."""
        from daedalus.model.plugin import wrap_catalog

        return {"marketplace_folders": [
            {"path": f.path, "marketplace": f.marketplace or None}
            for f in wrap_catalog.load_marketplaces()
        ]}

    def add_marketplace_folder(
        self, path: str, marketplace: str = ""
    ) -> dict[str, Any]:
        """마켓플레이스 폴더를 등록한다 — 외부 플러그인 카탈로그의 탐색 대상.

        path는 실존 폴더여야 한다(마켓 저장소, ~/.claude/plugins 계열,
        플러그인 폴더 자체 전부 가능). marketplace를 비우면 폴더의
        `.claude-plugin/marketplace.json` 이름을 자동 감지하고, 그것도 없으면
        bare(`플러그인`)가 된다 — bare는 LOCAL enabledPlugins 배선이 불가해
        컴파일이 경고한다. 같은 경로를 다시 등록하면 이름만 갱신된다.
        홈 설정 파일이라 undo 대상이 아니다.
        """
        if not Path(path).is_dir():
            raise ValueError(f"실존하는 폴더가 아닙니다: {path}")
        from daedalus.model.plugin import wrap_catalog

        folders = wrap_catalog.add_marketplace(path, marketplace)
        return {
            "added": path,
            "marketplace": marketplace or None,
            "marketplace_folders": [
                {"path": f.path, "marketplace": f.marketplace or None}
                for f in folders
            ],
        }

    def remove_marketplace_folder(self, path: str) -> dict[str, Any]:
        """마켓플레이스 폴더 등록을 지운다. 등록된 경로는
        `list_marketplace_folders`로 본다."""
        from daedalus.model.plugin import wrap_catalog

        if not wrap_catalog.remove_marketplace(path):
            known = ", ".join(
                f.path for f in wrap_catalog.load_marketplaces()
            ) or "(없음)"
            raise ValueError(f"등록되지 않은 폴더입니다: {path}. 현재 등록: {known}")
        return {"removed": path}

    def set_external_plugins(self, plugins: list[str]) -> dict[str, Any]:
        """이 프로젝트가 사용하는 외부 플러그인 선언을 **통째로 교체**한다 —
        undo 가능 (SetAttrCmd).

        원소는 `이름[@마켓]` 설치 식별자(`list_wrappable_skills`의 `plugin_id`).
        빌드가 이 선언에서 dependencies(MARKETPLACE)/enabledPlugins(LOCAL)를
        자동 배선한다 — 랩핑 스킬 source는 배선에 쓰이지 않는다(선언이 단일
        진실). 선언했는데 어떤 랩핑 스킬도 참조하지 않으면
        `unused_external_plugin` 경고(의도적 활성화면 무시), 랩핑 스킬이
        미선언 플러그인을 가리키면 `undeclared_external_plugin` 경고가 난다.
        GUI 카탈로그 창의 플러그인 체크박스와 같은 저장소를 편집한다.
        """
        from daedalus.view.commands.attr_commands import SetAttrCmd

        cleaned: list[str] = []
        for p in plugins:
            name = str(p).strip()
            if not name:
                raise ValueError("빈 플러그인 id는 넣을 수 없습니다.")
            if name not in cleaned:
                cleaned.append(name)
        project = self._project
        old = list(getattr(project, "external_plugins", None) or [])
        self._vm.execute(SetAttrCmd(
            project,
            "external_plugins",
            cleaned,
            label="외부 플러그인 사용 선언 변경",
            script=f"set_external_plugins({cleaned!r})",
        ))
        return {"old": old, "new": cleaned}
