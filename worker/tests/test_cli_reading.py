"""CLI `read`/`review` 의 DB 단계 예외 격리 + 게이트 동작 (픽스 라운드 1).

실호출 없음 — `reading_sheet.read_sheet`·`reading_region.merge_region`·
`reading_store.*` 를 전부 monkeypatch 로 가짜 처리한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from m3d import cli as cli_mod
from m3d.cli import app
from m3d.reading import region as reading_region
from m3d.reading import sheet as reading_sheet
from m3d.reading import store as reading_store
from m3d.reading.schema import RegionMergeOut, ReviewOut, SheetReadOut
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


def _one_page_b01(monkeypatch):
    """B 계열 1페이지가 캐시로 판독되는 상태 — 계열 단계만 보는 테스트의 공통 준비."""
    monkeypatch.setattr(reading_sheet, "list_pages",
                        lambda cfg, dataset, region=None, ord_=None: [_page("B01", "B")])
    monkeypatch.setattr(reading_sheet, "read_sheet",
                        lambda cfg, dataset, page, *, force, cache_only:
                        (SheetReadOut(readings=[], ambiguities=[]), _ok_usage()))


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


# ---------------------------------------------------------------- F3: 계열 = 단일 문자


@pytest.mark.parametrize("command", ["read", "review"])
@pytest.mark.parametrize("bad", ["C1", "b", "AB"])
def test_region_option_rejects_non_single_uppercase(command, bad):
    """[F3] 계열 키는 ord 첫 글자 한 글자다 — 'C1' 같은 접두어를 조용히 받으면
    빈 결과를 '대상 없음' 으로 오해하게 된다."""
    result = runner.invoke(app, [command, "ds", "--region", bad])

    assert result.exit_code != 0
    assert "계열" in result.output


# ------------------------------------------------- F4: review 경로 · has_review_rows 분기


def test_review_applies_findings_then_writes_rows_and_log(monkeypatch):
    """[F4] review 는 apply_findings → build_rows(round 3) → replace_region →
    _save_review 순서로, 각 단계의 산출물을 그대로 다음 단계에 넘긴다."""
    _one_page_b01(monkeypatch)
    merged = RegionMergeOut(readings=[], ambiguities=[], notes=[])
    reviewed = ReviewOut(findings=[])
    finals, ambs, log = [], [], [{"applied": True}, {"applied": False}]
    order = []

    def _merge(cfg, dataset, region, sheet_outs, pages, **kw):
        order.append(("merge", region, kw["force"], kw["cache_only"]))
        return merged, _ok_usage()

    def _review(cfg, dataset, region, m, pages, **kw):
        order.append(("review", region, m is merged, kw["force"]))
        return reviewed, _ok_usage("claude-fable-5")

    def _apply(readings, ambiguities, findings):
        order.append(("apply", findings is reviewed.findings))
        return finals, ambs, log

    def _build(region, readings, ambiguities, round_no):
        order.append(("build", region, readings is finals, ambiguities is ambs, round_no))
        return ["row-r"], ["row-a"]

    def _replace(cfg, dataset, region, rows_r, rows_a):
        order.append(("replace", region, rows_r, rows_a))
        return {"readings": 1, "ambiguities": 1, "kept": 0, "failed": 0, "protected": 0}

    def _save(cfg, dataset, region, log_arg):
        order.append(("save", region, log_arg is log))
        return Path("review-B.json")

    monkeypatch.setattr(reading_region, "merge_region", _merge)
    monkeypatch.setattr(reading_region, "review_region", _review)
    monkeypatch.setattr(reading_region, "apply_findings", _apply)
    monkeypatch.setattr(reading_store, "build_rows", _build)
    monkeypatch.setattr(reading_store, "replace_region", _replace)
    monkeypatch.setattr(cli_mod, "_save_review", _save)

    result = runner.invoke(app, ["review", "ds", "--region", "B", "--cache-only"])

    assert result.exit_code == 0, result.output
    assert [x[0] for x in order] == ["merge", "review", "apply", "build", "replace", "save"]
    # 통합은 캐시 고정(force 는 검토 호출에만), 검토 반영은 round 3 로 기록된다
    assert order[0] == ("merge", "B", False, True)
    assert order[1] == ("review", "B", True, False)
    assert order[2] == ("apply", True)
    assert order[3] == ("build", "B", True, True, 3)
    assert order[4] == ("replace", "B", ["row-r"], ["row-a"])
    assert order[5] == ("save", "B", True)
    assert "지적 2건(반영 1, 기각 0, 미종결 0)" in result.output
    assert "review-B.json" in result.output


def test_review_db_exception_isolated_still_prints_total_and_exits_1(monkeypatch):
    """[F4] review 의 DB 단계 예외도 계열 단위로 격리되고 합계 줄이 나온다."""
    _one_page_b01(monkeypatch)
    monkeypatch.setattr(reading_region, "merge_region",
                        lambda cfg, dataset, region, sheet_outs, pages, **kw:
                        (RegionMergeOut(readings=[], ambiguities=[], notes=[]), _ok_usage()))
    monkeypatch.setattr(reading_region, "review_region",
                        lambda cfg, dataset, region, merged, pages, **kw:
                        (ReviewOut(findings=[]), _ok_usage("claude-fable-5")))
    saved = []
    monkeypatch.setattr(cli_mod, "_save_review", lambda *a, **k: saved.append(1))

    def _boom(*a, **k):
        raise RuntimeError("연결 끊김")

    monkeypatch.setattr(reading_store, "replace_region", _boom)

    result = runner.invoke(app, ["review", "ds", "--region", "B", "--cache-only"])

    assert result.exit_code == 1
    assert "합계 비용" in result.output
    assert "B:db" in result.output and "RuntimeError" in result.output
    assert saved == []          # DB 가 실패했으면 검토 기록도 남기지 않는다


def test_read_keeps_existing_review_rows_and_skips_db(monkeypatch):
    """[F4] 검토(round 3) 결과가 있는 계열은 read 가 덮어쓰지 않는다."""
    _one_page_b01(monkeypatch)
    monkeypatch.setattr(reading_store, "has_review_rows", lambda cfg, dataset, region: True)
    merge_calls, db_calls = [], []
    monkeypatch.setattr(reading_region, "merge_region",
                        lambda *a, **k: merge_calls.append(1))
    monkeypatch.setattr(reading_store, "replace_region",
                        lambda *a, **k: db_calls.append(1))

    result = runner.invoke(app, ["read", "ds", "--region", "B"])

    assert result.exit_code == 0
    assert "검토 결과 보존" in result.output
    assert merge_calls == [] and db_calls == []


def test_read_force_overwrites_review_rows(monkeypatch):
    """[F4] --force 는 그 보존 게이트를 명시적으로 넘는다."""
    _one_page_b01(monkeypatch)

    def _has_review(cfg, dataset, region):
        raise AssertionError("--force 면 게이트를 묻지 않는다")

    monkeypatch.setattr(reading_store, "has_review_rows", _has_review)
    monkeypatch.setattr(reading_region, "merge_region",
                        lambda cfg, dataset, region, sheet_outs, pages, **kw:
                        (RegionMergeOut(readings=[], ambiguities=[], notes=[]), _ok_usage()))
    monkeypatch.setattr(reading_store, "build_rows",
                        lambda region, readings, ambiguities, round_no: ([], []))
    db_calls = []

    def _replace(cfg, dataset, region, rows_r, rows_a):
        db_calls.append(region)
        return {"readings": 0, "ambiguities": 0, "kept": 0, "failed": 0, "protected": 0}

    monkeypatch.setattr(reading_store, "replace_region", _replace)

    result = runner.invoke(app, ["read", "ds", "--region", "B", "--force"])

    assert result.exit_code == 0, result.output
    assert db_calls == ["B"]
    assert "검토 결과 보존" not in result.output


# ------------------------------------------- acceptance §3·§4: 조용한 유실을 출력에 드러낸다


def test_review_summary_counts_rejected_and_unresolved_and_names_unresolved(monkeypatch):
    """[acceptance §3] 지적 N건(반영 M) 만으로는 기각과 미종결(대상 없음)이 구분되지
    않아 F 계열 미종결 2건이 CLI 출력에 드러나지 않았다. 종결 상태별 수와 미종결
    대상명을 출력한다."""
    _one_page_b01(monkeypatch)
    log = [
        {"target_item": "두께", "verdict": "상태변경", "reason": "r", "applied": True,
         "note": "", "resolution": "반영"},
        {"target_item": "폭", "verdict": "기각", "reason": "r", "applied": False,
         "note": "", "resolution": "기각"},
        {"target_item": "받침 종류(P1/P4/P7/P8) 및 A/B(825/825, 845/845)",
         "verdict": "상태변경", "reason": "r", "applied": False,
         "note": "대상 없음 — 항목명이 통합 결과와 다르다", "resolution": "미종결"},
    ]
    monkeypatch.setattr(reading_region, "merge_region",
                        lambda cfg, dataset, region, sheet_outs, pages, **kw:
                        (RegionMergeOut(readings=[], ambiguities=[], notes=[]), _ok_usage()))
    monkeypatch.setattr(reading_region, "review_region",
                        lambda cfg, dataset, region, merged, pages, **kw:
                        (ReviewOut(findings=[]), _ok_usage("claude-fable-5")))
    monkeypatch.setattr(reading_region, "apply_findings",
                        lambda readings, ambiguities, findings: ([], [], log))
    monkeypatch.setattr(reading_store, "replace_region",
                        lambda cfg, dataset, region, rows_r, rows_a:
                        {"readings": 0, "ambiguities": 0, "kept": 0, "failed": 0,
                         "protected": 0, "failed_rows": []})
    monkeypatch.setattr(cli_mod, "_save_review", lambda *a, **k: Path("review-B.json"))

    result = runner.invoke(app, ["review", "ds", "--region", "B", "--cache-only"])

    assert result.exit_code == 0, result.output
    assert "지적 3건(반영 1, 기각 1, 미종결 1)" in result.output
    assert "받침 종류(P1/P4/P7/P8) 및 A/B(825/825, 845/845)" in result.output


def test_read_prints_each_unresolved_fk_row_with_reason(monkeypatch):
    """[acceptance §4] replace_region 이 버린 행(A03 p2 ambiguity 유실 사례)은
    미해석 1 숫자만이 아니라 어느 행이 왜 버려졌는지 줄로 나온다."""
    _one_page_b01(monkeypatch)
    monkeypatch.setattr(reading_store, "has_review_rows", lambda cfg, dataset, region: False)
    monkeypatch.setattr(reading_region, "merge_region",
                        lambda cfg, dataset, region, sheet_outs, pages, **kw:
                        (RegionMergeOut(readings=[], ambiguities=[], notes=[]), _ok_usage()))
    monkeypatch.setattr(reading_store, "replace_region",
                        lambda cfg, dataset, region, rows_r, rows_a:
                        {"readings": 5, "ambiguities": 2, "kept": 0, "failed": 1,
                         "protected": 0,
                         "failed_rows": [{"kind": "ambiguity", "item": "경간구성 표기 방식 차이",
                                          "ord": "A03", "page_no": 2, "reason": "페이지 없음"}]})

    result = runner.invoke(app, ["read", "ds", "--region", "B"])

    assert result.exit_code == 0, result.output
    assert "미해석 1" in result.output
    assert "A03 p2" in result.output and "페이지 없음" in result.output
    assert "경간구성 표기 방식 차이" in result.output
