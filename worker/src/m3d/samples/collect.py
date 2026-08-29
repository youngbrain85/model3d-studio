"""원본 → data/samples 복사 (설계서 §6-2).

원본은 읽기만 한다. 복사 후 사본 해시를 원본 해시와 대조하고, 원본의 크기·mtime 이
그대로인지도 확인한다. 재실행은 멱등 — 이미 같은 파일이면 건너뛴다.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import typer

from m3d.config import DXF_SUBDIR, PACKAGE_SUBDIR, Config
from m3d.samples.manifest import Manifest, ManifestEntry, sha256_file
from m3d.samples.source_manifest import (
    SourceSheet,
    dxf_filename,
    parse_source_manifest,
    png_filenames,
)

DATASET = "ab1-p4p5"
PDF_NAME = "P4P5_정밀조사_도면집.pdf"


class CollectError(RuntimeError):
    """원본 누락·복사 실패·원본 변경."""


@dataclass(frozen=True)
class PlannedFile:
    source: Path
    source_rel: str
    rel_path: str
    kind: str
    role: str
    ord: str | None
    drawing_no: str | None
    page_no: int | None


def manifest_path(cfg: Config) -> Path:
    return cfg.manifests_dir / f"{DATASET}.json"


def plan_files(cfg: Config, sheets: list[SourceSheet]) -> list[PlannedFile]:
    """무엇을 어디로 복사할지 결정한다. 파일시스템을 건드리지 않는다."""
    base = f"data/samples/{DATASET}"
    planned: list[PlannedFile] = []

    for sheet in sheets:
        dxf = dxf_filename(sheet)
        planned.append(
            PlannedFile(
                source=cfg.dxf_dir / dxf,
                source_rel=f"{DXF_SUBDIR}/{dxf}",
                rel_path=f"{base}/dxf/{dxf}",
                kind="dxf",
                role="source",
                ord=sheet.ord,
                drawing_no=sheet.drawing_no,
                page_no=None,
            )
        )
        for page_no, png in enumerate(png_filenames(sheet), start=1):
            planned.append(
                PlannedFile(
                    source=cfg.package_dir / png,
                    source_rel=f"{PACKAGE_SUBDIR}/{png}",
                    rel_path=f"{base}/png/{png}",
                    kind="png",
                    role="derived",
                    ord=sheet.ord,
                    drawing_no=sheet.drawing_no,
                    page_no=page_no,
                )
            )

    planned.append(
        PlannedFile(
            source=cfg.package_dir / PDF_NAME,
            source_rel=f"{PACKAGE_SUBDIR}/{PDF_NAME}",
            rel_path=f"{base}/pdf/{PDF_NAME}",
            kind="pdf",
            role="source",
            ord=None,
            drawing_no=None,
            page_no=None,
        )
    )
    return planned


def _copy_one(item: PlannedFile, repo_root: Path) -> tuple[ManifestEntry, bool]:
    """한 파일을 복사(또는 건너뜀)하고 (엔트리, 복사했는지) 를 돌려준다."""
    if not item.source.is_file():
        raise CollectError(f"원본이 없습니다: {item.source}")

    before = item.source.stat()
    source_hash = sha256_file(item.source)

    dest = repo_root / item.rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)

    copied = False
    already_same = (
        dest.is_file()
        and dest.stat().st_size == before.st_size
        and sha256_file(dest) == source_hash
    )
    if not already_same:
        shutil.copy2(item.source, dest)
        if sha256_file(dest) != source_hash:
            raise CollectError(f"복사 후 해시가 다릅니다: {item.rel_path}")
        copied = True

    after = item.source.stat()
    if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
        raise CollectError(
            f"원본이 변경되었습니다 — 즉시 중단합니다: {item.source} "
            "(참조 원본은 읽기 전용이어야 합니다)"
        )

    entry = ManifestEntry(
        rel_path=item.rel_path,
        source_rel=item.source_rel,
        kind=item.kind,
        role=item.role,
        bytes=before.st_size,
        sha256=source_hash,
        ord=item.ord,
        drawing_no=item.drawing_no,
        page_no=item.page_no,
    )
    return entry, copied


def collect(cfg: Config) -> Manifest:
    sheets = parse_source_manifest(cfg.source_manifest_path)
    planned = plan_files(cfg, sheets)

    entries: list[ManifestEntry] = []
    copied_count = 0
    for item in planned:
        entry, copied = _copy_one(item, cfg.repo_root)
        entries.append(entry)
        copied_count += int(copied)

    typer.echo(f"복사 {copied_count}개 / 건너뜀 {len(planned) - copied_count}개")
    return Manifest(dataset=DATASET, entries=tuple(entries))
