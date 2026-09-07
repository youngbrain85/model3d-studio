"""회귀 검증 (M8 D6) — 이미 쌓인 에이전트 산출에 새 합격 규칙을 돌려 본다. LLM 호출·업로드 없음.

규칙이 쓸모 있으려면 (1) 정답 대비 크게 어긋난 산출을 불합격시키고 (2) 정답과 같은 산출을 합격시켜야 한다.
정답이 있는 이 교량에서만 할 수 있는 검증이고, 무과금이라 규칙을 고칠 때마다 다시 돌린다.
"""

from __future__ import annotations

import json
from pathlib import Path

from m3d.agent import score as agent_score
from m3d.config import Config
from m3d.model import io as model_io
from m3d.model.spec import ModelSpec

BUCKETS = ("≤5mm", "5~100mm", "≥100mm")
BIG_M = 0.100
SMALL_M = 0.005


def bucket_of(dev_m) -> str:
    """정답 대비 편차 → 구간. 대조 불가(None)는 가장 나쁜 구간으로 본다."""
    if dev_m is None:
        return "≥100mm"
    if dev_m <= SMALL_M + 1e-4:
        return "≤5mm"
    return "5~100mm" if dev_m < BIG_M else "≥100mm"


def collect(cfg: Config, dataset: str) -> list[dict]:
    """에이전트 잡 디렉터리 → [{job_id, code, glb}]."""
    root = model_io.model_dir(cfg, dataset) / "agent"
    out: list[dict] = []
    if not root.is_dir():
        return out
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        build = d / "build.json"
        if not build.is_file():
            continue
        try:
            meta = json.loads(build.read_text(encoding="utf-8"))
        except ValueError:
            continue
        code = next((s["code"] for s in meta.get("sections", []) if s.get("source") == "agent"), None)
        if code is None:
            continue
        glb = d / "sections" / meta.get("segment", "P4P5") / f"{code}.glb"
        if glb.is_file():
            out.append({"job_id": d.name, "code": code, "glb": glb})
    return out


def run_rule(cfg: Config, dataset: str, *, ref_dir=None, out_dir=None) -> dict:
    """각 산출에 새 규칙을 적용하고 (편차 구간 × 합격) 혼동표를 낸다."""
    raw = model_io.load_modelspec_raw(cfg, dataset)
    spec = ModelSpec.model_validate(raw["spec"])
    ref_dir = Path(ref_dir) if ref_dir else model_io.model_dir(cfg, dataset)
    out_dir = Path(out_dir) if out_dir else model_io.model_dir(cfg, dataset) / "verify-rule"
    out_dir.mkdir(parents=True, exist_ok=True)
    matrix = {b: {"합격": 0, "불합격": 0} for b in BUCKETS}
    rows: list[dict] = []
    false_pass: list[dict] = []
    false_fail: list[dict] = []
    for item in collect(cfg, dataset):
        try:
            sc = agent_score.score_section(item["code"], item["glb"], spec, ref_dir,
                                           work_dir=out_dir / item["job_id"])
        except Exception as exc:                      # noqa: BLE001 — 임의 산출물에서도 끝까지 돈다
            row = {"job_id": item["job_id"], "code": item["code"], "bbox_dev_m": None, "bucket": "≥100mm",
                   "pass": False, "error": "%s: %s" % (type(exc).__name__, exc)}
            rows.append(row)
            matrix["≥100mm"]["불합격"] += 1
            continue
        dev = (sc.get("reference") or {}).get("bbox_dev_max_m")
        bucket = bucket_of(dev)
        matrix[bucket]["합격" if sc["pass"] else "불합격"] += 1
        row = {"job_id": item["job_id"], "code": item["code"], "bbox_dev_m": dev, "bucket": bucket,
               "pass": sc["pass"], "sanity_fail": sc["sanity"]["fail"],
               "section_fail": sc["section_selfcheck"]["fail"], "assembled_fail": sc["assembled_selfcheck"]["fail"],
               "measure_section_fail": sc["measure"]["section_fail"], "measure_failed": sc["measure"]["failed"][:3]}
        rows.append(row)
        if bucket == "≥100mm" and sc["pass"]:
            false_pass.append(row)
        if bucket == "≤5mm" and not sc["pass"]:
            false_fail.append(row)
    result = {"rows": rows, "matrix": matrix, "false_pass": false_pass, "false_fail": false_fail, "총건수": len(rows)}
    (out_dir / "verify_rule.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str),
                                              encoding="utf-8")
    return result
