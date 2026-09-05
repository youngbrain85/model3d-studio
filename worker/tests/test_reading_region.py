"""적대적 검토 반영 + 통합 결과 ord 검증 (설계서 §4-2·§4-3)."""

import json
from types import SimpleNamespace

import pytest

from m3d.config import load_config
from m3d.models import AmbiguityOption
from m3d.reading.cache import CacheMissError
from m3d.reading.region import apply_findings, merge_region, review_region
from m3d.reading.schema import (
    MergedAmbiguity,
    MergedReading,
    RegionMergeOut,
    ReviewFinding,
    ReviewOut,
    SheetReadOut,
)

BBOX = [1.0, 2.0, 3.0, 4.0]
PAPER = (841.0, 594.0)              # A3 — acceptance §4·§7 재현 기준 용지


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


def _merge_json(ords):
    return json.dumps({
        "readings": [{"item": "두께", "value_raw": "300", "unit": "mm", "page_no": 1,
                      "mm_bbox": BBOX, "crosscheck": None, "status": "확정", "ord": o}
                     for o in ords],
        "ambiguities": [], "notes": []}, ensure_ascii=False)


def _reading_dict(item="두께", ord_="B01", page_no=1, mm_bbox=None, status="확정"):
    return {"item": item, "value_raw": "300", "unit": "mm", "page_no": page_no,
            "mm_bbox": mm_bbox if mm_bbox is not None else BBOX,
            "crosscheck": None, "status": status, "ord": ord_}


def _ambiguity_dict(item="애매", ord_="B01", page_no=1, mm_bbox=None):
    return {"item": item, "page_no": page_no,
            "mm_bbox": mm_bbox if mm_bbox is not None else BBOX,
            "options": [{"label": "a", "basis": "b"}, {"label": "c", "basis": "d"}],
            "model_impact": "영향", "ord": ord_}


def _merge_json_full(readings=None, ambiguities=None):
    return json.dumps({"readings": readings or [], "ambiguities": ambiguities or [],
                       "notes": []}, ensure_ascii=False)


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


def test_status_change_composite_label_token_match_slash_suffix():
    """acceptance §3 — 어순 때문에 부분 문자열로는 마지막 항목만 잡히던 슬래시 합성
    라벨("P1/P3/P4 희생관 연장")도 토큰 부분집합 일치로 전부 잡는다."""
    readings = [_r("P1 희생관 연장", ord_="F01"), _r("P3 희생관 연장", ord_="F01"),
                _r("P4 희생관 연장", ord_="F01"), _r("무관 항목", ord_="F01")]
    target = "P1/P3/P4 희생관 연장(17.990/33.610/29.930) 및 제원"

    finals, _amb, log = apply_findings(
        readings, [],
        [ReviewFinding(target_item=target, verdict="상태변경", reason="과신",
                       new_status="추정")])

    lowered = {r.item for r in finals if r.status == "추정"}
    assert lowered == {"P1 희생관 연장", "P3 희생관 연장", "P4 희생관 연장"}
    assert [r.status for r in finals if r.item == "무관 항목"] == ["확정"]
    assert log[0]["applied"] is True
    assert "토큰일치 3건" in log[0]["note"]


def test_status_change_composite_label_token_match_parenthetical_list():
    """공통 접두 + 괄호 안 pier 목록 형태("받침 종류(P1/P4/P7/P8) …")도 토큰
    부분집합 일치로 대응 항목 전부를 잡는다 — F 계열 실측 두 번째 대상없음 사례."""
    readings = [_r("P1 받침 종류", ord_="F01"), _r("P4 받침 종류", ord_="F01"),
                _r("P7 받침 종류", ord_="F01"), _r("P8 받침 종류", ord_="F01"),
                _r("무관 항목", ord_="F01")]
    target = "받침 종류(P1/P4/P7/P8) 및 A/B(825/825, 845/845)"

    finals, _amb, log = apply_findings(
        readings, [],
        [ReviewFinding(target_item=target, verdict="상태변경", reason="과신",
                       new_status="추정")])

    lowered = {r.item for r in finals if r.status == "추정"}
    assert lowered == {"P1 받침 종류", "P4 받침 종류", "P7 받침 종류", "P8 받침 종류"}
    assert [r.status for r in finals if r.item == "무관 항목"] == ["확정"]
    assert log[0]["applied"] is True
    assert "토큰일치 4건" in log[0]["note"]


