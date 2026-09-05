"""GLB → 실척 정사영 렌더 세트 (지식베이스 §6-3) — 참조 render_ab1_p4p5.py 이식.

matplotlib painter + 램버트 음영, Y-up. 단면 컷은 slice_mesh_plane(cap=True); 콘크리트(SLAB)
절단면은 강재보다 50mm 뒤로 물려 캡 공면 z-fighting 을 피한다(KB §2-13 렌더판).
4장: side_context(측면 맥락 — 인접 경간 스텁·교각 개략), front_section(정면 단면 절편),
bottom_iso(저면 아이소), interior_cells(내부 격실 컷). pilot 은 앞의 2장.

시선 규약: `eye` 는 카메라가 놓인 방향(카메라 = +eye·∞, 원점을 향해 본다). 화면 x = up×eye.
painter 정렬은 먼 삼각형부터(깊이 오름차순) — 참조 render 는 내림차순이라 먼 면이 위에 그려지는
역순 정렬이었다(2-상자 실증으로 확인, test_model_render). 대칭 부재에서는 표가 안 나지만
'저면 아이소' 가 실제로는 상면을 보여 주고 있었다 → 수정.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import trimesh
from trimesh.intersections import slice_mesh_plane
from trimesh.remesh import subdivide_to_size

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402

from m3d.model.spec import ModelSpec  # noqa: E402

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

SETBACK = 0.05
Y_UP = np.array([0.0, 1.0, 0.0])


def load_nodes(glb: Path):
    """GLB 월드 전개(그래프 노드 순회, KB §2-16) — (이름, 메시, 균일색) 목록."""
    sc = trimesh.load(str(glb))
    out = []
    for node in sc.graph.nodes_geometry:
        T, gname = sc.graph[node]
        m = sc.geometry[gname].copy()
        m.apply_transform(T)
        col = np.asarray(m.visual.face_colors)[0].astype(float)
        out.append((str(gname), m, col))
    return out


def cut(nodes, planes, conc_setback=SETBACK):
    kept = []
    for name, m, col in nodes:
        is_conc = "SLAB" in name or "BARRIER" in name
        mm = m
        for normal, origin in planes:
            o = np.asarray(origin, float)
            if is_conc:
                o = o + np.asarray(normal, float) * conc_setback
            try:
                mm = slice_mesh_plane(mm, plane_normal=normal, plane_origin=o, cap=True)
            except Exception:
                mm = slice_mesh_plane(mm, plane_normal=normal, plane_origin=o)
            if mm is None or len(mm.faces) == 0:
                mm = None
                break
        if mm is not None:
            kept.append((name, mm, col))
    return kept


def to_tris(nodes, max_edge=None):
    V, F, C = [], [], []
    off = 0
    for _, m, col in nodes:
        v, f = np.asarray(m.vertices, float), np.asarray(m.faces)
        if max_edge is not None:
            v, f = subdivide_to_size(v, f, max_edge=max_edge, max_iter=12)
        V.append(v)
        F.append(f + off)
        C.append(np.tile(col[:3] / 255.0, (len(f), 1)))
        off += len(v)
    return np.vstack(V), np.vstack(F), np.vstack(C)


def render(V, F, C, eye, up, out: Path, title, size=(12, 7), dpi=140, edge_alpha=0.18, extra=None):
    eye = np.asarray(eye, float); eye = eye / np.linalg.norm(eye)
    up = np.asarray(up, float)
    right = np.cross(up, eye); right /= np.linalg.norm(right)
    upv = np.cross(eye, right)
    P = V @ np.stack([right, upv, eye], axis=1)
    tri = P[F]
    depth = tri[:, :, 2].mean(axis=1)
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(n, axis=1); ln[ln == 0] = 1
    n = n / ln[:, None]
    sh = 0.45 + 0.55 * np.abs(n @ np.array([0.32, 0.40, 0.86]))
    col = np.clip(C * sh[:, None], 0, 1)
    order = np.argsort(depth)                       # 먼 것부터 (카메라 = +eye 방향)
    fig, ax = plt.subplots(figsize=size)
    ec = (0, 0, 0, edge_alpha) if edge_alpha > 0 else "none"
    ax.add_collection(PolyCollection([tri[i][:, :2] for i in order], facecolors=col[order],
                                     edgecolors=ec, linewidths=0.14))
    if extra:
        extra(ax, right, upv)
    xy = tri[:, :, :2].reshape(-1, 2)
    pad = 0.06 * max(np.ptp(xy[:, 0]), np.ptp(xy[:, 1]))
    ax.set_xlim(xy[:, 0].min() - pad, xy[:, 0].max() + pad)
    ax.set_ylim(xy[:, 1].min() - pad, xy[:, 1].max() + pad)
    ax.set_aspect("equal"); ax.axis("off")
    if title:
        ax.set_title(title, fontsize=11)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out), dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def run_render(glb: Path, out_dir: Path, spec: ModelSpec, *, pilot: bool = False) -> list[Path]:
    nodes = load_nodes(glb)
    z4, z5 = spec.coord.z_p4, spec.coord.z_p5
    zc = (z4 + z5) / 2.0
    written = []

    # 1) 측면 맥락 — 인접 경간 스텁(점선 사각)·교각 개략을 오버레이 (KB §6-3 "경간만 뚝 자른 렌더 금지")
    V, F, C = to_tris(nodes)
    y_lo, y_hi = float(V[:, 1].min()), float(V[:, 1].max())

    def context(ax, right, upv):
        # 정사영: 측면(eye=+x) 에서는 화면 x = −z 방향(right = up×eye), 화면 y = y
        for (za, zb) in ((z4 - 8.0, z4), (z5, z5 + 8.0)):
            xs = [-za, -zb, -zb, -za, -za]
            ys = [y_lo, y_lo, y_hi, y_hi, y_lo]
            ax.plot(xs, ys, "--", color="#888", linewidth=0.8)
        for zp in (z4, z5):                                       # 교각 개략(폭 3.0m, 아래 6m)
            ax.add_patch(plt.Rectangle((-zp - 1.5, y_lo - 6.0), 3.0, 6.0, fill=False,
                                       linestyle=":", edgecolor="#666"))
        ax.set_ylim(y_lo - 6.5, y_hi + 1.0)
    written.append(render(V, F, C, (1, 0, 0), Y_UP, out_dir / "side_context.png",
                          "측면 맥락 — P4~P5 %.0fm 변단면(인접 경간 스텁·교각 개략)" % spec.coord.span,
                          size=(20, 5), extra=context))

    # 2) 정면 단면 절편 — 중앙 부근 격벽(체인 k=n_cell//2)이 카메라(+z) 쪽 최전면이 되도록
    #    [zd−1.4, zd+0.1] 절편: 격벽 판면·개구·WG 가 앞, 프레임(zd−1.4)은 뒤. 화면 좌 = −x(보도측)
    zd = z4 + spec.diaphragm.spacing * (spec.diaphragm.n_cell // 2)
    z_lo, z_hi = zd - 1.4, zd + 0.1
    half = cut(nodes, [((0, 0, -1), (0, 0, z_hi)), ((0, 0, 1), (0, 0, z_lo))])
    V, F, C = to_tris(half)
    written.append(render(V, F, C, (0, 0, 1), Y_UP, out_dir / "front_section.png",
                          "정면 단면(z %.1f~%.1f 절편, +z 측에서, 좌=보도측) — 격벽·개구·WG·CS·방호벽" % (z_lo, z_hi),
                          size=(12, 7)))
    if pilot:
        return written

    # 3) 저면 아이소 — 카메라가 아래(−y)·+x·+z 방향: 하판·받침·스트럿·CS 가 보인다
    V, F, C = to_tris(nodes, max_edge=1.0)
    written.append(render(V, F, C, (0.55, -1.0, 0.4), Y_UP, out_dir / "bottom_iso.png",
                          "저면 아이소 — 하면 포물선 변단면·받침·WG 스트럿·외측빔 CS", size=(16, 8), edge_alpha=0.0))

    # 4) 내부 격실 컷 — x<0(보도측) 절개 + 격실 7개 구간, 상판·콘크리트 제거 후 위(+x·+y·+z)에서 들여다본다
    inner = cut(nodes, [((-1, 0, 0), (0.0, 0, 0)), ((0, 0, 1), (0, 0, z4 + 10.0)),
                        ((0, 0, -1), (0, 0, z4 + 30.0))])
    inner = [(n, m, c) for (n, m, c) in inner
             if "SLAB" not in n and "BARRIER" not in n and not n.endswith("BOX_TOP") and "_SP04_TF" not in n]
    V, F, C = to_tris(inner, max_edge=0.7)
    written.append(render(V, F, C, (0.7, 0.45, 0.85), Y_UP, out_dir / "interior_cells.png",
                          "내부 격실 컷(x<0 절개·상판 제거, P4+10~+30) — 격벽·개구·리브·프레임·수평보강재",
                          size=(14, 8), edge_alpha=0.0))
    return written
