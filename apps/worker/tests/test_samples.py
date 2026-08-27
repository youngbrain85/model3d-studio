"""샘플 세트 연결 — 원본 읽기 전용, 매니페스트 대조, 한글/경로 정규화.

여기의 테스트는 대부분 **실측된 실패**를 고정한 것이다. 특히:

- ``test_ingest_leaves_source_byte_identical`` 은 "원본은 읽기 전용" (CLAUDE.md §2)의 증명이다.
- ``test_answer_is_never_guessed`` 는 정답 데이터를 추측으로 확정하지 않는다는 규칙 §3 의 증명이다.
- NFD/cp949 계열은 리눅스에서 실제로 재현되는 파일명 함정이다.
"""

from __future__ import annotations

import json
import os
import stat
import unicodedata
from pathlib import Path

import pytest
from pydantic import ValidationError

from model3d_worker.config import sample_source_env_name
from model3d_worker.contracts.models import SampleManifest, SampleSetDef
from model3d_worker.samples import (
    GlobSet,
    IngestError,
    PathPolicyError,
    SampleSet,
    VerifyState,
    assemble_manifest,
    build_manifest,
    explain_unusable_source,
    ingest_sample_set,
    list_sample_sets,
    load_sample_set,
    looks_like_windows_path,
    mangled_by_dotenv_quoting,
    normalize_rel_path,
    scan_files,
    verify_manifest,
    write_manifest,
    wsl_translation,
)

ANSWER_GLOBS = ["**/SPEC_v2.md", "**/*재실측*.json", "정답/**"]


# ── 픽스처 ────────────────────────────────────────────────────────────────
@pytest.fixture
def source_tree(tmp_path: Path) -> Path:
    """한글 파일명·중첩 디렉터리·정답 데이터를 포함한 가짜 원본 세트."""
    root = tmp_path / "원본_P4P5"
    (root / "도면").mkdir(parents=True)
    (root / "사진").mkdir()
    (root / "정답").mkdir()
    (root / "도면" / "AB1-S-021_단면도.pdf").write_bytes(b"%PDF-1.7 fake")
    (root / "도면" / "AB1-S-034.dxf").write_text("0\nSECTION\n", encoding="utf-8")
    (root / "사진" / "P4_거더_01.jpg").write_bytes(b"\xff\xd8\xff fake jpeg")
    (root / "정답" / "SPEC_v2.md").write_text("# 사양 정본\n", encoding="utf-8")
    (root / "정답" / "접속1교_재실측.json").write_text("{}", encoding="utf-8")
    (root / "메모.txt").write_text("참고", encoding="utf-8")
    (root / ".DS_Store").write_bytes(b"junk")
    return root


@pytest.fixture
def sample_set(tmp_path: Path) -> SampleSet:
    d = tmp_path / "samples" / "test_set"
    d.mkdir(parents=True)
    return SampleSet(
        definition=SampleSetDef(
            set_id="test_set",
            description="테스트 세트",
            source_hint=r"D:\Projects\원본",
            answers=ANSWER_GLOBS,
        ),
        dir=d,
    )


@pytest.fixture
def work(tmp_path: Path) -> Path:
    return tmp_path / "work"


# ── 경로 정규화 ───────────────────────────────────────────────────────────
def test_normalize_rel_path_posix_and_nfc() -> None:
    assert normalize_rel_path(r"도면\AB1-S-021.pdf") == "도면/AB1-S-021.pdf"
    nfd = unicodedata.normalize("NFD", "도면/가.pdf")
    assert normalize_rel_path(nfd) == unicodedata.normalize("NFC", "도면/가.pdf")
    # macOS(NFD)와 Windows/Linux(NFC)가 같은 문자열을 낸다
    assert normalize_rel_path(nfd) == normalize_rel_path("도면/가.pdf")


def test_nfd_file_is_recorded_as_nfc(tmp_path: Path, sample_set: SampleSet) -> None:
    """macOS 가 만든 NFD 이름이 매니페스트에서는 NFC 로 통일된다.

    리눅스에서 NFC 이름으로는 그 파일이 **열리지 않는다** — 그래서 매니페스트 경로는
    식별자일 뿐이고, 실제 접근은 스캔이 돌려준 Path 로만 한다.
    """
    root = tmp_path / "nfd"
    root.mkdir()
    nfd_name = unicodedata.normalize("NFD", "단면도.pdf")
    (root / nfd_name).write_bytes(b"x")
    assert not (root / unicodedata.normalize("NFC", "단면도.pdf")).exists()

    scanned = scan_files(root)
    assert [s.rel for s in scanned] == [unicodedata.normalize("NFC", "단면도.pdf")]
    assert scanned[0].path.read_bytes() == b"x"  # 실제 Path 로는 열린다


