"""m3d publish-model — 섹션 GLB·결합본·렌더·검증 JSON 을 비공개 버킷 `models` 에 올리고 builds·build_sections 행을 만든다 (M4 설계서 §5).

업로드는 service key(RLS 우회)로만 하며 값은 어떤 출력에도 남기지 않는다. HTTP 는 reading.publish._upload(표준 라이브러리) 재사용.
버전 규칙(D7): content_sha256 = sha256(결합본 sha256 ‖ modelspec sha256). 같은 해시의 빌드가 종류·버전 무관 하나라도 있으면 skip(--force 예외),
새 버전은 프로젝트 최대 버전 + 1.
업로드가 하나라도 실패하면 DB 행을 만들지 않는다. DB 에 저장하는 경로는 버킷 접두 없는 오브젝트 키다(웹 createSignedUrls 규칙).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from m3d.config import Config
from m3d.model import io as model_io
from m3d.reading.publish import _upload
from m3d.samples.manifest import sha256_file

BUCKET = "models"
REQUIRED = ("build.json", "AB1_P4P5.glb", "selfcheck.json", "selfcheck_sections.json", "modelspec.json", "renders/views.json")
OPTIONAL = ("measure.json", "compare.json")
CONTENT_TYPES = {".glb": "model/gltf-binary", ".png": "image/png", ".json": "application/json",
                 ".py": "text/x-python", ".md": "text/markdown"}
AGENT_FILES = ("agent/code.py", "agent/attempts.json", "agent/score.json", "agent/prompt.md")   # M5 에이전트 빌드 부속(시도 파일 제외)


def object_key(slug: str, version: int, rel: str) -> str:
    """버킷 안 오브젝트 키 — 웹(lib/models.ts modelObjectKey)과 같은 규칙."""
    return f"{slug}/b{version}/{rel}"


def _load(out_dir: Path, rel: str) -> dict:
    return json.loads((Path(out_dir) / rel).read_text(encoding="utf-8"))


def collect_files(out_dir: Path) -> list[str]:
    """필수 6 + 섹션 GLB(build.json 순서) + renders/*.png(이름순) + 선택 JSON — posix 상대경로."""
    out_dir = Path(out_dir)
    missing = [r for r in REQUIRED if not (out_dir / r).is_file()]
    if missing:
        raise RuntimeError("필수 산출물 없음: " + ", ".join(missing) + " — `m3d build`·`m3d render` 먼저")
    build = _load(out_dir, "build.json")
    files = list(REQUIRED) + [s["file"] for s in build["sections"]]
    files += sorted(p.relative_to(out_dir).as_posix() for p in (out_dir / "renders").glob("*.png"))
    files += [r for r in OPTIONAL if (out_dir / r).is_file()]
    files += [r for r in AGENT_FILES if (out_dir / r).is_file()]
    absent = [rel for rel in files if not (out_dir / rel).is_file()]
    if absent:
        raise RuntimeError("산출물 없음: " + ", ".join(absent))
    return files


def content_sha256(out_dir: Path) -> str:
    out_dir = Path(out_dir)
    return hashlib.sha256((sha256_file(out_dir / "AB1_P4P5.glb") + sha256_file(out_dir / "modelspec.json")).encode("ascii")).hexdigest()


def build_stats(out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    build, sc = _load(out_dir, "build.json"), _load(out_dir, "selfcheck.json")
    stats = {"meshes": build["assembled"]["meshes"], "triangles": build["assembled"]["triangles"],
             "selfcheck": {"pass": sc["pass"], "fail": sc["fail"], "skipped": sc["skipped"]}, "measure": None, "compare": None}
    if (out_dir / "measure.json").is_file():
        agg = _load(out_dir, "measure.json")["집계"]
        stats["measure"] = {"pass": agg["PASS"], "fail": agg["FAIL"], "info": agg["INFO"]}
    if (out_dir / "compare.json").is_file():
        stats["compare"] = dict(_load(out_dir, "compare.json")["summary"])
    if (out_dir / "agent" / "score.json").is_file():
        data = _load(out_dir, "agent/score.json")
        stats["agent"] = data.get("summary", data)          # 루프가 쓴 파일은 {summary, score, …}, 요약만 stats 에
    else:
        stats["agent"] = None
    return stats


def run_publish_model(cfg: Config, dataset: str, *, pilot: bool = False, force: bool = False,
                      out_dir: Path | None = None, kind: str | None = None) -> dict:
    """out_dir 를 주면 그 산출 디렉터리(에이전트 빌드 등)를, kind 를 주면 build.json 의 kind 대신 그 값을 쓴다."""
    if not cfg.supabase_url or not cfg.supabase_service_key:
        raise RuntimeError("SUPABASE_URL·SUPABASE_SERVICE_KEY 미설정 — .env 를 확인하세요")
    out_dir = Path(out_dir) if out_dir is not None else model_io.model_dir(cfg, dataset, pilot=pilot)
    files = collect_files(out_dir)
    build = _load(out_dir, "build.json")
    content = content_sha256(out_dir)
    base, key = cfg.supabase_url.rstrip("/"), cfg.supabase_service_key

    with psycopg.connect(cfg.require_db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute("select id from projects where slug = %s", (dataset,))
            row = cur.fetchone()
            if row is None:
                raise RuntimeError(f"프로젝트 '{dataset}' 없음 — seed 먼저")
            project_id = row[0]
            # 같은 내용의 빌드가 (종류·버전 무관) 하나라도 있으면 skip — 시범/전체가 번갈아 올라가도 새 버전을 만들지 않는다 (D7)
            cur.execute("select version from builds where project_id = %s and content_sha256 = %s order by version desc limit 1",
                        (project_id, content))
            same = cur.fetchone()
            cur.execute("select coalesce(max(version), 0) from builds where project_id = %s", (project_id,))
            max_version = cur.fetchone()[0]
        if same is not None and not force:
            return {"skipped": True, "version": same[0], "files": len(files), "uploaded": 0, "failures": [], "build_id": None}
        version = max_version + 1

        uploaded, failures = 0, []
        for rel in files:
            path = out_dir / rel
            status, body = _upload(
                f"{base}/storage/v1/object/{BUCKET}/{object_key(dataset, version, rel)}",
                {"Authorization": f"Bearer {key}", "apikey": key, "x-upsert": "true",
                 "Content-Type": CONTENT_TYPES.get(path.suffix, "application/octet-stream")},
                path.read_bytes())
            if 200 <= status < 300:
                uploaded += 1
            else:
                failures.append((rel, f"HTTP {status}: {body[:120]}"))
        if failures:
            return {"skipped": False, "version": None, "files": len(files), "uploaded": uploaded, "failures": failures, "build_id": None}

        keyed = {rel: object_key(dataset, version, rel) for rel in files}
        file_index = {"renders": [keyed[r] for r in files if r.startswith("renders/") and r.endswith(".png")],
                      "json": [keyed[r] for r in files if r.endswith(".json") and r != "renders/views.json" and not r.startswith("agent/")],
                      "views": keyed["renders/views.json"],
                      "agent": [keyed[r] for r in files if r.startswith("agent/")]}
        sec_checks = _load(out_dir, "selfcheck_sections.json")
        with conn.cursor() as cur:
            cur.execute("insert into builds (project_id, version, kind, segment, content_sha256, glb_path, files, stats, git_sha) "
                        "values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning id",
                        (project_id, version, kind or build["kind"], build["segment"], content, keyed["AB1_P4P5.glb"],
                         Jsonb(file_index), Jsonb(build_stats(out_dir)), build.get("git_sha")))
            build_id = cur.fetchone()[0]
            for s in build["sections"]:
                rs = sec_checks.get(s["key"], {"pass": 0, "fail": 0, "checks": []})
                cur.execute("insert into build_sections (build_id, section_key, code, label, glb_path, bytes, sha256, meshes, triangles, selfcheck, source) "
                            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                            (build_id, s["key"], s["code"], s["label"], keyed[s["file"]], s["bytes"], s["sha256"],
                             s["meshes"], s["triangles"], Jsonb({"pass": rs["pass"], "fail": rs["fail"], "checks": rs.get("checks", [])}),
                             s.get("source", "builder")))
        conn.commit()
    return {"skipped": False, "version": version, "files": len(files), "uploaded": uploaded, "failures": [], "build_id": str(build_id)}
