"""독립 재실측 — 기대값 자체 유도·월드 전개·H 프로파일 PASS/FAIL·빌더 미참조."""

import subprocess
import sys

import numpy as np
import trimesh

from m3d.model import measure as M
from m3d.model.geom import box_prism
from m3d.model.spec import ModelSpec


def test_expect_derives_reference_values_from_spec():
    E = M.Expect(ModelSpec())
    assert abs(E.EL_P4 - 24.948) < 1e-9 and abs(E.TOP_P5 - 21.331) < 1e-9
    assert abs(E.SOFFIT_P4 - 15.603) < 1e-9 and abs(E.Y_MIN_ALL - 15.111) < 1e-9
    assert abs(E.CROWN_P4 - 20.027) < 1e-9 and abs(E.BARRIER_LR_TOP - 21.861) < 1e-9
    assert abs(E.h_mm(7.975) - 3099.85) < 0.01                 # 도면 계수 그대로 (빌더 정규화값 3100 과 독립)
    assert E.DIA_Z[0] == -524.981 and E.DIA_Z[-1] == -455.019 and len(E.DIA_Z) == 26
    assert E.DIA_H[:3] == [4000.0, 3739.0, 3349.0] and E.DIA_H[13] == 2800.0
    assert E.DIA_OPEN[0] == 700.0 and E.DIA_OPEN[1] == 1400.0
    assert E.FRM_Z[0] == -523.6 and len(E.FRM_Z) == 25
    assert E.X3 == [-1.124, 0.0, 1.124] and E.X8[0] == -1.75 and len(E.X8) == 8
    assert E.N_RIB == 93 and E.N_HST == 10 and E.N_MESH == 515
    assert E.Z_RIB_PIER == -520.0 and E.Z_RIB_MID == -490.0 and E.WG_NO == 97


def test_rib_strip_count_follows_sp04_position():
    spec = ModelSpec()
    spec.box.z_sp04_offset = 35.0            # 중앙: 상판 중앙존만 분절, 하판 지점존 분절 없음
    E = M.Expect(spec)
    assert E.N_RIB == 6 + 22 + 16 + 24 - 8 + 22 + 3 + 3       # 하판 중앙존(3열) 분절 추가, 지점존 분절 제거


def _mini_glb(tmp_path, h):
    top = box_prism(-2.35, 2.35, h, h + 0.038, -525.0, -455.0)
    bot = box_prism(-2.35, 2.35, -0.038, 0.0, -525.0, -455.0)
    sc = trimesh.Scene()
    for name, m in (("AB1_S5_BOX_TOP", top), ("AB1_S5_BOX_BOT", bot)):
        m.visual.face_colors = [0, 150, 168, 255]
        sc.add_geometry(m, geom_name=name, node_name=name)
    p = tmp_path / "mini.glb"
    sc.export(str(p))
    return p


def _flat_spec(h):
    spec = ModelSpec()
    spec.box.h_pier = h
    spec.box.h_mid = h
    spec.box.a_dwg = 0.0
    return spec


def test_world_meshes_preserves_node_names(tmp_path):
    W = M.world_meshes(trimesh.load(str(_mini_glb(tmp_path, 3.0))))
    assert set(W) == {"AB1_S5_BOX_TOP", "AB1_S5_BOX_BOT"}
    assert abs(float(W["AB1_S5_BOX_TOP"].bounds[0][1]) - 3.0) < 1e-9


def test_h_profile_pass_and_fail_paths(tmp_path):
    W = M.world_meshes(trimesh.load(str(_mini_glb(tmp_path, 3.0))))
    ck, out = M.Checks(), {}
    M.sec_h_profile(W, M.Expect(_flat_spec(3.0)), ck, out)
    assert len(out["내공_H_프로파일"]) == 8 and all(r["판정"] == "PASS" for r in out["내공_H_프로파일"])
    ck2 = M.Checks()
    M.sec_h_profile(W, M.Expect(_flat_spec(3.010)), ck2, {})          # 10mm 차 → 5mm 허용 초과
    assert ck2.summary()["FAIL"] == 8
    assert ck2.rows[0]["최대편차"] == 10.0 and ck2.rows[0]["단위"] == "mm"


def test_run_records_missing_nodes_as_fail_not_crash(tmp_path):
    r = M.run(_mini_glb(tmp_path, 3.0), _flat_spec(3.0))
    assert r["종합판정"] == "FAIL" and r["집계"]["FAIL"] >= 1
    assert all(c["판정"] == "PASS" for c in r["대조"] if c["항목"].startswith("내공 H"))
    assert any("노드 누락" in c["항목"] for c in r["대조"])
    assert list(r)[:4] == ["대상", "치수정본", "월드전개", "허용오차"] and "대조" in r and "집계" in r


def test_x_gap_at_finds_central_opening():
    path = trimesh.load_path(np.array([[[-2.0, 0, 0], [-0.7, 0, 0]], [[0.7, 0, 0], [2.0, 0, 0]]], dtype=float))
    assert abs(M.x_gap_at(path) - 1400.0) < 1e-6


def test_measure_module_does_not_import_builder():
    code = ("import sys, m3d.model.measure; "
            "bad=[m for m in sys.modules if m.startswith('m3d.model.builder')]; "
            "print(bad); sys.exit(1 if bad else 0)")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
