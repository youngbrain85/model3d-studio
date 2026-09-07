"""독립 재실측 (지식베이스 §6-2, M3 설계 D5) — GLB 재로드 실측 vs ModelSpec 자체 유도 기대값.

검증관 역할: 빌더(builder.py·builder_full.py)를 import 하지 않는다 — 자기참조 검증 방지.
기대값은 modelspec.json(ModelSpec)에서 본 모듈이 독립적으로 유도한다(내공 H 는 도면 계수 a_dwg
그대로, 소핏은 상판두께+내공+하판두께, 받침 하면은 EL 검증치 …). 참조 measure_ab1_p4p5_v2.py
의 항목·구조를 그대로 잇는다(항목명 동일 → compare-model 이 이름으로 대조).
- 월드 전개: scene graph 노드 순회(KB §2-16 — geometry 직접 순회 금지)
- 허용오차: 길이 5mm / 개수 0 / 각도 0.5°
- 슬라이스 실측: mesh.section (z-법선 = 횡단면, y-법선 = 격벽 개구 수평 절단)
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import trimesh

from m3d.model.spec import ModelSpec

TOL = 0.005
TOL_MM = 5.0
TOL_ANG = 0.5


def _fmt(v: float) -> str:
    """항목명용 숫자 표기 — 정수는 천단위 콤마, 소수는 %g."""
    return "{:,}".format(int(round(v))) if abs(v - round(v)) < 1e-9 else "%g" % v


# ══ 기대값 유도 (ModelSpec → 자체 계산, 빌더 무관) ═══════════════════════════════
class Expect:
    def __init__(self, s: ModelSpec):
        self.s = s
        c, b = s.coord, s.box
        self.Z_P4, self.Z_P5 = c.z_p4, c.z_p5
        self.SPAN = c.z_p5 - c.z_p4
        self.EL_P4, self.EL_P5 = self.el(c.z_p4), self.el(c.z_p5)
        self.TOP_P4, self.TOP_P5 = self.top_y(c.z_p4), self.top_y(c.z_p5)
        self.T_TOP0 = self.t_of(b.top_t, 0.0)
        self.T_BOT0 = self.t_of(b.bot_t, 0.0)
        self.SOFFIT_P4 = self.TOP_P4 - (b.h_pier + self.T_TOP0 + self.T_BOT0)
        self.BRG_BOT = {p: el - c.y_datum for p, el in s.bearing.el_check.items()}
        self.Y_MIN_ALL = min(self.BRG_BOT.values()) - s.bearing.mortar[0] - s.bearing.block[1]
        pave = c.deck_drop - c.t_slab_crown                     # 포장 두께(계획고 − crown)
        self.CROWN_P4 = self.EL_P4 - pave - c.y_datum
        self.CROWN_P5 = self.EL_P5 - pave - c.y_datum
        sl = s.slab
        self.BARRIER_LR_TOP = max(self.CROWN_P4, self.CROWN_P5) - sl.slope * (sl.half_width - sl.barrier[0]) + sl.barrier[1]
        self.Z_SUP = [c.z_p4 - s.wg.fl_w / 2, c.z_p5 + s.wg.fl_w / 2]
        self.Z_ALL = [c.z_p4 - s.bearing.sole[0] / 2, c.z_p5 + s.bearing.sole[0] / 2]
        d = s.diaphragm
        n = d.n_cell
        self.N_DIA = n + 1
        self.DIA_Z = [c.z_p4 + d.support_t / 2] + [c.z_p4 + d.spacing * k for k in range(1, n)] + [c.z_p5 - d.support_t / 2]
        htab = {round(dd, 3): h for dd, h in d.h_table}
        self.DIA_H = []
        for k in range(n + 1):
            kk = min(k, n - k)
            self.DIA_H.append(b.h_pier * 1000.0 if kk == 0 else htab.get(round(kk * d.spacing, 3), b.h_mid) * 1000.0)
        self.DIA_OPEN = [(d.support_open[0] if k in (0, n) else d.interior_open[0]) * 1000.0 for k in range(n + 1)]
        self.DIA_Y0 = {"support": d.support_sill + d.support_open[1] / 2, "interior": d.sill_cl + d.interior_open[1] / 2}
        self.N_FRM = n
        self.FRM_Z = [c.z_p4 + s.frame.offset + d.spacing * k for k in range(n)]
        r = s.rib
        self.X3 = self.cols(r.top_pier.cols, r.top_pier.pitch)
        self.X8 = self.cols(r.top_mid.cols, r.top_mid.pitch)
        self.Z_RIB_PIER = c.z_p4 + min(5.0, min(r.top_switch[0], r.bot_switch[0]) / 2)   # 지점존 대표점
        self.Z_RIB_MID = (c.z_p4 + c.z_p5) / 2
        self.N_WG = 2 * (n + 1)
        self.WG_TIP = b.x_web + s.wg.length
        self.WG_NO = s.wg.first_no + 1                            # 실측 대표: 두 번째 WG(P4+spacing)
        self.STRUT_ANG = s.wg.strut_angle_deg
        self.N_BRG = 4
        self.SOLE_MM = s.bearing.sole[0] * 1000.0
        self.N_RIB = self.rib_strip_count()
        self.N_HST = 2 + len(s.hstiff.lower_factors) * 2 * 2
        w = s.wg
        self.Z_JOINT = c.z_p4 + b.z_sp04_offset                       # §9 현장이음선
        self.HST_UP_Z = [c.z_p4 + s.hstiff.upper_span, c.z_p5 - s.hstiff.upper_span]
        self.BRACKET_X = [b.x_web, b.x_web + w.bracket[0]]            # §6 정착대 x 범위(+측)
        self.BRACKET_Y_REL = [-w.bracket[2], -w.bracket[1]]           # y_deck_top 기준 아래 깊이
        self.STRUT_LO_REL = (b.x_web + w.strut_lower[0], -w.strut_lower[1])
        self.STRUT_HI_REL = (b.x_web + w.knee[0], -w.knee[1])
        self.CS_XC = b.x_web + w.length                               # §7 세그 x 중심
        _hw, _bw = sl.half_width, sl.barrier[0]
        _inner = c.walk_side_sign * (_hw - _bw - sl.walk_width)
        self.BARRIER_X = {"L": [-_hw, -_hw + _bw], "R": [_hw - _bw, _hw],
                          "CTR": sorted((_inner, _inner - c.walk_side_sign * sl.center_barrier))}
        self.N_MESH = (4 + 4 + self.N_DIA + 6 * self.N_FRM + self.N_RIB + self.N_WG * 3
                       + self.N_WG + self.N_HST + 1 + 3 + self.N_BRG * 4)

    # ── 프로파일 ────────────────────────────────────────────────────────────────
    def el(self, z):
        c = self.s.coord
        return c.el0 + c.grade * (z - c.z_sta3400)

    def top_y(self, z):
        c = self.s.coord
        return self.el(z) - c.deck_drop - c.y_datum

    @staticmethod
    def t_of(zone, d):
        for (d0, d1, t) in zone:
            if d0 - 1e-9 <= d <= d1 + 1e-9:
                return t
        raise ValueError("존 밖 d: %r" % d)

    def h_mm(self, d):
        """§1 내공 H(d) — 도면 계수 a_dwg 그대로(빌더의 정규화 계수와 독립)."""
        b = self.s.box
        if d <= b.l_flat:
            return b.h_pier * 1000.0
        if d >= b.l_flat + b.l_para:
            return b.h_mid * 1000.0
        return (b.h_mid + b.a_dwg * (b.l_flat + b.l_para - d) ** 2) * 1000.0

    def h_at_z(self, z):
        return self.h_mm(min(z - self.Z_P4, self.Z_P5 - z))

    @staticmethod
    def cols(n, pitch):
        return [round((i - (n - 1) / 2.0) * pitch, 6) for i in range(n)]

    def deck_top(self, z):
        """강상판 상면 y — 정착대·스트럿·이음판 기준면."""
        return self.top_y(z)

    def bot_out(self, z):
        """하판 하면 y = 강상판 상면 − 상판두께 − 내공 − 하판두께."""
        return (self.top_y(z) - self.t_of(self.s.box.top_t, z - self.Z_P4)
                - self.h_at_z(z) / 1000.0 - self.t_of(self.s.box.bot_t, z - self.Z_P4))

    def web_bot(self, z):
        """하판 상면 y."""
        return self.top_y(z) - self.t_of(self.s.box.top_t, z - self.Z_P4) - self.h_at_z(z) / 1000.0

    def web_top(self, z):
        """강상판 하면 y."""
        return self.top_y(z) - self.t_of(self.s.box.top_t, z - self.Z_P4)

    def h_stations(self):
        b = self.s.box
        lp = b.l_flat + b.l_para
        z4, z5 = self.Z_P4, self.Z_P5
        return [("P4 받침선", z4 + 0.001), ("P4+%g 등고경계" % b.l_flat, z4 + b.l_flat),
                ("P4+%g 포물선중간" % (b.l_flat + b.l_para / 2), z4 + b.l_flat + b.l_para / 2),
                ("P4+%g 포물선종점" % lp, z4 + lp), ("중앙 s=%g" % (self.SPAN / 2), z4 + self.SPAN / 2),
                ("P5−%g" % lp, z5 - lp), ("P5−%g" % b.l_flat, z5 - b.l_flat), ("P5 받침선", z5 - 0.001)]

    def rib_strip_count(self):
        """§4 존 모델 스트립 수 — 지점존 2 + 전이존 2 + 중앙존, SP04 가 놓인 존은 분절."""
        r, b = self.s.rib, self.s.box
        z_sp = b.z_sp04_offset
        n = 0
        for pier, mid, sw in ((r.top_pier, r.top_mid, r.top_switch), (r.bot_pier, r.bot_mid, r.bot_switch)):
            pier_split = 1 if z_sp < sw[0] else 0                     # P4측 지점존 분절
            mid_split = 1 if sw[1] < z_sp < self.SPAN - sw[1] else 0  # 중앙존 분절
            n += pier.cols * (2 + pier_split) + (pier.cols + mid.cols) * 2 + mid.cols * (1 + mid_split)
        return n


# ══ 월드 전개·슬라이스 유틸 ═══════════════════════════════════════════════════════
def world_meshes(sc: trimesh.Scene) -> dict[str, trimesh.Trimesh]:
    out = {}
    for node in sc.graph.nodes_geometry:
        T, gname = sc.graph[node]
        m = sc.geometry[gname].copy()
        m.apply_transform(T)
        out[str(gname)] = m
    return out


def sect_z(mesh, z0):
    try:
        s = mesh.section(plane_origin=[0.0, 0.0, z0], plane_normal=[0.0, 0.0, 1.0])
    except Exception:
        return None
    return None if s is None else np.asarray(s.vertices)


def sect_y(mesh, y0):
    try:
        return mesh.section(plane_origin=[0.0, y0, 0.0], plane_normal=[0.0, 1.0, 0.0])
    except Exception:
        return None


def x_gap_at(path3d):
    """수평 슬라이스 경로의 x-구간 합집합에서 x=0 을 포함하는 갭 폭[mm] (개구 폭 실측)."""
    V = np.asarray(path3d.vertices)
    ivs = []
    for ent in path3d.entities:
        pts = ent.points
        for a, b in zip(pts[:-1], pts[1:]):
            x1, x2 = V[a][0], V[b][0]
            ivs.append((min(x1, x2), max(x1, x2)))
    ivs.sort()
    merged: list[tuple[float, float]] = []
    for lo, hi in ivs:
        if merged and lo <= merged[-1][1] + 1e-6:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    left = max((hi for lo, hi in merged if hi <= 0), default=None)
    right = min((lo for lo, hi in merged if lo >= 0), default=None)
    if left is None or right is None:
        return None
    return (right - left) * 1000.0


# ══ 대조 누산기 ═══════════════════════════════════════════════════════════════════
class Checks:
    def __init__(self):
        self.rows: list[dict] = []
        self.group: str | None = None          # run() 이 섹션마다 설정 (M8 D1)

    def _row(self, row: dict, group: str | None) -> dict:
        row["섹션"] = group or self.group or "ASSEMBLY"
        self.rows.append(row)
        return row

    def add(self, name, exp, meas, tol, unit="", group=None):
        e = np.atleast_1d(np.asarray(exp, dtype=float))
        m = np.atleast_1d(np.asarray(meas, dtype=float))
        if len(e) != len(m):
            ok, dev = False, None
        else:
            dev = float(np.max(np.abs(e - m))) if len(e) else 0.0
            ok = bool(np.isfinite(dev)) and dev <= tol + 1e-9

        def val(a):
            return [round(float(v), 4) for v in a] if len(a) != 1 else round(float(a[0]), 4)
        self._row({"항목": name, "단위": unit, "기대": val(e), "실측": val(m),
                   "허용오차": tol, "최대편차": None if dev is None or not np.isfinite(dev) else round(dev, 4),
                   "판정": "PASS" if ok else "FAIL"}, group)
        return ok

    def add_info(self, name, meas, note, unit="", group=None):
        self._row({"항목": name, "단위": unit, "기대": "사양 미기재(" + note + ")",
                   "실측": meas, "허용오차": None, "최대편차": None, "판정": "INFO"}, group)

    def add_missing(self, name, detail, group=None):
        self._row({"항목": name, "단위": "", "기대": "노드 존재", "실측": detail,
                   "허용오차": None, "최대편차": None, "판정": "FAIL"}, group)

    def summary(self):
        n_pass = sum(1 for c in self.rows if c["판정"] == "PASS")
        n_fail = sum(1 for c in self.rows if c["판정"] == "FAIL")
        n_info = sum(1 for c in self.rows if c["판정"] == "INFO")
        return {"검증항목": len(self.rows), "PASS": n_pass, "FAIL": n_fail, "INFO": n_info}

    def by_section(self) -> dict[str, dict]:
        """섹션 코드 → 판정 집계 (M8 D1)."""
        agg: dict[str, dict] = {}
        for c in self.rows:
            g = agg.setdefault(c["섹션"], {"PASS": 0, "FAIL": 0, "INFO": 0})
            g[c["판정"]] += 1
        return agg


# ══ 실측 섹션 (각각 독립 — 노드 누락은 FAIL 1건으로 기록) ═════════════════════════
def sec_bbox(W, E: Expect, ck: Checks, out: dict):
    names = sorted(W)

    def group_bounds(keys):
        lo = np.min([W[n].bounds[0] for n in keys], axis=0)
        hi = np.max([W[n].bounds[1] for n in keys], axis=0)
        return lo, hi
    lo_a, hi_a = group_bounds(names)
    sup = [n for n in names if "_BRG_" not in n]
    lo_s, hi_s = group_bounds(sup)
    hw = E.s.slab.half_width
    ck.add("bbox 전체 x [최소,최대] (§8 폭원 %g)" % (2 * hw), [-hw, hw], [lo_a[0], hi_a[0]], TOL, "m")
    ck.add("bbox 전체 y 최소 (§10 블록 하면 = 받침하면−%s−%s)" % (_fmt(E.s.bearing.mortar[0] * 1000), _fmt(E.s.bearing.block[1] * 1000)),
           E.Y_MIN_ALL, lo_a[1], TOL, "m")
    ck.add("bbox 전체 z [최소,최대] (§10 받침선±솔플레이트 %s)" % _fmt(E.s.bearing.sole[0] * 500), E.Z_ALL, [lo_a[2], hi_a[2]], TOL, "m")
    ck.add("bbox 상부 x [최소,최대]", [-hw, hw], [lo_s[0], hi_s[0]], TOL, "m")
    ck.add("bbox 상부 y 최소 (§0·§1 P4 소핏 = 강상판상면−%s)" % _fmt((E.s.box.h_pier + E.T_TOP0 + E.T_BOT0) * 1000),
           E.SOFFIT_P4, lo_s[1], TOL, "m")
    ck.add("bbox 상부 z [최소,최대] (§6 받침선±WG 플랜지 %s)" % _fmt(E.s.wg.fl_w * 500), E.Z_SUP, [lo_s[2], hi_s[2]], TOL, "m")
    bar_tops = {b: float(W["AB1_S5_BARRIER_" + b].bounds[1][1]) for b in ("L", "R", "CTR")}
    ck.add("bbox 전체 y 최대 = 방호벽 최고점 (내부일관)", max(bar_tops.values()), hi_a[1], 0.001, "m")
    out["bbox"] = {
        "전체": {"x": [round(float(lo_a[0]), 4), round(float(hi_a[0]), 4)],
                 "y": [round(float(lo_a[1]), 4), round(float(hi_a[1]), 4)],
                 "z": [round(float(lo_a[2]), 4), round(float(hi_a[2]), 4)]},
        "상부구조": {"x": [round(float(lo_s[0]), 4), round(float(hi_s[0]), 4)],
                     "y": [round(float(lo_s[1]), 4), round(float(hi_s[1]), 4)],
                     "z": [round(float(lo_s[2]), 4), round(float(hi_s[2]), 4)]}}
    out["_bar_tops"] = bar_tops


def sec_h_profile(W, E: Expect, ck: Checks, out: dict):
    TOPM, BOTM = W["AB1_S5_BOX_TOP"], W["AB1_S5_BOX_BOT"]
    rows = []
    for label, z0 in E.h_stations():
        vt, vb = sect_z(TOPM, z0), sect_z(BOTM, z0)
        h = (float(vt[:, 1].min()) - float(vb[:, 1].max())) * 1000.0 if vt is not None and vb is not None else float("nan")
        h_exp = E.h_at_z(z0)
        ok = ck.add("내공 H " + label + " (§1 H식)", h_exp, h, TOL_MM, "mm")
        rows.append({"위치": label, "z": round(z0, 3), "기대_mm": round(h_exp, 1),
                     "실측_mm": round(h, 1), "판정": "PASS" if ok else "FAIL"})
    out["내공_H_프로파일"] = rows


def sec_deck_top(W, E: Expect, ck: Checks, out: dict):
    TOPM = W["AB1_S5_BOX_TOP"]
    for label, z0 in (("P4", E.Z_P4 + 0.001), ("P5", E.Z_P5 - 0.001)):
        vt = sect_z(TOPM, z0)
        ck.add("강상판 상면 y @" + label + " (§0 계획고−%g)" % E.s.coord.deck_drop, E.top_y(z0),
               float(vt[:, 1].max()) if vt is not None else float("nan"), TOL, "m")


def sec_diaphragms(W, E: Expect, ck: Checks, out: dict):
    """판 z 위치는 수평슬라이스 |x|>2.0(순수 판 구간) z중앙, 판높이는 내공 클램프 유효높이 (참조 measure 주의사항 계승)."""
    TOPM, BOTM = W["AB1_S5_BOX_TOP"], W["AB1_S5_BOX_BOT"]
    n = E.N_DIA
    dia_names = ["AB1_S5_DIA%02d" % (k + 1) for k in range(n)]
    present = [nm for nm in dia_names if nm in W]
    dia_z, dia_h, dia_open, rows, embeds = [], [], [], [], []
    for k, nm in enumerate(dia_names):
        if nm not in W:
            continue
        b = W[nm].bounds
        y0 = float(b[0][1]) + (E.DIA_Y0["support"] if k in (0, n - 1) else E.DIA_Y0["interior"])
        s = sect_y(W[nm], y0)
        sv = np.asarray(s.vertices)
        plate = sv[np.abs(sv[:, 0]) > 2.0]
        if len(plate) == 0:                                    # 폭 ≤ 4.0m 인 임의 판(에이전트 산출물) — 전체 정점으로 대체
            plate = sv
        zc = float((plate[:, 2].min() + plate[:, 2].max()) / 2)
        gap = x_gap_at(s)
        zs_ = min(max(zc, E.Z_P4 + 0.001), E.Z_P5 - 0.001)   # 받침선 위 판(에이전트 산출물)도 본체 슬라이스가 잡히게 안쪽으로
        vt, vb = sect_z(TOPM, zs_), sect_z(BOTM, zs_)
        top_in, bot_in = float(vt[:, 1].min()), float(vb[:, 1].max())
        h_eff = (min(float(b[1][1]), top_in) - max(float(b[0][1]), bot_in)) * 1000.0
        h_phys = float(b[1][1] - b[0][1]) * 1000.0
        embeds.append([round((float(b[1][1]) - top_in) * 1000.0, 2), round((bot_in - float(b[0][1])) * 1000.0, 2)])
        dia_z.append(zc); dia_h.append(h_eff); dia_open.append(gap if gap is not None else -1.0)
        rows.append({"격벽": nm[-5:], "z실측": round(zc, 4), "z기대": round(E.DIA_Z[k], 4),
                     "유효높이실측_mm": round(h_eff, 1), "판높이기대_mm": E.DIA_H[k],
                     "물리판높이_mm": round(h_phys, 1), "물림_상하_mm": embeds[-1],
                     "개구폭실측_mm": None if gap is None else round(gap, 1), "개구폭기대_mm": E.DIA_OPEN[k]})
    d = E.s.diaphragm
    ck.add("격벽 수 (§2 %d면)" % n, n, len(present), 0, "개")
    ck.add("격벽 판 z 위치 %d (§2 %s 그리드·지점판 내측 플러시)" % (n, _fmt(d.spacing * 1000)), E.DIA_Z, dia_z, TOL, "m")
    ck.add("격벽 유효높이(내공 충전) %d (§2 지점 %s / H표)" % (n, _fmt(E.s.box.h_pier * 1000)), E.DIA_H, dia_h, TOL_MM, "mm")
    ck.add("격벽 개구 폭 %d (§2 지점 %s / 일반 %s)" % (n, _fmt(d.support_open[0] * 1000), _fmt(d.interior_open[0] * 1000)),
           E.DIA_OPEN, dia_open, TOL_MM, "mm")
    if embeds:
        emb = np.asarray(embeds)
        ck.add_info("격벽 판 상·하 물림(플레이트 내 매입)",
                    {"상_mm": [float(emb[:, 0].min()), float(emb[:, 0].max())],
                     "하_mm": [float(emb[:, 1].min()), float(emb[:, 1].max())]},
                    "전 %d면 상·하 각 ~5mm 매입 — 내공·개구·외형 무영향, 모델링 기법" % n, "mm")
    out["격벽_상세"] = rows


def sec_frames(W, E: Expect, ck: Checks, out: dict):
    names = sorted(W)
    frm = [nm for nm in names if "_FRM" in nm]
    frm_ids = sorted({re.search(r"FRM(\d+)", nm).group(1) for nm in frm})
    roles: dict[str, list[str]] = {}
    for nm in frm:
        roles.setdefault(re.search(r"FRM\d+_(\w+)$", nm).group(1), []).append(nm)
    frm_z = []
    for fid in frm_ids:
        b = W["AB1_S5_FRM%s_TRW" % fid].bounds
        frm_z.append(float((b[0][2] + b[1][2]) / 2))
    n = E.N_FRM
    ck.add("프레임 수 (§3 %d개)" % n, n, len(frm_ids), 0, "개")
    ck.add("프레임 z 그리드 (§3 격벽 사이 %s)" % _fmt(E.s.frame.offset * 1000), E.FRM_Z, sorted(frm_z), TOL, "m")
    ck.add("프레임 부재 총수 (§3 6부재×%d=%d)" % (n, 6 * n), 6 * n, len(frm), 0, "개")
    ck.add("프레임 역할별 부재 수 6종 각 %d (TRW·TRF·BRW·BRF·VSL·VSR)" % n,
           [n] * 6, [len(roles.get(r, [])) for r in ("TRW", "TRF", "BRW", "BRF", "VSL", "VSR")], 0, "개")

    fid = frm_ids[0]
    trf = W["AB1_S5_FRM%s_TRF" % fid]
    brw, brf = W["AB1_S5_FRM%s_BRW" % fid], W["AB1_S5_FRM%s_BRF" % fid]
    row = E.s.frame.rows[0]
    ck.add("프레임 상부 플랜지 z 폭 (§3 [A6] 상부 웹 높이 %s)" % _fmt(row.top_web[1] * 1000), row.top_web[1] * 1000.0,
           float(trf.bounds[1][2] - trf.bounds[0][2]) * 1000.0, TOL_MM, "mm")
    zc = float((brw.bounds[0][2] + brw.bounds[1][2]) / 2)
    ck.add("프레임 하부 웹 상단 y (§3 하판 상면 + %s)" % _fmt(row.bot_web[1] * 1000), E.web_bot(zc) + row.bot_web[1],
           float(brw.bounds[1][1]), 0.02, "m")
    ck.add("프레임 하부 플랜지 z 폭 (§3 [A6] 하부 웹 높이 %s)" % _fmt(row.bot_web[1] * 1000), row.bot_web[1] * 1000.0,
           float(brf.bounds[1][2] - brf.bounds[0][2]) * 1000.0, TOL_MM, "mm")
    vsl = W["AB1_S5_FRM%s_VSL" % fid]
    ck.add("프레임 수직보강재 y 길이 (§3 [A7] %s)" % _fmt(row.vstiff[2] * 1000), row.vstiff[2] * 1000.0,
           float(vsl.bounds[1][1] - vsl.bounds[0][1]) * 1000.0, TOL_MM, "mm")

def sec_ribs(W, E: Expect, ck: Checks, out: dict):
    TOPM, BOTM = W["AB1_S5_BOX_TOP"], W["AB1_S5_BOX_BOT"]
    ribs = [nm for nm in sorted(W) if "_RIB_" in nm]

    def rib_columns(z0):
        vt, vb = sect_z(TOPM, z0), sect_z(BOTM, z0)
        y_mid = (float(vt[:, 1].min()) + float(vb[:, 1].max())) / 2
        top_x, bot_x = [], []
        for nm in ribs:
            b = W[nm].bounds
            if not (b[0][2] - 1e-6 <= z0 <= b[1][2] + 1e-6):
                continue
            v = sect_z(W[nm], z0)
            if v is None:
                continue
            (top_x if float(v[:, 1].mean()) > y_mid else bot_x).append(float(v[:, 0].mean()))
        return sorted(top_x), sorted(bot_x)
    r = E.s.rib
    zp, zm = E.Z_RIB_PIER, E.Z_RIB_MID
    tp, bp = rib_columns(zp)
    tm, bm = rib_columns(zm)
    lp, lm = "z=−%g" % abs(zp), "z=−%g" % abs(zm)
    ck.add("종리브 %s 상판 열수 (§4 지점존 %d열)" % (lp, r.top_pier.cols), r.top_pier.cols, len(tp), 0, "열")
    ck.add("종리브 %s 상판 x 위치 (§4 @%s)" % (lp, _fmt(r.top_pier.pitch * 1000)), E.cols(r.top_pier.cols, r.top_pier.pitch), tp, TOL, "m")
    ck.add("종리브 %s 하판 열수 (§4 지점존 %d열)" % (lp, r.bot_pier.cols), r.bot_pier.cols, len(bp), 0, "열")
    ck.add("종리브 %s 하판 x 위치 (§4 @%s)" % (lp, _fmt(r.bot_pier.pitch * 1000)), E.cols(r.bot_pier.cols, r.bot_pier.pitch), bp, TOL, "m")
    ck.add("종리브 %s 상판 열수 (§4 중앙존 %d열)" % (lm, r.top_mid.cols), r.top_mid.cols, len(tm), 0, "열")
    ck.add("종리브 %s 상판 x 위치 (§4 @%s)" % (lm, _fmt(r.top_mid.pitch * 1000)), E.cols(r.top_mid.cols, r.top_mid.pitch), tm, TOL, "m")
    ck.add("종리브 %s 하판 열수 (§4 중앙존 %d열)" % (lm, r.bot_mid.cols), r.bot_mid.cols, len(bm), 0, "열")
    ck.add("종리브 %s 하판 x 위치 (§4 @%s)" % (lm, _fmt(r.bot_mid.pitch * 1000)), E.cols(r.bot_mid.cols, r.bot_mid.pitch), bm, TOL, "m")
    out["종리브_열"] = {lp.replace("−", "-") + "_상판_x": [round(v, 4) for v in tp], lp.replace("−", "-") + "_하판_x": [round(v, 4) for v in bp],
                        lm.replace("−", "-") + "_상판_x": [round(v, 4) for v in tm], lm.replace("−", "-") + "_하판_x": [round(v, 4) for v in bm]}

    for nm, zone, lbl in (("AB1_S5_RIB_TP4_1", r.top_pier, "지점존 상판"), ("AB1_S5_RIB_BP4A_1", r.bot_pier, "지점존 하판")):
        mr = W.get(nm)
        if mr is None:
            continue
        # z 로 긴 부재는 bbox 에 종단경사·변단면이 섞인다 — 한 단면에서 잰다
        z0 = float((mr.bounds[0][2] + mr.bounds[1][2]) / 2)
        v = sect_z(mr, z0)
        h_meas = float(v[:, 1].max() - v[:, 1].min()) * 1000.0 if v is not None else float("nan")
        ck.add("종리브 %s 높이 (§4 %s)" % (lbl, _fmt(zone.h * 1000)), zone.h * 1000.0, h_meas, 10.0, "mm")

def sec_wg_cs(W, E: Expect, ck: Checks, out: dict):
    names = sorted(W)
    wg_main = [nm for nm in names if re.fullmatch(r"AB1_S5_WG\d{3}[LR]", nm)]
    cs_all = [nm for nm in names if re.fullmatch(r"AB1_S5_CS\d{3}[LR]", nm)]
    n_pair = E.N_WG // 2
    ck.add("WG 본체 수 (§6 %d쌍=%d)" % (n_pair, E.N_WG), E.N_WG, len(wg_main), 0, "개")
    ck.add("CS 세그 수 (§7 %d×2=%d)" % (n_pair, E.N_WG), E.N_WG, len(cs_all), 0, "개", group="CS")
    tag = "WG%03dL" % E.WG_NO
    wg = W["AB1_S5_" + tag]
    tip = float(wg.bounds[0][0]) if abs(wg.bounds[0][0]) > abs(wg.bounds[1][0]) else float(wg.bounds[1][0])
    ck.add("%s 선단 x (§6 −(%s+%s)=−%s)" % (tag, _fmt(E.s.box.x_web * 1000), _fmt(E.s.wg.length * 1000), _fmt(E.WG_TIP * 1000)),
           -E.WG_TIP, tip, TOL, "m")
    ck.add("%s z 중심 (P4+%g)" % (tag, E.s.diaphragm.spacing), E.Z_P4 + E.s.diaphragm.spacing,
           float((wg.bounds[0][2] + wg.bounds[1][2]) / 2), TOL, "m")
    stv = np.asarray(W["AB1_S5_%s_ST" % tag].vertices)
    cov = np.cov((stv - stv.mean(axis=0)).T)
    evals, evecs = np.linalg.eigh(cov)
    axis = evecs[:, np.argmax(evals)]
    ang = float(np.degrees(np.arctan2(abs(axis[1]), abs(axis[0]))))
    ck.add("스트럿 축 각도 %s_ST (§6 %g°)" % (tag, E.STRUT_ANG), E.STRUT_ANG, ang, TOL_ANG, "도")

    brs = [nm for nm in names if nm.endswith("_BR")]
    ck.add("정착대 수 (§6 가로보마다 1)", E.N_WG, len(brs), 0, "개")
    br = W["AB1_S5_%s_BR" % tag]
    zc_br = float((br.bounds[0][2] + br.bounds[1][2]) / 2)
    yd = E.deck_top(zc_br)
    ck.add("정착대 y 범위 %s_BR (§6 강상판 상면 −%g…−%g)" % (tag, E.s.wg.bracket[2], E.s.wg.bracket[1]),
           [yd + E.BRACKET_Y_REL[0], yd + E.BRACKET_Y_REL[1]],
           [float(br.bounds[0][1]), float(br.bounds[1][1])], TOL, "m")
    ck.add("정착대 x 바깥 끝 %s_BR (§6 웹 외면 + %g)" % (tag, E.s.wg.bracket[0]), -E.BRACKET_X[1],
           float(br.bounds[0][0]), TOL, "m")
    st = W["AB1_S5_%s_ST" % tag]
    zc_st = float((st.bounds[0][2] + st.bounds[1][2]) / 2)
    yd_st = E.deck_top(zc_st)
    ck.add("스트럿 x 범위 %s_ST (§6 하단 작업점 웹+%g … 상단 작업점 웹+%g)" % (tag, E.s.wg.strut_lower[0], E.s.wg.knee[0]),
           [-E.STRUT_HI_REL[0], -E.STRUT_LO_REL[0]], [float(st.bounds[0][0]), float(st.bounds[1][0])], 0.15, "m")
    # 스트럿은 작업점 밖으로 조금 더 뻗고 단면 폭이 있어 bbox 가 커진다 — 중점으로 본다
    ck.add("스트럿 중심 (x, y) %s_ST (§6 두 작업점의 중점)" % tag,
           [-(E.STRUT_LO_REL[0] + E.STRUT_HI_REL[0]) / 2, yd_st + (E.STRUT_LO_REL[1] + E.STRUT_HI_REL[1]) / 2],
           [float((st.bounds[0][0] + st.bounds[1][0]) / 2), float((st.bounds[0][1] + st.bounds[1][1]) / 2)],
           0.03, "m")
    cs_tag = "AB1_S5_CS%03dL" % E.WG_NO
    cs = W[cs_tag]
    ck.add("%s z 중심 (§7 가로보 체인 중심)" % cs_tag, E.Z_P4 + E.s.diaphragm.spacing,
           float((cs.bounds[0][2] + cs.bounds[1][2]) / 2), TOL, "m", group="CS")
    ck.add("%s x 중심 (§7 가로보 선단 %g)" % (cs_tag, E.CS_XC), -E.CS_XC,
           float((cs.bounds[0][0] + cs.bounds[1][0]) / 2), TOL, "m", group="CS")
    z_cs = float((cs.bounds[0][2] + cs.bounds[1][2]) / 2)
    v_cs = sect_z(cs, z_cs)
    ck.add("%s 춤 (§7 %s)" % (cs_tag, _fmt(E.s.cs.depth * 1000)), E.s.cs.depth * 1000.0,
           float(v_cs[:, 1].max() - v_cs[:, 1].min()) * 1000.0 if v_cs is not None else float("nan"),
           10.0, "mm", group="CS")

def sec_bearings(W, E: Expect, ck: Checks, out: dict):
    names = sorted(W)
    ck.add("받침 기수 (§10 P4·P5 각 2기)", E.N_BRG, len({nm.rsplit("_", 1)[0] for nm in names if "_BRG_" in nm}), 0, "기")
    bot_meas, bot_exp, xc_meas, sole_dims = [], [], [], []
    for p, i in (("P4", 1), ("P4", 2), ("P5", 1), ("P5", 2)):
        body = W["AB1_S5_BRG_%s_%d_BODY" % (p, i)]
        sole = W["AB1_S5_BRG_%s_%d_SOLE" % (p, i)]
        bot_meas.append(float(body.bounds[0][1]))
        bot_exp.append(E.BRG_BOT[p])
        xc_meas.append(float((body.bounds[0][0] + body.bounds[1][0]) / 2))
        sb = sole.bounds
        sole_dims += [float(sb[1][0] - sb[0][0]) * 1000, float(sb[1][2] - sb[0][2]) * 1000]
    xb = E.s.bearing.x
    ck.add("받침 하면 y 4기 (§10 EL.'X'−%g: P4 %.3f / P5 %.3f)" % (E.s.coord.y_datum, E.BRG_BOT["P4"], E.BRG_BOT["P5"]),
           bot_exp, bot_meas, TOL, "m")
    ck.add("받침 x 중심 4기 (§10 횡간격 %s → ±%g)" % (_fmt(2 * xb * 1000), xb), [-xb, xb, -xb, xb], xc_meas, TOL, "m")
    ck.add("솔플레이트 평면 4기×(x,z) (§10 %s×%s)" % (_fmt(E.SOLE_MM), _fmt(E.SOLE_MM)), [E.SOLE_MM] * 8, sole_dims, TOL_MM, "mm")

    brs_ = E.s.bearing
    sole1 = W["AB1_S5_BRG_P4_1_SOLE"]
    mort = W["AB1_S5_BRG_P4_1_MORTAR"]
    blk = W["AB1_S5_BRG_P4_1_BLOCK"]
    ck.add("솔플레이트 두께 (§10 %s)" % _fmt(brs_.sole[3] * 1000), brs_.sole[3] * 1000.0,
           float(sole1.bounds[1][1] - sole1.bounds[0][1]) * 1000.0, 25.0, "mm")
    ck.add("무수축 모르타르 두께 (§10 %s)" % _fmt(brs_.mortar[0] * 1000), brs_.mortar[0] * 1000.0,
           float(mort.bounds[1][1] - mort.bounds[0][1]) * 1000.0, TOL_MM, "mm")
    ck.add("받침 블록 한 변 (§10 %s)" % _fmt(brs_.block[0] * 1000), [brs_.block[0] * 1000.0] * 2,
           [float(blk.bounds[1][0] - blk.bounds[0][0]) * 1000.0, float(blk.bounds[1][2] - blk.bounds[0][2]) * 1000.0],
           TOL_MM, "mm")

def sec_slab(W, E: Expect, ck: Checks, out: dict):
    slab = W["AB1_S5_SLAB"]
    sl, c = E.s.slab, E.s.coord
    ck.add("슬래브 전폭 (§8 %s)" % _fmt(2 * sl.half_width * 1000), 2 * sl.half_width * 1000.0,
           float(slab.bounds[1][0] - slab.bounds[0][0]) * 1000.0, TOL_MM, "mm")
    vs = sect_z(slab, E.Z_P4 + 0.01)
    pave = c.deck_drop - c.t_slab_crown
    ck.add("슬래브 crown 상면 y @P4 (§0 Q2·§8: 계획고−포장%s = %.3f−%g)" % (_fmt(pave * 1000), E.EL_P4 - pave, c.y_datum),
           E.CROWN_P4 + c.grade * 0.01, float(vs[:, 1].max()) if vs is not None else float("nan"), TOL, "m")
    ck.add("방호벽 조수 (§8 연단 2 + 중앙 1 = 3)", 3, len([nm for nm in W if "_BARRIER_" in nm]), 0, "조")
    bar_tops = out.get("_bar_tops") or {b: float(W["AB1_S5_BARRIER_" + b].bounds[1][1]) for b in ("L", "R", "CTR")}
    ck.add("연단 방호벽 상단 y L·R (§8 P5 연단 수평면+%s = %.3f)" % (_fmt(sl.barrier[1] * 1000), E.BARRIER_LR_TOP),
           [E.BARRIER_LR_TOP] * 2, [bar_tops["L"], bar_tops["R"]], TOL, "m")
    ck.add_info("중앙 방호벽 상단 y", round(bar_tops["CTR"], 4), "§8 중앙 %s×상세(§판독) — 높이 SPEC 미기재" % _fmt(sl.center_barrier * 1000), "m")

    for b_ in ("L", "R", "CTR"):
        mb = W["AB1_S5_BARRIER_" + b_]
        ck.add("방호벽 %s x 범위 (§8 보도 폭 %g·방호벽 폭 %g)" % (b_, E.s.slab.walk_width, E.s.slab.barrier[0]),
               E.BARRIER_X[b_], [float(mb.bounds[0][0]), float(mb.bounds[1][0])], TOL, "m")

def sec_sp04(W, E: Expect, ck: Checks, out: dict):
    """§9 이음판 4매 — 부착면·이음선 z·폭 (M8 D2). 기대값은 ModelSpec 에서 유도한다."""
    sp = E.s.sp04
    names = [nm for nm in sorted(W) if "_SP04_" in nm]
    ck.add("이음판 매수 (§9 상·하면 + 복부 좌·우 = 4)", 4, len(names), 0, "매")
    zj = E.Z_JOINT
    tf, bf, wb = W["AB1_S5_SP04_TF"], W["AB1_S5_SP04_BF"], W["AB1_S5_SP04_WEB_L"]
    ck.add("이음판 z 중심 4매 (§9 이음선 P4+%g)" % E.s.box.z_sp04_offset, [zj] * 4,
           [float((W[nm].bounds[0][2] + W[nm].bounds[1][2]) / 2) for nm in
            ("AB1_S5_SP04_TF", "AB1_S5_SP04_BF", "AB1_S5_SP04_WEB_L", "AB1_S5_SP04_WEB_R")], TOL, "m")
    ck.add("상면판 상면 y (§9 강상판 상면 + 두께 %s, +z 끝단)" % _fmt(sp.tf[2] * 1000),
           E.deck_top(zj + sp.tf[1] / 2) + sp.tf[2], float(tf.bounds[1][1]), TOL, "m")
    ck.add("하면판 하면 y (§9 하판 하면 − 두께 %s, −z 끝단)" % _fmt(sp.bf[2] * 1000),
           E.bot_out(zj - sp.bf[1] / 2) - sp.bf[2], float(bf.bounds[0][1]), TOL, "m")
    ck.add("복부판 외면 x (§9 웹 외면 %g + 두께 %s)" % (E.s.box.x_web, _fmt(sp.web[2] * 1000)),
           -(E.s.box.x_web + sp.web[2]), float(wb.bounds[0][0]), TOL, "m")
    ck.add("복부판 y 중심 (§9 내공 중앙)", (E.web_top(zj) + E.web_bot(zj)) / 2,
           float((wb.bounds[0][1] + wb.bounds[1][1]) / 2), 0.02, "m")
    ck.add("복부판 높이 (§9 %s)" % _fmt(sp.web[0] * 1000), sp.web[0] * 1000.0,
           float(wb.bounds[1][1] - wb.bounds[0][1]) * 1000.0, 20.0, "mm")


def sec_hstiff(W, E: Expect, ck: Checks, out: dict):
    """§5 복부 수평보강재 — 열별 y·z 범위·내민 길이 (M8 D2)."""
    hs = E.s.hstiff
    names = [nm for nm in sorted(W) if "_HST_" in nm]
    ck.add("수평보강재 부재 수 (§5 상단 2 + 하단 %d)" % (E.N_HST - 2), E.N_HST, len(names), 0, "개")
    up = [W["AB1_S5_HST_UP_L"], W["AB1_S5_HST_UP_R"]]
    zc = (E.HST_UP_Z[0] + E.HST_UP_Z[1]) / 2
    ck.add("상단열 y 중심 (§5 강상판 하면 − %s)" % _fmt(hs.upper_drop * 1000), [E.web_top(zc) - hs.upper_drop] * 2,
           [float((m.bounds[0][1] + m.bounds[1][1]) / 2) for m in up], 0.02, "m")
    ck.add("상단열 z 범위 (§5 받침선 ±%g 안쪽)" % hs.upper_span, E.HST_UP_Z,
           [float(up[0].bounds[0][2]), float(up[0].bounds[1][2])], TOL, "m")
    lo = W["AB1_S5_HST_P4_LO1_L"]
    z0 = float(lo.bounds[0][2]) + 0.5                       # 받침선 쪽 끝에서 조금 안쪽 단면
    v_lo = sect_z(lo, z0)
    ck.add("하단 1열 y @P4+0.5 (§5 하판 상면 + %g·H)" % hs.lower_factors[0],
           E.web_bot(z0) + hs.lower_factors[0] * E.h_at_z(z0) / 1000.0,
           float(v_lo[:, 1].mean()) if v_lo is not None else float("nan"), 0.02, "m")
    ck.add("내민 길이 x (§5 웹 내면에서 %s)" % _fmt(hs.h * 1000), hs.h * 1000.0,
           float(v_lo[:, 0].max() - v_lo[:, 0].min()) * 1000.0 if v_lo is not None else float("nan"), 10.0, "mm")


def sec_mesh_count(W, E: Expect, ck: Checks, out: dict):
    ck.add("총 메시 수 (구성 유도 %d — §1~§10)" % E.N_MESH, E.N_MESH, len(W), 0, "개")


SECTIONS = [("bbox", "ASSEMBLY", sec_bbox), ("내공 H", "BOX", sec_h_profile), ("강상판 상면", "BOX", sec_deck_top),
            ("격벽", "DIA", sec_diaphragms), ("프레임", "FRM", sec_frames), ("종리브", "RIB", sec_ribs),
            ("WG·CS", "WG", sec_wg_cs), ("받침", "BRG", sec_bearings), ("슬래브·방호벽", "SLAB", sec_slab),
            ("이음판", "SP04", sec_sp04), ("수평보강재", "HST", sec_hstiff), ("메시 수", "ASSEMBLY", sec_mesh_count)]


def run(glb: Path, spec: ModelSpec) -> dict:
    """GLB 재로드 → 전 섹션 실측 → 참조 measure v2 와 동일 구조의 결과 dict."""
    W = world_meshes(trimesh.load(str(glb)))
    E = Expect(spec)
    ck = Checks()
    out: dict = {}
    for label, code, fn in SECTIONS:
        ck.group = code
        try:
            fn(W, E, ck, out)
        except KeyError as exc:
            ck.add_missing("%s 섹션 — 노드 누락" % label, "KeyError: %s" % exc)
        except Exception as exc:                               # noqa: BLE001 — 임의 형상(에이전트 산출물)에서도 재실측은 끝까지 간다
            ck.add_missing("%s 섹션 — 실측 오류" % label, "%s: %s" % (type(exc).__name__, exc))
    ck.group = None
    out.pop("_bar_tops", None)
    agg = ck.summary()
    result = {
        "대상": "%s — 독립 재실측 검증" % Path(glb).name,
        "치수정본": "modelspec.json (ModelSpec) — 기대값은 본 모듈이 자체 유도 (빌더 미참조)",
        "월드전개": "graph 노드 순회 (KB §2-16)",
        "허용오차": {"길이_mm": TOL_MM, "개수": 0, "각도_도": TOL_ANG},
    }
    result.update(out)
    result["대조"] = ck.rows
    result["집계"] = agg
    result["섹션별"] = ck.by_section()
    result["종합판정"] = "PASS" if agg["FAIL"] == 0 else "FAIL"
    return result