def test_nfc_collision_is_refused_not_silently_overwritten(tmp_path: Path) -> None:
    """NFC/NFD 두 이름이 공존하면 복사 시 한쪽이 사라진다 — 조용히 넘어가지 않는다."""
    root = tmp_path / "collide"
    root.mkdir()
    (root / unicodedata.normalize("NFC", "가.pdf")).write_bytes(b"A")
    (root / unicodedata.normalize("NFD", "가.pdf")).write_bytes(b"B")
    if len(list(root.iterdir())) == 1:
        pytest.skip("이 파일시스템은 유니코드 정규화를 하므로 충돌이 생기지 않는다")
    with pytest.raises(PathPolicyError, match="덮어씁니다"):
        scan_files(root)


def test_broken_cp949_filename_fails_early_with_guidance(tmp_path: Path) -> None:
    """cp949 로 깨진 파일명은 매니페스트를 쓸 수 없다 — 스캔 시점에 설명하고 멈춘다."""
    root = tmp_path / "mojibake"
    root.mkdir()
    raw = "정밀조사.pdf".encode("cp949")
    try:
        # surrogateescape 로 디코드하면 같은 바이트열로 되돌아간다 — 비-UTF8 이름 재현
        (root / os.fsdecode(raw)).write_bytes(b"x")
    except (OSError, UnicodeError):
        pytest.skip("이 파일시스템은 비-UTF8 파일명을 허용하지 않는다")
    with pytest.raises(PathPolicyError, match="유효한 UTF-8"):
        scan_files(root)


def test_dotenv_double_quote_mangling_is_detected() -> None:
    """`.env` 에서 큰따옴표로 감싼 Windows 경로는 망가진다 — 그 사실을 알아채야 한다.

    실측: dotenv 는 큰따옴표 안의 백슬래시를 이스케이프로 해석한다.
      M3D_X="D:\\Projects\\new\\test"  ->  'D:\\Projects\\new\\test' 가 아니라
                                         'D:\\Projects' + 개행 + 'ew' + 탭 + 'est'
    """
    mangled = "D:\\Projects\new\test"  # 실제 dotenv 결과 (\n, \t 포함)
    assert mangled_by_dotenv_quoting(mangled)
    assert not mangled_by_dotenv_quoting("D:\\Projects\\new\\test")
    assert not mangled_by_dotenv_quoting("/mnt/d/Projects/정밀조사")

    msg = explain_unusable_source(mangled, Path(mangled), "M3D_SAMPLE_SOURCE_X")
    assert "큰따옴표" in msg
    assert "제어문자" in msg


def test_windows_path_on_posix_explains_itself() -> None:
    """이 클라우드 컨테이너의 실제 상황 — '디렉터리가 아닙니다' 로 끝내지 않는다."""
    raw = r"D:\Projects\Inspection\_정밀조사패키지_P4P5"
    msg = explain_unusable_source(raw, Path(raw), "M3D_SAMPLE_SOURCE_AB1_P4P5")
    assert "Windows 경로" in msg
    assert "/mnt/d/" in msg  # WSL 힌트
    assert "verify" in msg  # 매니페스트만으로 할 수 있는 일을 알려 준다


def test_windows_path_detection_and_wsl_hint() -> None:
    assert looks_like_windows_path(r"D:\Projects\a")
    assert looks_like_windows_path(r"\\server\share\a")
    assert not looks_like_windows_path("/home/user/a")
    assert wsl_translation(r"D:\Projects\_정밀조사") == "/mnt/d/Projects/_정밀조사"


# ── glob ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("**/SPEC_v2.md", "정답/SPEC_v2.md", True),
        ("**/SPEC_v2.md", "SPEC_v2.md", True),
        ("정답/**", "정답/a/b.json", True),
        ("정답/**", "도면/a.pdf", False),
        ("*.pdf", "도면/a.pdf", False),  # * 는 / 를 넘지 않는다
        ("**/*재실측*.json", "정답/접속1교_재실측.json", True),
        ("**/*.bak", "도면/a.bak", True),
    ],
)
def test_glob_semantics(pattern: str, path: str, expected: bool) -> None:
    assert (GlobSet([pattern]).match(path) is not None) is expected


