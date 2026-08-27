"""``m3d samples`` — 샘플 도면 세트 연결 명령.

종료 코드 규약 (스크립트·CI 가 분기할 수 있게 고정한다):

| 코드 | 뜻 |
|---|---|
| 0 | 정상. ``verify`` 의 ``ABSENT`` 도 기본은 0 이다 (원본 없는 환경은 오류가 아니다). |
| 1 | 불일치 — 누락·변조·초과. **항상 오류다.** |
| 2 | 사용자 설정 문제 — 원본 미설정, 알 수 없는 세트, 매니페스트 없음. |
| 3 | ``--require-files`` 인데 파일이 없음 (파이프라인 실행 전 게이트용). |
"""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Annotated

import typer

from ..config import get_settings, raw_sample_source, sample_source_env_name
from .ingest import IngestError, ingest_sample_set, write_manifest
from .manifest import VerifyState, verify_manifest
from .paths import PathPolicyError, display_path, explain_unusable_source
from .registry import SampleSet, SampleSetError, list_sample_sets, load_sample_set

app = typer.Typer(help="샘플 도면 세트 연결", no_args_is_help=True)

OK = "✓"
NO = "✗"
WARN = "!"

EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_CONFIG = 2
EXIT_FILES_REQUIRED = 3

_MAX_LIST = 20


def _echo_items(label: str, items: list[str]) -> None:
    for item in items[:_MAX_LIST]:
        typer.echo(f"  [{label}] {item}")
    if len(items) > _MAX_LIST:
        typer.echo(f"  [{label}] … 외 {len(items) - _MAX_LIST}건")


def _load(set_id: str) -> SampleSet:
    try:
        return load_sample_set(set_id)
    except KeyError as exc:
        typer.echo(f"{NO} {exc}", err=True)
        raise typer.Exit(EXIT_CONFIG) from exc


def _resolve_source(sample_set: SampleSet) -> Path:
    """원본 경로를 얻는다. 없거나 못 쓰면 **왜 그런지** 말하고 종료한다."""
    set_id = sample_set.set_id
    env_name = sample_source_env_name(set_id)
    raw = raw_sample_source(set_id)
    if raw is None:
        typer.echo(
            f"{NO} {set_id}: 원본 경로가 설정되지 않았습니다.\n"
            f"  리포 루트의 `.env` 에 다음 줄을 추가하세요:\n"
            f"    {env_name}={sample_set.source_hint or '<원본 디렉터리 경로>'}\n"
            "  주의: Windows 경로를 큰따옴표로 감싸지 마세요 — `.env` 파서가 백슬래시를\n"
            "  이스케이프로 해석해 경로가 망가집니다 (\\n·\\t 로 변합니다).",
            err=True,
        )
        raise typer.Exit(EXIT_CONFIG)

    source = Path(raw)
    if not source.is_dir():
        typer.echo(f"{NO} {explain_unusable_source(raw, source, env_name)}", err=True)
        raise typer.Exit(EXIT_CONFIG)
    return source


@app.command("list")
def samples_list() -> None:
    """등록된 샘플 세트를 나열한다."""
    sets = list_sample_sets()
    if not sets:
        typer.echo("등록된 샘플 세트가 없습니다 (samples/<set_id>/set.json).")
        raise typer.Exit(EXIT_OK)
    work_dir = get_settings().resolved_work_dir()
    for st in sets:
        if st.has_manifest():
            manifest = st.load_manifest()
            n_answer = len(manifest.answer_entries())
            meta = f"매니페스트 {len(manifest.entries)}개 항목 (정답 {n_answer})"
        else:
            meta = "매니페스트 없음"
        state = "ingest됨" if st.work_root(work_dir).is_dir() else "로컬 파일 없음"
        typer.echo(f"{st.set_id}  — {st.description}")
        typer.echo(f"    {meta} · {state}")


@app.command("status")
def samples_status() -> None:
    """세트별로 원본·매니페스트·로컬 파일이 각각 있는지 보고한다."""
    sets = list_sample_sets()
    work_dir = get_settings().resolved_work_dir()
    for st in sets:
        raw = raw_sample_source(st.set_id)
        if raw is None:
            src_state = f"{WARN} 원본 미설정 ({sample_source_env_name(st.set_id)})"
        else:
            usable = Path(raw).is_dir()
            src_state = f"{OK} 원본 {raw}" if usable else f"{NO} 원본 접근 불가 {raw}"
        typer.echo(f"{st.set_id}:")
        typer.echo(f"  {src_state}")
        typer.echo(
            f"  {'매니페스트 있음' if st.has_manifest() else WARN + ' 매니페스트 없음'}"
            f" · {'로컬 파일 있음' if st.work_root(work_dir).is_dir() else '로컬 파일 없음'}"
        )


