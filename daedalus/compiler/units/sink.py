# daedalus/compiler/units/sink.py
"""쓰기·복사·병합·토큰 계상의 **유일한 실행자** (WP-5).

`dry_run`·`${ROOT}` 확장·LF/UTF-8·`out_root is None` 규약을 아는 곳이 여기
하나다. 단위는 "무엇을 낼지"만 말하고 "어떻게 디스크에 닿는지"는 모른다 —
그래서 dry-run 누락(파일을 쓰는 새 단위가 dry_run을 깜빡하는 것)이 구조적으로
불가능하다.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from daedalus.compiler.emit import expand_root_token
from daedalus.compiler.token_report import TokenKind
from daedalus.compiler.units.base import PlannedOutput
from daedalus.compiler.units.context import CompileContext
from daedalus.compiler.units.paths import _is_link_like
from daedalus.model.validation import ValidationError


def _write_text(path: Path, text: str) -> None:
    """LF 줄바꿈 + UTF-8(BOM 없음)으로 쓴다 (결정적)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="" → 파이썬이 \n을 변환하지 않음(LF 그대로). text는 emit에서 LF 보장.
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _copy_files_tree(
    src_dir: Path, dst_dir: Path, clear_first: bool = True,
    dry_run: bool = False,
) -> list[Path]:
    """src_dir 트리를 dst_dir로 정렬 순회 복사한다 (결정적 로그).

    심볼릭 링크는 따라가지 않는다 — 디렉토리는 재귀하지 않고, 파일은 복사하지
    않는다. 기존 dst_dir는 복사 전 삭제한다(스테일 잔존 방지 — out 디렉토리
    전체가 아니라 files/ 하위만 지운다).

    dry_run(G3)이면 **순회만 하고 아무것도 만들거나 지우지 않는다** — 반환
    목록은 동일하다(같은 순회 코드가 계획과 실행을 함께 만든다. 열거를 따로
    구현하면 두 목록이 언젠가 어긋난다).

    반환: 실제로 복사된 파일의 dst_dir 기준 경로 목록 (정렬 순서, 디렉토리
    자체는 포함하지 않음).
    """
    # clear_first=False(LOCAL — out_dir가 사용자의 작업 폴더)는 기존 dst_dir를
    # 지우지 않고 덮어쓰기 복사만 한다. 사용자 파일 삭제 위험 > 스테일 잔존.
    if not dry_run:
        if clear_first and dst_dir.exists():
            shutil.rmtree(dst_dir)
        dst_dir.mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []
    for root, dirnames, filenames in os.walk(src_dir, followlinks=False):
        root_path = Path(root)
        rel_root = root_path.relative_to(src_dir)
        # in-place 정렬 + 심볼릭 링크 디렉토리 제외 — os.walk가 다음 순회에서
        # 이 리스트를 그대로 재사용하므로 순회 순서·재귀 범위를 동시에 제어한다.
        # Windows 디렉토리 정션(junction)은 is_symlink()가 False다 — 거르지
        # 않으면 files/ 밖 내용이 산출물로 새고, 자기 참조 정션은 폭주 재귀가
        # 된다(리뷰 실측). isjunction은 Python 3.12 표준.
        dirnames[:] = sorted(
            d for d in dirnames if not _is_link_like(root_path / d)
        )
        if not dry_run:
            for dirname in dirnames:
                (dst_dir / rel_root / dirname).mkdir(parents=True, exist_ok=True)
        for filename in sorted(filenames):
            src_file = root_path / filename
            if _is_link_like(src_file):
                continue
            dst_file = dst_dir / rel_root / filename
            if not dry_run:
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
            copied.append(dst_file)
    return copied


@dataclass(frozen=True)
class MergeOutcome:
    """병합 단위가 계산한 결과 — 쓰기는 `OutputSink.merge`가 한다.

    text: 쓸 최종 텍스트. None이면 쓰지 않는다(바뀔 것이 없다).
    warning: 병합하지 못한 이유. 있으면 쓰지 않고 경고만 낸다.
    token: (표지, kind, 본문) — 계상할 비용. 파일 전체가 아니라 **이 플러그인의
        구역 본문**만 세는 자리라 경로·텍스트가 쓰기 대상과 다르다.
    """
    text: str | None
    warning: ValidationError | None = None
    token: tuple[str, str, str] | None = None


