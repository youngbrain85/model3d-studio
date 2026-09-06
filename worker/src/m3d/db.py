"""Supabase 직결 — 마이그레이션 적용과 상태 확인 (설계서 §5).

supabase CLI 도 Docker 도 없으므로 psycopg 로 Session pooler 에 직접 붙는다.
대시보드 수동 붙여넣기와 달리 재현 가능하고 이력이 schema_migrations 에 남는다.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import psycopg

from m3d.config import Config

TABLES = ("projects", "sheets", "sheet_pages", "assets", "readings", "ambiguities", "decisions",
          "builds", "build_sections", "approvals", "jobs", "job_events")

SCHEMA_MIGRATIONS_DDL = """
create table if not exists schema_migrations (
  version    text primary key,
  sha256     text not null,
  applied_at timestamptz not null default now()
);
"""


class MigrationError(RuntimeError):
    """마이그레이션 파일 누락·사후 변조."""


@dataclass(frozen=True)
class Migration:
    version: str
    path: Path
    sha256: str        # 줄끝 정규화(LF) 해시 — 기록·비교의 정본
    sha256_raw: str    # 파일 바이트 그대로의 해시 — 정규화 도입 전(M0·M1) 기록과의 호환


def migration_sha256(path: Path) -> str:
    """줄끝을 LF 로 정규화한 뒤 해시한다.

    core.autocrlf=true 체크아웃은 같은 파일을 CRLF 로 내놓아, 임시 워크트리(LF)에서 적용한
    마이그레이션이 메인 체크아웃에서 "사후 수정" 으로 오인됐다(2026-09-05 실측). 내용이 같으면
    줄끝과 무관하게 같은 sha 여야 한다.
    """
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def _raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover_migrations(directory: Path) -> list[Migration]:
    files = sorted(directory.glob("*.sql"))
    if not files:
        raise MigrationError(f"마이그레이션이 없습니다: {directory}")
    return [Migration(f.stem, f, migration_sha256(f), _raw_sha256(f)) for f in files]


def pending_migrations(
    available: list[Migration], applied: dict[str, str]
) -> list[Migration]:
    """아직 적용되지 않은 것만 돌려준다. 적용 후 수정된 파일은 에러로 정지시킨다.

    기록된 sha 는 정규화 해시(현재) 또는 바이트 해시(정규화 도입 전 기록) 중 하나와 맞으면 된다.
    """
    pending: list[Migration] = []
    for migration in available:
        recorded = applied.get(migration.version)
        if recorded is None:
            pending.append(migration)
        elif recorded not in (migration.sha256, migration.sha256_raw):
            raise MigrationError(
                f"{migration.version} 은 이미 적용되었는데 파일이 그 뒤 수정되었습니다 "
                f"(기록 {recorded[:12]}… / 현재 {migration.sha256[:12]}…). "
                "적용된 마이그레이션을 고치지 말고 새 파일을 추가하세요."
            )
    return pending


def apply_migrations(cfg: Config) -> list[str]:
    available = discover_migrations(cfg.migrations_dir)

    with psycopg.connect(cfg.require_db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_MIGRATIONS_DDL)
            cur.execute("select version, sha256 from schema_migrations")
            applied = dict(cur.fetchall())
        conn.commit()

        todo = pending_migrations(available, applied)
        for migration in todo:
            with conn.cursor() as cur:
                # 파라미터 없는 execute 는 단순 질의 프로토콜을 써서 여러 문장을 허용한다
                cur.execute(migration.path.read_text(encoding="utf-8"))
                cur.execute(
                    "insert into schema_migrations (version, sha256) values (%s, %s)",
                    (migration.version, migration.sha256),
                )
            conn.commit()

    return [m.version for m in todo]


def check(cfg: Config) -> dict:
    """테이블 행 수·RLS 활성 여부·프로젝트 좌표계를 읽어온다."""
    with psycopg.connect(cfg.require_db_url()) as conn, conn.cursor() as cur:
        counts: dict[str, int] = {}
        for table in TABLES:  # 테이블명은 상수 튜플에서만 온다 — 외부 입력 아님
            cur.execute(f"select count(*) from {table}")
            counts[table] = cur.fetchone()[0]

        cur.execute(
            "select c.relname, c.relrowsecurity "
            "from pg_class c join pg_namespace n on n.oid = c.relnamespace "
            "where n.nspname = 'public' and c.relname = any(%s)",
            (list(TABLES),),
        )
        rls = {name: enabled for name, enabled in cur.fetchall()}

        cur.execute(
            "select catalog_status, count(*) from sheets group by catalog_status"
        )
        catalog_status_counts = dict(cur.fetchall())

        cur.execute(
            "select count(*) from sheets where drawing_no_from_content is not null"
        )
        from_content_filled = cur.fetchone()[0]

        cur.execute(
            "select count(*) from sheet_pages "
            "where width_px is not null and height_px is not null"
        )
        pages_sized = cur.fetchone()[0]

        cur.execute(
            "select slug, name, coord_system, coord_assumptions "
            "from projects order by slug"
        )
        projects = [
            {
                "slug": slug,
                "name": name,
                "coord_system": coord_system,
                "coord_assumptions": coord_assumptions,
            }
            for slug, name, coord_system, coord_assumptions in cur.fetchall()
        ]

        cur.execute("select region, status, count(*) from readings group by 1, 2 order by 1, 2")
        reading_stats = [{"region": r, "status": s, "n": n} for r, s, n in cur.fetchall()]

        cur.execute("select status, count(*) from ambiguities group by 1 order by 1")
        ambiguity_stats = dict(cur.fetchall())

        cur.execute("select count(*) from ambiguities where crop_rel_path is not null")
        crops_ready = cur.fetchone()[0]

        cur.execute("select count(*) from ambiguities where crop_rel_path is null")
        crop_missing = cur.fetchone()[0]

        cur.execute("select count(*) from assets where role = 'derived' "
                    "and rel_path like '%%/crops/%%'")
        crops_assets = cur.fetchone()[0]

        cur.execute("select count(*), count(*) filter (where provisional) from decisions")
        decisions_total, decisions_provisional = cur.fetchone()

        cur.execute("select count(*) from assets where role = 'derived' "
                    "and rel_path like '%%/crops/%%' and storage_path is not null")
        published = cur.fetchone()[0]

    return {"counts": counts, "rls": rls, "projects": projects,
            "catalog_status_counts": catalog_status_counts,
            "from_content_filled": from_content_filled,
            "pages_sized": pages_sized,
            "reading_stats": reading_stats,
            "ambiguity_stats": ambiguity_stats,
            "crops_ready": crops_ready,
            "crop_missing": crop_missing,
            "crops_assets": crops_assets,
            "decisions_total": decisions_total,
            "decisions_provisional": decisions_provisional,
            "published": published}
