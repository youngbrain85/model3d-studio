"""샘플 도면 세트 매니페스트 — 만들기와 대조하기.

**왜 매니페스트인가**: 참조 원본(CLAUDE.md §2)은 사용자 로컬에만 있고 읽기 전용이다.
도면 PDF·DWG 는 용량이 커서 커밋할 수 없다. 그래서 리포에는 "이 세트에 무엇이 있어야
하는가"(경로·크기·SHA256·역할)만 커밋하고, 실제 파일은 ``.gitignore`` 된 작업 디렉터리로
ingest 한다. 원본이 없는 환경(이 클라우드 컨테이너, CI)에서도 세트 구성을 알 수 있고
나중에 무결성을 대조할 수 있다.

경로·파일명 정규화의 함정(NFC/NFD, cp949 깨짐)은 :mod:`.paths` 가 다룬다.

**세 가지 상태를 구분한다.** 이것이 "매니페스트만 있고 파일이 없을 때 우아하게"의 핵심이다.

| 상태 | 뜻 | 기본 종료코드 |
|---|---|---|
| ``OK`` | 파일이 있고 매니페스트와 일치 | 0 |
| ``ABSENT`` | 매니페스트는 있는데 이 머신에 파일이 없음 | 0 (정상) |
| ``MISMATCH`` | 파일이 있는데 다름 — 누락·변조·초과 | 1 (항상 오류) |

``ABSENT`` 를 오류로 만들면 원본 없는 CI 가 영구히 빨간불이 되고 결국 아무도 안 본다.
그렇다고 조용히 ``OK`` 로 만들면 "검증했다"는 거짓 보고가 된다 (규칙 §8). 그래서
**성공시키되 상태를 명시**하고, 파일이 반드시 있어야 하는 단계는 ``--require-files`` 로
강제하게 한다.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from ..contracts.models import SampleManifest, SampleManifestEntry, SampleRole
from .paths import ScannedFile, display_path, normalize_rel_path, scan_files
from .registry import SampleSet

CHUNK_SIZE = 1 << 20


class VerifyState(StrEnum):
    OK = "OK"
    ABSENT = "ABSENT"
    MISMATCH = "MISMATCH"


def sha256_file(path: Path, *, chunk_size: int = CHUNK_SIZE) -> str:
    """파일 해시. **읽기 전용** — 원본에도 안전하게 쓸 수 있다."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def iso_mtime(stat_result: os.stat_result) -> str:
    return datetime.fromtimestamp(stat_result.st_mtime, tz=UTC).isoformat()


# ── 만들기 ────────────────────────────────────────────────────────────────
def scan_set(sample_set: SampleSet, root: Path) -> list[ScannedFile]:
    """세트의 제외 규칙을 적용해 원본을 훑는다. **읽기만 한다.**"""
    return scan_files(root, exclude=sample_set.exclude_glob())


def entry_for(
    sample_set: SampleSet, scanned: ScannedFile, *, sha256: str | None = None
) -> SampleManifestEntry:
    """스캔된 파일 하나를 매니페스트 항목으로. 역할과 **그 근거**를 함께 남긴다.

    ``sha256`` 을 주면 다시 읽지 않는다 — ingest 는 복사하면서 해시를 계산하므로
    대용량 도면 PDF 를 두 번 읽을 이유가 없다.
    """
    decision = sample_set.classify(scanned.rel)
    stat = scanned.path.stat()
    return SampleManifestEntry(
        path=scanned.rel,
        size=stat.st_size,
        sha256=sha256 if sha256 is not None else sha256_file(scanned.path),
        mtime=iso_mtime(stat),
        role=decision.role,
        role_source=decision.source,
        matched_by=decision.matched_by,
    )


def assemble_manifest(
    sample_set: SampleSet,
    entries: Iterable[SampleManifestEntry],
    *,
    generated_on: str | None = None,
) -> SampleManifest:
    """항목들로 매니페스트를 조립하고 **정답 봉인**을 계산한다."""
    ordered = sorted(entries, key=lambda e: e.path)
    manifest = SampleManifest(
        manifest_version=2,
        set_id=sample_set.set_id,
        description=sample_set.description,
        source_hint=sample_set.source_hint,
        generated_at=datetime.now(tz=UTC).isoformat(),
        generated_on=generated_on,
        answers_seal=None,
        entries=ordered,
    )
    seal = manifest.compute_answers_seal()
    if seal is None:
        return manifest
    return manifest.model_copy(update={"answers_seal": seal})


def build_manifest(
    sample_set: SampleSet,
    root: Path,
    *,
    generated_on: str | None = None,
    scanned: Iterable[ScannedFile] | None = None,
) -> SampleManifest:
    """디렉터리를 훑어 매니페스트를 만든다. **읽기만 한다** — 원본을 건드리지 않는다."""
    files = list(scanned) if scanned is not None else scan_set(sample_set, root)
    return assemble_manifest(
        sample_set, (entry_for(sample_set, f) for f in files), generated_on=generated_on
    )


