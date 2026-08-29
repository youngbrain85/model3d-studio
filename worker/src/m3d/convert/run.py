"""convert 오케스트레이션 (설계서 §3) — DXF 50건 → 페이지 61건, 병렬·멱등·DB 반영.

워커(별도 프로세스)가 렌더·텍스트 추출을 하고, DB 쓰기는 부모가 한다.
멱등: 산출물 파일이 존재하고 sha256 이 DB 등재값과 같으면 그 파일 전체를 스킵.
실패는 수집해 마지막에 보고 — 한 파일 때문에 전체를 멈추지 않는다 (원 PARTIAL 정신).
"""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

import typer

from m3d.compare import compare_files
from m3d.config import Config
from m3d.samples.manifest import sha256_file
from m3d.samples.source_manifest import SourceSheet, png_filenames

# 회귀 대조 경고 임계 (dHash 해밍 거리, 256비트).
# 이 가드는 '고정된 파일명 쌍'의 렌더러 드리프트를 감지한다 — 쌍 매핑 자체는
# test_regression_pairs_maps_to_sample_names 가 고정한다. 시트 구별 용도가 아니다:
# 2026-08-29 실측 크로스시트 최저 거리가 2 (1,830쌍, 중앙값 89)라 어떤 임계로도
# '같은 시트 vs 닮은 다른 시트' 는 못 가른다.
# 동일쌍 실측 분포: 61쌍 중 0×56 · 1×3 · 2×2 (최대 2) → 임계 = 4 (최대+2).
# 이를 넘는 드리프트는 렌더러/폰트 변경 신호이므로 육안 확인 대상이다.
DHASH_WARN: int | None = 4


@dataclass(frozen=True)
class PageJob:
    ord: str
    drawing_no: str
    title: str
    page_count: int
    dxf_path: str
    dataset: str
    out_dir_png: str
    out_dir_text: str
    force: bool = False
    expected: dict | None = None   # rel_path → sha256 (DB 등재값, 스킵 판단용)


def derived_paths(cfg: Config, dataset: str, ord_: str, drawing_no: str,
                  page_no: int) -> tuple[Path, Path]:
    base = cfg.derived_dir / dataset
    stem = f"{ord_}_{drawing_no}_p{page_no}"
    return base / "png" / f"{stem}.png", base / "text" / f"{stem}.json"


def plan_jobs(cfg: Config, rows, dataset: str = "ab1-p4p5",
              force: bool = False, expected: dict | None = None) -> list[PageJob]:
    """rows: (ord, drawing_no, title, page_count) 반복 — DB sheets 조회 결과."""
    jobs = []
    base = cfg.derived_dir / dataset
    for ord_, drawing_no, title, page_count in rows:
        jobs.append(PageJob(
            ord=ord_, drawing_no=drawing_no, title=title, page_count=page_count,
            dxf_path=str(cfg.samples_dir / dataset / "dxf" / f"{drawing_no}.dxf"),
            dataset=dataset,
            out_dir_png=str(base / "png"),
            out_dir_text=str(base / "text"),
            force=force,
            expected=expected,
        ))
    return sorted(jobs, key=lambda j: j.ord)


def regression_pairs(cfg: Config, dataset: str, rows) -> list[tuple[Path, Path]]:
    """(파생 PNG, 샘플 PNG) 쌍 — 샘플명은 M0 파일명 규칙(1p 접미 없음)을 따른다."""
    pairs = []
    sample_png = cfg.samples_dir / dataset / "png"
    for ord_, drawing_no, title, page_count in rows:
        sheet = SourceSheet(ord=ord_, grade="핵심", drawing_no=drawing_no,
                            title=title, page_count=page_count)
        names = png_filenames(sheet)
        for page_no in range(1, page_count + 1):
            derived, _ = derived_paths(cfg, dataset, ord_, drawing_no, page_no)
            pairs.append((derived, sample_png / names[page_no - 1]))
    return pairs