def test_status_change_single_token_item_excluded_from_fallback():
    """1토큰 item("두께")은 그 토큰이 target 에 있어도 오매칭 위험 때문에
    폴백에서 제외한다 — 완전 일치가 없으면 대상없음으로 남는다."""
    readings = [_r("두께", ord_="F01")]
    target = "두께/색상 등 제원"

    finals, _amb, log = apply_findings(
        readings, [],
        [ReviewFinding(target_item=target, verdict="상태변경", reason="과신",
                       new_status="추정")])

    assert finals[0].status == "확정"
    assert log[0]["applied"] is False and "대상 없음" in log[0]["note"]


def test_status_change_no_exact_or_token_match_stays_untouched():
    """완전 일치도 토큰 일치도 없으면 기존대로 대상없음으로 남는다."""
    readings = [_r("완전 무관")]

    finals, _amb, log = apply_findings(
        readings, [],
        [ReviewFinding(target_item="존재하지 않는 합성 라벨", verdict="상태변경",
                       reason="x", new_status="추정")])

    assert finals[0].status == "확정"
    assert log[0]["applied"] is False and "대상 없음" in log[0]["note"]


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
    pages = {("B01", 1): PAPER}
    client = FakeClient([_merge_json(["Z99"]), _merge_json(["B01"])])
    out, usage = merge_region(cfg, "ds", "B", sheet_outs, pages, client=client)
    assert client.messages.calls == 2
    assert [r.ord for r in out.readings] == ["B01"]
    assert usage["retried"] is True


def test_merge_rejects_unknown_page_no_and_retries(cfg):
    """acceptance §4 — A03 page_no=2 유실 재발 방지: 존재하지 않는 페이지는 반려·재시도."""
    sheet_outs = [("B01", SheetReadOut(readings=[], ambiguities=[]))]
    pages = {("B01", 1): PAPER}                 # B01 은 p1 만 존재
    bad = _merge_json_full(readings=[_reading_dict(page_no=2)])   # 존재하지 않는 p2 를 근거로 댐
    good = _merge_json_full(readings=[_reading_dict(page_no=1)])
    client = FakeClient([bad, good])

    out, usage = merge_region(cfg, "ds", "B", sheet_outs, pages, client=client)

    assert client.messages.calls == 2
    assert out.readings[0].page_no == 1
    assert usage["retried"] is True


def test_merge_rejects_bbox_outside_paper_and_retries(cfg):
    """acceptance §7 — A02/D02 처럼 mm_bbox 가 용지 밖이면 크롭 실패 전에 여기서 반려."""
    sheet_outs = [("B01", SheetReadOut(readings=[], ambiguities=[]))]
    pages = {("B01", 1): PAPER}
    bad = _merge_json_full(
        readings=[_reading_dict(mm_bbox=[459.7, 130.0, 900.0, 148.0])])   # x1=900 > 841
    good = _merge_json_full(readings=[_reading_dict(mm_bbox=BBOX)])
    client = FakeClient([bad, good])

    out, usage = merge_region(cfg, "ds", "B", sheet_outs, pages, client=client)

    assert client.messages.calls == 2
    assert out.readings[0].mm_bbox == BBOX
    assert usage["retried"] is True


def test_review_new_ambiguity_bad_page_no_retries(cfg):
    """review 의 new_ambiguity 도 동일한 (ord,page_no)·bbox 검증을 거친다."""
    merged = RegionMergeOut(readings=[_r("두께")], ambiguities=[], notes=[])
    pages = {("B01", 1): PAPER}
    bad_finding = {"target_item": "두께", "verdict": "신규애매성", "reason": "상충",
                   "new_status": None, "new_ambiguity": _ambiguity_dict(page_no=9)}
    good_finding = {**bad_finding, "new_ambiguity": _ambiguity_dict(page_no=1)}
    bad = json.dumps({"findings": [bad_finding]}, ensure_ascii=False)
    good = json.dumps({"findings": [good_finding]}, ensure_ascii=False)
    client = FakeClient([bad, good])

    out, usage = review_region(cfg, "ds", "B", merged, pages, client=client)

    assert client.messages.calls == 2
    assert out.findings[0].new_ambiguity.page_no == 1
    assert usage["retried"] is True


