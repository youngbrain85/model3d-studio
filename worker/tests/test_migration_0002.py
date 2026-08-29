"""0002_convert — assets.kind 확장이 회귀로 사라지지 않게 고정한다."""

import re

import pytest

from m3d.config import REPO_ROOT
from m3d.db import discover_migrations


@pytest.fixture
def sql() -> str:
    path = REPO_ROOT / "supabase" / "migrations" / "0002_convert.sql"
    return path.read_text(encoding="utf-8")


@pytest.fixture
def norm(sql) -> str:
    return re.sub(r"\s+", " ", sql)


def test_discovered_in_order():
    """마이그레이션 러너가 0001 다음에 0002 를 집는다."""
    versions = [m.version for m in discover_migrations(REPO_ROOT / "supabase" / "migrations")]
    assert versions == ["0001_init", "0002_convert"]


def test_drops_then_recreates_kind_check(norm):
    assert "drop constraint assets_kind_check" in norm
    assert "add constraint assets_kind_check" in norm


def test_new_kind_list_includes_text(norm):
    assert "check (kind in ('dxf','pdf','png','photo','text'))" in norm