def worker_process(job: dict) -> dict:
    """1 DXF 전체 처리 — 별도 프로세스에서 실행 (모듈 최상위, 피클 가능)."""
    import ezdxf
    from ezdxf import recover

    from m3d.convert.frames import detect_frames, fallback_frame
    from m3d.convert.render import prepare_doc, render_frame
    from m3d.convert.sheet_text import build_sheet_text, collect_texts, write_sheet_text
    from m3d.samples.manifest import sha256_file as _sha

    out = {"ord": job["ord"], "pages": [], "error": None, "skipped_entities": 0}
    try:
        # ── 멱등 스킵: 모든 산출물이 존재하고 DB 등재 sha 와 같으면 렌더 생략 ──
        expected = job.get("expected") or {}
        if not job["force"] and expected:
            reuse = []
            for page_no in range(1, job["page_count"] + 1):
                stem = f"{job['ord']}_{job['drawing_no']}_p{page_no}"
                png = Path(job["out_dir_png"]) / f"{stem}.png"
                txt = Path(job["out_dir_text"]) / f"{stem}.json"
                ok = (png.is_file() and txt.is_file()
                      and expected.get(f"png/{png.name}") == _sha(png)
                      and expected.get(f"text/{txt.name}") == _sha(txt))
                if not ok:
                    reuse = None
                    break
                from PIL import Image
                Image.MAX_IMAGE_PIXELS = None
                with Image.open(png) as img:
                    w, h = img.width, img.height
                reuse.append(dict(page_no=page_no, png=str(png), png_sha=_sha(png),
                                  w=w, h=h, text=str(txt), text_sha=_sha(txt),
                                  fallback=False, reused=True))
            if reuse is not None:
                out["pages"] = reuse
                return out

        # ── 실제 처리 ────────────────────────────────────────────────
        try:
            doc = ezdxf.readfile(job["dxf_path"])
        except Exception:
            doc, _aud = recover.readfile(job["dxf_path"])

        frames = detect_frames(doc)
        if not frames:
            fb = fallback_frame(doc)
            if fb is None:
                out["error"] = "빈 modelspace"
                return out
            frames = [fb]

        if len(frames) != job["page_count"]:
            out["error"] = (f"도곽 {len(frames)}개 ≠ page_count {job['page_count']} "
                            "(편철·페이지 구조 확인 필요)")
            return out

        prepare_doc(doc)
        texts = collect_texts(doc)

        for frame in frames:
            stem = f"{job['ord']}_{job['drawing_no']}_p{frame.page_no}"
            png = Path(job["out_dir_png"]) / f"{stem}.png"
            txt = Path(job["out_dir_text"]) / f"{stem}.json"
            w, h = render_frame(doc, frame, png)
            payload = build_sheet_text(frame, texts, job["drawing_no"])
            write_sheet_text(payload, txt)
            out["pages"].append(dict(
                page_no=frame.page_no, png=str(png), png_sha=_sha(png),
                w=w, h=h, text=str(txt), text_sha=_sha(txt),
                fallback=frame.fallback, reused=False))
        return out
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out


def _load_sheet_rows(conn, dataset: str):
    with conn.cursor() as cur:
        cur.execute(
            "select s.id, s.ord, s.drawing_no_from_filename, s.title_from_filename, "
            "s.page_count, s.project_id "
            "from sheets s join projects p on p.id = s.project_id "
            "where p.slug = %s order by s.ord",
            (dataset,),
        )
        return cur.fetchall()


