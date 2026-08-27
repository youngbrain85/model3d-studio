"""원본 도면 세트 → 리포 작업 디렉터리 복사.

CLAUDE.md §2: 참조 원본은 **읽기 전용 — 수정 금지**.

"쓰기 함수를 호출하지 않는다"는 약속만으로는 보장이 아니다. 네 겹으로 막는다.

1. **경로 분리 검사** — 목적지가 원본 안에 있거나, 원본이 목적지 안에 있거나, 둘이 같으면
   복사를 **시작하기 전에** 거부한다. (한쪽만 검사하면 반대 방향으로 원본이 오염된다.)
2. **목적지 봉쇄** — 목적지는 반드시 작업 디렉터리 안이어야 한다. 아니면 거부한다.
3. **단일 통로** — 원본 접근은 이 모듈의 ``_copy_one`` 하나뿐이고, 거기서 원본은
   ``src.open("rb")`` 로만 열린다. 원본 경로에 ``chmod``·``utime``·``unlink``·``mkdir`` 를
   호출하는 코드가 없다.
4. **증명 테스트** — ``tests/test_samples.py`` 가 ingest 전후로 원본 트리의
   (경로·크기·mtime_ns·내용 해시) 스냅샷을 떠서 완전히 같은지 확인한다.

   (정직하게: **atime 은 보장 대상이 아니다.** 파일을 읽으면 커널이 atime 을 갱신할 수
   있고 이는 어떤 읽기 도구도 피할 수 없다. 내용·크기·mtime·권한은 불변이다.)

또한 복사는 **원자적**이다. 같은 디렉터리의 임시 파일에 쓴 뒤 ``os.replace`` 로 옮긴다.
중단된 ingest 가 잘린 파일을 남겨 두면, 다음 verify 가 그것을 '변조'로 보고하거나
더 나쁘게는 파이프라인이 잘린 도면을 읽는다.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..contracts.models import SampleManifest, SampleManifestEntry
from .manifest import (
    CHUNK_SIZE,
    assemble_manifest,
    iso_mtime,
    manifest_payload_changed,
    scan_set,
    sha256_file,
)
from .paths import ScannedFile, display_path
from .registry import SampleSet


class IngestError(RuntimeError):
    """원본을 가져올 수 없거나, 가져오면 안 되는 상황."""


@dataclass
class IngestResult:
    set_id: str
    source: Path
    destination: Path
    dry_run: bool = False
    copied: list[str] = field(default_factory=list)
    skipped_same: list[str] = field(default_factory=list)
    """이미 같은 크기·mtime 으로 존재해 건너뛴 파일."""
    pruned: list[str] = field(default_factory=list)
    """원본에서 사라져 작업 디렉터리에서도 지운 파일 (``--prune``)."""
    stale: list[str] = field(default_factory=list)
    """원본에 없는데 작업 디렉터리에 남아 있는 파일 (``--prune`` 없이 발견만)."""
    suspect_answers: list[str] = field(default_factory=list)
    """정답처럼 보이는데 set.json 에 선언되지 않은 파일."""
    bytes_copied: int = 0
    manifest: SampleManifest | None = None

    @property
    def answers(self) -> list[str]:
        if self.manifest is None:
            return []
        return [e.path for e in self.manifest.answer_entries()]

    def summary(self) -> str:
        mb = self.bytes_copied / (1 << 20)
        head = (
            f"{self.set_id}: {len(self.copied)}개 복사({mb:.1f}MB), "
            f"{len(self.skipped_same)}개 건너뜀"
        )
        if self.pruned:
            head += f", {len(self.pruned)}개 정리"
        return f"{head} → {display_path(self.destination)}"


# ── 안전 검사 ─────────────────────────────────────────────────────────────
def _normcase_resolve(p: Path) -> Path:
    """비교용 정규화. Windows 는 대소문자를 구분하지 않으므로 맞춰 준다."""
    return Path(os.path.normcase(p.resolve()))


def _is_within(child: Path, parent: Path) -> bool:
    c, p = _normcase_resolve(child), _normcase_resolve(parent)
    return c == p or p in c.parents


def assert_source_protected(source: Path, destination: Path, work_dir: Path) -> None:
    """원본을 건드릴 수 있는 배치를 **시작 전에** 전부 거부한다."""
    if _normcase_resolve(source) == _normcase_resolve(destination):
        raise IngestError(
            f"원본과 목적지가 같습니다 ({display_path(source)}) — "
            "원본은 읽기 전용입니다 (CLAUDE.md §2)."
        )
    if _is_within(destination, source):
        raise IngestError(
            f"목적지({display_path(destination)})가 원본({display_path(source)}) 안에 있습니다 "
            "— 원본은 읽기 전용입니다 (CLAUDE.md §2).\n"
            "  작업 디렉터리(M3D_WORK_DIR)를 원본 밖으로 옮기세요."
        )
    if _is_within(source, destination):
        raise IngestError(
            f"원본({display_path(source)})이 목적지({display_path(destination)}) 안에 있습니다 "
            "— 복사가 원본을 덮어쓸 수 있습니다 (CLAUDE.md §2)."
        )
    if not _is_within(destination, work_dir):
        raise IngestError(
            f"목적지({display_path(destination)})가 작업 디렉터리"
            f"({display_path(work_dir)}) 밖입니다 — 가져온 도면은 `.gitignore` 되는 "
            "작업 디렉터리 안에만 둡니다."
        )


# ── 복사 ──────────────────────────────────────────────────────────────────
def _copy_one(src: Path, dst: Path) -> tuple[int, str]:
    """원본 하나를 원자적으로 복사하면서 해시를 함께 계산한다.

    한 번만 읽는다 — 대용량 도면 PDF 를 해시용으로 두 번 읽지 않기 위해서다.
    원본은 ``"rb"`` 로만 열린다. 쓰기는 전부 목적지 쪽이다.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    size = 0
    fd, tmp_name = tempfile.mkstemp(dir=dst.parent, prefix=".m3d-", suffix=".part")
    tmp = Path(tmp_name)
    try:
        with src.open("rb") as fsrc, os.fdopen(fd, "wb") as fdst:
            while chunk := fsrc.read(CHUNK_SIZE):
                h.update(chunk)
                size += len(chunk)
                fdst.write(chunk)
        # 원본의 mtime 을 목적지에 옮긴다 (목적지에만 쓴다).
        st = src.stat()
        os.utime(tmp, ns=(st.st_atime_ns, st.st_mtime_ns))
        shutil.copymode(src, tmp)
        tmp.replace(dst)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return size, h.hexdigest()


