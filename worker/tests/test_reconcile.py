"""대조 판정 — 지식베이스 §3 '기계 대조' 의 구현 (설계서 §6)."""

from m3d.catalog.reconcile import Verdict, normalize_title, reconcile
from m3d.catalog.titleblock import TitleBlock


def _tb(drwno, title="제 목", subtitle="(부 제)", scale="H=1:100"):
    return TitleBlock(drwno, title, subtitle, scale)


def test_normalize_strips_all_whitespace_including_fullwidth():
    assert normalize_title("슬 래 브 일 반 도 (4)") == "슬래브일반도(4)"
    assert normalize_title("(접　속 1 교)") == "(접속1교)"


def test_no_blocks_is_unreadable():
    v = reconcile([], "C0050302-001", "접속1교종평면도(8차준공)(7차변경)")
    assert v.status == "unreadable"
    assert v.drawing_no is None and v.title is None and v.scale is None
    assert any("표제란 부재" in n for n in v.notes)


def test_single_match():
    v = reconcile([_tb("C0050304-030", "강상형일반도(5)", "(접속1교)")],
                  "C0050304-030", "강상형일반도(5)(접속1교)")
    assert v.status == "match"
    assert v.drawing_no == "C0050304-030"
    assert v.title == "강상형일반도(5) (접속1교)"   # 원문 결합 (정규화본 아님)
    assert v.notes == ()                            # 제목 포함 관계 성립 → 노트 없음


def test_mismatch_detected():
    """편철 오류 — 파일명과 내용의 도면번호가 다르다."""
    v = reconcile([_tb("C0050405-010")], "C0050305-040", "P10Tiedown상세도")
    assert v.status == "mismatch"
    assert v.drawing_no == "C0050405-010"           # 내용 유래 값을 저장
    assert any("C0050405-010" in n for n in v.notes)


def test_multipage_all_must_match():
    """다페이지 — 하나라도 다르면 mismatch (설계서 §6)."""
    v = reconcile([_tb("C0050301-001"), _tb("C0050301-999")],
                  "C0050301-001", "교량제원및특기사항(1)")
    assert v.status == "mismatch"


def test_multipage_consistent_match():
    v = reconcile([_tb("C0050301-001"), _tb("C0050301-001")],
                  "C0050301-001", "교량제원및특기사항(1)(접속1교)_(6차변경)")
    assert v.status == "match"


def test_title_not_contained_becomes_note_only():
    """제목 불일치는 판정에 영향 없음 — 노트만 (D4)."""
    v = reconcile([_tb("C0050304-030", "전혀다른제목", "")],
                  "C0050304-030", "강상형일반도(5)(접속1교)")
    assert v.status == "match"
    assert any("제목" in n for n in v.notes)


def test_filename_extra_suffix_is_ok():
    """파일명의 차수 접미 '(7차변경)' 은 정상 — 포함 관계로 흡수."""
    v = reconcile([_tb("C0050304-005", "슬 래 브 일 반 도 (5)", "(접 속 1 교)")],
                  "C0050304-005", "슬래브일반도(5)(접속1교)_(7차변경)")
    assert v.status == "match"
    assert not any("제목" in n for n in v.notes)


def test_empty_scale_stored_as_none():
    v = reconcile([_tb("X", scale="")], "X", "제목")
    assert v.scale is None
