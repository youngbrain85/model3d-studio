"""참조 대조 — 이름 매칭·허용오차 경계·na 판정."""

import trimesh

from m3d.model import compare as C
from m3d.model.geom import box_prism


def _row(name, unit, exp, meas, dev, verdict="PASS"):
    return {"항목": name, "단위": unit, "기대": exp, "실측": meas, "허용오차": 0.005, "최대편차": dev, "판정": verdict}


def test_compare_matches_by_item_name_and_unit_tolerance():
    ours = {"대상": "ours.glb", "bbox": {"전체": {"x": [-7.85, 7.85]}},
            "내공_H_프로파일": [{"위치": "P4 받침선", "z": -524.999, "기대_mm": 4000.0, "실측_mm": 4003.0, "판정": "PASS"}],
            "대조": [_row("A (m)", "m", 1.0, 1.004, 0.004), _row("B 수", "개", 26, 26, 0.0), _row("C (mm)", "mm", 100.0, 106.0, 6.0),
                     _row("D 각도", "도", 28.222, 28.6, 0.378)],
            "집계": {"PASS": 4, "FAIL": 0}}
    ref = {"대상": "ref.glb", "bbox": {"전체": {"x": [-7.85, 7.85]}},
           "내공_H_프로파일": [{"위치": "P4 받침선", "z": -524.999, "기대_mm": 4000.0, "실측_mm": 4000.0, "판정": "PASS"}],
           "대조": [_row("B 수", "개", 26, 26, 0.0), _row("A (m)", "m", 1.0, 1.0, 0.0), _row("C (mm)", "mm", 100.0, 100.0, 0.0),
                    _row("D 각도", "도", 28.222, 28.0, 0.222), _row("E 참조에만", "m", 1, 1, 0)],
           "집계": {"PASS": 5, "FAIL": 0}}
    r = C.compare(ours, ref, tol_len_mm=5.0)
    by = {it["path"]: it for it in r["items"]}
    assert by["내공_H_프로파일[P4 받침선]/실측_mm"]["verdict"] == "match"        # 3mm ≤ 5mm
    assert by["대조[A (m)]/실측"]["verdict"] == "match"                       # 4mm (m 단위 0.004 ≤ 0.005)
    assert by["대조[C (mm)]/실측"]["verdict"] == "mismatch"                   # 6mm > 5mm
    assert by["대조[D 각도]/실측"]["verdict"] == "mismatch"                   # 0.6° > 0.5°
    assert by["대조[B 수]/실측"]["verdict"] == "match"
    assert by["대조[E 참조에만]"]["verdict"] == "na" and by["대조[E 참조에만]"]["cause"] == "우리에 없음"
    assert by["집계/PASS"]["verdict"] == "mismatch" and by["집계/PASS"]["diff"] == -1
    assert "대상" not in by                                                      # 메타 문구 제외
    assert r["summary"]["mismatch"] == 4 and r["summary"]["na"] == 1


def test_compare_count_tolerance_is_zero_and_length_mismatch_is_na():
    ours = {"대조": [_row("N 수", "개", 3, 3, 0.0)], "종리브_열": {"z=-520_상판_x": [-1.124, 0.0, 1.124]}}
    ref = {"대조": [_row("N 수", "개", 3, 4, 1.0, "FAIL")], "종리브_열": {"z=-520_상판_x": [-1.124, 0.0]}}
    r = C.compare(ours, ref)
    by = {it["path"]: it for it in r["items"]}
    assert by["대조[N 수]/실측"]["verdict"] == "mismatch" and by["대조[N 수]/판정"]["verdict"] == "mismatch"
    assert by["종리브_열/z=-520_상판_x"]["verdict"] == "na" and "길이 불일치" in by["종리브_열/z=-520_상판_x"]["cause"]


def test_compare_glb_reports_node_sets_and_bbox_deviation(tmp_path):
    def glb(path, dy, extra=None):
        sc = trimesh.Scene()
        for name, m in [("A", box_prism(0, 1, 0, 1 + dy, 0, 1)), ("B", box_prism(2, 3, 0, 1, 0, 1))] + (extra or []):
            m.visual.face_colors = [0, 150, 168, 255]
            sc.add_geometry(m, geom_name=name, node_name=name)
        sc.export(str(path))
        return path
    a = glb(tmp_path / "a.glb", 0.002)
    b = glb(tmp_path / "b.glb", 0.0, [("C", box_prism(4, 5, 0, 1, 0, 1))])
    g = C.compare_glb(a, b)
    assert g["ours"]["nodes"] == 2 and g["ref"]["nodes"] == 3 and g["common"] == 2
    assert g["only_ref"] == ["C"] and g["only_ours"] == []
    assert abs(g["bbox_dev_max_m"] - 0.002) < 1e-6 and g["bbox_dev_over_1mm"] == 1 and g["worst"][0]["node"] == "A"
    assert g["faces_equal"] is True
