# daedalus/compiler/units/gate.py
"""계획 단계의 게이트 — 이름 규약 검사와 진단 수집 (WP-5, `plan.py`에서 이동만).

계획을 세우는 동안 나온 에러/경고가 모이는 자리다. 단위는 게이트에 **말만**
하고(`check_output_name` / `warn`), 무엇을 에러로 볼지·문구가 무엇인지는 여기
한 곳이 안다 — 산출 종류가 늘어도 문구 사본이 늘지 않는다.

에러 순서는 계약이다(`tests/compiler/test_plan_order_golden.py`):
프로젝트 이름 → 스킬 → 에이전트 → 훅 스크립트 충돌 → 규칙 문서 → 경로 충돌.
`Planner`가 `check_project_name`을 단위 순회 **앞**에서 부르고, 나머지는 단위
선언 순서가 곧 에러 순서다.
"""
from __future__ import annotations

from daedalus.compiler.units.paths import _OUTPUT_NAME_RE
from daedalus.model.validation import ValidationError


class Gate:
    """계획 단계에서 모인 에러·경고."""

    def __init__(self) -> None:
        self.errors: list[ValidationError] = []
        self.warnings: list[ValidationError] = []

    # ── 수집 ──

    def fail(self, error: ValidationError) -> None:
        self.errors.append(error)

    def warn(self, warning: ValidationError) -> None:
        self.warnings.append(warning)

    # ── 이름 규약 ──

    def check_output_name(self, name: str, label: str, subject: object) -> None:
        """산출 파일/디렉토리 이름이 되는 이름의 규약 검사.

        검증기에서는 경고 등급이지만(편집 중에는 경고가 맞다) 컴파일
        게이트에서는 에러로 승격한다 — CC 플러그인 로더가 받지 않는 산출물이
        나가기 때문이다.
        """
        if not _OUTPUT_NAME_RE.match(name or ""):
            self.errors.append(ValidationError(
                rule="compile_invalid_component_name",
                message=(
                    f"{label}의 이름 '{name}'이 규약 '^[a-z0-9][a-z0-9-]*$'에 맞지 "
                    f"않습니다. 컴파일 시에는 이름 규약이 필수입니다 — 산출 "
                    f"파일/디렉토리 이름이 되므로 CC 플러그인 로더가 받지 않는 "
                    f"산출물이 생깁니다."
                ),
                source=name,
                subject=subject,
            ))

    def check_project_name(self, project) -> None:
        """프로젝트 이름 — 마켓플레이스 빌드에서 plugin.json의 name(플러그인
        식별자)이 되므로 컴포넌트와 동일 규약을 컴파일 게이트에서 에러로
        강제한다. 로컬 빌드도 같은 규약을 적용한다(타깃을 오가며 새 에러가
        튀지 않도록 — 산출 이름·문서 제목에 그대로 쓰인다).

        문구가 `check_output_name`과 다르고 **모든 컴포넌트 에러보다 앞**에
        온다 — 그래서 별도 메서드다.
        """
        if not _OUTPUT_NAME_RE.match(project.name or ""):
            self.errors.append(ValidationError(
                rule="compile_invalid_component_name",
                message=(
                    f"프로젝트 '{project.name}'의 이름이 규약 '^[a-z0-9][a-z0-9-]*$'에 "
                    f"맞지 않습니다. 컴파일 시에는 이름 규약이 필수입니다 — 마켓플레이스 "
                    f"빌드에서는 plugin.json의 name(플러그인 식별자)이 되어 CC 플러그인 "
                    f"로더가 받지 않는 산출물이 생깁니다. 파일 → 프로젝트 속성…에서 "
                    f"이름을 변경하세요."
                ),
                source=project.name,
                subject=project,
            ))
