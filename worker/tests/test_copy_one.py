"""_copy_one 단위테스트 — 복사·스킵·손상 복구·원본 보호 가드 (설계서 §9 amendment).

_copy_one 은 되돌릴 수 없는 참조 원본 옆에서 도는 코드라 회귀 방어가 반드시 필요하다.
여기 모든 파일은 tmp_path 합성 파일이며 실데이터(data/samples, SAMPLE_SOURCE_DIR)는
전혀 건드리지 않는다.
"""

import hashlib
import shutil

import pytest

from m3d.samples.collect import CollectError, PlannedFile, _copy_one


def _make_source(repo_root, name: str, content: bytes) -> PlannedFile:
    """repo_root 아래 원본 파일을 만들고 대응하는 PlannedFile 을 돌려준다."""
    source = repo_root / "source" / name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(content)
    return PlannedFile(
        source=source,
        source_rel=f"_dxf/{name}",
        rel_path=f"dest/{name}",
        kind="dxf",
        role="source",
        ord="C01",
        drawing_no="C0050304-030",
        page_no=None,
    )


def test_first_copy_creates_destination_and_entry(tmp_path):
    """대상이 없으면 복사하고, copied=True 와 올바른 엔트리를 돌려준다."""
    content = b"first-copy-content"
    item = _make_source(tmp_path, "a.dxf", content)

    entry, copied = _copy_one(item, tmp_path)

    dest = tmp_path / item.rel_path
    assert copied is True
    assert dest.is_file()
    assert dest.read_bytes() == content
    assert entry.rel_path == item.rel_path
    assert entry.source_rel == item.source_rel
    assert entry.kind == item.kind
    assert entry.role == item.role
    assert entry.bytes == len(content)
    assert entry.sha256 == hashlib.sha256(content).hexdigest()


def test_identical_destination_is_skipped_and_not_rewritten(tmp_path):
    """대상이 이미 원본과 바이트 단위로 같으면 다시 쓰지 않는다 (멱등 재실행)."""
    content = b"already-same-content"
    item = _make_source(tmp_path, "b.dxf", content)

    dest = tmp_path / item.rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    mtime_before = dest.stat().st_mtime_ns

    entry, copied = _copy_one(item, tmp_path)

    assert copied is False
    assert dest.stat().st_mtime_ns == mtime_before, "건너뛰었다면 대상을 다시 쓰면 안 된다"
    assert entry.sha256 == hashlib.sha256(content).hexdigest()


def test_same_size_different_content_is_repaired(tmp_path):
    """크기는 같지만 내용이 다른 손상된 대상은 재복사해야 한다 — 크기만 보면 놓치는 사례.

    이 테스트가 실제로 해시 비교에 의존하는지는(크기 비교만으로 축소하면 실패하는지)
    작업 보고서의 mutation check 로 별도 확인했다.
    """
    source_content = b"AAAA"
    corrupt_content = b"BBBB"  # source_content 와 길이는 같지만 바이트가 다르다
    assert len(source_content) == len(corrupt_content)
    item = _make_source(tmp_path, "c.dxf", source_content)

    dest = tmp_path / item.rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(corrupt_content)

    entry, copied = _copy_one(item, tmp_path)

    assert copied is True, "크기만 같고 내용이 다르면 반드시 재복사해야 한다"
    assert dest.read_bytes() == source_content
    assert entry.sha256 == hashlib.sha256(source_content).hexdigest()


def test_source_mutated_during_copy_raises(tmp_path, monkeypatch):
    """복사 도중 원본이 바뀌면 즉시 CollectError — 참조 원본 보호 가드.

    shutil.copy2 를 가로채 '정상 복사 → 원본을 다른 크기로 재작성' 을 흉내내어
    _copy_one 의 사후 검사(before/after stat 비교)가 실제로 잡아내는지 확인한다.
    """
    content = b"original-content"
    item = _make_source(tmp_path, "d.dxf", content)
    real_copy2 = shutil.copy2

    def copy2_then_mutate_source(src, dst, *args, **kwargs):
        result = real_copy2(src, dst, *args, **kwargs)
        item.source.write_bytes(content + b"-mutated-after-copy")
        return result

    monkeypatch.setattr(shutil, "copy2", copy2_then_mutate_source)

    with pytest.raises(CollectError, match="원본이 변경되었습니다"):
        _copy_one(item, tmp_path)


def test_missing_source_raises(tmp_path):
    """원본이 아예 없으면 CollectError — 없는 파일을 조용히 건너뛰지 않는다."""
    item = PlannedFile(
        source=tmp_path / "source" / "missing.dxf",
        source_rel="_dxf/missing.dxf",
        rel_path="dest/missing.dxf",
        kind="dxf",
        role="source",
        ord="C99",
        drawing_no="C9999999-999",
        page_no=None,
    )

    with pytest.raises(CollectError, match="원본이 없습니다"):
        _copy_one(item, tmp_path)
