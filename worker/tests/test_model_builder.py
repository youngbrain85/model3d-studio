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


# ── 전 부재 빌드 (Task 4) ─────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def full():
    b = Builder(ModelSpec())
    return b, b.build(pilot=False)


def test_full_build_counts_and_names(full):
    _b, named = full

    def cnt(pat):
        return sum(1 for n in named if re.match(pat, n))
    assert cnt(r"^AB1_S5_DIA\d{2}$") == 26
    assert cnt(r"^AB1_S5_FRM\d{2}_(TRW|TRF|BRW|BRF|VSL|VSR)$") == 150
    assert cnt(r"^AB1_S5_RIB_") == 93                                 # 존 모델 스트립 수 (참조 v2 동일)
    assert cnt(r"^AB1_S5_HST_") == 10
    assert cnt(r"^AB1_S5_WG\d{3}[LR]$") == 52 and cnt(r"^AB1_S5_WG\d{3}[LR]_ST$") == 52
    assert cnt(r"^AB1_S5_WG\d{3}[LR]_BR$") == 52
    assert "AB1_S5_WG096R" in named and "AB1_S5_WG121L" in named       # 번호 96~121
    assert cnt(r"^AB1_S5_CS\d{3}[LR]$") == 52
    assert {"AB1_S5_SLAB", "AB1_S5_BARRIER_L", "AB1_S5_BARRIER_R", "AB1_S5_BARRIER_CTR"} <= set(named)
    assert cnt(r"^AB1_S5_SP04_(TF|BF|WEB_R|WEB_L)$") == 4
    assert cnt(r"^AB1_S5_BRG_P[45]_[12]_(SOLE|BODY|MORTAR|BLOCK)$") == 16
    assert 500 <= len(named) <= 700


def test_full_build_watertight_positive_volume(full):
    _b, named = full
    bad = [n for n, m in named.items() if not m.is_watertight or m.volume <= 0]
    assert bad == []


def test_full_selfcheck_all_pass(full):
    b, named = full
    r = selfcheck.run(named, b, pilot=False)
    assert r["fail"] == 0 and r["skipped"] == 0, [c for c in r["checks"] if c["ok"] is not True]
    labels = {c["label"] for c in r["checks"]}
    assert "받침 하면 y P4_1" in labels and "프레임 부재 25×6=150" in labels


def test_full_geometry_anchors(full):
    """WG·CS·방호벽·받침 앵커가 사양 유도값과 맞는지 (참조 v2 상수와 동일 결과)."""
    b, named = full
    s = b.s
    zc = b.dia_z(12)
    cr = b.y_crown(zc)
    wg = np.asarray(named["AB1_S5_WG108R"].vertices)
    assert abs(wg[:, 1].max() - (cr - 0.330 + 0.003)) < 1e-6           # 상플랜지 상면 = 캔틸레버 하면 + 3mm
    assert abs(wg[:, 0].max() - (s.box.x_web + s.wg.length)) < 1e-9     # 선단 x
    cs = np.asarray(named["AB1_S5_CS108R"].vertices)
    assert abs(cs[:, 0].mean() - (s.box.x_web + s.wg.length)) < 1e-9
    ctr = np.asarray(named["AB1_S5_BARRIER_CTR"].vertices)
    assert abs(ctr[:, 0].min() + 4.45) < 1e-9 and abs(ctr[:, 0].max() + 4.0) < 1e-9   # 보도측(−x) 중앙방호벽
    slab = np.asarray(named["AB1_S5_SLAB"].vertices)
    assert abs(slab[:, 0].max() - s.slab.half_width) < 1e-9
    body = np.asarray(named["AB1_S5_BRG_P5_2_BODY"].vertices)
    assert abs(body[:, 1].min() - (s.bearing.el_check["P5"] - s.coord.y_datum)) < 0.01


def test_full_spec_changes_propagate():
    spec = ModelSpec()
    spec.wg.length = 5.0
    spec.slab.walk_width = 2.0
    named = Builder(spec).build(pilot=False)
    cs = np.asarray(named["AB1_S5_CS100R"].vertices)
    assert abs(cs[:, 0].mean() - (spec.box.x_web + 5.0)) < 1e-9
    ctr = np.asarray(named["AB1_S5_BARRIER_CTR"].vertices)
    assert abs(ctr[:, 0].min() + (7.85 - 0.45 - 2.0)) < 1e-9
