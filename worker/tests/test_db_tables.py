"""db.TABLES — db check 가 세는 표 목록에 M4·M5 표가 들어간다."""

from m3d.db import TABLES


def test_tables_include_m4_m5_tables_in_order():
    assert TABLES[-5:] == ("builds", "build_sections", "approvals", "jobs", "job_events")
    assert len(TABLES) == len(set(TABLES)) == 12
