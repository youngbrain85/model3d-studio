"""기계 대조 판정 (설계서 §6) — 지식베이스 §3 의 구현.

판정 기준은 도면번호 하나다. 제목·척도는 원문 저장 + 노트(D4).
다페이지는 전 도곽 검사 — 페이지 간 번호 불일치도 편철 오류다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from m3d.catalog.titleblock import TitleBlock

_WS = re.compile(r"[\s　]+")


@dataclass(frozen=True)
class Verdict:
    status: str                    # match | mismatch | unreadable
    drawing_no: str | None
    title: str | None
    scale: str | None
    notes: tuple[str, ...]


def normalize_title(s: str) -> str:
    return _WS.sub("", s)


def reconcile(blocks: list[TitleBlock], drawing_no_filename: str,
              title_filename: str) -> Verdict:
    if not blocks:
        return Verdict("unreadable", None, None, None,
                       ("표제란 부재 — 도곽 블록 또는 DI_DRWNO 없음",))

    notes: list[str] = []
    first = blocks[0]

    content_nos = [b.drawing_no for b in blocks]
    if all(no == drawing_no_filename for no in content_nos):
        status = "match"
    else:
        status = "mismatch"
        distinct = sorted(set(no for no in content_nos if no != drawing_no_filename))
        notes.append(
            f"도면번호 불일치: 파일명 {drawing_no_filename} vs 내용 {', '.join(distinct)}"
        )

    title_raw = f"{first.title} {first.subtitle}".strip()
    content_norm = normalize_title(title_raw)
    if content_norm and content_norm not in normalize_title(title_filename):
        notes.append(f"제목 불일치(참고): 내용 '{title_raw}'")
    if len(blocks) > 1:
        others = {normalize_title(f"{b.title} {b.subtitle}".strip()) for b in blocks[1:]}
        if others - {content_norm}:
            notes.append("페이지 간 제목 상이(참고)")

    return Verdict(
        status=status,
        drawing_no=first.drawing_no,
        title=title_raw or None,
        scale=first.scale or None,
        notes=tuple(notes),
    )
