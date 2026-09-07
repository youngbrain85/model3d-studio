"""채점 — 정답 섹션이면 pass, 노드가 빠지거나 어긋나면 fail + 피드백 (M5 D6)."""

import json

import pytest

from m3d.agent import score as S
from m3d.model import sections as X
from m3d.model.builder import Builder
from m3d.model.spec import ModelSpec


@pytest.fixture(scope="module")
def ref_dir(tmp_path_factory):
    """정답 빌드 디렉터리(섹션 10 GLB) — 실제 빌더로 한 번만 만든다."""
    d = tmp_path_factory.mktemp("ref")
    spec = ModelSpec()
    b = Builder(spec)
    secs = X.split(b.build(pilot=False), spec.coord.segment)
    b.export_sections(secs, d)
    return d


def test_reference_section_scores_pass(ref_dir, tmp_path):
    spec = ModelSpec()
    sc = S.score_section("DIA", ref_dir / "sections" / "P4P5" / "DIA.glb", spec, ref_dir, work_dir=tmp_path)
    assert sc["pass"] is True
    assert sc["reference"]["only_ours"] == [] and sc["reference"]["only_ref"] == [] and sc["reference"]["bbox_dev_max_m"] == 0.0
    assert sc["sanity"]["fail"] == 0
    assert sc["section_selfcheck"]["fail"] == 0 and sc["assembled_selfcheck"]["fail"] == 0 and sc["measure"]["FAIL"] == 0
    assert (tmp_path / "assembled.glb").is_file()
    summ = S.summary(sc, attempts=1)
    assert summ == {"pass": True, "sanity_fail": 0, "section_fail": 0, "assembled_fail": 0,
                    "measure_section_fail": 0, "measure_fail": 0, "attempts": 1,
                    "bbox_dev_max_m": 0.0, "only_ours": 0, "only_ref": 0}


def test_missing_and_shifted_nodes_fail_with_feedback(ref_dir, tmp_path):
    spec = ModelSpec()
    named = S.load_named(ref_dir / "sections" / "P4P5" / "DIA.glb")
    named.pop("AB1_S5_DIA26")
    named["AB1_S5_DIA03"].apply_translation([0, 0, 0.02])            # 20mm 밀림
    b = Builder(spec)
    glb = tmp_path / "agent.glb"
    b.export(named, glb)
    sc = S.score_section("DIA", glb, spec, ref_dir, work_dir=tmp_path)
    assert sc["pass"] is False
    assert sc["reference"]["only_ref"] == ["AB1_S5_DIA26"] and sc["reference"]["bbox_dev_max_m"] > 0.005
    assert sc["section_selfcheck"]["fail"] >= 1                     # 격벽 26 개수·체인
    fb = S.feedback_text(sc)
    assert "AB1_S5_DIA26" in fb and "AB1_S5_DIA03" in fb and "20" in fb
    wd = sc["reference"]["worst_detail"]
    assert wd[0]["node"] == "AB1_S5_DIA03" and wd[0]["role"] == "일반 격벽"
    assert {(a["axis"], a["bound"], a["delta_mm"]) for a in wd[0]["axes"]} == {("z", "min", -20), ("z", "max", -20)}
    assert "노드 bbox = 그 노드에 합친 모든 솔리드" in fb
    assert "AB1_S5_DIA03(일반 격벽): z 최소" in fb and "정답이 -z 쪽으로 20mm 더 뻗음" in fb and "우리가 +z 쪽으로 20mm 더 뻗음(초과)" in fb
    assert "판면 정점이 체인 위치 ±10mm 에 없다" in fb
    json.dumps(sc)                                                    # 직렬화 가능(JSON 저장용)


def test_feedback_hints_plate_ok_when_checks_pass():
    """판 검사(체인·결합·재실측)가 통과했으면 '판을 바꾸지 말 것' 힌트, 체인 힌트는 없음(M6 D3)."""
    sc = {"pass": False,
          "reference": {"only_ours": [], "only_ref": [], "common": 26, "bbox_dev_max_m": 0.326, "bbox_dev_over_1mm": 2, "faces_equal": False,
                      "worst": [{"node": "AB1_S5_DIA01", "dev_m": 0.326}],
                      "worst_detail": [{"node": "AB1_S5_DIA01", "role": "지점 격벽", "ours": [[-2.239, 15.636, -525.0], [2.239, 19.646, -524.936]],
                                        "ref": [[-2.239, 15.636, -525.0], [2.239, 19.646, -524.61]],
                                        "axes": [{"axis": "z", "bound": "max", "ours": -524.936, "ref": -524.61, "delta_mm": 326}]}]},
          "sanity": {"pass": 3, "fail": 0, "checks": []},
          "section_selfcheck": {"pass": 5, "fail": 0, "failed": []}, "assembled_selfcheck": {"pass": 24, "fail": 0, "failed": []},
          "measure": {"PASS": 47, "FAIL": 0, "INFO": 2, "section_fail": 0, "failed": []}}
    fb = S.feedback_text(sc)
    assert fb.splitlines()[0] == "채점: FAIL"
    assert "(노드 bbox = 그 노드에 합친 모든 솔리드 — 판+보강재 — 의 전체 범위이며 판 두께가 아니다)" in fb
    assert "  AB1_S5_DIA01(지점 격벽): z 최대 -524.936 → 정답 -524.61 — 정답이 +z 쪽으로 326mm 더 뻗음" in fb
    assert "합격 여부는 위 항목으로 정한다" in fb            # 정답 대조는 참고 정보라고 밝힌다(M8 D5)
    assert "체인 위치 ±10mm 에 없다" not in fb


