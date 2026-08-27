"""마이그레이션 SQL 구조 — 규칙을 구현한 제약이 실수로 빠지지 않게 고정한다.

DB 없이 텍스트만 본다. 실제 적용 검증은 Task 7 의 `m3d db apply` 가 담당한다.
"""

import re

import pytest

from m3d.config import REPO_ROOT

TABLES = ("projects", "sheets", "sheet_pages", "assets")


@pytest.fixture
def sql() -> str:
    path = REPO_ROOT / "supabase" / "migrations" / "0001_init.sql"
    return path.read_text(encoding="utf-8")


@pytest.fixture
def norm(sql) -> str:
    """공백을 하나로 접은 SQL.

    정렬용 공백은 언제든 바뀔 수 있다. 그때마다 테스트가 깨지면 테스트를 고치는
    습관이 들고, 그 습관이 진짜 제약이 사라진 것도 놓치게 만든다.
    """
    return re.sub(r"\s+", " ", sql)


def test_all_four_tables_created(norm):
    for table in TABLES:
        assert f"create table {table} (" in norm, table


def test_rls_enabled_on_every_table(norm):
    for table in TABLES:
        assert f"alter table {table} enable row level security" in norm, table


def test_one_select_policy_per_table(sql, norm):
    assert sql.count('create policy "authenticated read"') == len(TABLES)
    assert "to authenticated" in norm
    assert "to anon" not in norm, "anon 에게 정책을 주면 RLS 증명이 무너진다"


def test_coord_system_is_not_null(norm):
    """§1 — 전역 좌표계 확정을 스키마가 강제해야 한다."""
    assert "coord_system jsonb not null" in norm


def test_sheets_separates_filename_and_content_sources(norm):
    """§3 — 파일명 유래와 내용 유래를 섞으면 편철 오류를 검출할 수 없다."""
    assert "drawing_no_from_filename text not null" in norm
    assert "drawing_no_from_content text," in norm
    assert "title_from_filename text not null" in norm
    assert "title_from_content text," in norm


def test_catalog_status_defaults_to_unverified(norm):
    assert "catalog_status text not null default 'unverified'" in norm
    for status in ("unverified", "match", "mismatch", "unreadable"):
        assert f"'{status}'" in norm


def test_sheet_pages_keeps_pixel_size(norm):
    """§4 — 질문 크롭이 원본 픽셀 좌표를 쓰므로 필수."""
    assert "width_px int" in norm
    assert "height_px int" in norm


def test_asset_role_and_kind_constraints(norm):
    assert "check (kind in ('dxf','pdf','png','photo'))" in norm
    assert "check (role in ('source','derived'))" in norm


def test_sha256_length_constraint(norm):
    assert "char_length(sha256) = 64" in norm


def test_grade_constraint_uses_korean_values(norm):
    assert "check (grade in ('핵심','참고'))" in norm
