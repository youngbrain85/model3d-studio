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
    json.dumps(sc)                                                    # 직렬화 가능(JSON 저장용)
