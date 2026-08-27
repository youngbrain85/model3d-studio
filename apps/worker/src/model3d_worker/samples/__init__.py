"""샘플 도면 세트 연결 — 원본은 읽기 전용, 리포에는 매니페스트만.

한눈에 보는 규칙
----------------
- 원본(`.env` 의 ``M3D_SAMPLE_SOURCE_*``)은 **읽기 전용**이다. 복사만 한다 (CLAUDE.md §2).
- 실제 파일은 ``work/samples/<set_id>/`` 로 간다 — `.gitignore` 대상이다.
- ``samples/<set_id>/manifest.json`` 만 커밋한다 — 원본 없이도 구성을 알고 대조할 수 있다.
- 정답 데이터는 ``answers/`` 로 **물리적으로 분리**되고, ``set.json`` 에 **명시 선언**된
  것만 정답이 된다. 파일명으로 추측하지 않는다 (규칙 §3).
"""

from .ingest import (
    IngestError,
    IngestResult,
    assert_source_protected,
    ingest_sample_set,
    write_manifest,
)
from .manifest import (
    VerifyReport,
    VerifyState,
    assemble_manifest,
    build_manifest,
    entry_for,
    manifest_payload_changed,
    scan_set,
    seal_from_disk,
    sha256_file,
    verify_manifest,
)
from .paths import (
    DEFAULT_EXCLUDE,
    GlobSet,
    PathPolicyError,
    ScannedFile,
    explain_unusable_source,
    has_surrogates,
    looks_like_windows_path,
    mangled_by_dotenv_quoting,
    normalize_rel_path,
    scan_files,
    wsl_translation,
)
from .registry import (
    ANSWER_SUBDIR,
    INPUT_SUBDIR,
    RoleDecision,
    SampleSet,
    SampleSetError,
    list_sample_sets,
    load_sample_set,
    samples_dir,
)

__all__ = [
    "ANSWER_SUBDIR",
    "DEFAULT_EXCLUDE",
    "INPUT_SUBDIR",
    "GlobSet",
    "IngestError",
    "IngestResult",
    "PathPolicyError",
    "RoleDecision",
    "SampleSet",
    "SampleSetError",
    "ScannedFile",
    "VerifyReport",
    "VerifyState",
    "assemble_manifest",
    "assert_source_protected",
    "build_manifest",
    "entry_for",
    "explain_unusable_source",
    "has_surrogates",
    "ingest_sample_set",
    "list_sample_sets",
    "load_sample_set",
    "looks_like_windows_path",
    "mangled_by_dotenv_quoting",
    "manifest_payload_changed",
    "normalize_rel_path",
    "samples_dir",
    "scan_files",
    "scan_set",
    "seal_from_disk",
    "sha256_file",
    "verify_manifest",
    "write_manifest",
    "wsl_translation",
]
