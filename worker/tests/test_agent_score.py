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
    assert sc["compare"]["only_ours"] == [] and sc["compare"]["only_ref"] == [] and sc["compare"]["bbox_dev_max_m"] == 0.0
    assert sc["section_selfcheck"]["fail"] == 0 and sc["assembled_selfcheck"]["fail"] == 0 and sc["measure"]["FAIL"] == 0
    assert (tmp_path / "assembled.glb").is_file()
    summ = S.summary(sc, attempts=1)
    assert summ == {"pass": True, "only_ours": 0, "only_ref": 0, "bbox_dev_max_m": 0.0, "section_fail": 0,
                    "assembled_fail": 0, "measure_fail": 0, "attempts": 1}


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
    assert sc["compare"]["only_ref"] == ["AB1_S5_DIA26"] and sc["compare"]["bbox_dev_max_m"] > 0.005
    assert sc["section_selfcheck"]["fail"] >= 1                     # 격벽 26 개수·체인
    fb = S.feedback_text(sc)
    assert "AB1_S5_DIA26" in fb and "AB1_S5_DIA03" in fb and "20" in fb
    wd = sc["compare"]["worst_detail"]
    assert wd[0]["node"] == "AB1_S5_DIA03"
    assert {(a["axis"], a["bound"], a["delta_mm"]) for a in wd[0]["axes"]} == {("z", "min", -20), ("z", "max", -20)}
    assert "노드 bbox = 그 노드에 합친 모든 솔리드" in fb
    assert "AB1_S5_DIA03: z 최소" in fb and "정답이 -z 쪽으로 20mm 더 뻗음" in fb and "우리가 +z 쪽으로 20mm 더 뻗음(초과)" in fb
    assert "판면 정점이 체인 위치 ±10mm 에 없다" in fb and "바꾸지 말 것" not in fb
    json.dumps(sc)                                                    # 직렬화 가능(JSON 저장용)


def test_feedback_hints_plate_ok_when_checks_pass():
    """판 검사(체인·결합·재실측)가 통과했으면 '판을 바꾸지 말 것' 힌트, 체인 힌트는 없음(M6 D3)."""
    sc = {"pass": False,
          "compare": {"only_ours": [], "only_ref": [], "common": 26, "bbox_dev_max_m": 0.326, "bbox_dev_over_1mm": 2, "faces_equal": False,
                      "worst": [{"node": "AB1_S5_DIA01", "dev_m": 0.326}],
                      "worst_detail": [{"node": "AB1_S5_DIA01", "ours": [[-2.239, 15.636, -525.0], [2.239, 19.646, -524.936]],
                                        "ref": [[-2.239, 15.636, -525.0], [2.239, 19.646, -524.61]],
                                        "axes": [{"axis": "z", "bound": "max", "ours": -524.936, "ref": -524.61, "delta_mm": 326}]}]},
          "section_selfcheck": {"pass": 5, "fail": 0, "failed": []}, "assembled_selfcheck": {"pass": 24, "fail": 0, "failed": []},
          "measure": {"PASS": 47, "FAIL": 0, "INFO": 2, "failed": []}}
    fb = S.feedback_text(sc)
    assert fb.splitlines()[0] == "채점: FAIL"
    assert "(노드 bbox = 그 노드에 합친 모든 솔리드 — 판+보강재 — 의 전체 범위이며 판 두께가 아니다)" in fb
    assert "  AB1_S5_DIA01: z 최대 -524.936 → 정답 -524.61 — 정답이 +z 쪽으로 326mm 더 뻗음" in fb
    assert "판 두께·위치는 검사를 통과했으니 바꾸지 말 것" in fb and "체인 위치 ±10mm 에 없다" not in fb
