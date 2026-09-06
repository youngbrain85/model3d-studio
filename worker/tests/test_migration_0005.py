"""0005_builds — 빌드·섹션·승인 표, RLS, 트리거, Storage 버킷이 회귀로 사라지지 않게 고정한다."""

import re

import pytest

from m3d.config import REPO_ROOT
from m3d.db import discover_migrations


@pytest.fixture
def norm() -> str:
    path = REPO_ROOT / "supabase" / "migrations" / "0005_builds.sql"
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_discovered_after_0004():
    versions = [m.version for m in discover_migrations(REPO_ROOT / "supabase" / "migrations")]
    assert versions[:5] == ["0001_init", "0002_convert", "0003_readings", "0004_decisions", "0005_builds"]


def test_tables_columns_and_constraints(norm):
    assert "create table builds (" in norm and "unique (project_id, version)" in norm
    assert "kind text not null check (kind in ('pilot','full'))" in norm
    assert "status text not null default '대기' check (status in ('대기','승인','반려'))" in norm
    assert "create table build_sections (" in norm and "unique (build_id, section_key)" in norm
    assert "references builds(id) on delete cascade" in norm
    assert "create table approvals (" in norm
    assert "section_id uuid references build_sections(id) on delete cascade" in norm
    assert "user_id uuid not null default auth.uid()" in norm
    assert "verdict text not null check (verdict in ('승인','반려'))" in norm


def test_rls_read_all_and_own_insert_only(norm):
    for t in ("builds", "build_sections", "approvals"):
        assert f"alter table {t} enable row level security" in norm
        assert f'create policy "authenticated read" on {t} for select to authenticated using (true)' in norm
    assert "for insert to authenticated with check (user_id = auth.uid())" in norm
    assert norm.count("for insert") == 1 and "for update" not in norm and "for delete" not in norm
    assert "to anon" not in norm


def test_trigger_applies_status(norm):
    assert "create function apply_approval() returns trigger" in norm and "security definer" in norm
    assert "if new.section_id is null then update builds set status = new.verdict where id = new.build_id;" in norm
    assert "else update build_sections set status = new.verdict where id = new.section_id;" in norm
    assert "create trigger approvals_apply after insert on approvals" in norm


def test_private_bucket_models(norm):
    assert "insert into storage.buckets (id, name, public) values ('models', 'models', false)" in norm
    assert "on storage.objects for select to authenticated using (bucket_id = 'models')" in norm
