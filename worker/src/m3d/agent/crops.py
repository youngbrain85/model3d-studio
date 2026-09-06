"""섹션 판독 근거 크롭 (M5 D3) — readings 의 basis 시트·mm_bbox 로 도면 크롭을 만든다(무과금).

M2a 판독이 남긴 근거 좌표를 재사용한다: 같은 시트·페이지의 근거는 bbox 합집합으로 1장, 여백 120mm, 최대 6장.
"""

from __future__ import annotations

import json
from pathlib import Path

import psycopg
from PIL import Image

from m3d.config import Config
from m3d.reading.crops import mm_bbox_to_px, render_crop
from m3d.reading.inputs import resize_for_vision
from m3d.reading.sheet import PageRef, list_pages

Image.MAX_IMAGE_PIXELS = None

SECTION_PATTERNS = {"DIA": r"다이아프램|격벽|DIAP|개구|문턱|잭업|수직보강"}
CONTEXT_MM = 120.0
MAX_IMAGES = 8
LONG_SIDE = 1400


def _priority(key: tuple[str, int]) -> tuple[int, str, int]:
    """강상형(C) 상세·단면 > 기타 상세(E) > 일반도(A·B·D·F) — 상한에 걸릴 때 덜 중요한 시트부터 뺀다."""
    ord_ = key[0]
    return (0 if ord_.startswith("C") else 1 if ord_.startswith("E") else 2, ord_, key[1])


def fetch_evidence(cfg: Config, dataset: str, pattern: str) -> list[dict]:
    """섹션 키워드에 맞는 판독 행(근거 시트·페이지·mm_bbox 포함)."""
    with psycopg.connect(cfg.require_db_url()) as conn, conn.cursor() as cur:
        cur.execute(
            "select s.ord, coalesce(p.page_no, 1), r.item, r.value_raw, r.unit, r.status, r.basis_mm_bbox "
            "from readings r join projects pj on pj.id = r.project_id join sheets s on s.id = r.basis_sheet_id "
            "left join sheet_pages p on p.id = r.basis_page_id "
            "where pj.slug = %s and r.item ~* %s order by s.ord, p.page_no, r.item", (dataset, pattern))
        return [{"ord": o, "page_no": int(pn), "item": it, "value": v, "unit": u, "status": st, "mm_bbox": bb}
                for (o, pn, it, v, u, st, bb) in cur.fetchall()]


def _paper_mm(page: PageRef) -> tuple[float, float]:
    w, h = json.loads(page.text.read_text(encoding="utf-8"))["paper_mm"]
    return float(w), float(h)


def section_crops(cfg: Config | None, dataset: str, evidence: list[dict], out_dir: Path, *,
                  pages: dict[tuple[str, int], PageRef] | None = None) -> list[dict]:
    """근거 → 크롭 PNG 목록. pages 를 주면(테스트) 페이지 탐색 없이 그 페이지를 쓴다."""
    if pages is None:
        pages = {(p.ord, p.page_no): p for p in list_pages(cfg, dataset)}
    groups: dict[tuple[str, int], list[dict]] = {}
    for ev in evidence:
        groups.setdefault((ev["ord"], int(ev.get("page_no") or 1)), []).append(ev)
    out: list[dict] = []
    out_dir = Path(out_dir)
    for (ord_, pno), evs in sorted(groups.items(), key=lambda kv: _priority(kv[0])):
        page = pages.get((ord_, pno))
        if page is None:
            continue
        paper = _paper_mm(page)
        with Image.open(page.png) as im:
            size = im.size
        boxes = [b for b in (e.get("mm_bbox") for e in evs) if isinstance(b, (list, tuple)) and len(b) == 4]
        boxes = [b for b in boxes if 0 <= min(b[0], b[2]) and max(b[0], b[2]) <= paper[0]
                 and 0 <= min(b[1], b[3]) and max(b[1], b[3]) <= paper[1]]
        if not boxes:
            continue
        union = [min(min(b[0], b[2]) for b in boxes), min(min(b[1], b[3]) for b in boxes),
                 max(max(b[0], b[2]) for b in boxes), max(max(b[1], b[3]) for b in boxes)]
        try:
            px = mm_bbox_to_px(union, paper, size, context_mm=CONTEXT_MM)
            path = out_dir / f"{ord_}_p{pno}.png"
            render_crop(page.png, px, path)
        except ValueError:
            continue
        resize_for_vision(path, path, long_side=LONG_SIDE)
        out.append({"ord": ord_, "page_no": pno, "path": path,
                    "items": [{"item": e["item"], "value": e.get("value"), "unit": e.get("unit"), "status": e.get("status")} for e in evs]})
        if len(out) >= MAX_IMAGES:
            break
    return out
