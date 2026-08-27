"""매니페스트 — 460MB 를 커밋하지 않고도 무결성을 증명하는 유일한 수단."""

import hashlib
import json

import pytest

from m3d.samples.manifest import (
    Manifest,
    ManifestEntry,
    SCHEMA_VERSION,
    load_manifest,
    sha256_file,
    verify_manifest,
    write_manifest,
)

DATASET = "ab1-p4p5"


def _make_file(repo_root, rel_path, content: bytes) -> ManifestEntry:
    """repo_root 아래에 파일을 만들고 그에 대응하는 엔트리를 돌려준다."""
    target = repo_root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return ManifestEntry(
        rel_path=rel_path,
        source_rel=f"_dxf/{target.name}",
        kind="dxf",
        role="source",
        bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        ord="C01",
        drawing_no="C0050304-030",
    )


@pytest.fixture
def repo(tmp_path):
    return tmp_path


@pytest.fixture
def manifest(repo):
    entries = (
        _make_file(repo, f"data/samples/{DATASET}/dxf/a.dxf", b"alpha"),
        _make_file(repo, f"data/samples/{DATASET}/dxf/b.dxf", b"bravo"),
    )
    return Manifest(dataset=DATASET, entries=entries)


def test_sha256_file_matches_hashlib(repo):
    path = repo / "x.bin"
    path.write_bytes(b"hello world")
    assert sha256_file(path) == hashlib.sha256(b"hello world").hexdigest()


def test_total_bytes(manifest):
    assert manifest.total_bytes == len(b"alpha") + len(b"bravo")


def test_write_load_roundtrip(repo, manifest):
    path = repo / "data/manifests/ab1-p4p5.json"
    write_manifest(manifest, path)
    assert load_manifest(path) == manifest


def test_written_json_is_utf8_and_has_counts(repo, manifest):
    path = repo / "data/manifests/ab1-p4p5.json"
    write_manifest(manifest, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == SCHEMA_VERSION
    assert payload["dataset"] == DATASET
    assert payload["file_count"] == 2
    assert payload["total_bytes"] == manifest.total_bytes


def test_verify_ok(repo, manifest):
    report = verify_manifest(manifest, repo)
    assert report.ok
    assert report.checked == 2


def test_verify_detects_missing(repo, manifest):
    (repo / manifest.entries[0].rel_path).unlink()
    report = verify_manifest(manifest, repo)
    assert not report.ok
    assert report.missing == (manifest.entries[0].rel_path,)


def test_verify_detects_content_change(repo, manifest):
    (repo / manifest.entries[1].rel_path).write_bytes(b"CHANGED")
    report = verify_manifest(manifest, repo)
    assert not report.ok
    assert report.mismatched == (manifest.entries[1].rel_path,)


def test_verify_detects_same_size_content_change(repo, manifest):
    """크기가 같아도 내용이 바뀌면 잡아야 한다 — 크기만 보면 놓친다."""
    (repo / manifest.entries[0].rel_path).write_bytes(b"ALPHA")
    report = verify_manifest(manifest, repo)
    assert report.mismatched == (manifest.entries[0].rel_path,)


def test_verify_detects_extra_file(repo, manifest):
    stray = repo / f"data/samples/{DATASET}/dxf/stray.dxf"
    stray.write_bytes(b"unlisted")
    report = verify_manifest(manifest, repo)
    assert not report.ok
    assert report.extra == (f"data/samples/{DATASET}/dxf/stray.dxf",)


def test_load_rejects_wrong_schema(repo, manifest):
    path = repo / "m.json"
    write_manifest(manifest, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema"] = 99
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        load_manifest(path)


def test_load_rejects_count_mismatch(repo, manifest):
    path = repo / "m.json"
    write_manifest(manifest, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["file_count"] = 99
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="file_count"):
        load_manifest(path)


def test_korean_filenames_roundtrip_and_verify(repo):
    """한글 파일명이 utf-8로 왕복 가능한지 + 검증 통과하는지 회귀 방어.

    실제 데이터는 'C01_C0050304-030_강상형일반도(5)(접속1교).png' 같은 파일명을 쓴다.
    ensure_ascii=True 실수나 인코딩 슬립이 생기면 이 테스트가 잡는다.
    """
    korean_rel_path = "data/samples/ab1-p4p5/png/C01_C0050304-030_강상형일반도(5)(접속1교).png"
    korean_source_rel = "_png/C01_C0050304-030_강상형일반도(5)(접속1교).png"
    korean_drawing_no = "C0050304-030-강상형일반도"

    target = repo / korean_rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    content = b"korean_test_image_data"
    target.write_bytes(content)

    entry = ManifestEntry(
        rel_path=korean_rel_path,
        source_rel=korean_source_rel,
        kind="png",
        role="source",
        bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        ord="C01",
        drawing_no=korean_drawing_no,
    )
    manifest = Manifest(dataset=DATASET, entries=(entry,))

    # write → load 왕복 검증
    path = repo / "data/manifests/korean-test.json"
    write_manifest(manifest, path)

    # JSON 파일이 한글 문자를 직접 포함해야 한다 (escape 되면 안 됨)
    json_text = path.read_text(encoding="utf-8")
    assert "강상형일반도" in json_text, "한글이 \\uXXXX 로 escape 되면 이 단언에서 실패한다"
    assert "C0050304-030-강상형일반도" in json_text, "drawing_no 한글도 직접 포함되어야 한다"

    loaded = load_manifest(path)
    assert loaded == manifest, "한글 파일명이 손실되면 이 단언에서 실패한다"

    # verify_manifest 도 ok 를 보고해야 한다
    report = verify_manifest(loaded, repo)
    assert report.ok, f"파일은 있는데도 verify 가 실패: {report}"
