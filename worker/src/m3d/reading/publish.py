"""m3d publish — 크롭 PNG 를 비공개 Storage 버킷 `crops` 에 올린다 (M2b 설계서 §4-1).

웹은 로그인 세션으로 서명 URL 을 받아 이 오브젝트를 표시한다. 업로드는 service key 로만
하고(RLS 우회), 그 값은 어떤 로그·출력에도 남기지 않는다. HTTP 는 표준 라이브러리만 쓴다 —
테스트는 `_upload` 를 가짜로 바꾼다.
"""

from __future__ import annotations

import urllib.error
import urllib.request

import psycopg

from m3d.config import Config
from m3d.samples.manifest import sha256_file

BUCKET = "crops"


def object_key(slug: str, amb_id) -> str:
    """버킷 안 오브젝트 키 — 웹(questions.ts cropObjectKey)과 같은 규칙."""
    return f"{slug}/{amb_id}.png"


def _upload(url: str, headers: dict[str, str], data: bytes) -> tuple[int, str]:
    """순수 HTTP POST. (상태코드, 본문) — 예외를 상태코드로 바꿔 호출자가 집계하게 한다."""
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        return 0, str(e.reason)


def run_publish(cfg: Config, dataset: str, *, force: bool = False) -> dict:
    """crop_rel_path 가 있는 ambiguity 전건을 업로드하고 assets.storage_path 를 채운다.

    스킵 규칙: storage_path 가 이미 있고 assets.sha256 이 현재 파일과 같으면 스킵(--force 시 재업로드).
    """
    if not cfg.supabase_url or not cfg.supabase_service_key:
        raise RuntimeError("SUPABASE_URL·SUPABASE_SERVICE_KEY 미설정 — .env 를 확인하세요")
    base = cfg.supabase_url.rstrip("/")
    key = cfg.supabase_service_key
    uploaded = skipped = 0
    failures: list[tuple[str, str]] = []

    with psycopg.connect(cfg.require_db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute("select id from projects where slug = %s", (dataset,))
            row = cur.fetchone()
            if row is None:
                raise RuntimeError(f"프로젝트 '{dataset}' 없음 — seed 먼저")
            project_id = row[0]
            cur.execute(
                "select a.id, a.crop_rel_path, x.sha256, x.storage_path "
                "from ambiguities a "
                "left join assets x on x.project_id = a.project_id and x.rel_path = a.crop_rel_path "
                "where a.project_id = %s and a.crop_rel_path is not null "
                "order by a.crop_rel_path", (project_id,))
            rows = cur.fetchall()

        for amb_id, rel, sha_db, storage_path in rows:
            path = cfg.repo_root / rel
            if not path.is_file():
                failures.append((str(amb_id), "크롭 파일 없음 — crops 먼저"))
                continue
            sha = sha256_file(path)
            if storage_path and not force and sha_db == sha:
                skipped += 1
                continue
            obj = object_key(dataset, amb_id)
            status, body = _upload(
                f"{base}/storage/v1/object/{BUCKET}/{obj}",
                {"Authorization": f"Bearer {key}", "apikey": key,
                 "x-upsert": "true", "Content-Type": "image/png"},
                path.read_bytes())
            if status < 200 or status >= 300:
                failures.append((str(amb_id), f"HTTP {status}: {body[:120]}"))
                continue
            with conn.cursor() as cur:
                cur.execute("update assets set storage_path = %s "
                            "where project_id = %s and rel_path = %s",
                            (f"{BUCKET}/{obj}", project_id, rel))
            uploaded += 1
        conn.commit()

    return {"uploaded": uploaded, "skipped": skipped, "failures": failures, "total": len(rows)}