# ── 역할 분류 ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("path", "role"),
    [
        ("도면/AB1-S-021.pdf", "drawing"),
        ("도면/AB1.dwg", "drawing"),
        ("사진/P4_01.jpg", "photo"),
        ("정답/SPEC_v2.md", "answer"),
        ("정답/접속1교_재실측.json", "answer"),
        ("메모.txt", "doc"),
        ("데이터.bin", "other"),
    ],
)
def test_classify_role(sample_set: SampleSet, path: str, role: str) -> None:
    assert sample_set.classify(path).role == role


def test_answer_is_never_guessed(sample_set: SampleSet) -> None:
    """규칙 §3 — 정답은 **선언**으로만 정해진다.

    'SPEC' 이 이름에 들어갔다는 이유로 정답 처리하면, 오분류 한 번에 진짜 도면이
    판독 입력에서 빠지거나 정답이 입력으로 샌다.
    """
    decision = sample_set.classify("도면/특수사양_spec_상세.pdf")
    assert decision.role == "drawing"
    assert decision.source == "extension"

    declared = sample_set.classify("정답/SPEC_v2.md")
    assert declared.role == "answer"
    assert declared.source == "declared"
    assert declared.matched_by == "**/SPEC_v2.md"


def test_suspect_answers_are_reported_not_classified(sample_set: SampleSet) -> None:
    """정답처럼 보이지만 선언 안 된 파일은 경고만 하고 자동 분류하지 않는다."""
    rels = ["도면/AB1.pdf", "기타/P5_재실측_초안.xlsx"]
    assert sample_set.suspect_answers(rels) == ["기타/P5_재실측_초안.xlsx"]
    assert sample_set.classify("기타/P5_재실측_초안.xlsx").role == "doc"


def test_manifest_rejects_undeclared_answer(sample_set: SampleSet) -> None:
    """계약이 런타임에 실제로 강제되는지 — 추측 정답은 매니페스트에 들어갈 수 없다."""
    with pytest.raises(ValidationError, match="선언 근거가 없습니다"):
        SampleManifest(
            manifest_version=2,
            set_id="test_set",
            description="d",
            generated_at="2026-08-27T00:00:00Z",
            entries=[
                {
                    "path": "정답/SPEC_v2.md",
                    "size": 1,
                    "sha256": "0" * 64,
                    "role": "answer",
                    "role_source": "extension",
                }
            ],
        )


def test_manifest_rejects_non_nfc_and_backslash_paths() -> None:
    base = {
        "manifest_version": 2,
        "set_id": "t",
        "description": "d",
        "generated_at": "2026-08-27T00:00:00Z",
    }
    entry = {"size": 1, "sha256": "0" * 64, "role": "doc"}
    with pytest.raises(ValidationError, match="백슬래시"):
        SampleManifest(**base, entries=[{**entry, "path": r"도면\a.pdf"}])
    with pytest.raises(ValidationError, match="NFC"):
        SampleManifest(**base, entries=[{**entry, "path": unicodedata.normalize("NFD", "가.pdf")}])


# ── 원본 읽기 전용 (CLAUDE.md §2) ─────────────────────────────────────────
def _snapshot(root: Path) -> dict[str, tuple[int, int, int, bytes]]:
    """원본 트리의 불변 스냅샷. atime 은 제외한다 — 읽으면 커널이 갱신하므로."""
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            p = Path(dirpath) / name
            st = p.stat()
            out[str(p.relative_to(root))] = (
                st.st_size,
                st.st_mtime_ns,
                stat.S_IMODE(st.st_mode),
                p.read_bytes(),
            )
    return out


def test_ingest_leaves_source_byte_identical(
    source_tree: Path, sample_set: SampleSet, work: Path
) -> None:
    """**원본은 읽기 전용이다** (CLAUDE.md §2). 이 테스트가 그 증명이다."""
    before = _snapshot(source_tree)
    ingest_sample_set(sample_set, source_tree, work)
    after = _snapshot(source_tree)
    assert after == before, "원본이 변경되었다 — 참조 원본은 읽기 전용이다 (CLAUDE.md §2)"