def test_review_new_ambiguity_bbox_outside_paper_retries(cfg):
    merged = RegionMergeOut(readings=[_r("두께")], ambiguities=[], notes=[])
    pages = {("B01", 1): PAPER}
    bad_finding = {"target_item": "두께", "verdict": "신규애매성", "reason": "상충",
                   "new_status": None,
                   "new_ambiguity": _ambiguity_dict(mm_bbox=[1230.0, 120.0, 1600.0, 270.0])}
    good_finding = {**bad_finding, "new_ambiguity": _ambiguity_dict(mm_bbox=BBOX)}
    bad = json.dumps({"findings": [bad_finding]}, ensure_ascii=False)
    good = json.dumps({"findings": [good_finding]}, ensure_ascii=False)
    client = FakeClient([bad, good])

    out, usage = review_region(cfg, "ds", "B", merged, pages, client=client)

    assert client.messages.calls == 2
    assert out.findings[0].new_ambiguity.mm_bbox == BBOX
    assert usage["retried"] is True


def test_merge_reports_all_violations_in_one_message(cfg):
    """[F2] 첫 위반에서 멈추면 재시도가 남은 위반을 모르고 같은 실수를 반복한다 —
    위반 전건을 한 사유로 모아 알린다."""
    sheet_outs = [("B01", SheetReadOut(readings=[], ambiguities=[]))]
    pages = {("B01", 1): PAPER}
    bad = _merge_json_full(
        readings=[_reading_dict(item="A", page_no=2),                       # 없는 페이지
                  _reading_dict(item="B", mm_bbox=[10.0, 10.0, 900.0, 20.0])])  # 용지 밖
    good = _merge_json_full(readings=[_reading_dict(page_no=1)])
    client = FakeClient([bad, good])

    merge_region(cfg, "ds", "B", sheet_outs, pages, client=client)

    note = client.messages.sent[1]["messages"][-1]["content"][-1]["text"]
    assert "2건" in note
    assert "p2" in note and "900.0" in note


def test_merge_cache_hit_revalidated_falls_back_to_real_call_when_stale(cfg):
    """캐시된 통합 결과도 post_validate 를 거친다 — 낡은 캐시는 재호출로 취급한다."""
    sheet_outs = [("B01", SheetReadOut(readings=[], ambiguities=[]))]
    pages_v1 = {("B01", 1): PAPER}
    good = _merge_json_full(readings=[_reading_dict(page_no=1)])

    client1 = FakeClient([good])
    merge_region(cfg, "ds", "B", sheet_outs, pages_v1, client=client1)
    assert client1.messages.calls == 1

    # 같은 pages 로 재호출하면 캐시 히트(재호출 없음)
    client2 = FakeClient([])
    out2, usage2 = merge_region(cfg, "ds", "B", sheet_outs, pages_v1, client=client2)
    assert usage2["cached"] is True and client2.messages.calls == 0
    assert out2.readings[0].page_no == 1

    # 페이지 재번호 등으로 known 페이지가 바뀌어 캐시된 출력(p1)이 새 검증에 실패하면
    # (§4 시나리오와 동형) 재호출로 전환한다 — 새 응답은 새 pages 에 맞는 p2 를 낸다
    pages_v2 = {("B01", 2): PAPER}                # B01 p1 이 더는 known 페이지가 아님
    good_p2 = _merge_json_full(readings=[_reading_dict(page_no=2)])
    client3 = FakeClient([good_p2])
    out3, usage3 = merge_region(cfg, "ds", "B", sheet_outs, pages_v2, client=client3)
    assert client3.messages.calls == 1
    assert usage3["cached"] is False
    assert out3.readings[0].page_no == 2


def test_merge_cache_only_raises_cache_miss_when_cached_output_invalid(cfg):
    """--cache-only 인데 캐시된 출력이 새 검증에 실패하면 실호출 대신 CacheMissError."""
    sheet_outs = [("B01", SheetReadOut(readings=[], ambiguities=[]))]
    pages_v1 = {("B01", 1): PAPER}
    good = _merge_json_full(readings=[_reading_dict(page_no=1)])
    merge_region(cfg, "ds", "B", sheet_outs, pages_v1, client=FakeClient([good]))

    pages_v2: dict = {}
    with pytest.raises(CacheMissError):
        merge_region(cfg, "ds", "B", sheet_outs, pages_v2, client=FakeClient([]),
                     cache_only=True)
