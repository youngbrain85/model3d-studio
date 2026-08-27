"""m3d CLI 엔트리 (설계서 §6). make 가 없는 환경이라 이 CLI 가 태스크 러너를 겸한다."""

from __future__ import annotations

import sys

import typer

from m3d import doctor as doctor_mod

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


if __name__ == "__main__":
    sys.exit(app())
