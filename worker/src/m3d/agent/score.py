"""채점 (M5 D6) — 정답 섹션 대조 + 섹션 self-check + 레고식 결합(정답 9 + 에이전트 1) self-check·재실측."""

from __future__ import annotations

from pathlib import Path

import trimesh

from m3d.model import compare, measure, sections, selfcheck
from m3d.model.builder import Builder
from m3d.model.render import load_nodes
from m3d.model.spec import ModelSpec

BBOX_TOL_M = 0.005


def load_named(glb: Path) -> dict[str, trimesh.Trimesh]:
    return {name: m for name, m, _c in load_nodes(Path(glb))}


def score_section(code: str, agent_glb: Path, spec: ModelSpec, ref_dir: Path, *, work_dir: Path) -> dict:
    segment = spec.coord.segment
    ref_glb = Path(ref_dir) / "sections" / segment / f"{code}.glb"
    cmp = compare.compare_glb(Path(agent_glb), ref_glb)
    b = Builder(spec)
    agent_named = load_named(agent_glb)
    sec = selfcheck.run(agent_named, b, section=code)
    named: dict[str, trimesh.Trimesh] = {}
    for c in sections.CODES:
        named.update(agent_named if c == code else load_named(Path(ref_dir) / "sections" / segment / f"{c}.glb"))
    full = selfcheck.run(named, b, pilot=False)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    assembled = work_dir / "assembled.glb"
    b.export(named, assembled)
    meas = measure.run(assembled, spec)
    failed_meas = [c["항목"] for c in meas["대조"] if c["판정"] == "FAIL"]
    dev = cmp["bbox_dev_max_m"]
    passed = (not cmp["only_ours"] and not cmp["only_ref"] and dev is not None and dev <= BBOX_TOL_M
              and sec["fail"] == 0 and full["fail"] == 0 and not failed_meas)
    return {
        "pass": bool(passed),
        "compare": {k: cmp[k] for k in ("only_ours", "only_ref", "common", "bbox_dev_max_m", "bbox_dev_over_1mm", "faces_equal", "worst")},
        "section_selfcheck": _sc(sec), "assembled_selfcheck": _sc(full),
        "measure": {"PASS": meas["집계"]["PASS"], "FAIL": meas["집계"]["FAIL"], "INFO": meas["집계"]["INFO"], "failed": failed_meas},
        "assembled_glb": str(assembled),
    }


def _sc(r: dict) -> dict:
    return {"pass": r["pass"], "fail": r["fail"], "failed": [f"{c['label']} — {c['detail']}" for c in r["checks"] if c["ok"] is False]}


def summary(score: dict, attempts: int) -> dict:
    return {"pass": score["pass"], "only_ours": len(score["compare"]["only_ours"]), "only_ref": len(score["compare"]["only_ref"]),
            "bbox_dev_max_m": score["compare"]["bbox_dev_max_m"], "section_fail": score["section_selfcheck"]["fail"],
            "assembled_fail": score["assembled_selfcheck"]["fail"], "measure_fail": score["measure"]["FAIL"], "attempts": attempts}


def feedback_text(score: dict) -> str:
    """다음 시도 프롬프트용 — 무엇이 어긋났는지 노드명·mm 로."""
    c = score["compare"]
    lines = ["채점: " + ("PASS" if score["pass"] else "FAIL")]
    if c["only_ref"]:
        lines.append("빠진 노드(정답에는 있음): " + ", ".join(c["only_ref"][:30]))
    if c["only_ours"]:
        lines.append("남는 노드(정답에 없음): " + ", ".join(c["only_ours"][:30]))
    worst = [w for w in c["worst"] if w["dev_m"] > BBOX_TOL_M]
    if worst:
        lines.append("정답 대비 bbox 편차 상위: " + ", ".join(f"{w['node']} {w['dev_m'] * 1000:.0f}mm" for w in worst[:8]))
    for key, label in (("section_selfcheck", "섹션 self-check 실패"), ("assembled_selfcheck", "결합 self-check 실패")):
        if score[key]["failed"]:
            lines.append(label + ": " + " | ".join(score[key]["failed"][:8]))
    if score["measure"]["failed"]:
        lines.append("재실측 실패 항목: " + " | ".join(score["measure"]["failed"][:8]))
    return "\n".join(lines)