def test_ingest_refuses_destination_inside_source(source_tree: Path, tmp_path: Path) -> None:
    """작업 디렉터리를 원본 안에 두면 원본을 오염시킨다 — 시작 전에 거부한다."""
    st = SampleSet(
        definition=SampleSetDef(set_id="test_set", description="d"),
        dir=tmp_path / "samples/test_set",
    )
    with pytest.raises(IngestError, match="원본은 읽기 전용"):
        ingest_sample_set(st, source_tree, source_tree / "work")


def test_ingest_refuses_source_inside_destination(tmp_path: Path, sample_set: SampleSet) -> None:
    """반대 방향도 막는다 — 한쪽만 검사하면 원본이 오염되는 배치가 남는다."""
    work_dir = tmp_path / "work"
    inner = work_dir / "samples" / "test_set" / "원본"
    inner.mkdir(parents=True)
    (inner / "a.pdf").write_bytes(b"x")
    with pytest.raises(IngestError, match="안에 있습니다"):
        ingest_sample_set(sample_set, inner, work_dir)


def test_ingest_missing_source_reports_env_var(sample_set: SampleSet, tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="M3D_SAMPLE_SOURCE"):
        ingest_sample_set(sample_set, tmp_path / "없는경로", tmp_path / "work")


@pytest.mark.skipif(os.name == "nt", reason="POSIX 권한 모델 전용")
def test_readonly_source_can_still_be_ingested(
    source_tree: Path, sample_set: SampleSet, work: Path
) -> None:
    """원본이 읽기 전용으로 마운트되어 있어도 ingest 가 동작해야 한다."""
    for p in source_tree.rglob("*"):
        if p.is_file():
            p.chmod(stat.S_IRUSR)
    try:
        assert ingest_sample_set(sample_set, source_tree, work).copied
    finally:
        for p in source_tree.rglob("*"):
            if p.is_file():
                p.chmod(stat.S_IRUSR | stat.S_IWUSR)


# ── ingest 동작 ───────────────────────────────────────────────────────────
def test_ingest_separates_answers_from_inputs(
    source_tree: Path, sample_set: SampleSet, work: Path
) -> None:
    """정답은 판독 입력과 **물리적으로** 분리된다 — 자기 채점을 어렵게 만든다."""
    result = ingest_sample_set(sample_set, source_tree, work)
    inputs = sample_set.input_root(work)
    answers = sample_set.answers_root(work)

    assert (inputs / "도면" / "AB1-S-021_단면도.pdf").is_file()
    assert (answers / "정답" / "SPEC_v2.md").is_file()
    assert not (inputs / "정답" / "SPEC_v2.md").exists()

    # 입력 트리 어디에도 정답이 없다
    input_files = {p.name for p in inputs.rglob("*") if p.is_file()}
    assert "SPEC_v2.md" not in input_files
    assert "접속1교_재실측.json" not in input_files

    assert result.manifest is not None
    assert sorted(result.answers) == ["정답/SPEC_v2.md", "정답/접속1교_재실측.json"]
    assert [e.path for e in result.manifest.input_entries()] == sorted(
        ["도면/AB1-S-021_단면도.pdf", "도면/AB1-S-034.dxf", "사진/P4_거더_01.jpg", "메모.txt"]
    )


def test_ingest_skips_os_junk(source_tree: Path, sample_set: SampleSet, work: Path) -> None:
    result = ingest_sample_set(sample_set, source_tree, work)
    assert result.manifest is not None
    assert ".DS_Store" not in {e.path for e in result.manifest.entries}


def test_ingest_is_idempotent(source_tree: Path, sample_set: SampleSet, work: Path) -> None:
    first = ingest_sample_set(sample_set, source_tree, work)
    second = ingest_sample_set(sample_set, source_tree, work)
    assert second.copied == []
    assert sorted(second.skipped_same) == sorted(first.copied)
    assert second.manifest is not None
    assert first.manifest is not None
    # 내용이 같으므로 매니페스트를 다시 쓰지 않는다 (커밋 diff 를 더럽히지 않는다)
    write_manifest(sample_set, first.manifest)
    _, changed = write_manifest(sample_set, second.manifest)
    assert changed is False


def test_dry_run_writes_nothing(source_tree: Path, sample_set: SampleSet, work: Path) -> None:
    result = ingest_sample_set(sample_set, source_tree, work, dry_run=True)
    assert result.copied
    assert result.manifest is None
    assert not sample_set.work_root(work).exists()


