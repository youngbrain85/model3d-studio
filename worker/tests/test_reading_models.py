"""판독 행 모델 — DB 왕복 전에 스키마 위반을 잡는다."""

import pytest
from pydantic import ValidationError

from m3d.models import AmbiguityOption, AmbiguityRow, ReadingRow

BBOX = [10.0, 20.0, 30.0, 40.0]


def _reading(**kw):
    base = dict(region="B", item="슬래브 두께", value_raw="300", unit="mm",
                basis_ord="B01", basis_page_no=1, basis_mm_bbox=BBOX,
                crosscheck=None, status="확정", round=1)
    base.update(kw)
    return ReadingRow(**base)


def _ambiguity(**kw):
    base = dict(item="슬래브 기입두께 해석", basis_ord="B01", basis_page_no=1,
                mm_bbox=BBOX,
                options=[AmbiguityOption(label="콘크리트 순두께", basis="계획고 검산 일치"),
                         AmbiguityOption(label="포장 포함 총두께", basis="표기 위치")],
                model_impact="슬래브 상면 EL 이 48mm 달라진다")
    base.update(kw)
    return AmbiguityRow(**base)


def test_reading_accepts_valid():
    r = _reading()
    assert r.status == "확정" and r.round == 1


def test_reading_rejects_unknown_status():
    with pytest.raises(ValidationError):
        _reading(status="대충맞음")


def test_reading_requires_four_point_bbox():
    with pytest.raises(ValidationError):
        _reading(basis_mm_bbox=[1.0, 2.0])


def test_reading_value_raw_must_be_nonempty():
    """§2 — 근거 없는/빈 수치는 싣지 않는다."""
    with pytest.raises(ValidationError):
        _reading(value_raw="")


def test_ambiguity_accepts_two_options():
    a = _ambiguity()
    assert a.status == "대기" and len(a.options) == 2


def test_ambiguity_rejects_single_option():
    """선택지가 하나면 질문이 아니라 확정이다 (§4: 선택지 2~4)."""
    with pytest.raises(ValidationError):
        _ambiguity(options=[AmbiguityOption(label="하나", basis="근거")])


def test_ambiguity_rejects_five_options():
    with pytest.raises(ValidationError):
        _ambiguity(options=[AmbiguityOption(label=f"안{i}", basis="근거") for i in range(5)])


def test_ambiguity_option_requires_basis():
    """§4 — 각 선택지에 근거를 붙인다."""
    with pytest.raises(ValidationError):
        AmbiguityOption(label="라벨만", basis="")


def test_ambiguity_requires_model_impact():
    with pytest.raises(ValidationError):
        _ambiguity(model_impact="")
