"""seed 행 생성 — DB 없이 '무엇을 넣을지' 를 검증한다."""

import pytest

from m3d.samples.collect import DATASET, manifest_path
from m3d.samples.manifest import load_manifest
from m3d.samples.source_manifest import parse_source_manifest
from m3d.seed.ab1_p4p5 import COORD_SYSTEM, build_rows
from m3d.config import load_config


@pytest.fixture
def payload(fixtures_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    cfg = load_config(env_file=tmp_path / "absent.env")
    manifest = load_manifest(manifest_path(cfg))
    sheets = parse_source_manifest(fixtures_dir / "_manifest.txt")
    return build_rows(manifest, sheets)


def test_counts(payload):
    """설계서 §9-5 의 기대값 — projects 1 · sheets 50 · pages 61 · assets 112."""
    assert len(payload.sheets) == 50
    assert len(payload.pages) == 61
    assert len(payload.assets) == 112


def test_project_slug_and_coord_system(payload):
    assert payload.project.slug == DATASET
    assert payload.project.coord_system == COORD_SYSTEM
    assert payload.project.coord_system["unit"] == "m"
    assert payload.project.coord_system["up"] == "Y"


def test_project_records_known_correction(payload):
    """패키지 README 의 P4 STA 오기를 가정·정정 메모로 남긴다 (설계서 §6-4)."""
    assert len(payload.project.coord_assumptions) == 1
    assert "3+665.45" in payload.project.coord_assumptions[0]


def test_all_sheets_are_unverified(payload):
    """M0 는 내용 유래 값을 채우지 않는다 — M1 [3] 의 시험 문제 (설계서 §6-3)."""
    assert all(s.catalog_status == "unverified" for s in payload.sheets)


def test_sheet_grade_split(payload):
    assert sum(1 for s in payload.sheets if s.grade == "핵심") == 43
    assert sum(1 for s in payload.sheets if s.grade == "참고") == 7


def test_page_count_sum_matches_pages(payload):
    assert sum(s.page_count for s in payload.sheets) == len(payload.pages)


def test_pages_are_one_based_per_sheet(payload):
    by_ord: dict[str, list[int]] = {}
    for page in payload.pages:
        by_ord.setdefault(page.ord, []).append(page.page_no)
    assert len(by_ord) == 50
    for ord_, page_nos in by_ord.items():
        assert sorted(page_nos) == list(range(1, len(page_nos) + 1)), ord_


def test_asset_kind_counts(payload):
    counts: dict[str, int] = {}
    for asset in payload.assets:
        counts[asset.kind] = counts.get(asset.kind, 0) + 1
    assert counts == {"dxf": 50, "png": 61, "pdf": 1}


def test_dxf_assets_link_to_sheet_only(payload):
    dxf = [a for a in payload.assets if a.kind == "dxf"]
    assert all(a.ord is not None and a.page_no is None for a in dxf)


def test_png_assets_link_to_sheet_and_page(payload):
    png = [a for a in payload.assets if a.kind == "png"]
    assert all(a.ord is not None and a.page_no is not None for a in png)


def test_pdf_asset_links_to_project_only(payload):
    pdf = [a for a in payload.assets if a.kind == "pdf"]
    assert len(pdf) == 1
    assert pdf[0].ord is None and pdf[0].page_no is None


def test_asset_roles(payload):
    for asset in payload.assets:
        expected = "derived" if asset.kind == "png" else "source"
        assert asset.role == expected, asset.rel_path


def test_every_asset_ord_exists_in_sheets(payload):
    sheet_ords = {s.ord for s in payload.sheets}
    for asset in payload.assets:
        if asset.ord is not None:
            assert asset.ord in sheet_ords, asset.rel_path
