"""catalog 리포트 빌더 — 순수 부분만. DB 왕복은 §9 실행으로 검증."""

from m3d.catalog.reconcile import Verdict
from m3d.catalog.run import SheetVerdict, build_report


def _sv(ord_, drwno, status, notes=(), changed=True):
    return SheetVerdict(
        ord=ord_, drawing_no_filename=drwno,
        verdict=Verdict(status, drwno if status != "unreadable" else None,
                        "제목" if status != "unreadable" else None,
                        None, tuple(notes)),
        changed=changed,
    )


def test_counts_by_status():
    results = [
        _sv("A01", "C1", "match"),
        _sv("A02", "C2", "match"),
        _sv("A03", "C3", "unreadable", notes=("표제란 부재",)),
        _sv("B01", "C4", "mismatch", notes=("도면번호 불일치: ...",)),
    ]
    report = build_report(results)
    assert report["counts"] == {"match": 2, "mismatch": 1, "unreadable": 1}
    assert report["total"] == 4


def test_non_match_rows_listed_with_notes():
    results = [_sv("A03", "C3", "unreadable", notes=("표제란 부재",))]
    report = build_report(results)
    assert len(report["attention"]) == 1
    row = report["attention"][0]
    assert row["ord"] == "A03" and row["status"] == "unreadable"
    assert "표제란 부재" in row["notes"][0]


def test_notes_on_match_rows_are_kept():
    """match 라도 제목 노트는 리포트에 남는다 (참고 정보 유실 금지)."""
    results = [_sv("B02", "C9", "match", notes=("제목 불일치(참고): ...",))]
    report = build_report(results)
    assert len(report["attention"]) == 1


def test_changed_count():
    results = [_sv("A01", "C1", "match", changed=False),
               _sv("A02", "C2", "match", changed=True)]
    assert build_report(results)["changed"] == 1


def test_failures_are_reported_without_polluting_counts():
    """DXF 읽기 실패 시트는 failures 로 남고 total/counts 는 성공 처리분만 반영한다
    (지식베이스 원칙 — 실패해도 나머지는 계속 처리하고 마지막에 보고, 전체 중단 금지)."""
    results = [_sv("A01", "C1", "match")]

    report = build_report(results)
    assert report["failures"] == []  # 실패 없으면 빈 목록(기본값)

    report2 = build_report(results, failures=[("A05", "DXFStructureError: 손상된 파일")])
    assert report2["total"] == 1  # 실패 건은 total/counts 에 포함하지 않음
    assert report2["failures"] == [{"ord": "A05", "error": "DXFStructureError: 손상된 파일"}]
