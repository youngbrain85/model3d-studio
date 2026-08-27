"""샘플 매니페스트 — 112파일 SHA256 정본 (설계서 §6-2·§9).

460MB 바이너리는 커밋하지 않는다. 리포에 남는 이 JSON 이 무결성의 유일한 증거다.
원본 절대경로는 담지 않는다(머신 종속·경로 유출) — SAMPLE_SOURCE_DIR 기준 상대경로만.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

SCHEMA_VERSION = 1
CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ManifestEntry:
    rel_path: str            # 리포 루트 기준 POSIX 상대경로
    source_rel: str          # SAMPLE_SOURCE_DIR 기준 POSIX 상대경로
    kind: str                # dxf | pdf | png
    role: str                # source | derived
    bytes: int
    sha256: str
    ord: str | None = None
    drawing_no: str | None = None
    page_no: int | None = None


@dataclass(frozen=True)
class Manifest:
    dataset: str
    entries: tuple[ManifestEntry, ...]

    @property
    def total_bytes(self) -> int:
        return sum(e.bytes for e in self.entries)


@dataclass(frozen=True)
class VerifyReport:
    checked: int
    missing: tuple[str, ...]
    extra: tuple[str, ...]
    mismatched: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not (self.missing or self.extra or self.mismatched)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(manifest: Manifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA_VERSION,
        "dataset": manifest.dataset,
        "file_count": len(manifest.entries),
        "total_bytes": manifest.total_bytes,
        "entries": [asdict(entry) for entry in manifest.entries],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_manifest(path: Path) -> Manifest:
    payload = json.loads(path.read_text(encoding="utf-8"))

    if payload.get("schema") != SCHEMA_VERSION:
        raise ValueError(
            f"매니페스트 schema 불일치: {payload.get('schema')!r} (기대 {SCHEMA_VERSION})"
        )

    entries = tuple(ManifestEntry(**entry) for entry in payload["entries"])
    if len(entries) != payload["file_count"]:
        raise ValueError(
            f"file_count({payload['file_count']}) 와 entries 길이({len(entries)}) 가 "
            "다릅니다 — 매니페스트가 손상되었습니다."
        )

    return Manifest(dataset=payload["dataset"], entries=entries)


def verify_manifest(manifest: Manifest, repo_root: Path) -> VerifyReport:
    """목록 대비 누락·변조·여분을 모두 본다.

    여분(목록에 없는 파일)까지 잡아야 '이 폴더가 매니페스트와 같다' 고 말할 수 있다.
    """
    missing: list[str] = []
    mismatched: list[str] = []

    for entry in manifest.entries:
        target = repo_root / entry.rel_path
        if not target.is_file():
            missing.append(entry.rel_path)
            continue
        if target.stat().st_size != entry.bytes or sha256_file(target) != entry.sha256:
            mismatched.append(entry.rel_path)

    listed = {entry.rel_path for entry in manifest.entries}
    dataset_root = repo_root / "data" / "samples" / manifest.dataset
    present: set[str] = set()
    if dataset_root.is_dir():
        present = {
            path.relative_to(repo_root).as_posix()
            for path in dataset_root.rglob("*")
            if path.is_file()
        }

    return VerifyReport(
        checked=len(manifest.entries),
        missing=tuple(missing),
        extra=tuple(sorted(present - listed)),
        mismatched=tuple(mismatched),
    )
