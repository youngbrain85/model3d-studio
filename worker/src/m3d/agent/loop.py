"""잡 실행 루프 (M5 D7·D8·D9) — 묶음 → LLM → 샌드박스 → 채점, 시도 ≤ 4, 예산 상한, 에이전트 빌드 디렉터리 → publish.

의존성(llm·scorer·publisher·evidence·crops·ref_dir)은 주입 가능 — 테스트는 실호출 없이 돈다.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from m3d.agent import context as agent_context
from m3d.agent import crops as agent_crops
from m3d.agent import critique as agent_critique
from m3d.agent import sandbox
from m3d.agent import score as agent_score
from m3d.agent import sections_meta as agent_sections_meta
from m3d.agent.schema import AgentOut, validate_agent_out
from m3d.config import Config
from m3d.model import io as model_io
from m3d.model import measure, publish, render, sections, selfcheck
from m3d.model.builder import Builder
from m3d.model.spec import ModelSpec
from m3d.reading.client import MODEL_READ, build_client, call_structured
from m3d.samples.manifest import sha256_file

MAX_ATTEMPTS = 4
MAX_TOKENS = 16000
EST_CALL_USD = 0.15
STAGE = "model-agent"


def spent_usd(cfg: Config, dataset: str, stage: str = STAGE) -> float:
    path = cfg.derived_dir / dataset / "usage.jsonl"
    if not path.is_file():
        return 0.0
    total = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("stage") == stage and not r.get("cached"):
            total += float(r.get("cost_usd") or 0.0)
    return total


def real_llm(cfg: Config, dataset: str, bundle: dict, extra: dict) -> tuple[AgentOut, dict]:
    client = build_client(cfg)
    return call_structured(client, cfg, dataset, model=MODEL_READ, system=bundle["system"], messages=bundle["messages"],
                           out_format=AgentOut, max_tokens=MAX_TOKENS, stage=STAGE, extra=extra, post_validate=validate_agent_out)


def _section_meta(path: Path, key: str, code: str, source: str) -> dict:
    named = agent_score.load_named(path)
    return {"key": key, "code": code, "label": sections.LABELS[code], "file": f"sections/{key.split('/')[0]}/{code}.glb",
            "meshes": len(named), "triangles": int(sum(len(m.faces) for m in named.values())),
            "bytes": path.stat().st_size, "sha256": sha256_file(path), "source": source}


def build_agent_dir(cfg: Config, dataset: str, *, out_dir: Path, ref_dir: Path, spec: ModelSpec, code: str, agent_glb: Path,
                    final: AgentOut, attempts: list[dict], score: dict, bundle: dict, do_render: bool = True) -> Path:
    """정답 빌드 디렉터리를 복제하고 섹션 하나를 에이전트 결과로 교체한 산출 디렉터리(D9)."""
    segment = spec.coord.segment
    sec_dir = out_dir / "sections" / segment
    sec_dir.mkdir(parents=True, exist_ok=True)
    meta, named_all = [], {}
    for c in sections.CODES:
        src = Path(agent_glb) if c == code else Path(ref_dir) / "sections" / segment / f"{c}.glb"
        dst = sec_dir / f"{c}.glb"
        shutil.copyfile(src, dst)
        meta.append(_section_meta(dst, f"{segment}/{c}", c, "agent" if c == code else "builder"))
        named_all.update(agent_score.load_named(dst))
    b = Builder(spec)
    glb = out_dir / "AB1_P4P5.glb"
    b.export(named_all, glb)
    r_all = selfcheck.run(named_all, b, pilot=False)
    sec_results = {}
    for m in meta:
        rs = selfcheck.run(agent_score.load_named(sec_dir / f"{m['code']}.glb"), b, section=m["code"])
        sec_results[m["key"]] = rs
        m["selfcheck"] = {"pass": rs["pass"], "fail": rs["fail"]}
    (out_dir / "selfcheck.json").write_text(json.dumps(r_all, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "selfcheck_sections.json").write_text(json.dumps(sec_results, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "measure.json").write_text(json.dumps(measure.run(glb, spec), ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.copyfile(model_io.model_dir(cfg, dataset) / "modelspec.json", out_dir / "modelspec.json")
    if do_render:
        render.run_render(glb, out_dir / "renders", spec, pilot=False)
    else:
        (out_dir / "renders").mkdir(exist_ok=True)
        (out_dir / "renders" / "views.json").write_text("{}", encoding="utf-8")
    agent_dir = out_dir / "agent"
    agent_dir.mkdir(exist_ok=True)
    (agent_dir / "code.py").write_text(final.code, encoding="utf-8")
    (agent_dir / "attempts.json").write_text(json.dumps(attempts, ensure_ascii=False, indent=2), encoding="utf-8")
    (agent_dir / "score.json").write_text(json.dumps({"summary": agent_score.summary(score, len(attempts)), "score": score,
                                                      "assumptions": final.assumptions, "questions": final.questions},
                                                     ensure_ascii=False, indent=2), encoding="utf-8")
    texts = "\n\n".join(p["text"] for p in bundle["messages"][0]["content"] if p["type"] == "text")
    (agent_dir / "prompt.md").write_text("# system\n\n" + bundle["system"] + "\n\n# user\n\n" + texts, encoding="utf-8")
    model_io.write_build_json(out_dir, {
        "kind": "agent", "segment": segment,
        "assembled": {"file": "AB1_P4P5.glb", "meshes": r_all["meshes"], "triangles": r_all["triangles"],
                      "bytes": glb.stat().st_size, "sha256": sha256_file(glb)},
        "sections": meta, "selfcheck": {"pass": r_all["pass"], "fail": r_all["fail"], "skipped": r_all["skipped"]}, "git_sha": None})
    return out_dir


def _default_publisher(cfg, dataset, *, out_dir, kind, force):
    return publish.run_publish_model(cfg, dataset, out_dir=out_dir, kind=kind, force=force)


def run_job(cfg: Config, dataset: str, job: dict, emit, *, llm=None, scorer=None, publisher=None, evidence=None, crops=None,
            ref_dir=None, critic=None, do_render: bool = True) -> dict:
    llm = llm or real_llm
    scorer = scorer or agent_score.score_section
    publisher = publisher or _default_publisher
    critic = critic or agent_critique.render_views
    segment, code = job["section_key"].split("/")
    if agent_sections_meta.meta(code) is None:
        emit("error", f"지원하지 않는 섹션: {job['section_key']}")
        return {"pass": False, "reason": "unsupported_section", "attempts": 0, "cost_usd": 0.0, "assumptions": [], "questions": []}
    pattern = agent_crops.SECTION_PATTERNS.get(code)          # None 이면 크롭 없이 진행(HST, M7 D9)
    raw = model_io.load_modelspec_raw(cfg, dataset)
    spec, sources = ModelSpec.model_validate(raw["spec"]), raw.get("sources", {})
    ref_dir = Path(ref_dir) if ref_dir else model_io.model_dir(cfg, dataset)
    if not all((ref_dir / "sections" / segment / f"{c}.glb").is_file() for c in sections.CODES):
        emit("error", "정답 섹션 GLB 없음 — `m3d build` 먼저")
        return {"pass": False, "reason": "no_reference", "attempts": 0, "cost_usd": 0.0, "assumptions": [], "questions": []}
    work = model_io.model_dir(cfg, dataset) / "agent" / str(job["id"])
    (work / "agent").mkdir(parents=True, exist_ok=True)
    if evidence is None:
        evidence = agent_crops.fetch_evidence(cfg, dataset, pattern) if pattern else []
    if crops is None:
        crops = agent_crops.section_crops(cfg, dataset, evidence, work / "agent" / "crops")
    emit("info", f"입력: 판독 근거 {len(evidence)}건, 크롭 {len(crops)}장")
    prev_code = None
    if job.get("parent_job_id"):
        p = model_io.model_dir(cfg, dataset) / "agent" / str(job["parent_job_id"]) / "agent" / "code.py"
        prev_code = p.read_text(encoding="utf-8") if p.is_file() else None
    feedback, critique, attempts, cost, last, bundle = None, None, [], 0.0, None, None
    budget = float(job.get("budget_usd") or cfg.model_agent_budget_usd)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        spent = spent_usd(cfg, dataset)
        if spent + EST_CALL_USD > budget:
            emit("error", f"예산 상한: 누적 ${spent:.2f} + 예상 ${EST_CALL_USD:.2f} > ${budget:.2f}")
            return {"pass": False, "reason": "budget", "attempts": len(attempts), "cost_usd": cost, "assumptions": [], "questions": []}
        bundle = agent_context.section_bundle(job["section_key"], spec_dict=spec.model_dump(), sources=sources, evidence=evidence,
                                              crops=crops, feedback=feedback, request=job.get("request") or "", prev_code=prev_code, critique=critique)
        emit("info", f"시도 {attempt}/{MAX_ATTEMPTS}: LLM 호출(이미지 {bundle['n_images']}장)")
        out, usage = llm(cfg, dataset, bundle, {"job_id": str(job["id"]), "attempt": attempt, "section": job["section_key"]})
        cost += float(usage.get("cost_usd") or 0.0)
        (work / "agent" / f"attempt{attempt}.py").write_text(out.code, encoding="utf-8")
        res = sandbox.run_code(out.code, spec.model_dump(), work / "agent" / f"attempt{attempt}.glb")
        prev_code = out.code
        if not res.ok:
            feedback = "실행 오류:\n" + res.error
            attempts.append({"attempt": attempt, "ok": False, "error": res.error[:2000], "cost_usd": usage.get("cost_usd")})
            critique = None
            emit("warn", f"시도 {attempt}: 실행 실패 — {res.error.splitlines()[0][:160]}")
            continue
        sc = scorer(code, res.glb, spec, ref_dir, work_dir=work / f"score{attempt}")
        attempts.append({"attempt": attempt, "ok": True, "pass": sc["pass"], "score": agent_score.summary(sc, attempt),
                         "cost_usd": usage.get("cost_usd")})
        last = (out, res, sc)
        emit("info", f"시도 {attempt}: 채점 {'PASS' if sc['pass'] else 'FAIL'} — 노드 누락 {len(sc['compare']['only_ref'])}·"
                     f"초과 {len(sc['compare']['only_ours'])}·bbox {(sc['compare']['bbox_dev_max_m'] or 0) * 1000:.0f}mm·"
                     f"결합 fail {sc['assembled_selfcheck']['fail']}·재실측 fail {sc['measure']['FAIL']}")
        if sc["pass"]:
            break
        feedback = agent_score.feedback_text(sc)
        critique = critic(res.glb, spec, code, work / "agent" / f"critique{attempt}")
        if critique:
            attempts[-1]["critique"] = [Path(c["path"]).name for c in critique]
        emit("info", f"시도 {attempt}: 자기 렌더 {len(critique)}장")
    (work / "agent" / "attempts.json").write_text(json.dumps(attempts, ensure_ascii=False, indent=2), encoding="utf-8")
    if last is None:
        emit("error", "모든 시도가 실행에 실패했다")
        return {"pass": False, "reason": "no_run", "attempts": len(attempts), "cost_usd": cost, "assumptions": [], "questions": []}
    out, res, sc = last
    out_dir = build_agent_dir(cfg, dataset, out_dir=work, ref_dir=ref_dir, spec=spec, code=code, agent_glb=res.glb, final=out,
                              attempts=attempts, score=sc, bundle=bundle, do_render=do_render)
    pub = publisher(cfg, dataset, out_dir=out_dir, kind="agent", force=True)
    emit("info", f"에이전트 빌드 b{pub['version']} 업로드({pub['uploaded']} 파일)")
    return {"pass": sc["pass"], "attempts": len(attempts), "cost_usd": cost, "build_version": pub["version"], "build_id": pub["build_id"],
            "assumptions": out.assumptions, "questions": out.questions, "score": agent_score.summary(sc, len(attempts))}
