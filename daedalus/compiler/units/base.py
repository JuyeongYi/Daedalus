# daedalus/compiler/units/base.py
"""컴파일 참여자의 공통 계약 — `CompileUnit` 계층과 계획 행 (WP-5).

지시문의 *"컴파일 과정에 참여하는 것들은 묶을 필요가 있다. 적어도 인터페이스
형태로, 각각의 구성요소가 알아서 자기 할 일을 하도록"*의 실체가 이 모듈이다.

종전에는 산출 종류마다 **세 자리**에 지식이 흩어져 있었다 — 계획
(`plan._plan_outputs`의 한 문단), 쓰기(`project_compiler`의 kind 사다리),
그리고 "이 kind는 ${ROOT}를 확장하는가 / 토큰을 어떻게 세는가"의 튜플 두 개.
하나를 고치고 나머지를 잊으면 조용한 불일치가 된다(C2~C5).

이제 산출 종류 하나 = `CompileUnit` 하나이고, 그 단위가 자기 계획·자기 렌더·
자기 쓰기 방식을 전부 말한다. 계획 행(`PlannedOutput`)은 그 선언을 **값으로**
들고 다니므로 드라이버는 kind를 비교하지 않는다:

    plan  = [단위.plan(ctx, gate) for 단위 in UNITS]   # 순서 = 선언 순서
    write = UNIT_BY_ID[행.kind].emit(행, ctx, sink)

`mode`/`phase`/`expands_root`/`token_kind`/`exclusive`는 전부 **행이 선언**하는
값이다 — 새 산출을 더하는 사람은 단위 하나만 쓰면 되고, 드라이버·게이트·토큰
리포트는 한 줄도 고치지 않는다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, ClassVar

from daedalus.compiler.token_report import TokenKind

if TYPE_CHECKING:  # pragma: no cover - 정적 타입 전용(순환 임포트 방지)
    from daedalus.compiler.units.context import CompileContext
    from daedalus.compiler.units.gate import Gate
    from daedalus.compiler.units.sink import OutputSink


class OutputMode(StrEnum):
    """산출이 파일이 되는 방식 — 쓰기 실행자(`OutputSink`)가 고르는 경로."""
    TEXT = "text"            # 텍스트 렌더 후 쓰기
    COPY_FILE = "copy_file"  # 원본 파일 1건 복사
    COPY_TREE = "copy_tree"  # 트리 복사
    MERGE = "merge"          # 기존 내용을 읽고 병합(사용자 파일)


class Phase(StrEnum):
    """쓰기 루프의 단계 — 오늘의 드라이버 문장 순서를 값으로 보존한다.

    WRITE는 산출 파일을 만드는 단계이고, INSTALL은 **그 뒤에** 도는 LOCAL 설치
    배선이다. 둘 사이에는 드라이버가 소유한 진단 스캔 2건(dangling_file_ref /
    dangling_skill_file_ref)이 있다 — 그래서 단계가 둘이다. 한 루프로 합치면
    경고 순서가 조용히 바뀐다(`test_plan_order_golden`이 잡는다).
    """
    WRITE = "write"
    INSTALL = "install"


@dataclass
class PlannedOutput:
    """쓰기 전 계획된 산출물 1건.

    `kind`가 곧 이 행을 쓸 단위의 id다(`units.registry.UNIT_BY_ID`).
    """
    rel_path: PurePosixPath          # out_dir 기준 상대 경로 (충돌 키)
    label: str                       # 사람이 읽는 원인 컴포넌트 표지
    subject: object                  # 노드 점프용 모델 객체
    kind: str                        # "skill" | "agent" | "hook_script" | …
    component: object                # 컴파일 대상 (skill/agent)
    script_name: str = ""            # hook_script일 때 파일명 (WP-HS)
    src_path: Path | None = None     # skill_file일 때 복사 원본 (WP-SF)
    # ── 산출 방식 선언 (WP-5 — 종전에는 드라이버의 kind 튜플이었다) ──
    mode: OutputMode = OutputMode.TEXT
    phase: Phase = Phase.WRITE
    #: 타깃 중립 토큰 `${ROOT}`를 빌드 타깃 변수로 확장하는가 (WP-RT).
    expands_root: bool = False
    #: 토큰 계기판에서 세는 방식 (A5-lite).
    token_kind: TokenKind = TokenKind.NONE
    #: 공통 안내 파일인가 — notice()의 "추가로 실린다" 줄 대상.
    is_guide: bool = False
    #: 경로 충돌 게이트·`skipped` 보고의 대상인가. 트리 복사와 병합은 "경로
    #: 하나 = 산출 하나"라는 전제를 만족하지 않아 False다(오늘도 계획 밖이라
    #: 검사를 받지 않았고 `skipped`에도 실리지 않았다 — 형상 불변).
    exclusive: bool = True
    #: 단위 전용 메모 — 계획 단계에서 렌더한 텍스트, 러너 표지 등.
    payload: Any = None


class CompileUnit(ABC):
    """산출 종류 하나 — 자기 계획과 자기 쓰기를 안다.

    `id`/`ids`는 계획 행의 `kind`와 같은 문자열이다(`plan_kinds`가 소유).
    인스턴스가 여럿인 단위(`ComponentUnit`·`GuideUnit`)는 생성자에서 자기 id를
    인스턴스 속성으로 덮는다.
    """

    id: ClassVar[str] = ""
    #: 한 단위가 여러 kind를 낼 때. 비면 `(id,)`.
    ids: ClassVar[tuple[str, ...]] = ()

    def unit_ids(self) -> tuple[str, ...]:
        return tuple(self.ids) if self.ids else (self.id,)

    @abstractmethod
    def plan(self, ctx: "CompileContext", gate: "Gate") -> list[PlannedOutput]:
        """이 단위가 낼 산출 행 0..N개. 게이트 에러·경고는 `gate`에 넣는다."""

    @abstractmethod
    def emit(
        self, planned: PlannedOutput, ctx: "CompileContext", sink: "OutputSink",
    ) -> None:
        """계획 행 1건을 실제 산출로 만든다 — 쓰기는 전부 `sink` 경유."""

    def render(
        self, planned: PlannedOutput, ctx: "CompileContext",
    ) -> str | None:
        """순수 렌더(미리보기·테스트). 텍스트 산출이 아니면 None."""
        return None


class TextUnit(CompileUnit, ABC):
    """텍스트를 렌더해서 쓰는 단위 — 하위는 `render`만 구현한다."""

    def emit(self, planned, ctx, sink) -> None:
        sink.write_text(planned, self.render(planned, ctx) or "")


class CopyUnit(CompileUnit, ABC):
    """원본을 복사하는 단위 — 렌더할 텍스트가 없다."""


class MergeUnit(CompileUnit, ABC):
    """사용자 파일을 읽고 병합하는 단위 (LOCAL 설치, `Phase.INSTALL`).

    "경로 하나 = 산출 하나"라는 계획의 전제를 만족하지 않으므로 행은
    `exclusive=False`다 — 경로 충돌 게이트와 `skipped` 보고의 대상이 아니다.
    """