def test_prune_removes_stale_copies(source_tree: Path, sample_set: SampleSet, work: Path) -> None:
    """원본에서 지워진 도면이 작업 디렉터리에 살아남아 세트 구성을 거짓말하게 두지 않는다."""
    ingest_sample_set(sample_set, source_tree, work)
    (source_tree / "도면" / "AB1-S-034.dxf").unlink()

    found = ingest_sample_set(sample_set, source_tree, work)
    assert found.stale == ["source/도면/AB1-S-034.dxf"]
    assert (sample_set.input_root(work) / "도면" / "AB1-S-034.dxf").is_file()

    pruned = ingest_sample_set(sample_set, source_tree, work, prune=True)
    assert pruned.pruned == ["source/도면/AB1-S-034.dxf"]
    assert not (sample_set.input_root(work) / "도면" / "AB1-S-034.dxf").exists()


def test_no_partial_files_left_behind(source_tree: Path, sample_set: SampleSet, work: Path) -> None:
    """원자적 복사 — 임시 파일이 남지 않는다."""
    ingest_sample_set(sample_set, source_tree, work)
    leftovers = [p.name for p in sample_set.work_root(work).rglob(".m3d-*")]
    assert leftovers == []


# ── verify ────────────────────────────────────────────────────────────────
def test_verify_ok_after_ingest(source_tree: Path, sample_set: SampleSet, work: Path) -> None:
    manifest = ingest_sample_set(sample_set, source_tree, work).manifest
    assert manifest is not None
    report = verify_manifest(sample_set, manifest, work)
    assert report.state is VerifyState.OK
    assert report.checked == len(manifest.entries)


def test_verify_absent_is_distinct_from_mismatch(
    source_tree: Path, sample_set: SampleSet, work: Path, tmp_path: Path
) -> None:
    """원본 없는 환경(이 클라우드 컨테이너)은 ABSENT 다 — MISMATCH 로 뭉개지 않는다."""
    manifest = build_manifest(sample_set, source_tree)
    report = verify_manifest(sample_set, manifest, tmp_path / "빈작업디렉터리")
    assert report.state is VerifyState.ABSENT
    assert report.ok is False
    assert report.missing == []  # 전부 '누락'으로 쏟아내지 않는다
    assert report.expected == len(manifest.entries)
    assert "ABSENT" in report.summary()
    assert "ingest" in report.summary()


def test_verify_detects_missing_and_tampering(
    source_tree: Path, sample_set: SampleSet, work: Path
) -> None:
    manifest = ingest_sample_set(sample_set, source_tree, work).manifest
    assert manifest is not None
    inputs = sample_set.input_root(work)

    (inputs / "메모.txt").unlink()
    target = inputs / "도면" / "AB1-S-034.dxf"
    target.write_text(target.read_text(encoding="utf-8") + "변조", encoding="utf-8")

    report = verify_manifest(sample_set, manifest, work)
    assert report.state is VerifyState.MISMATCH
    assert "메모.txt" in report.missing
    assert "도면/AB1-S-034.dxf" in report.size_mismatch


def test_verify_detects_same_size_tampering(
    source_tree: Path, sample_set: SampleSet, work: Path
) -> None:
    """크기가 같아도 해시로 잡아낸다."""
    manifest = ingest_sample_set(sample_set, source_tree, work).manifest
    assert manifest is not None
    target = sample_set.input_root(work) / "도면" / "AB1-S-034.dxf"
    data = target.read_bytes()
    target.write_bytes(b"X" + data[1:])
    assert "도면/AB1-S-034.dxf" in verify_manifest(sample_set, manifest, work).hash_mismatch


def test_verify_detects_extra_files(source_tree: Path, sample_set: SampleSet, work: Path) -> None:
    manifest = ingest_sample_set(sample_set, source_tree, work).manifest
    assert manifest is not None
    (sample_set.input_root(work) / "몰래_추가.pdf").write_bytes(b"x")
    assert "source/몰래_추가.pdf" in verify_manifest(sample_set, manifest, work).extra


