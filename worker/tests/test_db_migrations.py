"""마이그레이션 러너의 순수 로직 — DB 없이 검증한다.

핵심 규칙: 이미 적용된 마이그레이션 파일이 나중에 수정되면 조용히 넘어가지 않는다.
"""

import pytest

from m3d.db import MigrationError, discover_migrations, pending_migrations


def _write(directory, name, body):
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def test_discover_sorts_by_version(tmp_path):
    _write(tmp_path, "0002_more.sql", "select 2;")
    _write(tmp_path, "0001_init.sql", "select 1;")
    versions = [m.version for m in discover_migrations(tmp_path)]
    assert versions == ["0001_init", "0002_more"]


def test_discover_raises_on_empty_dir(tmp_path):
    with pytest.raises(MigrationError, match="마이그레이션이 없습니다"):
        discover_migrations(tmp_path)


def test_discover_records_file_hash(tmp_path):
    _write(tmp_path, "0001_init.sql", "select 1;")
    migration = discover_migrations(tmp_path)[0]
    assert len(migration.sha256) == 64


def test_all_pending_when_nothing_applied(tmp_path):
    _write(tmp_path, "0001_init.sql", "select 1;")
    _write(tmp_path, "0002_more.sql", "select 2;")
    available = discover_migrations(tmp_path)
    assert [m.version for m in pending_migrations(available, {})] == ["0001_init", "0002_more"]


def test_applied_versions_are_skipped(tmp_path):
    _write(tmp_path, "0001_init.sql", "select 1;")
    _write(tmp_path, "0002_more.sql", "select 2;")
    available = discover_migrations(tmp_path)
    applied = {available[0].version: available[0].sha256}
    assert [m.version for m in pending_migrations(available, applied)] == ["0002_more"]


def test_modified_applied_migration_raises(tmp_path):
    """적용 후 수정된 마이그레이션을 조용히 무시하면 스키마가 코드와 어긋난다."""
    _write(tmp_path, "0001_init.sql", "select 1;")
    available = discover_migrations(tmp_path)
    applied = {"0001_init": "0" * 64}
    with pytest.raises(MigrationError, match="파일이 그 뒤 수정"):
        pending_migrations(available, applied)


def test_nothing_pending_when_all_applied(tmp_path):
    _write(tmp_path, "0001_init.sql", "select 1;")
    available = discover_migrations(tmp_path)
    applied = {m.version: m.sha256 for m in available}
    assert pending_migrations(available, applied) == []
