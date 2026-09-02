"""LLM 입력 조립 — 8000px 원본을 비전 한도에 맞추고 sheet_text 를 안전하게 자른다."""

import base64
import json

from PIL import Image

from m3d.reading.inputs import (
    image_block,
    resize_for_vision,
    sheet_text_excerpt,
    tile_titleblock,
)


def _make_png(path, w=8000, h=5650):
    Image.new("RGB", (w, h), "white").save(path)
    return path


def test_resize_caps_long_side(tmp_path):
    src = _make_png(tmp_path / "s.png")
    out = tmp_path / "r.png"
    w, h = resize_for_vision(src, out)
    assert max(w, h) == 1568
    assert abs(w / h - 8000 / 5650) < 0.01     # 종횡비 보존
    with Image.open(out) as im:
        assert im.size == (w, h)


def test_resize_does_not_upscale_small(tmp_path):
    src = _make_png(tmp_path / "s.png", 800, 600)
    out = tmp_path / "r.png"
    w, h = resize_for_vision(src, out)
    assert (w, h) == (800, 600)                # 작은 이미지는 그대로


def test_resize_creates_missing_parent_dir(tmp_path):
    """작은 이미지 분기도 출력 디렉터리를 만든다 — Task 4 의 llm-input/ 이 여기 의존한다."""
    src = _make_png(tmp_path / "s.png", 800, 600)
    out = tmp_path / "nested" / "deep" / "r.png"
    w, h = resize_for_vision(src, out)
    assert (w, h) == (800, 600) and out.is_file()


def test_titleblock_tile_is_bottom_right(tmp_path):
    """표제란은 도면 우하단 — 원본 대비 작고, 우하단 픽셀을 포함해야 한다."""
    src = tmp_path / "s.png"
    img = Image.new("RGB", (1000, 800), "white")
    img.putpixel((995, 795), (0, 0, 0))        # 우하단 표식
    img.save(src)
    out = tmp_path / "t.png"
    tile_titleblock(src, out)
    with Image.open(out) as tile:
        assert tile.width < 1000 and tile.height < 800
        assert tile.convert("L").getextrema()[0] == 0   # 검은 픽셀 포함


def test_image_block_shape(tmp_path):
    src = _make_png(tmp_path / "s.png", 100, 100)
    block = image_block(src)
    assert block["type"] == "image"
    assert block["source"]["type"] == "base64"
    assert block["source"]["media_type"] == "image/png"
    base64.b64decode(block["source"]["data"])   # 디코드 가능해야 한다


def _write_sheet_text(path, n, drawing_no="C1"):
    rows = [{"x_mm": float(i), "y_mm": float(i), "h_mm": 1.0 + (i % 10),
             "kind": "TEXT", "text": f"t{i}"} for i in range(n)]
    path.write_text(json.dumps(
        {"schema": 1, "drawing_no": drawing_no, "page_no": 1,
         "paper_mm": [1189.0, 841.0], "scale": 100.0, "rotation_deg": 0,
         "fallback": False, "texts": rows}, ensure_ascii=False), encoding="utf-8")
    return path


def test_excerpt_keeps_all_when_small(tmp_path):
    p = _write_sheet_text(tmp_path / "s.json", 50)
    out = sheet_text_excerpt(p)
    assert len(out["texts"]) == 50
    assert out["truncated"] is False


def test_excerpt_truncates_by_text_height(tmp_path):
    """자를 때는 작은 글자부터 버린다 — 제목·치수 같은 큰 글자가 살아남아야 한다."""
    p = _write_sheet_text(tmp_path / "s.json", 3000)
    out = sheet_text_excerpt(p, max_rows=100)
    assert len(out["texts"]) == 100
    assert out["truncated"] is True
    assert out["total_texts"] == 3000
    assert min(t["h_mm"] for t in out["texts"]) >= 9.0   # 큰 글자만 남음


def test_excerpt_preserves_header_fields(tmp_path):
    p = _write_sheet_text(tmp_path / "s.json", 10, drawing_no="C0050304-030")
    out = sheet_text_excerpt(p)
    assert out["drawing_no"] == "C0050304-030"
    assert out["paper_mm"] == [1189.0, 841.0]
    assert out["scale"] == 100.0
