"""§3~§10 부재 — 프레임·종리브·수평보강재·WG·CS·슬래브·방호벽·SP04·받침 (참조 v2 포팅, 값은 ModelSpec).

`add_all(b, add)` 가 Builder(§1·§2 프로파일 함수·상수)를 받아 나머지 노드를 추가한다.
단순화 항목 번호([A6]~[A21])는 builder.py 헤더 참조.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from m3d.model.builder import COL_BRG, COL_CONC, COL_SOLE, COL_STEEL, INS, Builder
from m3d.model.geom import box_prism, extrude, loft, mirror_mesh, mirror_poly, paint, rect


# ── §3 개방 프레임 25개 — z = P4 + spacing·k + offset. 부재 6개/프레임 ──────────────
def frame_row(b: Builder, dmin: float):
    key = round(dmin, 1)
    for row in b.s.frame.rows:
        if any(abs(key - d) < 1e-6 for d in row.d_list):
            return row
    raise ValueError("프레임 타입 없음: d=%r" % dmin)


def build_frame_parts(b: Builder, k: int) -> dict[str, trimesh.Trimesh]:
    """프레임 1개 → {접미사: 메시} 6부재. [A6] 플랜지 t=웹 t 근사(G1 상면 제외), [A7] V-STIFF 내공 중앙."""
    zf = b.Z_P4 + b.s.frame.offset + k * b.s.diaphragm.spacing
    row = frame_row(b, min(zf - b.Z_P4, b.Z_P5 - zf))
    twt, hwt = row.top_web
    tft = row.top_flange_t if row.top_flange_t is not None else twt
    wft = hwt
    twb, hwb = row.bot_web
    tfb, wfb = twb, hwb
    tv, wv, lv = row.vstiff
    xh = b.dia_half_w(zf)
    y_t, y_b = b.y_web_top(zf), b.y_web_bot(zf)
    out = {}
    out["TRW"] = box_prism(-xh, xh, y_t - hwt, y_t + INS, zf - twt / 2, zf + twt / 2)
    out["TRF"] = box_prism(-xh, xh, y_t - hwt - tft, y_t - hwt + INS, zf - wft / 2, zf + wft / 2)
    out["BRW"] = box_prism(-xh, xh, y_b - INS, y_b + hwb, zf - twb / 2, zf + twb / 2)
    out["BRF"] = box_prism(-xh, xh, y_b + hwb - INS, y_b + hwb + tfb, zf - wfb / 2, zf + wfb / 2)
    yc = (y_t + y_b) / 2.0
    xw_in = b.s.box.x_web - b.t_web(zf)
    for sfx, sx in (("VSL", -1), ("VSR", +1)):
        x0, x1 = sorted((sx * (xw_in + INS), sx * (xw_in - wv)))
        out[sfx] = box_prism(x0, x1, yc - lv / 2, yc + lv / 2, zf - tv / 2, zf + tv / 2)
    for m in out.values():
        paint(m, COL_STEEL)
    return out


# ── §4 종리브 존 모델 ─────────────────────────────────────────────────────────────
def _cols(n: int, pitch: float) -> list[float]:
    return [(i - (n - 1) / 2.0) * pitch for i in range(n)]


def build_rib_top(b: Builder, x_c, z0, z1, t, h):
    return paint(b._zone_loft(z0, z1, lambda z: rect(
        x_c - t / 2, x_c + t / 2, b.y_web_top(z) - h, b.y_web_top(z) + INS)), COL_STEEL)


def build_rib_bot(b: Builder, x_c, z0, z1, t, h):
    return paint(b._zone_loft(z0, z1, lambda z: rect(
        x_c - t / 2, x_c + t / 2, b.y_web_bot(z) - INS, b.y_web_bot(z) + h)), COL_STEEL)


def rib_layout(b: Builder):
    """리브 스트립 (이름, 종류, x, z0, z1, t, h) — 존 경계·SP04 분절 (§4)."""
    r = b.s.rib
    Z4, Z5 = b.Z_P4, b.Z_P5
    z_sp = Z4 + b.s.box.z_sp04_offset
    tp, tm, bp, bm = r.top_pier, r.top_mid, r.bot_pier, r.bot_mid
    x_tp, x_tm, x_bp, x_bm = _cols(tp.cols, tp.pitch), _cols(tm.cols, tm.pitch), _cols(bp.cols, bp.pitch), _cols(bm.cols, bm.pitch)
    out = []
    zt0, zt1 = Z4 + r.top_switch[0], Z4 + r.top_switch[1]
    zt2, zt3 = Z5 - r.top_switch[1], Z5 - r.top_switch[0]
    for i, x in enumerate(x_tp):
        out.append(("TP4_%d" % (i + 1), "T", x, Z4, zt0, tp.t, tp.h))
        out.append(("TP5_%d" % (i + 1), "T", x, zt3, Z5, tp.t, tp.h))
    for i, x in enumerate(x_tp + x_tm):
        t_, h_ = (tp.t, tp.h) if i < len(x_tp) else (tm.t, tm.h)
        out.append(("TX4_%02d" % (i + 1), "T", x, zt0, zt1, t_, h_))
        out.append(("TX5_%02d" % (i + 1), "T", x, zt2, zt3, t_, h_))
    for i, x in enumerate(x_tm):
        out.append(("TMA_%d" % (i + 1), "T", x, zt1, z_sp, tm.t, tm.h))
        out.append(("TMB_%d" % (i + 1), "T", x, z_sp, zt2, tm.t, tm.h))
    zb0, zb1 = Z4 + r.bot_switch[0], Z4 + r.bot_switch[1]
    zb2, zb3 = Z5 - r.bot_switch[1], Z5 - r.bot_switch[0]
    for i, x in enumerate(x_bp):
        out.append(("BP4A_%d" % (i + 1), "B", x, Z4, z_sp, bp.t, bp.h))
        out.append(("BP4B_%d" % (i + 1), "B", x, z_sp, zb0, bp.t, bp.h))
        out.append(("BP5_%d" % (i + 1), "B", x, zb3, Z5, bp.t, bp.h))
    for i, x in enumerate(x_bp + x_bm):
        t_, h_ = (bp.t, bp.h) if i < len(x_bp) else (bm.t, bm.h)
        out.append(("BX4_%02d" % (i + 1), "B", x, zb0, zb1, t_, h_))
        out.append(("BX5_%02d" % (i + 1), "B", x, zb2, zb3, t_, h_))
    for i, x in enumerate(x_bm):
        out.append(("BM_%d" % (i + 1), "B", x, zb1, zb2, bm.t, bm.h))
    return out


# ── §5 복부 수평보강재 (평강, 웹 내면 양측) ────────────────────────────────────────
def _hst_poly(b: Builder, yc, side):
    hs = b.s.hstiff
    x_end = b.s.box.x_web - 0.010                     # 웹 판 내부 관통 삽입 고정단
    p = rect(x_end - (hs.h + INS), x_end, yc - hs.t / 2, yc + hs.t / 2)
    return mirror_poly(p) if side < 0 else p


def build_hst_upper(b: Builder, side):
    hs = b.s.hstiff
    return paint(b._zone_loft(b.Z_P4 + hs.upper_span, b.Z_P5 - hs.upper_span,
                              lambda z: _hst_poly(b, b.y_web_top(z) - hs.upper_drop, side)), COL_STEEL)


def build_hst_lower(b: Builder, side, pier, factor):
    """하단 2열: 받침선 ±lower_span, 패널(spacing/2) 절선으로 H 비례 추종 [A20]."""
    hs = b.s.hstiff
    panel = b.s.diaphragm.spacing / 2.0
    n = int(round(hs.lower_span / panel))
    zs = [b.Z_P4 + panel * i for i in range(n + 1)] if pier == 4 else [b.Z_P5 - panel * i for i in range(n, -1, -1)]
    st = [(z, _hst_poly(b, b.y_web_bot(z) + factor * b.h_box(z), side)) for z in zs]
    return paint(loft(st), COL_STEEL)


# ── §6 외측가로보 WG 26쌍 — 실형상 ────────────────────────────────────────────────
class WGGeom:
    """WG 절선·니치 원호 (crown 상대 좌표, X' = 웹면 기점) [A8]~[A11]."""

    SHIFT = 0.003        # [A9] 공면 회피 상향 시프트
    X0 = -0.010          # 웹 판 내부 관통 삽입

    def __init__(self, b: Builder):
        w, s = b.s.wg, b.s.slab
        self.w = w
        self.U0 = -(s.cant_drop[0][1] + w.fl_t) + self.SHIFT          # 상플랜지 밑면 root(crown 상대)
        self.KNEE = (w.knee[0], -(b.s.coord.t_slab_crown + w.knee[1]) + self.SHIFT)
        self.TIP_BOT = self.u(w.length) + w.fl_t - w.tip_depth        # 선단블록 하면
        self.niche_xt, self.niche_arc = self._solve_niche()

    def u(self, xp):
        w = self.w
        return self.U0 - w.flange_slope * max(0.0, min(xp, w.flange_flat1) - w.flange_flat0)

    def _solve_niche(self):
        w = self.w
        r = w.niche_r
        nx, ny = w.flange_slope, -1.0
        nn = math.hypot(nx, ny)
        nx, ny = nx / nn, ny / nn
        kx, ky = self.KNEE

        def f(xt):
            ox = xt + nx * r
            oy = (self.u(xt) - w.depth0) + ny * r
            return math.hypot(kx - ox, ky - oy) - r
        lo, hi = 2.0, kx - 0.01
        assert f(lo) > 0 > f(hi), "니치 원호 해 없음"
        for _ in range(80):
            mid = (lo + hi) / 2.0
            if f(mid) > 0:
                lo = mid
            else:
                hi = mid
        xt = (lo + hi) / 2.0
        ox = xt + nx * r
        oy = (self.u(xt) - w.depth0) + ny * r
        a0 = math.atan2(self.u(xt) - w.depth0 - oy, xt - ox)
        a1 = math.atan2(ky - oy, kx - ox)
        pts = [(ox + r * math.cos(a0 + (a1 - a0) * i / 8.0), oy + r * math.sin(a0 + (a1 - a0) * i / 8.0))
               for i in range(1, 8)]
        return xt, pts

    def bottom_polyline(self):
        w = self.w
        pts = [(self.X0, self.U0 - w.depth0), (w.flange_flat0, self.U0 - w.depth0),
               (self.niche_xt, self.u(self.niche_xt) - w.depth0)]
        pts += self.niche_arc
        pts += [self.KNEE, (w.flange_flat1, self.TIP_BOT), (w.length, self.TIP_BOT)]
        return pts


def build_wg_main(b: Builder, g: WGGeom, zc):
    w = b.s.wg
    xw = b.s.box.x_web
    cr = b.y_crown(zc)
    bot = g.bottom_polyline()
    outline = list(bot) + [(w.length, g.u(w.length) + INS), (w.flange_flat1, g.u(w.flange_flat1) + INS),
                           (w.flange_flat0, g.U0 + INS), (g.X0, g.U0 + INS)]
    web = [(xw + xp, cr + yy) for (xp, yy) in outline]
    parts = [extrude(web, zc - w.web_t / 2, zc + w.web_t / 2)]
    fl_pts = [(g.X0, g.U0), (w.flange_flat0, g.U0), (w.flange_flat1, g.u(w.flange_flat1)), (w.length, g.u(w.length))]
    fl = [(xw + xp, cr + yy) for (xp, yy) in fl_pts] + [(xw + xp, cr + yy + w.fl_t) for (xp, yy) in reversed(fl_pts)]
    hf = w.fl_w / 2.0
    parts.append(extrude(fl, zc - hf, zc + hf))
    bf = [(xw + xp, cr + yy - 0.007) for (xp, yy) in bot] + [(xw + xp, cr + yy + INS) for (xp, yy) in reversed(bot)]
    parts.append(extrude(bf, zc - hf, zc + hf))
    return paint(trimesh.util.concatenate(parts), COL_STEEL)


def build_wg_strut(b: Builder, zc):
    """스트럿 I형: 웹 + 플랜지 2, 상부 작업점(knee) → 하부 작업점(strut_lower)."""
    w = b.s.wg
    xw = b.s.box.x_web
    yd = b.y_deck_top(zc)
    A = np.array([xw + w.strut_lower[0], yd - w.strut_lower[1]])
    B = np.array([xw + w.knee[0], yd - w.knee[1]])
    ax = B - A
    a = ax / float(np.linalg.norm(ax))
    n = np.array([-a[1], a[0]])
    A0, B0 = A - a * 0.08, B + a * 0.05
    half = w.strut_size / 2.0
    web = [tuple(A0 - n * half), tuple(B0 - n * half), tuple(B0 + n * half), tuple(A0 + n * half)]
    parts = [extrude(web, zc - 0.006, zc + 0.006)]
    for s_ in (+1, -1):
        f = [tuple(A0 + n * (s_ * half)), tuple(B0 + n * (s_ * half)),
             tuple(B0 + n * (s_ * (half + w.fl_t))), tuple(A0 + n * (s_ * (half + w.fl_t)))]
        if s_ < 0:
            f = list(reversed(f))
        parts.append(extrude(f, zc - w.fl_w / 2, zc + w.fl_w / 2))
    return paint(trimesh.util.concatenate(parts), COL_STEEL)


def build_wg_bracket(b: Builder, zc):
    """정착대 [A11]: 웹면 돌출 블록."""
    d, y0, y1 = b.s.wg.bracket
    xw = b.s.box.x_web
    yd = b.y_deck_top(zc)
    return paint(box_prism(xw - INS, xw + d, yd - y1, yd - y0, zc - 0.150, zc + 0.150), COL_STEEL)


# ── §7 외측빔 CS 26세그 ×2 ────────────────────────────────────────────────────────
def build_cs_seg(b: Builder, g: WGGeom, zc, side):
    """CS 세그: I형, WG 중심 ±seg/2, 받침선 절단 [A14]. 상면 = WG 선단 상면 [A13]."""
    c, w = b.s.cs, b.s.wg
    x_cs = b.s.box.x_web + w.length
    top_rel = g.u(w.length) + w.fl_t
    z0, z1 = max(b.Z_P4, zc - c.seg / 2), min(b.Z_P5, zc + c.seg / 2)
    hw, hf = c.web_t / 2, c.fl_w / 2

    def polys(z):
        top = b.y_crown(z) + top_rel
        return [rect(x_cs - hf, x_cs + hf, top - c.fl_t, top),
                rect(x_cs - hw, x_cs + hw, top - (c.depth - c.fl_t) - INS, top - c.fl_t + INS),
                rect(x_cs - hf, x_cs + hf, top - c.depth, top - (c.depth - c.fl_t))]
    parts = []
    for i in range(3):
        st = [(z, mirror_poly(polys(z)[i]) if side < 0 else polys(z)[i]) for z in (z0, z1)]
        parts.append(loft(st))
    return paint(trimesh.util.concatenate(parts), COL_STEEL)


# ── §8 슬래브 + 방호벽 3조 ────────────────────────────────────────────────────────
def slab_poly(b: Builder, z):
    s = b.s.slab
    c = b.y_crown(z)
    hw, bw = s.half_width, s.barrier[0]
    box_sof = -b.s.coord.t_slab_crown - INS
    cant = s.cant_drop                                   # [(x, drop)] crown 상대
    bot = [(-x, -d) for (x, d) in reversed(cant)] + [(-cant[0][0], box_sof), (cant[0][0], box_sof)] + [(x, -d) for (x, d) in cant]
    edge = -s.slope * (hw - bw)
    top = [(hw, edge), (hw - bw, edge), (0.0, 0.0), (-(hw - bw), edge), (-hw, edge)]
    return [(x, c + y) for (x, y) in bot + top]


def build_slab(b: Builder):
    return paint(loft([(b.Z_P4, slab_poly(b, b.Z_P4)), (b.Z_P5, slab_poly(b, b.Z_P5))]), COL_CONC)


def barrier_poly(b: Builder, z, x0, x1):
    s = b.s.slab
    c = b.y_crown(z)
    hw, bw, bh, ch = s.half_width, s.barrier[0], s.barrier[1], s.barrier[2]

    def top_surf(x):
        return c - s.slope * min(abs(x), hw - bw)
    y_base = min(top_surf(x0), top_surf(x1)) - INS
    y_top = max(top_surf(x0), top_surf(x1)) + bh
    return [(x0, y_base), (x1, y_base), (x1, y_top - ch), (x1 - ch, y_top), (x0 + ch, y_top), (x0, y_top - ch)]


def build_barrier(b: Builder, x0, x1):
    return paint(loft([(b.Z_P4, barrier_poly(b, b.Z_P4, x0, x1)), (b.Z_P5, barrier_poly(b, b.Z_P5, x0, x1))]), COL_CONC)


def barrier_spans(b: Builder) -> dict[str, tuple[float, float]]:
    """연단 좌·우 + 보도측 중앙방호벽 [Q3] — 보도 폭·중앙방호벽 폭에서 유도."""
    s = b.s.slab
    hw, bw = s.half_width, s.barrier[0]
    sg = b.s.coord.walk_side_sign
    inner = sg * (hw - bw - s.walk_width)
    ctr = tuple(sorted((inner, inner - sg * s.center_barrier)))
    return {"L": (-hw, -hw + bw), "R": (hw - bw, hw), "CTR": ctr}


# ── §9 SP04 이음 외면판 4매 [A17] ─────────────────────────────────────────────────
def build_sp04(b: Builder) -> dict[str, trimesh.Trimesh]:
    sp = b.s.sp04
    z_sp = b.Z_P4 + b.s.box.z_sp04_offset
    out = {}
    L, W, T = sp.tf
    out["TF"] = loft([(z, rect(-L / 2, L / 2, b.y_deck_top(z) - INS, b.y_deck_top(z) + T)) for z in (z_sp - W / 2, z_sp + W / 2)])
    L, W, T = sp.bf
    hf = b.s.box.half_flange
    out["BF"] = loft([(z, rect(-hf, hf, b.y_bot_out(z) - T, b.y_bot_out(z) + INS)) for z in (z_sp - W / 2, z_sp + W / 2)])
    L, W, T = sp.web
    xw = b.s.box.x_web
    for sfx, side in (("WEB_R", +1), ("WEB_L", -1)):
        st = []
        for z in (z_sp - W / 2, z_sp + W / 2):
            yc = (b.y_web_top(z) + b.y_web_bot(z)) / 2.0
            p = rect(xw - INS, xw + T, yc - L / 2, yc + L / 2)
            st.append((z, mirror_poly(p) if side < 0 else p))
        out[sfx] = loft(st)
    for m in out.values():
        paint(m, COL_STEEL)
    return out


# ── §10 받침 4기 (P4·P5 × 좌우) [A18][A19] ─────────────────────────────────────────
def bearing_parts(b: Builder, zp, xb) -> dict[str, trimesh.Trimesh]:
    br = b.s.bearing
    sole_w, _t0, _t1, t_mid = br.sole
    hs = sole_w / 2.0
    soffit = b.y_deck_top(zp) - b.t_top(zp) - b.s.box.h_pier - b.t_bot(zp)
    out = {}
    st = []
    for z in (zp - hs, zp + hs):
        y_top = soffit + b.s.coord.grade * (z - zp) + 0.003
        st.append((z, rect(xb - hs, xb + hs, soffit - t_mid, y_top)))
    out["SOLE"] = paint(loft(st), COL_SOLE)
    y1 = soffit - t_mid                                   # 본체 상면
    y0 = soffit - br.body_h                               # 본체 하면 (EL 검증 기준면) [A18]
    hb = br.base / 2.0
    body = [box_prism(xb - hb, xb + hb, y1 - 0.050, y1, zp - hb, zp + hb),
            box_prism(xb - hb, xb + hb, y0, y0 + 0.050, zp - hb, zp + hb)]
    cyl = trimesh.creation.cylinder(radius=br.body_d / 2.0, height=(y1 - 0.050) - (y0 + 0.050) + 0.006, sections=48)
    cyl.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2.0, [1, 0, 0]))
    cyl.apply_translation([xb, (y0 + y1) / 2.0, zp])
    body.append(cyl)
    out["BODY"] = paint(trimesh.util.concatenate(body), COL_BRG)
    mt, mw = br.mortar
    hm = mw / 2.0
    out["MORTAR"] = paint(box_prism(xb - hm, xb + hm, y0 - mt, y0 + 0.003, zp - hm, zp + hm), COL_CONC)
    bw, bt = br.block
    hbk = bw / 2.0
    out["BLOCK"] = paint(box_prism(xb - hbk, xb + hbk, y0 - mt - bt, y0 - mt + 0.003, zp - hbk, zp + hbk), COL_CONC)
    return out