def _same_file(src_stat: os.stat_result, dst: Path) -> bool:
    """이미 같은 파일인가 — 크기 + mtime(초) 휴리스틱.

    mtime 을 초 단위로 비교하는 이유: FAT/exFAT 외장 드라이브는 2초 해상도이고
    Windows↔Linux 간 나노초가 보존되지 않는 경우가 있다. 확신이 필요하면
    ``--recheck`` 로 해시를 대조한다.
    """
    if not dst.is_file():
        return False
    dst_stat = dst.stat()
    return dst_stat.st_size == src_stat.st_size and int(dst_stat.st_mtime) == int(src_stat.st_mtime)


def ingest_sample_set(
    sample_set: SampleSet,
    source: Path,
    work_dir: Path,
    *,
    dry_run: bool = False,
    prune: bool = False,
    recheck: bool = False,
    force: bool = False,
    generated_on: str | None = None,
) -> IngestResult:
    """원본 세트를 작업 디렉터리로 복사하고 매니페스트를 만든다.

    원본에는 절대 쓰지 않는다. 위험한 배치는 시작 전에 거부한다.
    정답 데이터는 ``answers/`` 로, 나머지는 ``source/`` 로 **물리적으로 분리**해 놓는다.
    """
    if not source.is_dir():
        raise IngestError(
            f"{sample_set.set_id}: 원본 경로가 디렉터리가 아닙니다: {display_path(source)}\n"
            "  .env 의 M3D_SAMPLE_SOURCE_* 를 확인하세요."
        )

    destination = sample_set.work_root(work_dir)
    assert_source_protected(source, destination, work_dir)

    result = IngestResult(
        set_id=sample_set.set_id, source=source, destination=destination, dry_run=dry_run
    )

    # 스캔은 읽기 전용이며, 여기서 파일명 문제(cp949 깨짐·NFC 충돌)를 먼저 잡는다.
    scanned: list[ScannedFile] = scan_set(sample_set, source)
    result.suspect_answers = sample_set.suspect_answers([s.rel for s in scanned])

    entries: list[SampleManifestEntry] = []
    for item in scanned:
        decision = sample_set.classify(item.rel)
        dst = sample_set.destination_for(work_dir, item.rel, decision.role)
        src_stat = item.path.stat()

        reuse = not force and _same_file(src_stat, dst)
        if reuse and recheck:
            reuse = sha256_file(dst) == sha256_file(item.path)

        if dry_run:
            (result.skipped_same if reuse else result.copied).append(item.rel)
            continue

        if reuse:
            result.skipped_same.append(item.rel)
            digest = sha256_file(dst)
            size = src_stat.st_size
        else:
            size, digest = _copy_one(item.path, dst)
            result.copied.append(item.rel)
            result.bytes_copied += size

        entries.append(
            SampleManifestEntry(
                path=item.rel,
                size=size,
                sha256=digest,
                mtime=iso_mtime(src_stat),
                role=decision.role,
                role_source=decision.source,
                matched_by=decision.matched_by,
            )
        )

    expected = {(sample_set.subdir_for(e.role), e.path) for e in entries}
    result.stale = _find_stale(sample_set, work_dir, expected) if not dry_run else []
    if prune and not dry_run:
        result.pruned = _prune(sample_set, work_dir, result.stale)
        result.stale = []

    if not dry_run:
        result.manifest = assemble_manifest(sample_set, entries, generated_on=generated_on)
    return result


