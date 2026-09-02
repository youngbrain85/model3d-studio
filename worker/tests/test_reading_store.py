"""DB 반영 — 계열 단위 교체(멱등)와 자연키 id 보존. 가짜 커서로 SQL 을 검증한다."""

import pytest

from m3d.config import load_config
from m3d.models import AmbiguityOption
from m3d.reading import store
from m3d.reading.schema import MergedAmbiguity, MergedReading
from m3d.reading.store import build_rows

BBOX = [1.0, 2.0, 3.0, 4.0]
# jsonb 는 numeric 기반이라 후행 0 을 보존하며(공식 문서) 이 저장 경로에서는
# [100.0, …] 이 그대로 돌아온다. 다만 다른 경로(수동 SQL 시드·타 도구)가 정수 표기로
# 써 넣거나 자릿수가 달라질 수 있으므로 좌표는 표기에 무관하게 float 반올림으로 비교한다.
BBOX_NEW = [100.0, 200.0, 120.0, 220.0]
BBOX_FROM_DB = [100, 200, 120, 220]
PROJECT = "proj-1"


def _r(item, ord_="B01", page_no=1):
    return MergedReading(item=item, value_raw="300", unit="mm", page_no=page_no,
                         mm_bbox=BBOX, crosscheck="합=300 ✓", status="확정", ord=ord_)


def _a(item, ord_="B01", page_no=1, mm_bbox=None):
    return MergedAmbiguity(item=item, page_no=page_no, mm_bbox=mm_bbox or BBOX,
                           options=[AmbiguityOption(label="a", basis="b"),
                                    AmbiguityOption(label="c", basis="d")],
                           model_impact="영향", ord=ord_)


class FakeDb:
    """sheets·sheet_pages·ambiguities 만 흉내낸다 — 나머지는 SQL 기록으로 검사."""

    def __init__(self, ambiguities=()):
        self.sheets = {"A01": "s-a01", "B01": "s-b01", "B02": "s-b02"}
        self.pages = {("A01", 1): "p-a01-1", ("B01", 1): "p-b01-1", ("B02", 1): "p-b02-1"}
        self.ambiguities = list(ambiguities)
        self.sql, self.inserted_r, self.inserted_a = [], [], []
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
            self._rows = [(PROJECT,)]
        elif s.startswith("select ord, id from sheets"):
            self._rows = list(self.db.sheets.items())
        elif s.startswith("select s.ord, sp.page_no"):
            self._rows = [(o, n, i) for (o, n), i in self.db.pages.items()]
        elif s.startswith("select id, basis_sheet_id"):
            self._rows = list(self.db.ambiguities)
        elif s.startswith("delete from ambiguities"):
            self.db.ambiguities = []
        elif s.startswith("insert into readings"):
            self.db.inserted_r.append(params)
        elif s.startswith("insert into ambiguities"):
            self.db.inserted_a.append(params)

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
    return load_config(env_file=tmp_path / "absent.env")


def _patch(monkeypatch, db):
    monkeypatch.setattr(store.psycopg, "connect", lambda *a, **k: FakeConn(db))


def test_build_rows_uses_each_row_own_ord():
    """통합 결과의 항목마다 근거 시트가 다르다 — 호출부가 ord 를 하나로 뭉치지 않는다."""
    rows_r, rows_a = build_rows("B", [_r("두께", ord_="B02")], [_a("해석", ord_="B03")],
                                round_no=3)
    assert rows_r[0].region == "B" and rows_r[0].basis_ord == "B02"
    assert rows_r[0].round == 3
    assert rows_a[0].basis_ord == "B03" and rows_a[0].status == "대기"


def test_build_rows_preserves_crosscheck_and_bbox():
    rows_r, _ = build_rows("B", [_r("두께")], [], round_no=1)
    assert rows_r[0].crosscheck == {"expr": "합=300 ✓"}
    assert rows_r[0].basis_mm_bbox == BBOX


def test_build_rows_options_serialised():
    _, rows_a = build_rows("B", [], [_a("해석")], round_no=1)
    assert [o.label for o in rows_a[0].options] == ["a", "c"]


def test_build_rows_empty_inputs():
    rows_r, rows_a = build_rows("B", [], [], round_no=1)
    assert rows_r == [] and rows_a == []


