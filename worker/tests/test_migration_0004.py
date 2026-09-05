"""0004_decisions — 결정 이력·트리거·Storage 정책이 회귀로 사라지지 않게 고정한다."""

import re

import pytest

from m3d.config import REPO_ROOT
from m3d.db import discover_migrations


@pytest.fixture
def norm() -> str:
    path = REPO_ROOT / "supabase" / "migrations" / "0004_decisions.sql"
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_discovered_in_order():
    versions = [m.version for m in discover_migrations(REPO_ROOT / "supabase" / "migrations")]
    assert versions[:4] == ["0001_init", "0002_convert", "0003_readings", "0004_decisions"]


def test_decisions_table_and_restrict_fk(norm):
    assert "create table decisions (" in norm
    assert "references ambiguities(id) on delete restrict" in norm
    assert "choice_index int not null check (choice_index >= 0)" in norm
    assert "provisional boolean not null default false" in norm
    assert "decided_by uuid not null default auth.uid()" in norm


def test_rls_select_and_own_insert_only(norm):
    assert "alter table decisions enable row level security" in norm
    assert 'create policy "authenticated read" on decisions for select to authenticated using (true)' in norm
    assert "for insert to authenticated with check (decided_by = auth.uid())" in norm
    assert "for update" not in norm and "for delete" not in norm
    assert "to anon" not in norm


def test_trigger_applies_status_and_checks_range(norm):
    assert "create function apply_decision() returns trigger" in norm
    assert "security definer" in norm
    assert "jsonb_array_length(options)" in norm
    assert "case when new.provisional then '잠정' else '결정' end" in norm
    assert "create trigger decisions_apply after insert on decisions" in norm


def test_private_bucket_and_authenticated_read(norm):
    assert "insert into storage.buckets (id, name, public) values ('crops', 'crops', false)" in norm
    assert "on storage.objects for select to authenticated using (bucket_id = 'crops')" in norm
