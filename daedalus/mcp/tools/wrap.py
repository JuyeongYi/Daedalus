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

    def list_wrappable_skills(
        self, include_unfetched: bool = False
    ) -> dict[str, Any]:
        """등록된 마켓플레이스 폴더에서 외부 플러그인·스킬을 나열한다.

        **가르는 기준은 "설치했는가"가 아니라 "실물을 읽었는가"다**(사용자 확정
        2026-09-07). 마켓은 플러그인을 `marketplace.json`에 **선언**만 하고
        실물은 따로 있다(실측: 공식 마켓 291개 선언). 실물은 세 군데에서 온다 —
        마켓 저장소 동봉 / Claude Code가 설치한 것 / `fetch_plugin_skills`로
        받아 둔 캐시. 어디서 왔든 스킬은 같은 스캐너가 읽고 `files_from`이 출처를
        말한다.

        include_unfetched(기본 False)면 **실물을 읽은 것만** 나오고
        `unfetched_count`로 나머지가 몇 개인지 알려준다 — 수백 개를 매번 실으면
        그것만으로 응답이 커진다. True면 못 읽은 것도 이름·설명과 함께 나온다
        (`has_files: false`, `skills: []`).

        실물이 없어도 **사용 선언은 지금 할 수 있다** — plugin_id만 있으면
        빌드가 dependencies/enabledPlugins를 내고 설치는 CC가 한다. 다만
        **랩핑(WrappedSkill)은 스킬 이름을 알아야** 하므로 실물이 필요하다
        (`fetch_plugin_skills`가 받아 온다).

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
        unfetched_total = 0
        for folder, plugins in wrap_catalog.scan_catalog():
            plugins_out: list[dict[str, Any]] = []
            for p in plugins:
                if not p.has_files:
                    unfetched_total += 1
                    if not include_unfetched:
                        continue
                    # 실물이 없으면 **스킬을 알 수 없다** — 마켓은 이름과
                    # 설명만 선언한다. 사용 선언은 이것만으로 충분하다.
                    plugins_out.append({
                        "name": p.name,
                        "plugin_id": p.plugin_id,
                        "description": p.description,
                        "used": p.plugin_id in declared,
                        "has_files": False,
                        "skills": [],
                    })
                    continue
                plugins_out.append({
                    "name": p.name,
                    "plugin_id": p.plugin_id,
                    "description": p.description,
                    "used": p.plugin_id in declared,
                    "has_files": True,
                    "files_from": p.files_from,
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
                })
            folders_out.append({
                "path": folder.path,
                "marketplace": folder.marketplace or None,
                "plugins": plugins_out,
            })
        out: dict[str, Any] = {
            "marketplace_folders": folders_out,
            "external_plugins": list(
                getattr(project, "external_plugins", None) or []
            ),
            # 마켓이 선언했지만 실물을 못 읽은 것 — 스킬은 받아야 안다.
            "unfetched_count": unfetched_total,
        }
        if unfetched_total and not include_unfetched:
            out["unfetched_note"] = (
                f"실물이 없어 스킬을 모르는 플러그인 {unfetched_total}개는 목록에서 "
                "뺐습니다 — include_unfetched=true로 이름·설명을 볼 수 있고, 사용 "
                "선언은 지금도 됩니다. 스킬이 필요하면 fetch_plugin_skills로 받으세요."
            )
        if not folders_out:
            out["note"] = (
                "등록된 마켓플레이스 폴더가 없습니다 — add_marketplace_folder"
                "(path, marketplace)로 플러그인들이 들어 있는 폴더를 등록하세요."
            )
        return out

    def fetch_plugin_skills(
        self, plugin_id: str, refresh: bool = False
    ) -> dict[str, Any]:
        """실물이 없는 플러그인의 스킬을 받아온다 (WP-WR).

        마켓은 플러그인을 선언만 하므로 실물이 없으면 스킬 목록을 알 수 없고,
        그러면 랩핑(WrappedSkill)을 만들 수 없다.
        이 도구는 실물을 `~/.daedalus/cache/plugin/`에 **얕게 클론**해 받아
        두고 거기서 스킬을 읽는다 — 그래서 이름뿐 아니라 **설명(SKILL.md
        프론트매터)까지** 나오고, 스캔은 설치된 플러그인과 **같은 코드**를 쓴다.

        **여기서만 인터넷에 나간다**(사용자 확정) — 카탈로그 조회·새로고침은
        절대 받지 않는다. 캐시 폴더 이름에 커밋 SHA(없으면 ref)가 들어가므로
        같은 버전은 다시 받지 않고, 버전이 바뀌면 새로 받는다
        (`refresh=true`로 강제 재수신).

        클론할 수 없는 source(마켓 폴더 안 상대 경로 등)는 `skills: null`이다.
        git URL이면 GitHub이 아니어도 된다. 이미 설치된 플러그인은
        `list_wrappable_skills`가 로컬에서 읽으므로 여기 올 필요가 없다.

        받은 이름으로 `create_skill(kind="wrapped", source="<plugin_id>:<스킬>")`
        를 만들 수 있다.
        """
        from daedalus.model.plugin import plugin_cache, wrap_catalog

        target = None
        for _folder, plugins in wrap_catalog.scan_catalog():
            for p in plugins:
                if p.plugin_id == plugin_id:
                    target = p
                    break
            if target is not None:
                break
        if target is None:
            raise ValueError(
                f"카탈로그에 '{plugin_id}'가 없습니다 — list_wrappable_skills"
                "(include_unfetched=true)로 id를 확인하세요."
            )
        if target.has_files:
            return {
                "plugin_id": plugin_id,
                "has_files": True,
                "files_from": target.files_from,
                "skills": [
                    {"name": s.name, "description": s.description, "source": s.source}
                    for s in target.skills
                ],
                "note": "실물이 이미 로컬에 있어 그대로 읽었습니다(받지 않음).",
            }

        skills = plugin_cache.cached_skills(
            plugin_id, target.source_spec, refresh=refresh,
        )
        if skills is None:
            return {
                "plugin_id": plugin_id,
                "has_files": False,
                "skills": None,
                "note": (
                    "클론할 수 있는 저장소 주소가 선언에 없어 받아올 수 "
                    "없습니다 — 설치 후 list_wrappable_skills로 확인하세요."
                ),
            }
        return {
            "plugin_id": plugin_id,
            "has_files": True,
            "files_from": "cache",
            "skills": [
                {"name": s.name, "description": s.description, "source": s.source}
                for s in skills
            ],
            "note": (
                "실물을 캐시에 받아 스킬을 읽었습니다 — source를 create_skill"
                '(kind="wrapped", source=…)에 그대로 쓸 수 있습니다.'
            ),
        }

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

    def set_wrapped_usage(
        self, name: str, usage: str, force: bool = False
    ) -> dict[str, Any]:
        """랩핑 스킬의 용도를 바꾼다 — state ↔ reference (WP-WR), undo 가능.

        최초 배치가 용도를 고정하지만 나중에 바꿀 수 있다. 지켜지는 불변식은
        "**동시에** 두 용도로 쓰이지 않는다"이므로, 전환은 기존 배치를 걷어낸
        뒤에만 성립한다 — 이미 놓여 있으면 무엇을 지워야 하는지 알리며
        **거부**하고, `force=True`면 그 배치(참조 노드·워크플로 노드·연결
        전이)를 함께 지우고 전환까지 **1 undo**로 묶는다. 전이가 말없이
        사라지지 않도록 기본값이 거부인 것이다.

        GUI 랩핑 편집기의 "용도를 …로 바꾸기" 버튼과 같은 실체
        (`actions/wrapped_usage.change_wrapped_usage`).
        """
        from daedalus.view.actions.wrapped_usage import change_wrapped_usage

        comp = self._find_component(name)
        result = change_wrapped_usage(self._window, comp, usage, force=force)
        return {"component": name, **result}

    def set_wrapped_enabled(self, name: str, enabled: bool) -> dict[str, Any]:
        """랩핑 스킬을 켜고 끈다 — **삭제의 대체재**(WP-WR), undo 가능.

        랩핑 스킬은 `delete_component`로 지울 수 없다(사용자 확정 2026-09-07) —
        소스·프론트매터·배선을 다시 입력하는 비용이 크고, 지우면 이 프로젝트가
        그 외부 스킬을 한때 썼다는 사실 자체가 사라진다. 대신 이 스위치로 끈다.

        끄면 빌드 산출에서 빠지고(state 용도는 SKILL.md 미산출, reference 용도는
        consult 지시 미합류) 외부 플러그인 참조 판정에서도 제외된다 — 꺼둔 것은
        쓰지 않는 것이다. **배치는 그대로 둔다**: 끄는 것과 캔버스에서 치우는
        것은 다른 결정이고 전이가 말없이 사라지면 안 된다(용도 전환이 force를
        요구하는 것과 같은 이유). 비활성인 채 배치가 남아 있으면
        `disabled_wrapped_placed` 경고가 짚는다. 다시 켜면 즉시 되돌아온다.

        GUI 랩핑 편집기의 [비활성화]/[활성화] 버튼과 같은 실체
        (`actions/wrapped_usage.set_wrapped_enabled`).
        """
        from daedalus.view.actions.wrapped_usage import set_wrapped_enabled

        comp = self._find_component(name)
        result = set_wrapped_enabled(self._window, comp, enabled)
        return {"component": name, **result}

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
