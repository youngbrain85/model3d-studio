"""LLM 클라이언트 — 헤더·비용·구조화 호출. 실호출은 하지 않는다(가짜 클라이언트)."""

import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, Field, ValidationError

from m3d.config import load_config
from m3d.reading.client import (
    MODEL_READ,
    MODEL_REVIEW,
    PRICING,
    build_client,
    call_structured,
    estimate_cost,
    log_usage,
)


class Out(BaseModel):
    answer: str = Field(min_length=1)


GOOD = json.dumps({"answer": "ping"}, ensure_ascii=False)
BAD = json.dumps({"answer": ""}, ensure_ascii=False)     # min_length 위반
MSGS = [{"role": "user", "content": [{"type": "text", "text": "ping 이라고만 답해"}]}]


def _resp(text, *, in_tok=1000, out_tok=200, stop_reason="end_turn"):
    """SDK 응답 객체의 최소 형태 — content/usage/stop_reason 만 쓴다.

    text=None 은 텍스트 블록이 아예 없는 응답(사고 토큰이 max_tokens 를 먹은 경우)이다.
    """
    content = [] if text is None else [SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(
        content=content,
        usage=SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok),
        stop_reason=stop_reason,
    )


class FakeMessages:
    """texts 는 응답 텍스트, 또는 (텍스트, stop_reason) 쌍."""

    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        item = self.texts.pop(0)
        text, stop_reason = item if isinstance(item, tuple) else (item, "end_turn")
        return _resp(text, stop_reason=stop_reason)


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


def _usage_lines(cfg, dataset="ds"):
    path = cfg.derived_dir / dataset / "usage.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").strip().splitlines()]


def test_client_sends_workspace_header(cfg):
    """identity-linked 키는 이 헤더가 없으면 400 — 실측 확인된 요건."""
    client = build_client(cfg)
    assert client.default_headers["anthropic-workspace-id"] == "wrkspc_test"


def test_models_match_architecture_doc():
    assert MODEL_READ == "claude-sonnet-5"
    assert MODEL_REVIEW == "claude-fable-5"


def test_cost_uses_per_million_rates():
    """sonnet-5 = $2/$10 per 1M."""
    assert estimate_cost(MODEL_READ, 1_000_000, 0) == pytest.approx(2.0)
    assert estimate_cost(MODEL_READ, 0, 1_000_000) == pytest.approx(10.0)
    assert estimate_cost(MODEL_REVIEW, 1_000_000, 1_000_000) == pytest.approx(60.0)


def test_cost_zero_for_unknown_model():
    assert estimate_cost("mystery", 1000, 1000) == 0.0


def test_all_used_models_have_pricing():
    for m in (MODEL_READ, MODEL_REVIEW):
        assert m in PRICING


def test_log_usage_appends_jsonl_and_returns_row(cfg):
    row = log_usage(cfg, "ds", {"stage": "read", "model": MODEL_READ, "in": 100,
                                "out": 50, "cached": False, "attempt": 1,
                                "retried": False, "stop_reason": "end_turn"})
    log_usage(cfg, "ds", {"stage": "read", "model": MODEL_READ, "in": 0, "out": 0,
                          "cached": True, "attempt": 0, "retried": False,
                          "stop_reason": None})
    lines = _usage_lines(cfg)
    assert len(lines) == 2
    assert row == lines[0]
    assert lines[0]["cost_usd"] == pytest.approx(estimate_cost(MODEL_READ, 100, 50))
    assert lines[0]["attempt"] == 1 and lines[0]["stop_reason"] == "end_turn"
    assert "ts" in lines[0]


def test_call_structured_validates_and_uses_json_schema(cfg):
    client = FakeClient([GOOD])
    out, usage = call_structured(client, cfg, "ds", model=MODEL_READ, system="sys",
                                 messages=MSGS, out_format=Out, max_tokens=64,
                                 stage="smoke", extra={"ord": "B01"})
    assert out.answer == "ping"
    assert usage["cached"] is False and usage["retried"] is False and usage["ord"] == "B01"
    kw = client.messages.calls[0]
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert "properties" in kw["output_config"]["format"]["schema"]


def test_call_structured_retries_once_on_invalid_output(cfg):
    """검증 실패는 사유를 붙여 1회 재시도한다 (지식베이스 §8 — 근거 없는 응답은 반려)."""
    client = FakeClient([BAD, GOOD])
    out, usage = call_structured(client, cfg, "ds", model=MODEL_READ, system="sys",
                                 messages=MSGS, out_format=Out, max_tokens=64,
                                 stage="smoke")
    assert out.answer == "ping"
    assert len(client.messages.calls) == 2 and usage["retried"] is True
    assert abs(usage["cost_usd"] - 0.008) < 1e-9          # 반환 usage 의 비용은 재시도 포함 합계(각 호출 $0.004) — M6 잡 원장 정합
    retry_blocks = client.messages.calls[1]["messages"][-1]["content"]
    assert any("[재시도]" in b["text"] for b in retry_blocks)