def test_answers_seal_detects_edited_ground_truth(
    source_tree: Path, sample_set: SampleSet, work: Path
) -> None:
    """정답을 고쳐 M3 대조를 통과시키는 것은 검증이 아니다 (규칙 §6·§8)."""
    manifest = ingest_sample_set(sample_set, source_tree, work).manifest
    assert manifest is not None
    assert manifest.answers_seal is not None
    assert verify_manifest(sample_set, manifest, work).seal_broken is False

    spec = sample_set.answers_root(work) / "정답" / "SPEC_v2.md"
    spec.write_text("# 사양 정본\n거더 높이 = 내 모델과 같은 값\n", encoding="utf-8")

    report = verify_manifest(sample_set, manifest, work)
    assert report.seal_broken is True
    assert report.state is VerifyState.MISMATCH


def test_seal_is_stable_and_recomputable(sample_set: SampleSet, source_tree: Path) -> None:
    m1 = build_manifest(sample_set, source_tree)
    m2 = build_manifest(sample_set, source_tree)
    assert m1.answers_seal == m2.answers_seal == m1.compute_answers_seal()


def test_manifest_roundtrips_through_json(
    source_tree: Path, sample_set: SampleSet, work: Path
) -> None:
    """커밋되는 산출물이므로 JSON 왕복이 손실 없이 되어야 한다 (한글 포함)."""
    manifest = ingest_sample_set(sample_set, source_tree, work).manifest
    assert manifest is not None
    path, changed = write_manifest(sample_set, manifest)
    assert changed is True
    loaded = SampleManifest.model_validate_json(path.read_text(encoding="utf-8"))
    assert loaded == manifest
    assert "도면/AB1-S-021_단면도.pdf" in {e.path for e in loaded.entries}


def test_written_manifest_matches_committed_schema(
    source_tree: Path, sample_set: SampleSet, work: Path
) -> None:
    """pydantic 과 JSON Schema 정본이 같은 판정을 내는지 (계약 이중화 방지)."""
    from jsonschema import Draft202012Validator, FormatChecker

    from model3d_worker.contracts.schemas import load_schema

    manifest = ingest_sample_set(sample_set, source_tree, work).manifest
    assert manifest is not None
    doc = json.loads(manifest.model_dump_json())
    validator = Draft202012Validator(
        load_schema("sample_manifest.schema.json"), format_checker=FormatChecker()
    )
    assert list(validator.iter_errors(doc)) == []


def test_empty_set_still_produces_valid_manifest(sample_set: SampleSet, tmp_path: Path) -> None:
    empty = tmp_path / "비어있음"
    empty.mkdir()
    manifest = assemble_manifest(sample_set, [])
    assert manifest.entries == []
    assert manifest.answers_seal is None
    assert verify_manifest(sample_set, manifest, empty).state is VerifyState.ABSENT


# ── 레지스트리 / 설정 ─────────────────────────────────────────────────────
def test_env_var_name_mapping() -> None:
    assert sample_source_env_name("ab1_p4p5") == "M3D_SAMPLE_SOURCE_AB1_P4P5"
    assert sample_source_env_name("ab1-p4p5") == "M3D_SAMPLE_SOURCE_AB1_P4P5"


def test_repo_sample_set_is_registered() -> None:
    """리포에 커밋된 세트 정의를 실제로 읽을 수 있어야 한다."""
    ids = {s.set_id for s in list_sample_sets()}
    assert "ab1_p4p5" in ids, f"등록된 세트: {ids}"
    st = load_sample_set("ab1_p4p5")
    assert "P4" in st.description
    assert st.source_hint  # 원본 위치 힌트가 있어야 사용자가 .env 를 채울 수 있다
    assert st.definition.answers, "정답 글롭이 선언되어 있어야 M3 대조 기준이 분리된다"


def test_unknown_set_lists_known_ones() -> None:
    with pytest.raises(KeyError, match="ab1_p4p5"):
        load_sample_set("없는세트")


def test_manifest_only_environment_can_read_set_composition() -> None:
    """이 클라우드 컨테이너처럼 원본이 없어도 세트 구성을 알 수 있어야 한다.

    (매니페스트가 아직 커밋되지 않았다면 그 사실을 명확히 말하는 것으로 충분하다.)
    """
    st = load_sample_set("ab1_p4p5")
    if not st.has_manifest():
        pytest.skip("매니페스트 미커밋 — 원본이 있는 머신에서 ingest 후 커밋된다")
    manifest = st.load_manifest()
    assert manifest.set_id == "ab1_p4p5"
    assert all(e.role != "answer" or e.role_source == "declared" for e in manifest.entries)
