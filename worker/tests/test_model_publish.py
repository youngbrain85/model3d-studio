"""m3d publish-model — 산출물 수집·해시·업로드·builds/build_sections 행 (M4 §5). 실호출 없음(가짜 업로드·DB)."""

import dataclasses
import json

import pytest
from typer.testing import CliRunner

from m3d.cli import app
from m3d.config import load_config
from m3d.model import publish as P

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class FakeDb:
    def __init__(self, latest=None):
        self.latest = latest            # (version, content_sha256) | None
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
        elif s.startswith("select version, content_sha256 from builds"):
            self._rows = [self.db.latest] if self.db.latest else []
        elif s.startswith("insert into builds"):
            self._rows = [("build-1",)]

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


def _model_dir(cfg, *, with_measure=True):
    d = cfg.derived_dir / "ds" / "model"
    (d / "sections" / "P4P5").mkdir(parents=True)
    (d / "renders").mkdir()
    (d / "sections" / "P4P5" / "BOX.glb").write_bytes(b"glTF-box")
    (d / "sections" / "P4P5" / "DIA.glb").write_bytes(b"glTF-dia")
    (d / "AB1_P4P5.glb").write_bytes(b"glTF-all")
    build = {"kind": "full", "segment": "P4P5", "git_sha": "abc",
             "assembled": {"file": "AB1_P4P5.glb", "meshes": 30, "triangles": 100, "bytes": 8, "sha256": "x"},
             "sections": [
                 {"key": "P4P5/BOX", "code": "BOX", "label": "본체", "file": "sections/P4P5/BOX.glb", "meshes": 4,
                  "triangles": 40, "bytes": 8, "sha256": "b", "selfcheck": {"pass": 9, "fail": 0}},
                 {"key": "P4P5/DIA", "code": "DIA", "label": "격벽", "file": "sections/P4P5/DIA.glb", "meshes": 26,
                  "triangles": 60, "bytes": 8, "sha256": "d", "selfcheck": {"pass": 5, "fail": 0}}],
             "selfcheck": {"pass": 15, "fail": 0, "skipped": 5}}
    (d / "build.json").write_text(json.dumps(build), encoding="utf-8")
    (d / "selfcheck.json").write_text(json.dumps({"pass": 15, "fail": 0, "skipped": 5, "checks": []}), encoding="utf-8")
    (d / "selfcheck_sections.json").write_text(json.dumps({
        "P4P5/BOX": {"pass": 9, "fail": 0, "checks": [{"label": "수밀 전건", "ok": True, "detail": "4/4", "group": "COMMON"}]},
        "P4P5/DIA": {"pass": 5, "fail": 0, "checks": []}}), encoding="utf-8")
    (d / "modelspec.json").write_text('{"spec": {}}', encoding="utf-8")
    (d / "renders" / "side_context.png").write_bytes(PNG)
    (d / "renders" / "views.json").write_text("{}", encoding="utf-8")
    if with_measure:
        (d / "measure.json").write_text(json.dumps({"집계": {"PASS": 47, "FAIL": 0, "INFO": 2}}), encoding="utf-8")
        (d / "compare.json").write_text(json.dumps({"summary": {"match": 836, "mismatch": 0, "na": 0}}), encoding="utf-8")
    return d


def _patch(monkeypatch, db, fail_rel=None):
    calls = []

    def fake_upload(url, headers, data):
        calls.append((url, headers, data))
        return (500, "boom") if fail_rel and url.endswith(fail_rel) else (200, "{}")
    monkeypatch.setattr(P.psycopg, "connect", lambda *a, **k: FakeConn(db))
    monkeypatch.setattr(P, "_upload", fake_upload)
    return calls


def test_object_key_matches_web_rule():
    assert P.object_key("ab1-p4p5", 3, "sections/P4P5/DIA.glb") == "ab1-p4p5/b3/sections/P4P5/DIA.glb"


def test_collect_files_required_sections_renders_optional(cfg):
    d = _model_dir(cfg)
    files = P.collect_files(d)
    assert files[:6] == list(P.REQUIRED)
    assert "sections/P4P5/BOX.glb" in files and "sections/P4P5/DIA.glb" in files
    assert "renders/side_context.png" in files and files[-2:] == ["measure.json", "compare.json"]
    assert len(files) == 11
    (d / "selfcheck_sections.json").unlink()
    with pytest.raises(RuntimeError, match="selfcheck_sections.json"):
        P.collect_files(d)


