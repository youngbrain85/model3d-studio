"""기하 유틸 — 로프트·압출·미러·존 분할 (참조 v2 포팅, 상수 의존 제거)."""

import numpy as np

from m3d.model import geom


def test_extrude_rect_volume_and_watertight():
    m = geom.extrude(geom.rect(0, 2, 0, 3), -1, 4)
    assert m.is_watertight and m.is_winding_consistent
    assert abs(m.volume - 2 * 3 * 5) < 1e-9


def test_box_prism_bounds_and_mirror():
    m = geom.box_prism(1, 3, 0, 1, 0, 2)
    assert np.allclose(m.bounds, [[1, 0, 0], [3, 1, 2]])
    mm = geom.mirror_mesh(m)
    assert np.allclose(mm.bounds, [[-3, 0, 0], [-1, 1, 2]])
    assert mm.is_watertight and abs(mm.volume - m.volume) < 1e-9   # 와인딩 보정 → 부피 양수 유지


def test_ear_clip_concave_polygon_preserves_area():
    poly = [(0, 0), (4, 0), (4, 3), (2, 1), (0, 3)]          # 오목 5각형(CCW)
    tris = geom.ear_clip(poly)
    assert len(tris) == 3
    area = 0.0
    for i0, i1, i2 in tris:
        (ax, ay), (bx, by), (cx, cy) = poly[i0], poly[i1], poly[i2]
        area += abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / 2
    assert abs(area - 8.0) < 1e-9                             # 12 − 4(노치)


def test_loft_trapezoid_stations_watertight():
    def poly(w):
        return geom.rect(-w, w, 0, 1)
    m = geom.loft([(0, poly(1)), (1, poly(2)), (2, poly(1))])
    assert m.is_watertight and m.volume > 0


def test_stations_and_zone_split():
    zs = geom.stations(0.0, 10.0, para_ranges=[(2.0, 4.0)], checks=[7.5, 20.0], step=0.7)
    assert zs[0] == 0.0 and zs[-1] == 10.0 and 7.5 in zs and 20.0 not in zs
    assert any(2.0 < z < 4.0 for z in zs)                     # 포물선 구간 세분
    assert geom.zone_split(0.0, 10.0, [3.0, 7.0, 12.0]) == [(0.0, 3.0), (3.0, 7.0), (7.0, 10.0)]


def test_zone_loft_concatenates_segments_watertight_each():
    def poly_fn(z):
        w = 1.0 + 0.1 * z
        return geom.rect(-w, w, 0, 1)
    m = geom.zone_loft(0.0, 4.0, poly_fn, breaks=[2.0], para_ranges=[], checks=[])
    assert m.volume > 0 and len(m.faces) > 12


def test_loft_normalizes_winding_and_repeated_closing_point():
    """폴리곤 방향이 반대이거나 첫 점이 끝에 다시 있어도 닫힌 솔리드를 만든다(M7 SLAB 3회 실패 원인).

    ear_clip 은 CCW 전제라 CW 입력이면 캡이 뒤집혀 조용히 수밀이 깨졌다.
    """
    from m3d.model.geom import loft, rect
    p = rect(-1, 1, -1, 1)
    ccw = loft([(0.0, p), (1.0, p)])
    cw = loft([(0.0, list(reversed(p))), (1.0, list(reversed(p)))])
    dup = loft([(0.0, p + [p[0]]), (1.0, p + [p[0]])])
    for m, name in ((ccw, "ccw"), (cw, "cw"), (dup, "dup")):
        assert m.is_watertight, name
        assert abs(m.volume - 4.0) < 1e-9, name       # 2×2 단면 × 높이 1


def test_loft_handles_concave_polygon_either_winding():
    from m3d.model.geom import loft
    notch = [(-2, 0), (-1, 0), (-1, 0.5), (1, 0.5), (1, 0), (2, 0), (2, 1), (-2, 1)]
    for poly in (notch, list(reversed(notch))):
        m = loft([(0.0, poly), (1.0, poly)])
        assert m.is_watertight and abs(m.volume - 3.0) < 1e-9