def test_call_structured_logs_every_attempt(cfg):
    """parse 대신 create 를 쓰는 이유 — 실패한 시도의 토큰도 원장에 남아야 한다."""
    client = FakeClient([BAD, BAD])
    with pytest.raises(ValidationError):
        call_structured(client, cfg, "ds", model=MODEL_READ, system="sys",
                        messages=MSGS, out_format=Out, max_tokens=64, stage="smoke")
    lines = _usage_lines(cfg)
    assert [x["attempt"] for x in lines] == [1, 2]
    assert all(x["cost_usd"] > 0 for x in lines)


def _retry_note(client) -> str:
    """2번째 요청의 마지막 블록 = 재시도 안내문."""
    return client.messages.calls[1]["messages"][-1]["content"][-1]["text"]


def _call(cfg, client, *, stage="smoke", post_validate=None):
    return call_structured(client, cfg, "ds", model=MODEL_READ, system="sys",
                           messages=MSGS, out_format=Out, max_tokens=64, stage=stage,
                           post_validate=post_validate)


def test_retry_note_for_truncated_json_is_max_tokens_specific(cfg):
    """[F2] max_tokens 로 JSON 이 잘린 것을 '스키마 위반' 으로 알리면 모델이 엉뚱한
    수정을 한다 — 서술을 줄이라는 전용 문구를 준다."""
    client = FakeClient([('{"answer": "pi', "max_tokens"), GOOD])

    out, usage = _call(cfg, client)

    assert out.answer == "ping" and usage["retried"] is True
    note = _retry_note(client)
    assert "max_tokens" in note and "절단" in note
    assert "항목 수는 유지" in note


def test_missing_text_block_on_max_tokens_retries_once(cfg):
    """[F2] 텍스트 블록 없이 max_tokens 로 끝난 응답은 즉시 죽지 않고 1회 흡수한다."""
    client = FakeClient([(None, "max_tokens"), GOOD])

    out, _usage = _call(cfg, client)

    assert out.answer == "ping"
    assert len(client.messages.calls) == 2
    assert "절단" in _retry_note(client)
    # 실패한 시도의 토큰도 원장에 남는다
    assert [x["attempt"] for x in _usage_lines(cfg)] == [1, 2]


def test_missing_text_block_without_max_tokens_still_raises(cfg):
    """절단이 아닌 원인으로 텍스트가 없으면 조용히 재시도하지 않는다."""
    client = FakeClient([(None, "end_turn")])
    with pytest.raises(RuntimeError):
        _call(cfg, client)
    assert len(client.messages.calls) == 1


def test_missing_text_block_twice_on_max_tokens_raises(cfg):
    client = FakeClient([(None, "max_tokens"), (None, "max_tokens")])
    with pytest.raises(RuntimeError):
        _call(cfg, client)
    assert len(client.messages.calls) == 2


def test_retry_reason_keeps_long_validation_message(cfg):
    """[F2] 사유를 500자에서 자르면 위반 전건 목록의 뒷부분이 사라진다."""
    long_reason = "검증 실패 3건: " + "가" * 1500
    seen = {"n": 0}

    def _pv(_out):
        seen["n"] += 1
        if seen["n"] == 1:
            raise ValueError(long_reason)

    client = FakeClient([GOOD, GOOD])
    _call(cfg, client, post_validate=_pv)

    assert long_reason in _retry_note(client)


def test_retry_note_read_stage_carries_reading_specific_guidance(cfg):
    client = FakeClient([BAD, GOOD])
    _call(cfg, client, stage="read")
    assert "선택지 2~4개" in _retry_note(client)


def test_retry_note_merge_stage_drops_reading_specific_guidance(cfg):
    """[F2] 판독 전용 문구(선택지 2~4개)를 통합 재시도에 붙이면 지시가 어긋난다."""
    client = FakeClient([BAD, GOOD])
    _call(cfg, client, stage="merge")
    note = _retry_note(client)
    assert "선택지 2~4개" not in note
    assert "ord" in note and "mm_bbox" in note


def test_retry_note_review_stage_targets_new_ambiguity(cfg):
    client = FakeClient([BAD, GOOD])
    _call(cfg, client, stage="review")
    note = _retry_note(client)
    assert "선택지 2~4개" not in note
    assert "애매성" in note


def test_call_structured_disables_thinking_for_sonnet(cfg):
    """Sonnet 5 는 thinking 생략 시 adaptive 가 기본 ON — 사고 토큰이 max_tokens 를 먹어
    텍스트 블록 없이 끝난다(실측 2026-09-02 B01). 구조화 출력엔 끈다."""
    client = FakeClient([GOOD])
    call_structured(client, cfg, "ds", model=MODEL_READ, system="sys",
                    messages=MSGS, out_format=Out, max_tokens=64, stage="smoke")
    assert client.messages.calls[0]["thinking"] == {"type": "disabled"}


def test_call_structured_omits_thinking_for_fable(cfg):
    """Fable 은 thinking 이 항상 ON 이고 disabled 는 400 — 파라미터를 보내지 않는다."""
    client = FakeClient([GOOD])
    call_structured(client, cfg, "ds", model=MODEL_REVIEW, system="sys",
                    messages=MSGS, out_format=Out, max_tokens=64, stage="smoke")
    assert "thinking" not in client.messages.calls[0]
