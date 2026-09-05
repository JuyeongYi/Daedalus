# tests/model/test_user_templates.py
"""사용자 템플릿 (~/.daedalus/templates/) — 카탈로그 병합 (A7 확장).

실사용 프로젝트를 시드로 삼는 경로(사용자 확정 — UE 작업 폴더를 템플릿으로).
내장과 달리 영어 본문·플레이스홀더 게이트의 대상이 아니다. 폴더는 conftest의
_isolate_user_templates가 tmp로 돌려놓는다.
"""
from __future__ import annotations

import json

import pytest

from daedalus.model import templates
from daedalus.model.project import PluginProject
from daedalus.model.serialize import serialize_project


def _write_user_template(name: str, project: PluginProject) -> None:
    d = templates.user_templates_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(
        json.dumps(serialize_project(project)), encoding="utf-8"
    )


def test_no_user_dir_lists_builtins_only():
    assert list(templates.list_templates()) == list(templates.TEMPLATES)


def test_user_template_appended_after_builtins():
    _write_user_template("ue-dev", PluginProject(name="ue-dev-template", description="UE 작업 시드"))
    catalogue = templates.list_templates()
    assert [t.id for t in catalogue[:len(templates.TEMPLATES)]] == [
        t.id for t in templates.TEMPLATES
    ]
    user = catalogue[-1]
    assert user.id == "ue-dev"  # id = 파일 stem (파일 안 name과 무관)
    assert user.title == "ue-dev-template"  # 표시 제목 = 프로젝트 name
    assert user.summary == "UE 작업 시드"  # 요약 = description
    assert user.file is not None


def test_user_template_loads_roundtrip():
    proj = PluginProject(name="mine", description="d")
    _write_user_template("mine-seed", proj)
    loaded = templates.load_template("mine-seed")
    assert loaded.name == "mine"


def test_user_template_shadows_builtin_with_same_id():
    """동명 id는 사용자가 이긴다 (전역←프로젝트 병합과 같은 방향)."""
    builtin_id = templates.TEMPLATES[0].id
    _write_user_template(builtin_id, PluginProject(name="shadowed"))
    catalogue = templates.list_templates()
    assert [t.id for t in catalogue].count(builtin_id) == 1
    entry = templates.find_template(builtin_id)
    assert entry.file is not None  # 사용자 쪽이 이겼다
    assert templates.load_template(builtin_id).name == "shadowed"


def test_broken_user_template_skipped(capsys):
    """깨진 파일은 stderr 경고 후 스킵 — 다이얼로그가 안 뜨면 안 된다."""
    d = templates.user_templates_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "broken.json").write_text("{not json", encoding="utf-8")
    _write_user_template("ok", PluginProject(name="ok"))
    ids = [t.id for t in templates.list_templates()]
    assert "ok" in ids and "broken" not in ids
    assert "broken.json" in capsys.readouterr().err


def test_unknown_id_error_lists_user_templates_too():
    _write_user_template("mine-seed", PluginProject(name="m"))
    with pytest.raises(templates.TemplateError, match="mine-seed"):
        templates.find_template("no-such-id")
