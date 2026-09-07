"""회귀 검증 (M8 D6) — 기존 에이전트 산출에 새 규칙을 돌려 혼동표를 낸다. LLM·업로드 없음."""

import dataclasses
import json

import pytest

from m3d.agent.score import load_named
from m3d.config import load_config
from m3d.model import sections as X
from m3d.model import verify_rule
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


def _job(cfg, job_id, code, ref_dir, shift):
    d = cfg.derived_dir / "ds" / "model" / "agent" / job_id
    (d / "agent").mkdir(parents=True)
    (d / "sections" / "P4P5").mkdir(parents=True)
    named = load_named(ref_dir / "sections" / "P4P5" / f"{code}.glb")
    if shift:
        list(named.values())[0].apply_translation([0, shift, 0])
    Builder(ModelSpec()).export(named, d / "sections" / "P4P5" / f"{code}.glb")
    (d / "build.json").write_text(json.dumps({"kind": "agent", "segment": "P4P5",
                                              "sections": [{"code": code, "source": "agent"}]}), encoding="utf-8")
    (d / "agent" / "score.json").write_text(json.dumps({"summary": {"pass": False}}), encoding="utf-8")


def test_collect_finds_agent_outputs(cfg, ref_dir):
    _job(cfg, "j1", "SP04", ref_dir, 0.0)
    _job(cfg, "j2", "DIA", ref_dir, 0.02)
    got = verify_rule.collect(cfg, "ds")
    assert sorted((g["job_id"], g["code"]) for g in got) == [("j1", "SP04"), ("j2", "DIA")]


def test_matrix_buckets_by_reference_deviation(cfg, ref_dir, tmp_path):
    _job(cfg, "ok", "SP04", ref_dir, 0.0)          # 편차 0 → ≤5mm
    _job(cfg, "mid", "SP04", ref_dir, 0.05)        # 50mm → 5~100mm
    _job(cfg, "big", "SP04", ref_dir, 1.0)         # 1m → ≥100mm
    r = verify_rule.run_rule(cfg, "ds", ref_dir=ref_dir, out_dir=tmp_path)
    m = r["matrix"]
    assert m["≤5mm"]["합격"] == 1 and m["≤5mm"]["불합격"] == 0
    assert m["≥100mm"]["합격"] == 0 and m["≥100mm"]["불합격"] == 1
    assert r["false_pass"] == [] and r["false_fail"] == []


def test_bucket_of_boundaries():
    assert verify_rule.bucket_of(0.0) == "≤5mm" and verify_rule.bucket_of(0.005001) == "≤5mm"
    assert verify_rule.bucket_of(0.02) == "5~100mm"
    assert verify_rule.bucket_of(0.1) == "≥100mm" and verify_rule.bucket_of(None) == "≥100mm"
