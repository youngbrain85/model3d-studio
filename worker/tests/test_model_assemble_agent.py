"""전집 결합 (M7 D8) — 섹션마다 통과한 에이전트 산출을 골라 결합 빌드를 만든다. LLM·업로드 없음."""

import dataclasses
import json

import pytest

from m3d.config import load_config
from m3d.model import assemble_agent as A
from m3d.model import sections as X
from m3d.model.builder import Builder
from m3d.model.spec import ModelSpec


@pytest.fixture(scope="module")
def ref_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("ref")
    spec = ModelSpec()
    b = Builder(spec)
    b.export_sections(X.split(b.build(pilot=False), spec.coord.segment), d)
    (d / "modelspec.json").write_text(json.dumps({"spec": spec.model_dump(), "sources": {}, "stats": {}}), encoding="utf-8")
    return d


@pytest.fixture
def cfg(tmp_path, monkeypatch, ref_dir):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    c = dataclasses.replace(load_config(env_file=tmp_path / "absent.env"), repo_root=tmp_path)
    model = c.derived_dir / "ds" / "model"
    model.mkdir(parents=True)
    (model / "modelspec.json").write_text((ref_dir / "modelspec.json").read_text(encoding="utf-8"), encoding="utf-8")
    return c


def _job(cfg, job_id, code, ref_dir, passed):
    """에이전트 잡 산출 흉내 — 그 섹션 GLB 와 score.json·build.json 만 있으면 된다."""
    d = cfg.derived_dir / "ds" / "model" / "agent" / job_id
    (d / "agent").mkdir(parents=True)
    (d / "sections" / "P4P5").mkdir(parents=True)
    src = ref_dir / "sections" / "P4P5" / f"{code}.glb"
    (d / "sections" / "P4P5" / f"{code}.glb").write_bytes(src.read_bytes())
    (d / "agent" / "score.json").write_text(json.dumps({"summary": {"pass": passed, "bbox_dev_max_m": 0.0}}), encoding="utf-8")
    (d / "build.json").write_text(json.dumps({"kind": "agent", "segment": "P4P5",
                                              "sections": [{"code": code, "source": "agent"}]}), encoding="utf-8")
    return d


def test_pick_sources_prefers_passing_agent_output(cfg, ref_dir):
    _job(cfg, "j-fail", "SP04", ref_dir, passed=False)
    _job(cfg, "j-pass", "SP04", ref_dir, passed=True)
    _job(cfg, "j-brg", "BRG", ref_dir, passed=False)
    picked = A.pick_sources(cfg, "ds", ref_dir=ref_dir, segment="P4P5")
    assert set(picked) == set(X.CODES)
    assert picked["SP04"]["source"] == "agent" and picked["SP04"]["job_id"] == "j-pass" and picked["SP04"]["pass"] is True
    assert picked["BRG"]["source"] == "builder"          # 통과분이 없으면 정답 빌더
    assert picked["BOX"]["source"] == "builder"


def test_run_assemble_writes_build_and_verification(cfg, ref_dir):
    _job(cfg, "j-pass", "SP04", ref_dir, passed=True)
    out = cfg.derived_dir / "ds" / "model" / "agent-all"
    r = A.run_assemble(cfg, "ds", out_dir=out, ref_dir=ref_dir, publish=False, do_render=False)
    assert r["sections"]["SP04"]["source"] == "agent" and r["selfcheck"]["fail"] == 0 and r["measure"]["FAIL"] == 0
    assert r["agent_sections"] == 1
    build = json.loads((out / "build.json").read_text(encoding="utf-8"))
    assert build["kind"] == "agent"
    assert {s["code"]: s["source"] for s in build["sections"]}["SP04"] == "agent"
    assert sum(1 for s in build["sections"] if s["source"] == "builder") == 9
    assert (out / "AB1_P4P5.glb").is_file() and (out / "selfcheck.json").is_file() and (out / "measure.json").is_file()
