"""계열 통합 + 적대적 검토 (설계서 §4-2·§4-3)."""

from __future__ import annotations

import json

from m3d.config import Config
from m3d.reading import prompts
from m3d.reading.cache import (
    CacheMissError,
    cache_key,
    cache_path,
    load_cached,
    save_cached,
    schema_fingerprint,
)
from m3d.reading.client import (
    MODEL_READ,
    MODEL_REVIEW,
    build_client,
    call_structured,
    log_usage,
)
from m3d.reading.schema import (
    FinalReading,
    MergedAmbiguity,
    MergedReading,
    RegionMergeOut,
    ReviewFinding,
    ReviewOut,
    SheetReadOut,
)

MAX_TOKENS = 16000


def _call(cfg: Config, dataset: str, client, *, stage: str, region: str, model: str,
          system: str, user_text: str, out_format, key_payload: dict,
          force: bool, cache_only: bool, post_validate=None):
    key = cache_key({
        "kind": stage,
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "schema": schema_fingerprint(out_format),
        "user_text": [user_text],
        "inputs": key_payload,
    })
    path = cache_path(cfg, dataset, stage, key)
    if not force:
        cached = load_cached(path)
        if cached is not None:
            usage = log_usage(cfg, dataset, {
                "stage": stage, "region": region, "model": model, "in": 0, "out": 0,
                "cached": True, "attempt": 0, "retried": False, "stop_reason": None})
            return out_format.model_validate(cached), usage

    if cache_only:
        raise CacheMissError(stage, region, key)

    out, usage = call_structured(
        client or build_client(cfg), cfg, dataset,
        model=model, system=system,
        messages=[{"role": "user", "content": [{"type": "text", "text": user_text}]}],
        out_format=out_format, max_tokens=MAX_TOKENS, stage=stage,
        extra={"region": region}, post_validate=post_validate,
    )
    save_cached(path, out.model_dump())
    return out, usage


def merge_region(cfg: Config, dataset: str, region: str,
                 sheet_outs: list[tuple[str, SheetReadOut]], *,
                 force: bool = False, cache_only: bool = False, client=None):
    """sheet_outs: [(ord, SheetReadOut)] — 계열 내 전 페이지 판독."""
    payload = [{"ord": o, **out.model_dump()} for o, out in sheet_outs]
    known = {o for o, _ in sheet_outs}
    user = ("계열 내 시트별 판독 결과다. 하나의 치수 정본으로 통합하라.\n"
            "각 항목의 ord 는 그 값이 실제로 적힌 시트의 ord 여야 한다.\n"
            + json.dumps(payload, ensure_ascii=False))

    def _check(out: RegionMergeOut) -> None:
        seen = {r.ord for r in out.readings} | {a.ord for a in out.ambiguities}
        bad = sorted(seen - known)
        if bad:
            raise ValueError(f"통합 결과에 입력에 없는 ord: {bad}")

    return _call(cfg, dataset, client, stage="merge", region=region, model=MODEL_READ,
                 system=prompts.merge_system(region), user_text=user,
                 out_format=RegionMergeOut,
                 key_payload={"sheets": cache_key({"p": payload})},
                 force=force, cache_only=cache_only, post_validate=_check)


def review_region(cfg: Config, dataset: str, region: str, merged: RegionMergeOut, *,
                  force: bool = False, cache_only: bool = False, client=None):
    known = {r.ord for r in merged.readings} | {a.ord for a in merged.ambiguities}
    user = ("아래는 한 계열의 통합 판독 결과다. 반박을 시도하라.\n"
            + json.dumps(merged.model_dump(), ensure_ascii=False))

    def _check(out: ReviewOut) -> None:
        bad = sorted({f.new_ambiguity.ord for f in out.findings
                      if f.new_ambiguity is not None} - known)
        if bad:
            raise ValueError(f"신규 애매성에 통합 결과에 없는 ord: {bad}")

    return _call(cfg, dataset, client, stage="review", region=region, model=MODEL_REVIEW,
                 system=prompts.review_system(region), user_text=user,
                 out_format=ReviewOut,
                 key_payload={"merged": cache_key({"m": merged.model_dump()})},
                 force=force, cache_only=cache_only, post_validate=_check)


def apply_findings(readings: list[MergedReading], ambiguities: list[MergedAmbiguity],
                   findings: list[ReviewFinding]
                   ) -> tuple[list[FinalReading], list[MergedAmbiguity], list[dict]]:
    """검토 지적을 최종 결과에 반영한다. 기각도 기록으로 남긴다 (§3).

    상태는 낮추기만 한다 — '확정' 승격은 ReviewFinding 스키마가 이미 막는다.
    지적이 없는 항목도 FinalReading 으로 승격해 반환 타입을 한 종류로 유지한다.
    """
    finals = [FinalReading.model_validate(r.model_dump()) for r in readings]
    ambs = list(ambiguities)
    log: list[dict] = []

    for f in findings:
        entry = {"target_item": f.target_item, "verdict": f.verdict,
                 "reason": f.reason, "applied": False, "note": ""}
        if f.verdict == "기각":
            log.append(entry)
            continue
        if f.verdict == "상태변경":
            hits = [i for i, r in enumerate(finals) if r.item == f.target_item]
            if not hits:
                entry["note"] = "대상 없음 — 항목명이 통합 결과와 다르다"
            else:
                for i in hits:
                    finals[i] = FinalReading.model_validate(
                        {**finals[i].model_dump(), "status": f.new_status})
                entry["applied"] = True
                if len(hits) > 1:
                    entry["note"] = f"동명 {len(hits)}건 전부 적용"
        elif f.verdict == "신규애매성":
            ambs.append(f.new_ambiguity)
            entry["applied"] = True
        log.append(entry)

    return finals, ambs, log
