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
    """SDK 응답 객체의 최소 형태 — content/usage/stop_reason 만 쓴다."""
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok),
        stop_reason=stop_reason,
    )


class FakeMessages:
    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
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
