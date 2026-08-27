"""원본 `_manifest.txt` 파서 (설계서 §1-4).

형식: 탭 4필드 — `접두 / 등급 / 도면번호_제목 / 페이지수`. UTF-8, BOM 없음.
파일명 유도 규칙도 여기 둔다 — 둘 다 이 한 행에서 나오므로 함께 산다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DRAWING_NO_RE = re.compile(r"^(C\d{7}-\d{3})_(.+)$")
PAGES_RE = re.compile(r"^(\d+)p$")
VALID_GRADES = ("핵심", "참고")


class SourceManifestError(ValueError):
    """`_manifest.txt` 형식 위반."""


@dataclass(frozen=True)
class SourceSheet:
    ord: str
    grade: str
    drawing_no: str
    title: str
    page_count: int


def parse_source_manifest(path: Path) -> list[SourceSheet]:
    sheets: list[SourceSheet] = []
    text = path.read_text(encoding="utf-8")

    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue

        fields = line.split("\t")
        if len(fields) != 4:
            raise SourceManifestError(
                f"{path}:{lineno} 탭 4필드가 아닙니다 ({len(fields)}개): {line!r}"
            )

        ord_, grade, name, pages = (f.strip() for f in fields)

        if grade not in VALID_GRADES:
            raise SourceManifestError(
                f"{path}:{lineno} 알 수 없는 등급 {grade!r} (허용: {VALID_GRADES})"
            )

        name_match = DRAWING_NO_RE.match(name)
        if name_match is None:
            raise SourceManifestError(f"{path}:{lineno} 도면번호 추출 실패: {name!r}")

        pages_match = PAGES_RE.match(pages)
        if pages_match is None:
            raise SourceManifestError(f"{path}:{lineno} 페이지수 형식 오류: {pages!r}")

        sheets.append(
            SourceSheet(
                ord=ord_,
                grade=grade,
                drawing_no=name_match.group(1),
                title=name_match.group(2),
                page_count=int(pages_match.group(1)),
            )
        )

    return sheets


def png_filenames(sheet: SourceSheet) -> list[str]:
    """설계서 §1-4 — 1페이지는 접미사 없음, 여러 페이지는 `_p{i}`."""
    stem = f"{sheet.ord}_{sheet.drawing_no}_{sheet.title}"
    if sheet.page_count == 1:
        return [f"{stem}.png"]
    return [f"{stem}_p{i}.png" for i in range(1, sheet.page_count + 1)]


def dxf_filename(sheet: SourceSheet) -> str:
    return f"{sheet.drawing_no}.dxf"
