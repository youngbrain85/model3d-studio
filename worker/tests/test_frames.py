"""도곽 감지 — 페이지 수·좌표 변환의 유일한 근원.

합성 DXF 로 검증한다: A0 도곽 블록(1189×841mm)을 스케일·회전 조합으로 삽입.
"""

import math

import ezdxf
import pytest

from m3d.convert.frames import SheetFrame, detect_frames, fallback_frame

PAPER_W, PAPER_H = 1189.0, 841.0


def _doc_with_frames(*inserts, block_name="CXBLKA1-구조"):
    """inserts: (insert_xy, scale, rotation_deg) 튜플들."""
    doc = ezdxf.new("R2018")
    blk = doc.blocks.new(block_name)
    blk.add_lwpolyline(
        [(0, 0), (PAPER_W, 0), (PAPER_W, PAPER_H), (0, PAPER_H)], close=True
    )
    # ATTDEF·TEXT 는 도곽 bbox 산정에서 제외돼야 한다 (원 로직 계승)
    blk.add_attdef("DI_DRWNO", insert=(2 * PAPER_W, 20))
    msp = doc.modelspace()
    for xy, scale, rot in inserts:
        msp.add_blockref(
            block_name, xy,
            dxfattribs={"xscale": scale, "yscale": scale, "rotation": rot},
        )
    return doc


def test_single_frame_world_rect():
    doc = _doc_with_frames(((1000.0, 2000.0), 200.0, 0.0))
    frames = detect_frames(doc)
    assert len(frames) == 1
    fr = frames[0]
    assert fr.page_no == 1 and not fr.fallback
    assert fr.scale == pytest.approx(200.0)
    assert (fr.x0, fr.y0) == pytest.approx((1000.0, 2000.0))
    assert fr.x1 == pytest.approx(1000.0 + PAPER_W * 200.0)
    assert fr.y1 == pytest.approx(2000.0 + PAPER_H * 200.0)
    assert (fr.paper_w, fr.paper_h) == pytest.approx((PAPER_W, PAPER_H))


def test_attdef_excluded_from_bbox():
    """ATTDEF 가 bbox 에 들어가면 도곽 폭이 2×PAPER_W 로 왜곡된다."""
    doc = _doc_with_frames(((0.0, 0.0), 1.0, 0.0))
    fr = detect_frames(doc)[0]
    assert fr.paper_w == pytest.approx(PAPER_W)


def test_two_frames_page_order_left_to_right():
    """같은 높이의 도곽 2개 — 왼쪽이 1페이지 (원 정렬: y 내림, x 오름)."""
    doc = _doc_with_frames(
        ((300000.0, 0.0), 200.0, 0.0),   # 오른쪽
        ((0.0, 0.0), 200.0, 0.0),        # 왼쪽
    )
    frames = detect_frames(doc)
    assert [f.page_no for f in frames] == [1, 2]
    assert frames[0].x0 < frames[1].x0


def test_rotated_90_frame():
    doc = _doc_with_frames(((5000.0, 1000.0), 100.0, 90.0))
    fr = detect_frames(doc)[0]
    assert fr.rot == 1
    # 90° CCW: world 폭 = paper 높이 × s, world 높이 = paper 폭 × s
    assert fr.world_w == pytest.approx(PAPER_H * 100.0)
    assert fr.world_h == pytest.approx(PAPER_W * 100.0)


def test_non_orthogonal_rotation_skipped():
    doc = _doc_with_frames(((0.0, 0.0), 100.0, 45.0))
    assert detect_frames(doc) == []


def test_small_block_not_a_frame():
    """200mm 미만 블록(범례 등)은 도곽이 아니다."""
    doc = ezdxf.new("R2018")
    blk = doc.blocks.new("CZBLK-LEGEND")
    blk.add_lwpolyline([(0, 0), (150, 0), (150, 100), (0, 100)], close=True)
    doc.modelspace().add_blockref("CZBLK-LEGEND", (0, 0))
    assert detect_frames(doc) == []


def test_to_paper_roundtrip_all_rotations():
    for rot in (0.0, 90.0, 180.0, 270.0):
        doc = _doc_with_frames(((1234.0, -777.0), 50.0, rot))
        fr = detect_frames(doc)[0]
        for pm in [(0.0, 0.0), (100.0, 200.0), (PAPER_W, PAPER_H), (600.5, 33.3)]:
            wx, wy = fr.paper_to_world(*pm)
            back = fr.to_paper(wx, wy)
            assert back == pytest.approx(pm, abs=1e-6), f"rot={rot} pm={pm}"


def test_to_paper_origin_is_frame_min_corner():
    doc = _doc_with_frames(((1000.0, 2000.0), 200.0, 0.0))
    fr = detect_frames(doc)[0]
    assert fr.to_paper(1000.0, 2000.0) == pytest.approx((0.0, 0.0))
    assert fr.to_paper(fr.x1, fr.y1) == pytest.approx((PAPER_W, PAPER_H))


def test_fallback_frame_from_extents():
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_line((10.0, 20.0), (510.0, 320.0))
    assert detect_frames(doc) == []
    fr = fallback_frame(doc)
    assert fr is not None and fr.fallback
    assert fr.scale is None and fr.paper_w is None
    assert (fr.x0, fr.y0) == pytest.approx((10.0, 20.0))
    assert (fr.x1, fr.y1) == pytest.approx((510.0, 320.0))
    # 폴백의 to_paper 는 world 오프셋 그대로
    assert fr.to_paper(110.0, 120.0) == pytest.approx((100.0, 100.0))


def test_fallback_empty_modelspace_is_none():
    doc = ezdxf.new("R2018")
    assert fallback_frame(doc) is None