def _find_stale(sample_set: SampleSet, work_dir: Path, expected: set[tuple[str, str]]) -> list[str]:
    """원본에서 사라졌는데 작업 디렉터리에 남아 있는 파일.

    이것을 보고하지 않으면, 지워진 도면이 매니페스트에 계속 살아남아 세트 구성을
    거짓으로 만든다.
    """
    root = sample_set.work_root(work_dir)
    out: list[str] = []
    for subdir in {sample_set.subdir_for("drawing"), sample_set.subdir_for("answer")}:
        sub_root = root / subdir
        if not sub_root.is_dir():
            continue
        for scanned in scan_set(sample_set, sub_root):
            if (subdir, scanned.rel) not in expected:
                out.append(f"{subdir}/{scanned.rel}")
    return sorted(out)


def _prune(sample_set: SampleSet, work_dir: Path, stale: list[str]) -> list[str]:
    """작업 디렉터리 안의 낡은 파일만 지운다. 원본은 절대 건드리지 않는다."""
    root = sample_set.work_root(work_dir)
    removed: list[str] = []
    for rel in stale:
        target = root / rel
        if not _is_within(target, root):  # 방어: 경로가 작업 디렉터리를 벗어나면 건너뛴다
            continue
        target.unlink(missing_ok=True)
        removed.append(rel)
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        if not dirnames and not filenames and Path(dirpath) != root:
            Path(dirpath).rmdir()
    return removed


def write_manifest(sample_set: SampleSet, manifest: SampleManifest) -> tuple[Path, bool]:
    """매니페스트를 ``samples/<set_id>/manifest.json`` 에 쓴다 — 이 파일은 **커밋한다**.

    내용이 같으면 다시 쓰지 않는다 (타임스탬프만 바뀌는 커밋 diff 를 만들지 않기 위해).
    돌려주는 bool 은 "실제로 바뀌었는가".
    """
    sample_set.dir.mkdir(parents=True, exist_ok=True)
    path = sample_set.manifest_path
    if path.is_file():
        try:
            existing = SampleManifest.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            existing = None  # 깨진 매니페스트는 덮어쓴다
        if existing is not None and not manifest_payload_changed(existing, manifest):
            return path, False
    path.write_text(manifest.model_dump_json(indent=2, exclude_none=False) + "\n", encoding="utf-8")
    return path, True