# ── 조립 ──────────────────────────────────────────────────────────────────────────
def add_all(b: Builder, add) -> None:
    s = b.s
    n_cell = s.diaphragm.n_cell
    # §3 프레임 25 × 부재 6
    for k in range(n_cell):
        for sfx, m in build_frame_parts(b, k).items():
            add("AB1_S5_FRM%02d_%s" % (k + 1, sfx), m)
    # §4 종리브 존
    for (sfx, kind, x, z0, z1, t, h) in rib_layout(b):
        add("AB1_S5_RIB_%s" % sfx, build_rib_top(b, x, z0, z1, t, h) if kind == "T" else build_rib_bot(b, x, z0, z1, t, h))
    # §5 수평보강재 3레벨
    add("AB1_S5_HST_UP_R", build_hst_upper(b, +1))
    add("AB1_S5_HST_UP_L", build_hst_upper(b, -1))
    for pier in (4, 5):
        for row, f in (("LO1", s.hstiff.lower_factors[0]), ("LO2", s.hstiff.lower_factors[1])):
            add("AB1_S5_HST_P%d_%s_R" % (pier, row), build_hst_lower(b, +1, pier, f))
            add("AB1_S5_HST_P%d_%s_L" % (pier, row), build_hst_lower(b, -1, pier, f))
    # §6 WG 26쌍 (WG096~121) — 격벽선과 동일 전역 체인 / §7 CS 26세그 ×2
    g = WGGeom(b)
    for k in range(n_cell + 1):
        zc = b.dia_z(k)
        num = s.wg.first_no + k
        main_r, strut_r, brk_r = build_wg_main(b, g, zc), build_wg_strut(b, zc), build_wg_bracket(b, zc)
        add("AB1_S5_WG%03dR" % num, main_r)
        add("AB1_S5_WG%03dR_ST" % num, strut_r)
        add("AB1_S5_WG%03dR_BR" % num, brk_r)
        add("AB1_S5_WG%03dL" % num, paint(mirror_mesh(main_r), COL_STEEL))
        add("AB1_S5_WG%03dL_ST" % num, paint(mirror_mesh(strut_r), COL_STEEL))
        add("AB1_S5_WG%03dL_BR" % num, paint(mirror_mesh(brk_r), COL_STEEL))
        add("AB1_S5_CS%03dR" % num, build_cs_seg(b, g, zc, +1))
        add("AB1_S5_CS%03dL" % num, build_cs_seg(b, g, zc, -1))
    # §8 슬래브 + 방호벽 3조
    add("AB1_S5_SLAB", build_slab(b))
    for sfx, (x0, x1) in barrier_spans(b).items():
        add("AB1_S5_BARRIER_%s" % sfx, build_barrier(b, x0, x1))
    # §9 SP04 외면 이음판 4매
    for sfx, m in build_sp04(b).items():
        add("AB1_S5_SP04_%s" % sfx, m)
    # §10 받침 4기 × 부품 4
    for pier, zp in (("P4", b.Z_P4), ("P5", b.Z_P5)):
        for i, xb in ((1, -s.bearing.x), (2, s.bearing.x)):
            for sfx, m in bearing_parts(b, zp, xb).items():
                add("AB1_S5_BRG_%s_%d_%s" % (pier, i, sfx), m)