class OutputSink:
    """계획 행을 디스크에 닿게 하는 실행자."""

    def __init__(self, result, ctx: CompileContext) -> None:
        self.result = result
        self.ctx = ctx

    # ── 경로 ──

    def out(self, rel) -> Path:
        """계획 상대 경로 → 실제 경로. out_dir 생략(dry_run)이면 상대 경로 그대로."""
        root = self.ctx.out_root
        return (root / rel) if root is not None else Path(rel)

    # ── 진단 ──

    def warn(self, warning: ValidationError) -> None:
        self.result.warnings.append(warning)

    def note_tokens(
        self, label: str, kind: str, text: str, *,
        token_kind: TokenKind, is_guide: bool = False,
    ) -> None:
        """토큰 리포트 계상 (A5-lite). `TokenKind.NONE`이면 세지 않는다."""
        if token_kind is TokenKind.NONE:
            return
        self.result.token_report.add(
            label, kind, text, token_kind=token_kind, is_guide=is_guide,
        )

    # ── 쓰기 ──

    def write_text(self, planned: PlannedOutput, text: str) -> None:
        if planned.expands_root:
            # 타깃 중립 토큰 ${ROOT}를 빌드 타깃에 맞는 CC 변수로 확장한다(WP-RT).
            # 본문 정본은 어느 타깃에도 기울지 않고, 여기서만 갈라진다.
            text = expand_root_token(text, self.ctx.project)
        path = self.out(planned.rel_path)
        if not self.ctx.dry_run:
            _write_text(path, text)
        self.result.written.append(path)
        # 토큰 리포트(A5-lite) — **확장 후 최종 텍스트**를 잰다. 실제로 컨텍스트에
        # 실리는 것이 그것이고, ${ROOT} 확장으로 길이가 달라진다.
        self.note_tokens(
            str(planned.rel_path), planned.kind, text,
            token_kind=planned.token_kind, is_guide=planned.is_guide,
        )

    def copy_file(self, planned: PlannedOutput, src: Path) -> None:
        dst = self.out(planned.rel_path)
        if not self.ctx.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        self.result.copied_files.append(dst)

    def copy_tree(
        self, planned: PlannedOutput, src: Path, *, clear_first: bool,
    ) -> None:
        # 스킬별 동봉 파일(WP-SF) 복사분을 덮어쓰지 않고 이어 붙인다 —
        # 대입이면 files/와 skill-files/를 함께 준 컴파일에서 앞의 목록이
        # 통째로 사라져 "복사 N개"가 거짓말이 된다.
        self.result.copied_files.extend(_copy_files_tree(
            src, self.out(planned.rel_path),
            clear_first=clear_first, dry_run=self.ctx.dry_run,
        ))

    # ── 병합 ──

    def read_existing(
        self, planned: PlannedOutput,
    ) -> tuple[str | None, OSError | None]:
        """병합 대상의 현재 내용 — (없음, None) / (내용, None) / (None, 예외).

        "파일이 없다"와 "읽지 못했다"를 구분한다 — 전자는 새로 만들면 되고
        후자는 사용자 파일을 건드리지 않고 경고만 내야 한다(원칙 5).
        """
        path = self.out(planned.rel_path)
        if not path.is_file():
            return None, None
        try:
            return path.read_text(encoding="utf-8"), None
        except OSError as exc:  # pragma: no cover - 권한 등 환경 의존
            return None, exc

    def merge(self, planned: PlannedOutput, outcome: MergeOutcome) -> None:
        """병합 결과를 반영한다 — 경고면 쓰지 않고, text가 None이어도 쓰지 않는다."""
        if outcome.warning is not None:
            self.warn(outcome.warning)
            return
        if outcome.text is None:
            return
        path = self.out(planned.rel_path)
        if not self.ctx.dry_run:
            _write_text(path, outcome.text)
        self.result.written.append(path)
        if outcome.token is not None:
            label, kind, text = outcome.token
            self.note_tokens(
                label, kind, text,
                token_kind=planned.token_kind, is_guide=planned.is_guide,
            )
