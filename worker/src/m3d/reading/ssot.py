"""m3d ssot — 치수 정본(실측정리) 문서 생성 (M2b 설계서 §4-2, 지식베이스 §2·§7).

판독값(확정/추정/검토지적)과 사용자 결정(결정/잠정)·미결을 한 문서로 묶는다. 모든 수치에
근거 도면(ord·page·mm_bbox)을 병기한다. 본문 해시가 바뀔 때만 버전이 오른다 — 재실행이
문서를 늘리지 않는다. 결정은 판독값을 고치지 않고 병기한다(설계 D4).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import psycopg

from m3d.config import Config

STATUS_ORDER = ("확정", "추정", "검토지적")
READING_KEYS = ("region", "ord", "page_no", "item", "value_raw", "unit", "status", "mm_bbox", "crosscheck")
AMB_KEYS = ("id", "ord", "page_no", "item", "options", "model_impact", "status",
            "choice_index", "choice_label", "provisional", "note", "decided_at")


def fetch_ssot_inputs(conn, dataset: str) -> tuple[dict, list[dict], list[dict]]:
    """DB 에서 프로젝트·판독·애매성(최신 결정 조인)을 읽는다."""
    with conn.cursor() as cur:
        cur.execute("select id, slug, name, coord_system, coord_assumptions from projects where slug = %s",
                    (dataset,))
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(f"프로젝트 '{dataset}' 없음 — seed 먼저")
        project_id, slug, name, coord_system, coord_assumptions = row
        project = {"slug": slug, "name": name, "coord_system": coord_system,
                   "coord_assumptions": list(coord_assumptions or [])}

        cur.execute(
            "select r.region, s.ord, sp.page_no, r.item, r.value_raw, r.unit, r.status, "
            "       r.basis_mm_bbox, r.crosscheck "
            "from readings r join sheets s on s.id = r.basis_sheet_id "
            "left join sheet_pages sp on sp.id = r.basis_page_id "
            "where r.project_id = %s order by r.region, s.ord, sp.page_no, r.item", (project_id,))
        readings = [dict(zip(READING_KEYS, r)) for r in cur.fetchall()]

        cur.execute(
            "select a.id, s.ord, sp.page_no, a.item, a.options, a.model_impact, a.status, "
            "       d.choice_index, d.choice_label, d.provisional, d.note, d.decided_at "
            "from ambiguities a join sheets s on s.id = a.basis_sheet_id "
            "left join sheet_pages sp on sp.id = a.sheet_page_id "
            "left join lateral (select choice_index, choice_label, provisional, note, decided_at "
            "                   from decisions where ambiguity_id = a.id "
            "                   order by decided_at desc limit 1) d on true "
            "where a.project_id = %s order by s.ord, sp.page_no, a.item", (project_id,))
        ambiguities = [dict(zip(AMB_KEYS, r)) for r in cur.fetchall()]
    return project, readings, ambiguities


def _bbox(b) -> str:
    return "[" + ", ".join(f"{float(v):g}" for v in (b or [])) + "]"


def _crosscheck(c) -> str:
    if not c:
        return ""
    return str(c.get("expr", "")) if isinstance(c, dict) else str(c)


def _iso(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


def build_ssot(project: dict, readings: list[dict], ambiguities: list[dict]) -> tuple[str, dict]:
    """(마크다운 본문, JSON dict). 본문에는 생성 시각을 넣지 않는다 — 해시가 안정돼야 한다."""
    lines = [f"# 실측정리 — {project['name']} ({project['slug']})", ""]
    lines += ["## 0. 좌표계·가정", "", "```json",
              json.dumps(project["coord_system"], ensure_ascii=False, indent=2), "```", ""]
    lines += [f"- 가정·정정: {note}" for note in project["coord_assumptions"]]
    lines.append("")

    for n, status in enumerate(STATUS_ORDER, start=1):
        rows = [r for r in readings if r["status"] == status]
        lines += [f"## {n}. {status} ({len(rows)}건)", ""]
        for region in sorted({r["region"] for r in rows}):
            lines += [f"### {region} 계열", "", "| 항목 | 값 | 단위 | 근거 | 검산 |", "|---|---|---|---|---|"]
            for r in (x for x in rows if x["region"] == region):
                lines.append(f"| {r['item']} | {r['value_raw']} | {r['unit'] or ''} | "
                             f"{r['ord']} p{r['page_no']} {_bbox(r['mm_bbox'])} | {_crosscheck(r['crosscheck'])} |")
            lines.append("")

    decided = [a for a in ambiguities if a["choice_index"] is not None]
    open_ = [a for a in ambiguities if a["choice_index"] is None]
    provisional_n = sum(1 for a in decided if a["provisional"])
    lines += [f"## 4. 결정 ({len(decided)}건 — 잠정 {provisional_n}건)", ""]
    for a in decided:
        opt = a["options"][a["choice_index"]]
        kind = "잠정" if a["provisional"] else "결정"
        lines += [f"### [{kind}] {a['item']} — {a['ord']} p{a['page_no']}",
                  f"- 선택: {a['choice_label']} — 근거: {opt.get('basis', '')}",
                  f"- 모델 영향: {a['model_impact']}"]
        if a["note"]:
            lines.append(f"- 메모: {a['note']}")
        lines += [f"- 결정 시각: {_iso(a['decided_at'])}", ""]

    lines += [f"## 5. 미결 ({len(open_)}건)", ""]
    for a in open_:
        lines.append(f"### {a['item']} — {a['ord']} p{a['page_no']}")
        lines += [f"- ({i}) {o['label']} — {o['basis']}" for i, o in enumerate(a["options"])]
        lines += [f"- 모델 영향: {a['model_impact']}", ""]

    counts = {"readings": {s: sum(1 for r in readings if r["status"] == s) for s in STATUS_ORDER},
              "decided": len(decided), "provisional": provisional_n, "open": len(open_)}
    lines += ["## 6. 통계", "",
              f"- 판독 {len(readings)}건: " + ", ".join(f"{s} {counts['readings'][s]}" for s in STATUS_ORDER),
              f"- 결정 {counts['decided']}건(잠정 {counts['provisional']}), 미결 {counts['open']}건", ""]

    doc = {
        "project": project,
        "readings": [{k: r[k] for k in READING_KEYS} for r in readings],
        "decisions": [{"ambiguity_id": str(a["id"]), "ord": a["ord"], "page_no": a["page_no"],
                       "item": a["item"], "choice_index": a["choice_index"],
                       "choice_label": a["choice_label"],
                       "basis": a["options"][a["choice_index"]].get("basis", ""),
                       "provisional": bool(a["provisional"]), "model_impact": a["model_impact"],
                       "note": a["note"] or "", "decided_at": _iso(a["decided_at"])} for a in decided],
        "open": [{"ambiguity_id": str(a["id"]), "ord": a["ord"], "page_no": a["page_no"],
                  "item": a["item"], "options": a["options"], "model_impact": a["model_impact"]}
                 for a in open_],
        "counts": counts,
    }
    return "\n".join(lines), doc


def run_ssot(cfg: Config, dataset: str) -> dict:
    """문서를 생성한다. 본문 해시가 마지막 버전과 같으면 아무것도 쓰지 않는다."""
    with psycopg.connect(cfg.require_db_url()) as conn:
        project, readings, ambiguities = fetch_ssot_inputs(conn, dataset)
    body, doc = build_ssot(project, readings, ambiguities)

    out_dir = cfg.derived_dir / dataset / "ssot"
    out_dir.mkdir(parents=True, exist_ok=True)
    index_path = out_dir / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else []
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if index and index[-1]["sha256"] == sha:
        v = index[-1]["version"]
        return {"changed": False, "version": v, "path": str(out_dir / f"실측정리_v{v}.md"),
                "counts": doc["counts"]}

    version = (index[-1]["version"] + 1) if index else 1
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    md_path = out_dir / f"실측정리_v{version}.md"
    md_path.write_text(f"<!-- version {version} · generated {generated_at} -->\n" + body, encoding="utf-8")
    (out_dir / "ssot.json").write_text(
        json.dumps({"version": version, "generated_at": generated_at, **doc},
                   ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    index.append({"version": version, "sha256": sha, "generated_at": generated_at, "counts": doc["counts"]})
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"changed": True, "version": version, "path": str(md_path), "counts": doc["counts"]}
