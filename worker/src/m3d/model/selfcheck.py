"""빌더 self-check (지식베이스 §6-1) — 계획고·bbox·내공 H 8점·부재 개수·받침 EL·수밀·컬러.

항목마다 `group` 태그(BOX·DIA·FRM·WG·CS·BRG·ASSEMBLY·COMMON)를 붙인다. `section=` 을 주면 그 섹션 메시만 받아
그룹이 section 또는 COMMON 인 항목만 실행한다(M4 D3). pilot(본체·격벽만) 이면 개수·받침 항목은 skipped.
"""

from __future__ import annotations

import re

import numpy as np
import trimesh

from m3d.model.builder import Builder


def run(named: dict[str, trimesh.Trimesh], b: Builder, *, pilot: bool = False, section: str | None = None) -> dict:
    s = b.s
    checks: list[dict] = []

    def want(group):
        return section is None or group in (section, "COMMON")

    def check(label, ok, detail, group):
        if want(group):
            checks.append({"label": label, "ok": bool(ok), "detail": detail, "group": group})

    def skip(label, group):
        if want(group):
            checks.append({"label": label, "ok": None, "detail": "pilot — skipped", "group": group})

    def cnt(pat):
        return sum(1 for n in named if re.match(pat, n))

    # 0) 계획고 기준 검산 — EL(P4)/EL(P5) 는 계획고 식에서 유도(정보 + 단조 증가)
    el4, el5 = b.el_road(b.Z_P4), b.el_road(b.Z_P5)
    check("계획고 P4<P5(종단경사 부호)", el5 > el4, "EL(P4)=%.3f EL(P5)=%.3f" % (el4, el5), "BOX")

    # 1) bbox — 상부구조(받침 제외), 결합본에서만 의미 있음
    if want("ASSEMBLY"):
        sup = trimesh.util.concatenate([m for n, m in named.items() if not n.startswith("AB1_S5_BRG_")])
        bb = sup.bounds
        x_exp = s.slab.half_width if not pilot else s.box.half_flange
        check("bbox x(상부구조)", abs(bb[0][0] + x_exp) < 0.01 and abs(bb[1][0] - x_exp) < 0.01,
              "x[%.3f, %.3f] (기대 ±%.2f)" % (bb[0][0], bb[1][0], x_exp), "ASSEMBLY")
        z_lo_exp, z_hi_exp = (b.Z_P4, b.Z_P5) if pilot else (b.Z_P4 - 0.15, b.Z_P5 + 0.15)
        check("bbox z(상부구조)", abs(bb[0][2] - z_lo_exp) < 0.05 and abs(bb[1][2] - z_hi_exp) < 0.16,
              "z[%.3f, %.3f] (기대 [%.2f, %.2f])" % (bb[0][2], bb[1][2], z_lo_exp, z_hi_exp), "ASSEMBLY")

    # 2) 내공 H 8점 — BOX_TOP 하면 − BOX_BOT 상면 슬라이스 실측
    if want("BOX"):
        vt = np.asarray(named["AB1_S5_BOX_TOP"].vertices)
        vb = np.asarray(named["AB1_S5_BOX_BOT"].vertices)
        for (zc, h_exp) in b.H_CHECK:
            st = vt[np.abs(vt[:, 2] - zc) < 1e-6]
            sb = vb[np.abs(vb[:, 2] - zc) < 1e-6]
            ok = len(st) > 0 and len(sb) > 0
            h_meas = float(st[:, 1].min() - sb[:, 1].max()) if ok else float("nan")
            check("내공 H @P4%+0.3f" % (zc - b.Z_P4), ok and abs(h_meas - h_exp) < 0.002,
                  "실측 %.4f (기대 %.3f)" % (h_meas, h_exp), "BOX")

    # 3) 격벽 z 체인 (KB §2-18) + 개수
    if want("DIA"):
        n_cell = s.diaphragm.n_cell
        dia = sorted(n for n in named if re.match(r"^AB1_S5_DIA\d{2}$", n))
        check("격벽 %d" % (n_cell + 1), len(dia) == n_cell + 1, "%d" % len(dia), "DIA")
        chain_ok = True
        for k, name in enumerate(dia):
            zs = np.asarray(named[name].vertices)[:, 2]
            zc = b.dia_z(k)
            # 판면 정점이 체인 위치 ±10mm 에 있고, 보강재까지 포함한 노드 전체가 ±0.4m 안 (지점 격벽 잭업 350)
            if np.min(np.abs(zs - zc)) > 0.01 or zs.min() < zc - 0.4 or zs.max() > zc + 0.4:
                chain_ok = False
        check("격벽 z 체인 P4+%.1fk" % s.diaphragm.spacing, chain_ok, "판면 정점이 체인 위치 ±10mm", "DIA")

    if pilot and section is None:
        skip("프레임 부재 25×6=150", "FRM")
        skip("WG 부재 그룹 52", "WG")
        skip("CS 52", "CS")
        skip("받침 부품 16", "BRG")
        skip("받침 하면 y", "BRG")
    elif not pilot:
        n_frm = cnt(r"^AB1_S5_FRM\d{2}_(TRW|TRF|BRW|BRF|VSL|VSR)$")
        check("프레임 부재 25×6=150", n_frm == 150, "%d" % n_frm, "FRM")
        n_wg = cnt(r"^AB1_S5_WG\d{3}[LR]$")
        check("WG 부재 그룹 52", n_wg == 52, "%d" % n_wg, "WG")
        n_cs = cnt(r"^AB1_S5_CS\d{3}[LR]$")
        check("CS 52", n_cs == 52, "%d" % n_cs, "CS")
        n_brg = cnt(r"^AB1_S5_BRG_P[45]_[12]_(SOLE|BODY|MORTAR|BLOCK)$")
        check("받침 부품 16", n_brg == 16, "%d" % n_brg, "BRG")
        for pier, el in s.bearing.el_check.items():
            y_exp = el - s.coord.y_datum
            for i in (1, 2):
                m = named.get("AB1_S5_BRG_%s_%d_BODY" % (pier, i))
                y_meas = float(np.asarray(m.vertices)[:, 1].min()) if m is not None else float("nan")
                check("받침 하면 y %s_%d" % (pier, i), m is not None and abs(y_meas - y_exp) < 0.01,
                      "실측 %.4f (기대 %.3f)" % (y_meas, y_exp), "BRG")

    # 4) 메시 수·수밀·색상
    n_mesh = len(named)
    if section is None:
        lo, hi = (25, 40) if pilot else (500, 700)
        check("메시 수 %d~%d" % (lo, hi), lo <= n_mesh <= hi, "%d" % n_mesh, "ASSEMBLY")
    else:
        check("메시 수 ≥1", n_mesh >= 1, "%d" % n_mesh, "COMMON")
    n_wt = sum(1 for m in named.values() if m.is_watertight)
    check("수밀 전건", n_wt == n_mesh, "%d/%d" % (n_wt, n_mesh), "COMMON")
    n_col = sum(1 for m in named.values() if np.asarray(m.visual.face_colors).shape[0] == len(m.faces))
    check("버텍스 컬러 전건", n_col == n_mesh, "%d/%d" % (n_col, n_mesh), "COMMON")
    tris = sum(len(m.faces) for m in named.values())

    passed = sum(1 for c in checks if c["ok"] is True)
    failed = sum(1 for c in checks if c["ok"] is False)
    skipped = sum(1 for c in checks if c["ok"] is None)
    return {"checks": checks, "pass": passed, "fail": failed, "skipped": skipped,
            "meshes": n_mesh, "watertight": n_wt, "triangles": tris, "pilot": pilot, "section": section}
