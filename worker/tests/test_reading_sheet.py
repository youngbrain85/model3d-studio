"""시트 판독 — 캐시·검증 재시도·usage 기록. 실 API 는 호출하지 않는다."""

import json
from types import SimpleNamespace

import pytest
from PIL import Image
from pydantic import ValidationError

from m3d.config import load_config
from m3d.reading.cache import CacheMissError
from m3d.reading.sheet import PageRef, list_pages, read_sheet

BBOX = [10.0, 20.0, 30.0, 40.0]
GOOD = json.dumps({
    "readings": [{"item": "슬래브 두께", "value_raw": "300", "unit": "mm",
                  "page_no": 1, "mm_bbox": BBOX, "crosscheck": None, "status": "확정"}],
    "ambiguities": [],
}, ensure_ascii=False)
# 근거(mm_bbox·page_no) 없는 응답 — 스키마가 반려해야 한다
BAD = json.dumps({"readings": [{"item": "두께", "value_raw": "300"}],
                  "ambiguities": []}, ensure_ascii=False)


def _resp(text):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=1000, output_tokens=200),
        stop_reason="end_turn")


class FakeMessages:
    """호출 횟수를 세고, 준비된 응답 텍스트를 순서대로 돌려준다."""

    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return _resp(self.texts.pop(0))


class FakeClient:
    def __init__(self, texts):
        self.messages = FakeMessages(texts)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_test")
    cfg = load_config(env_file=tmp_path / "absent.env")
    monkeypatch.setattr(type(cfg), "derived_dir",
                        property(lambda self: tmp_path / "derived"))
    return cfg


@pytest.fixture
def page(cfg):
    base = cfg.derived_dir / "ds"
    png = base / "png" / "B01_C1_p1.png"
    txt = base / "text" / "B01_C1_p1.json"
    png.parent.mkdir(parents=True, exist_ok=True)
    txt.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 600), "white").save(png)
    txt.write_text(json.dumps({"schema": 1, "drawing_no": "C1", "page_no": 1,
                               "paper_mm": [1189.0, 841.0], "scale": 100.0,
                               "rotation_deg": 0, "fallback": False,
                               "texts": [{"x_mm": 1.0, "y_mm": 2.0, "h_mm": 5.0,
                                          "kind": "TEXT", "text": "300"}]},
                              ensure_ascii=False), encoding="utf-8")
    return PageRef(ord="B01", drawing_no="C1", page_no=1, region="B", png=png, text=txt)


def test_reads_and_returns_parsed(cfg, page):
    client = FakeClient([GOOD])
    out, usage = read_sheet(cfg, "ds", page, client=client)
    assert out.readings[0].item == "슬래브 두께"
    assert usage["cached"] is False and usage["in"] == 1000
    assert client.messages.calls == 1


def test_second_call_hits_cache(cfg, page):
    client = FakeClient([GOOD])
    read_sheet(cfg, "ds", page, client=client)
    client2 = FakeClient([])          # 호출되면 IndexError 로 드러난다
    out, usage = read_sheet(cfg, "ds", page, client=client2)
    assert usage["cached"] is True and usage["in"] == 0
    assert client2.messages.calls == 0
    assert out.readings[0].value_raw == "300"


def test_force_bypasses_cache(cfg, page):
    read_sheet(cfg, "ds", page, client=FakeClient([GOOD]))
    client = FakeClient([GOOD])
    _out, usage = read_sheet(cfg, "ds", page, client=client, force=True)
    assert client.messages.calls == 1 and usage["cached"] is False


def test_schema_violation_retries_once(cfg, page):
    """근거 없는 수치는 반려하고 사유를 붙여 1회 재시도한다 (지식베이스 §8)."""
    client = FakeClient([BAD, GOOD])
    out, usage = read_sheet(cfg, "ds", page, client=client)
    assert client.messages.calls == 2
    assert usage["retried"] is True
    assert out.readings[0].item == "슬래브 두께"


def test_schema_violation_twice_raises(cfg, page):
    client = FakeClient([BAD, BAD])
    with pytest.raises(ValidationError):
        read_sheet(cfg, "ds", page, client=client)


def test_usage_logged_to_jsonl(cfg, page):
    read_sheet(cfg, "ds", page, client=FakeClient([GOOD]))
    lines = (cfg.derived_dir / "ds" / "usage.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    rec = json.loads(lines[-1])
    assert rec["stage"] == "read" and rec["ord"] == "B01" and rec["cost_usd"] > 0


def test_cache_only_raises_on_miss(cfg, page):
    """--cache-only 는 실호출 대신 실패한다 — verify 스크립트의 무과금 보증."""
    client = FakeClient([GOOD])
    with pytest.raises(CacheMissError):
        read_sheet(cfg, "ds", page, client=client, cache_only=True)
    assert client.messages.calls == 0


def test_list_pages_filters_by_region(cfg, page):
    pages = list_pages(cfg, "ds", region="B")
    assert [p.ord for p in pages] == ["B01"]
    assert list_pages(cfg, "ds", region="C") == []
