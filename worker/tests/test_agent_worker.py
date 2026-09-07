"""워커 데몬 — claim/finish SQL·상태 전이·이벤트 (가짜 DB)."""

import dataclasses
import json

import pytest

from m3d.agent import worker as W
from m3d.config import load_config


class FakeCursor:
    def __init__(self, db):
        self.db, self._rows = db, []

    def execute(self, sql, params=None):
        s = " ".join(sql.split())
        self.db.sql.append((s, params))
        self._rows = []
        if s.startswith("update jobs set status = 'running'"):
            self._rows = [self.db.queued.pop(0)] if self.db.queued else []
        elif s.startswith("select slug from projects"):
            self._rows = [("ds",)]

    def fetchone(self):
        return self._rows[0] if self._rows else None

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
        self.db.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeDb:
    def __init__(self, queued=()):
        self.queued, self.sql, self.commits = list(queued), [], 0


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://fake/none")
    return dataclasses.replace(load_config(env_file=tmp_path / "absent.env"), repo_root=tmp_path)


ROW = ("job-1", "proj-1", "model-section", "P4P5/DIA", "", None, 5.0)


def test_run_once_claims_runs_and_finishes_done(cfg, monkeypatch):
    db = FakeDb(queued=[ROW])
    monkeypatch.setattr(W.psycopg, "connect", lambda *a, **k: FakeConn(db))
    seen = {}

    def fake_run_job(cfg, dataset, job, emit):
        seen.update(job=job, dataset=dataset)
        emit("info", "hello")
        return {"pass": True, "attempts": 2, "cost_usd": 0.31, "build_version": 7, "build_id": "b-7", "assumptions": [], "questions": []}
    assert W.run_once(cfg, run_job_fn=fake_run_job) is True
    assert seen["dataset"] == "ds" and seen["job"]["section_key"] == "P4P5/DIA" and seen["job"]["id"] == "job-1"
    claim_sql = db.sql[0][0]
    assert "for update skip locked" in claim_sql and "order by created_at limit 1" in claim_sql
    assert any(s.startswith("insert into job_events") and p[1:] == ("info", "hello") for s, p in db.sql)
    fin = [(s, p) for s, p in db.sql if s.startswith("update jobs set status = %s")][0]
    assert fin[1][0] == "done" and fin[1][2] == "b-7" and abs(float(fin[1][3]) - 0.31) < 1e-9 and fin[1][4] == 2
    assert fin[1][1].obj["build_version"] == 7
    assert db.commits >= 2


def test_run_once_returns_false_when_queue_empty(cfg, monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(W.psycopg, "connect", lambda *a, **k: FakeConn(db))
    assert W.run_once(cfg, run_job_fn=lambda *a: None) is False


def test_run_once_marks_failed_on_reason_or_exception(cfg, monkeypatch):
    db = FakeDb(queued=[ROW, ROW])
    monkeypatch.setattr(W.psycopg, "connect", lambda *a, **k: FakeConn(db))
    W.run_once(cfg, run_job_fn=lambda cfg, ds, job, emit: {"pass": False, "reason": "budget", "attempts": 0, "cost_usd": 0.0})
    fin = [p for s, p in db.sql if s.startswith("update jobs set status = %s")][-1]
    assert fin[0] == "failed"

    def boom(cfg, ds, job, emit):
        raise RuntimeError("kaboom")
    W.run_once(cfg, run_job_fn=boom)
    fin2 = [p for s, p in db.sql if s.startswith("update jobs set status = %s")][-1]
    assert fin2[0] == "failed" and "kaboom" in json.dumps(fin2[1].obj, ensure_ascii=False)
    assert any(s.startswith("insert into job_events") and p[1] == "error" for s, p in db.sql)


def test_serve_drain_processes_queue_then_returns(cfg, monkeypatch):
    """일괄 큐: --drain 이면 큐를 비우고 스스로 끝난다(M7 D6)."""
    db = FakeDb(queued=[ROW, ROW])
    monkeypatch.setattr(W.psycopg, "connect", lambda *a, **k: FakeConn(db))
    done = []

    def fake_run_job(cfg, dataset, job, emit):
        done.append(job["section_key"])
        return {"pass": True, "attempts": 1, "cost_usd": 0.1, "build_version": 1, "build_id": "b",
                "assumptions": [], "questions": []}
    W.serve(cfg, poll=0.0, drain=True, run_job_fn=fake_run_job)
    assert len(done) == 2


def test_serve_once_still_returns_after_one_job(cfg, monkeypatch):
    db = FakeDb(queued=[ROW, ROW])
    monkeypatch.setattr(W.psycopg, "connect", lambda *a, **k: FakeConn(db))
    n = []

    def one(cfg, dataset, job, emit):
        n.append(1)
        return {"pass": True, "attempts": 1, "cost_usd": 0.0, "assumptions": [], "questions": []}
    W.serve(cfg, poll=0.0, once=True, run_job_fn=one)
    assert len(n) == 1