def manifest_payload_changed(old: SampleManifest, new: SampleManifest) -> bool:
    """``generated_at`` 만 다른 재생성인가.

    ingest 를 돌릴 때마다 타임스탬프가 바뀌어 매니페스트가 커밋 diff 를 더럽히면,
    사람은 곧 그 diff 를 안 읽게 된다. 내용이 같으면 다시 쓰지 않는다.
    """
    drop = {"generated_at"}
    return old.model_dump(exclude=drop) != new.model_dump(exclude=drop)


# ── 대조 ──────────────────────────────────────────────────────────────────
@dataclass
class VerifyReport:
    """매니페스트 ↔ 실제 파일 대조 결과."""

    set_id: str
    root: Path
    state: VerifyState
    expected: int = 0
    checked: int = 0
    missing: list[str] = field(default_factory=list)
    """매니페스트에 있으나 디스크에 없는 파일."""
    extra: list[str] = field(default_factory=list)
    """디스크에 있으나 매니페스트에 없는 파일."""
    size_mismatch: list[str] = field(default_factory=list)
    hash_mismatch: list[str] = field(default_factory=list)
    seal_broken: bool = False
    hashes_checked: bool = True

    @property
    def ok(self) -> bool:
        return self.state is VerifyState.OK

    @property
    def absent(self) -> bool:
        return self.state is VerifyState.ABSENT

    @property
    def problems(self) -> list[tuple[str, list[str]]]:
        return [
            ("누락", self.missing),
            ("매니페스트 밖", self.extra),
            ("크기 불일치", self.size_mismatch),
            ("해시 불일치", self.hash_mismatch),
        ]

    def summary(self) -> str:
        if self.state is VerifyState.ABSENT:
            return (
                f"{self.set_id}: ABSENT — 이 머신에는 파일이 없습니다 "
                f"(매니페스트 {self.expected}개 항목).\n"
                f"  원본이 있는 머신에서 `m3d samples ingest {self.set_id}` 를 실행하세요.\n"
                f"  기대 위치: {display_path(self.root)}"
            )
        if self.state is VerifyState.OK:
            scope = "크기+SHA256" if self.hashes_checked else "크기만 (--no-hash)"
            return f"{self.set_id}: OK — {self.checked}개 파일이 매니페스트와 일치 ({scope})"
        bits = [f"{label} {len(items)}" for label, items in self.problems if items]
        if self.seal_broken:
            bits.append("정답 봉인 깨짐")
        return f"{self.set_id}: MISMATCH — {', '.join(bits)}"


def verify_manifest(
    sample_set: SampleSet,
    manifest: SampleManifest,
    work_dir: Path,
    *,
    check_hashes: bool = True,
    roles: Iterable[SampleRole] | None = None,
) -> VerifyReport:
    """매니페스트와 ingest 된 실제 파일을 대조한다.

    항목의 역할에 따라 ``source/`` 와 ``answers/`` 중 맞는 쪽을 본다 —
    정답이 판독 입력 쪽에 있으면 그것 자체가 결함이므로 '누락'으로 잡힌다.

    파일이 아예 없으면 ``ABSENT`` 로 **구분해서** 보고한다 — 전부 '누락'으로 쏟아내
    사람이 진짜 문제를 못 보게 만들지 않는다.
    """
    work_root = sample_set.work_root(work_dir)
    role_filter = set(roles) if roles is not None else None
    wanted = [e for e in manifest.entries if role_filter is None or e.role in role_filter]

    report = VerifyReport(
        set_id=manifest.set_id,
        root=work_root,
        state=VerifyState.OK,
        expected=len(wanted),
        hashes_checked=check_hashes,
    )
    if not work_root.is_dir():
        report.state = VerifyState.ABSENT
        return report

    expected_paths: set[Path] = set()
    for entry in wanted:
        path = sample_set.destination_for(work_dir, entry.path, entry.role)
        expected_paths.add(path)
        if not path.is_file():
            report.missing.append(entry.path)
            continue
        report.checked += 1
        if path.stat().st_size != entry.size:
            report.size_mismatch.append(entry.path)
            continue
        if check_hashes and sha256_file(path) != entry.sha256:
            report.hash_mismatch.append(entry.path)

    if role_filter is None:
        for found in scan_files(work_root, exclude=sample_set.exclude_glob()):
            if found.path not in expected_paths:
                report.extra.append(normalize_rel_path(found.path.relative_to(work_root)))
        report.extra.sort()

    # 정답 봉인 — 정답을 고쳐 M3 대조를 통과시키는 일을 막는다 (규칙 §6·§8).
    if manifest.answers_seal is not None and check_hashes:
        recomputed = seal_from_disk(sample_set, manifest, work_dir)
        report.seal_broken = recomputed is not None and recomputed != manifest.answers_seal

    if any(items for _, items in report.problems) or report.seal_broken:
        report.state = VerifyState.MISMATCH
    return report


def seal_from_disk(sample_set: SampleSet, manifest: SampleManifest, work_dir: Path) -> str | None:
    """디스크의 정답 파일로 봉인을 다시 계산한다. 정답이 없거나 하나라도 없으면 None."""
    answers = sorted(manifest.answer_entries(), key=lambda e: e.path)
    if not answers:
        return None
    parts: list[str] = []
    for entry in answers:
        path = sample_set.destination_for(work_dir, entry.path, entry.role)
        if not path.is_file():
            return None
        parts.append(f"{entry.path}\0{sha256_file(path)}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
