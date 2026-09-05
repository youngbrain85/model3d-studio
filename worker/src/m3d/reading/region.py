"""계열 통합 + 적대적 검토 (설계서 §4-2·§4-3)."""

from __future__ import annotations

import json
import logging
import re

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

log = logging.getLogger(__name__)

# 합성 라벨("P1/P3/P4 희생관 연장(…) 및 제원", "받침 종류(P1/P4/P7/P8) …")을 항목
# 단위 토큰으로 쪼갤 때 쓰는 구분자. 마침표는 포함하지 않는다 — "17.990" 같은 소수·
# "NO.1" 같은 표기가 깨지면 안 되기 때문이다.
_LABEL_TOKEN_DELIMS = ["/", "·", ",", "(", ")", "[", "]", "및", "와", "과"]
_LABEL_TOKEN_RE = re.compile(
    "|".join(re.escape(d) for d in _LABEL_TOKEN_DELIMS) + r"|\s+")


def _tokens(s: str) -> set[str]:
    """합성 라벨 비교용 토큰 집합.

    `_LABEL_TOKEN_DELIMS` 구분자와 공백으로 문자열을 쪼개고 빈 토큰을 버린다.
    """
    return {t for t in _LABEL_TOKEN_RE.split(s) if t}

# (ord, page_no) → 용지 크기(w_mm, h_mm) — merge_region/review_region 의 post_validate 가
# "입력에 실제로 존재하는 페이지인가·그 용지 안의 bbox인가"를 확인하는 데 쓴다.
PageKey = tuple[str, int]
PaperMm = tuple[float, float]


def page_and_bbox_violations(ord_: str, page_no: int, mm_bbox: list[float],
                             pages: dict[PageKey, PaperMm]) -> list[str]:
    """acceptance §4·§7 재발 방지 — 존재하지 않는 페이지·용지 밖 bbox 를 여기서 반려한다.

    이전에는 ord 만 봤다: A03(p1 만 존재)에 대해 LLM 이 지어낸 page_no=2 가 스키마 검증을
    통과해버려 resolve_ids 에서야(조용히) 유실됐고, 용지 밖 mm_bbox(A02·D02)는 크롭 단계에서야
    실패로 드러났다. 둘 다 여기서 앞당겨 잡아 post_validate 재시도 경로를 태운다.

    예외를 바로 올리지 않고 위반 문자열 목록(정상이면 [])을 돌려준다 — 호출부가 전건을
    모아 한 사유로 알려야 재시도가 나머지 위반을 모른 채 같은 실수를 되풀이하지 않는다.
    시트 판독(`sheet.read_sheet`)도 pages 에 자기 페이지 하나만 담아 이 함수를 재사용한다.
    """
    paper = pages.get((ord_, page_no))
    if paper is None:
        return [f"입력에 없는 페이지: {ord_} p{page_no}"]
    w, h = paper
    x0, y0, x1, y1 = mm_bbox
    if not (0.0 <= min(x0, x1) and max(x0, x1) <= w
            and 0.0 <= min(y0, y1) and max(y0, y1) <= h):
        return [f"mm_bbox 가 용지 밖: {ord_} p{page_no} {mm_bbox} / paper {paper}"]
    return []


def raise_violations(label: str, problems: list[str]) -> None:
    """위반 전건을 한 ValueError 로 올린다 — call_structured 가 이 문자열을 재시도 사유로 쓴다."""
    if problems:
        raise ValueError(f"{label} 검증 실패 {len(problems)}건: " + "; ".join(problems))


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
            out = out_format.model_validate(cached)
            stale_reason = None
            if post_validate is not None:
                try:
                    post_validate(out)
                except ValueError as exc:
                    stale_reason = str(exc)
            if stale_reason is None:
                usage = log_usage(cfg, dataset, {
                    "stage": stage, "region": region, "model": model, "in": 0, "out": 0,
                    "cached": True, "attempt": 0, "retried": False, "stop_reason": None})
                return out, usage
            log.warning(
                "캐시된 출력이 post_validate 에 실패해 캐시 미스로 취급한다 "
                "(stage=%s region=%s): %s", stage, region, stale_reason)

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
                 sheet_outs: list[tuple[str, SheetReadOut]],
                 pages: dict[PageKey, PaperMm], *,
                 force: bool = False, cache_only: bool = False, client=None):
    """sheet_outs: [(ord, SheetReadOut)] — 계열 내 전 페이지 판독.

    pages: {(ord, page_no): (paper_w_mm, paper_h_mm)} — 입력에 실제로 존재하는 페이지
    전부와 그 용지 크기. 통합 결과의 (ord, page_no)·mm_bbox 가 여기 없으면 반려한다.
    """
    payload = [{"ord": o, **out.model_dump()} for o, out in sheet_outs]
    known = {o for o, _ in sheet_outs}
    user = ("계열 내 시트별 판독 결과다. 하나의 치수 정본으로 통합하라.\n"
            "각 항목의 ord 는 그 값이 실제로 적힌 시트의 ord 여야 한다.\n"
            + json.dumps(payload, ensure_ascii=False))

    def _check(out: RegionMergeOut) -> None:
        problems: list[str] = []
        seen = {r.ord for r in out.readings} | {a.ord for a in out.ambiguities}
        bad = sorted(seen - known)
        if bad:
            problems.append(f"입력에 없는 ord: {bad}")
        for r in out.readings:
            problems += page_and_bbox_violations(r.ord, r.page_no, r.mm_bbox, pages)
        for a in out.ambiguities:
            problems += page_and_bbox_violations(a.ord, a.page_no, a.mm_bbox, pages)
        raise_violations("통합 결과", problems)

    return _call(cfg, dataset, client, stage="merge", region=region, model=MODEL_READ,
                 system=prompts.merge_system(region), user_text=user,
                 out_format=RegionMergeOut,
                 key_payload={"sheets": cache_key({"p": payload})},
                 force=force, cache_only=cache_only, post_validate=_check)


