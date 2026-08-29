"""catalog 오케스트레이션 (설계서 §3·§6) — 표제란 대조 실행·DB 갱신·리포트.

멱등: 산출 값이 DB 현재 값과 같으면 갱신하지 않는다 (changed=False).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import typer

from m3d.catalog.reconcile import Verdict, reconcile
from m3d.catalog.titleblock import extract_titleblocks
from m3d.config import Config


@dataclass(frozen=True)
class SheetVerdict:
    ord: str
    drawing_no_filename: str
    verdict: Verdict
    changed: bool


def build_report(results: list["SheetVerdict"]) -> dict:
    counts: dict[str, int] = {}
    attention = []
    for r in results:
        counts[r.verdict.status] = counts.get(r.verdict.status, 0) + 1
        if r.verdict.status != "match" or r.verdict.notes:
            attention.append({
                "ord": r.ord,
                "drawing_no_filename": r.drawing_no_filename,
                "status": r.verdict.status,
                "drawing_no_content": r.verdict.drawing_no,
                "notes": list(r.verdict.notes),
            })
    return {
        "total": len(results),
        "counts": counts,
        "changed": sum(1 for r in results if r.changed),
        "attention": attention,
    }


def run_catalog(cfg: Config, dataset: str, *, force: bool = False) -> int:
    import ezdxf
    import psycopg
    from ezdxf import recover

    results: list[SheetVerdict] = []
    with psycopg.connect(cfg.require_db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select s.id, s.ord, s.drawing_no_from_filename, s.title_from_filename, "
                "s.drawing_no_from_content, s.title_from_content, s.scale_from_content, "
                "s.catalog_status "
                "from sheets s join projects p on p.id = s.project_id "
                "where p.slug = %s order by s.ord",
                (dataset,),
            )
            rows = cur.fetchall()
        if not rows:
            typer.echo(f"프로젝트 '{dataset}' 의 sheets 가 없습니다 — seed 먼저.")
            return 1

        with conn.cursor() as cur:
            for (sheet_id, ord_, drwno_file, title_file,
                 cur_drwno, cur_title, cur_scale, cur_status) in rows:
                dxf = cfg.samples_dir / dataset / "dxf" / f"{drwno_file}.dxf"
                try:
                    try:
                        doc = ezdxf.readfile(dxf)
                    except Exception:
                        doc, _aud = recover.readfile(dxf)
                    blocks = extract_titleblocks(doc)
                except Exception as exc:
                    typer.echo(f"{ord_}: DXF 읽기 실패 — {type(exc).__name__}: {exc}")
                    return 1

                v = reconcile(blocks, drwno_file, title_file)
                same = (cur_status == v.status and cur_drwno == v.drawing_no
                        and cur_title == v.title and cur_scale == v.scale)
                if same and not force:
                    results.append(SheetVerdict(ord_, drwno_file, v, changed=False))
                    continue
                cur.execute(
                    "update sheets set drawing_no_from_content=%s, "
                    "title_from_content=%s, scale_from_content=%s, catalog_status=%s "
                    "where id=%s",
                    (v.drawing_no, v.title, v.scale, v.status, sheet_id),
                )
                results.append(SheetVerdict(ord_, drwno_file, v, changed=True))
        conn.commit()

    report = build_report(results)
    out = cfg.derived_dir / dataset / "catalog_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    counts = report["counts"]
    typer.echo(f"대조 {report['total']}건 — "
               f"match {counts.get('match', 0)} / "
               f"mismatch {counts.get('mismatch', 0)} / "
               f"unreadable {counts.get('unreadable', 0)} "
               f"(갱신 {report['changed']}건)")
    for row in report["attention"]:
        typer.echo(f"  [{row['status']}] {row['ord']} {row['drawing_no_filename']}")
        for note in row["notes"]:
            typer.echo(f"      {note}")
    typer.echo(f"리포트: {out}")
    return 1 if counts.get("mismatch", 0) > 0 else 0
    # mismatch 는 파이프라인 실패가 아니라 '검출 성공' 이지만, 사람이 봐야 하므로
    # 종료 코드 1 로 주의를 끈다 (지식베이스 §3: 불일치만 사람이 본다)
