"""sheet_text 추출 (설계서 §1-2의 4·§5) — 원 파이프라인의 텍스트 인벤토리 이식.

TEXT/MTEXT + DIMENSION 지오메트리 블록 내 텍스트를 용지 mm 좌표로 덤프한다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from m3d.convert.frames import SheetFrame

SCHEMA_VERSION = 1
_CONTROL_CODES = re.compile(r"%%[cdpu]", re.I)


@dataclass(frozen=True)
class WorldText:
    x: float
    y: float
    h: float
    text: str
    kind: str  # "TEXT" | "DIM"


def _clean(s: str) -> str:
    return _CONTROL_CODES.sub("", s).strip()


def collect_texts(doc) -> list[WorldText]:
    msp = doc.modelspace()
    out: list[WorldText] = []

    for e in msp.query("TEXT MTEXT"):
        try:
            if e.dxftype() == "TEXT":
                s, h, p = e.dxf.text, e.dxf.height, e.dxf.insert
            else:
                s, h, p = e.plain_text(), e.dxf.char_height, e.dxf.insert
            s = _clean(s)
            if s:
                out.append(WorldText(p.x, p.y, h, s, "TEXT"))
        except Exception:
            pass  # 손상 엔티티는 건너뛴다 (원 로직 — 텍스트 하나에 전체를 죽이지 않음)

    for e in msp.query("DIMENSION"):
        try:
            bdef = doc.blocks.get(e.dxf.geometry)
            for t in bdef.query("TEXT MTEXT"):
                if t.dxftype() == "TEXT":
                    s, h, p = t.dxf.text, t.dxf.height, t.dxf.insert
                else:
                    s, h, p = t.plain_text(), t.dxf.char_height, t.dxf.insert
                s = _clean(s)
                if s:
                    out.append(WorldText(p.x, p.y, h, s, "DIM"))
        except Exception:
            pass

    return out


def build_sheet_text(frame: SheetFrame, texts: list[WorldText], drawing_no: str) -> dict:
    rows = []
    for t in texts:
        if not frame.contains(t.x, t.y):
            continue
        px, py = frame.to_paper(t.x, t.y)
        h_mm = t.h / frame.scale if frame.scale else t.h
        rows.append({"x_mm": round(px, 2), "y_mm": round(py, 2),
                     "h_mm": round(h_mm, 3), "kind": t.kind, "text": t.text})
    rows.sort(key=lambda r: (-r["y_mm"], r["x_mm"]))

    if frame.scale is not None:
        paper_mm = [frame.paper_w, frame.paper_h]
    else:
        paper_mm = [frame.world_w, frame.world_h]

    return {
        "schema": SCHEMA_VERSION,
        "drawing_no": drawing_no,
        "page_no": frame.page_no,
        "paper_mm": paper_mm,
        "scale": frame.scale,
        "rotation_deg": frame.rot * 90,
        "fallback": frame.fallback,
        "texts": rows,
    }


def write_sheet_text(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
