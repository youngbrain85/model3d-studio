"""도곽(시트 프레임) 감지와 world↔용지 mm 좌표 변환 (설계서 §1-2의 1).

원 로직: render_pipeline.py 의 frames 블록 이식. "BLK" 포함 블록명 + 정의 bbox
(ATTDEF/TEXT/MTEXT 제외) ≥200mm 휴리스틱 — 이름 완전일치에 걸지 않는다 (§11).
용지 좌표 원점은 도곽 world rect 의 최소 모서리다 (블록 정의 원점이 아님).
"""

from __future__ import annotations

from dataclasses import dataclass

from ezdxf import bbox as ezbbox

MIN_FRAME_MM = 200.0
_EXCLUDE_IN_BBOX = ("ATTDEF", "TEXT", "MTEXT")


@dataclass(frozen=True)
class SheetFrame:
    page_no: int
    x0: float
    y0: float
    x1: float
    y1: float
    scale: float | None      # world 단위 / 용지 mm. 폴백이면 None
    rot: int                 # 0..3 (×90° CCW)
    paper_w: float | None    # 용지 mm. 폴백이면 None
    paper_h: float | None
    fallback: bool = False

    @property
    def world_w(self) -> float:
        return self.x1 - self.x0

    @property
    def world_h(self) -> float:
        return self.y1 - self.y0

    def contains(self, wx: float, wy: float, margin: float = 1.0) -> bool:
        return (self.x0 - margin <= wx <= self.x1 + margin
                and self.y0 - margin <= wy <= self.y1 + margin)

    def to_paper(self, wx: float, wy: float) -> tuple[float, float]:
        """world → 용지 mm (원 로직 이식 — 회전 역변환 포함)."""
        rx, ry = wx - self.x0, wy - self.y0
        if self.scale is None:
            return rx, ry
        if self.rot == 0:
            px, py = rx, ry
        elif self.rot == 1:      # 90° CCW
            px, py = ry, self.world_w - rx
        elif self.rot == 2:
            px, py = self.world_w - rx, self.world_h - ry
        else:                    # 270°
            px, py = self.world_h - ry, rx
        return px / self.scale, py / self.scale

    def paper_to_world(self, px: float, py: float) -> tuple[float, float]:
        """용지 mm → world (M2 크롭이 같은 변환을 쓴다)."""
        if self.scale is None:
            return self.x0 + px, self.y0 + py
        s = self.scale
        if self.rot == 0:
            rx, ry = px * s, py * s
        elif self.rot == 1:
            rx, ry = self.world_w - py * s, px * s
        elif self.rot == 2:
            rx, ry = self.world_w - px * s, self.world_h - py * s
        else:
            rx, ry = py * s, self.world_h - px * s
        return self.x0 + rx, self.y0 + ry


def detect_frames(doc) -> list[SheetFrame]:
    msp = doc.modelspace()
    blkdef_cache: dict[str, tuple[float, float, float, float] | None] = {}
    raw: list[dict] = []

    for e in msp.query("INSERT"):
        name = e.dxf.name
        if "BLK" not in name.upper():
            continue
        if name not in blkdef_cache:
            try:
                bdef = doc.blocks.get(name)
                bb = ezbbox.extents(
                    (x for x in bdef if x.dxftype() not in _EXCLUDE_IN_BBOX),
                    fast=True,
                )
                blkdef_cache[name] = (
                    (bb.extmin.x, bb.extmin.y, bb.extmax.x, bb.extmax.y)
                    if bb.has_data else None
                )
            except Exception:
                blkdef_cache[name] = None
        pb = blkdef_cache[name]
        if pb is None:
            continue
        pw, ph = pb[2] - pb[0], pb[3] - pb[1]
        if pw < MIN_FRAME_MM or ph < MIN_FRAME_MM:
            continue

        sx = abs(e.dxf.xscale)
        rot = e.dxf.rotation % 360.0
        if min(abs(rot - a) for a in (0, 90, 180, 270, 360)) > 0.5:
            continue  # 직교 회전만 도곽으로 인정 (원 로직)
        r = round(rot / 90.0) % 4

        ins = e.dxf.insert
        corners = []
        for cx, cy in ((pb[0], pb[1]), (pb[2], pb[1]), (pb[2], pb[3]), (pb[0], pb[3])):
            x, y = cx * sx, cy * sx
            for _ in range(r):
                x, y = -y, x
            corners.append((ins.x + x, ins.y + y))
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        raw.append(dict(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys),
                        scale=sx, rot=r, pw=pw, ph=ph))

    raw.sort(key=lambda f: (round(f["y0"], 1) * -1, f["x0"]))
    return [
        SheetFrame(page_no=i, x0=f["x0"], y0=f["y0"], x1=f["x1"], y1=f["y1"],
                   scale=f["scale"], rot=f["rot"],
                   paper_w=f["pw"], paper_h=f["ph"])
        for i, f in enumerate(raw, start=1)
    ]


def fallback_frame(doc) -> SheetFrame | None:
    """도곽 미검출 시 modelspace 전체 bbox 로 1페이지 (원 로직의 폴백)."""
    bb = ezbbox.extents(doc.modelspace(), fast=True)
    if not bb.has_data:
        return None
    return SheetFrame(page_no=1,
                      x0=bb.extmin.x, y0=bb.extmin.y,
                      x1=bb.extmax.x, y1=bb.extmax.y,
                      scale=None, rot=0, paper_w=None, paper_h=None,
                      fallback=True)
