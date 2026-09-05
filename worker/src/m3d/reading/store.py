"""판독 결과 DB 반영 (설계서 §5) — 계열 단위 교체로 멱등을 만든다."""

from __future__ import annotations

import uuid

import psycopg

from m3d.config import Config
from m3d.models import AmbiguityRow, ReadingRow


def build_rows(region: str, readings, ambiguities, round_no: int
               ) -> tuple[list[ReadingRow], list[AmbiguityRow]]:
    """LLM 출력(Merged*/FinalReading) → DB 행 모델. 근거 시트는 행마다 자기 ord 다."""
    rows_r = [
        ReadingRow(region=region, item=r.item, value_raw=r.value_raw, unit=r.unit,
                   basis_ord=r.ord, basis_page_no=r.page_no, basis_mm_bbox=r.mm_bbox,
                   crosscheck={"expr": r.crosscheck} if r.crosscheck else None,
                   status=r.status, round=round_no)
        for r in readings
    ]
    rows_a = [
        AmbiguityRow(item=a.item, basis_ord=a.ord, basis_page_no=a.page_no,
                     mm_bbox=a.mm_bbox, options=a.options, model_impact=a.model_impact)
        for a in ambiguities
    ]
    return rows_r, rows_a


def resolve_ids(conn, project_id):
    with conn.cursor() as cur:
        cur.execute("select ord, id from sheets where project_id = %s", (project_id,))
        sheet_ids = dict(cur.fetchall())
        cur.execute(
            "select s.ord, sp.page_no, sp.id from sheet_pages sp "
            "join sheets s on s.id = sp.sheet_id where s.project_id = %s",
            (project_id,))
        page_ids = {(o, n): i for o, n, i in cur.fetchall()}
    return sheet_ids, page_ids


def _project_id(cur, dataset: str):
    cur.execute("select id from projects where slug = %s", (dataset,))
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"프로젝트 '{dataset}' 없음 — seed 먼저")
    return row[0]


def _natural_key(sheet_id, page_id, item: str, mm_bbox) -> tuple:
    """ambiguity 자연키 — 같은 시트·페이지의 같은 항목·같은 영역이면 같은 질문이다.

    jsonb 는 numeric 기반이라 후행 0 을 보존하며(공식 문서) 이 저장 경로에서는
    [100.0, …] 이 그대로 돌아온다. 다만 다른 경로(수동 SQL 시드·타 도구)가 정수
    표기로 써 넣거나 자릿수가 달라질 수 있으므로, 좌표는 표기에 무관하게 float
    반올림(round(…, 2))으로 비교한다 — 문자열 비교는 표기 차이에 취약하다.
    """
    return (str(sheet_id), str(page_id), item,
            tuple(round(float(v), 2) for v in mm_bbox))


def has_review_rows(cfg: Config, dataset: str, region: str) -> bool:
    """해당 계열에 검토(round 3) 결과가 이미 있는가 — read 가 덮어쓰지 않게."""
    with psycopg.connect(cfg.require_db_url()) as conn, conn.cursor() as cur:
        project_id = _project_id(cur, dataset)
        cur.execute("select 1 from readings where project_id = %s and region = %s "
                    "and round = 3 limit 1", (project_id, region))
        return cur.fetchone() is not None


def replace_region(cfg: Config, dataset: str, region: str,
                   rows_r: list[ReadingRow], rows_a: list[AmbiguityRow]) -> dict[str, int]:
    """해당 계열의 기존 행을 지우고 새로 넣는다 — 재실행이 누적되지 않게.

    ambiguity 는 자연키가 같으면 옛 id·crop_rel_path 를 이어받는다(크롭 링크 보존).
    시트·페이지 id 를 해석하지 못한 행은 NULL 로 밀어넣지 않고 failed 로 센다.
    """
    kept = failed = 0
    with psycopg.connect(cfg.require_db_url()) as conn:
        with conn.cursor() as cur:
            project_id = _project_id(cur, dataset)
        sheet_ids, page_ids = resolve_ids(conn, project_id)
        # 삭제 범위 = 이 계열의 시트 전체. 불변식: 계열 키는 ord 첫 글자 한 글자이므로
        # `ord[0] == region` 이 곧 계열 소속이다(접두 일치는 'C1' 같은 값에 오작동한다 —
        # cli._validated_region·sheet.list_pages 와 같은 규칙을 쓴다).
        region_sheet_ids = [sid for o, sid in sheet_ids.items() if o[0] == region]

        with conn.cursor() as cur:
            # 삭제 전에 자연키 → (id, crop_rel_path) 맵을 뜬다
            cur.execute(
                "select id, basis_sheet_id, sheet_page_id, item, mm_bbox, crop_rel_path "
                "from ambiguities where project_id = %s and basis_sheet_id = any(%s)",
                (project_id, region_sheet_ids))
            keep = {_natural_key(r[1], r[2], r[3], r[4]): (r[0], r[5])
                    for r in cur.fetchall()}

            cur.execute("delete from readings where project_id = %s and region = %s",
                        (project_id, region))
            # rows_a 가 비어도 무조건 실행한다 — 옛 행 잔존이 멱등을 깬다
            cur.execute(
                "delete from ambiguities where project_id = %s and basis_sheet_id = any(%s)",
                (project_id, region_sheet_ids))

            n_r = 0
            for r in rows_r:
                sid = sheet_ids.get(r.basis_ord)
                pid = page_ids.get((r.basis_ord, r.basis_page_no))
                if sid is None or pid is None:
                    failed += 1
                    continue
                cur.execute(
                    "insert into readings (project_id, region, item, value_raw, unit, "
                    "basis_sheet_id, basis_page_id, basis_mm_bbox, crosscheck, status, round) "
                    "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (project_id, r.region, r.item, r.value_raw, r.unit, sid, pid,
                     psycopg.types.json.Json(r.basis_mm_bbox),
                     psycopg.types.json.Json(r.crosscheck) if r.crosscheck else None,
                     r.status, r.round))
                n_r += 1

            n_a = 0
            for a in rows_a:
                sid = sheet_ids.get(a.basis_ord)
                pid = page_ids.get((a.basis_ord, a.basis_page_no))
                if sid is None or pid is None:
                    failed += 1
                    continue
                old = keep.get(_natural_key(sid, pid, a.item, a.mm_bbox))
                if old is not None:
                    kept += 1
                amb_id = old[0] if old else str(uuid.uuid4())
                crop_rel = old[1] if old else None
                cur.execute(
                    "insert into ambiguities (id, project_id, item, basis_sheet_id, "
                    "sheet_page_id, mm_bbox, options, model_impact, crop_rel_path, status) "
                    "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (amb_id, project_id, a.item, sid, pid,
                     psycopg.types.json.Json(a.mm_bbox),
                     psycopg.types.json.Json([o.model_dump() for o in a.options]),
                     a.model_impact, crop_rel, a.status))
                n_a += 1
        conn.commit()

    return {"readings": n_r, "ambiguities": n_a, "kept": kept, "failed": failed}
