"""렌더 — painter 정렬(가까운 면이 위), 시범 2장·전체 4장 생성."""

import numpy as np
import matplotlib.image as mpimg

from m3d.model import render as R
from m3d.model.geom import box_prism


def test_painter_draws_nearest_surface_on_top(tmp_path):
    """카메라 = +eye 방향. eye=+z 일 때 z 큰 상자(빨강)가 z 작은 상자(파랑)를 가려야 한다."""
    near = box_prism(-1, 1, -1, 1, 4, 5)
    far = box_prism(-1, 1, -1, 1, 0, 1)
    nodes = [("FAR", far, np.array([0, 0, 255, 255.0])), ("NEAR", near, np.array([255, 0, 0, 255.0]))]
    V, F, C = R.to_tris(nodes)
    out = R.render(V, F, C, (0, 0, 1), R.Y_UP, tmp_path / "p.png", "", size=(3, 3), dpi=60)
    img = mpimg.imread(str(out))
    h, w = img.shape[:2]
    px = img[h // 2, w // 2, :3]
    assert px[0] > 0.5 and px[2] < 0.3, px                      # 빨강(가까운 면)


def test_screen_right_is_up_cross_eye(tmp_path):
    """eye=+z 에서 화면 오른쪽 = +x (카메라가 +z 에서 −z 를 본다)."""
    left = box_prism(-3, -1, -1, 1, 0, 1)
    right = box_prism(1, 3, -1, 1, 0, 1)
    nodes = [("L", left, np.array([0, 0, 255, 255.0])), ("R", right, np.array([255, 0, 0, 255.0]))]
    V, F, C = R.to_tris(nodes)
    out = R.render(V, F, C, (0, 0, 1), R.Y_UP, tmp_path / "lr.png", "", size=(4, 2), dpi=60)
    img = mpimg.imread(str(out))
    h, w = img.shape[:2]
    assert img[h // 2, int(w * 0.8), 0] > 0.5 and img[h // 2, int(w * 0.2), 2] > 0.5


def test_view_contract_roundtrips_bbox_corners(tmp_path):
    """뷰 계약: 장면 bbox 모서리가 (u,v)∈[0,1] 로 들어오고 origin 이 좌하단 한계와 일치한다."""
    a = box_prism(-1, -2, -3, 1, 0, 4)
    nodes = [("A", a, np.array([0, 150, 168, 255.0]))]
    V, F, C = R.to_tris(nodes)
    frame = {}
    R.render(V, F, C, (0.55, -1.0, 0.4), R.Y_UP, tmp_path / "v.png", "", size=(3, 3), dpi=40, frame_out=frame)
    assert set(frame) == {"eye", "up", "right", "xlim", "ylim"}
    c = R.view_contract(frame, center=V.mean(axis=0))
    o, u, v, n = (np.asarray(c[k]) for k in ("origin", "u_axis", "v_axis", "normal"))
    assert abs(np.dot(u, v)) < 1e-9 and abs(np.linalg.norm(n) - 1) < 1e-9
    for corner in [V.min(axis=0), V.max(axis=0), [V[:, 0].min(), V[:, 1].max(), V[:, 2].min()]]:
        d = np.asarray(corner, float) - o
        uu, vv = np.dot(d, u) / c["extent"][0], np.dot(d, v) / c["extent"][1]
        assert 0.0 <= uu <= 1.0 and 0.0 <= vv <= 1.0, (uu, vv)
    assert abs(np.dot(o, np.asarray(frame["right"])) - frame["xlim"][0]) < 1e-9


def test_run_render_pilot_writes_views_json(tmp_path):
    import json
    from m3d.model.builder import Builder
    from m3d.model.spec import ModelSpec
    spec = ModelSpec()
    b = Builder(spec)
    glb = tmp_path / "p.glb"
    b.export(b.build(pilot=True), glb)
    paths = R.run_render(glb, tmp_path / "renders", spec, pilot=True)
    assert [p.name for p in paths] == ["side_context.png", "front_section.png", "views.json"]
    views = json.loads((tmp_path / "renders" / "views.json").read_text(encoding="utf-8"))
    assert set(views) == {"side_context", "front_section"}
    assert views["front_section"]["file"] == "front_section.png" and len(views["front_section"]["extent"]) == 2
