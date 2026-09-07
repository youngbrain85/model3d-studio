"""채점 (M5 D6) — 정답 섹션 대조 + 섹션 self-check + 레고식 결합(정답 9 + 에이전트 1) self-check·재실측."""

from __future__ import annotations

from pathlib import Path

import trimesh

from m3d.model import compare, measure, sections, selfcheck
from m3d.model.builder import Builder
from m3d.model.render import load_nodes
from m3d.model.spec import ModelSpec

BBOX_TOL_M = 0.005


def node_role(code: str, node: str, spec: ModelSpec) -> str | None:
    """노드 → 부재 역할 라벨(피드백용, M6 잡 2 교훈). DIA: 01·마지막 = 지점 격벽, 나머지 = 일반 격벽."""
    if code == "DIA" and node.startswith("AB1_S5_DIA") and node[-2:].isdigit():
        return "지점 격벽" if int(node[-2:]) in (1, spec.diaphragm.n_cell + 1) else "일반 격벽"
    return None


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
    failed_meas = [c["항목"] + (f" ({str(c['실측'])[:160]})" if isinstance(c.get("실측"), str) else "")
                   for c in meas["대조"] if c["판정"] == "FAIL"]
    dev = cmp["bbox_dev_max_m"]
    passed = (not cmp["only_ours"] and not cmp["only_ref"] and dev is not None and dev <= BBOX_TOL_M
              and sec["fail"] == 0 and full["fail"] == 0 and not failed_meas)
    ref_named = load_named(ref_glb)
    worst_detail = []
    for w in cmp["worst"][:4]:
        if w["dev_m"] <= BBOX_TOL_M or w["node"] not in agent_named or w["node"] not in ref_named:
            continue
        a, r = agent_named[w["node"]].bounds, ref_named[w["node"]].bounds
        axes = []
        for i, ax in enumerate("xyz"):
            for bound, idx in (("min", 0), ("max", 1)):
                o, rf = float(a[idx][i]), float(r[idx][i])
                if abs(rf - o) > BBOX_TOL_M:
                    axes.append({"axis": ax, "bound": bound, "ours": round(o, 3), "ref": round(rf, 3), "delta_mm": int(round((rf - o) * 1000))})
        worst_detail.append({"node": w["node"], "role": node_role(code, w["node"], spec), "ours": [[round(float(v), 3) for v in a[0]], [round(float(v), 3) for v in a[1]]],
                             "ref": [[round(float(v), 3) for v in r[0]], [round(float(v), 3) for v in r[1]]], "axes": axes})
    return {
        "pass": bool(passed),
        "compare": {**{k: cmp[k] for k in ("only_ours", "only_ref", "common", "bbox_dev_max_m", "bbox_dev_over_1mm", "faces_equal", "worst")},
                    "worst_detail": worst_detail},
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


BBOX_NOTE = "(노드 bbox = 그 노드에 합친 모든 솔리드 — 판+보강재 — 의 전체 범위이며 판 두께가 아니다)"
PLATE_OK_HINT = ("판 두께·위치는 검사를 통과했으니 바꾸지 말 것 — 차이는 판면에 붙는 부속 솔리드(보강재 등)의 유무·방향·돌출 크기에서 난다. "
                 "돌출량은 spec 의 '돌출[축]' 값이고 두께 t 는 판면 안 방향이다 — 돌출부의 판면 법선 방향 크기를 t 로 두지 않는다.")
CHAIN_HINT = "판면 정점이 체인 위치 ±10mm 에 없다 — 판 두께 중심(지점 격벽은 받침선 쪽 판면)을 체인 z 에 두고 두께는 스펙값만큼만."


def _delta_phrase(e: dict) -> str:
    """축별 델타 한 구절 — 누가 어느 쪽으로 얼마나 더 뻗었는지(설계서 §3.3)."""
    d, ax = e["delta_mm"], e["axis"]
    if e["bound"] == "max":
        return f"정답이 +{ax} 쪽으로 {d}mm 더 뻗음" if d > 0 else f"우리가 +{ax} 쪽으로 {-d}mm 더 뻗음(초과)"
    return f"정답이 -{ax} 쪽으로 {-d}mm 더 뻗음" if d < 0 else f"우리가 -{ax} 쪽으로 {d}mm 더 뻗음(초과)"


def feedback_text(score: dict) -> str:
    """다음 시도 프롬프트용 — 무엇이 어긋났는지 노드명·축·mm 로, 숫자마다 의미를 붙여서(M6 D3)."""
    c = score["compare"]
    if score["pass"]:
        return "채점: PASS"
    lines = ["채점: FAIL", BBOX_NOTE]
    if c["only_ref"]:
        lines.append("빠진 노드(정답에는 있음): " + ", ".join(c["only_ref"][:30]))
    if c["only_ours"]:
        lines.append("남는 노드(정답에 없음): " + ", ".join(c["only_ours"][:30]))
    worst = [w for w in c["worst"] if w["dev_m"] > BBOX_TOL_M]
    if worst:
        lines.append("정답 대비 bbox 편차 상위: " + ", ".join(f"{w['node']} {w['dev_m'] * 1000:.0f}mm" for w in worst[:8]))
    for d in c.get("worst_detail", []):
        for e in d.get("axes", [])[:6]:
            name = f"{d['node']}({d['role']})" if d.get("role") else d["node"]
            lines.append(f"  {name}: {e['axis']} {'최대' if e['bound'] == 'max' else '최소'} {e['ours']} → 정답 {e['ref']} — {_delta_phrase(e)}")
    failed = score["section_selfcheck"]["failed"] + score["assembled_selfcheck"]["failed"]
    checks_ok = (score["section_selfcheck"]["fail"] == 0 and score["assembled_selfcheck"]["fail"] == 0 and score["measure"]["FAIL"] == 0)
    if worst and checks_ok:
        lines.append(PLATE_OK_HINT)
    if any("z 체인" in f for f in failed):
        lines.append(CHAIN_HINT)
    for key, label in (("section_selfcheck", "섹션 self-check 실패"), ("assembled_selfcheck", "결합 self-check 실패")):
        if score[key]["failed"]:
            lines.append(label + ": " + " | ".join(score[key]["failed"][:8]))
    if score["measure"]["failed"]:
        lines.append("재실측 실패 항목: " + " | ".join(score["measure"]["failed"][:8]))
    return "\n".join(lines)