def test_bbox_rule_has_float32_rounding_margin():
    """정확히 5mm(INS 누락) 차이가 GLB float32 반올림으로 5.001mm 가 되어도 통과, 5.2mm 는 실패(M6 잡 3: dev 0.005001).

    float32 는 |좌표| ≤ 1,000m 에서 ulp ≤ 6e-5 m 이므로 여유 0.1mm 면 반올림을 덮고 실제 편차(0.2mm+)는 걸러진다.
    """
    assert S.BBOX_EPS_M == 1e-4
    assert S.within_bbox_tol(0.005) and S.within_bbox_tol(0.005001) and S.within_bbox_tol(0.0051)
    assert not S.within_bbox_tol(0.0052) and not S.within_bbox_tol(0.008)
    assert not S.within_bbox_tol(None)


def test_feedback_role_label_comes_from_section_meta():
    """역할 라벨은 섹션 메타에서 온다 — 격벽 전용 분기가 아니다(M7 D2)."""
    from m3d.agent import sections_meta as M
    assert S.node_role("FRM", "AB1_S5_FRM07_VSL", ModelSpec()) == M.role_of("FRM", "AB1_S5_FRM07_VSL") == "수직보강재"
    assert S.node_role("BRG", "AB1_S5_BRG_P4_1_SOLE", ModelSpec()) == "솔플레이트"
    assert S.node_role("SP04", "AB1_S5_SP04_TF", ModelSpec()) == "상면판"


def test_reference_free_pass_without_ref_dir(ref_dir, tmp_path):
    """정답 없이도 판정한다 — 새 교량 경로(M8 D4)."""
    spec = ModelSpec()
    sc = S.score_section("DIA", ref_dir / "sections" / "P4P5" / "DIA.glb", spec, None, work_dir=tmp_path / "a")
    assert sc["pass"] is True and "reference" not in sc
    assert sc["sanity"]["fail"] == 0 and sc["measure"]["section_fail"] == 0
    summ = S.summary(sc, attempts=1)
    assert summ["bbox_dev_max_m"] is None and summ["sanity_fail"] == 0 and summ["measure_section_fail"] == 0


def test_reference_is_informational_only(ref_dir, tmp_path):
    """정답이 있으면 참고로 싣되 합격 여부에는 넣지 않는다."""
    spec = ModelSpec()
    named = S.load_named(ref_dir / "sections" / "P4P5" / "DIA.glb")
    named["AB1_S5_DIA13"].apply_translation([0, 0, 0.02])          # 20mm — 정답 대비 어긋남
    glb = tmp_path / "shift.glb"
    Builder(spec).export(named, glb)
    sc = S.score_section("DIA", glb, spec, ref_dir, work_dir=tmp_path / "b")
    assert sc["reference"]["bbox_dev_max_m"] > 0.005               # 정답 대조는 어긋났다고 말하고
    assert sc["section_selfcheck"]["fail"] >= 1                    # 합격 여부는 정답 무관 검사가 정한다
    assert sc["pass"] is False


def test_feedback_leads_with_reference_free_findings(ref_dir, tmp_path):
    spec = ModelSpec()
    named = S.load_named(ref_dir / "sections" / "P4P5" / "SP04.glb")
    named["AB1_S5_SP04_TF"].apply_translation([0, -0.02, 0])
    glb = tmp_path / "sp04.glb"
    Builder(spec).export(named, glb)
    sc = S.score_section("SP04", glb, spec, None, work_dir=tmp_path / "c")
    fb = S.feedback_text(sc)
    assert sc["pass"] is False and "재실측 실패" in fb
    assert "상면판 상면 y" in fb and "기대" in fb and "실측" in fb
    assert "정답" not in fb                                        # 정답이 없으면 정답 얘기를 하지 않는다
