"""시작 템플릿 — 아키타입 프로젝트 시드.

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

**갱신 절차:** 템플릿을 앱에서 열어(Ctrl+N 통합 다이얼로그) 고친 뒤 임시
폴더에 저장하고, 그 폴더의 `.daedalus.json`을 여기 `<id>.json`으로 덮어쓴다. 손으로
JSON을 고치지 않는다 — 파일은 직렬화기의 산출이라는 성질이 이 설계의 전부다.
갱신 후 `tests/model/test_templates.py`가 F7 에러 0과 경고 스냅샷을 다시 받아준다.

**사용자 템플릿:** `~/.daedalus/templates/<id>.json`(프로젝트 저장 파일을 그대로
복사)이 카탈로그에 병합된다 — 동명 id는 사용자가 이긴다. 내장과 달리 영어
본문·플레이스홀더 게이트의 대상이 아니다(자기 프로젝트를 시드로 삼는 것이라
내용은 소유자의 것). 갱신 = 파일 재복사.

**폴더형 사용자 템플릿:** `~/.daedalus/templates/<id>/`(= `.daedalus.json` +
`files/`·`skill-files/`)도 인식한다 — 프로젝트 폴더를 그대로 복사해 두면 되고,
동봉 파일은 템플릿에서 만든 프로젝트를 **처음 저장할 때** 프로젝트 폴더로
딸려 간다(SessionIO.carry_template_assets). 동명 id의 폴더형과 단일 JSON형이
공존하면 폴더형이 이긴다.
"""
from __future__ import annotations

