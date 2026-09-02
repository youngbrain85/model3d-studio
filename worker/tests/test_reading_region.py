"""적대적 검토 반영 + 통합 결과 ord 검증 (설계서 §4-2·§4-3)."""

import json
from types import SimpleNamespace

import pytest

from m3d.config import load_config
from m3d.models import AmbiguityOption
from m3d.reading.region import apply_findings, merge_region
from m3d.reading.schema import (
    MergedAmbiguity,
    MergedReading,
    ReviewFinding,
    SheetReadOut,
)

BBOX = [1.0, 2.0, 3.0, 4.0]


def _r(item, status="확정", ord_="B01"):
    return MergedReading(item=item, value_raw="300", unit="mm", page_no=1,
                         mm_bbox=BBOX, crosscheck=None, status=status, ord=ord_)


def _a(item, ord_="B01"):
    return MergedAmbiguity(item=item, page_no=1, mm_bbox=BBOX,
                           options=[AmbiguityOption(label="a", basis="b"),
                                    AmbiguityOption(label="c", basis="d")],
                           model_impact="영향", ord=ord_)


def _resp(text):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=1000, output_tokens=200),
        stop_reason="end_turn")


class FakeMessages:
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


def _merge_json(ords):
    return json.dumps({
        "readings": [{"item": "두께", "value_raw": "300", "unit": "mm", "page_no": 1,
                      "mm_bbox": BBOX, "crosscheck": None, "status": "확정", "ord": o}
                     for o in ords],
        "ambiguities": [], "notes": []}, ensure_ascii=False)


def test_status_change_applied():
    readings, _amb, log = apply_findings(
        [_r("두께")], [],
        [ReviewFinding(target_item="두께", verdict="상태변경",
                       reason="단일 소스", new_status="추정")])
    assert readings[0].status == "추정" and readings[0].ord == "B01"
    assert log[0]["applied"] is True


def test_new_ambiguity_appended():
    _readings, ambiguities, _log = apply_findings(
        [_r("두께")], [_a("기존")],
        [ReviewFinding(target_item="두께", verdict="신규애매성", reason="상충",
                       new_ambiguity=_a("신규", ord_="B02"))])
    assert [(a.item, a.ord) for a in ambiguities] == [("기존", "B01"), ("신규", "B02")]


def test_rejection_changes_nothing_but_is_logged():
    """기각도 기록한다 — 무엇을 왜 받아들이지 않았는지 남아야 한다 (§3)."""
    readings, ambiguities, log = apply_findings(
        [_r("두께")], [],
        [ReviewFinding(target_item="두께", verdict="기각", reason="원문 재현 결과 정합")])
    assert readings[0].status == "확정" and ambiguities == []
    assert log[0]["verdict"] == "기각" and log[0]["applied"] is False


def test_unknown_target_is_logged_not_crashed():
    """존재하지 않는 항목을 지적해도 죽지 않고 미적용으로 기록한다."""
    readings, _a, log = apply_findings(
        [_r("두께")], [],
        [ReviewFinding(target_item="없는항목", verdict="상태변경", reason="x",
                       new_status="추정")])
    assert readings[0].status == "확정"
    assert log[0]["applied"] is False and "대상 없음" in log[0]["note"]


def test_multiple_findings_all_recorded():
    readings, _a, log = apply_findings(
        [_r("A"), _r("B")],
        [],
        [ReviewFinding(target_item="A", verdict="상태변경", reason="r",
                       new_status="검토지적"),
         ReviewFinding(target_item="B", verdict="기각", reason="r2")])
    assert {r.item: r.status for r in readings} == {"A": "검토지적", "B": "확정"}
    assert len(log) == 2


def test_same_item_name_all_lowered():
    """동명 항목이 여럿이면 전부에 적용한다 — 낮추기 전용이라 보수적이다."""
    readings, _a, log = apply_findings(
        [_r("두께", ord_="B01"), _r("두께", ord_="B02")],
        [],
        [ReviewFinding(target_item="두께", verdict="상태변경", reason="r",
                       new_status="추정")])
    assert [r.status for r in readings] == ["추정", "추정"]
    assert log[0]["applied"] is True and "동명 2건" in log[0]["note"]


def test_merge_rejects_unknown_ord_and_retries(cfg):
    """입력에 없는 시트를 지어내면 스키마 위반과 똑같이 반려·재시도한다 (§4-2)."""
    sheet_outs = [("B01", SheetReadOut(readings=[], ambiguities=[]))]
    client = FakeClient([_merge_json(["Z99"]), _merge_json(["B01"])])
    out, usage = merge_region(cfg, "ds", "B", sheet_outs, client=client)
    assert client.messages.calls == 2
    assert [r.ord for r in out.readings] == ["B01"]
    assert usage["retried"] is True
