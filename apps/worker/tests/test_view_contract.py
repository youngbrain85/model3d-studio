"""뷰 계약 수학 — 규칙 §7. TS 구현과 **같은 픽스처**로 교차 검증한다."""

from __future__ import annotations

import json
from typing import Any

import pytest

from model3d_worker.contracts.models import ViewContract
from model3d_worker.contracts.schemas import fixture_dir
from model3d_worker.contracts.view_contract import (
    pixel_to_view,
    roundtrip_check,
    validate_axes,
    view_to_pixel,
    view_to_world,
    world_to_view,
)

_FIXTURE: dict[str, Any] = json.loads(
    (fixture_dir() / "view_contract.cases.json").read_text(encoding="utf-8")
)
_CASES: list[dict[str, Any]] = _FIXTURE["cases"]
_TOL = _FIXTURE["tolerance"]


def _vc(case: dict[str, Any]) -> ViewContract:
    return ViewContract.model_validate(case["contract"])


@pytest.mark.parametrize("case", _CASES, ids=lambda c: str(c["name"]))
def test_axes(case: dict[str, Any]) -> None:
    assert validate_axes(_vc(case)).ok is case["axes_ok"]


@pytest.mark.parametrize("case", _CASES, ids=lambda c: str(c["name"]))
def test_forward(case: dict[str, Any]) -> None:
    vc = _vc(case)
    for f in case["forward"]:
        got = view_to_world(vc, f["u"], f["v"])
        assert got == pytest.approx(tuple(f["world"]), abs=_TOL)


@pytest.mark.parametrize("case", _CASES, ids=lambda c: str(c["name"]))
def test_inverse(case: dict[str, Any]) -> None:
    vc = _vc(case)
    for inv in case["inverse"]:
        got = world_to_view(vc, tuple(inv["world"]))
        assert got.u == pytest.approx(inv["u"], abs=_TOL)
        assert got.v == pytest.approx(inv["v"], abs=_TOL)
        assert got.off_plane == pytest.approx(inv["off_plane"], abs=_TOL)
        assert got.in_extent is inv["in_extent"]


@pytest.mark.parametrize("case", _CASES, ids=lambda c: str(c["name"]))
def test_roundtrip_verdict(case: dict[str, Any]) -> None:
    assert roundtrip_check(_vc(case)).result == case["roundtrip_result"]


@pytest.mark.parametrize(
    "case", [c for c in _CASES if c.get("pixel")], ids=lambda c: str(c["name"])
)
def test_pixel_mapping(case: dict[str, Any]) -> None:
    vc = _vc(case)
    for p in case["pixel"]:
        px = view_to_pixel(vc, p["u"], p["v"])
        assert px is not None
        assert px == pytest.approx((p["px"], p["py"]), abs=_TOL)

        back = pixel_to_view(vc, p["px"], p["py"])
        assert back is not None
        assert back == pytest.approx((p["u"], p["v"]), abs=_TOL)


def test_pixel_mapping_absent() -> None:
    vc = _vc(_CASES[0])
    assert view_to_pixel(vc, 1.0, 1.0) is None
    assert pixel_to_view(vc, 1.0, 1.0) is None


def test_extent_boundary_tolerates_float_error() -> None:
    """회전 축에서 u = 10 이 10.000000000000002 가 되어도 안쪽으로 봐야 한다."""
    case = next(c for c in _CASES if "45" in c["name"])
    vc = _vc(case)
    corner = view_to_world(vc, vc.u_extent, vc.v_extent)
    assert world_to_view(vc, corner).in_extent is True

    outside = view_to_world(vc, vc.u_extent + 1e-3, 0.0)
    assert world_to_view(vc, outside).in_extent is False
