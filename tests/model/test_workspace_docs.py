"""작업 폴더 문서 모델 — `.claude/CLAUDE.md` + `.claude/rules/*.md` (WP-WD).

편집만 제공한다(D7) — 생성 로직도, 마커 병합 규칙도 모델의 관심사가 아니다. 모델은
"무엇을 쓸 것인가"만 들고 있고, 어디에 어떻게 놓을지는 컴파일러가 정한다.

CLAUDE.md는 **최대 하나**라 리스트가 아니라 단일 필드다 — 불변식을 검증으로 지키는
대신 구조로 만든다. 규칙은 파일 하나가 문서 하나라 리스트다.
"""
from __future__ import annotations

import pytest

from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.workspace_doc import WorkspaceDoc
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project
from daedalus.model.validation import Validator


def _project(**kwargs) -> PluginProject:
    return PluginProject(name="my-plugin", **kwargs)


# ─────────────────────────── 모델 ───────────────────────────


def test_defaults_are_empty():
    project = _project()
    assert project.claude_md is None
    assert project.rules == []


def test_docs_have_stable_ids():
    """id는 본문 undo 스택(BodyDocumentRegistry)이 문서를 식별하는 키다."""
    first = WorkspaceDoc(name="testing")
    second = WorkspaceDoc(name="testing")
    assert first.id and second.id and first.id != second.id


def test_id_is_excluded_from_equality():
    """값 동등성 클래스 — id는 비교에서 빠진다(Skill/Agent와 같은 관례)."""
    assert WorkspaceDoc(name="a", body="x") == WorkspaceDoc(name="a", body="x")


# ─────────────────────────── 직렬화 ───────────────────────────


def test_roundtrip_preserves_docs():
    project = _project(
        claude_md=WorkspaceDoc(name="my-plugin", body="# my-plugin\n\nrules here"),
        rules=[
            WorkspaceDoc(name="testing", body="run pytest"),
            WorkspaceDoc(name="api-design", body="validate input"),
        ],
    )
    restored = deserialize_project(serialize_project(project))
    assert restored.claude_md is not None
    assert restored.claude_md.name == "my-plugin"
    assert restored.claude_md.body == "# my-plugin\n\nrules here"
    assert [(r.name, r.body) for r in restored.rules] == [
        ("testing", "run pytest"),
        ("api-design", "validate input"),
    ]


def test_roundtrip_preserves_ids():
    doc = WorkspaceDoc(name="testing", body="x")
    project = _project(rules=[doc])
    restored = deserialize_project(serialize_project(project))
    assert restored.rules[0].id == doc.id


def test_legacy_file_without_keys_loads_empty():
    """구버전 파일(키 부재)은 경고 없이 빈 값으로 읽힌다."""
    data = serialize_project(_project())
    data.pop("claude_md", None)
    data.pop("rules", None)
    restored = deserialize_project(data)
    assert restored.claude_md is None
    assert restored.rules == []


# ─────────────────────────── paths 필드 (A13) ───────────────────────────


def test_paths_defaults_to_empty_list():
    """비어 있으면 프론트매터가 나가지 않아 규칙이 항상 로드된다."""
    assert WorkspaceDoc(name="testing").paths == []


def test_paths_participate_in_equality():
    assert WorkspaceDoc(name="a", paths=["src/**"]) != WorkspaceDoc(name="a")


def test_paths_are_not_shared_between_docs():
    """default_factory 확인 — 한 문서의 편집이 다른 문서로 새면 안 된다."""
    first, second = WorkspaceDoc(name="a"), WorkspaceDoc(name="b")
    first.paths.append("src/**")
    assert second.paths == []


def test_roundtrip_preserves_paths():
    project = _project(
        rules=[WorkspaceDoc(name="testing", body="x", paths=["src/**", "lib/**"])]
    )
    restored = deserialize_project(serialize_project(project))
    assert restored.rules[0].paths == ["src/**", "lib/**"]


def test_legacy_file_without_paths_key_loads_empty():
    """paths 필드 도입 전 파일 — 키 부재는 경고 없이 빈 리스트다."""
    data = serialize_project(_project(rules=[WorkspaceDoc(name="testing", body="x")]))
    for doc in data["rules"]:
        doc.pop("paths", None)
    restored = deserialize_project(data)
    assert restored.rules[0].paths == []


# ─────────────────────────── 검증 ───────────────────────────


def _rules(project) -> list[str]:
    return [e.rule for e in Validator.validate_project(project)]


def test_duplicate_rule_name_is_error():
    project = _project(
        rules=[WorkspaceDoc(name="testing"), WorkspaceDoc(name="testing")]
    )
    findings = [e for e in Validator.validate_project(project)
                if e.rule == "duplicate_rule_name"]
    assert findings and not findings[0].is_warning


def test_invalid_rule_name_is_warning():
    """이름은 파일명이 된다 — 편집 중에는 경고, 컴파일 게이트에서 에러로 승격된다."""
    project = _project(rules=[WorkspaceDoc(name="Testing Rules")])
    findings = [e for e in Validator.validate_project(project)
                if e.rule == "invalid_rule_name"]
    assert findings and findings[0].is_warning


def test_valid_rule_name_passes():
    project = _project(rules=[WorkspaceDoc(name="api-design-2")])
    assert "invalid_rule_name" not in _rules(project)


def test_workspace_docs_in_marketplace_build_warn():
    """마켓플레이스 플러그인은 작업 폴더에 쓸 수 없다 — 배출되지 않는다."""
    project = _project(rules=[WorkspaceDoc(name="testing", body="x")])
    project.build_target = BuildTarget.MARKETPLACE
    findings = [e for e in Validator.validate_project(project)
                if e.rule == "workspace_doc_in_marketplace_build"]
    assert findings and findings[0].is_warning


def test_workspace_docs_in_local_build_do_not_warn():
    project = _project(rules=[WorkspaceDoc(name="testing", body="x")])
    project.build_target = BuildTarget.LOCAL
    assert "workspace_doc_in_marketplace_build" not in _rules(project)


def test_empty_docs_do_not_warn_in_marketplace():
    """본문이 비어 있으면 배출할 것이 없으므로 경고하지 않는다."""
    project = _project(
        claude_md=WorkspaceDoc(name="my-plugin", body="   "),
        rules=[WorkspaceDoc(name="testing", body="")],
    )
    project.build_target = BuildTarget.MARKETPLACE
    assert "workspace_doc_in_marketplace_build" not in _rules(project)


@pytest.mark.parametrize("name", ["", "Testing", "1-ok", "a_b"])
def test_rule_name_regex_matches_component_convention(name):
    """컴포넌트 이름과 같은 규약을 쓴다 — 산출 파일명이 되기 때문이다."""
    project = _project(rules=[WorkspaceDoc(name=name)])
    findings = _rules(project)
    expected_ok = name == "1-ok"
    assert ("invalid_rule_name" in findings) is not expected_ok
