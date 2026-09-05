"""시트 단위 판독 (설계서 §4-1) — 캐시·검증 재시도·usage 기록.

재시도 로직은 client.call_structured 에만 둔다(여기서 중복 구현하지 않는다).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from m3d.config import Config
from m3d.reading import prompts
from m3d.reading.cache import (
    CacheMissError,
    cache_key,
    cache_path,
    load_cached,
    save_cached,
    schema_fingerprint,
)
from m3d.reading.client import MODEL_READ, build_client, call_structured, log_usage
from m3d.reading.inputs import (
    image_block,
    resize_for_vision,
    sheet_text_excerpt,
    tile_titleblock,
)
from m3d.reading.schema import SheetReadOut
from m3d.samples.manifest import sha256_file

MAX_TOKENS = 8000


@dataclass(frozen=True)
class PageRef:
    ord: str
    drawing_no: str
    page_no: int
    region: str
    png: Path
    text: Path


def list_pages(cfg: Config, dataset: str, region: str | None = None,
               ord_: str | None = None) -> list[PageRef]:
    """data/derived 의 페이지 산출물에서 판독 대상을 만든다. 계열은 ord 첫 글자."""
    base = cfg.derived_dir / dataset
    pages: list[PageRef] = []
    for png in sorted((base / "png").glob("*.png")):
        stem = png.stem                       # {ord}_{drawing_no}_p{n}
        ord_part, rest = stem.split("_", 1)
        drawing_no, page_part = rest.rsplit("_p", 1)
        if region and not ord_part.startswith(region):
            continue
        if ord_ and ord_part != ord_:
            continue
        text = base / "text" / f"{stem}.json"
        if not text.is_file():
            continue
        pages.append(PageRef(ord=ord_part, drawing_no=drawing_no,
                             page_no=int(page_part), region=ord_part[0],
                             png=png, text=text))
    return pages


def page_paper_mm(cfg: Config, dataset: str, page: PageRef) -> tuple[float, float]:
    """페이지의 용지 크기(mm) — text JSON 의 paper_mm 재사용 (crops.py 와 같은 소스).

    merge_region/review_region 의 post_validate 가 (ord,page_no)·mm_bbox 를 용지
    범위 안인지 검증하는 데 쓴다(cli.py 가 list_pages 결과로 이 맵을 만들어 넘긴다).
    """
    meta = json.loads(page.text.read_text(encoding="utf-8"))
    w, h = meta["paper_mm"]
    return float(w), float(h)


def _build_messages(cfg: Config, dataset: str, page: PageRef) -> tuple[list[dict], dict]:
    """user 메시지와 캐시 키에 넣을 입력 지문을 함께 만든다."""
    work = cfg.derived_dir / dataset / "llm-input"
    work.mkdir(parents=True, exist_ok=True)
    vis = work / f"{page.png.stem}.vis.png"
    tile = work / f"{page.png.stem}.title.png"
    resize_for_vision(page.png, vis)
    tile_titleblock(page.png, tile)
    excerpt = sheet_text_excerpt(page.text)

    parts = [
        {"type": "text", "text": f"도면 {page.drawing_no} {page.page_no}페이지 (계열 {page.region})."},
        image_block(vis),
        {"type": "text", "text": "표제란 확대:"},
        image_block(tile),
        {"type": "text", "text":
            "sheet_text (용지 mm 좌표, 이 값이 치수 판독의 1차 소스다):\n"
            + json.dumps(excerpt, ensure_ascii=False)},
        {"type": "text", "text":
            "이 시트에서 판독 가능한 치수를 readings 로, 해석이 갈리는 것을 "
            "ambiguities 로 내라."},
    ]
    inputs = {"ord": page.ord, "page_no": page.page_no,
              "image_sha": sha256_file(vis), "tile_sha": sha256_file(tile),
              "text_sha": sha256_file(page.text)}
    return [{"role": "user", "content": parts}], inputs


def read_sheet(cfg: Config, dataset: str, page: PageRef, *,
               force: bool = False, cache_only: bool = False,
               client=None) -> tuple[SheetReadOut, dict]:
    system = prompts.sheet_system(page.region)
    messages, inputs = _build_messages(cfg, dataset, page)
    key = cache_key({
        "kind": "sheet",
        "model": MODEL_READ,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "schema": schema_fingerprint(SheetReadOut),
        # 이미지 블록은 위 inputs 의 sha 로만 들어간다(본문은 키에 싣지 않는다)
        "user_text": [b["text"] for b in messages[0]["content"] if b["type"] == "text"],
        "inputs": inputs,
    })
    path = cache_path(cfg, dataset, "read", key)

    if not force:
        cached = load_cached(path)
        if cached is not None:
            usage = log_usage(cfg, dataset, {
                "stage": "read", "ord": page.ord, "page_no": page.page_no,
                "model": MODEL_READ, "in": 0, "out": 0, "cached": True,
                "attempt": 0, "retried": False, "stop_reason": None})
            return SheetReadOut.model_validate(cached), usage

    if cache_only:
        raise CacheMissError("read", f"{page.ord}p{page.page_no}", key)

    out, usage = call_structured(
        client or build_client(cfg), cfg, dataset,
        model=MODEL_READ, system=system, messages=messages,
        out_format=SheetReadOut, max_tokens=MAX_TOKENS, stage="read",
        extra={"ord": page.ord, "page_no": page.page_no},
    )
    save_cached(path, out.model_dump())
    return out, usage
