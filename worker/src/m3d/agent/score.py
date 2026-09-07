"""채점 (M5 D6 → M8 D4) — 정답 없이 판정한다: 기하 건전성 + 섹션 self-check + 결합 self-check + 그 섹션 재실측.

정답 빌더가 있는 교량에서는 대조 결과를 `reference` 로 함께 싣지만 합격 여부에는 넣지 않는다.
새 교량에서는 `ref_dir=None` 으로 부르면 된다 — 본체(BOX)는 스펙에서 결정론으로 나오므로 빌더에서 채운다.
"""

from __future__ import annotations

from pathlib import Path

import trimesh

from m3d.agent import sections_meta
from m3d.model import compare, measure, sanity, sections, selfcheck
from m3d.model.builder import Builder
from m3d.model.render import load_nodes
from m3d.model.spec import ModelSpec

BBOX_TOL_M = 0.005
BBOX_EPS_M = 1e-4       # GLB float32 반올림 여유 — |좌표| ≤ 1,000m 에서 ulp ≤ 6e-5 m (M6 잡 3)


def within_bbox_tol(dev_m) -> bool:
    """정답 대비 bbox 편차 판정 — 5mm 이하(반올림 여유 0.1mm 포함). 참고 정보에만 쓴다."""
    return dev_m is not None and dev_m <= BBOX_TOL_M + BBOX_EPS_M


def node_role(code: str, node: str, spec: ModelSpec) -> str | None:
    """노드 → 부재 역할 라벨(피드백용). 표는 sections_meta 에 있다(M7 D2)."""
    return sections_meta.role_of(code, node)


def load_named(glb: Path) -> dict[str, trimesh.Trimesh]:
    return {name: m for name, m, _c in load_nodes(Path(glb))}


def _meas_line(c: dict) -> str:
    return "%s — 기대 %s / 실측 %s (허용 %s)" % (c["항목"], c["기대"], c["실측"], c["허용오차"])


def score_section(code: str, agent_glb: Path, spec: ModelSpec, ref_dir=None, *, work_dir: Path) -> dict:
    """정답 무관 판정 (M8 D4). ref_dir 을 주면 정답 대조를 참고 정보로 덧붙인다."""
    segment = spec.coord.segment
    b = Builder(spec)
    agent_named = load_named(agent_glb)
    sec = selfcheck.run(agent_named, b, section=code)
    named: dict[str, trimesh.Trimesh] = {}
    if ref_dir is None:
        # 정답 섹션이 없는 교량 — 재실측이 기준면을 잡으려면 본체(BOX)는 있어야 한다.
        # BOX 는 에이전트 대상이 아니고(M7 D1) 스펙에서 결정론으로 나오므로 빌더에서 가져온다.
        named.update({n: m for n, m in b.build(pilot=True).items() if sections.group_of(n) == "BOX"})
    for c in sections.CODES:
        if c == code:
            named.update(agent_named)
        elif ref_dir is not None:
            named.update(load_named(Path(ref_dir) / "sections" / segment / f"{c}.glb"))
    full = selfcheck.run(named, b, pilot=False) if ref_dir is not None else {"pass": 0, "fail": 0, "checks": []}
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    assembled = work_dir / "assembled.glb"
    b.export(named, assembled)
    san = sanity.run(named, spec)
    meas = measure.run(assembled, spec)
    sec_rows = [c for c in meas["대조"] if c.get("섹션") == code]
    failed_meas = [_meas_line(c) for c in sec_rows if c["판정"] == "FAIL"]
    passed = (san["fail"] == 0 and sec["fail"] == 0 and full["fail"] == 0 and not failed_meas)
    out = {
        "pass": bool(passed),
        "sanity": san,
        "section_selfcheck": _sc(sec), "assembled_selfcheck": _sc(full),
        "measure": {"PASS": meas["집계"]["PASS"], "FAIL": meas["집계"]["FAIL"], "INFO": meas["집계"]["INFO"],
                    "section_fail": len(failed_meas), "failed": failed_meas},
        "assembled_glb": str(assembled),
    }
    if ref_dir is not None:
        out["reference"] = _reference(code, agent_glb, agent_named, spec, Path(ref_dir))
    return out


def _reference(code, agent_glb, agent_named, spec, ref_dir: Path) -> dict:
    """참고용 정답 대조 — 합격 여부에는 쓰지 않는다(M8 D4)."""
    ref_glb = ref_dir / "sections" / spec.coord.segment / f"{code}.glb"
    cmp = compare.compare_glb(Path(agent_glb), ref_glb)
    ref_named = load_named(ref_glb)
    worst_detail = []
    for w in cmp["worst"][:4]:
        if within_bbox_tol(w["dev_m"]) or w["node"] not in agent_named or w["node"] not in ref_named:
            continue
        a, r = agent_named[w["node"]].bounds, ref_named[w["node"]].bounds
        axes = []
        for i, ax in enumerate("xyz"):
            for bound, idx in (("min", 0), ("max", 1)):
                o, rf = float(a[idx][i]), float(r[idx][i])
                if not within_bbox_tol(abs(rf - o)):
                    axes.append({"axis": ax, "bound": bound, "ours": round(o, 3), "ref": round(rf, 3),
                                 "delta_mm": int(round((rf - o) * 1000))})
        worst_detail.append({"node": w["node"], "role": node_role(code, w["node"], spec),
                             "ours": [[round(float(v), 3) for v in a[0]], [round(float(v), 3) for v in a[1]]],
                             "ref": [[round(float(v), 3) for v in r[0]], [round(float(v), 3) for v in r[1]]],
                             "axes": axes})
    return {**{k: cmp[k] for k in ("only_ours", "only_ref", "common", "bbox_dev_max_m", "bbox_dev_over_1mm",
                                   "faces_equal", "worst")}, "worst_detail": worst_detail}


