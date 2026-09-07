"""전집 결합 (M7 D8) — 섹션마다 가장 좋은 에이전트 산출을 골라 하나의 결합 빌드로 만든다.

LLM 호출이 없는 결정론 작업이다. 통과분이 없는 섹션은 정답 빌더 산출로 채우고 build.json 에 출처를 남긴다.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from m3d.agent import score as agent_score
from m3d.config import Config
from m3d.model import io as model_io
from m3d.model import measure, publish, render, sections, selfcheck
from m3d.model.builder import Builder
from m3d.model.spec import ModelSpec
from m3d.samples.manifest import sha256_file


def _agent_jobs(cfg: Config, dataset: str) -> list[dict]:
    """에이전트 잡 디렉터리 → [{job_id, code, glb, pass}] — 오래된 것부터(뒤에 오는 것이 이긴다)."""
    root = model_io.model_dir(cfg, dataset) / "agent"
    if not root.is_dir():
        return []
    out: list[dict] = []
    for d in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime):
        score, build = d / "agent" / "score.json", d / "build.json"
        if not score.is_file() or not build.is_file():
            continue
        try:
            summ = json.loads(score.read_text(encoding="utf-8")).get("summary", {})
            meta = json.loads(build.read_text(encoding="utf-8"))
        except ValueError:
            continue
        code = next((s["code"] for s in meta.get("sections", []) if s.get("source") == "agent"), None)
        if code is None:
            continue
        glb = d / "sections" / meta.get("segment", "P4P5") / f"{code}.glb"
        if glb.is_file():
            out.append({"job_id": d.name, "code": code, "glb": glb, "pass": bool(summ.get("pass"))})
    return out


def pick_sources(cfg: Config, dataset: str, *, ref_dir, segment: str) -> dict[str, dict]:
    """섹션마다 쓸 GLB — 통과한 에이전트 산출 우선(최신), 없으면 정답 빌더."""
    ref_dir = Path(ref_dir)
    picked = {c: {"glb": ref_dir / "sections" / segment / f"{c}.glb", "source": "builder", "job_id": None, "pass": False}
              for c in sections.CODES}
    for job in _agent_jobs(cfg, dataset):
        if job["pass"]:
            picked[job["code"]] = {"glb": job["glb"], "source": "agent", "job_id": job["job_id"], "pass": True}
    return picked


def _publish(cfg: Config, dataset: str, out_dir: Path) -> dict:
    return publish.run_publish_model(cfg, dataset, out_dir=out_dir, kind="agent", force=True)


def run_assemble(cfg: Config, dataset: str, *, out_dir=None, ref_dir=None, publish: bool = True,
                 do_render: bool = True) -> dict:
    """결합 빌드 디렉터리를 만들고(선택) 업로드한다."""
    raw = model_io.load_modelspec_raw(cfg, dataset)
    spec = ModelSpec.model_validate(raw["spec"])
    segment = spec.coord.segment
    ref_dir = Path(ref_dir) if ref_dir else model_io.model_dir(cfg, dataset)
    out_dir = Path(out_dir) if out_dir else model_io.model_dir(cfg, dataset) / "agent-all"
    sec_dir = out_dir / "sections" / segment
    sec_dir.mkdir(parents=True, exist_ok=True)
    picked = pick_sources(cfg, dataset, ref_dir=ref_dir, segment=segment)
    b = Builder(spec)
    meta: list[dict] = []
    named_all: dict = {}
    sec_results: dict = {}
    for c in sections.CODES:
        dst = sec_dir / f"{c}.glb"
        shutil.copyfile(picked[c]["glb"], dst)
        named = agent_score.load_named(dst)
        named_all.update(named)
        rs = selfcheck.run(named, b, section=c)
        sec_results[f"{segment}/{c}"] = rs
        meta.append({"key": f"{segment}/{c}", "code": c, "label": sections.LABELS[c], "file": f"sections/{segment}/{c}.glb",
                     "meshes": len(named), "triangles": int(sum(len(m.faces) for m in named.values())),
                     "bytes": dst.stat().st_size, "sha256": sha256_file(dst), "source": picked[c]["source"],
                     "job_id": picked[c]["job_id"], "selfcheck": {"pass": rs["pass"], "fail": rs["fail"]}})
    glb = out_dir / "AB1_P4P5.glb"
    b.export(named_all, glb)
    r_all = selfcheck.run(named_all, b, pilot=False)
    meas = measure.run(glb, spec)
    (out_dir / "selfcheck.json").write_text(json.dumps(r_all, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "selfcheck_sections.json").write_text(json.dumps(sec_results, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "measure.json").write_text(json.dumps(meas, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.copyfile(model_io.model_dir(cfg, dataset) / "modelspec.json", out_dir / "modelspec.json")
    if do_render:
        render.run_render(glb, out_dir / "renders", spec, pilot=False)
    else:
        (out_dir / "renders").mkdir(exist_ok=True)
        (out_dir / "renders" / "views.json").write_text("{}", encoding="utf-8")
    model_io.write_build_json(out_dir, {
        "kind": "agent", "segment": segment,
        "assembled": {"file": "AB1_P4P5.glb", "meshes": r_all["meshes"], "triangles": r_all["triangles"],
                      "bytes": glb.stat().st_size, "sha256": sha256_file(glb)},
        "sections": meta, "selfcheck": {"pass": r_all["pass"], "fail": r_all["fail"], "skipped": r_all["skipped"]},
        "git_sha": None})
    result = {"out_dir": str(out_dir),
              "sections": {m["code"]: {"source": m["source"], "job_id": m["job_id"]} for m in meta},
              "agent_sections": sum(1 for m in meta if m["source"] == "agent"),
              "selfcheck": {"pass": r_all["pass"], "fail": r_all["fail"]},
              "measure": {"PASS": meas["집계"]["PASS"], "FAIL": meas["집계"]["FAIL"], "INFO": meas["집계"]["INFO"]}}
    if publish:
        result["publish"] = _publish(cfg, dataset, out_dir)
    return result
