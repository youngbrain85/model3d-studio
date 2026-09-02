"""LLM 출력 스키마 — 근거 없는 수치를 API 응답 검증 단계에서 반려한다 (지식베이스 §8)."""

import pytest
from pydantic import ValidationError

from m3d.models import AmbiguityOption
from m3d.reading.schema import (
    FinalReading,
    LlmAmbiguity,
    LlmReading,
    MergedAmbiguity,
    MergedReading,
    RegionMergeOut,
    ReviewFinding,
    ReviewOut,
    SheetReadOut,
)

BBOX = [10.0, 20.0, 30.0, 40.0]


def _r(**kw):
    base = dict(item="슬래브 두께", value_raw="300", unit="mm", page_no=1,
                mm_bbox=BBOX, crosscheck=None, status="확정")
    base.update(kw)
    return LlmReading(**base)


def _a(**kw):
    base = dict(item="두께 해석", page_no=1, mm_bbox=BBOX,
                options=[AmbiguityOption(label="순두께", basis="검산 일치"),
                         AmbiguityOption(label="총두께", basis="표기 위치")],
                model_impact="상면 EL 48mm 차이")
    base.update(kw)
    return LlmAmbiguity(**base)


def _mr(**kw):
    return MergedReading(**{**_r().model_dump(), "ord": "B01", **kw})


def _ma(**kw):
    return MergedAmbiguity(**{**_a().model_dump(), "ord": "B01", **kw})


def test_reading_valid():
    assert _r().status == "확정"


def test_reading_rejects_review_status():
    """검토지적은 3단계가 붙이는 상태 — LLM 판독은 확정/추정만 낸다."""
    with pytest.raises(ValidationError):
        _r(status="검토지적")


def test_reading_rejects_missing_bbox():
    with pytest.raises(ValidationError):
        _r(mm_bbox=[1.0, 2.0, 3.0])


def test_reading_rejects_empty_value():
    with pytest.raises(ValidationError):
        _r(value_raw="")


def test_ambiguity_needs_two_options():
    with pytest.raises(ValidationError):
        _a(options=[AmbiguityOption(label="하나", basis="근거")])


def test_sheet_read_out_allows_empty_lists():
    """판독할 게 없는 시트도 정상 — 빈 결과를 에러로 만들지 않는다."""
    out = SheetReadOut(readings=[], ambiguities=[])
    assert out.readings == [] and out.ambiguities == []


def test_sheet_read_out_roundtrip():
    out = SheetReadOut(readings=[_r()], ambiguities=[_a()])
    again = SheetReadOut.model_validate(out.model_dump())
    assert again.readings[0].item == "슬래브 두께"
    assert again.ambiguities[0].options[1].label == "총두께"


def test_merged_reading_requires_ord():
    """통합 결과가 근거 시트를 잃으면 크롭이 엉뚱한 도면에서 잘린다 (§4-2)."""
    with pytest.raises(ValidationError):
        MergedReading(**_r().model_dump())


def test_region_merge_out_keeps_ord_per_item():
    out = RegionMergeOut(readings=[_mr(ord="B02")], ambiguities=[_ma(ord="B03")], notes=[])
    again = RegionMergeOut.model_validate(out.model_dump())
    assert again.readings[0].ord == "B02" and again.ambiguities[0].ord == "B03"


def test_final_reading_allows_review_status():
    """검토지적은 FinalReading 에서만 허용 — dump→재검증이 깨지지 않는다."""
    f = FinalReading.model_validate({**_mr().model_dump(), "status": "검토지적"})
    assert f.status == "검토지적" and f.ord == "B01"


def test_review_finding_status_change_requires_status():
    """상태변경 판정인데 새 상태가 없으면 반쪽 지적이다."""
    with pytest.raises(ValidationError):
        ReviewFinding(target_item="X", verdict="상태변경", reason="단일 소스", new_status=None)


def test_review_finding_rejects_promotion_to_confirmed():
    """검토는 낮추기만 한다 — '확정' 승격은 스키마가 막는다 (§4-3)."""
    with pytest.raises(ValidationError):
        ReviewFinding(target_item="X", verdict="상태변경", reason="r", new_status="확정")


def test_review_finding_new_ambiguity_requires_payload():
    with pytest.raises(ValidationError):
        ReviewFinding(target_item="X", verdict="신규애매성", reason="상충", new_ambiguity=None)


def test_review_finding_rejection_needs_no_payload():
    f = ReviewFinding(target_item="X", verdict="기각", reason="원문 재확인 결과 정합")
    assert f.new_status is None and f.new_ambiguity is None


def test_review_out_empty_is_valid():
    assert ReviewOut(findings=[]).findings == []
