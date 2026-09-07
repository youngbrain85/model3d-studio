"""워커 데몬 (M5 D10) — jobs 큐에서 잡을 집어 실행하고 상태·이벤트를 기록한다. DB URL 직결(RLS 비적용)."""

from __future__ import annotations

import time
import traceback

import psycopg
from psycopg.types.json import Jsonb

from m3d.agent import loop as agent_loop
from m3d.config import Config

CLAIM_SQL = ("update jobs set status = 'running', updated_at = now() "
             "where id = (select id from jobs where status = 'queued' order by created_at limit 1 for update skip locked) "
             "returning id, project_id, kind, section_key, request, parent_job_id, budget_usd")
FAIL_REASONS = {"budget", "no_run", "unsupported_section", "no_reference", "error"}


def claim(conn) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(CLAIM_SQL)
        row = cur.fetchone()
    conn.commit()
    if row is None:
        return None
    keys = ("id", "project_id", "kind", "section_key", "request", "parent_job_id", "budget_usd")
    job = dict(zip(keys, row))
    for k in ("id", "project_id", "parent_job_id"):
        if job.get(k) is not None:
            job[k] = str(job[k])
    return job


def emit_event(conn, job_id: str, level: str, message: str) -> None:
    with conn.cursor() as cur:
        cur.execute("insert into job_events (job_id, level, message) values (%s, %s, %s)", (job_id, level, message[:2000]))
    conn.commit()


def finish(conn, job_id: str, *, status: str, result: dict, build_id, cost_usd: float, attempts: int) -> None:
    with conn.cursor() as cur:
        cur.execute("update jobs set status = %s, result = %s, build_id = %s, cost_usd = %s, attempts = %s, updated_at = now() where id = %s",
                    (status, Jsonb(result), build_id, round(float(cost_usd), 4), int(attempts), job_id))
    conn.commit()


def dataset_slug(conn, project_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute("select slug from projects where id = %s", (project_id,))
        row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"프로젝트 없음: {project_id}")
    return row[0]


def run_once(cfg: Config, *, run_job_fn=None) -> bool:
    """큐에서 잡 1건을 처리한다. 처리했으면 True, 비어 있으면 False."""
    run_job_fn = run_job_fn or agent_loop.run_job
    with psycopg.connect(cfg.require_db_url()) as conn:
        job = claim(conn)
        if job is None:
            return False
        dataset = dataset_slug(conn, job["project_id"])

        def emit(level, message):
            emit_event(conn, job["id"], level, message)
            print(f"[{level}] {message}")
        emit("info", f"잡 시작 {job['section_key']} (요청: {job.get('request') or '없음'})")
        try:
            result = run_job_fn(cfg, dataset, job, emit)
            status = "failed" if result.get("reason") in FAIL_REASONS else "done"
        except Exception as exc:                       # noqa: BLE001 — 잡은 failed 로 남기고 데몬은 계속
            emit("error", f"예외: {type(exc).__name__}: {exc}")
            result = {"pass": False, "reason": "error", "error": f"{type(exc).__name__}: {exc}",
                      "traceback": traceback.format_exc()[-2000:], "attempts": 0, "cost_usd": 0.0}
            status = "failed"
        finish(conn, job["id"], status=status, result=result, build_id=result.get("build_id"),
               cost_usd=result.get("cost_usd", 0.0), attempts=result.get("attempts", 0))
        bv = result.get("build_version")
        print(f"worker job={job['id']} section={job['section_key']} attempts={result.get('attempts', 0)} pass={result.get('pass')} "
              f"cost=${float(result.get('cost_usd', 0.0)):.2f} build={'b' + str(bv) if bv else '-'} status={status}")
        return True


def serve(cfg: Config, *, poll: float = 2.0, once: bool = False, drain: bool = False, run_job_fn=None) -> None:
    """큐를 처리한다 — once: 1건, drain: 큐가 빌 때까지(일괄 실행, M7 D6), 그 밖에는 상주."""
    mode = "한 건" if once else ("큐 소진" if drain else "상주")
    print(f"worker 시작 — {mode}, poll {poll}s, 기본 예산 상한 ${cfg.model_agent_budget_usd:.2f} (Ctrl+C 로 종료)")
    while True:
        did = run_once(cfg) if run_job_fn is None else run_once(cfg, run_job_fn=run_job_fn)
        if did and once:
            return
        if not did:
            if once or drain:
                return
            time.sleep(poll)
