"""m3d CLI 엔트리 (설계서 §6). make 가 없는 환경이라 이 CLI 가 태스크 러너를 겸한다."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import typer

from m3d import db as db_mod
from m3d import doctor as doctor_mod
from m3d.catalog import run as catalog_run
from m3d.config import load_config
from m3d.convert import run as convert_run
from m3d.reading import crops as crops_run
from m3d.reading import region as reading_region
from m3d.reading import sheet as reading_sheet
from m3d.reading import store as reading_store
from m3d.reading.client import estimate_cost
from m3d.samples.collect import DATASET, collect, manifest_path
from m3d.samples.manifest import load_manifest, verify_manifest, write_manifest
from m3d.seed import ab1_p4p5 as seed_mod

app = typer.Typer(help="model3d-studio 워커 CLI", no_args_is_help=True)


@app.callback()
def main() -> None:
    """m3d — model3d-studio 워커 태스크 러너.

    주의: typer 는 서브커맨드가 1개뿐이면 이름 없이 바로 실행되도록
    축약한다(`m3d doctor` 가 "예상 밖 인자"로 실패함). 이후 태스크에서
    서브커맨드가 늘어나도 `m3d <command>` 형태가 항상 성립하도록 이
    콜백으로 그룹 모드를 강제한다.
    """


@app.command()
def doctor() -> None:
    """venv 스택 import 점검. 표로 보고하고 종료 코드는 0 을 유지한다."""
    checks = doctor_mod.run_doctor()
    typer.echo(f"{'패키지':<20} {'구분':<4} {'결과':<4} 상세")
    typer.echo("-" * 72)
    for check in checks:
        kind = "필수" if check.required else "선택"
        result = "PASS" if check.ok else "FAIL"
        detail = check.version if check.ok else (check.error or "")
        typer.echo(f"{check.name:<20} {kind:<4} {result:<4} {detail}")

    failures = doctor_mod.required_failures(checks)
    typer.echo("")
    if failures:
        names = ", ".join(f.name for f in failures)
        typer.echo(f"필수 {len(failures)}종 FAIL: {names} — M0 를 완료로 선언하지 마세요.")
    else:
        typer.echo(f"필수 {len(doctor_mod.REQUIRED)}종 PASS.")


samples_app = typer.Typer(help="샘플 도면 세트 수집·검증", no_args_is_help=True)
app.add_typer(samples_app, name="samples")


@samples_app.command("collect")
def samples_collect() -> None:
    """원본을 data/samples 로 복사하고 매니페스트를 생성한다."""
    cfg = load_config()
    manifest = collect(cfg)
    path = manifest_path(cfg)
    write_manifest(manifest, path)
    size_mb = manifest.total_bytes / 1024 / 1024
    typer.echo(f"데이터셋 {DATASET}: {len(manifest.entries)}파일 / {size_mb:.1f} MB")
    typer.echo(f"매니페스트: {path}")


@samples_app.command("verify")
def samples_verify() -> None:
    """매니페스트와 실제 파일을 대조한다. 불일치가 있으면 종료 코드 1."""
    cfg = load_config()
    manifest = load_manifest(manifest_path(cfg))
    report = verify_manifest(manifest, cfg.repo_root)

    if report.ok:
        typer.echo(f"{report.checked}/{report.checked} SHA256 일치 — PASS")
        raise typer.Exit(code=0)

    typer.echo(f"검사 {report.checked}개 — FAIL")
    for label, items in (
        ("누락", report.missing),
        ("변조", report.mismatched),
        ("여분", report.extra),
    ):
        if not items:
            continue
        typer.echo(f"  {label} {len(items)}개:")
        for rel_path in items[:10]:
            typer.echo(f"    {rel_path}")
        if len(items) > 10:
            typer.echo(f"    … 외 {len(items) - 10}개")
    raise typer.Exit(code=1)


db_app = typer.Typer(help="Supabase 스키마 적용·확인", no_args_is_help=True)
app.add_typer(db_app, name="db")


@db_app.command("apply")
def db_apply() -> None:
    """supabase/migrations/*.sql 을 순서대로 적용한다."""
    cfg = load_config()
    try:
        applied = db_mod.apply_migrations(cfg)
    except db_mod.MigrationError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)
    if applied:
        typer.echo(f"적용 {len(applied)}건: {', '.join(applied)}")
    else:
        typer.echo("적용할 마이그레이션이 없습니다 (모두 반영됨).")


@db_app.command("check")
def db_check() -> None:
    """테이블 행 수·RLS 상태·프로젝트 좌표계를 출력한다."""
    import json

    cfg = load_config()
    result = db_mod.check(cfg)

    typer.echo("테이블        행수   RLS")
    typer.echo("-" * 32)
    for table in db_mod.TABLES:
        rls = "on" if result["rls"].get(table) else "OFF"
        typer.echo(f"{table:<13} {result['counts'][table]:>5}   {rls}")

    if result["catalog_status_counts"]:
        dist = " / ".join(f"{k} {v}" for k, v in
                          sorted(result["catalog_status_counts"].items()))
        typer.echo(f"\ncatalog_status: {dist}")
        typer.echo(f"from_content 채움: {result['from_content_filled']} · "
                   f"페이지 크기 채움: {result['pages_sized']}")

    for project in result["projects"]:
        typer.echo(f"\n프로젝트 {project['slug']} — {project['name']}")
        typer.echo("좌표계: " + json.dumps(project["coord_system"], ensure_ascii=False, indent=2))
        for note in project["coord_assumptions"]:
            typer.echo(f"가정·정정: {note}")

    typer.echo("")
    for row in result["reading_stats"]:
        typer.echo(f"readings {row['region']}/{row['status']}: {row['n']}")
    typer.echo(f"ambiguities: {result['ambiguity_stats']}")
    # 아래 한 줄은 verify-m2a.ps1 이 정규식으로 읽는다 — 형식을 바꾸지 않는다(ASCII 고정)
    typer.echo(f"crops_ready={result['crops_ready']} crop_missing={result['crop_missing']} "
               f"crops_assets={result['crops_assets']}")


@app.command()
def seed(
    dataset: str = typer.Argument(..., help="데이터셋 슬러그 (예: ab1-p4p5)"),
    reseed: bool = typer.Option(False, "--reseed", help="기존 프로젝트를 지우고 다시 넣는다"),
) -> None:
    """샘플 세트를 projects/sheets/sheet_pages/assets 에 등재한다."""
    if dataset != DATASET:
        typer.echo(f"알 수 없는 데이터셋: {dataset} (현재 지원: {DATASET})")
        raise typer.Exit(code=1)

    cfg = load_config()
    counts = seed_mod.seed(cfg, reseed=reseed)
    for table, count in counts.items():
        typer.echo(f"{table:<13} {count:>5}")


@app.command()
def convert(
    dataset: str = typer.Argument(..., help="데이터셋 슬러그 (예: ab1-p4p5)"),
    force: bool = typer.Option(False, "--force", help="산출물이 있어도 재렌더"),
    workers: int = typer.Option(4, "--workers", help="병렬 워커 수"),
    compare: bool = typer.Option(True, "--compare/--no-compare",
                                 help="기존 샘플 PNG 와 지각 해시 회귀 대조"),
) -> None:
    """[2] DXF → 페이지 PNG + sheet_text JSON, DB 반영 (설계서 §3)."""
    cfg = load_config()
    raise typer.Exit(code=convert_run.run_convert(
        cfg, dataset, force=force, workers=workers, compare=compare))


@app.command()
def catalog(
    dataset: str = typer.Argument(..., help="데이터셋 슬러그 (예: ab1-p4p5)"),
    force: bool = typer.Option(False, "--force", help="값이 같아도 재기록"),
) -> None:
    """[3] 표제란 추출 → 파일명과 기계 대조 → catalog_status (설계서 §6)."""
    cfg = load_config()
    raise typer.Exit(code=catalog_run.run_catalog(cfg, dataset, force=force))


@app.command()
def crops(
    dataset: str = typer.Argument(..., help="데이터셋 슬러그"),
    force: bool = typer.Option(False, "--force", help="이미 있어도 재생성"),
) -> None:
    """[5 준비] ambiguity 크롭 생성 — 질문 카드의 이미지 (설계서 §6)."""
    cfg = load_config()
    try:
        r = crops_run.run_crops(cfg, dataset, force=force)
    except RuntimeError as exc:
        typer.echo(f"실패: {exc}")
        raise typer.Exit(code=1) from None
    typer.echo(f"크롭 {r['made']}건 생성 / {r['skipped']}건 스킵 / "
               f"고아 정리 {r['purged']}건 / 전체 {r['total']}건")
    # 아래 한 줄은 verify-m2a.ps1 이 정규식으로 읽는다 — 형식을 바꾸지 않는다(ASCII 고정)
    typer.echo(f"made={r['made']} skipped={r['skipped']} purged={r['purged']} "
               f"failures={len(r['failures'])} total={r['total']}")
    for aid, err in r["failures"]:
        typer.echo(f"  실패 {aid}: {err}")
    raise typer.Exit(code=1 if r["failures"] else 0)


def _read_pages(cfg, dataset, pages, *, force, cache_only):
    """페이지별 시트 판독. (계열별 [(ord, out)], 총비용, 실패목록) 을 돌려준다."""
    outs: dict[str, list] = {}
    total_cost, failures = 0.0, []
    for i, page in enumerate(pages, start=1):
        try:
            out, usage = reading_sheet.read_sheet(cfg, dataset, page,
                                                  force=force, cache_only=cache_only)
        except Exception as exc:
            failures.append((f"{page.ord}p{page.page_no}", f"{type(exc).__name__}: {exc}"))
            typer.echo(f"[{i}/{len(pages)}] {page.ord}p{page.page_no} 실패: {type(exc).__name__}")
            continue
        cost = 0.0 if usage["cached"] else estimate_cost(
            usage["model"], usage["in"], usage["out"])
        total_cost += cost
        mark = "캐시" if usage["cached"] else f"${cost:.4f}"
        outs.setdefault(page.region, []).append((page.ord, out))
        typer.echo(f"[{i}/{len(pages)}] {page.ord}p{page.page_no} "
                   f"readings {len(out.readings)} / ambiguities {len(out.ambiguities)} ({mark})")
    return outs, total_cost, failures


def _save_review(cfg, dataset, region, log):
    """검토 기록 저장. 기존 파일은 UTC 타임스탬프를 붙여 보존한다(비교용)."""
    path = cfg.derived_dir / dataset / f"review-{region}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path.replace(path.with_name(f"review-{region}.{stamp}.json"))
    path.write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8", newline="\n")
    return path


def _finish(total_cost, failures):
    typer.echo(f"\n합계 비용 ${total_cost:.4f} / 실패 {len(failures)}건")
    for ref, err in failures:
        typer.echo(f"  실패 {ref}: {err}")
    raise typer.Exit(code=1 if failures else 0)


@app.command()
def read(
    dataset: str = typer.Argument(..., help="데이터셋 슬러그"),
    region: str = typer.Option(None, "--region", help="계열 필터 (A~F)"),
    sheet: str = typer.Option(None, "--sheet", help="시트 ord 필터 — DB 반영 없음"),
    force: bool = typer.Option(False, "--force", help="캐시 무시·검토 결과 덮어쓰기"),
    cache_only: bool = typer.Option(False, "--cache-only",
                                    help="캐시만 사용 — 미스는 실패(무과금 보증)"),
) -> None:
    """[4] 시트 판독 + 계열 통합 → readings·ambiguities (round 2) 반영."""
    if force and cache_only:
        typer.echo("--force 와 --cache-only 는 함께 쓸 수 없습니다.")
        raise typer.Exit(code=2)

    cfg = load_config()
    pages = reading_sheet.list_pages(cfg, dataset, region=region, ord_=sheet)
    if not pages:
        typer.echo("대상 페이지가 없습니다 — convert 를 먼저 돌렸는지 확인하세요.")
        raise typer.Exit(code=1)

    typer.echo(f"판독 {len(pages)}페이지 (계열 {region or '전체'})")
    outs, total_cost, failures = _read_pages(cfg, dataset, pages,
                                             force=force, cache_only=cache_only)

    if sheet:
        typer.echo("--sheet 지정 시 DB 반영 없음 — 계열 반영은 --region 으로 실행하세요.")
        _finish(total_cost, failures)

    failed_regions = {ref[0] for ref, _ in failures}
    for reg, sheet_outs in sorted(outs.items()):
        if reg in failed_regions:
            typer.echo(f"[{reg}] 시트 실패가 있어 통합·DB 반영을 건너뜁니다(전건 성공일 때만 반영).")
            continue
        if not force:
            try:
                skip = reading_store.has_review_rows(cfg, dataset, reg)
            except Exception as exc:
                failures.append((f"{reg}:db", f"{type(exc).__name__}: {exc}"))
                typer.echo(f"[{reg}] 검토 확인 실패: {type(exc).__name__}")
                continue
            if skip:
                typer.echo(f"[{reg}] 검토 결과 보존 — 갱신하려면 `m3d review` 재실행 또는 --force")
                continue
        try:
            merged, usage = reading_region.merge_region(
                cfg, dataset, reg, sheet_outs, force=force, cache_only=cache_only)
        except Exception as exc:
            failures.append((reg, f"{type(exc).__name__}: {exc}"))
            typer.echo(f"[{reg}] 통합 실패: {type(exc).__name__}")
            continue
        total_cost += 0.0 if usage["cached"] else estimate_cost(
            usage["model"], usage["in"], usage["out"])
        rows_r, rows_a = reading_store.build_rows(reg, merged.readings,
                                                  merged.ambiguities, 2)
        try:
            res = reading_store.replace_region(cfg, dataset, reg, rows_r, rows_a)
        except Exception as exc:
            failures.append((f"{reg}:db", f"{type(exc).__name__}: {exc}"))
            typer.echo(f"[{reg}] DB 반영 실패: {type(exc).__name__}")
            continue
        typer.echo(f"[{reg}] DB 반영 readings {res['readings']} / "
                   f"ambiguities {res['ambiguities']} / id 보존 {res['kept']} / "
                   f"미해석 {res['failed']}")

    _finish(total_cost, failures)


@app.command()
def review(
    dataset: str = typer.Argument(..., help="데이터셋 슬러그"),
    region: str = typer.Option(None, "--region", help="계열 필터 (A~F)"),
    force: bool = typer.Option(
        False, "--force",
        help="검토 호출만 캐시 무시(시트 판독·통합은 캐시 사용; "
             "전부 재실행은 read --force 후 review)"),
    cache_only: bool = typer.Option(False, "--cache-only",
                                    help="캐시만 사용 — 미스는 실패(무과금 보증)"),
) -> None:
    """[4] 적대적 검토 → 검토 반영 결과를 readings (round 3) 로 반영 (설계서 §4-3)."""
    if force and cache_only:
        typer.echo("--force 와 --cache-only 는 함께 쓸 수 없습니다.")
        raise typer.Exit(code=2)

    cfg = load_config()
    pages = reading_sheet.list_pages(cfg, dataset, region=region)
    if not pages:
        typer.echo("대상 페이지가 없습니다 — convert·read 를 먼저 돌렸는지 확인하세요.")
        raise typer.Exit(code=1)

    outs, total_cost, failures = _read_pages(cfg, dataset, pages,
                                             force=False, cache_only=cache_only)
    failed_regions = {ref[0] for ref, _ in failures}
    for reg, sheet_outs in sorted(outs.items()):
        if reg in failed_regions:
            typer.echo(f"[{reg}] 시트 실패가 있어 검토를 건너뜁니다.")
            continue
        try:
            merged, u1 = reading_region.merge_region(
                cfg, dataset, reg, sheet_outs, force=False, cache_only=cache_only)
            reviewed, u2 = reading_region.review_region(
                cfg, dataset, reg, merged, force=force, cache_only=cache_only)
        except Exception as exc:
            failures.append((reg, f"{type(exc).__name__}: {exc}"))
            typer.echo(f"[{reg}] 검토 실패: {type(exc).__name__}")
            continue
        for u in (u1, u2):
            total_cost += 0.0 if u["cached"] else estimate_cost(u["model"], u["in"], u["out"])

        finals, ambs, log = reading_region.apply_findings(
            merged.readings, merged.ambiguities, reviewed.findings)
        rows_r, rows_a = reading_store.build_rows(reg, finals, ambs, 3)
        try:
            res = reading_store.replace_region(cfg, dataset, reg, rows_r, rows_a)
            path = _save_review(cfg, dataset, reg, log)
        except Exception as exc:
            failures.append((f"{reg}:db", f"{type(exc).__name__}: {exc}"))
            typer.echo(f"[{reg}] DB 반영 실패: {type(exc).__name__}")
            continue
        applied = sum(1 for e in log if e["applied"])
        typer.echo(f"[{reg}] 지적 {len(log)}건(반영 {applied}) → readings {res['readings']} / "
                   f"ambiguities {res['ambiguities']} / id 보존 {res['kept']} / "
                   f"미해석 {res['failed']}  기록: {path.name}")

    _finish(total_cost, failures)


if __name__ == "__main__":
    sys.exit(app())
