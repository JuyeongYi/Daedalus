"""시작 템플릿 — 아키타입 프로젝트 시드 (A7).

빈 캔버스에서 출발하면 단순한 플러그인 하나에도 노드·포트·진행 상태 규칙을
전부 손으로 놓아야 한다("배보다 배꼽"). 자주 쓰는 뼈대 3종을 미리 만들어 두고
새 프로젝트를 그 위에서 시작하게 한다.

**템플릿 파일은 `serialize_project`가 만든 format 2 JSON이고, 로드는 기존
`deserialize_project`를 그대로 태운다** — 전용 파서를 두면 정본 직렬화기와
어긋나는 순간(필드 추가·마이그레이션) 템플릿만 조용히 낡는다. 저장 파일과
같은 경로를 타므로 마이그레이션도 공짜로 따라온다.

표시 문구(제목·요약)는 **여기 코드**에 있고 파일에는 없다 — 파일은 프로젝트
직렬화 형식 그 자체여야 하고(사이드카 키를 섞으면 로드 경로가 특수해진다),
문구는 GUI 텍스트라 한국어다(A12의 "산출로 나가는 값"이 아니다).

템플릿 **본문은 영어**다 — 컴파일 산출로 그대로 나가는 사용자 값의 출발점이기
때문이다(A12). 이름·설명은 사용자가 갈아끼울 플레이스홀더다.

**갱신 절차:** 템플릿을 앱에서 열어(File→"템플릿에서 새 프로젝트…") 고친 뒤 임시
폴더에 저장하고, 그 폴더의 `.daedalus.json`을 여기 `<id>.json`으로 덮어쓴다. 손으로
JSON을 고치지 않는다 — 파일은 직렬화기의 산출이라는 성질이 이 설계의 전부다.
갱신 후 `tests/model/test_templates.py`가 F7 에러 0과 경고 스냅샷을 다시 받아준다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project

#: 템플릿 JSON이 사는 곳 — 패키지 데이터(pyproject의 package-data에 등재).
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

TEMPLATE_SUFFIX = ".json"


class TemplateError(ValueError):
    """템플릿을 읽을 수 없다 — 알 수 없는 id, 파일 부재, 손상."""


@dataclass(frozen=True)
class ProjectTemplate:
    """시작 템플릿 하나의 카탈로그 항목.

    `id`가 곧 파일 이름(stem)이다 — 진실이 둘이면(파일 안에 이름을 또 적으면)
    파일을 복사해 이름을 바꿨을 때 어느 쪽이 이겼는지 알 수 없다(전역 훅
    저장소 A1과 같은 규약).
    """

    id: str
    title: str
    summary: str

    @property
    def path(self) -> Path:
        return TEMPLATE_DIR / f"{self.id}{TEMPLATE_SUFFIX}"


#: 카탈로그 — 표시 순서의 단일 진실(단순한 것부터가 아니라 **자주 쓰는 것부터**).
TEMPLATES: tuple[ProjectTemplate, ...] = (
    ProjectTemplate(
        id="implementation-review",
        title="구현 → 리뷰 파이프라인",
        summary="에이전트 2개(구현자·리뷰어) + 블랙보드 + 진행 상태, 리뷰 반려 루프 포함",
    ),
    ProjectTemplate(
        id="research-pipeline",
        title="리서치 파이프라인",
        summary="질문을 쪼개 병렬 조사 후 하나로 합성 — 조사 에이전트 1개 + 블랙보드 3종",
    ),
    ProjectTemplate(
        id="single-skill-reference",
        title="단일 스킬 + 참조 문서",
        summary="사용자 호출 스킬 하나에 참조 문서·배경 지식 스킬을 붙인 최소 구성",
    ),
)


def list_templates() -> tuple[ProjectTemplate, ...]:
    """카탈로그를 표시 순서대로 돌려준다."""
    return TEMPLATES


def find_template(template_id: str) -> ProjectTemplate:
    """id로 카탈로그 항목을 찾는다. 없으면 `TemplateError`."""
    for template in TEMPLATES:
        if template.id == template_id:
            return template
    known = ", ".join(t.id for t in TEMPLATES)
    raise TemplateError(f"알 수 없는 템플릿 id: {template_id} (가용: {known})")


def load_template(
    template_id: str,
    collect_warnings: list[str] | None = None,
) -> PluginProject:
    """템플릿을 새 `PluginProject`로 로드한다.

    호출할 때마다 파일에서 새로 만든다 — 모듈 전역에 캐시해 두면 한 번 편집한
    템플릿 프로젝트가 다음 "새 프로젝트"에 그대로 딸려 나온다.
    """
    template = find_template(template_id)
    try:
        with open(template.path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError as exc:
        raise TemplateError(f"템플릿 파일을 읽을 수 없습니다: {template.path} ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise TemplateError(f"템플릿 파일이 손상되었습니다: {template.path} ({exc})") from exc
    return deserialize_project(data, collect_warnings=collect_warnings)
