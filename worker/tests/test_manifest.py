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
