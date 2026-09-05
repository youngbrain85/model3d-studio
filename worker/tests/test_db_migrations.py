"""마이그레이션 러너의 순수 로직 — DB 없이 검증한다.

핵심 규칙: 이미 적용된 마이그레이션 파일이 나중에 수정되면 조용히 넘어가지 않는다.
"""

import pytest

from m3d.db import MigrationError, discover_migrations, migration_sha256, pending_migrations


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


def test_migration_sha_ignores_line_endings(tmp_path):
    """CRLF 체크아웃과 LF 워크트리가 같은 파일을 다른 sha 로 보면 db apply 가 오판한다."""
    lf = _write(tmp_path, "0001_a.sql", "create table t (\n  id int\n);\n")
    crlf = tmp_path / "0001_b.sql"
    crlf.write_bytes(b"create table t (\r\n  id int\r\n);\r\n")
    assert migration_sha256(lf) == migration_sha256(crlf)


def test_pending_accepts_legacy_raw_sha_record(tmp_path):
    """정규화 도입 전(M0·M1)에 기록된 바이트 해시도 '수정됨' 으로 오판하지 않는다."""
    crlf = tmp_path / "0001_init.sql"
    crlf.write_bytes(b"select 1;" + bytes([13, 10]))
    (m,) = discover_migrations(tmp_path)
    assert m.sha256 != m.sha256_raw
    assert pending_migrations([m], {"0001_init": m.sha256_raw}) == []
    assert pending_migrations([m], {"0001_init": m.sha256}) == []
    with pytest.raises(MigrationError):
        pending_migrations([m], {"0001_init": "0" * 64})
