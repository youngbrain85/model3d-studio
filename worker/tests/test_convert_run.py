"""convert 오케스트레이션의 순수 부분 — 경로 명명·작업 계획·회귀 쌍 매핑."""

import pytest

from m3d.config import load_config
from m3d.convert.run import derived_paths, plan_jobs, regression_pairs


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    for key in ("SAMPLE_SOURCE_DIR", "REFERENCE_MODELS_DIR", "SUPABASE_DB_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    return load_config(env_file=tmp_path / "absent.env")


ROWS = [
    # (ord, drawing_no, title, page_count) — DB sheets 행 형태
    ("A02", "C0050301-002", "교량제원및특기사항(2)(접속1교)", 1),
    ("A01", "C0050301-001", "교량제원및특기사항(1)(접속1교)_(6차변경)", 2),
]


def test_derived_paths_uniform_p_suffix(cfg):
    png, text = derived_paths(cfg, "ab1-p4p5", "A02", "C0050301-002", 1)
    assert png.name == "A02_C0050301-002_p1.png"      # 1페이지도 _p1 (파생물 균일 명명)
    assert text.name == "A02_C0050301-002_p1.json"
    assert "data" in png.parts and "derived" in png.parts


def test_plan_jobs_one_per_dxf(cfg):
    jobs = plan_jobs(cfg, ROWS, "ab1-p4p5")
    assert len(jobs) == 2
    by_ord = {j.ord: j for j in jobs}
    assert by_ord["A01"].page_count == 2
    assert by_ord["A01"].dxf_path.endswith("C0050301-001.dxf")


def test_regression_pairs_maps_to_sample_names(cfg):
    """파생 p{n} ↔ 샘플 파일명 규칙(1p 접미 없음 / Np _pN) 매핑."""
    pairs = regression_pairs(cfg, "ab1-p4p5", ROWS)
    names = {(d.name, s.name) for d, s in pairs}
    assert ("A02_C0050301-002_p1.png",
            "A02_C0050301-002_교량제원및특기사항(2)(접속1교).png") in names
    assert ("A01_C0050301-001_p2.png",
            "A01_C0050301-001_교량제원및특기사항(1)(접속1교)_(6차변경)_p2.png") in names
    assert len(pairs) == 3  # 1 + 2 페이지
