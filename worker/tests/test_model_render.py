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
