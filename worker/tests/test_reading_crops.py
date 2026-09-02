"""ambiguity mm bbox → 크롭 픽셀 + 고아 정리. M1 의 용지 mm 계약 회수 지점 (§6)."""

import dataclasses
import json

import pytest
from PIL import Image

from m3d.config import load_config
from m3d.reading import crops as crops_mod
from m3d.reading.crops import CONTEXT_MM, mm_bbox_to_px, render_crop
from m3d.samples.manifest import sha256_file

PAPER = [1189.0, 841.0]
SIZE = (8000, 5659)          # M1 렌더 실측 비율에 가까운 값
BBOX = [10.0, 20.0, 30.0, 40.0]


def test_center_maps_to_center():
    x0, y0, x1, y1 = mm_bbox_to_px([594.5, 420.5, 594.5, 420.5], PAPER, SIZE, context_mm=0)
    assert x0 == pytest.approx(4000, abs=3) and x1 == pytest.approx(4000, abs=3)
    assert y0 == pytest.approx(2829, abs=3)


def test_y_axis_is_flipped():
    """용지 y 는 아래에서 위로, 픽셀 y 는 위에서 아래로 — 뒤집혀야 한다."""
    top = mm_bbox_to_px([100, 800, 200, 830], PAPER, SIZE, context_mm=0)
    bottom = mm_bbox_to_px([100, 10, 200, 40], PAPER, SIZE, context_mm=0)
    assert top[1] < bottom[1]


def test_context_margin_expands_box():
    tight = mm_bbox_to_px([500, 400, 520, 420], PAPER, SIZE, context_mm=0)
    padded = mm_bbox_to_px([500, 400, 520, 420], PAPER, SIZE, context_mm=CONTEXT_MM)
    assert padded[0] < tight[0] and padded[2] > tight[2]
    assert padded[1] < tight[1] and padded[3] > tight[3]


def test_clamped_to_image_bounds():
    box = mm_bbox_to_px([0.0, 0.0, 5.0, 5.0], PAPER, SIZE, context_mm=CONTEXT_MM)
    assert box[0] >= 0 and box[1] >= 0
    assert box[2] <= SIZE[0] and box[3] <= SIZE[1]


def test_degenerate_point_bbox_still_has_area():
    """LLM 이 점 하나를 주더라도 맥락 여백이 면적을 만든다."""
    x0, y0, x1, y1 = mm_bbox_to_px([600, 400, 600, 400], PAPER, SIZE)
    assert x1 > x0 and y1 > y0


def test_bbox_beyond_paper_width_raises():
    """용지 밖 좌표는 clamp 로 뭉개지 않고 드러낸다 — 조용한 1px 스트립 금지."""
    with pytest.raises(ValueError, match="용지 범위 밖"):
        mm_bbox_to_px([1300, 100, 1320, 120], PAPER, SIZE)


def test_bbox_with_negative_y_raises():
    with pytest.raises(ValueError, match="용지 범위 밖"):
        mm_bbox_to_px([100, -200, 120, -180], PAPER, SIZE)


def test_render_crop_upscales_small(tmp_path):
    src = tmp_path / "s.png"
    Image.new("RGB", (2000, 1500), "white").save(src)
    out = tmp_path / "c.png"
    w, h = render_crop(src, (100, 100, 250, 200), out)
    assert min(w, h) >= 400          # 너무 작으면 확대해서 읽히게
    with Image.open(out) as im:
        assert im.size == (w, h)


def test_render_crop_keeps_large_as_is(tmp_path):
    src = tmp_path / "s.png"
    Image.new("RGB", (4000, 3000), "white").save(src)
    out = tmp_path / "c.png"
    w, h = render_crop(src, (0, 0, 2000, 1500), out)
    assert (w, h) == (2000, 1500)


# ── run_crops (가짜 커서) ────────────────────────────────────────────────

class FakeDb:
    def __init__(self, rows=(), fail_on=None):
        self.rows = list(rows)
        self.sql = []
        self.committed = False
        self.rolled_back = False
        self.fail_on = fail_on  # SQL 접두어 — 매치되면 execute 가 RuntimeError 를 던진다


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self._rows = []

    def execute(self, sql, params=None):
        s = " ".join(sql.split())
        self.db.sql.append((s, params))
        self._rows = []
        if self.db.fail_on and s.startswith(self.db.fail_on):
            raise RuntimeError("db boom")
        if s.startswith("select id from projects"):
            self._rows = [("proj-1",)]
        elif s.startswith("select a.id, a.mm_bbox"):
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

    def rollback(self):
        self.db.rolled_back = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://fake/none")
    cfg = load_config(env_file=tmp_path / "absent.env")
    # repo_root 를 tmp 로 바꾸면 derived_dir(= repo_root/data/derived)도 따라와
    # crops_dir 과 `cfg.repo_root / rel` 이 같은 트리를 가리킨다 — 실제 리포 오염 금지.
    # derived_dir 만 패치하면 out 경로가 실제 리포로 새므로 패치하지 않는다.
    return dataclasses.replace(cfg, repo_root=tmp_path)


