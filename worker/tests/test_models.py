"""Pydantic 모델 — 0001_init.sql 의 check 제약을 파이썬 쪽에서도 막는다.

DB 왕복 전에 잘못된 값을 걸러야 seed 실패 원인이 명확해진다.
"""

import pytest
from pydantic import ValidationError

from m3d.models import AssetRow, ProjectRow, SheetPageRow, SheetRow

VALID_SHA = "a" * 64


def test_project_requires_coord_system():
    with pytest.raises(ValidationError):
        ProjectRow(slug="x", name="X")


def test_project_accepts_minimal_valid():
    row = ProjectRow(slug="ab1-p4p5", name="접속1교 P4~P5", coord_system={"up": "Y"})
    assert row.coord_assumptions == []
    assert row.structure is None


def test_sheet_rejects_unknown_grade():
    with pytest.raises(ValidationError):
        SheetRow(
            ord="A01",
            drawing_no_from_filename="C0050301-001",
            title_from_filename="제목",
            grade="중요",
            page_count=1,
        )


def test_sheet_rejects_zero_page_count():
    with pytest.raises(ValidationError):
        SheetRow(
            ord="A01",
            drawing_no_from_filename="C0050301-001",
            title_from_filename="제목",
            grade="참고",
            page_count=0,
        )


def test_sheet_defaults_to_unverified():
    """M0 는 정답을 채우지 않는다 — 그게 M1 의 시험 문제다 (설계서 §6-3)."""
    row = SheetRow(
        ord="A01",
        drawing_no_from_filename="C0050301-001",
        title_from_filename="제목",
        grade="참고",
        page_count=1,
    )
    assert row.catalog_status == "unverified"


def test_sheet_page_rejects_zero_page_no():
    with pytest.raises(ValidationError):
        SheetPageRow(ord="A01", page_no=0)


def test_asset_rejects_bad_sha_length():
    with pytest.raises(ValidationError):
        AssetRow(
            kind="dxf", role="source", rel_path="a", bytes=1, sha256="abc",
        )


def test_asset_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        AssetRow(
            kind="dwg", role="source", rel_path="a", bytes=1, sha256=VALID_SHA,
        )


def test_asset_rejects_unknown_role():
    with pytest.raises(ValidationError):
        AssetRow(
            kind="png", role="golden", rel_path="a", bytes=1, sha256=VALID_SHA,
        )


def test_asset_rejects_zero_bytes():
    with pytest.raises(ValidationError):
        AssetRow(
            kind="png", role="derived", rel_path="a", bytes=0, sha256=VALID_SHA,
        )


def test_asset_accepts_valid():
    row = AssetRow(
        kind="png", role="derived", rel_path="data/samples/x.png",
        bytes=10, sha256=VALID_SHA, ord="A01", page_no=1,
    )
    assert row.ord == "A01" and row.page_no == 1
