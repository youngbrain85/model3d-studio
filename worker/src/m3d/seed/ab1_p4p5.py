"""접속1교 P4~P5 샘플 세트 시딩 (설계서 §6-3·§6-4).

M0 는 `*_from_filename` 만 채운다. `*_from_content` 는 M1 [3] 이 시트 내부 텍스트에서
독립적으로 판독해 채우고 대조한다 — 편철 오류 검출의 회귀 테스트가 여기서 성립한다.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from m3d.config import Config
from m3d.models import AssetRow, ProjectRow, SheetPageRow, SheetRow
from m3d.samples.collect import DATASET, manifest_path
from m3d.samples.manifest import Manifest, load_manifest
from m3d.samples.source_manifest import SourceSheet, parse_source_manifest

# 설계서 §6-4 — models_3d/ab1/SPEC_v2.md §0 에서 가져왔다
COORD_SYSTEM = {
    "up": "Y",
    "unit": "m",
    "axes": {
        "x": "교축직각 (상자 중심 x=0, 보도측 = x 음/서측)",
        "y": "EL − 4.871",
        "z": "STA − 4190",
    },
    "datums": {
        "P4_bearing_z": -525.0,
        "P4_sta": "3+665.000",
        "P5_bearing_z": -455.0,
        "P5_sta": "3+735.000",
    },
    "source": "models_3d/ab1/SPEC_v2.md §0",
}

COORD_ASSUMPTIONS = [
    "패키지 README 의 P4 STA '3+665.45' 는 오기 — SPEC_v2 §0 의 3+665.000 이 정본"
    " (상세도 M.L STA 역산)"
]

PROJECT_NAME = "접속1교 P4~P5"
PROJECT_STRUCTURE = "원산안면대교(솔빛대교) 접속1교"


class SeedError(RuntimeError):
    """이미 시딩된 프로젝트를 덮어쓰려 할 때."""


@dataclass(frozen=True)
class SeedPayload:
    project: ProjectRow
    sheets: tuple[SheetRow, ...]
    pages: tuple[SheetPageRow, ...]
    assets: tuple[AssetRow, ...]


def build_rows(manifest: Manifest, sheets: list[SourceSheet]) -> SeedPayload:
    """매니페스트 + 원본 카탈로그 → 삽입할 행 전부. 파일시스템·DB 를 건드리지 않는다."""
    project = ProjectRow(
        slug=DATASET,
        name=PROJECT_NAME,
        structure=PROJECT_STRUCTURE,
        coord_system=COORD_SYSTEM,
        coord_assumptions=list(COORD_ASSUMPTIONS),
    )

    sheet_rows = tuple(
        SheetRow(
            ord=sheet.ord,
            drawing_no_from_filename=sheet.drawing_no,
            title_from_filename=sheet.title,
            grade=sheet.grade,
            page_count=sheet.page_count,
        )
        for sheet in sheets
    )

    page_rows = tuple(
        SheetPageRow(ord=sheet.ord, page_no=page_no)
        for sheet in sheets
        for page_no in range(1, sheet.page_count + 1)
    )

    asset_rows = tuple(
        AssetRow(
            kind=entry.kind,
            role=entry.role,
            rel_path=entry.rel_path,
            bytes=entry.bytes,
            sha256=entry.sha256,
            ord=entry.ord,
            page_no=entry.page_no,
        )
        for entry in manifest.entries
    )

    return SeedPayload(
        project=project, sheets=sheet_rows, pages=page_rows, assets=asset_rows
    )


def seed(cfg: Config, *, reseed: bool = False) -> dict[str, int]:
    manifest = load_manifest(manifest_path(cfg))
    sheets = parse_source_manifest(cfg.source_manifest_path)
    payload = build_rows(manifest, sheets)

    with psycopg.connect(cfg.require_db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute("select id from projects where slug = %s", (payload.project.slug,))
            existing = cur.fetchone()
            if existing is not None:
                if not reseed:
                    raise SeedError(
                        f"프로젝트 '{payload.project.slug}' 가 이미 있습니다. "
                        "덮어쓰려면 --reseed 를 주세요 (자식 행이 모두 삭제됩니다)."
                    )
                cur.execute("delete from projects where slug = %s", (payload.project.slug,))

            cur.execute(
                "insert into projects (slug, name, structure, coord_system, coord_assumptions) "
                "values (%s, %s, %s, %s, %s) returning id",
                (
                    payload.project.slug,
                    payload.project.name,
                    payload.project.structure,
                    psycopg.types.json.Json(payload.project.coord_system),
                    payload.project.coord_assumptions,
                ),
            )
            project_id = cur.fetchone()[0]

            sheet_ids: dict[str, str] = {}
            for sheet in payload.sheets:
                cur.execute(
                    "insert into sheets (project_id, ord, drawing_no_from_filename, "
                    "title_from_filename, grade, catalog_status, page_count) "
                    "values (%s, %s, %s, %s, %s, %s, %s) returning id",
                    (
                        project_id,
                        sheet.ord,
                        sheet.drawing_no_from_filename,
                        sheet.title_from_filename,
                        sheet.grade,
                        sheet.catalog_status,
                        sheet.page_count,
                    ),
                )
                sheet_ids[sheet.ord] = cur.fetchone()[0]

            page_ids: dict[tuple[str, int], str] = {}
            for page in payload.pages:
                cur.execute(
                    "insert into sheet_pages (sheet_id, page_no) values (%s, %s) returning id",
                    (sheet_ids[page.ord], page.page_no),
                )
                page_ids[(page.ord, page.page_no)] = cur.fetchone()[0]

            for asset in payload.assets:
                sheet_id = sheet_ids[asset.ord] if asset.ord is not None else None
                page_id = (
                    page_ids[(asset.ord, asset.page_no)]
                    if asset.ord is not None and asset.page_no is not None
                    else None
                )
                cur.execute(
                    "insert into assets (project_id, sheet_id, sheet_page_id, kind, role, "
                    "rel_path, bytes, sha256) values (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        project_id,
                        sheet_id,
                        page_id,
                        asset.kind,
                        asset.role,
                        asset.rel_path,
                        asset.bytes,
                        asset.sha256,
                    ),
                )
        conn.commit()

    return {
        "projects": 1,
        "sheets": len(payload.sheets),
        "sheet_pages": len(payload.pages),
        "assets": len(payload.assets),
    }