import json
import re
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

    `file`이 None이면 내장(패키지 동봉), 아니면 사용자 템플릿의 실제 경로다.
    """

    id: str
    title: str
    summary: str
    file: Path | None = None
    # 폴더형 사용자 템플릿의 폴더 — files/·skill-files/ 동반 복사의 원천.
    # None이면 동반 파일 없음(내장·단일 JSON형).
    source_dir: Path | None = None

    @property
    def path(self) -> Path:
        if self.file is not None:
            return self.file
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


def user_templates_dir(home_dir: Path | None = None) -> Path:
    """사용자 템플릿 폴더 — `~/.daedalus/templates/` (전역 훅 저장소와 같은 규약).

    테스트는 이 함수를 몽키패치해 실제 홈을 읽지 않는다(hook_store와 동일 —
    실제 홈을 읽으면 개발자가 거기 둔 템플릿에 따라 결과가 달라진다).
    """
    home = home_dir if home_dir is not None else Path.home()
    return home / ".daedalus" / "templates"


def _read_template_head(file: Path) -> dict | None:
    """템플릿 JSON에서 표시용 name/description을 읽는다. 깨졌으면 None + stderr."""
    import sys

    try:
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[daedalus] 사용자 템플릿 스킵 {file.name}: {exc}", file=sys.stderr)
        return None
    if not isinstance(data, dict):
        print(f"[daedalus] 사용자 템플릿 스킵 {file.name}: 프로젝트 JSON이 아님",
              file=sys.stderr)
        return None
    return data


def _load_user_templates() -> list[ProjectTemplate]:
    """사용자 템플릿을 카탈로그 항목으로 읽는다 — 두 형태를 인식한다.

    - **단일 JSON형**: `<id>.json` (프로젝트 저장 파일 복사).
    - **폴더형**: `<id>/.daedalus.json` — 프로젝트 폴더를 그대로 둔 것.
      `files/`·`skill-files/`가 함께 살고, 템플릿에서 만든 프로젝트를 처음
      저장할 때 동반 복사된다(SessionIO — 동봉 스크립트가 딸려 가지 않던
      한계의 해소).

    id = 파일 stem/폴더 이름(내장과 같은 규약). 표시 문구는 내장과 달리 코드에
    없으므로 **파일 안의 프로젝트 name/description을 그대로 쓴다** — 사용자
    템플릿은 "내 프로젝트를 시드로 삼는 것"이라 그 이름이 곧 제목이다. 깨진
    파일은 stderr 경고 후 스킵한다(카탈로그·전역 훅 관례 — 파일 하나 때문에
    새 프로젝트 다이얼로그가 안 뜨면 안 된다). 같은 id의 폴더형과 단일 JSON형이
    공존하면 **폴더형이 이긴다**(더 완전한 쪽) — 정렬상 폴더 이름이 항상 먼저
    오지만, 순서에 기대지 않고 명시적으로 판정해 경고를 낸다.
    """
    import sys

    directory = user_templates_dir()
    if not directory.is_dir():
        return []
    out: list[ProjectTemplate] = []
    seen: set[str] = set()

    def _add(template_id: str, file: Path, source_dir: Path | None) -> None:
        if template_id in seen:
            print(
                f"[daedalus] 사용자 템플릿 스킵 {file}: 동명 id '{template_id}'의 "
                "폴더형이 이미 있습니다(폴더형 우선)",
                file=sys.stderr,
            )
            return
        data = _read_template_head(file)
        if data is None:
            return
        seen.add(template_id)
        out.append(ProjectTemplate(
            id=template_id,
            title=str(data.get("name") or template_id),
            summary=str(data.get("description") or "사용자 템플릿"),
            file=file,
            source_dir=source_dir,
        ))

    # 폴더형 먼저 — 동명 충돌 시 이기는 쪽을 먼저 등록해야 스킵 경고가 정확하다.
    from daedalus.model.package import PROJECT_FILENAME

    for child in sorted(p for p in directory.iterdir() if p.is_dir()):
        inner = child / PROJECT_FILENAME
        if inner.is_file():
            _add(child.name, inner, source_dir=child)
    for file in sorted(directory.glob(f"*{TEMPLATE_SUFFIX}")):
        if file.is_file():
            _add(file.stem, file, source_dir=None)
    out.sort(key=lambda t: t.id)
    return out


def list_templates() -> tuple[ProjectTemplate, ...]:
    """내장 + 사용자 템플릿을 표시 순서대로 — 동명 id는 **사용자가 이긴다**.

    (전역 ← 프로젝트 병합에서 프로젝트가 이기는 것과 같은 방향 — 더 구체적인
    쪽 우선.) 사용자 템플릿은 내장 뒤에 붙는다.
    """
    users = _load_user_templates()
    shadowed = {t.id for t in users}
    return tuple(t for t in TEMPLATES if t.id not in shadowed) + tuple(users)


#: 사용자 템플릿 id 규약 — 파일·폴더 이름이 되므로 경로 문자를 받지 않는다.
#: 컴포넌트 이름과 같은 규약을 쓰는 이유는 예측 가능성이다(둘 다 파일 이름이
#: 된다). 어긋난 입력은 **거절하고 알려준다** — 조용히 슬러그로 바꾸면 사용자가
#: 지은 이름과 카탈로그에 뜨는 이름이 달라진다.
_TEMPLATE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def save_user_template(
    project: PluginProject,
    template_id: str,
    source_dir: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """현재 프로젝트를 사용자 템플릿으로 저장한다 — `~/.daedalus/templates/`.

    저장 형식은 **프로젝트 저장 파일 그 자체**다(`serialize_project`의 format 2)
    — 로드가 `deserialize_project`를 그대로 타는 설계를 저장 쪽에서도 지킨다.

    `source_dir`(프로젝트 폴더)에 동봉 파일(`files/`·`skill-files/`)이 있으면
    **폴더형**(`<id>/.daedalus.json` + 그 디렉토리들)으로 저장한다 — 그래야
    이 템플릿에서 만든 프로젝트가 처음 저장될 때 동봉 파일이 함께 간다
    (`SessionIO.carry_template_assets`). 없으면 단일 JSON(`<id>.json`).

    같은 id가 이미 있으면 `overwrite=False`에서 `TemplateError`다 — 덮어쓰기는
    남의 템플릿을 지우는 일이라 호출자가 명시해야 한다.

    Returns: 실제로 쓴 정본 파일 경로.
    """
    import shutil

    from daedalus.model.package import PROJECT_FILENAME
    from daedalus.model.serialize import serialize_project

    name = (template_id or "").strip()
    if not _TEMPLATE_ID_RE.match(name):
        raise TemplateError(
            f"템플릿 id '{template_id}'는 쓸 수 없습니다 — 소문자·숫자·하이픈만 "
            "쓰고 소문자나 숫자로 시작하세요(파일 이름이 됩니다)."
        )

    root = user_templates_dir()
    file_form = root / f"{name}{TEMPLATE_SUFFIX}"
    dir_form = root / name
    existing = [p for p in (file_form, dir_form) if p.exists()]
    if existing and not overwrite:
        raise TemplateError(
            f"템플릿 '{name}'이 이미 있습니다: {existing[0]} — 덮어쓰려면 "
            "overwrite를 지정하세요."
        )

    side_dirs = []
    if source_dir is not None:
        for sub in ("files", "skill-files"):
            candidate = Path(source_dir) / sub
            if candidate.is_dir() and any(candidate.iterdir()):
                side_dirs.append((sub, candidate))

    text = json.dumps(serialize_project(project), ensure_ascii=False, indent=2)
    text = text.replace("\r\n", "\n").replace("\r", "\n") + "\n"

    root.mkdir(parents=True, exist_ok=True)
    if side_dirs:
        # 폴더형 — 기존 것을 통째로 갈아엎는다(부분 갱신이면 지운 파일이 남는다).
        if dir_form.exists():
            shutil.rmtree(dir_form)
        if file_form.exists():
            file_form.unlink()  # 같은 id의 단일 JSON형은 폴더형에 가려진다
        dir_form.mkdir(parents=True)
        target = dir_form / PROJECT_FILENAME
        target.write_text(text, encoding="utf-8", newline="")
        for sub, src in side_dirs:
            shutil.copytree(src, dir_form / sub, symlinks=False)
        return target

    if dir_form.exists():
        shutil.rmtree(dir_form)  # 폴더형 → 파일형으로 바뀌는 갱신
    file_form.write_text(text, encoding="utf-8", newline="")
    return file_form


def delete_user_template(template_id: str) -> bool:
    """사용자 템플릿을 지운다(파일형·폴더형 둘 다). 지운 것이 있으면 True.

    내장 템플릿은 패키지 데이터라 지울 수 없다 — 그쪽 id를 주면 False다
    (같은 id의 **사용자** 사본만 지워지고 내장이 다시 드러난다).
    """
    import shutil

    root = user_templates_dir()
    removed = False
    file_form = root / f"{template_id}{TEMPLATE_SUFFIX}"
    dir_form = root / template_id
    if file_form.is_file():
        file_form.unlink()
        removed = True
    if dir_form.is_dir():
        shutil.rmtree(dir_form)
        removed = True
    return removed


def find_template(template_id: str) -> ProjectTemplate:
    """id로 카탈로그 항목을 찾는다. 없으면 `TemplateError`."""
    catalogue = list_templates()
    for template in catalogue:
        if template.id == template_id:
            return template
    known = ", ".join(t.id for t in catalogue)
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
