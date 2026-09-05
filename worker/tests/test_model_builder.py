"""빌더 — 시범(본체·격벽) 빌드·노드 규칙·격벽 체인·수밀·self-check."""

import re

import numpy as np
import pytest

from m3d.model import selfcheck
from m3d.model.builder import Builder
from m3d.model.spec import ModelSpec


@pytest.fixture(scope="module")
def pilot():
    b = Builder(ModelSpec())
    return b, b.build(pilot=True)


def test_profile_functions_match_reference_values():
    b = Builder(ModelSpec())
    assert abs(b.el_road(b.Z_P4) - 24.948) < 1e-9 and abs(b.el_road(b.Z_P5) - 26.600) < 1e-9
    assert abs(b.h_box(b.Z_P4) - 4.0) < 1e-9 and abs(b.h_box((b.Z_P4 + b.Z_P5) / 2) - 2.8) < 1e-9
    assert abs(b.h_box(b.Z_P4 + 7.975) - 3.1) < 1e-9                  # 포물선 중간점
    assert b.t_top(b.Z_P4 + 1.0) == 0.038 and b.t_top(b.Z_P4 + 35.0) == 0.016
    assert b.t_bot(b.Z_P4 + 35.0) == 0.014 and b.t_web(b.Z_P4 + 35.0) == 0.012
    assert len(b.H_CHECK) == 8 and b.H_CHECK[2][1] == pytest.approx(3.1)


def test_pilot_nodes_names_and_chain(pilot):
    b, named = pilot
    assert len(named) == 4 + 26
    assert {"AB1_S5_BOX_TOP", "AB1_S5_BOX_BOT", "AB1_S5_BOX_WEB_R", "AB1_S5_BOX_WEB_L"} <= set(named)
    dia = sorted(n for n in named if re.match(r"^AB1_S5_DIA\d{2}$", n))
    assert dia[0] == "AB1_S5_DIA01" and dia[-1] == "AB1_S5_DIA26"
    for k, name in enumerate(dia):
        zs = np.asarray(named[name].vertices)[:, 2]
        assert np.min(np.abs(zs - (b.Z_P4 + 2.8 * k))) < 0.01       # 판면이 전역 체인 위치 (KB §2-18)


def test_pilot_meshes_colored_and_box_watertight(pilot):
    _b, named = pilot
    for name, m in named.items():
        assert np.asarray(m.visual.face_colors).shape[0] == len(m.faces), name
    for name in ("AB1_S5_BOX_TOP", "AB1_S5_BOX_BOT"):
        assert named[name].volume > 0


def test_pilot_selfcheck_passes(pilot):
    b, named = pilot
    r = selfcheck.run(named, b, pilot=True)
    assert r["fail"] == 0, [c for c in r["checks"] if c["ok"] is False]
    assert r["skipped"] == 5 and r["pass"] >= 12
    labels = {c["label"] for c in r["checks"]}
    assert "격벽 26" in labels and any(l.startswith("내공 H @P4") for l in labels)


def test_spec_changes_propagate_to_geometry():
    spec = ModelSpec()
    spec.diaphragm.spacing = 3.5
    spec.diaphragm.n_cell = 20
    named = Builder(spec).build(pilot=True)
    assert sum(1 for n in named if n.startswith("AB1_S5_DIA")) == 21
