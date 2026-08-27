"""m3d CLI 엔트리 (설계서 §6). make 가 없는 환경이라 이 CLI 가 태스크 러너를 겸한다."""

from __future__ import annotations

import sys

import typer

from m3d import doctor as doctor_mod
from m3d.config import load_config
from m3d.samples.collect import DATASET, collect, manifest_path
from m3d.samples.manifest import load_manifest, verify_manifest, write_manifest

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


if __name__ == "__main__":
    sys.exit(app())
