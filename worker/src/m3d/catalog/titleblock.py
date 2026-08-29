"""표제란 ATTRIB 추출 (설계서 §1-1).

표준 도곽 블록(CXBLKA1 계열)의 속성에서 도면번호·제목·척도를 읽는다.
블록 이름이 아니라 DI_DRWNO ATTRIB 보유 여부로 판정한다 — 이름 변형에 안전 (§11).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TitleBlock:
    drawing_no: str
    title: str
    subtitle: str
    scale: str


def extract_titleblocks(doc) -> list[TitleBlock]:
    found = []
    for e in doc.modelspace().query("INSERT"):
        try:
            tags = {a.dxf.tag: (a.dxf.text or "").strip() for a in e.attribs}
        except Exception:
            continue
        if "DI_DRWNO" not in tags or not tags["DI_DRWNO"]:
            continue
        ins = e.dxf.insert
        found.append((round(-ins.y, 1), ins.x, TitleBlock(
            drawing_no=tags["DI_DRWNO"],
            title=tags.get("DI_TITLE", ""),
            subtitle=tags.get("DI_SUBTITLE", ""),
            scale=tags.get("DA_HSCALE", ""),
        )))
    found.sort(key=lambda t: (t[0], t[1]))   # 페이지 순서: y 내림, x 오름 (frames 와 동일)
    return [t[2] for t in found]
