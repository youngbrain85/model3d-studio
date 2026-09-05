"""m3d publish — 크롭 PNG 를 비공개 Storage 버킷에 올리고 assets.storage_path 를 채운다."""

import dataclasses

import pytest

from m3d.config import load_config
from m3d.reading import publish
from m3d.samples.manifest import sha256_file

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class FakeDb:
    def __init__(self, rows=()):
        self.rows = list(rows)          # (amb_id, crop_rel_path, assets.sha256, assets.storage_path)
        self.sql = []
        self.committed = False


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self._rows = []

    def execute(self, sql, params=None):
        s = " ".join(sql.split())
        self.db.sql.append((s, params))
        self._rows = []
        if s.startswith("select id from projects"):
            self._rows = [("proj-1",)]
        elif s.startswith("select a.id, a.crop_rel_path"):
            self._rows = list(self.db.rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, db):
        self.db = db

    def cursor(self):
        return FakeCursor(self.db)

    def commit(self):
        self.db.committed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://fake/none")
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-test-key")
    cfg = load_config(env_file=tmp_path / "absent.env")
    return dataclasses.replace(cfg, repo_root=tmp_path)


def _crop(cfg, amb_id):
    rel = f"data/derived/ds/crops/{amb_id}.png"
    path = cfg.repo_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG)
    return rel, sha256_file(path)


def _patch(monkeypatch, db, status=200):
    calls = []

    def fake_upload(url, headers, data):
        calls.append((url, headers, data))
        return status, "{}"

    monkeypatch.setattr(publish.psycopg, "connect", lambda *a, **k: FakeConn(db))
    monkeypatch.setattr(publish, "_upload", fake_upload)
    return calls


def test_uploads_with_service_key_headers_and_updates_storage_path(cfg, monkeypatch):
    rel, sha = _crop(cfg, "amb-1")
    db = FakeDb(rows=[("amb-1", rel, sha, None)])
    calls = _patch(monkeypatch, db)
    r = publish.run_publish(cfg, "ds")
    assert r == {"uploaded": 1, "skipped": 0, "failures": [], "total": 1}
    url, headers, data = calls[0]
    assert url == "https://fake.supabase.co/storage/v1/object/crops/ds/amb-1.png"
    assert headers["Authorization"] == "Bearer service-test-key"
    assert headers["apikey"] == "service-test-key"
    assert headers["x-upsert"] == "true" and headers["Content-Type"] == "image/png"
    assert data == PNG
    upd = next((s, p) for s, p in db.sql if s.startswith("update assets set storage_path"))
    assert upd[1] == ("crops/ds/amb-1.png", "proj-1", rel)
    assert db.committed


def test_skips_when_already_published_with_same_sha(cfg, monkeypatch):
    rel, sha = _crop(cfg, "amb-1")
    db = FakeDb(rows=[("amb-1", rel, sha, "crops/ds/amb-1.png")])
    calls = _patch(monkeypatch, db)
    r = publish.run_publish(cfg, "ds")
    assert r["skipped"] == 1 and r["uploaded"] == 0 and calls == []


def test_force_reuploads_even_if_published(cfg, monkeypatch):
    rel, sha = _crop(cfg, "amb-1")
    db = FakeDb(rows=[("amb-1", rel, sha, "crops/ds/amb-1.png")])
    calls = _patch(monkeypatch, db)
    r = publish.run_publish(cfg, "ds", force=True)
    assert r["uploaded"] == 1 and len(calls) == 1


def test_http_error_counts_as_failure_without_db_update(cfg, monkeypatch):
    rel, sha = _crop(cfg, "amb-1")
    db = FakeDb(rows=[("amb-1", rel, sha, None)])
    _patch(monkeypatch, db, status=403)
    r = publish.run_publish(cfg, "ds")
    assert r["uploaded"] == 0 and len(r["failures"]) == 1 and "HTTP 403" in r["failures"][0][1]
    assert not any(s.startswith("update assets") for s, _ in db.sql)


def test_missing_file_counts_as_failure(cfg, monkeypatch):
    db = FakeDb(rows=[("amb-1", "data/derived/ds/crops/amb-1.png", "0" * 64, None)])
    calls = _patch(monkeypatch, db)
    r = publish.run_publish(cfg, "ds")
    assert calls == [] and r["failures"] == [("amb-1", "크롭 파일 없음 — crops 먼저")]


def test_requires_url_and_service_key(cfg, monkeypatch):
    monkeypatch.setattr(publish.psycopg, "connect", lambda *a, **k: FakeConn(FakeDb()))
    bad = dataclasses.replace(cfg, supabase_service_key=None)
    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        publish.run_publish(bad, "ds")
