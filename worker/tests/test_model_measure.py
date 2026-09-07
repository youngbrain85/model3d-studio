"""독립 재실측 — 기대값 자체 유도·월드 전개·H 프로파일 PASS/FAIL·빌더 미참조."""

import subprocess
import sys

import numpy as np
import pytest
import trimesh

from m3d.model import measure as M
from m3d.model.builder import Builder
from m3d.model.geom import box_prism
from m3d.model.spec import ModelSpec


@pytest.fixture(scope="module")
def spec():
    return ModelSpec()


@pytest.fixture(scope="module")
def ref_glb(tmp_path_factory, spec):
    d = tmp_path_factory.mktemp("m")
    b = Builder(spec)
    glb = d / "ref.glb"
    b.export(b.build(pilot=False), glb)
    return glb


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


def test_every_measure_row_carries_a_section_tag(ref_glb, spec):
    """섹션별 판정(M8 D1)을 하려면 행마다 귀속 섹션이 있어야 한다."""
    from m3d.model import sections as X
    r = M.run(ref_glb, spec)
    codes = set(X.CODES) | {"ASSEMBLY"}
    missing = [c["항목"] for c in r["대조"] if not c.get("섹션")]
    assert missing == [], f"섹션 태그 없는 행: {missing}"
    assert {c["섹션"] for c in r["대조"]} <= codes
    agg = r["섹션별"]
    assert agg["DIA"]["PASS"] >= 1 and agg["BRG"]["PASS"] >= 1
    assert sum(v["PASS"] + v["FAIL"] + v["INFO"] for v in agg.values()) == len(r["대조"])


MIN_ITEMS = {"BOX": 4, "DIA": 4, "FRM": 4, "RIB": 4, "HST": 4, "WG": 4, "CS": 4, "SLAB": 4, "SP04": 4, "BRG": 4}


def test_every_section_has_real_coverage(ref_glb, spec):
    """정답을 빼면 이 항목들만 남는다 — 섹션마다 최소 4개, 합계 75개 이상(M8 ②)."""
    r = M.run(ref_glb, spec)
    agg = r["섹션별"]

    def n_of(code):
        v = agg.get(code, {})
        return v.get("PASS", 0) + v.get("FAIL", 0) + v.get("INFO", 0)
    thin = {c: n for c, n in MIN_ITEMS.items() if n_of(c) < n}
    assert thin == {}, f"항목이 모자란 섹션: {thin}"
    assert len(r["대조"]) >= 75, len(r["대조"])
    assert r["집계"]["FAIL"] == 0, [c["항목"] for c in r["대조"] if c["판정"] == "FAIL"]


def test_moved_sp04_plate_fails_only_its_section(ref_glb, spec, tmp_path):
    """이음판 상면판을 20mm 내리면 SP04 항목만 걸린다."""
    from m3d.agent.score import load_named
    named = load_named(ref_glb)
    named["AB1_S5_SP04_TF"].apply_translation([0, -0.02, 0])
    glb = tmp_path / "moved.glb"
    Builder(spec).export(named, glb)
    r = M.run(glb, spec)
    failed = {c["섹션"] for c in r["대조"] if c["판정"] == "FAIL"}
    assert failed == {"SP04"}, [(c["섹션"], c["항목"]) for c in r["대조"] if c["판정"] == "FAIL"]


def test_moved_wg_bracket_is_caught(ref_glb, spec, tmp_path):
    """M7 에서 정답 대조로만 잡히던 1.7m 정착대 오류를 재실측이 잡는다."""
    from m3d.agent.score import load_named
    named = load_named(ref_glb)
    for nm in [n for n in named if n.endswith("_BR")]:
        named[nm].apply_translation([0, 1.688, 0])
    glb = tmp_path / "wgbr.glb"
    Builder(spec).export(named, glb)
    r = M.run(glb, spec)
    assert "WG" in {c["섹션"] for c in r["대조"] if c["판정"] == "FAIL"}
