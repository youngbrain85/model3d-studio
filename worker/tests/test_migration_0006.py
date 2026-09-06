"""0006_jobs — 잡 큐·이벤트·RLS, builds.kind agent, build_sections.source 가 회귀로 사라지지 않게 고정한다."""

import re

import pytest

from m3d.config import REPO_ROOT
from m3d.db import discover_migrations


@pytest.fixture
def norm() -> str:
    path = REPO_ROOT / "supabase" / "migrations" / "0006_jobs.sql"
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_discovered_after_0005():
    versions = [m.version for m in discover_migrations(REPO_ROOT / "supabase" / "migrations")]
    assert versions[:6] == ["0001_init", "0002_convert", "0003_readings", "0004_decisions", "0005_builds", "0006_jobs"]


def test_jobs_and_events_tables(norm):
    assert "create table jobs (" in norm
    assert "kind text not null check (kind in ('model-section'))" in norm
    assert "status text not null default 'queued' check (status in ('queued','running','done','failed'))" in norm
    assert "parent_job_id uuid references jobs(id) on delete set null" in norm
    assert "budget_usd numeric(8,2) not null default 5" in norm
    assert "build_id uuid references builds(id) on delete set null" in norm
    assert "user_id uuid not null default auth.uid()" in norm
    assert "create table job_events (" in norm and "level text not null check (level in ('info','warn','error'))" in norm
    assert "references jobs(id) on delete cascade" in norm


def test_rls_select_and_own_insert_only(norm):
    for t in ("jobs", "job_events"):
        assert f"alter table {t} enable row level security" in norm
        assert f'create policy "authenticated read" on {t} for select to authenticated using (true)' in norm
    assert 'create policy "authenticated insert" on jobs for insert to authenticated with check (user_id = auth.uid())' in norm
    assert norm.count("for insert") == 1 and "for update" not in norm and "for delete" not in norm and "to anon" not in norm


def test_builds_kind_agent_and_section_source(norm):
    assert "alter table builds drop constraint builds_kind_check" in norm
    assert "add constraint builds_kind_check check (kind in ('pilot','full','agent'))" in norm
    assert "alter table build_sections add column source text not null default 'builder' check (source in ('builder','agent'))" in norm
