"""Anthropic 클라이언트·비용 계산·사용량 로깅·구조화 호출 (설계서 §2-1).

실측 확정 사항 (2026-08-30):
  - identity-linked 키는 요청마다 anthropic-workspace-id 헤더가 필요하다.
    SDK 의 ANTHROPIC_WORKSPACE_ID env 자동 인식은 api_key 경로에서 동작하지 않는다.
  - 구조화 출력은 messages.create(output_config={"format": {"type": "json_schema",
    "schema": anthropic.transform_schema(Out)}}) 로 넘긴다.
    output_config={"format": Class} 는 TypeError 로 죽는다.
  - messages.parse 는 쓰지 않는다 — 검증 실패 시 응답 객체 없이
    ValidationError 가 올라와 그 시도의 usage 를 기록할 수 없다.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import anthropic

from m3d.config import Config

MODEL_READ = "claude-sonnet-5"    # 판독·통합 (아키텍처 §2)
MODEL_REVIEW = "claude-fable-5"   # 적대적 검토

# 모델 → ($ per 1M input, $ per 1M output)
PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-5": (2.0, 10.0),
    "claude-fable-5": (10.0, 50.0),
}


def build_client(cfg: Config) -> anthropic.Anthropic:
    ws = cfg.require_anthropic_workspace_id()
    return anthropic.Anthropic(
        api_key=cfg.require_anthropic_api_key(),
        default_headers={"anthropic-workspace-id": ws},
    )


def estimate_cost(model: str, in_tokens: int, out_tokens: int) -> float:
    rates = PRICING.get(model)
    if rates is None:
        return 0.0
    return in_tokens / 1_000_000 * rates[0] + out_tokens / 1_000_000 * rates[1]


def log_usage(cfg: Config, dataset: str, record: dict) -> dict:
    """usage.jsonl 에 한 줄 적재하고 그 행을 돌려준다 — 지출을 눈에 보이게 한다."""
    path = cfg.derived_dir / dataset / "usage.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **record,
        "cost_usd": round(
            estimate_cost(record.get("model", ""), record.get("in", 0), record.get("out", 0)), 6
        ),
    }
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _with_retry_note(messages: list[dict], reason: str) -> list[dict]:
    """마지막 user 메시지 끝에 재시도 사유를 덧붙인다.

    새 user 메시지를 붙이지 않는다 — Messages API 는 역할 교대를 요구한다.
    """
    last = messages[-1]
    note = {"type": "text", "text":
            f"[재시도] 직전 응답이 검증에 실패했다: {reason}\n"
            "모든 필수 필드를 채우고(page_no·mm_bbox 4개 실수·선택지 2~4개) "
            "같은 JSON 스키마로만 답하라."}
    return [*messages[:-1], {**last, "content": [*last["content"], note]}]


def call_structured(client, cfg: Config, dataset: str, *, model: str, system: str,
                    messages: list[dict], out_format, max_tokens: int, stage: str,
                    extra: dict | None = None, post_validate=None) -> tuple[object, dict]:
    """구조화 출력 1회 호출. 검증 실패 시 사유를 붙여 1회 재시도한다.

    매 시도마다 usage 를 **먼저** 적재한다 — 실패한 시도의 토큰도 원장에 남긴다
    (Global Constraints "모든 실호출은 usage.jsonl 에").
    `post_validate(out)` 로 스키마 밖 규칙(예: 입력에 없는 ord 금지)을 걸 수 있고,
    거기서 오른 ValueError 는 스키마 검증 실패와 똑같이 재시도된다.
    """
    schema = anthropic.transform_schema(out_format)
    attempt_messages = messages
    for attempt in (1, 2):
        resp = client.messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=attempt_messages,
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        usage = log_usage(cfg, dataset, {
            **(extra or {}),
            "stage": stage, "model": model,
            "in": resp.usage.input_tokens, "out": resp.usage.output_tokens,
            "cached": False, "attempt": attempt, "retried": attempt > 1,
            "stop_reason": resp.stop_reason,
        })
        text = next((b.text for b in resp.content if b.type == "text"), None)
        if text is None:
            raise RuntimeError(
                f"구조화 출력 없음 (stage={stage}, stop_reason={resp.stop_reason})")
        try:
            out = out_format.model_validate_json(text)
            if post_validate is not None:
                post_validate(out)
            return out, usage
        except ValueError as exc:   # pydantic ValidationError 는 ValueError 하위
            if attempt == 2:
                raise
            attempt_messages = _with_retry_note(messages, str(exc)[:500])
    raise AssertionError("unreachable")