def _sc(r: dict) -> dict:
    return {"pass": r["pass"], "fail": r["fail"],
            "failed": [f"{c['label']} — {c['detail']}" for c in r["checks"] if c["ok"] is False]}


def summary(score: dict, attempts: int) -> dict:
    ref = score.get("reference")
    return {"pass": score["pass"], "sanity_fail": score["sanity"]["fail"],
            "section_fail": score["section_selfcheck"]["fail"],
            "assembled_fail": score["assembled_selfcheck"]["fail"],
            "measure_section_fail": score["measure"]["section_fail"], "measure_fail": score["measure"]["FAIL"],
            "attempts": attempts,
            "bbox_dev_max_m": ref["bbox_dev_max_m"] if ref else None,
            "only_ours": len(ref["only_ours"]) if ref else 0, "only_ref": len(ref["only_ref"]) if ref else 0}


BBOX_NOTE = "(노드 bbox = 그 노드에 합친 모든 솔리드 — 판+보강재 — 의 전체 범위이며 판 두께가 아니다)"
CHAIN_HINT = "판면 정점이 체인 위치 ±10mm 에 없다 — 판 두께 중심(지점 격벽은 받침선 쪽 판면)을 체인 z 에 두고 두께는 스펙값만큼만."


def _delta_phrase(e: dict) -> str:
    """축별 델타 한 구절 — 누가 어느 쪽으로 얼마나 더 뻗었는지."""
    d, ax = e["delta_mm"], e["axis"]
    if e["bound"] == "max":
        return f"정답이 +{ax} 쪽으로 {d}mm 더 뻗음" if d > 0 else f"우리가 +{ax} 쪽으로 {-d}mm 더 뻗음(초과)"
    return f"정답이 -{ax} 쪽으로 {-d}mm 더 뻗음" if d < 0 else f"우리가 -{ax} 쪽으로 {d}mm 더 뻗음(초과)"


def feedback_text(score: dict) -> str:
    """다음 시도 프롬프트용 — 정답 없이도 나오는 소견을 먼저, 정답 대조는 있을 때만 뒤에(M8 D5)."""
    if score["pass"]:
        return "채점: PASS"
    lines = ["채점: FAIL"]
    bad_san = [c for c in score["sanity"]["checks"] if not c["ok"]]
    if bad_san:
        lines.append("기하 건전성 위반: "
                     + " | ".join("%s — %s (%s)" % (c["label"], c["detail"], ", ".join(c["nodes"][:5])) for c in bad_san))
    if score["measure"]["failed"]:
        lines.append("재실측 실패(스펙에서 유도한 기대값 대비):")
        lines += ["  " + f for f in score["measure"]["failed"][:8]]
    failed = score["section_selfcheck"]["failed"] + score["assembled_selfcheck"]["failed"]
    for key, label in (("section_selfcheck", "섹션 self-check 실패"), ("assembled_selfcheck", "결합 self-check 실패")):
        if score[key]["failed"]:
            lines.append(label + ": " + " | ".join(score[key]["failed"][:8]))
    if any("z 체인" in f for f in failed):
        lines.append(CHAIN_HINT)
    ref = score.get("reference")
    if ref:
        lines.append("(참고 — 이 교량은 정답 모델이 있어 대조도 싣는다. 합격 여부는 위 항목으로 정한다.)")
        lines.append(BBOX_NOTE)
        if ref["only_ref"]:
            lines.append("빠진 노드: " + ", ".join(ref["only_ref"][:30]))
        if ref["only_ours"]:
            lines.append("남는 노드: " + ", ".join(ref["only_ours"][:30]))
        worst = [w for w in ref["worst"] if not within_bbox_tol(w["dev_m"])]
        if worst:
            lines.append("정답 대비 bbox 편차 상위: "
                         + ", ".join("%s %.0fmm" % (w["node"], w["dev_m"] * 1000) for w in worst[:8]))
        for d in ref.get("worst_detail", []):
            for e in d.get("axes", [])[:6]:
                name = f"{d['node']}({d['role']})" if d.get("role") else d["node"]
                lines.append(f"  {name}: {e['axis']} {'최대' if e['bound'] == 'max' else '최소'} {e['ours']} "
                             f"→ 정답 {e['ref']} — {_delta_phrase(e)}")
    return "\n".join(lines)
