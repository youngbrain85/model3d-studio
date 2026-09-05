"""P4~P5 정밀 3D 모델 빌더 — ModelSpec 준거 결정론 빌더 (M3 설계서 D1, 참조 v2 기법 계승).

치수는 전부 `ModelSpec`(modelspec.json)에서 읽는다 — 이 모듈은 상수를 갖지 않는다. 기하 기법·
노드 명명(`AB1_S5_*`)·색상·관통 삽입은 참조 v2 빌더(`build_ab1_p4p5_v2.py`)를 그대로 잇는다.

KB 가드(지식베이스_교훈 §2): 2-13·17 공면 금지 → 접합부 5mm 관통 삽입 / 2-14 전 메시 버텍스 컬러 /
2-15 대소문자만 다른 노드명 금지 / 2-18 반복 부재 위치는 전역 체인(받침선 + n×spacing)에서 유도.

── 사양 대비 단순화·근사 (참조 v2 [A1]~[A21] 계승 — 본문 주석에도 개별 명기) ──────────
 [A1] §1 판두께 내면 돌출: 내공 H(z) 파라볼라를 정본으로 삼아 웹·격벽 높이=H 고정.
      → 상판 외면(EL−deck_drop 평면)은 평탄, 하판 '외면'은 두께 전이점에서 계단(내면이 연속).
      §1 "외면 평탄"과 §1 H식·§2 격벽높이표는 동시 만족 불가 — H식·격벽표를 우선(사양 모순 항목).
 [A2] §1 포물선 계수: 도면 계수(a_dwg) 대신 경계연속 정규화 A=(h_pier−h_mid)/l_para²
      (차이 최대 0.6mm, 검산 assert 로 도면 계수 정합 확인).
 [A3] §2 개구 R100: 격벽 개구는 판 4장 조합(불리언 회피)으로 구성 — 모서리 R100 생략.
 [A4] §2 지점 격벽 수직·잭업보강재: '양면' 중 경간 외측면은 모델 범위 밖 → 내측면만 부착.
 [A5] §2 일반 격벽 개구 보강재: 부착면 미기재 → +z 단면(한 면)에만 부착.
 [A6] §3 T리브 플랜지 두께: G1 상면(BOM 26t) 외 미기재 → 웹 두께와 동일로 근사.
 [A7] §3 V-STIFF 연직 위치: 상·하 이격 미기재 → 내공 중앙 배치.
 [A8] §6 WG niche R300 의 X' 위치 미기재 → 등깊이 하연에 접하고 knee 를 지나는 원호로 수치 해석 도출.
 [A9] §6 WG 연직 앵커: 상플랜지 상면 = 슬래브 캔틸레버 하면 시작(−330, §8) + 3mm 삽입.
 [A10] §6 WG 웹 판두께 미기재 → 12t 로 근사. 하플랜지는 하연 절선을 따르는 연직오프셋 리본.
 [A11] §6 정착대: 상세 미기재 → 웹면 돌출 350 블록으로 근사.
 [A12] §6 가설거셋: 사양대로 미포함(현장 확인 항목).
 [A13] §7 CS 상면 = WG 선단 상면(crown−409, 시프트 반영) — §8 슬래브 하면 절선값과 약 7mm 차, §7 동일면 우선.
 [A14] §7 CS 세그 분절: WG 위치 중심 ±1,400, 양끝 세그는 받침선에서 절단(26세그 유지).
 [A15] §8 중앙방호벽 단면 상세 미전재 → 연단과 동일 450×330(모따기 30) 근사.
 [A16] §8 포장·보도 마감·상부 난간: 사양대로 생략.
 [A17] §9 SP04 내면판·리브이음판·볼트: 사양대로 생략(외면 4매만).
 [A18] §10 받침 하면 EL 검증치와 정합하려면 '본체 337'은 솔플레이트 중앙두께 38 포함 총높이 → 본체 순높이 299.
 [A19] §10 받침은 받침선 중심 배치 → z 로 ±0.685 경간 밖 돌출(사양 형상 유지). bbox 검증은 상부구조 기준.
 [A20] §5 하단 수평보강재 예시값(+2.8 에서 518/1,342)은 0.14H/0.36H 공식값과 4~5mm 상이 — 공식 채택.
 [A21] §1 "웹 2매 @4,500(중심)" vs "상판 웹 밖 100 돌출": 웹 외면 x=±x_web 채택(사양 내부 불일치 항목).

좌표계(§0): x=교축직각, y=EL−y_datum, z=STA−4190 (m, Y-up). 상자 중심 x=0.
"""

