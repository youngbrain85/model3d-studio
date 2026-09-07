"""기하 건전성 (M8 D3) — 스펙과 무관하게 큰 사고를 잡는다: 외곽 이탈·부유 부재·중복 배치."""

import pytest

from m3d.model import sanity
from m3d.model.builder import Builder
from m3d.model.spec import ModelSpec


@pytest.fixture(scope="module")
def spec():
    return ModelSpec()


@pytest.fixture(scope="module")
def named(spec):
    return Builder(spec).build(pilot=False)


def test_reference_model_is_healthy(named, spec):
    r = sanity.run(named, spec)
    assert r["fail"] == 0, [c["label"] + " " + c["detail"] for c in r["checks"] if not c["ok"]]
    assert r["pass"] == 3


def test_node_far_outside_is_caught(named, spec):
    bad = {k: v.copy() for k, v in named.items()}
    bad["AB1_S5_DIA13"].apply_translation([0, 0, 500.0])
    r = sanity.run(bad, spec)
    labels = [c["label"] for c in r["checks"] if not c["ok"]]
    assert "외곽 이탈" in labels and "부유 부재" in labels
    assert "AB1_S5_DIA13" in [n for c in r["checks"] if not c["ok"] for n in c["nodes"]]


def test_duplicate_placement_is_caught(named, spec):
    bad = {k: v.copy() for k, v in named.items()}
    bad["AB1_S5_DIA13_DUP"] = bad["AB1_S5_DIA13"].copy()
    r = sanity.run(bad, spec)
    assert "중복 배치" in [c["label"] for c in r["checks"] if not c["ok"]]


def test_envelope_comes_from_spec(spec):
    lo, hi = sanity.envelope(spec)
    assert lo[0] < -spec.slab.half_width and hi[0] > spec.slab.half_width
    assert lo[2] < spec.coord.z_p4 and hi[2] > spec.coord.z_p5
