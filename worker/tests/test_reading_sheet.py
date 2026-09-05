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
PAPER_MM = [1189.0, 841.0]          # 픽스처 페이지의 용지(A0) — 아래 위반값의 기준


def _reading(page_no=1, mm_bbox=None):
    return {"item": "슬래브 두께", "value_raw": "300", "unit": "mm", "page_no": page_no,
            "mm_bbox": mm_bbox or BBOX, "crosscheck": None, "status": "확정"}


def _ambiguity(page_no=1, mm_bbox=None):
    return {"item": "해석 갈림", "page_no": page_no, "mm_bbox": mm_bbox or BBOX,
            "options": [{"label": "a", "basis": "b"}, {"label": "c", "basis": "d"}],
            "model_impact": "영향"}


def _sheet_json(readings=None, ambiguities=None):
    return json.dumps({"readings": readings or [], "ambiguities": ambiguities or []},
                      ensure_ascii=False)


# 이 시트에 없는 페이지를 근거로 댄 응답 — post_validate 가 반려해야 한다
OTHER_PAGE = _sheet_json(readings=[_reading(page_no=2)])
# 용지(1189×841) 밖 mm_bbox — 크롭 단계가 아니라 판독 단계에서 잡아야 한다
OUTSIDE_PAPER = _sheet_json(ambiguities=[_ambiguity(mm_bbox=[10.0, 20.0, 1300.0, 40.0])])
# 위반 2건(다른 page_no + 용지 밖 bbox)이 한 번에 담긴 응답
TWO_VIOLATIONS = _sheet_json(readings=[_reading(page_no=2)],
                             ambiguities=[_ambiguity(mm_bbox=[10.0, 20.0, 1300.0, 40.0])])


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
        self.sent: list[dict] = []      # 재시도 사유를 확인하기 위한 요청 기록

    def create(self, **kwargs):
        self.calls += 1
        self.sent.append(kwargs)
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


def _make_page(cfg, ord_="B01", drawing_no="C1", page_no=1):
    """data/derived 의 페이지 산출물(png + text JSON) 한 쌍을 만든다."""
    base = cfg.derived_dir / "ds"
    stem = f"{ord_}_{drawing_no}_p{page_no}"
    png = base / "png" / f"{stem}.png"
    txt = base / "text" / f"{stem}.json"
    png.parent.mkdir(parents=True, exist_ok=True)
    txt.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 600), "white").save(png)
    txt.write_text(json.dumps({"schema": 1, "drawing_no": drawing_no, "page_no": page_no,
                               "paper_mm": PAPER_MM, "scale": 100.0,
                               "rotation_deg": 0, "fallback": False,
                               "texts": [{"x_mm": 1.0, "y_mm": 2.0, "h_mm": 5.0,
                                          "kind": "TEXT", "text": "300"}]},
                              ensure_ascii=False), encoding="utf-8")
    return PageRef(ord=ord_, drawing_no=drawing_no, page_no=page_no, region=ord_[0],
                   png=png, text=txt)


@pytest.fixture
def page(cfg):
    return _make_page(cfg)


def _cache_file(cfg):
    """이 데이터셋의 유일한 시트 캐시 파일 — 캐시 재검증 테스트가 내용을 갈아끼운다."""
    files = sorted((cfg.derived_dir / "ds" / "llm-cache" / "read").glob("*.json"))
    assert len(files) == 1, files
    return files[0]


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


def test_list_pages_region_is_single_char_not_prefix(cfg, page):
    """[F3] 계열 키는 ord 첫 글자 한 글자다 — 'C1' 은 접두 필터로 동작하면 안 된다."""
    _make_page(cfg, ord_="C10", drawing_no="C1")

    assert [p.ord for p in list_pages(cfg, "ds", region="C1")] == []
    assert [p.ord for p in list_pages(cfg, "ds", region="C")] == ["C10"]
    assert [p.ord for p in list_pages(cfg, "ds", ord_="C10")] == ["C10"]


def test_rejects_other_page_no_and_retries(cfg, page):
    """[F1] 이 시트에 없는 page_no 를 근거로 대면 반려·재시도한다 (acceptance §4)."""
    client = FakeClient([OTHER_PAGE, GOOD])
    out, usage = read_sheet(cfg, "ds", page, client=client)
    assert client.messages.calls == 2 and usage["retried"] is True
    assert out.readings[0].page_no == 1


def test_rejects_bbox_outside_paper_and_retries(cfg, page):
    """[F1] 용지 밖 mm_bbox 는 크롭 단계가 아니라 판독 단계에서 반려한다 (acceptance §7)."""
    client = FakeClient([OUTSIDE_PAPER, GOOD])
    out, usage = read_sheet(cfg, "ds", page, client=client)
    assert client.messages.calls == 2 and usage["retried"] is True
    assert out.ambiguities == [] and out.readings[0].mm_bbox == BBOX


def test_all_violations_collected_into_one_retry_note(cfg, page):
    """[F1·F2] 위반이 여러 건이면 첫 건에서 멈추지 않고 전건을 한 사유로 알린다."""
    client = FakeClient([TWO_VIOLATIONS, GOOD])
    read_sheet(cfg, "ds", page, client=client)

    note = client.messages.sent[1]["messages"][-1]["content"][-1]["text"]
    assert "2건" in note
    assert "p2" in note and "1300.0" in note


def test_cache_hit_revalidated_falls_back_to_real_call_when_stale(cfg, page):
    """[F1] 캐시된 시트 판독도 post_validate 를 거친다 — 낡은 캐시는 재호출로 취급."""
    read_sheet(cfg, "ds", page, client=FakeClient([GOOD]))
    _cache_file(cfg).write_text(OTHER_PAGE, encoding="utf-8")

    client = FakeClient([GOOD])
    out, usage = read_sheet(cfg, "ds", page, client=client)

    assert client.messages.calls == 1 and usage["cached"] is False
    assert out.readings[0].page_no == 1


def test_cache_only_raises_cache_miss_when_cached_output_invalid(cfg, page):
    """[F1] --cache-only 인데 캐시가 stale 이면 실호출 대신 CacheMissError (무과금 보증)."""
    read_sheet(cfg, "ds", page, client=FakeClient([GOOD]))
    _cache_file(cfg).write_text(OTHER_PAGE, encoding="utf-8")

    client = FakeClient([])
    with pytest.raises(CacheMissError):
        read_sheet(cfg, "ds", page, client=client, cache_only=True)
    assert client.messages.calls == 0
