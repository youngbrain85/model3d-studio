"""sheet_text — M2 판독의 입력 계약 (설계서 §5)."""

import json

import ezdxf
import pytest

from m3d.convert.frames import detect_frames, fallback_frame
from m3d.convert.sheet_text import (
    SCHEMA_VERSION,
    build_sheet_text,
    collect_texts,
    write_sheet_text,
)

PAPER_W, PAPER_H = 1189.0, 841.0


@pytest.fixture
def doc():
    d = ezdxf.new("R2018")
    blk = d.blocks.new("CXBLKA1-구조")
    blk.add_lwpolyline([(0, 0), (PAPER_W, 0), (PAPER_W, PAPER_H), (0, PAPER_H)], close=True)
    msp = d.modelspace()
    msp.add_blockref("CXBLKA1-구조", (0, 0), dxfattribs={"xscale": 200.0, "yscale": 200.0})
    # 도곽 내부: 용지 (100, 400)mm 위치, 높이 5mm → world (20000, 80000), h=1000
    msp.add_text("S=1:100", height=1000.0, dxfattribs={"insert": (20000.0, 80000.0)})
    # %%c 제어코드 — 제거돼야 한다
    msp.add_text("%%c2,800", height=700.0, dxfattribs={"insert": (40000.0, 40000.0)})
    # 도곽 밖 텍스트 — 페이지에서 제외돼야 한다
    msp.add_text("범위밖", height=1000.0, dxfattribs={"insert": (999999.0, 0.0)})
    return d


def test_collect_texts_kinds_and_control_codes(doc):
    texts = collect_texts(doc)
    strings = {t.text for t in texts}
    assert "S=1:100" in strings
    assert "2,800" in strings          # %%c 제거
    assert all(t.kind == "TEXT" for t in texts)


def test_build_filters_to_frame_and_converts_mm(doc):
    frame = detect_frames(doc)[0]
    payload = build_sheet_text(frame, collect_texts(doc), "C0050304-030")
    assert payload["schema"] == SCHEMA_VERSION
    assert payload["drawing_no"] == "C0050304-030"
    assert payload["page_no"] == 1
    assert payload["paper_mm"] == pytest.approx([PAPER_W, PAPER_H])
    assert payload["scale"] == pytest.approx(200.0)
    assert payload["fallback"] is False
    strings = [t["text"] for t in payload["texts"]]
    assert "범위밖" not in strings
    row = next(t for t in payload["texts"] if t["text"] == "S=1:100")
    assert (row["x_mm"], row["y_mm"]) == pytest.approx((100.0, 400.0))
    assert row["h_mm"] == pytest.approx(5.0)


def test_texts_sorted_top_to_bottom(doc):
    frame = detect_frames(doc)[0]
    payload = build_sheet_text(frame, collect_texts(doc), "X")
    ys = [t["y_mm"] for t in payload["texts"]]
    assert ys == sorted(ys, reverse=True)


def test_fallback_payload_has_null_scale():
    d = ezdxf.new("R2018")
    d.modelspace().add_text("본문", height=300.0, dxfattribs={"insert": (100.0, 100.0)})
    fr = fallback_frame(d)
    payload = build_sheet_text(fr, collect_texts(d), "C0050302-001")
    assert payload["fallback"] is True
    assert payload["scale"] is None
    # 폴백은 world 크기·world 오프셋 그대로
    assert payload["paper_mm"][0] == pytest.approx(fr.world_w)
    row = payload["texts"][0]
    assert row["h_mm"] == pytest.approx(300.0)


def test_write_roundtrip_utf8(tmp_path, doc):
    frame = detect_frames(doc)[0]
    payload = build_sheet_text(frame, collect_texts(doc), "C0050304-030")
    path = tmp_path / "t.json"
    write_sheet_text(payload, path)
    raw = path.read_text(encoding="utf-8")
    assert json.loads(raw) == payload
