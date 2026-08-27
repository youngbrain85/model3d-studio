"""_manifest.txt 파서 — 카탈로그 정답의 유일한 입구다.

실제 커밋된 fixture(50행)로 회귀를 걸고, 형식 오류는 합성 데이터로 검증한다.
"""

import re

import pytest

from m3d.samples.source_manifest import (
    SourceManifestError,
    SourceSheet,
    dxf_filename,
    parse_source_manifest,
    png_filenames,
)


@pytest.fixture
def sheets(fixtures_dir):
    return parse_source_manifest(fixtures_dir / "_manifest.txt")


def test_parses_50_rows(sheets):
    assert len(sheets) == 50


def test_page_count_sum_matches_png_total(sheets):
    """합계 61 = 실제 PNG 파일 수. 검산 없는 수치는 싣지 않는다 (지식베이스 §2)."""
    assert sum(s.page_count for s in sheets) == 61


def test_grade_split(sheets):
    assert {s.grade for s in sheets} == {"핵심", "참고"}
    assert sum(1 for s in sheets if s.grade == "핵심") == 43
    assert sum(1 for s in sheets if s.grade == "참고") == 7


def test_drawing_numbers_unique_and_well_formed(sheets):
    assert len({s.drawing_no for s in sheets}) == 50
    assert all(re.fullmatch(r"C\d{7}-\d{3}", s.drawing_no) for s in sheets)


def test_ords_unique(sheets):
    assert len({s.ord for s in sheets}) == 50


def test_titles_are_not_empty(sheets):
    assert all(s.title for s in sheets)


def test_png_filenames_single_page_has_no_suffix():
    """설계서 §1-4 — 1페이지 시트는 _p1 접미사가 붙지 않는다."""
    sheet = SourceSheet(
        ord="A02",
        grade="참고",
        drawing_no="C0050301-002",
        title="교량제원및특기사항(2)(접속1교)",
        page_count=1,
    )
    assert png_filenames(sheet) == ["A02_C0050301-002_교량제원및특기사항(2)(접속1교).png"]


def test_png_filenames_multi_page_uses_p_suffix():
    sheet = SourceSheet(
        ord="A01",
        grade="참고",
        drawing_no="C0050301-001",
        title="교량제원및특기사항(1)(접속1교)_(6차변경)",
        page_count=2,
    )
    assert png_filenames(sheet) == [
        "A01_C0050301-001_교량제원및특기사항(1)(접속1교)_(6차변경)_p1.png",
        "A01_C0050301-001_교량제원및특기사항(1)(접속1교)_(6차변경)_p2.png",
    ]


def test_png_filename_total_is_61(sheets):
    assert sum(len(png_filenames(s)) for s in sheets) == 61


def test_dxf_filename():
    sheet = SourceSheet(
        ord="C01",
        grade="핵심",
        drawing_no="C0050304-030",
        title="강상형일반도(5)(접속1교)",
        page_count=1,
    )
    assert dxf_filename(sheet) == "C0050304-030.dxf"


def _write(tmp_path, line):
    path = tmp_path / "_manifest.txt"
    path.write_text(line + "\n", encoding="utf-8")
    return path


def test_wrong_field_count_raises(tmp_path):
    path = _write(tmp_path, "A01\t참고\tC0050301-001_제목")
    with pytest.raises(SourceManifestError, match="탭 4필드"):
        parse_source_manifest(path)


def test_unknown_grade_raises(tmp_path):
    path = _write(tmp_path, "A01\t중요\tC0050301-001_제목\t1p")
    with pytest.raises(SourceManifestError, match="등급"):
        parse_source_manifest(path)


def test_bad_drawing_no_raises(tmp_path):
    path = _write(tmp_path, "A01\t참고\tX999_제목\t1p")
    with pytest.raises(SourceManifestError, match="도면번호"):
        parse_source_manifest(path)


def test_bad_page_format_raises(tmp_path):
    path = _write(tmp_path, "A01\t참고\tC0050301-001_제목\t2쪽")
    with pytest.raises(SourceManifestError, match="페이지수"):
        parse_source_manifest(path)


def test_blank_lines_are_skipped(tmp_path):
    path = tmp_path / "_manifest.txt"
    path.write_text("\nA01\t참고\tC0050301-001_제목\t1p\n\n", encoding="utf-8")
    assert len(parse_source_manifest(path)) == 1
