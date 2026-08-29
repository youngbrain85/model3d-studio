"""collect 계획 — 실제 413MB 복사 없이 '무엇을 어디로' 만 검증한다."""

import pytest

from m3d.config import load_config
from m3d.samples.collect import DATASET, PDF_NAME, plan_files
from m3d.samples.source_manifest import parse_source_manifest


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    for key in ("SAMPLE_SOURCE_DIR", "REFERENCE_MODELS_DIR", "SUPABASE_DB_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    return load_config(env_file=tmp_path / "absent.env")


@pytest.fixture
def planned(cfg, fixtures_dir):
    sheets = parse_source_manifest(fixtures_dir / "_manifest.txt")
    return plan_files(cfg, sheets)


def test_plans_112_files(planned):
    assert len(planned) == 112


def test_kind_counts(planned):
    counts: dict[str, int] = {}
    for item in planned:
        counts[item.kind] = counts.get(item.kind, 0) + 1
    assert counts == {"dxf": 50, "png": 61, "pdf": 1}


def test_roles(planned):
    """DXF·PDF 는 [1] 업로드 입력(source), PNG 는 [2] 변환 산출물(derived)."""
    for item in planned:
        expected = "derived" if item.kind == "png" else "source"
        assert item.role == expected, item.rel_path


def test_rel_paths_unique(planned):
    assert len({item.rel_path for item in planned}) == 112


def test_rel_paths_are_under_dataset_dir(planned):
    prefix = f"data/samples/{DATASET}/"
    assert all(item.rel_path.startswith(prefix) for item in planned)
    assert all("\\" not in item.rel_path for item in planned)


def test_dxf_entries_have_no_page_no(planned):
    dxf = [i for i in planned if i.kind == "dxf"]
    assert len(dxf) == 50
    assert all(i.page_no is None and i.drawing_no is not None for i in dxf)


def test_png_page_numbers_start_at_one_per_sheet(planned):
    pages: dict[str, list[int]] = {}
    for item in planned:
        if item.kind == "png":
            pages.setdefault(item.ord, []).append(item.page_no)
    assert len(pages) == 50
    for ord_, page_nos in pages.items():
        assert page_nos == list(range(1, len(page_nos) + 1)), ord_


def test_pdf_entry_has_no_sheet_linkage(planned):
    pdf = [i for i in planned if i.kind == "pdf"]
    assert len(pdf) == 1
    assert pdf[0].ord is None and pdf[0].drawing_no is None and pdf[0].page_no is None
    assert pdf[0].rel_path == f"data/samples/{DATASET}/pdf/{PDF_NAME}"


def test_sources_point_into_configured_dirs(cfg, planned):
    for item in planned:
        if item.kind == "dxf":
            assert item.source.parent == cfg.dxf_dir
        else:
            assert item.source.parent == cfg.package_dir


def test_source_rel_is_posix_relative(planned):
    assert all(not item.source_rel.startswith("/") for item in planned)
    assert all("\\" not in item.source_rel for item in planned)