def test_ambiguities_deleted_even_when_new_result_is_empty(cfg, monkeypatch):
    """새 결과가 0건이어도 계열의 옛 행은 지운다 — 잔존 행이 '전건' 표를 오염시킨다."""
    db = FakeDb(ambiguities=[("old-id", "s-b01", "p-b01-1", "옛항목", BBOX,
                              "data/derived/ds/crops/old-id.png")])
    _patch(monkeypatch, db)
    res = store.replace_region(cfg, "ds", "B", [], [])
    dels = [(s, p) for s, p in db.sql if s.startswith("delete from ambiguities")]
    assert len(dels) == 1
    assert sorted(dels[0][1][1]) == ["s-b01", "s-b02"]     # 계열 시트 전체가 대상
    assert db.inserted_a == [] and db.committed is True
    assert res == {"readings": 0, "ambiguities": 0, "kept": 0, "failed": 0}


def test_same_natural_key_keeps_id_and_crop_path(cfg, monkeypatch):
    """자연키가 같으면 옛 id·crop_rel_path 를 이어받는다 — 크롭 링크가 끊기지 않는다.

    jsonb 는 numeric 기반이라 후행 0 을 보존하지만(공식 문서), 다른 경로(수동 SQL
    시드·타 도구)가 정수 표기로 써 넣으면 DB 행은 [100, …], 새 행은 [100.0, …] 로
    표기가 갈린다. 문자열 비교는 이 차이에 취약하다 — 표기가 달라도 같은 좌표면
    id·crop_rel_path 를 이어받는다는 것을 여기서 고정한다.
    """
    db = FakeDb(ambiguities=[("old-id", "s-b01", "p-b01-1", "해석", BBOX_FROM_DB,
                              "data/derived/ds/crops/old-id.png")])
    _patch(monkeypatch, db)
    _rows_r, rows_a = build_rows("B", [], [_a("해석", mm_bbox=BBOX_NEW)], round_no=3)
    assert str(BBOX_FROM_DB) != str(BBOX_NEW)      # 표기는 다르고 좌표는 같다
    res = store.replace_region(cfg, "ds", "B", [], rows_a)
    assert res["kept"] == 1 and res["ambiguities"] == 1
    params = db.inserted_a[0]
    assert params[0] == "old-id"                                  # id 보존
    assert params[8] == "data/derived/ds/crops/old-id.png"        # crop_rel_path 보존
    # keep-맵 SELECT 가 DELETE 보다 앞서야 한다 — 순서가 뒤바뀌면 FakeCursor 가 DELETE 때
    # ambiguities 를 비우므로 keep-맵이 빈 채로 뜨고, 이 단언이 먼저 잡아낸다.
    select_idx = next(i for i, (s, _) in enumerate(db.sql)
                      if s.startswith("select id, basis_sheet_id"))
    delete_idx = next(i for i, (s, _) in enumerate(db.sql)
                      if s.startswith("delete from ambiguities"))
    assert select_idx < delete_idx


def test_replace_region_inserts_readings_with_region_and_round(cfg, monkeypatch):
    """[Important 3-a] readings 삽입이 실제로 실행되고 region·round 가 실린다."""
    db = FakeDb()
    _patch(monkeypatch, db)
    rows_r, _rows_a = build_rows("B", [_r("두께", ord_="B01")], [], round_no=2)
    res = store.replace_region(cfg, "ds", "B", rows_r, [])
    assert res == {"readings": 1, "ambiguities": 0, "kept": 0, "failed": 0}
    assert len(db.inserted_r) == 1
    params = db.inserted_r[0]
    # insert into readings (project_id, region, item, value_raw, unit,
    #                        basis_sheet_id, basis_page_id, basis_mm_bbox, crosscheck, status, round)
    assert params[1] == "B" and params[10] == 2


def test_replace_region_counts_unresolved_ord_as_failed(cfg, monkeypatch):
    """[Important 3-a] 시트·페이지 id 를 못 찾는 행은 버려지고 failed 로 센다."""
    db = FakeDb()
    _patch(monkeypatch, db)
    rows_r, rows_a = build_rows(
        "B", [_r("두께", ord_="Z99")], [_a("해석", ord_="Z99")], round_no=2)
    res = store.replace_region(cfg, "ds", "B", rows_r, rows_a)
    assert res == {"readings": 0, "ambiguities": 0, "kept": 0, "failed": 2}
    assert db.inserted_r == [] and db.inserted_a == []