@app.command("ingest")
def samples_ingest(
    set_id: Annotated[str, typer.Argument(help="샘플 세트 id (samples/<set_id>)")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="복사하지 않고 계획만 보고")] = False,
    prune: Annotated[
        bool, typer.Option("--prune", help="원본에서 사라진 파일을 작업 디렉터리에서도 지운다")
    ] = False,
    recheck: Annotated[
        bool, typer.Option("--recheck", help="크기·mtime 이 같아도 해시로 다시 대조한다")
    ] = False,
    force: Annotated[bool, typer.Option("--force", help="전부 다시 복사한다")] = False,
) -> None:
    """원본 도면 세트를 작업 디렉터리로 복사하고 매니페스트를 갱신한다.

    원본은 읽기 전용이다 — 이 명령은 원본에 쓰지 않는다 (CLAUDE.md §2).
    정답 데이터는 ``answers/`` 로 분리되어 판독 입력과 섞이지 않는다.
    """
    st = _load(set_id)
    source = _resolve_source(st)
    settings = get_settings()

    try:
        result = ingest_sample_set(
            st,
            source,
            settings.resolved_work_dir(),
            dry_run=dry_run,
            prune=prune,
            recheck=recheck,
            force=force,
            generated_on=platform.system(),
        )
    except PathPolicyError as exc:
        typer.echo(f"{NO} 파일명 문제로 중단했습니다:\n{exc}", err=True)
        raise typer.Exit(EXIT_CONFIG) from exc
    except IngestError as exc:
        typer.echo(f"{NO} {exc}", err=True)
        raise typer.Exit(EXIT_CONFIG) from exc

    typer.echo(result.summary())

    if result.suspect_answers:
        typer.echo(
            f"{WARN} 정답처럼 보이는데 set.json 의 answers 에 선언되지 않은 파일이 "
            f"{len(result.suspect_answers)}건 있습니다. 추측으로 분류하지 않았습니다 (규칙 §3):"
        )
        _echo_items("의심", result.suspect_answers)
        typer.echo(f"  정답이 맞다면 samples/{set_id}/set.json 의 answers 에 추가하세요.")

    if dry_run:
        typer.echo(f"복사 예정 {len(result.copied)}건 / 그대로 둘 것 {len(result.skipped_same)}건")
        typer.echo("(dry-run — 복사도 매니페스트 기록도 하지 않았습니다)")
        raise typer.Exit(EXIT_OK)

    if result.stale:
        typer.echo(
            f"{WARN} 원본에 없는데 작업 디렉터리에 남아 있는 파일 {len(result.stale)}건 "
            "— `--prune` 으로 정리할 수 있습니다:"
        )
        _echo_items("잔여", result.stale)

    manifest = result.manifest
    if manifest is None:  # dry_run 이 아니면 항상 채워진다
        raise typer.Exit(EXIT_OK)
    path, changed = write_manifest(st, manifest)
    by_role: dict[str, int] = {}
    for e in manifest.entries:
        by_role[e.role] = by_role.get(e.role, 0) + 1
    typer.echo(f"매니페스트 {'기록' if changed else '변경 없음'}: {display_path(path)}")
    typer.echo("  역할별: " + ", ".join(f"{k}={v}" for k, v in sorted(by_role.items())))

    if manifest.answer_entries():
        typer.echo(
            f"  {WARN} 정답 데이터 {len(manifest.answer_entries())}건 → "
            f"{display_path(st.answers_root(settings.resolved_work_dir()))}"
        )
        typer.echo("     M3 대조 기준입니다. 판독 입력으로 넣지 마세요 (자기 채점 금지).")
        typer.echo(f"     봉인: {manifest.answers_seal}")
    if changed:
        shown = path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path
        typer.echo(f"  → 이 매니페스트를 커밋하세요: git add {shown}")


@app.command("verify")
def samples_verify(
    set_id: Annotated[str, typer.Argument(help="샘플 세트 id")],
    check_hashes: Annotated[
        bool, typer.Option("--hash/--no-hash", help="SHA256 까지 대조할지")
    ] = True,
    require_files: Annotated[
        bool,
        typer.Option(
            "--require-files",
            help="로컬 파일이 없으면 실패로 취급한다 (파이프라인 실행 전 게이트)",
        ),
    ] = False,
) -> None:
    """매니페스트와 실제 파일을 대조한다.

    파일이 없는 환경(이 클라우드 컨테이너, CI)은 ``ABSENT`` 로 **구분해 보고**하고
    기본적으로 성공한다 — 그 사실을 숨기지도, 영구 실패로 만들지도 않는다.
    """
    st = _load(set_id)
    try:
        manifest = st.load_manifest()
    except SampleSetError as exc:
        typer.echo(f"{NO} {exc}", err=True)
        raise typer.Exit(EXIT_CONFIG) from exc

    report = verify_manifest(
        st, manifest, get_settings().resolved_work_dir(), check_hashes=check_hashes
    )
    typer.echo(report.summary())
    for label, items in report.problems:
        _echo_items(label, items)
    if report.seal_broken:
        typer.echo(
            f"{NO} 정답 봉인이 깨졌습니다 — 정답 파일(M3 대조 기준)이 ingest 이후 바뀌었습니다.\n"
            "  정답을 고쳐 대조를 통과시키는 것은 검증이 아닙니다 (규칙 §6·§8)."
        )

    if report.state is VerifyState.MISMATCH:
        raise typer.Exit(EXIT_MISMATCH)
    if report.state is VerifyState.ABSENT and require_files:
        raise typer.Exit(EXIT_FILES_REQUIRED)
    raise typer.Exit(EXIT_OK)


@app.command("paths")
def samples_paths(
    set_id: Annotated[str, typer.Argument(help="샘플 세트 id")],
    answers: Annotated[
        bool, typer.Option("--answers", help="정답 경로를 낸다 (M3 대조 전용)")
    ] = False,
) -> None:
    """파이프라인이 쓸 입력 루트를 출력한다.

    기본은 판독 입력(``source/``)이다. 정답은 ``--answers`` 를 **명시**해야 나온다 —
    실수로 정답 경로를 판독 에이전트에 넘기는 일을 어렵게 만든다.
    """
    st = _load(set_id)
    work_dir = get_settings().resolved_work_dir()
    root = st.answers_root(work_dir) if answers else st.input_root(work_dir)
    if not root.is_dir():
        typer.echo(
            f"{NO} 아직 없습니다: {display_path(root)}\n"
            f"  `m3d samples ingest {set_id}` 를 먼저 실행하세요.",
            err=True,
        )
        raise typer.Exit(EXIT_FILES_REQUIRED)
    typer.echo(str(root))
