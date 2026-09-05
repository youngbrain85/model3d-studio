"""Anthropic 클라이언트·비용 계산·사용량 로깅·구조화 호출 (설계서 §2-1).

실측 확정 사항 (2026-08-30):
  - identity-linked 키는 요청마다 anthropic-workspace-id 헤더가 필요하다.
    SDK 의 ANTHROPIC_WORKSPACE_ID env 자동 인식은 api_key 경로에서 동작하지 않는다.
  - 구조화 출력은 messages.create(output_config={"format": {"type": "json_schema",
    "schema": anthropic.transform_schema(Out)}}) 로 넘긴다.
    output_config={"format": Class} 는 TypeError 로 죽는다.
  - messages.parse 는 쓰지 않는다 — 검증 실패 시 응답 객체 없이
    ValidationError 가 올라와 그 시도의 usage 를 기록할 수 없다.
  - thinking 규약: Sonnet 계열은 thinking={"type": "disabled"} 를 명시한다(생략 시
    adaptive thinking 이 기본 ON 이라 사고 토큰이 max_tokens 를 소진, 텍스트 블록 없이
    끝난다 — 실측 2026-09-02). Fable/Mythos 계열은 thinking 이 항상 ON 이고 disabled 는
    400 이므로 파라미터를 생략한다.
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


# 재시도 사유 상한. 500자에서 자르면 "검증 실패 5건: …" 목록의 뒷부분이 사라져
# 모델이 남은 위반을 모른 채 같은 실수를 되풀이한다.
MAX_RETRY_REASON_CHARS = 3000

# 단계별 안내문 — 판독 전용 문구(선택지 2~4개)를 통합·검토에 붙이면 지시가 어긋난다.
STAGE_RETRY_GUIDANCE = {
    "read": "모든 필수 필드를 채우고(page_no·mm_bbox 4개 실수·선택지 2~4개) "
            "같은 JSON 스키마로만 답하라. mm_bbox 는 sheet_text 의 x_mm/y_mm 와 같은 "
            "좌표계(용지 mm, 원점 좌하단, 용지 크기 안)로 적는다 — 이미지 픽셀 좌표가 아니다.",
    "merge": "각 항목의 ord·page_no 는 입력에 실제로 있는 시트·페이지여야 하고, "
             "mm_bbox 는 그 페이지 용지(mm) 안이어야 한다. 같은 JSON 스키마로만 답하라.",
    "review": "신규 애매성의 ord·page_no 는 통합 결과에 있는 시트·페이지여야 하고, "
              "mm_bbox 는 그 페이지 용지(mm) 안이어야 한다. 같은 JSON 스키마로만 답하라.",
}
DEFAULT_RETRY_GUIDANCE = "같은 JSON 스키마로만 답하라."

# 절단은 스키마 위반이 아니다 — "필드를 채우라"고 하면 응답이 더 길어져 또 잘린다.
TRUNCATED_REASON = ("직전 응답이 max_tokens 에서 절단됨 — 각 항목의 서술을 줄이고 "
                    "항목 수는 유지하며 JSON 만 출력하라.")


def _with_retry_note(messages: list[dict], reason: str, *, stage: str,
                     truncated: bool = False) -> list[dict]:
    """마지막 user 메시지 끝에 재시도 사유를 덧붙인다.

    새 user 메시지를 붙이지 않는다 — Messages API 는 역할 교대를 요구한다.
    `truncated` 면 사유 대신 절단 전용 문구를 쓴다.
    """
    last = messages[-1]
    head = TRUNCATED_REASON if truncated else f"직전 응답이 검증에 실패했다: {reason}"
    guidance = STAGE_RETRY_GUIDANCE.get(stage, DEFAULT_RETRY_GUIDANCE)
    note = {"type": "text", "text": f"[재시도] {head}\n{guidance}"}
    return [*messages[:-1], {**last, "content": [*last["content"], note]}]


THINKING_ALWAYS_ON_PREFIXES = ("claude-fable", "claude-mythos")


def _thinking_kwargs(model: str) -> dict:
    """모델별 thinking 파라미터 (Global Constraints 'thinking 규약').

    Sonnet 5 는 생략 시 adaptive thinking 이 기본 ON 이라 사고 토큰이 max_tokens 를 먹고
    텍스트 블록 없이 max_tokens 로 끝난다(실측 2026-09-02). 구조화 JSON 출력에는 사고가
    필요 없으므로 끈다. Fable/Mythos 는 항상 ON 이고 disabled 가 400 이므로 생략한다.
    """
    if model.startswith(THINKING_ALWAYS_ON_PREFIXES):
        return {}
    return {"thinking": {"type": "disabled"}}


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
            **_thinking_kwargs(model),
        )
        usage = log_usage(cfg, dataset, {
            **(extra or {}),
            "stage": stage, "model": model,
            "in": resp.usage.input_tokens, "out": resp.usage.output_tokens,
            "cached": False, "attempt": attempt, "retried": attempt > 1,
            "stop_reason": resp.stop_reason,
        })
        truncated = resp.stop_reason == "max_tokens"
        text = next((b.text for b in resp.content if b.type == "text"), None)
        if text is None:
            # 사고 토큰이 max_tokens 를 먹어 텍스트 블록이 아예 없는 경우(실측 2026-09-02)는
            # 재시도로 흡수한다 — 원인이 다른 '텍스트 없음' 은 그대로 실패시킨다.
            if truncated and attempt == 1:
                attempt_messages = _with_retry_note(messages, "", stage=stage,
                                                    truncated=True)
                continue
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
            attempt_messages = _with_retry_note(
                messages, str(exc)[:MAX_RETRY_REASON_CHARS], stage=stage,
                truncated=truncated)
    raise AssertionError("unreachable")