from __future__ import annotations

import numpy as np
import trimesh

from m3d.model.geom import (box_prism, loft, mirror_mesh, mirror_poly, paint, rect,
                            zone_loft)
from m3d.model.spec import ModelSpec

COL_STEEL = [0, 150, 168, 255]     # 강재 teal (참조 v1 관례, KB §2-14)
COL_CONC = [200, 198, 192, 255]    # 콘크리트 회백
COL_BRG = [75, 75, 82, 255]        # 받침 진회
COL_SOLE = [40, 70, 120, 255]      # 솔플레이트 암청
INS = 0.005                        # KB §2-13·17: 표준 관통 삽입 5mm


class Builder:
    """ModelSpec → 노드명별 메시. `build(pilot=True)` 는 §1 본체 + §2 격벽만."""

    def __init__(self, spec: ModelSpec):
        self.s = spec
        c, b = spec.coord, spec.box
        self.Z_P4, self.Z_P5 = c.z_p4, c.z_p5
        self.SPAN = c.span
        self.A_EFF = (b.h_pier - b.h_mid) / (b.l_para ** 2)              # [A2]
        self.BREAKS_D = sorted({d for zone in (b.top_t, b.bot_t, b.web_t) for (d0, d1, _) in zone
                                for d in (d0, d1) if 0.0 < d < self.SPAN})
        self.BREAKS_Z = [self.Z_P4 + d for d in self.BREAKS_D]
        self.PARA = [(self.Z_P4 + b.l_flat, self.Z_P4 + b.l_flat + b.l_para),
                     (self.Z_P5 - b.l_flat - b.l_para, self.Z_P5 - b.l_flat)]
        l_p = b.l_flat + b.l_para
        z_mid = (self.Z_P4 + self.Z_P5) / 2.0
        h_q = self.h_at_d(l_p / 2.0 + b.l_flat / 2.0)   # 중간 검산점(등고+포물선 중간)
        self.H_CHECK = [
            (self.Z_P4, b.h_pier), (self.Z_P4 + b.l_flat, b.h_pier),
            (self.Z_P4 + b.l_flat / 2.0 + l_p / 2.0, h_q), (self.Z_P4 + l_p, b.h_mid), (z_mid, b.h_mid),
            (self.Z_P5 - l_p, b.h_mid), (self.Z_P5 - b.l_flat / 2.0 - l_p / 2.0, h_q),
            (self.Z_P5 - b.l_flat, b.h_pier),
        ]
        self._assert_spec()

    # ── 검산 (참조 v1·v2 계승) ─────────────────────────────────────────────────
    def _assert_spec(self):
        b, c = self.s.box, self.s.coord
        assert abs(b.a_dwg * b.l_para ** 2 - (b.h_pier - b.h_mid)) < 2e-3, "포물선 계수 검산 실패"  # [A2]
        assert self.SPAN - 2 * (b.l_flat + b.l_para) > 0, "변단면 사슬 검산 실패(중앙 등고 구간 ≤ 0)"
        for zone in (b.top_t, b.bot_t, b.web_t):
            assert abs(zone[0][0]) < 1e-9 and abs(zone[-1][1] - self.SPAN) < 1e-9, "판두께 존 범위"
            for a, bb in zip(zone, zone[1:]):
                assert abs(a[1] - bb[0]) < 1e-9, "판두께 존 사슬 불연속"
        assert c.walk_side_sign in (-1, 1)

    # ── §0·§1 프로파일 함수 (전부 전역 z 식에서 유도 — KB §2-18) ──────────────
    def el_road(self, z):
        """§0 도로 계획고(crown 기준)."""
        c = self.s.coord
        return c.el0 + c.grade * (z - c.z_sta3400)

    def y_deck_top(self, z):
        """§0: 강상판 상면 y = 계획고 − deck_drop − y_datum (횡방향 수평)."""
        c = self.s.coord
        return self.el_road(z) - c.deck_drop - c.y_datum

    def y_crown(self, z):
        return self.y_deck_top(z) + self.s.coord.t_slab_crown

    @staticmethod
    def _t_of(zone, d):
        for (d0, d1, t) in zone:
            if d0 - 1e-9 <= d <= d1 + 1e-9:
                return t
        raise ValueError("존 밖 d: %r" % d)

    def t_top(self, z):
        return self._t_of(self.s.box.top_t, z - self.Z_P4)

    def t_bot(self, z):
        return self._t_of(self.s.box.bot_t, z - self.Z_P4)

    def t_web(self, z):
        return self._t_of(self.s.box.web_t, z - self.Z_P4)

    def h_at_d(self, d):
        b = self.s.box
        if d <= b.l_flat:
            return b.h_pier
        if d <= b.l_flat + b.l_para:
            s_ = (b.l_flat + b.l_para) - d
            return b.h_mid + self.A_EFF * s_ * s_
        return b.h_mid

    def h_box(self, z):
        """§1: 내공 H(z) — 받침선距 d≤l_flat 등고 / 포물선 / 중앙 등고 [A2]."""
        d = min(z - self.Z_P4, self.Z_P5 - z)
        assert d > -1e-6, "경간 밖 z: %r" % z
        return self.h_at_d(d)

    def y_web_top(self, z):
        return self.y_deck_top(z) - self.t_top(z)

    def y_web_bot(self, z):
        return self.y_web_top(z) - self.h_box(z)

    def y_bot_out(self, z):
        """하판 외면(하면) — [A1] 내공 정본화로 두께 전이점에서 계단 발생."""
        return self.y_web_bot(z) - self.t_bot(z)

    def _zone_loft(self, z0, z1, poly_fn):
        return zone_loft(z0, z1, poly_fn, breaks=self.BREAKS_Z, para_ranges=self.PARA,
                         checks=[zc for zc, _ in self.H_CHECK])

    # ── §1 강상자 본체 ─────────────────────────────────────────────────────────
    def build_box_top(self):
        hf = self.s.box.half_flange
        return paint(self._zone_loft(self.Z_P4, self.Z_P5, lambda z: rect(
            -hf, hf, self.y_deck_top(z) - self.t_top(z), self.y_deck_top(z))), COL_STEEL)

    def build_box_bot(self):
        hf = self.s.box.half_flange
        return paint(self._zone_loft(self.Z_P4, self.Z_P5, lambda z: rect(
            -hf, hf, self.y_bot_out(z), self.y_web_bot(z))), COL_STEEL)

    def build_box_web(self, side):
        xw = self.s.box.x_web

        def poly(z):
            tw = self.t_web(z)
            p = rect(xw - tw, xw, self.y_web_bot(z) - INS, self.y_web_top(z) + INS)
            return mirror_poly(p) if side < 0 else p
        return paint(self._zone_loft(self.Z_P4, self.Z_P5, poly), COL_STEEL)

    # ── §2 격벽 26면 — z = P4 + spacing·k. 개구는 판 4장 조합 [A3] ─────────────
    def dia_z(self, k):
        return self.Z_P4 + k * self.s.diaphragm.spacing

    def dia_half_w(self, z):
        return self.s.box.x_web - self.t_web(z) + INS

    def _dia_panels(self, zc, z0, z1, open_w, open_h, sill):
        xh = self.dia_half_w(zc)
        y_lo = self.y_web_bot(zc) - INS
        y_top = self.y_web_top(zc) + INS
        y_o0 = self.y_web_bot(zc) + sill
        y_o1 = y_o0 + open_h
        parts = [box_prism(-xh, xh, y_lo, y_o0, z0, z1), box_prism(-xh, xh, y_o1, y_top, z0, z1)]
        for sx in (+1, -1):
            xa, xb = sorted((sx * open_w / 2.0, sx * xh))
            parts.append(box_prism(xa, xb, y_o0 - 0.03, y_o1 + 0.03, z0 - 0.002, z1 + 0.002))
        return parts

    def build_dia_support(self, k):
        """§2 지점 격벽(P4/P5) — 수직·잭업보강재는 내측면만 [A4]."""
        d = self.s.diaphragm
        zc = self.dia_z(k)
        inward = +1 if k == 0 else -1
        z0 = zc + (0.002 if inward > 0 else -0.002 - d.support_t)
        z1 = z0 + d.support_t
        parts = self._dia_panels(zc, z0, z1, d.support_open[0], d.support_open[1], d.support_sill)
        y_b, y_t = self.y_web_bot(zc), self.y_web_top(zc)
        zf = z1 if inward > 0 else z0
        vt, vw, _n = d.support_vstiff
        za, zb = sorted((zf - inward * INS, zf + inward * vw))
        xb_ = self.s.bearing.x
        for sx in (+1, -1):                                   # 수직보강재 ×6(내측면)
            for xo in (xb_ - 0.2, xb_, xb_ + 0.2):
                parts.append(box_prism(sx * xo - vt / 2, sx * xo + vt / 2, y_b + 0.002, y_t - 0.002, za, zb))
        jt, jw, jh = d.support_jack
        za, zb = sorted((zf - inward * INS, zf + inward * jw))
        for sx in (+1, -1):                                   # 잭업보강재 상·하(받침 직상)
            parts.append(box_prism(sx * xb_ - jt / 2, sx * xb_ + jt / 2, y_t - jh, y_t - 0.002, za, zb))
            parts.append(box_prism(sx * xb_ - jt / 2, sx * xb_ + jt / 2, y_b + 0.002, y_b + jh, za, zb))
        return paint(trimesh.util.concatenate(parts), COL_STEEL)

    def dia_sill(self, dmin):
        d = self.s.diaphragm
        cx = [dd for dd, name in d.type_map if name.startswith("CX")]
        return d.sill_cx if cx and (min(cx) - 0.1 < dmin < max(cx) + 0.1) else d.sill_cl

    def build_dia_interior(self, k):
        """§2 일반 격벽: 개구 보강재는 +z 면에만 [A5]."""
        d = self.s.diaphragm
        zc = self.dia_z(k)
        dmin = min(zc - self.Z_P4, self.Z_P5 - zc)
        sill = self.dia_sill(dmin)
        zh = d.interior_t / 2.0
        ow, oh = d.interior_open
        parts = self._dia_panels(zc, zc - zh, zc + zh, ow, oh, sill)
        y_o0 = self.y_web_bot(zc) + sill
        y_o1 = y_o0 + oh
        y_mid = (y_o0 + y_o1) / 2.0
        st, sh_, sv, sl = d.open_stiff
        zf0, zf1 = zc + zh - INS, zc + zh + sh_
        parts.append(box_prism(-sl / 2, sl / 2, y_o0 - st, y_o0, zf0, zf1))
        parts.append(box_prism(-sl / 2, sl / 2, y_o1, y_o1 + st, zf0, zf1))
        zf1 = zc + zh + sv
        for sx in (+1, -1):
            xa, xb = sorted((sx * ow / 2, sx * ow / 2 + sx * st))
            parts.append(box_prism(xa, xb, y_mid - sl / 2, y_mid + sl / 2, zf0, zf1))
        return paint(trimesh.util.concatenate(parts), COL_STEEL)

    # ── 조립 ───────────────────────────────────────────────────────────────────
    def build(self, pilot: bool = False) -> dict[str, trimesh.Trimesh]:
        named: dict[str, trimesh.Trimesh] = {}

        def add(name, mesh):
            assert name not in named, "노드명 중복: %s" % name
            mesh.metadata["name"] = name
            named[name] = mesh

        add("AB1_S5_BOX_TOP", self.build_box_top())
        add("AB1_S5_BOX_BOT", self.build_box_bot())
        add("AB1_S5_BOX_WEB_R", self.build_box_web(+1))
        add("AB1_S5_BOX_WEB_L", self.build_box_web(-1))
        n_cell = self.s.diaphragm.n_cell
        for k in range(n_cell + 1):
            name = "AB1_S5_DIA%02d" % (k + 1)
            add(name, self.build_dia_support(k) if k in (0, n_cell) else self.build_dia_interior(k))
        if pilot:
            return named
        from m3d.model import builder_full            # §3~§10 (Task 4)
        builder_full.add_all(self, add)
        return named

    def export(self, named: dict[str, trimesh.Trimesh], glb_path) -> trimesh.Scene:
        """색상·노드명 가드(KB §2-14·15) 후 GLB 로 내보낸다."""
        lows = [n.lower() for n in named]
        assert len(set(lows)) == len(lows), "대소문자만 다른 노드명 존재 (KB §2-15)"
        scene = trimesh.Scene()
        for name, m in named.items():
            fc = np.asarray(m.visual.face_colors)
            assert fc.shape[0] == len(m.faces) and fc[:, 3].min() > 0, "무색 메시 존재 (KB §2-14): %s" % name
            scene.add_geometry(m, geom_name=name, node_name=name)
        scene.export(str(glb_path))
        return scene