def run_convert(cfg: Config, dataset: str, *, force: bool = False,
                workers: int = 4, compare: bool = True) -> int:
    import psycopg

    with psycopg.connect(cfg.require_db_url()) as conn:
        sheet_rows = _load_sheet_rows(conn, dataset)
        if not sheet_rows:
            typer.echo(f"프로젝트 '{dataset}' 의 sheets 가 없습니다 — seed 먼저.")
            return 1
        project_id = sheet_rows[0][5]

        # DB 등재 sha 맵 (멱등 스킵 판단) — derived 자산만
        with conn.cursor() as cur:
            cur.execute(
                "select rel_path, sha256 from assets "
                "where project_id = %s and rel_path like %s",
                (project_id, f"data/derived/{dataset}/%"),
            )
            expected = {}
            prefix = f"data/derived/{dataset}/"
            for rel, sha in cur.fetchall():
                expected[rel.removeprefix(prefix)] = sha

        # (ord, page_no) → sheet_page_id / ord → sheet_id
        with conn.cursor() as cur:
            cur.execute(
                "select sp.id, s.ord, sp.page_no from sheet_pages sp "
                "join sheets s on s.id = sp.sheet_id where s.project_id = %s",
                (project_id,),
            )
            page_ids = {(o, n): i for i, o, n in cur.fetchall()}
        sheet_ids = {r[1]: r[0] for r in sheet_rows}

        rows = [(r[1], r[2], r[3], r[4]) for r in sheet_rows]
        jobs = plan_jobs(cfg, rows, dataset, force=force, expected=expected)

        results, failures = [], []
        typer.echo(f"convert 시작: DXF {len(jobs)}건, 워커 {workers}")
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(worker_process, asdict(j)): j for j in jobs}
            done = 0
            for fut in as_completed(futures):
                job = futures[fut]
                res = fut.result()
                done += 1
                if res["error"]:
                    failures.append((job.ord, res["error"]))
                    typer.echo(f"[{done}/{len(jobs)}] {job.ord} 실패: {res['error']}")
                    continue
                reused = all(p.get("reused") for p in res["pages"])
                label = "스킵(동일)" if reused else f"페이지 {len(res['pages'])}건"
                typer.echo(f"[{done}/{len(jobs)}] {job.ord} {label}")
                results.append((job, res))

        # ── DB 반영 (부모 프로세스) ──────────────────────────────────
        n_assets = 0
        with conn.cursor() as cur:
            for job, res in results:
                for p in res["pages"]:
                    sheet_id = sheet_ids[job.ord]
                    key = (job.ord, p["page_no"])
                    if key not in page_ids:
                        raise KeyError(f"sheet_pages 에 없는 페이지: {key} — seed 와 도곽 수 불일치")
                    page_id = page_ids[key]
                    cur.execute(
                        "update sheet_pages set width_px=%s, height_px=%s where id=%s",
                        (p["w"], p["h"], page_id),
                    )
                    for kind, path_key, sha_key in (("png", "png", "png_sha"),
                                                    ("text", "text", "text_sha")):
                        fpath = Path(p[path_key])
                        rel = fpath.relative_to(cfg.repo_root).as_posix()
                        cur.execute(
                            "insert into assets (project_id, sheet_id, sheet_page_id, "
                            "kind, role, rel_path, bytes, sha256) "
                            "values (%s,%s,%s,%s,'derived',%s,%s,%s) "
                            "on conflict (project_id, rel_path) do update set "
                            "bytes=excluded.bytes, sha256=excluded.sha256, "
                            "sheet_id=excluded.sheet_id, sheet_page_id=excluded.sheet_page_id",
                            (project_id, sheet_id, page_id, kind, rel,
                             fpath.stat().st_size, p[sha_key]),
                        )
                        n_assets += 1
        conn.commit()

    total_pages = sum(len(r["pages"]) for _, r in results)
    typer.echo(f"\n페이지 {total_pages}건 / assets 반영 {n_assets}건 / 실패 {len(failures)}건")
    for ord_, err in failures:
        typer.echo(f"  실패 {ord_}: {err}")

    # ── 회귀 대조 (설계서 §8-2) ─────────────────────────────────────
    if compare and not failures:
        pairs = regression_pairs(cfg, dataset, rows)
        report = []
        for derived, sample in pairs:
            if not (derived.is_file() and sample.is_file()):
                report.append({"derived": derived.name, "sample": sample.name,
                               "distance": None})
                continue
            report.append({"derived": derived.name, "sample": sample.name,
                           "distance": compare_files(derived, sample)})
        dists = [r["distance"] for r in report if r["distance"] is not None]
        rp = cfg.derived_dir / dataset / "compare_report.json"
        rp.write_text(json.dumps(
            {"pairs": report, "max": max(dists) if dists else None,
             "threshold": DHASH_WARN}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        typer.echo(f"\n회귀 대조 {len(dists)}쌍: 최대 {max(dists) if dists else '-'} / "
                   f"평균 {sum(dists)/len(dists):.1f}" if dists else "회귀 대조 쌍 없음")
        if DHASH_WARN is None:
            typer.echo("임계 미확정(DHASH_WARN=None) — 분포만 보고. 상위 5쌍:")
            for r in sorted(report, key=lambda r: -(r["distance"] or 0))[:5]:
                typer.echo(f"  {r['distance']:>4}  {r['derived']}")
        else:
            over = [r for r in report
                    if r["distance"] is None or r["distance"] > DHASH_WARN]
            for r in over:
                typer.echo(f"  임계 초과 {r['distance']}: {r['derived']} — 육안 확인 필요")
            typer.echo(f"임계 {DHASH_WARN} 초과: {len(over)}건")

    return 1 if failures else 0