def review_region(cfg: Config, dataset: str, region: str, merged: RegionMergeOut,
                  pages: dict[PageKey, PaperMm], *,
                  force: bool = False, cache_only: bool = False, client=None):
    known = {r.ord for r in merged.readings} | {a.ord for a in merged.ambiguities}
    user = ("아래는 한 계열의 통합 판독 결과다. 반박을 시도하라.\n"
            + json.dumps(merged.model_dump(), ensure_ascii=False))

    def _check(out: ReviewOut) -> None:
        problems: list[str] = []
        new_ambs = [f.new_ambiguity for f in out.findings if f.new_ambiguity is not None]
        bad = sorted({a.ord for a in new_ambs} - known)
        if bad:
            problems.append(f"신규 애매성에 통합 결과에 없는 ord: {bad}")
        for a in new_ambs:
            problems += page_and_bbox_violations(a.ord, a.page_no, a.mm_bbox, pages)
        raise_violations("검토 결과", problems)

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

    '상태변경' 은 완전 일치를 우선 시도한다. 완전 일치가 0건이면 검토(Fable)가 여러
    reading 을 하나의 합성 라벨("P1/P3/P4 희생관 연장(…) 및 제원", "받침 종류
    (P1/P4/P7/P8) …")로 묶어 지적한 경우를 대비해 토큰 부분집합 일치로 한 번 더
    시도한다 — item 의 토큰(`_tokens`, 2개 이상)이 전부 target_item 의 토큰에
    포함되면 매칭. 부분 문자열 규칙("P4 희생관 연장"만 잡히고 "P1 희생관 연장"·
    "P3 희생관 연장"은 어순 때문에 놓치는 문제)의 재발 방지(acceptance §3 F계열
    사례). 1토큰 item(예: "두께")은 오매칭 위험이 커 폴백에서 제외한다. 그래도
    0건이면 기존대로 대상 없음으로 남긴다.

    기록 행의 `resolution` 은 반영·기각·미종결 셋 중 하나다. 미종결(대상 없음)은
    설계서 §8 ⑥("전건이 반영 또는 사유付 기각으로 종결") 위반이므로 기각과 같은
    applied=False 로 뭉개지 않고 구분해 남긴다 — CLI 가 이 값으로 드러낸다
    (acceptance §3: F 계열 미종결 2건이 출력에 보이지 않았다).
    """
    finals = [FinalReading.model_validate(r.model_dump()) for r in readings]
    ambs = list(ambiguities)
    log_rows: list[dict] = []

    for f in findings:
        entry = {"target_item": f.target_item, "verdict": f.verdict,
                 "reason": f.reason, "applied": False, "note": "", "resolution": "미종결"}
        if f.verdict == "기각":
            entry["resolution"] = "기각"
            log_rows.append(entry)
            continue
        if f.verdict == "상태변경":
            hits = [i for i, r in enumerate(finals) if r.item == f.target_item]
            fallback_note = ""
            if not hits:
                target_tokens = _tokens(f.target_item)
                fallback_hits = []
                for i, r in enumerate(finals):
                    item_tokens = _tokens(r.item) if r.item else set()
                    if len(item_tokens) >= 2 and item_tokens <= target_tokens:
                        fallback_hits.append(i)
                if fallback_hits:
                    hits = fallback_hits
                    fallback_note = f"합성 라벨 토큰일치 {len(hits)}건"
            if not hits:
                entry["note"] = "대상 없음 — 항목명이 통합 결과와 다르다"
            else:
                for i in hits:
                    finals[i] = FinalReading.model_validate(
                        {**finals[i].model_dump(), "status": f.new_status})
                entry["applied"] = True
                if fallback_note:
                    entry["note"] = fallback_note
                elif len(hits) > 1:
                    entry["note"] = f"동명 {len(hits)}건 전부 적용"
        elif f.verdict == "신규애매성":
            ambs.append(f.new_ambiguity)
            entry["applied"] = True
        if entry["applied"]:
            entry["resolution"] = "반영"
        log_rows.append(entry)

    return finals, ambs, log_rows
