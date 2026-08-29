"""렌더 — ACI-7 가드가 살아있는지를 픽셀로 검증한다.

원 프로젝트 실사고: 배경 미지정 시 ACI-7(흑백 자동) 엔티티가 흰색으로 그려져
238파일에서 텍스트가 비가시화됐다. 여기서는 ACI-7 선을 그려 넣고
'어두운 픽셀이 실제로 존재하는가'를 단언한다 — 가드가 죽으면 전백 이미지가 된다.
"""

import ezdxf
import numpy as np
import pytest
from PIL import Image

from m3d.convert.frames import detect_frames
from m3d.convert.render import prepare_doc, render_frame

PAPER_W, PAPER_H = 1189.0, 841.0


@pytest.fixture
def doc():
    d = ezdxf.new("R2018")
    blk = d.blocks.new("CXBLKA1-구조")
    blk.add_lwpolyline([(0, 0), (PAPER_W, 0), (PAPER_W, PAPER_H), (0, PAPER_H)], close=True)
    msp = d.modelspace()
    msp.add_blockref("CXBLKA1-구조", (0, 0), dxfattribs={"xscale": 1.0, "yscale": 1.0})
    # ACI-7 (흑백 자동) 대각선 — 가드의 검증 대상
    msp.add_line((100, 100), (1000, 700), dxfattribs={"color": 7})
    return d


def test_render_size_and_aspect(tmp_path, doc):
    frame = detect_frames(doc)[0]
    out = tmp_path / "sheet.png"
    w, h = render_frame(doc, frame, out, sheet_px=400)
    assert out.is_file()
    with Image.open(out) as img:
        assert (img.width, img.height) == (w, h)
    assert max(w, h) == 400
    # 종횡비 ≈ 1189:841 (savefig 반올림 ±2px 허용)
    assert h == pytest.approx(400 * PAPER_H / PAPER_W, abs=2)


def test_aci7_renders_dark_on_white(tmp_path, doc):
    """ACI-7 선이 흰 배경 위에 '어둡게' 그려져야 한다 — 전백이면 가드 회귀."""
    frame = detect_frames(doc)[0]
    out = tmp_path / "sheet.png"
    render_frame(doc, frame, out, sheet_px=400)
    arr = np.asarray(Image.open(out).convert("L"))
    assert arr.min() < 100, "어두운 픽셀 없음 — ACI-7 가드가 죽었다"
    assert (arr > 240).mean() > 0.9, "배경이 흰색이 아니다"


def test_prepare_doc_darkens_bright_colors(doc):
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 10), dxfattribs={"color": 2})  # yellow
    prepare_doc(doc)
    line = [e for e in msp.query("LINE") if e.dxf.color == 2][0]
    assert line.rgb == (140, 115, 0)  # DARKEN 맵 (원 파이프라인)


def test_fills_drawn_before_lines(tmp_path, doc):
    """SOLID 가 선·텍스트를 덮지 않도록 선행 드로우 — 순서 로직만 픽셀로 확인.

    프레임 중앙에 SOLID 를 깔고 그 위 ACI-7 선을 긋는다. 선행 드로우가 맞으면
    선(어두움)이 SOLID(연회색) 위에 보인다 → 최암 픽셀이 SOLID 색보다 어둡다.

    전체 이미지가 아닌 내부 크롭만 본다 — 도곽 테두리(픽스처의 프레임 사각형)가
    색 미지정(BYLAYER→레이어 0→ACI-7)이라 흰 배경 가드에 의해 검정으로 그려지고,
    x=0 열 등 테두리에 항상 어두운 픽셀을 공급한다. 이걸 포함해 arr.min() 을 전체
    이미지에서 재면 선행 드로우가 깨져도 테두리 흑픽셀 때문에 항상 통과 — 공허한
    단언이 된다.
    """
    msp = doc.modelspace()
    solid = msp.add_solid([(80, 80), (1100, 80), (80, 760), (1100, 760)])
    solid.rgb = (200, 200, 200)
    frame = detect_frames(doc)[0]
    out = tmp_path / "sheet.png"
    render_frame(doc, frame, out, sheet_px=400)
    arr = np.asarray(Image.open(out).convert("L"))
    interior = arr[8:-8, 8:-8]   # 도곽 테두리(x=0 열의 흑픽셀) 제외 — 전체 min 은 공허했다
    assert interior.min() < 100, "선이 SOLID 에 덮였다 — 선행 드로우 회귀"