def test_build_stats_folds_summaries(cfg):
    d = _model_dir(cfg)
    st = P.build_stats(d)
    assert st == {"meshes": 30, "triangles": 100, "selfcheck": {"pass": 15, "fail": 0, "skipped": 5},
                  "measure": {"pass": 47, "fail": 0, "info": 2}, "compare": {"match": 836, "mismatch": 0, "na": 0}}
    assert P.build_stats(_model_dir(dataclasses.replace(cfg, repo_root=cfg.repo_root / "b"), with_measure=False))["measure"] is None


def test_publish_uploads_all_files_and_inserts_rows(cfg, monkeypatch):
    d = _model_dir(cfg)
    db = FakeDb(latest=None)
    calls = _patch(monkeypatch, db)
    r = P.run_publish_model(cfg, "ds")
    assert r == {"skipped": False, "version": 1, "files": 11, "uploaded": 11, "failures": [], "build_id": "build-1"}
    urls = [u for (u, _h, _d) in calls]
    assert all(u.startswith("https://fake.supabase.co/storage/v1/object/models/ds/b1/") for u in urls)
    types = {u.rsplit(".", 1)[1]: h["Content-Type"] for (u, h, _d) in calls}
    assert types == {"glb": "model/gltf-binary", "png": "image/png", "json": "application/json"}
    assert all(h["x-upsert"] == "true" for (_u, h, _d) in calls)
    inserts = [s for s, _p in db.sql if s.startswith("insert into")]
    assert len(inserts) == 1 + 2 and inserts[0].startswith("insert into builds")
    b_params = [p for s, p in db.sql if s.startswith("insert into builds")][0]
    assert b_params[:6] == ("proj-1", 1, "full", "P4P5", P.content_sha256(d), "ds/b1/AB1_P4P5.glb")
    s_params = [p for s, p in db.sql if s.startswith("insert into build_sections")]
    assert s_params[0][:5] == ("build-1", "P4P5/BOX", "BOX", "본체", "ds/b1/sections/P4P5/BOX.glb")
    assert db.committed is True
    assert "service-test-key" not in json.dumps(r)


def test_publish_skips_same_content_unless_force(cfg, monkeypatch):
    d = _model_dir(cfg)
    db = FakeDb(latest=(2, P.content_sha256(d)))
    calls = _patch(monkeypatch, db)
    r = P.run_publish_model(cfg, "ds")
    assert r["skipped"] is True and r["version"] == 2 and r["uploaded"] == 0 and calls == []
    assert not any(s.startswith("insert") for s, _p in db.sql)
    r2 = P.run_publish_model(cfg, "ds", force=True)
    assert r2["skipped"] is False and r2["version"] == 3 and r2["uploaded"] == 11
    assert calls[0][0].startswith("https://fake.supabase.co/storage/v1/object/models/ds/b3/")


def test_upload_failure_blocks_db_rows(cfg, monkeypatch):
    _model_dir(cfg)
    db = FakeDb(latest=None)
    _patch(monkeypatch, db, fail_rel="sections/P4P5/DIA.glb")
    r = P.run_publish_model(cfg, "ds")
    assert r["version"] is None and r["build_id"] is None and r["uploaded"] == 10
    assert r["failures"] == [("sections/P4P5/DIA.glb", "HTTP 500: boom")]
    assert not any(s.startswith("insert") for s, _p in db.sql) and db.committed is False


def test_cli_prints_summary_and_exit_code(cfg, monkeypatch):
    monkeypatch.setattr(P, "run_publish_model",
                        lambda cfg, ds, *, pilot=False, force=False:
                        {"skipped": False, "version": 4, "files": 11, "uploaded": 11, "failures": [], "build_id": "b"})
    res = CliRunner().invoke(app, ["publish-model", "ds"])
    assert res.exit_code == 0 and "publish-model version=4 files=11 uploaded=11 skipped=false" in res.output
    monkeypatch.setattr(P, "run_publish_model",
                        lambda cfg, ds, *, pilot=False, force=False:
                        {"skipped": False, "version": None, "files": 11, "uploaded": 10,
                         "failures": [("renders/views.json", "HTTP 500: boom")], "build_id": None})
    res = CliRunner().invoke(app, ["publish-model", "ds", "--pilot"])
    assert res.exit_code == 1 and "실패: renders/views.json — HTTP 500: boom" in res.output
