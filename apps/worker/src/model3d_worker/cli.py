"""m3d — model3d-studio 워커 CLI.

M0 에서 제공하는 것: 환경 점검(doctor), 샘플 세트 연결(samples), 계약 검증(contracts).
파이프라인 단계 [2]~[8] 은 M1 이후에 붙는다 — 여기서 그 사실을 숨기지 않는다.
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path

import typer

from . import __version__
from .config import get_settings, raw_sample_source, sample_source_env_name
from .contracts.schemas import SCHEMA_FILES, fixture_dir, repo_root, schema_dir
from .samples import list_sample_sets
from .samples.cli import app as samples_app

app = typer.Typer(
    name="m3d",
    help="model3d-studio 워커 — 도면 기반 3D 모델링 파이프라인",
    no_args_is_help=True,
    add_completion=False,
)
contracts_app = typer.Typer(help="공유 데이터 계약", no_args_is_help=True)
app.add_typer(samples_app, name="samples")
app.add_typer(contracts_app, name="contracts")

_OK = "✓"
_NO = "✗"
_WARN = "!"


@app.command()
def version() -> None:
    """버전을 출력한다."""
    typer.echo(f"model3d-worker {__version__}")


@app.command()
def doctor() -> None:
    """환경 점검. **설정되지 않은 것을 설정된 것처럼 보고하지 않는다.**"""
    s = get_settings()
    typer.echo(
        f"model3d-worker {__version__}  (python {platform.python_version()}, {sys.platform})"
    )
    typer.echo(f"리포 루트         : {repo_root()}")
    typer.echo(f"작업 디렉터리     : {s.resolved_work_dir()}")

    mark = _OK if s.supabase_configured else _WARN
    detail = (
        "설정됨"
        if s.supabase_configured
        else "미설정 — .env 의 SUPABASE_URL / SUPABASE_SERVICE_KEY"
    )
    typer.echo(f"{mark} Supabase        : {detail}")

    mark = _OK if s.llm_configured else _WARN
    typer.echo(f"{mark} ANTHROPIC_API_KEY: {'설정됨' if s.llm_configured else '미설정'}")

    try:
        sd = schema_dir()
        typer.echo(f"{_OK} 계약 스키마     : {len(SCHEMA_FILES)}개 ({sd})")
    except FileNotFoundError as e:
        typer.echo(f"{_NO} 계약 스키마     : {e}")

    sets = list_sample_sets()
    typer.echo(f"  샘플 세트       : {len(sets)}개")
    for st in sets:
        raw = raw_sample_source(st.set_id)
        work = st.work_root(s.resolved_work_dir())
        if raw is None:
            state = f"{_WARN} 원본 미설정 ({sample_source_env_name(st.set_id)})"
        elif not Path(raw).is_dir():
            state = f"{_NO} 원본 접근 불가: {raw}"
        else:
            state = f"{_OK} 원본 {raw}"
        ingested = f"ingest됨({work})" if work.is_dir() else "미ingest"
        manifest = "매니페스트 있음" if st.has_manifest() else "매니페스트 없음"
        typer.echo(f"    - {st.set_id}: {state} · {ingested} · {manifest}")


@contracts_app.command("check")
def contracts_check() -> None:
    """계약 픽스처를 JSON Schema 와 pydantic 양쪽으로 검증한다.

    규칙(§2·§3·§4·§6)이 **실제로 강제되는지**의 증거다:
    valid 는 전부 통과해야 하고, invalid 는 전부 거부되어야 한다.
    """
    import json

    from jsonschema import Draft202012Validator, FormatChecker

    from .contracts import models as m
    from .contracts.schemas import load_schema

    failures = 0

    for name in SCHEMA_FILES:
        try:
            Draft202012Validator.check_schema(load_schema(name))
        except Exception as exc:  # noqa: BLE001 — 어떤 실패든 보고한다
            failures += 1
            typer.echo(f"{_NO} 스키마 불량 {name}: {exc}", err=True)
    typer.echo(f"{_OK} 스키마 {len(SCHEMA_FILES)}개 검사")

    model_by_case: dict[str, type[m.BaseContract]] = {
        "ambiguity.cases.json": m.Ambiguity,
        "decision.cases.json": m.Decision,
        "ssot_item.cases.json": m.SsotItem,
        "verification_report.cases.json": m.VerificationReport,
    }
    for case_file, model in model_by_case.items():
        data = json.loads((fixture_dir() / case_file).read_text(encoding="utf-8"))
        validator = Draft202012Validator(
            load_schema(data["schema"]), format_checker=FormatChecker()
        )
        for i, doc in enumerate(data.get("valid", [])):
            errs = list(validator.iter_errors(doc))
            if errs:
                failures += 1
                typer.echo(f"{_NO} {case_file} valid[{i}] 스키마 거부: {errs[0].message}", err=True)
            try:
                model.model_validate(doc)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                typer.echo(f"{_NO} {case_file} valid[{i}] pydantic 거부: {exc}", err=True)
        for i, case in enumerate(data.get("invalid", [])):
            schema_rejected = bool(list(validator.iter_errors(case["doc"])))
            try:
                model.model_validate(case["doc"])
                pydantic_rejected = False
            except Exception:  # noqa: BLE001
                pydantic_rejected = True
            if not schema_rejected:
                failures += 1
                typer.echo(
                    f"{_NO} {case_file} invalid[{i}] 스키마 통과됨 (거부되어야 함): {case['why']}",
                    err=True,
                )
            if not pydantic_rejected:
                failures += 1
                typer.echo(
                    f"{_NO} {case_file} invalid[{i}] pydantic 통과됨 "
                    f"(거부되어야 함): {case['why']}",
                    err=True,
                )
        typer.echo(
            f"{_OK} {case_file}: valid {len(data.get('valid', []))} / "
            f"invalid {len(data.get('invalid', []))}"
        )

    if failures:
        typer.echo(f"{_NO} {failures}건 실패", err=True)
        raise typer.Exit(1)
    typer.echo(f"{_OK} 계약 검증 통과 — 스키마와 pydantic 이 같은 판정을 냈습니다")


if __name__ == "__main__":
    app()
