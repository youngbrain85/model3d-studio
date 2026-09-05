"""CLI `read`/`review` 의 DB 단계 예외 격리 + 게이트 동작 (픽스 라운드 1).

실호출 없음 — `reading_sheet.read_sheet`·`reading_region.merge_region`·
`reading_store.*` 를 전부 monkeypatch 로 가짜 처리한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from m3d.cli import app
from m3d.reading import region as reading_region
from m3d.reading import sheet as reading_sheet
from m3d.reading import store as reading_store
from m3d.reading.schema import RegionMergeOut, SheetReadOut
from m3d.reading.sheet import PageRef

runner = CliRunner()


def _page(ord_: str, region: str) -> PageRef:
    return PageRef(ord=ord_, drawing_no="D001", page_no=1, region=region,
                  png=Path("x.png"), text=Path("x.json"))


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    # load_config() 가 SAMPLE_SOURCE_DIR 만 있으면 되게 — DB·API 는 전부 monkeypatch 로 우회한다.
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    # cli._pages_map 이 실제 text JSON 을 읽지 않도록 — 이 파일의 PageRef 는 가짜 경로다.
    monkeypatch.setattr(reading_sheet, "page_paper_mm",
                        lambda cfg, dataset, page: (1000.0, 1000.0))


def _ok_usage(model="claude-sonnet-5"):
    return {"model": model, "in": 100, "out": 50, "cached": False}


def test_db_exception_isolated_still_prints_total_and_exits_1(monkeypatch):
    """[Important 1] replace_region 이 RuntimeError 를 던져도 '합계 비용' 줄이 나오고 exit 1."""
    monkeypatch.setattr(reading_sheet, "list_pages",
                        lambda cfg, dataset, region=None, ord_=None: [_page("B01", "B")])
    monkeypatch.setattr(reading_sheet, "read_sheet",
                        lambda cfg, dataset, page, *, force, cache_only:
                        (SheetReadOut(readings=[], ambiguities=[]), _ok_usage()))
    monkeypatch.setattr(reading_store, "has_review_rows", lambda cfg, dataset, region: False)
    monkeypatch.setattr(reading_region, "merge_region",
                        lambda cfg, dataset, region, sheet_outs, pages, **kw:
                        (RegionMergeOut(readings=[], ambiguities=[], notes=[]), _ok_usage()))

    def _boom(*a, **k):
        raise RuntimeError("연결 끊김")

    monkeypatch.setattr(reading_store, "replace_region", _boom)

    result = runner.invoke(app, ["read", "ds", "--region", "B"])

    assert result.exit_code == 1
    assert "합계 비용" in result.output
    assert "B:db" in result.output and "RuntimeError" in result.output


def test_sheet_filter_skips_db_entirely(monkeypatch):
    """[Important 3-b] --sheet 지정 시 replace_region 을 호출하지 않고 안내 문구를 낸다."""
    monkeypatch.setattr(reading_sheet, "list_pages",
                        lambda cfg, dataset, region=None, ord_=None: [_page("B01", "B")])
    monkeypatch.setattr(reading_sheet, "read_sheet",
                        lambda cfg, dataset, page, *, force, cache_only:
                        (SheetReadOut(readings=[], ambiguities=[]), _ok_usage()))
    calls = []
    monkeypatch.setattr(reading_store, "replace_region",
                        lambda *a, **k: calls.append(1))
    monkeypatch.setattr(reading_region, "merge_region",
                        lambda *a, **k: calls.append(1))

    result = runner.invoke(app, ["read", "ds", "--sheet", "B01"])

    assert result.exit_code == 0
    assert "DB 반영 없음" in result.output
    assert calls == []


def test_page_failure_skips_region_merge_and_db(monkeypatch):
    """[Important 3-b] 계열 내 한 페이지 실패 시 merge_region·replace_region 이 호출되지 않는다."""
    monkeypatch.setattr(reading_sheet, "list_pages",
                        lambda cfg, dataset, region=None, ord_=None:
                        [_page("B01", "B"), _page("B02", "B")])

    def _read_sheet(cfg, dataset, page, *, force, cache_only):
        if page.ord == "B01":
            raise RuntimeError("판독 실패")
        return SheetReadOut(readings=[], ambiguities=[]), _ok_usage()

    monkeypatch.setattr(reading_sheet, "read_sheet", _read_sheet)
    merge_calls, db_calls = [], []
    monkeypatch.setattr(reading_region, "merge_region",
                        lambda *a, **k: merge_calls.append(1))
    monkeypatch.setattr(reading_store, "replace_region",
                        lambda *a, **k: db_calls.append(1))
    monkeypatch.setattr(reading_store, "has_review_rows", lambda cfg, dataset, region: False)

    result = runner.invoke(app, ["read", "ds", "--region", "B"])

    assert result.exit_code == 1
    assert merge_calls == [] and db_calls == []
    assert "시트 실패가 있어 통합" in result.output
    assert "실패 1건" in result.output
