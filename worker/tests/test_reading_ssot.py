"""m3d ssot — 판독값·결정을 합친 치수 정본 문서(실측정리) 생성."""

import dataclasses
import json

import pytest

from m3d.config import load_config
from m3d.reading import ssot

PROJECT = {"slug": "ds", "name": "테스트교", "coord_system": {"unit": "m"},
           "coord_assumptions": ["P4 STA 정정"]}
READINGS = [
    {"region": "B", "ord": "B01", "page_no": 1, "item": "전체 폭원", "value_raw": "15,700",
     "unit": "mm", "status": "확정", "mm_bbox": [1.0, 2.0, 3.0, 4.0],
     "crosscheck": {"expr": "5,600+4,500+5,600=15,700"}},
    {"region": "B", "ord": "B01", "page_no": 1, "item": "교량 총길이", "value_raw": "684,280",
     "unit": "mm", "status": "추정", "mm_bbox": [1, 2, 3, 4], "crosscheck": None},
    {"region": "C", "ord": "C01", "page_no": 1, "item": "형고", "value_raw": "4,000",
     "unit": "mm", "status": "검토지적", "mm_bbox": [1, 2, 3, 4], "crosscheck": None},
]
OPTS = [{"label": "순두께", "basis": "단면 C-C"}, {"label": "포장 포함", "basis": "표기 관례"}]
AMBS = [
    {"id": "amb-1", "ord": "B01", "page_no": 1, "item": "슬래브 두께 의미", "options": OPTS,
     "model_impact": "자중 44% 차이", "status": "결정", "choice_index": 1, "choice_label": "포장 포함",
     "provisional": False, "note": "현장 확인", "decided_at": "2026-09-05T10:00:00+00:00"},
    {"id": "amb-2", "ord": "B02", "page_no": 2, "item": "방호벽 대칭", "options": OPTS,
     "model_impact": "패밀리 1종", "status": "잠정", "choice_index": 0,
     "choice_label": "모르겠다 — 권장대로 진행, 나중에 확인", "provisional": True, "note": "",
     "decided_at": "2026-09-05T10:05:00+00:00"},
    {"id": "amb-3", "ord": "C01", "page_no": 1, "item": "형고 의미", "options": OPTS,
     "model_impact": "내공/전강고", "status": "대기", "choice_index": None, "choice_label": None,
     "provisional": None, "note": None, "decided_at": None},
]


def test_build_ssot_sections_and_counts():
    body, doc = ssot.build_ssot(PROJECT, READINGS, AMBS)
    for head in ("## 0. 좌표계·가정", "## 1. 확정 (1건)", "## 2. 추정 (1건)", "## 3. 검토지적 (1건)",
                 "## 4. 결정 (2건 — 잠정 1건)", "## 5. 미결 (1건)", "## 6. 통계"):
        assert head in body, head
    assert "| 전체 폭원 | 15,700 | mm | B01 p1 [1, 2, 3, 4] | 5,600+4,500+5,600=15,700 |" in body
    assert "### [결정] 슬래브 두께 의미 — B01 p1" in body and "- 선택: 포장 포함 — 근거: 표기 관례" in body
    assert "### [잠정] 방호벽 대칭 — B02 p2" in body
    assert "- (0) 순두께 — 단면 C-C" in body            # 미결 절은 선택지 전부 나열
    assert doc["counts"] == {"readings": {"확정": 1, "추정": 1, "검토지적": 1},
                             "decided": 2, "provisional": 1, "open": 1}
    assert doc["decisions"][0]["basis"] == "표기 관례" and doc["open"][0]["ambiguity_id"] == "amb-3"
    assert "generated" not in body                       # 본문은 시각을 담지 않는다(해시 안정)


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self._rows = []

    def execute(self, sql, params=None):
        s = " ".join(sql.split())
        self.db.sql.append(s)
        self._rows = []
        if s.startswith("select id, slug, name, coord_system, coord_assumptions from projects"):
            p = self.db.project
            self._rows = [("proj-1", p["slug"], p["name"], p["coord_system"], p["coord_assumptions"])]
        elif s.startswith("select r.region, s.ord, sp.page_no"):
            self._rows = [tuple(r[k] for k in ("region", "ord", "page_no", "item", "value_raw",
                                                 "unit", "status", "mm_bbox", "crosscheck"))
                          for r in self.db.readings]
        elif s.startswith("select a.id, s.ord, sp.page_no"):
            self._rows = [tuple(a[k] for k in ("id", "ord", "page_no", "item", "options", "model_impact",
                                                 "status", "choice_index", "choice_label", "provisional",
                                                 "note", "decided_at"))
                          for a in self.db.ambiguities]

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeDb:
    def __init__(self, project, readings, ambiguities):
        self.project, self.readings, self.ambiguities = project, list(readings), list(ambiguities)
        self.sql = []


class FakeConn:
    def __init__(self, db):
        self.db = db

    def cursor(self):
        return FakeCursor(self.db)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://fake/none")
    cfg = load_config(env_file=tmp_path / "absent.env")
    return dataclasses.replace(cfg, repo_root=tmp_path)


def test_run_ssot_writes_v1_then_no_change_then_v2(cfg, monkeypatch):
    db = FakeDb(PROJECT, READINGS, AMBS)
    monkeypatch.setattr(ssot.psycopg, "connect", lambda *a, **k: FakeConn(db))
    out = cfg.derived_dir / "ds" / "ssot"

    r1 = ssot.run_ssot(cfg, "ds")
    assert r1["changed"] is True and r1["version"] == 1
    assert (out / "실측정리_v1.md").is_file() and (out / "ssot.json").is_file()
    doc = json.loads((out / "ssot.json").read_text(encoding="utf-8"))
    assert doc["version"] == 1 and set(doc) >= {"generated_at", "project", "readings", "decisions", "open", "counts"}

    r2 = ssot.run_ssot(cfg, "ds")
    assert r2["changed"] is False and r2["version"] == 1
    assert not (out / "실측정리_v2.md").exists()

    db.ambiguities[2] = {**AMBS[2], "status": "결정", "choice_index": 0, "choice_label": "순두께",
                         "provisional": False, "note": "", "decided_at": "2026-09-05T11:00:00+00:00"}
    r3 = ssot.run_ssot(cfg, "ds")
    assert r3["changed"] is True and r3["version"] == 2
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert [i["version"] for i in index] == [1, 2] and index[1]["counts"]["open"] == 0


def test_run_ssot_requires_project(cfg, monkeypatch):
    class NoProjectCursor(FakeCursor):
        def execute(self, sql, params=None):
            super().execute(sql, params)
            if sql.lstrip().startswith("select id, slug"):
                self._rows = []

    db = FakeDb(PROJECT, [], [])

    class Conn(FakeConn):
        def cursor(self):
            return NoProjectCursor(self.db)

    monkeypatch.setattr(ssot.psycopg, "connect", lambda *a, **k: Conn(db))
    with pytest.raises(RuntimeError, match="없음"):
        ssot.run_ssot(cfg, "ds")