def test_run_crops_makes_then_skips_by_sha(cfg, monkeypatch):
    """정상 경로: 크롭 생성 → assets 등재 → 재실행 시 sha 대조로 스킵."""
    base = cfg.derived_dir / "ds"
    (base / "png").mkdir(parents=True)
    (base / "text").mkdir(parents=True)
    Image.new("RGB", (800, 600), "white").save(base / "png" / "B01_C1_p1.png")
    (base / "text" / "B01_C1_p1.json").write_text(
        json.dumps({"paper_mm": PAPER, "rotation_deg": 0}), encoding="utf-8")
    db = FakeDb(rows=[("amb-1", BBOX, None, "B01", "s-b01", 1, "p-b01-1", 800, 600, None)])
    monkeypatch.setattr(crops_mod.psycopg, "connect", lambda *a, **k: FakeConn(db))

    r = crops_mod.run_crops(cfg, "ds")
    out = base / "crops" / "amb-1.png"
    assert r["made"] == 1 and not r["failures"] and out.is_file() and db.committed
    assert any(s.startswith("update ambiguities set crop_rel_path") for s, _ in db.sql)
    assert any(s.startswith("insert into assets") for s, _ in db.sql)

    sha = sha256_file(out)
    db2 = FakeDb(rows=[("amb-1", BBOX, "data/derived/ds/crops/amb-1.png",
                        "B01", "s-b01", 1, "p-b01-1", 800, 600, sha)])
    monkeypatch.setattr(crops_mod.psycopg, "connect", lambda *a, **k: FakeConn(db2))
    r2 = crops_mod.run_crops(cfg, "ds")
    assert r2["skipped"] == 1 and r2["made"] == 0
    assert not any(s.startswith("insert into assets") for s, _ in db2.sql)


def test_run_crops_purges_orphans(cfg, monkeypatch):
    """옛 실행이 남긴 크롭 PNG·assets 행을 지운다 — 실행마다 쌓이면 전건 대조가 깨진다."""
    crops_dir = cfg.derived_dir / "ds" / "crops"
    crops_dir.mkdir(parents=True)
    (crops_dir / "orphan.png").write_bytes(b"stale")
    db = FakeDb(rows=[])
    monkeypatch.setattr(crops_mod.psycopg, "connect", lambda *a, **k: FakeConn(db))

    r = crops_mod.run_crops(cfg, "ds")
    assert r["purged"] == 1 and not (crops_dir / "orphan.png").exists()
    assert any(s.startswith("delete from assets") for s, _ in db.sql)


def test_run_crops_reports_rotated_frame(cfg, monkeypatch):
    """회전 도곽은 조용히 엉뚱한 영역을 자르지 않고 실패로 남는다 (M2a 범위 밖)."""
    base = cfg.derived_dir / "ds"
    (base / "png").mkdir(parents=True)
    (base / "text").mkdir(parents=True)
    Image.new("RGB", (800, 600), "white").save(base / "png" / "B01_C1_p1.png")
    (base / "text" / "B01_C1_p1.json").write_text(
        json.dumps({"paper_mm": PAPER, "rotation_deg": 90}), encoding="utf-8")
    db = FakeDb(rows=[("amb-1", BBOX, None, "B01", "s-b01", 1, "p-b01-1", 800, 600, None)])
    monkeypatch.setattr(crops_mod.psycopg, "connect", lambda *a, **k: FakeConn(db))

    r = crops_mod.run_crops(cfg, "ds")
    assert r["made"] == 0 and len(r["failures"]) == 1
    assert "회전 도곽" in r["failures"][0][1]


def test_run_crops_db_error_rolls_back_and_raises(cfg, monkeypatch):
    """DB 반영(update/insert) 실패는 삼키지 않는다 — rollback 후 RuntimeError 로 올린다.

    psycopg3 는 SQL 오류 후 트랜잭션이 aborted 상태가 되므로, 여기서 삼키고 다음
    행을 계속 처리하면 원인과 무관한 행까지 failures 로 오염된다.
    """
    base = cfg.derived_dir / "ds"
    (base / "png").mkdir(parents=True)
    (base / "text").mkdir(parents=True)
    Image.new("RGB", (800, 600), "white").save(base / "png" / "B01_C1_p1.png")
    (base / "text" / "B01_C1_p1.json").write_text(
        json.dumps({"paper_mm": PAPER, "rotation_deg": 0}), encoding="utf-8")
    db = FakeDb(
        rows=[("amb-1", BBOX, None, "B01", "s-b01", 1, "p-b01-1", 800, 600, None)],
        fail_on="update ambiguities set crop_rel_path",
    )
    monkeypatch.setattr(crops_mod.psycopg, "connect", lambda *a, **k: FakeConn(db))

    with pytest.raises(RuntimeError, match="크롭 DB 반영 실패"):
        crops_mod.run_crops(cfg, "ds")
    assert db.committed is False
    assert db.rolled_back is True


def test_run_crops_render_error_isolates_row_and_still_commits(cfg, monkeypatch):
    """렌더 단계(용지 밖 bbox 등) 실패는 해당 행만 failures 로 남기고, 나머지 행은
    정상 처리되어 commit 까지 이어진다."""
    base = cfg.derived_dir / "ds"
    (base / "png").mkdir(parents=True)
    (base / "text").mkdir(parents=True)
    Image.new("RGB", (800, 600), "white").save(base / "png" / "B01_C1_p1.png")
    (base / "text" / "B01_C1_p1.json").write_text(
        json.dumps({"paper_mm": PAPER, "rotation_deg": 0}), encoding="utf-8")
    bad_bbox = [1300.0, 100.0, 1320.0, 120.0]   # 용지(1189mm) 밖
    db = FakeDb(rows=[
        ("amb-bad", bad_bbox, None, "B01", "s-b01", 1, "p-b01-1", 800, 600, None),
        ("amb-good", BBOX, None, "B01", "s-b01", 1, "p-b01-1", 800, 600, None),
    ])
    monkeypatch.setattr(crops_mod.psycopg, "connect", lambda *a, **k: FakeConn(db))

    r = crops_mod.run_crops(cfg, "ds")
    assert r["made"] == 1 and len(r["failures"]) == 1
    assert r["failures"][0][0] == "amb-bad"
    assert (base / "crops" / "amb-good.png").is_file()
    assert db.committed is True
