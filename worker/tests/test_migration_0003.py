"""0003_readings — 판독 스키마의 제약이 회귀로 사라지지 않게 고정한다."""

import re

import pytest

from m3d.config import REPO_ROOT
from m3d.db import discover_migrations

TABLES = ("readings", "ambiguities")


@pytest.fixture
def norm() -> str:
    path = REPO_ROOT / "supabase" / "migrations" / "0003_readings.sql"
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_discovered_in_order():
    versions = [m.version for m in discover_migrations(REPO_ROOT / "supabase" / "migrations")]
    assert versions[:3] == ["0001_init", "0002_convert", "0003_readings"]


def test_both_tables_created(norm):
    for t in TABLES:
        assert f"create table {t} (" in norm, t


def test_rls_enabled_and_select_only(norm):
    for t in TABLES:
        assert f"alter table {t} enable row level security" in norm, t
    assert norm.count("for select to authenticated using (true)") == len(TABLES)
    assert "to anon" not in norm


def test_status_domains_pinned(norm):
    assert "check (status in ('확정','추정','검토지적'))" in norm
    assert "check (status in ('대기','결정','잠정'))" in norm


def test_value_raw_and_bbox_not_null(norm):
    """§2 원문 보존 · §4 크롭 좌표 — 둘 다 필수다."""
    assert "value_raw text not null" in norm
    assert "basis_mm_bbox jsonb not null" in norm
    assert "mm_bbox jsonb not null" in norm


def test_options_and_impact_not_null(norm):
    """선택지·모델 영향 없는 ambiguity 는 질문 카드가 될 수 없다 (§4)."""
    assert "options jsonb not null" in norm
    assert "model_impact text not null" in norm


def test_ambiguity_defaults_to_waiting(norm):
    assert "status text not null default '대기'" in norm
