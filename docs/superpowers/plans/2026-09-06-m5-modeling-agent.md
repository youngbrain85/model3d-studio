# M5 모델링 에이전트(격벽 1섹션) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> 이 프로젝트 규칙: 서브에이전트 없이 **이 세션에서 직접** 실행한다. TDD. LLM 실호출은 Task 7 실증에서만(상한 $5); 그 전 태스크는 전부 가짜 LLM·무과금.

**Goal:** 웹에서 격벽 섹션 "LLM 으로 만들기"를 누르면 로컬 워커가 잡을 집어 Sonnet 5 로 격벽 빌더 코드를 받아 샌드박스에서 실행·채점(정답 대조 + 레고식 결합 재실측)하고 에이전트 빌드로 올려 화면에 띄우며, 수정 요청과 승인이 이어진다 (설계서 `docs/superpowers/specs/2026-09-06-m5-modeling-agent-design.md`).

**Architecture:** `worker/src/m3d/agent/` — `schema`(출력), `sandbox`+`runner`(AST 화이트리스트 + 별도 프로세스 실행, ctx 는 본체 기하만), `crops`+`context`(판독 근거 크롭·규칙·툴킷·스펙 발췌로 프롬프트 묶음), `score`(정답 대조·섹션 self-check·결합 self-check·재실측), `loop`(시도 ≤4·예산·산출 디렉터리·publish), `worker`(잡 claim/finish 데몬). DB 0006 `jobs`·`job_events`, `builds.kind='agent'`, `build_sections.source`. 웹은 잡 생성·폴링·에이전트 빌드 표시·수정 요청.

**Tech Stack:** Python 3.12(anthropic 1.2·pydantic 2·trimesh·psycopg 3·typer·PIL), Supabase(PostgreSQL RLS·Storage), React 18 + Mantine 8 + supabase-js + three, pytest·vitest.

## Global Constraints

- LLM 실호출은 Task 7 에서만. 모든 실호출은 `call_structured`(기존) 경로로 `usage.jsonl` 에 stage `model-agent` 로 기록. 누적 상한 `MODEL_AGENT_BUDGET_USD`(기본 5.0) — 호출 전 `spent + 0.15 > budget` 이면 호출하지 않는다.
- 모델 `claude-sonnet-5`(`client.MODEL_READ`), `max_tokens=16000`, thinking 비활성(`_thinking_kwargs` 기존 규약). 가격표 `client.PRICING` = Sonnet $2/M in·$10/M out.
- 비밀값 출력 금지. 참조 원본 읽기 전용.
- 에이전트 코드 계약: `build_section(spec: dict, ctx) -> dict[str, trimesh.Trimesh]`, 노드명 정규식 `^AB1_S5_[A-Z0-9_]+$`(격벽은 `AB1_S5_DIA01`~`DIA26`), 반환 메시는 수밀·버텍스 컬러 필수. 허용 import: `math`·`numpy`·`trimesh`·`m3d.model.geom`. `ctx` 노출 목록(D2): `x_web, z_p4, z_p5, y_web_top(z), y_web_bot(z), h_box(z), t_web(z), COL_STEEL, INS, geom`.
- 채점 pass 규칙(D6): `only_ours == [] and only_ref == [] and bbox_dev_max_m <= 0.005 and 섹션 self-check fail == 0 and 결합 self-check fail == 0 and 재실측 FAIL == 0`.
- 잡 상태 `queued → running → done|failed`, 이벤트 level `info|warn|error`. 에이전트 빌드는 `builds.kind='agent'`, 격벽 `build_sections.source='agent'`, 나머지 9섹션 `source='builder'`(정답 빌드 디렉터리 복제).
- 오브젝트 키·버전 규칙은 M4 그대로(`<slug>/b<version>/<rel>`, 내용 해시 전체 대조; 에이전트 빌드는 `force=True` 로 항상 새 버전).
- 실행 명령: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests -q` / `npm --prefix web run typecheck` / `npm --prefix web test`. 브랜치 `feat/m5-modeling-agent`(main 1b5ff2e 분기). 커밋 트레일러 `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## File Structure

| 경로 | 책임 |
|---|---|
| `supabase/migrations/0006_jobs.sql` (신규) | jobs·job_events·RLS, builds.kind agent, build_sections.source |
| `worker/src/m3d/db.py`, `contracts/db.types.ts` (수정) | TABLES 12표, TS 타입(jobs·job_events·kind·source·BuildFiles.agent·BuildStats.agent) |
| `worker/src/m3d/config.py` (수정) | `model_agent_budget_usd` (env `MODEL_AGENT_BUDGET_USD`, 기본 5.0) |
| `worker/src/m3d/agent/__init__.py`, `schema.py` (신규) | `AgentOut` |
| `worker/src/m3d/agent/sandbox.py`, `runner.py` (신규) | AST 검사, 서브프로세스 실행, `BoxContext`, 반환 검증·GLB |
| `worker/src/m3d/agent/crops.py`, `context.py` (신규) | 판독 근거 크롭, 프롬프트 묶음(규칙·툴킷·ctx·계약·스펙 발췌·피드백) |
| `worker/src/m3d/agent/score.py` (신규) | 정답 대조·섹션/결합 self-check·재실측·피드백 문장 |
| `worker/src/m3d/agent/loop.py`, `worker.py` (신규) | 잡 실행 루프·예산·산출 디렉터리·publish; claim/finish 데몬 |
| `worker/src/m3d/model/publish.py`, `io.py` (수정) | `run_publish_model(out_dir=, kind=)`, `agent/*` 파일·stats.agent·sections[].source; `load_modelspec_raw` |
| `worker/src/m3d/cli.py` (수정) | `m3d worker [--once] [--poll]` |
| `web/src/lib/jobs.ts` (+test), `web/src/routes/Model.tsx`, `web/src/components/VerifyPanel.tsx`, `web/src/components/JobPanel.tsx` (신규) | 잡 생성·폴링·패널, 에이전트 빌드 채점·assumptions·questions·코드 링크·수정 요청, LLM 배지 |
| 테스트 | `worker/tests/test_migration_0006.py`, `test_db_tables.py`(수정), `test_agent_sandbox.py`, `test_agent_context.py`, `test_agent_score.py`, `test_agent_loop.py`, `test_agent_worker.py`, `test_model_publish.py`(수정); `web/src/lib/jobs.test.ts` |

---

### Task 1: 마이그레이션 0006 (jobs·job_events·kind agent·source) + TABLES + 타입 + config

**Files:**
- Create: `supabase/migrations/0006_jobs.sql`, `worker/tests/test_migration_0006.py`
- Modify: `worker/src/m3d/db.py`, `worker/tests/test_db_tables.py`, `contracts/db.types.ts`, `worker/src/m3d/config.py`, `worker/tests/test_config.py`(있으면 추가), `.env.example`

**Interfaces:**
- Produces: 표 `jobs`·`job_events`(설계서 §4 그대로), `builds.kind ∈ {pilot,full,agent}`, `build_sections.source ∈ {builder,agent}`; `db.TABLES` 12개(끝에 `"jobs", "job_events"`); TS `Tables.jobs`·`Tables.job_events`, `BuildFiles.agent?: string[]`, `BuildStats.agent?: AgentScoreSummary | null`; `Config.model_agent_budget_usd: float`.

- [ ] **Step 1: 실패 테스트**

`worker/tests/test_migration_0006.py`:
```python
"""0006_jobs — 잡 큐·이벤트·RLS, builds.kind agent, build_sections.source 가 회귀로 사라지지 않게 고정한다."""

import re

import pytest

from m3d.config import REPO_ROOT
from m3d.db import discover_migrations


@pytest.fixture
def norm() -> str:
    path = REPO_ROOT / "supabase" / "migrations" / "0006_jobs.sql"
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_discovered_after_0005():
    versions = [m.version for m in discover_migrations(REPO_ROOT / "supabase" / "migrations")]
    assert versions[:6] == ["0001_init", "0002_convert", "0003_readings", "0004_decisions", "0005_builds", "0006_jobs"]


def test_jobs_and_events_tables(norm):
    assert "create table jobs (" in norm
    assert "kind text not null check (kind in ('model-section'))" in norm
    assert "status text not null default 'queued' check (status in ('queued','running','done','failed'))" in norm
    assert "parent_job_id uuid references jobs(id) on delete set null" in norm
    assert "budget_usd numeric(8,2) not null default 5" in norm
    assert "build_id uuid references builds(id) on delete set null" in norm
    assert "user_id uuid not null default auth.uid()" in norm
    assert "create table job_events (" in norm and "level text not null check (level in ('info','warn','error'))" in norm
    assert "references jobs(id) on delete cascade" in norm


def test_rls_select_and_own_insert_only(norm):
    for t in ("jobs", "job_events"):
        assert f"alter table {t} enable row level security" in norm
        assert f'create policy "authenticated read" on {t} for select to authenticated using (true)' in norm
    assert 'create policy "authenticated insert" on jobs for insert to authenticated with check (user_id = auth.uid())' in norm
    assert norm.count("for insert") == 1 and "for update" not in norm and "for delete" not in norm and "to anon" not in norm


def test_builds_kind_agent_and_section_source(norm):
    assert "alter table builds drop constraint builds_kind_check" in norm
    assert "add constraint builds_kind_check check (kind in ('pilot','full','agent'))" in norm
    assert "alter table build_sections add column source text not null default 'builder' check (source in ('builder','agent'))" in norm
```

`worker/tests/test_db_tables.py` 를 교체:
```python
"""db.TABLES — db check 가 세는 표 목록에 M4·M5 표가 들어간다."""

from m3d.db import TABLES


def test_tables_include_m4_m5_tables_in_order():
    assert TABLES[-5:] == ("builds", "build_sections", "approvals", "jobs", "job_events")
    assert len(TABLES) == len(set(TABLES)) == 12
```

config 테스트(`worker/tests/test_config.py` 끝에 추가):
```python


def test_model_agent_budget_default_and_env(tmp_path, monkeypatch):
    from m3d.config import load_config
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    monkeypatch.delenv("MODEL_AGENT_BUDGET_USD", raising=False)
    assert load_config(env_file=tmp_path / "absent.env").model_agent_budget_usd == 5.0
    monkeypatch.setenv("MODEL_AGENT_BUDGET_USD", "2.5")
    assert load_config(env_file=tmp_path / "absent.env").model_agent_budget_usd == 2.5
```

- [ ] **Step 2: 실패 확인**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_migration_0006.py worker/tests/test_db_tables.py worker/tests/test_config.py -q`
Expected: FAIL — 파일 없음 / TABLES 불일치 / `model_agent_budget_usd` 속성 없음

- [ ] **Step 3: 마이그레이션·TABLES·config·타입**

`supabase/migrations/0006_jobs.sql` (LF):
```sql
-- 0006_jobs — 모델링 에이전트 잡 큐·이벤트 + builds.kind agent + build_sections.source (M5 설계서 §4)
-- jobs 는 웹이 만들고(본인 행만) 로컬 워커가 DB URL 로 집어 갱신한다(RLS 비적용 경로). job_events 는 워커 로그.

create table jobs (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references projects(id) on delete cascade,
  kind          text not null check (kind in ('model-section')),
  section_key   text not null,
  request       text not null default '',
  parent_job_id uuid references jobs(id) on delete set null,
  status        text not null default 'queued' check (status in ('queued','running','done','failed')),
  attempts      int  not null default 0,
  cost_usd      numeric(8,4) not null default 0,
  budget_usd    numeric(8,2) not null default 5,
  result        jsonb,
  build_id      uuid references builds(id) on delete set null,
  user_id       uuid not null default auth.uid(),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index on jobs (project_id, status, created_at);
create table job_events (
  id      bigserial primary key,
  job_id  uuid not null references jobs(id) on delete cascade,
  ts      timestamptz not null default now(),
  level   text not null check (level in ('info','warn','error')),
  message text not null
);
create index on job_events (job_id, id);

alter table jobs       enable row level security;
alter table job_events enable row level security;
create policy "authenticated read"   on jobs       for select to authenticated using (true);
create policy "authenticated read"   on job_events for select to authenticated using (true);
create policy "authenticated insert" on jobs       for insert to authenticated
  with check (user_id = auth.uid());

-- 에이전트 빌드 종류 + 섹션 출처(정답 빌더 / LLM 에이전트)
alter table builds drop constraint builds_kind_check;
alter table builds add constraint builds_kind_check check (kind in ('pilot','full','agent'));
alter table build_sections add column source text not null default 'builder' check (source in ('builder','agent'));
```

`worker/src/m3d/db.py`:
```python
TABLES = ("projects", "sheets", "sheet_pages", "assets", "readings", "ambiguities", "decisions",
          "builds", "build_sections", "approvals", "jobs", "job_events")
```

`worker/src/m3d/config.py`: dataclass 에 `model_agent_budget_usd: float` 필드 추가(다른 선택 필드 옆), `load_config` 에서
```python
        model_agent_budget_usd=float(_env("MODEL_AGENT_BUDGET_USD") or "5.0"),
```
`.env.example` 에 `MODEL_AGENT_BUDGET_USD=5.0   # M5 모델링 에이전트 누적 API 상한(USD)` 한 줄.

`contracts/db.types.ts`:
- `builds.Row.kind: 'pilot' | 'full' | 'agent'`.
- `build_sections.Row` 에 `source: 'builder' | 'agent';`.
- `BuildFiles` 에 `agent?: string[];`, `BuildStats` 에 `agent?: AgentScoreSummary | null;`, 보조 타입:
```ts
export interface AgentScoreSummary {
  pass: boolean; only_ours: number; only_ref: number; bbox_dev_max_m: number | null;
  section_fail: number; assembled_fail: number; measure_fail: number | null; attempts: number;
}
```
- `approvals` 블록 뒤에:
```ts
      jobs: {
        Row: {
          id: string; project_id: string; kind: 'model-section'; section_key: string; request: string;
          parent_job_id: string | null; status: 'queued' | 'running' | 'done' | 'failed'; attempts: number;
          cost_usd: number; budget_usd: number; result: JobResult | null; build_id: string | null; user_id: string;
          created_at: string; updated_at: string;
        };
        Insert: {
          id?: string; project_id: string; kind: 'model-section'; section_key: string; request?: string;
          parent_job_id?: string | null; budget_usd?: number; user_id?: string;
        };
        Update: never;
      };
      job_events: {
        Row: { id: number; job_id: string; ts: string; level: 'info' | 'warn' | 'error'; message: string };
        Insert: never;
        Update: never;
      };
```
보조 타입: `export interface JobResult { pass: boolean; reason?: string; attempts: number; cost_usd: number; build_version?: number; assumptions?: string[]; questions?: string[] }`. 파일 머리 주석 `0001~0006`.

- [ ] **Step 4: 테스트·적용**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests -q` → 전건 PASS; `npm --prefix web run typecheck` → 0
Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli db apply && PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli db check | grep -E "^jobs|^job_events"` → `적용 1건: 0006_jobs`, `jobs 0 on`, `job_events 0 on`

- [ ] **Step 5: 커밋**

```bash
git add supabase/migrations/0006_jobs.sql worker/src/m3d/db.py worker/src/m3d/config.py .env.example contracts/db.types.ts worker/tests/test_migration_0006.py worker/tests/test_db_tables.py worker/tests/test_config.py
git commit -m "feat(db): 0006 jobs·job_events + builds.kind agent + build_sections.source; MODEL_AGENT_BUDGET_USD" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: 에이전트 출력 스키마 + 샌드박스(AST 화이트리스트·서브프로세스 러너·BoxContext)

**Files:**
- Create: `worker/src/m3d/agent/__init__.py`(빈 파일), `worker/src/m3d/agent/schema.py`, `worker/src/m3d/agent/sandbox.py`, `worker/src/m3d/agent/runner.py`, `worker/tests/test_agent_sandbox.py`

**Interfaces:**
- Produces: `schema.AgentOut(code, assumptions, questions)`, `schema.validate_agent_out(out)`(계약·AST 위반 시 ValueError — `call_structured` 의 post_validate 로 쓴다);
  `sandbox.ALLOWED_IMPORTS`, `sandbox.check_code(code) -> list[str]`, `sandbox.run_code(code, spec_dict, out_glb, *, timeout=120.0) -> RunResult(ok, glb, node_names, meshes, triangles, error, stdout, stderr)`;
  `runner.BoxContext(builder)`(속성 `x_web, z_p4, z_p5, y_web_top, y_web_bot, h_box, t_web, COL_STEEL, INS, geom`), `runner.main(argv)`.

- [ ] **Step 1: 실패 테스트**

`worker/tests/test_agent_sandbox.py`:
```python
"""샌드박스 — AST 화이트리스트, 별도 프로세스 실행, 반환 검증 (M5 D5)."""

import textwrap

import pytest

from m3d.agent import sandbox, schema
from m3d.model.spec import ModelSpec

GOOD = textwrap.dedent('''
    import numpy as np
    from m3d.model.geom import box_prism, paint

    def build_section(spec, ctx):
        d = spec["diaphragm"]
        out = {}
        for k in range(d["n_cell"] + 1):
            zc = ctx.z_p4 + k * d["spacing"]
            zc = min(max(zc, ctx.z_p4 + 0.01), ctx.z_p5 - 0.01)
            m = box_prism(-2.0, 2.0, ctx.y_web_bot(zc), ctx.y_web_top(zc), zc - 0.005, zc + 0.005)
            out["AB1_S5_DIA%02d" % (k + 1)] = paint(m, ctx.COL_STEEL)
        return out
''')


def test_check_code_flags_forbidden_imports_and_names():
    bad = "import os\nfrom subprocess import run\ndef build_section(spec, ctx):\n    open('x')\n    return getattr(ctx, '__dict__')"
    v = sandbox.check_code(bad)
    assert any("import 금지: os" in x for x in v) and any("subprocess" in x for x in v)
    assert any("이름 금지: open" in x for x in v) and any("이름 금지: getattr" in x for x in v)
    assert any("속성 금지: __dict__" in x for x in v)
    assert sandbox.check_code("x = 1") == ["최상위 def build_section(spec, ctx) 가 없다"]
    assert sandbox.check_code("def build_section(spec, ctx):\n  return {") and "문법 오류" in sandbox.check_code("def build_section(spec, ctx):\n  return {")[0]
    assert sandbox.check_code(GOOD) == []


def test_validate_agent_out_rejects_bad_code():
    with pytest.raises(ValueError, match="import 금지"):
        schema.validate_agent_out(schema.AgentOut(code="import os\ndef build_section(spec, ctx):\n    return {}"))
    schema.validate_agent_out(schema.AgentOut(code=GOOD))


def test_run_code_executes_in_subprocess_and_exports_glb(tmp_path):
    r = sandbox.run_code(GOOD, ModelSpec().model_dump(), tmp_path / "out.glb")
    assert r.ok, r.error
    assert r.meshes == 26 and r.node_names[0] == "AB1_S5_DIA01" and r.node_names[-1] == "AB1_S5_DIA26"
    assert (tmp_path / "out.glb").stat().st_size > 1000 and r.triangles == 26 * 12


def test_run_code_reports_runtime_error_and_bad_return(tmp_path):
    r = sandbox.run_code("def build_section(spec, ctx):\n    return 1 / 0", ModelSpec().model_dump(), tmp_path / "a.glb")
    assert not r.ok and "ZeroDivisionError" in r.error
    r2 = sandbox.run_code("def build_section(spec, ctx):\n    return {'bad name': None}", ModelSpec().model_dump(), tmp_path / "b.glb")
    assert not r2.ok and "노드명 규칙 위반" in r2.error
    r3 = sandbox.run_code("from m3d.model.geom import box_prism\ndef build_section(spec, ctx):\n    return {'AB1_S5_DIA01': box_prism(0, 1, 0, 1, 0, 1)}",
                          ModelSpec().model_dump(), tmp_path / "c.glb")
    assert not r3.ok and "버텍스 컬러" in r3.error


def test_run_code_times_out(tmp_path):
    r = sandbox.run_code("def build_section(spec, ctx):\n    while True:\n        pass", ModelSpec().model_dump(), tmp_path / "t.glb", timeout=3.0)
    assert not r.ok and "시간 초과" in r.error


def test_guarded_import_blocks_at_runtime(tmp_path):
    """AST 를 우회하려 해도(문자열 조립) 러너의 __import__ 가 막는다."""
    code = "def build_section(spec, ctx):\n    m = __builtins__['__import__']('os')\n    return {}"
    assert sandbox.check_code(code)            # AST 단계에서도 걸린다(__import__ 이름 금지)
    r = sandbox.run_code("def build_section(spec, ctx):\n    import socket\n    return {}", ModelSpec().model_dump(), tmp_path / "s.glb")
    assert not r.ok and "import 금지" in r.error
```

- [ ] **Step 2: 실패 확인**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_agent_sandbox.py -q`
Expected: FAIL — `ModuleNotFoundError: m3d.agent`

- [ ] **Step 3: 구현**

`worker/src/m3d/agent/schema.py`:
```python
"""모델링 에이전트 출력 (M5 D1) — 코드 + 가정 + 질문."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentOut(BaseModel):
    code: str = Field(description="build_section(spec, ctx) 를 정의하는 파이썬 코드 전체(허용 import: math, numpy, trimesh, m3d.model.geom)")
    assumptions: list[str] = Field(default_factory=list, description="도면·스펙에서 확정하지 못해 가정한 것(한 항목 = 한 가정)")
    questions: list[str] = Field(default_factory=list, description="사용자에게 확인이 필요한 질문(한 질문 = 한 요소)")


def validate_agent_out(out: AgentOut) -> None:
    """call_structured 의 post_validate — 계약·AST 위반은 ValueError 로 올려 1회 재시도를 유도한다."""
    from m3d.agent.sandbox import check_code
    violations = check_code(out.code)
    if violations:
        raise ValueError("코드 계약 위반: " + "; ".join(violations[:10]))
```

`worker/src/m3d/agent/sandbox.py`:
```python
"""LLM 코드 샌드박스 (M5 D5) — AST 화이트리스트 검사 + 별도 프로세스(`python -I`) 실행.

완전한 격리(네트워크·파일)는 OS 샌드박스가 아니면 불가능하다. 여기서는 (1) AST 로 import·위험 이름을 거르고
(2) 러너가 제한된 builtins 와 가드된 __import__ 로 실행하며 (3) 타임아웃으로 무한 루프를 끊는다.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ALLOWED_IMPORTS = {"math", "numpy", "trimesh", "m3d.model.geom"}
FORBIDDEN_NAMES = {"open", "exec", "eval", "__import__", "compile", "input", "breakpoint", "globals", "locals",
                   "getattr", "setattr", "delattr", "vars", "__builtins__"}
FORBIDDEN_ATTRS = {"__subclasses__", "__globals__", "__code__", "__builtins__", "__dict__", "__class__", "__bases__",
                   "__mro__", "__getattribute__", "__reduce__"}


def _import_ok(name: str) -> bool:
    return name in ALLOWED_IMPORTS or name.split(".")[0] in {"math", "numpy", "trimesh"} or name.startswith("m3d.model.geom")


def check_code(code: str) -> list[str]:
    """계약 위반 목록(비면 통과). 문법 오류도 위반으로 돌려준다."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"문법 오류: {exc.msg} (line {exc.lineno})"]
    bad: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if not _import_ok(a.name):
                    bad.add(f"import 금지: {a.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if not _import_ok(mod):
                bad.add(f"import 금지: {mod}")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            bad.add(f"이름 금지: {node.id}")
        elif isinstance(node, ast.Attribute) and (node.attr in FORBIDDEN_ATTRS or node.attr.startswith("__")):
            bad.add(f"속성 금지: {node.attr}")
    if not any(isinstance(n, ast.FunctionDef) and n.name == "build_section" for n in tree.body):
        bad.add("최상위 def build_section(spec, ctx) 가 없다")
    return sorted(bad)


@dataclass
class RunResult:
    ok: bool
    glb: Path | None
    node_names: list[str] = field(default_factory=list)
    meshes: int = 0
    triangles: int = 0
    error: str = ""
    stdout: str = ""
    stderr: str = ""


def run_code(code: str, spec_dict: dict, out_glb: Path, *, timeout: float = 120.0) -> RunResult:
    """코드를 임시 디렉터리에 쓰고 `python -I -X utf8 -m m3d.agent.runner` 로 실행한다. 마지막 stdout 줄이 결과 JSON."""
    work = Path(tempfile.mkdtemp(prefix="m3d-agent-"))
    code_path, spec_path = work / "code.py", work / "spec.json"
    code_path.write_text(code, encoding="utf-8")
    spec_path.write_text(json.dumps(spec_dict), encoding="utf-8")
    out_glb = Path(out_glb)
    out_glb.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-I", "-X", "utf8", "-m", "m3d.agent.runner", str(code_path), str(spec_path), str(out_glb)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, cwd=str(work))
    except subprocess.TimeoutExpired as exc:
        return RunResult(ok=False, glb=None, error=f"시간 초과 {timeout:.0f}s", stdout=(exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
                         stderr=(exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "")
    last = next((ln for ln in reversed(proc.stdout.splitlines()) if ln.startswith("{")), None)
    if last is None:
        return RunResult(ok=False, glb=None, error="러너 결과 없음: " + proc.stderr[-1500:], stdout=proc.stdout[-2000:], stderr=proc.stderr[-2000:])
    res = json.loads(last)
    if not res.get("ok"):
        return RunResult(ok=False, glb=None, error=res.get("error", "?") + ("\n" + res.get("traceback", "") if res.get("traceback") else ""),
                         stdout=proc.stdout[-2000:], stderr=proc.stderr[-2000:])
    return RunResult(ok=True, glb=out_glb, node_names=res["nodes"], meshes=res["meshes"], triangles=res["triangles"],
                     stdout=proc.stdout[-2000:], stderr=proc.stderr[-2000:])
```

`worker/src/m3d/agent/runner.py`:
```python
"""샌드박스 진입점 (M5 D5) — 별도 프로세스에서 LLM 코드를 실행한다. 인자: code.py spec.json out.glb.

에이전트 코드에는 `ctx`(본체 기하 D2)·툴킷·제한된 builtins 만 보인다. Builder 는 ctx 를 만드는 데만 쓰고 노출하지 않는다.
결과는 stdout 마지막 줄 JSON({"ok": true, "nodes": [...], "meshes": n, "triangles": t} 또는 {"ok": false, "error": ..., "traceback": ...}).
"""

from __future__ import annotations

import builtins as _bi
import json
import re
import sys
import traceback
from pathlib import Path

import trimesh

from m3d.model import geom
from m3d.model.builder import COL_STEEL, INS, Builder
from m3d.model.spec import ModelSpec

NODE_RE = re.compile(r"^AB1_S5_[A-Z0-9_]+$")
_ALLOWED_ROOTS = {"math", "numpy", "trimesh"}
_real_import = _bi.__import__


def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name.split(".")[0] in _ALLOWED_ROOTS or name == "m3d.model.geom" or name.startswith("m3d.model.geom."):
        return _real_import(name, globals, locals, fromlist, level)
    raise ImportError(f"import 금지: {name}")


_SAFE_NAMES = ("abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter", "float", "int", "isinstance", "len",
               "list", "map", "max", "min", "pow", "print", "range", "reversed", "round", "set", "sorted", "str", "sum",
               "tuple", "zip", "Exception", "ValueError", "AssertionError", "KeyError", "IndexError", "True", "False", "None")
SAFE_BUILTINS = {k: getattr(_bi, k) for k in _SAFE_NAMES if hasattr(_bi, k)}
SAFE_BUILTINS["__import__"] = _guarded_import
SAFE_BUILTINS["__build_class__"] = _bi.__build_class__


class BoxContext:
    """에이전트에 노출하는 본체 기하 (D2) — Builder 의 프로파일 함수와 상수만."""

    def __init__(self, b: Builder):
        self.x_web = b.s.box.x_web
        self.z_p4, self.z_p5 = b.Z_P4, b.Z_P5
        self.y_web_top, self.y_web_bot, self.h_box, self.t_web = b.y_web_top, b.y_web_bot, b.h_box, b.t_web
        self.COL_STEEL = list(COL_STEEL)
        self.INS = INS
        self.geom = geom


def _validate(named) -> None:
    if not isinstance(named, dict) or not named:
        raise RuntimeError("반환값은 비어 있지 않은 dict[str, Trimesh] 여야 한다")
    problems = []
    for name, m in named.items():
        if not isinstance(name, str) or not NODE_RE.match(name):
            problems.append(f"노드명 규칙 위반: {name!r} (^AB1_S5_[A-Z0-9_]+$)")
            continue
        if not isinstance(m, trimesh.Trimesh):
            problems.append(f"{name}: Trimesh 아님 ({type(m).__name__})")
            continue
        if len(m.faces) == 0:
            problems.append(f"{name}: 면 없음")
        elif not m.is_watertight:
            problems.append(f"{name}: 수밀 아님(loft/extrude 로 닫힌 솔리드를 만들 것)")
        fc = getattr(m.visual, "face_colors", None)
        if fc is None or len(fc) != len(m.faces) or m.visual.kind != "face" and m.visual.kind != "vertex":
            problems.append(f"{name}: 버텍스 컬러 없음(geom.paint(mesh, ctx.COL_STEEL) 사용)")
    if problems:
        raise RuntimeError("; ".join(problems[:20]))


def main(argv: list[str]) -> None:
    code_path, spec_path, out_glb = (Path(a) for a in argv[1:4])
    spec = ModelSpec.model_validate(json.loads(spec_path.read_text(encoding="utf-8")))
    b = Builder(spec)
    ctx = BoxContext(b)
    g = {"__builtins__": SAFE_BUILTINS, "__name__": "agent_code"}
    exec(compile(code_path.read_text(encoding="utf-8"), "agent_code.py", "exec"), g)   # noqa: S102 — 샌드박스 진입점
    fn = g.get("build_section")
    if not callable(fn):
        raise RuntimeError("build_section 이 정의되지 않았다")
    named = fn(spec.model_dump(), ctx)
    _validate(named)
    b.export(named, out_glb)
    print(json.dumps({"ok": True, "nodes": sorted(named), "meshes": len(named),
                      "triangles": int(sum(len(m.faces) for m in named.values()))}))


if __name__ == "__main__":
    try:
        main(sys.argv)
    except BaseException as exc:      # noqa: BLE001 — 어떤 실패든 JSON 으로 보고
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()[-3000:]},
                         ensure_ascii=False))
        sys.exit(1)
```
주의: `m.visual.kind` 검사는 `trimesh` 가 색 없는 메시에 `visual.kind == None`·`face_colors` 를 기본 회색으로 채워 돌려주므로 `kind` 로 판단한다 — 테스트 3(`box_prism` 만 반환)이 "버텍스 컬러 없음" 을 내야 한다. 구현 후 실제 값으로 조건을 맞춘다(`m.visual.kind in ("face", "vertex")` 이면 통과).

- [ ] **Step 4: 통과 확인·커밋**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_agent_sandbox.py -q` → 6 passed (타임아웃 테스트 ~3s)
```bash
git add worker/src/m3d/agent/__init__.py worker/src/m3d/agent/schema.py worker/src/m3d/agent/sandbox.py worker/src/m3d/agent/runner.py worker/tests/test_agent_sandbox.py
git commit -m "feat(agent): 출력 스키마 + 샌드박스(AST 화이트리스트·별도 프로세스 러너·BoxContext)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: 프롬프트 묶음 — 판독 근거 크롭 + 규칙·툴킷·ctx·계약·스펙 발췌·피드백

**Files:**
- Create: `worker/src/m3d/agent/crops.py`, `worker/src/m3d/agent/context.py`, `worker/tests/test_agent_context.py`
- Modify: `worker/src/m3d/model/io.py` (`load_modelspec_raw`)

**Interfaces:**
- Consumes: `reading.sheet.list_pages/page_paper_mm`, `reading.crops.mm_bbox_to_px/render_crop`, `reading.inputs.resize_for_vision/image_block`, `docs/모델링규칙_지식베이스_v0.md`, `model.geom` 독스트링, `modelspec.json`(`spec`·`sources`).
- Produces: `crops.SECTION_PATTERNS = {"DIA": r"다이아프램|격벽|DIAP|개구|문턱|잭업|수직보강"}`, `crops.fetch_evidence(cfg, dataset, pattern) -> list[dict]`(`{ord, page_no, item, value, unit, status, mm_bbox}`), `crops.section_crops(cfg, dataset, evidence, out_dir, *, pages=None) -> list[dict]`(`{ord, page_no, path, items}`; 같은 시트·페이지는 bbox 합집합 1장, 최대 6장, 컨텍스트 120mm, 긴 변 ≤ 1400px);
  `context.kb_excerpt(text) -> str`, `context.toolkit_doc() -> str`, `context.spec_excerpt(spec_dict, sources) -> dict`, `context.section_bundle(section_key, *, spec_dict, sources, evidence, crops, feedback=None, request="", prev_code=None) -> {"system", "messages", "digest", "n_images"}`;
  `model_io.load_modelspec_raw(cfg, dataset) -> dict`(`{"spec","sources","stats"}`).

- [ ] **Step 1: 실패 테스트**

`worker/tests/test_agent_context.py`:
```python
"""프롬프트 묶음 — 규칙·툴킷·ctx·계약·스펙 발췌(출처)·크롭·피드백·요청 (M5 D3). LLM 호출 없음."""

import json

from PIL import Image

from m3d.agent import context as C
from m3d.agent import crops as K
from m3d.model.spec import ModelSpec
from m3d.reading.sheet import PageRef

SOURCES = {"coord.z_p4": "ssot:project.coord_system.datums", "diaphragm.spacing": "ssot:C01/다이아프램 간격",
           "diaphragm.support_t": "default:SPEC_v2 §2", "box.h_pier": "ssot:C01/측면도 전체 형고 4,000"}


def _page(tmp_path, ord_, w=2000, h=1400):
    png = tmp_path / "png" / f"{ord_}_D-1_p1.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), "white").save(png)
    text = tmp_path / "text" / f"{ord_}_D-1_p1.json"
    text.parent.mkdir(parents=True, exist_ok=True)
    text.write_text(json.dumps({"paper_mm": [1189.0, 841.0], "rows": []}), encoding="utf-8")
    return PageRef(ord=ord_, drawing_no="D-1", page_no=1, region=ord_[0], png=png, text=text)


def test_section_crops_groups_by_page_and_limits(tmp_path):
    pages = {("C13", 1): _page(tmp_path, "C13"), ("C16", 1): _page(tmp_path, "C16")}
    ev = [{"ord": "C13", "page_no": 1, "item": "CL 다이아프램 규격", "value": "DIAP 10x4500x3739", "unit": "mm", "status": "확정", "mm_bbox": [100, 100, 160, 120]},
          {"ord": "C13", "page_no": 1, "item": "CU3 다이아프램 판 규격", "value": "DIAP 10x4500x2400", "unit": "mm", "status": "확정", "mm_bbox": [400, 300, 460, 320]},
          {"ord": "C16", "page_no": 1, "item": "CL7", "value": "DIAP 10x4500x2881", "unit": "mm", "status": "확정", "mm_bbox": [10, 10, 30, 20]},
          {"ord": "C99", "page_no": 1, "item": "없는 시트", "value": "x", "unit": None, "status": "추정", "mm_bbox": [0, 0, 1, 1]},
          {"ord": "C16", "page_no": 1, "item": "용지 밖", "value": "x", "unit": None, "status": "추정", "mm_bbox": [5000, 5000, 5001, 5001]}]
    out = K.section_crops(None, "ds", ev, tmp_path / "crops", pages=pages)
    assert [(c["ord"], c["page_no"]) for c in out] == [("C13", 1), ("C16", 1)]
    assert len(out[0]["items"]) == 2 and out[0]["path"].is_file()
    with Image.open(out[0]["path"]) as im:
        assert max(im.size) <= K.LONG_SIDE and min(im.size) >= 400          # 합집합 + 120mm 여백, 축소 상한
    many = [dict(ev[0], ord=f"C{10 + i}") for i in range(8)]
    pages8 = {(f"C{10 + i}", 1): _page(tmp_path, f"C{10 + i}") for i in range(8)}
    assert len(K.section_crops(None, "ds", many, tmp_path / "crops8", pages=pages8)) == K.MAX_IMAGES


def test_kb_excerpt_keeps_only_rule_sections():
    text = "# KB\n\n## 1. 좌표\n- a\n\n## 3. 판독\n- b\n\n## 5. 모델링 규칙\n- c\n\n## 6. 검증\n- d\n"
    ex = C.kb_excerpt(text)
    assert "## 1. 좌표" in ex and "## 5. 모델링 규칙" in ex and "- c" in ex
    assert "## 3. 판독" not in ex and "- d" not in ex


def test_toolkit_doc_lists_geom_functions_with_signatures():
    doc = C.toolkit_doc()
    for fn in ("loft(", "extrude(", "rect(", "box_prism(", "mirror_poly(", "mirror_mesh(", "paint(", "zone_loft("):
        assert fn in doc
    assert "ear_clip" not in doc                        # 내부 함수 제외


def test_spec_excerpt_marks_sources_and_limits_fields():
    ex = C.spec_excerpt(ModelSpec().model_dump(), SOURCES)
    assert set(ex) == {"coord", "box", "diaphragm", "bearing"}
    assert ex["diaphragm"]["spacing"] == {"value": 2.8, "source": "ssot:C01/다이아프램 간격"}
    assert ex["diaphragm"]["support_t"]["source"].startswith("default:")
    assert ex["bearing"] == {"x": {"value": 1.55, "source": "default"}}


def test_section_bundle_composes_system_and_user_with_feedback(tmp_path):
    img = tmp_path / "c.png"
    Image.new("RGB", (600, 400), "white").save(img)
    crops = [{"ord": "C13", "page_no": 1, "path": img, "items": [{"item": "CL 다이아프램 규격", "value": "DIAP 10x4500x3739", "status": "확정"}]}]
    b = C.section_bundle("P4P5/DIA", spec_dict=ModelSpec().model_dump(), sources=SOURCES, evidence=[], crops=crops,
                         feedback="only_ref: AB1_S5_DIA26", request="개구를 1.4×1.4 로", prev_code="def build_section(spec, ctx):\n    return {}")
    assert "build_section(spec, ctx)" in b["system"] and "AB1_S5_DIA01" in b["system"] and "전역 체인" in b["system"]
    assert "geom.paint" in b["system"] and "y_web_top(z)" in b["system"]
    parts = b["messages"][0]["content"]
    kinds = [p["type"] for p in parts]
    assert kinds.count("image") == 1 and b["n_images"] == 1
    text = "\n".join(p["text"] for p in parts if p["type"] == "text")
    assert '"source": "ssot:C01/다이아프램 간격"' in text and "참조 차용" in text
    assert "이전 시도" in text and "only_ref: AB1_S5_DIA26" in text and "개구를 1.4×1.4 로" in text
    assert len(b["digest"]) == 64
    b2 = C.section_bundle("P4P5/DIA", spec_dict=ModelSpec().model_dump(), sources=SOURCES, evidence=[], crops=crops)
    assert b2["digest"] != b["digest"] and "이전 시도" not in "\n".join(p["text"] for p in b2["messages"][0]["content"] if p["type"] == "text")
```

- [ ] **Step 2: 실패 확인**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_agent_context.py -q` → FAIL(모듈 없음)

- [ ] **Step 3: 구현**

`worker/src/m3d/model/io.py` 끝에:
```python
def load_modelspec_raw(cfg: Config, dataset: str) -> dict:
    """modelspec.json 원문({"spec","sources","stats"}) — 에이전트 프롬프트가 출처를 같이 쓴다."""
    path = model_dir(cfg, dataset) / "modelspec.json"
    if not path.is_file():
        raise RuntimeError(f"modelspec.json 없음 — `m3d modelspec {dataset}` 먼저")
    return json.loads(path.read_text(encoding="utf-8"))
```

`worker/src/m3d/agent/crops.py`:
```python
"""섹션 판독 근거 크롭 (M5 D3) — readings 의 basis 시트·mm_bbox 로 도면 크롭을 만든다(무과금).

M2a 판독이 남긴 근거 좌표를 재사용한다: 같은 시트·페이지의 근거는 bbox 합집합으로 1장, 여백 120mm, 최대 6장.
"""

from __future__ import annotations

from pathlib import Path

import psycopg
from PIL import Image

from m3d.config import Config
from m3d.reading.crops import mm_bbox_to_px, render_crop
from m3d.reading.inputs import resize_for_vision
from m3d.reading.sheet import PageRef, list_pages, page_paper_mm

Image.MAX_IMAGE_PIXELS = None

SECTION_PATTERNS = {"DIA": r"다이아프램|격벽|DIAP|개구|문턱|잭업|수직보강"}
CONTEXT_MM = 120.0
MAX_IMAGES = 6
LONG_SIDE = 1400


def fetch_evidence(cfg: Config, dataset: str, pattern: str) -> list[dict]:
    """섹션 키워드에 맞는 판독 행(근거 시트·페이지·mm_bbox 포함)."""
    with psycopg.connect(cfg.require_db_url()) as conn, conn.cursor() as cur:
        cur.execute(
            "select s.ord, coalesce(p.page_no, 1), r.item, r.value_raw, r.unit, r.status, r.basis_mm_bbox "
            "from readings r join projects pj on pj.id = r.project_id join sheets s on s.id = r.basis_sheet_id "
            "left join sheet_pages p on p.id = r.basis_page_id "
            "where pj.slug = %s and r.item ~* %s order by s.ord, p.page_no, r.item", (dataset, pattern))
        return [{"ord": o, "page_no": int(pn), "item": it, "value": v, "unit": u, "status": st, "mm_bbox": bb}
                for (o, pn, it, v, u, st, bb) in cur.fetchall()]


def section_crops(cfg: Config | None, dataset: str, evidence: list[dict], out_dir: Path, *,
                  pages: dict[tuple[str, int], PageRef] | None = None) -> list[dict]:
    """근거 → 크롭 PNG 목록. pages 를 주면(테스트) DB·파일 탐색 없이 그 페이지를 쓴다."""
    if pages is None:
        pages = {(p.ord, p.page_no): p for p in list_pages(cfg, dataset)}
    groups: dict[tuple[str, int], list[dict]] = {}
    for ev in evidence:
        groups.setdefault((ev["ord"], int(ev["page_no"] or 1)), []).append(ev)
    out: list[dict] = []
    out_dir = Path(out_dir)
    for (ord_, pno), evs in groups.items():
        page = pages.get((ord_, pno))
        if page is None:
            continue
        paper = page_paper_mm(cfg, dataset, page) if cfg is not None else _paper_from_text(page)
        with Image.open(page.png) as im:
            size = im.size
        boxes = [e["mm_bbox"] for e in evs if isinstance(e.get("mm_bbox"), (list, tuple)) and len(e["mm_bbox"]) == 4]
        boxes = [b for b in boxes if 0 <= min(b[0], b[2]) and max(b[0], b[2]) <= paper[0] and 0 <= min(b[1], b[3]) and max(b[1], b[3]) <= paper[1]]
        if not boxes:
            continue
        union = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
        try:
            px = mm_bbox_to_px(union, paper, size, context_mm=CONTEXT_MM)
            path = out_dir / f"{ord_}_p{pno}.png"
            render_crop(page.png, px, path)
        except ValueError:
            continue
        resize_for_vision(path, path, long_side=LONG_SIDE)
        out.append({"ord": ord_, "page_no": pno, "path": path,
                    "items": [{"item": e["item"], "value": e.get("value"), "unit": e.get("unit"), "status": e.get("status")} for e in evs]})
        if len(out) >= MAX_IMAGES:
            break
    return out


def _paper_from_text(page: PageRef) -> tuple[float, float]:
    import json
    w, h = json.loads(page.text.read_text(encoding="utf-8"))["paper_mm"]
    return float(w), float(h)
```
(`page_paper_mm(cfg, dataset, page)` 는 cfg 를 쓰지 않고 `page.text` 만 읽는다 — 그래도 시그니처를 지키기 위해 cfg=None 분기를 둔다.)

`worker/src/m3d/agent/context.py`:
```python
"""에이전트 입력 묶음 (M5 D3) — 규칙(KB §1·§2·§5)·툴킷 문서·ctx·코드 계약·스펙 발췌(출처)·크롭·판독값·피드백·요청."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

from m3d.config import REPO_ROOT
from m3d.model import geom
from m3d.reading.inputs import image_block
from m3d.samples.manifest import sha256_file

KB_PATH = REPO_ROOT / "docs" / "모델링규칙_지식베이스_v0.md"
KB_KEEP = ("## 1. ", "## 2. ", "## 5. ")
TOOLKIT_FUNCS = ("loft", "extrude", "rect", "box_prism", "mirror_poly", "mirror_mesh", "paint", "zone_loft")
SPEC_SECTIONS = ("coord", "box", "diaphragm")

ROLE = ("당신은 강상자형교 3D 모델링 에이전트다. 주어진 치수 정본(ModelSpec 발췌)·도면 크롭·규칙만으로 한 섹션(부재 그룹)의 "
        "파이썬 빌더 함수를 작성한다. 추정으로 확정하지 말고 가정은 assumptions 에, 확인이 필요한 것은 questions 에 낸다.")

CTX_DOC = """## ctx (본체 기하 — 주어진 조건)
- ctx.x_web: 웹 외면 x(m, +측). 웹은 x=±x_web 에 있고 두께 ctx.t_web(z) 만큼 안쪽으로 들어온다.
- ctx.z_p4, ctx.z_p5: P4·P5 받침선 z(m). 격벽·프레임 같은 반복 부재의 위치는 전역 체인 z = z_p4 + k·간격 에서 유도한다.
- ctx.y_web_top(z), ctx.y_web_bot(z): 상판 하면 y / 하판 상면 y (내공 경계, m). ctx.h_box(z) = 내공 높이.
- ctx.t_web(z): 웹 판두께(m). ctx.COL_STEEL: 강재 색 [r,g,b,a]. ctx.INS: 접합부 관통 삽입 5mm.
- ctx.geom: 아래 툴킷 모듈(직접 import 해도 된다: from m3d.model.geom import ...)."""

CODE_CONTRACT = """## 코드 계약
- 최상위에 `def build_section(spec, ctx) -> dict[str, trimesh.Trimesh]` 를 정의한다. spec 은 ModelSpec 전체 dict(m 단위), ctx 는 위 본체 기하.
- 노드명은 `AB1_S5_<그룹><번호>` 규칙(격벽: AB1_S5_DIA01 … AB1_S5_DIA26, 받침선 P4 쪽이 01). 노드명 = 객체 DB 연결 키.
- 모든 메시는 수밀(loft/extrude/box_prism 결과)이고 `geom.paint(mesh, ctx.COL_STEEL)` 로 색을 입힌다. 접합부는 ctx.INS 만큼 관통 삽입한다(공면 금지).
- 허용 import: math, numpy, trimesh, m3d.model.geom. 파일·네트워크·다른 모듈 접근 금지. 단위 m, Y-up, 좌표계는 §1 규약.
- 판두께 방향·개구·보강재 배치처럼 도면에서 확인한 값은 코드 주석에 근거(시트·값)를 적는다."""

OUTPUT_FORMAT = """## 출력
JSON: {"code": "<파이썬 코드 전체>", "assumptions": ["…"], "questions": ["…"]}. code 외 설명은 assumptions/questions 에만."""


def kb_excerpt(text: str) -> str:
    """'## n. ' 절 중 KB_KEEP 로 시작하는 절만 남긴다(다음 '## ' 까지)."""
    out, keep = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            keep = line.startswith(KB_KEEP)
        if keep:
            out.append(line)
    return "\n".join(out).strip()


def toolkit_doc() -> str:
    lines = ["## 툴킷 m3d.model.geom (Poly = [(x,y),...] CCW; z 로프트/압출은 Trimesh 솔리드를 돌려준다)"]
    for name in TOOLKIT_FUNCS:
        fn = getattr(geom, name)
        doc = (inspect.getdoc(fn) or "").splitlines()[0] if inspect.getdoc(fn) else ""
        lines.append(f"- {name}{inspect.signature(fn)} — {doc}")
    return "\n".join(lines)


def spec_excerpt(spec_dict: dict, sources: dict) -> dict:
    out = {}
    for sec in SPEC_SECTIONS:
        out[sec] = {k: {"value": v, "source": sources.get(f"{sec}.{k}", "default")} for k, v in spec_dict[sec].items()}
    out["bearing"] = {"x": {"value": spec_dict["bearing"]["x"], "source": sources.get("bearing.x", "default")}}
    return out


def section_bundle(section_key: str, *, spec_dict: dict, sources: dict, evidence: list[dict], crops: list[dict],
                   feedback: str | None = None, request: str = "", prev_code: str | None = None) -> dict:
    segment, code = section_key.split("/")
    kb = kb_excerpt(KB_PATH.read_text(encoding="utf-8")) if KB_PATH.is_file() else ""
    system = "\n\n".join([ROLE, "## 모델링 규칙(지식베이스 발췌)", kb, toolkit_doc(), CTX_DOC, CODE_CONTRACT, OUTPUT_FORMAT])
    ex = spec_excerpt(spec_dict, sources)
    parts: list[dict] = [
        {"type": "text", "text": f"섹션 {section_key} (구간 {segment}, 부재그룹 {code}). 이 섹션의 모든 노드를 만드는 build_section 을 작성하라."},
        {"type": "text", "text": "ModelSpec 발췌 (m 단위; source 가 ssot: 이면 판독 확정값, default 는 참조 차용 — 도면으로 확인할 것):\n"
                                 + json.dumps(ex, ensure_ascii=False)},
    ]
    if evidence:
        rows = [f"- [{e['ord']} p{e['page_no']}] {e['item']} = {e.get('value')} {e.get('unit') or ''} ({e.get('status')})" for e in evidence]
        parts.append({"type": "text", "text": "판독값(근거 시트·상태):\n" + "\n".join(rows)})
    for c in crops:
        cap = ", ".join(f"{it['item']} = {it.get('value')}" for it in c["items"][:6])
        parts.append({"type": "text", "text": f"도면 크롭 {c['ord']} p{c['page_no']} — {cap}"})
        parts.append(image_block(Path(c["path"])))
    if prev_code:
        parts.append({"type": "text", "text": "이전 시도 코드:\n```python\n" + prev_code[-12000:] + "\n```"})
    if feedback:
        parts.append({"type": "text", "text": "이전 시도의 실행 오류·채점(고쳐야 할 것):\n" + feedback[-6000:]})
    if request:
        parts.append({"type": "text", "text": "사용자 요청: " + request})
    h = hashlib.sha256(system.encode("utf-8"))
    for p in parts:
        h.update((p["text"] if p["type"] == "text" else "img").encode("utf-8"))
    for c in crops:
        h.update(sha256_file(Path(c["path"])).encode("ascii"))
    return {"system": system, "messages": [{"role": "user", "content": parts}], "digest": h.hexdigest(), "n_images": len(crops)}
```

- [ ] **Step 4: 통과 확인·커밋**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_agent_context.py -q` → 5 passed
실데이터 확인(무과금): heredoc 파이썬으로 `fetch_evidence(cfg, "ab1-p4p5", SECTION_PATTERNS["DIA"])` → 12행, `section_crops(...)` → 크롭 수·크기 출력, 크롭 1장 `Read` 로 육안(격벽 규격 표가 보이는지).
```bash
git add worker/src/m3d/agent/crops.py worker/src/m3d/agent/context.py worker/src/m3d/model/io.py worker/tests/test_agent_context.py
git commit -m "feat(agent): 판독 근거 크롭 + 프롬프트 묶음(규칙·툴킷·ctx·계약·스펙 발췌·피드백)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: 채점(정답 대조·섹션/결합 self-check·재실측·피드백) + publish 일반화

**Files:**
- Create: `worker/src/m3d/agent/score.py`, `worker/tests/test_agent_score.py`
- Modify: `worker/src/m3d/model/publish.py`, `worker/tests/test_model_publish.py`

**Interfaces:**
- Consumes: `model.compare.compare_glb`, `model.selfcheck.run(named, b, section=)`, `model.measure.run`, `model.sections.CODES`, `model.render.load_nodes`.
- Produces: `score.load_named(glb) -> dict[name, Trimesh]`, `score.score_section(code, agent_glb, spec, ref_dir, *, work_dir) -> dict`(`{"pass", "compare": {...}, "section_selfcheck": {pass, fail, failed:[label — detail]}, "assembled_selfcheck": {...}, "measure": {PASS, FAIL, INFO, failed:[항목]}, "assembled_glb": str}`), `score.summary(score, attempts) -> AgentScoreSummary dict`, `score.feedback_text(score) -> str`;
  `publish.run_publish_model(cfg, dataset, *, pilot=False, force=False, out_dir=None, kind=None)` — `out_dir` 가 있으면 그 디렉터리, `kind` 가 있으면 build.json 의 kind 대신; `collect_files` 가 `agent/*`(`code.py, attempts.json, score.json, prompt.md`) 포함, `files["agent"]` 키, `build_stats` 가 `agent/score.json` 있으면 `stats["agent"]`, `build_sections` insert 에 `source` 컬럼(`s.get("source", "builder")`). CONTENT_TYPES 에 `.py: text/x-python`, `.md: text/markdown`.

- [ ] **Step 1: 실패 테스트**

`worker/tests/test_agent_score.py`:
```python
"""채점 — 정답 섹션이면 pass, 노드가 빠지거나 어긋나면 fail + 피드백 (M5 D6)."""

import json

import pytest

from m3d.agent import score as S
from m3d.model import sections as X
from m3d.model.builder import Builder
from m3d.model.spec import ModelSpec


@pytest.fixture(scope="module")
def ref_dir(tmp_path_factory):
    """정답 빌드 디렉터리(섹션 10 GLB) — 실제 빌더로 한 번만 만든다."""
    d = tmp_path_factory.mktemp("ref")
    spec = ModelSpec()
    b = Builder(spec)
    secs = X.split(b.build(pilot=False), spec.coord.segment)
    b.export_sections(secs, d)
    return d


def test_reference_section_scores_pass(ref_dir, tmp_path):
    spec = ModelSpec()
    sc = S.score_section("DIA", ref_dir / "sections" / "P4P5" / "DIA.glb", spec, ref_dir, work_dir=tmp_path)
    assert sc["pass"] is True
    assert sc["compare"]["only_ours"] == [] and sc["compare"]["only_ref"] == [] and sc["compare"]["bbox_dev_max_m"] == 0.0
    assert sc["section_selfcheck"]["fail"] == 0 and sc["assembled_selfcheck"]["fail"] == 0 and sc["measure"]["FAIL"] == 0
    assert (tmp_path / "assembled.glb").is_file()
    summ = S.summary(sc, attempts=1)
    assert summ == {"pass": True, "only_ours": 0, "only_ref": 0, "bbox_dev_max_m": 0.0, "section_fail": 0,
                    "assembled_fail": 0, "measure_fail": 0, "attempts": 1}


def test_missing_and_shifted_nodes_fail_with_feedback(ref_dir, tmp_path):
    spec = ModelSpec()
    named = S.load_named(ref_dir / "sections" / "P4P5" / "DIA.glb")
    named.pop("AB1_S5_DIA26")
    named["AB1_S5_DIA03"].apply_translation([0, 0, 0.02])            # 20mm 밀림
    b = Builder(spec)
    glb = tmp_path / "agent.glb"
    b.export(named, glb)
    sc = S.score_section("DIA", glb, spec, ref_dir, work_dir=tmp_path)
    assert sc["pass"] is False
    assert sc["compare"]["only_ref"] == ["AB1_S5_DIA26"] and sc["compare"]["bbox_dev_max_m"] > 0.005
    assert sc["section_selfcheck"]["fail"] >= 1                     # 격벽 26 개수·체인
    fb = S.feedback_text(sc)
    assert "AB1_S5_DIA26" in fb and "AB1_S5_DIA03" in fb and "20" in fb
    json.dumps(sc)                                                    # 직렬화 가능(JSON 저장용)
```

`worker/tests/test_model_publish.py` 에 추가:
```python


def test_publish_agent_dir_with_kind_and_sources(cfg, monkeypatch):
    d = _model_dir(cfg)
    build = json.loads((d / "build.json").read_text(encoding="utf-8"))
    build["sections"][1]["source"] = "agent"
    (d / "build.json").write_text(json.dumps(build), encoding="utf-8")
    (d / "agent").mkdir()
    (d / "agent" / "code.py").write_text("def build_section(spec, ctx):\n    return {}\n", encoding="utf-8")
    (d / "agent" / "score.json").write_text(json.dumps({"pass": True, "only_ours": 0, "only_ref": 0, "bbox_dev_max_m": 0.0,
                                                        "section_fail": 0, "assembled_fail": 0, "measure_fail": 0, "attempts": 2}), encoding="utf-8")
    db = FakeDb()
    calls = _patch(monkeypatch, db)
    r = P.run_publish_model(cfg, "ds", out_dir=d, kind="agent", force=True)
    assert r["version"] == 1 and r["files"] == 13
    b_params = [p for s, p in db.sql if s.startswith("insert into builds")][0]
    assert b_params[2] == "agent" and b_params[6].obj["agent"] == ["ds/b1/agent/code.py", "ds/b1/agent/score.json"]
    assert b_params[7].obj["agent"]["pass"] is True
    s_sql, s_params = [(s, p) for s, p in db.sql if s.startswith("insert into build_sections")][1]
    assert "source" in s_sql and s_params[-1] == "agent"
    assert any(h["Content-Type"] == "text/x-python" for (_u, h, _d) in calls)
```

- [ ] **Step 2: 실패 확인**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_agent_score.py worker/tests/test_model_publish.py -q` → FAIL(모듈 없음 / 인자 없음)

- [ ] **Step 3: 구현**

`worker/src/m3d/agent/score.py`:
```python
"""채점 (M5 D6) — 정답 섹션 대조 + 섹션 self-check + 레고식 결합(정답 9 + 에이전트 1) self-check·재실측."""

from __future__ import annotations

from pathlib import Path

import trimesh

from m3d.model import compare, measure, sections, selfcheck
from m3d.model.builder import Builder
from m3d.model.render import load_nodes
from m3d.model.spec import ModelSpec

BBOX_TOL_M = 0.005


def load_named(glb: Path) -> dict[str, trimesh.Trimesh]:
    return {name: m for name, m, _c in load_nodes(Path(glb))}


def score_section(code: str, agent_glb: Path, spec: ModelSpec, ref_dir: Path, *, work_dir: Path) -> dict:
    segment = spec.coord.segment
    ref_glb = Path(ref_dir) / "sections" / segment / f"{code}.glb"
    cmp = compare.compare_glb(Path(agent_glb), ref_glb)
    b = Builder(spec)
    agent_named = load_named(agent_glb)
    sec = selfcheck.run(agent_named, b, section=code)
    named: dict[str, trimesh.Trimesh] = {}
    for c in sections.CODES:
        named.update(agent_named if c == code else load_named(Path(ref_dir) / "sections" / segment / f"{c}.glb"))
    full = selfcheck.run(named, b, pilot=False)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    assembled = work_dir / "assembled.glb"
    b.export(named, assembled)
    meas = measure.run(assembled, spec)
    failed_meas = [c["항목"] for c in meas["대조"] if c["판정"] == "FAIL"]
    dev = cmp["bbox_dev_max_m"]
    passed = (not cmp["only_ours"] and not cmp["only_ref"] and dev is not None and dev <= BBOX_TOL_M
              and sec["fail"] == 0 and full["fail"] == 0 and not failed_meas)
    return {
        "pass": bool(passed),
        "compare": {k: cmp[k] for k in ("only_ours", "only_ref", "common", "bbox_dev_max_m", "bbox_dev_over_1mm", "faces_equal", "worst")},
        "section_selfcheck": _sc(sec), "assembled_selfcheck": _sc(full),
        "measure": {"PASS": meas["집계"]["PASS"], "FAIL": meas["집계"]["FAIL"], "INFO": meas["집계"]["INFO"], "failed": failed_meas},
        "assembled_glb": str(assembled),
    }


def _sc(r: dict) -> dict:
    return {"pass": r["pass"], "fail": r["fail"], "failed": [f"{c['label']} — {c['detail']}" for c in r["checks"] if c["ok"] is False]}


def summary(score: dict, attempts: int) -> dict:
    return {"pass": score["pass"], "only_ours": len(score["compare"]["only_ours"]), "only_ref": len(score["compare"]["only_ref"]),
            "bbox_dev_max_m": score["compare"]["bbox_dev_max_m"], "section_fail": score["section_selfcheck"]["fail"],
            "assembled_fail": score["assembled_selfcheck"]["fail"], "measure_fail": score["measure"]["FAIL"], "attempts": attempts}


def feedback_text(score: dict) -> str:
    """다음 시도 프롬프트용 — 무엇이 어긋났는지 노드명·mm 로."""
    c = score["compare"]
    lines = ["채점: " + ("PASS" if score["pass"] else "FAIL")]
    if c["only_ref"]:
        lines.append("빠진 노드(정답에는 있음): " + ", ".join(c["only_ref"][:30]))
    if c["only_ours"]:
        lines.append("남는 노드(정답에 없음): " + ", ".join(c["only_ours"][:30]))
    if c["worst"]:
        lines.append("정답 대비 bbox 편차 상위: " + ", ".join(f"{w['node']} {w['dev_m'] * 1000:.0f}mm" for w in c["worst"][:8] if w["dev_m"] > BBOX_TOL_M))
    for key, label in (("section_selfcheck", "섹션 self-check 실패"), ("assembled_selfcheck", "결합 self-check 실패")):
        if score[key]["failed"]:
            lines.append(label + ": " + " | ".join(score[key]["failed"][:8]))
    if score["measure"]["failed"]:
        lines.append("재실측 실패 항목: " + " | ".join(score["measure"]["failed"][:8]))
    return "\n".join(lines)
```

`worker/src/m3d/model/publish.py` 수정:
- `CONTENT_TYPES` 에 `".py": "text/x-python", ".md": "text/markdown"`.
- `collect_files`: 선택 JSON 뒤에 `files += sorted(p.relative_to(out_dir).as_posix() for p in (out_dir / "agent").glob("*") if p.is_file() and p.suffix in (".py", ".json", ".md"))` (디렉터리 있을 때).
- `build_stats`: 끝에 `if (out_dir / "agent" / "score.json").is_file(): stats["agent"] = _load(out_dir, "agent/score.json")`; 없으면 `stats["agent"] = None`.
- `run_publish_model(cfg, dataset, *, pilot=False, force=False, out_dir=None, kind=None)`: `out_dir = Path(out_dir) if out_dir else model_io.model_dir(cfg, dataset, pilot=pilot)`; `kind_v = kind or build["kind"]`; `file_index["agent"] = [keyed[r] for r in files if r.startswith("agent/")]`; builds insert 에 `kind_v`; build_sections insert 컬럼에 `source` 추가(값 `s.get("source", "builder")`, 파라미터 맨 끝).
- 테스트의 `b_params[6].obj` 는 `psycopg.types.json.Jsonb` 의 `.obj` 속성이다.

- [ ] **Step 4: 통과 확인·커밋**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_agent_score.py worker/tests/test_model_publish.py -q` → PASS (score 테스트는 빌드·재실측 포함 ~1분)
```bash
git add worker/src/m3d/agent/score.py worker/src/m3d/model/publish.py worker/tests/test_agent_score.py worker/tests/test_model_publish.py
git commit -m "feat(agent): 채점(정답 대조·섹션/결합 self-check·재실측·피드백) + publish out_dir/kind/source·agent 파일" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: 잡 실행 루프(시도 ≤4·예산·산출 디렉터리·publish) + 워커 데몬 `m3d worker`

**Files:**
- Create: `worker/src/m3d/agent/loop.py`, `worker/src/m3d/agent/worker.py`, `worker/tests/test_agent_loop.py`, `worker/tests/test_agent_worker.py`
- Modify: `worker/src/m3d/cli.py` (`worker` 명령)

**Interfaces:**
- Consumes: `context.section_bundle`, `crops.fetch_evidence/section_crops/SECTION_PATTERNS`, `sandbox.run_code`, `score.score_section/summary/feedback_text`, `publish.run_publish_model(out_dir=, kind=, force=True)`, `render.run_render`, `measure.run`, `selfcheck.run`, `client.build_client/call_structured/MODEL_READ`, `schema.AgentOut/validate_agent_out`, `io.load_modelspec_raw`.
- Produces: `loop.MAX_ATTEMPTS=4`, `loop.EST_CALL_USD=0.15`, `loop.STAGE="model-agent"`, `loop.spent_usd(cfg, dataset, stage=STAGE) -> float`, `loop.real_llm(cfg, dataset, bundle, extra) -> (AgentOut, usage)`,
  `loop.run_job(cfg, dataset, job, emit, *, llm=None, scorer=None, publisher=None, evidence=None, crops=None, ref_dir=None, do_render=True) -> dict`
  (job = `{"id", "section_key", "request", "parent_job_id", "budget_usd"}`; 결과 `{"pass", "reason"?, "attempts", "cost_usd", "build_version"?, "build_id"?, "assumptions", "questions", "score"?}`; reason ∈ `unsupported_section|no_reference|budget|no_run`);
  `worker.claim(conn) -> dict|None`, `worker.emit_event(conn, job_id, level, message)`, `worker.finish(conn, job_id, *, status, result, build_id, cost_usd, attempts)`, `worker.run_once(cfg, *, run_job_fn=None) -> bool`, `worker.serve(cfg, *, poll=2.0, once=False)`; CLI `m3d worker [--once] [--poll 2.0]` 콘솔 `worker job=<id> section=<key> attempts=N pass=<bool> cost=$x.xx build=bN|-`.

- [ ] **Step 1: 실패 테스트**

`worker/tests/test_agent_loop.py`:
```python
"""잡 루프 — 가짜 LLM/채점/업로드로 시도·피드백·예산·산출 디렉터리를 검증한다 (M5 D7·D8·D9). 실호출 없음."""

import dataclasses
import json
import textwrap

import pytest

from m3d.agent import loop as L
from m3d.agent.schema import AgentOut
from m3d.config import load_config
from m3d.model import sections as X
from m3d.model.builder import Builder
from m3d.model.spec import ModelSpec

GOOD = textwrap.dedent('''
    from m3d.model.geom import box_prism, paint
    def build_section(spec, ctx):
        d = spec["diaphragm"]
        out = {}
        for k in range(d["n_cell"] + 1):
            zc = min(max(ctx.z_p4 + k * d["spacing"], ctx.z_p4 + 0.02), ctx.z_p5 - 0.02)
            out["AB1_S5_DIA%02d" % (k + 1)] = paint(box_prism(-2.0, 2.0, ctx.y_web_bot(zc), ctx.y_web_top(zc), zc - 0.005, zc + 0.005), ctx.COL_STEEL)
        return out
''')
BAD = "def build_section(spec, ctx):\n    return 1 / 0\n"


@pytest.fixture(scope="module")
def ref_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("ref")
    spec = ModelSpec()
    b = Builder(spec)
    b.export_sections(X.split(b.build(pilot=False), spec.coord.segment), d)
    (d / "modelspec.json").write_text(json.dumps({"spec": spec.model_dump(), "sources": {}, "stats": {}}), encoding="utf-8")
    return d


@pytest.fixture
def cfg(tmp_path, monkeypatch, ref_dir):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    c = dataclasses.replace(load_config(env_file=tmp_path / "absent.env"), repo_root=tmp_path)
    model = c.derived_dir / "ds" / "model"
    model.mkdir(parents=True)
    (model / "modelspec.json").write_text((ref_dir / "modelspec.json").read_text(encoding="utf-8"), encoding="utf-8")
    return c


def _job(**over):
    return {"id": "job-1", "section_key": "P4P5/DIA", "request": "", "parent_job_id": None, "budget_usd": 5.0, **over}


def _fake_llm(codes):
    calls = []

    def llm(cfg, dataset, bundle, extra):
        calls.append({"attempt": extra["attempt"], "n_images": bundle["n_images"],
                      "text": "\n".join(p["text"] for p in bundle["messages"][0]["content"] if p["type"] == "text")})
        return AgentOut(code=codes[len(calls) - 1], assumptions=["가정1"], questions=["질문1"]), {"cost_usd": 0.1}
    return llm, calls


def _fake_scorer(passes):
    seen = []

    def scorer(code, glb, spec, ref, *, work_dir):
        seen.append(glb)
        ok = passes[len(seen) - 1]
        return {"pass": ok, "compare": {"only_ours": [], "only_ref": [] if ok else ["AB1_S5_DIA26"], "common": 25, "bbox_dev_max_m": 0.0 if ok else 0.02,
                                        "bbox_dev_over_1mm": 0, "faces_equal": ok, "worst": []},
                "section_selfcheck": {"pass": 5, "fail": 0, "failed": []}, "assembled_selfcheck": {"pass": 24, "fail": 0, "failed": []},
                "measure": {"PASS": 47, "FAIL": 0, "INFO": 2, "failed": []}, "assembled_glb": str(work_dir / "assembled.glb")}
    return scorer, seen


def _fake_publisher(record):
    def publisher(cfg, dataset, *, out_dir, kind, force):
        record.update({"out_dir": out_dir, "kind": kind, "force": force})
        return {"version": 7, "build_id": "b-7", "files": 20, "uploaded": 20, "skipped": False, "failures": []}
    return publisher


def test_loop_retries_with_feedback_then_passes_and_builds_agent_dir(cfg, ref_dir, monkeypatch):
    llm, calls = _fake_llm([BAD, GOOD, GOOD])
    scorer, seen = _fake_scorer([False, True])
    pub = {}
    events = []
    monkeypatch.setattr(L, "spent_usd", lambda cfg, ds, stage=L.STAGE: 0.0)
    r = L.run_job(cfg, "ds", _job(), lambda lv, m: events.append((lv, m)), llm=llm, scorer=scorer, publisher=_fake_publisher(pub),
                  evidence=[], crops=[], ref_dir=ref_dir, do_render=False)
    assert r["pass"] is True and r["attempts"] == 3 and r["build_version"] == 7 and r["build_id"] == "b-7"
    assert abs(r["cost_usd"] - 0.3) < 1e-9 and r["assumptions"] == ["가정1"] and r["questions"] == ["질문1"]
    assert "실행 오류" in calls[1]["text"] and "ZeroDivisionError" in calls[1]["text"]          # 1차 실행 오류 → 2차 피드백
    assert "AB1_S5_DIA26" in calls[2]["text"] and "이전 시도 코드" in calls[2]["text"]           # 2차 채점 실패 → 3차 피드백
    out_dir = pub["out_dir"]
    assert pub["kind"] == "agent" and pub["force"] is True
    assert sorted(p.name for p in (out_dir / "sections" / "P4P5").glob("*.glb")) == [f"{c}.glb" for c in sorted(X.CODES)]
    build = json.loads((out_dir / "build.json").read_text(encoding="utf-8"))
    assert build["kind"] == "agent" and {s["code"]: s["source"] for s in build["sections"]}["DIA"] == "agent"
    assert sum(1 for s in build["sections"] if s["source"] == "builder") == 9
    agent = out_dir / "agent"
    assert (agent / "code.py").read_text(encoding="utf-8") == GOOD and (agent / "prompt.md").is_file()
    attempts = json.loads((agent / "attempts.json").read_text(encoding="utf-8"))
    assert [a["ok"] for a in attempts] == [False, True, True] and [a.get("pass") for a in attempts] == [None, False, True]
    assert json.loads((agent / "score.json").read_text(encoding="utf-8"))["summary"]["attempts"] == 3
    assert (out_dir / "AB1_P4P5.glb").is_file() and (out_dir / "selfcheck_sections.json").is_file() and (out_dir / "measure.json").is_file()
    assert [lv for lv, _ in events].count("warn") >= 1 and events[-1][0] == "info"


def test_loop_stops_on_budget_before_calling_llm(cfg, ref_dir, monkeypatch):
    llm, calls = _fake_llm([GOOD])
    monkeypatch.setattr(L, "spent_usd", lambda cfg, ds, stage=L.STAGE: 4.9)
    r = L.run_job(cfg, "ds", _job(budget_usd=5.0), lambda lv, m: None, llm=llm, evidence=[], crops=[], ref_dir=ref_dir, do_render=False)
    assert r["reason"] == "budget" and r["pass"] is False and calls == []


def test_loop_reports_no_run_when_every_attempt_fails(cfg, ref_dir, monkeypatch):
    llm, calls = _fake_llm([BAD] * 4)
    monkeypatch.setattr(L, "spent_usd", lambda cfg, ds, stage=L.STAGE: 0.0)
    r = L.run_job(cfg, "ds", _job(), lambda lv, m: None, llm=llm, evidence=[], crops=[], ref_dir=ref_dir, do_render=False)
    assert r["reason"] == "no_run" and r["attempts"] == 4 and len(calls) == 4


def test_loop_uses_parent_code_for_revision(cfg, ref_dir, monkeypatch):
    parent = cfg.derived_dir / "ds" / "model" / "agent" / "job-0" / "agent"
    parent.mkdir(parents=True)
    (parent / "code.py").write_text(GOOD, encoding="utf-8")
    llm, calls = _fake_llm([GOOD])
    scorer, _ = _fake_scorer([True])
    monkeypatch.setattr(L, "spent_usd", lambda cfg, ds, stage=L.STAGE: 0.0)
    r = L.run_job(cfg, "ds", _job(id="job-1", parent_job_id="job-0", request="개구를 1.4×1.4 로"), lambda lv, m: None, llm=llm, scorer=scorer,
                  publisher=_fake_publisher({}), evidence=[], crops=[], ref_dir=ref_dir, do_render=False)
    assert r["pass"] is True and "이전 시도 코드" in calls[0]["text"] and "개구를 1.4×1.4 로" in calls[0]["text"]


def test_spent_usd_sums_only_stage_rows(cfg):
    p = cfg.derived_dir / "ds" / "usage.jsonl"
    p.write_text('{"stage": "read", "cost_usd": 1.0}\n{"stage": "model-agent", "cost_usd": 0.25}\n{"stage": "model-agent", "cost_usd": 0.5, "cached": true}\n', encoding="utf-8")
    assert abs(L.spent_usd(cfg, "ds") - 0.75) < 1e-9
```

`worker/tests/test_agent_worker.py`:
```python
"""워커 데몬 — claim/finish SQL·상태 전이·이벤트 (가짜 DB)."""

import dataclasses
import json

import pytest

from m3d.agent import worker as W
from m3d.config import load_config


class FakeCursor:
    def __init__(self, db):
        self.db, self._rows = db, []

    def execute(self, sql, params=None):
        s = " ".join(sql.split())
        self.db.sql.append((s, params))
        self._rows = []
        if s.startswith("update jobs set status = 'running'"):
            self._rows = [self.db.queued.pop(0)] if self.db.queued else []
        elif s.startswith("select slug from projects"):
            self._rows = [("ds",)]

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, db):
        self.db = db

    def cursor(self):
        return FakeCursor(self.db)

    def commit(self):
        self.db.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeDb:
    def __init__(self, queued=()):
        self.queued, self.sql, self.commits = list(queued), [], 0


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://fake/none")
    return dataclasses.replace(load_config(env_file=tmp_path / "absent.env"), repo_root=tmp_path)


ROW = ("job-1", "proj-1", "model-section", "P4P5/DIA", "", None, 5.0)


def test_run_once_claims_runs_and_finishes_done(cfg, monkeypatch):
    db = FakeDb(queued=[ROW])
    monkeypatch.setattr(W.psycopg, "connect", lambda *a, **k: FakeConn(db))
    seen = {}

    def fake_run_job(cfg, dataset, job, emit):
        seen.update(job=job, dataset=dataset)
        emit("info", "hello")
        return {"pass": True, "attempts": 2, "cost_usd": 0.31, "build_version": 7, "build_id": "b-7", "assumptions": [], "questions": []}
    assert W.run_once(cfg, run_job_fn=fake_run_job) is True
    assert seen["dataset"] == "ds" and seen["job"]["section_key"] == "P4P5/DIA" and seen["job"]["id"] == "job-1"
    claim_sql = db.sql[0][0]
    assert "for update skip locked" in claim_sql and "order by created_at limit 1" in claim_sql
    assert any(s.startswith("insert into job_events") and p[1:] == ("info", "hello") for s, p in db.sql)
    fin = [(s, p) for s, p in db.sql if s.startswith("update jobs set status = %s")][0]
    assert fin[1][0] == "done" and fin[1][2] == "b-7" and abs(float(fin[1][3]) - 0.31) < 1e-9 and fin[1][4] == 2
    assert json.loads(fin[1][1].dumps() if hasattr(fin[1][1], "dumps") else json.dumps(fin[1][1].obj))["build_version"] == 7
    assert db.commits >= 2


def test_run_once_returns_false_when_queue_empty(cfg, monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(W.psycopg, "connect", lambda *a, **k: FakeConn(db))
    assert W.run_once(cfg, run_job_fn=lambda *a: None) is False


def test_run_once_marks_failed_on_reason_or_exception(cfg, monkeypatch):
    db = FakeDb(queued=[ROW, ROW])
    monkeypatch.setattr(W.psycopg, "connect", lambda *a, **k: FakeConn(db))
    W.run_once(cfg, run_job_fn=lambda cfg, ds, job, emit: {"pass": False, "reason": "budget", "attempts": 0, "cost_usd": 0.0})
    fin = [p for s, p in db.sql if s.startswith("update jobs set status = %s")][-1]
    assert fin[0] == "failed"

    def boom(cfg, ds, job, emit):
        raise RuntimeError("kaboom")
    W.run_once(cfg, run_job_fn=boom)
    fin2 = [p for s, p in db.sql if s.startswith("update jobs set status = %s")][-1]
    assert fin2[0] == "failed" and "kaboom" in json.dumps(fin2[1].obj, ensure_ascii=False)
    assert any(s.startswith("insert into job_events") and p[1] == "error" for s, p in db.sql)
```

- [ ] **Step 2: 실패 확인**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_agent_loop.py worker/tests/test_agent_worker.py -q` → FAIL(모듈 없음)

- [ ] **Step 3: 구현**

`worker/src/m3d/agent/loop.py`:
```python
"""잡 실행 루프 (M5 D7·D8·D9) — 묶음 → LLM → 샌드박스 → 채점, 시도 ≤ 4, 예산 상한, 에이전트 빌드 디렉터리 → publish.

의존성(llm·scorer·publisher·evidence·crops·ref_dir)은 주입 가능 — 테스트는 실호출 없이 돈다.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from m3d.agent import context as agent_context
from m3d.agent import crops as agent_crops
from m3d.agent import sandbox, score as agent_score
from m3d.agent.schema import AgentOut, validate_agent_out
from m3d.config import Config
from m3d.model import io as model_io
from m3d.model import measure, publish, render, sections, selfcheck
from m3d.model.builder import Builder
from m3d.model.spec import ModelSpec
from m3d.reading.client import MODEL_READ, build_client, call_structured
from m3d.samples.manifest import sha256_file

MAX_ATTEMPTS = 4
MAX_TOKENS = 16000
EST_CALL_USD = 0.15
STAGE = "model-agent"


def spent_usd(cfg: Config, dataset: str, stage: str = STAGE) -> float:
    path = cfg.derived_dir / dataset / "usage.jsonl"
    if not path.is_file():
        return 0.0
    total = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("stage") == stage and not r.get("cached"):
            total += float(r.get("cost_usd") or 0.0)
    return total


def real_llm(cfg: Config, dataset: str, bundle: dict, extra: dict) -> tuple[AgentOut, dict]:
    client = build_client(cfg)
    return call_structured(client, cfg, dataset, model=MODEL_READ, system=bundle["system"], messages=bundle["messages"],
                           out_format=AgentOut, max_tokens=MAX_TOKENS, stage=STAGE, extra=extra, post_validate=validate_agent_out)


def _section_meta(path: Path, key: str, code: str, source: str) -> dict:
    named = agent_score.load_named(path)
    return {"key": key, "code": code, "label": sections.LABELS[code], "file": f"sections/{key.split('/')[0]}/{code}.glb",
            "meshes": len(named), "triangles": int(sum(len(m.faces) for m in named.values())),
            "bytes": path.stat().st_size, "sha256": sha256_file(path), "source": source}


def build_agent_dir(cfg: Config, dataset: str, *, out_dir: Path, ref_dir: Path, spec: ModelSpec, code: str, agent_glb: Path,
                    final: AgentOut, attempts: list[dict], score: dict, bundle: dict, do_render: bool = True) -> Path:
    """정답 빌드 디렉터리를 복제하고 섹션 하나를 에이전트 결과로 교체한 산출 디렉터리(D9)."""
    segment = spec.coord.segment
    sec_dir = out_dir / "sections" / segment
    sec_dir.mkdir(parents=True, exist_ok=True)
    meta, named_all = [], {}
    for c in sections.CODES:
        src = Path(agent_glb) if c == code else Path(ref_dir) / "sections" / segment / f"{c}.glb"
        dst = sec_dir / f"{c}.glb"
        shutil.copyfile(src, dst)
        meta.append(_section_meta(dst, f"{segment}/{c}", c, "agent" if c == code else "builder"))
        named_all.update(agent_score.load_named(dst))
    b = Builder(spec)
    glb = out_dir / "AB1_P4P5.glb"
    b.export(named_all, glb)
    r_all = selfcheck.run(named_all, b, pilot=False)
    sec_results = {}
    for m in meta:
        rs = selfcheck.run(agent_score.load_named(sec_dir / f"{m['code']}.glb"), b, section=m["code"])
        sec_results[m["key"]] = rs
        m["selfcheck"] = {"pass": rs["pass"], "fail": rs["fail"]}
    (out_dir / "selfcheck.json").write_text(json.dumps(r_all, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "selfcheck_sections.json").write_text(json.dumps(sec_results, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "measure.json").write_text(json.dumps(measure.run(glb, spec), ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.copyfile(model_io.model_dir(cfg, dataset) / "modelspec.json", out_dir / "modelspec.json")
    if do_render:
        render.run_render(glb, out_dir / "renders", spec, pilot=False)
    else:
        (out_dir / "renders").mkdir(exist_ok=True)
        (out_dir / "renders" / "views.json").write_text("{}", encoding="utf-8")
    agent_dir = out_dir / "agent"
    agent_dir.mkdir(exist_ok=True)
    (agent_dir / "code.py").write_text(final.code, encoding="utf-8")
    (agent_dir / "attempts.json").write_text(json.dumps(attempts, ensure_ascii=False, indent=2), encoding="utf-8")
    (agent_dir / "score.json").write_text(json.dumps({"summary": agent_score.summary(score, len(attempts)), "score": score,
                                                      "assumptions": final.assumptions, "questions": final.questions},
                                                     ensure_ascii=False, indent=2), encoding="utf-8")
    texts = "\n\n".join(p["text"] for p in bundle["messages"][0]["content"] if p["type"] == "text")
    (agent_dir / "prompt.md").write_text("# system\n\n" + bundle["system"] + "\n\n# user\n\n" + texts, encoding="utf-8")
    model_io.write_build_json(out_dir, {
        "kind": "agent", "segment": segment,
        "assembled": {"file": "AB1_P4P5.glb", "meshes": r_all["meshes"], "triangles": r_all["triangles"],
                      "bytes": glb.stat().st_size, "sha256": sha256_file(glb)},
        "sections": meta, "selfcheck": {"pass": r_all["pass"], "fail": r_all["fail"], "skipped": r_all["skipped"]}, "git_sha": None})
    return out_dir


def run_job(cfg: Config, dataset: str, job: dict, emit, *, llm=None, scorer=None, publisher=None, evidence=None, crops=None,
            ref_dir=None, do_render: bool = True) -> dict:
    llm = llm or real_llm
    scorer = scorer or agent_score.score_section
    publisher = publisher or (lambda cfg, dataset, *, out_dir, kind, force: publish.run_publish_model(cfg, dataset, out_dir=out_dir, kind=kind, force=force))
    segment, code = job["section_key"].split("/")
    pattern = agent_crops.SECTION_PATTERNS.get(code)
    if pattern is None:
        emit("error", f"지원하지 않는 섹션: {job['section_key']}")
        return {"pass": False, "reason": "unsupported_section", "attempts": 0, "cost_usd": 0.0, "assumptions": [], "questions": []}
    raw = model_io.load_modelspec_raw(cfg, dataset)
    spec, sources = ModelSpec.model_validate(raw["spec"]), raw.get("sources", {})
    ref_dir = Path(ref_dir) if ref_dir else model_io.model_dir(cfg, dataset)
    if not all((ref_dir / "sections" / segment / f"{c}.glb").is_file() for c in sections.CODES):
        emit("error", "정답 섹션 GLB 없음 — `m3d build` 먼저")
        return {"pass": False, "reason": "no_reference", "attempts": 0, "cost_usd": 0.0, "assumptions": [], "questions": []}
    work = model_io.model_dir(cfg, dataset) / "agent" / str(job["id"])
    (work / "agent").mkdir(parents=True, exist_ok=True)
    if evidence is None:
        evidence = agent_crops.fetch_evidence(cfg, dataset, pattern)
    if crops is None:
        crops = agent_crops.section_crops(cfg, dataset, evidence, work / "agent" / "crops")
    emit("info", f"입력: 판독 근거 {len(evidence)}건, 크롭 {len(crops)}장")
    prev_code = None
    if job.get("parent_job_id"):
        p = model_io.model_dir(cfg, dataset) / "agent" / str(job["parent_job_id"]) / "agent" / "code.py"
        prev_code = p.read_text(encoding="utf-8") if p.is_file() else None
    feedback, attempts, cost, last, bundle = None, [], 0.0, None, None
    budget = float(job.get("budget_usd") or cfg.model_agent_budget_usd)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        spent = spent_usd(cfg, dataset)
        if spent + EST_CALL_USD > budget:
            emit("error", f"예산 상한: 누적 ${spent:.2f} + 예상 ${EST_CALL_USD:.2f} > ${budget:.2f}")
            return {"pass": False, "reason": "budget", "attempts": len(attempts), "cost_usd": cost, "assumptions": [], "questions": []}
        bundle = agent_context.section_bundle(job["section_key"], spec_dict=spec.model_dump(), sources=sources, evidence=evidence,
                                              crops=crops, feedback=feedback, request=job.get("request") or "", prev_code=prev_code)
        emit("info", f"시도 {attempt}/{MAX_ATTEMPTS}: LLM 호출(이미지 {bundle['n_images']}장)")
        out, usage = llm(cfg, dataset, bundle, {"job_id": str(job["id"]), "attempt": attempt, "section": job["section_key"]})
        cost += float(usage.get("cost_usd") or 0.0)
        (work / "agent" / f"attempt{attempt}.py").write_text(out.code, encoding="utf-8")
        res = sandbox.run_code(out.code, spec.model_dump(), work / "agent" / f"attempt{attempt}.glb")
        prev_code = out.code
        if not res.ok:
            feedback = "실행 오류:\n" + res.error
            attempts.append({"attempt": attempt, "ok": False, "error": res.error[:2000], "cost_usd": usage.get("cost_usd")})
            emit("warn", f"시도 {attempt}: 실행 실패 — {res.error.splitlines()[0][:160]}")
            continue
        sc = scorer(code, res.glb, spec, ref_dir, work_dir=work / f"score{attempt}")
        attempts.append({"attempt": attempt, "ok": True, "pass": sc["pass"], "score": agent_score.summary(sc, attempt),
                         "cost_usd": usage.get("cost_usd")})
        last = (out, res, sc)
        emit("info", f"시도 {attempt}: 채점 {'PASS' if sc['pass'] else 'FAIL'} — 노드 누락 {len(sc['compare']['only_ref'])}·"
                     f"초과 {len(sc['compare']['only_ours'])}·bbox {(sc['compare']['bbox_dev_max_m'] or 0) * 1000:.0f}mm·"
                     f"결합 fail {sc['assembled_selfcheck']['fail']}·재실측 fail {sc['measure']['FAIL']}")
        if sc["pass"]:
            break
        feedback = agent_score.feedback_text(sc)
    (work / "agent" / "attempts.json").write_text(json.dumps(attempts, ensure_ascii=False, indent=2), encoding="utf-8")
    if last is None:
        emit("error", "모든 시도가 실행에 실패했다")
        return {"pass": False, "reason": "no_run", "attempts": len(attempts), "cost_usd": cost, "assumptions": [], "questions": []}
    out, res, sc = last
    out_dir = build_agent_dir(cfg, dataset, out_dir=work, ref_dir=ref_dir, spec=spec, code=code, agent_glb=res.glb, final=out,
                              attempts=attempts, score=sc, bundle=bundle, do_render=do_render)
    pub = publisher(cfg, dataset, out_dir=out_dir, kind="agent", force=True)
    emit("info", f"에이전트 빌드 b{pub['version']} 업로드({pub['uploaded']} 파일)")
    return {"pass": sc["pass"], "attempts": len(attempts), "cost_usd": cost, "build_version": pub["version"], "build_id": pub["build_id"],
            "assumptions": out.assumptions, "questions": out.questions, "score": agent_score.summary(sc, len(attempts))}
```
주의: `build_agent_dir` 의 `out_dir=work` — 잡 작업 디렉터리를 그대로 산출 디렉터리로 쓴다(`agent/` 하위에 시도 파일도 남지만 `collect_files` 는 `agent/*.py|json|md` 만 올린다 → `attempt*.py`·`attempt*.glb` 는 제외하려면 `collect_files` 에서 `agent/` 직속 파일 중 이름이 `code.py|attempts.json|score.json|prompt.md` 인 것만 담는다 — Task 4 의 `collect_files` 를 그렇게 고정한다(`AGENT_FILES = ("agent/code.py", "agent/attempts.json", "agent/score.json", "agent/prompt.md")` 중 존재하는 것)).

`worker/src/m3d/agent/worker.py`:
```python
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
    return {k: (str(v) if k in ("id", "project_id") or (k == "parent_job_id" and v is not None) else v) for k, v in zip(keys, row)}


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
            result = {"pass": False, "reason": "error", "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()[-2000:],
                      "attempts": 0, "cost_usd": 0.0}
            status = "failed"
        finish(conn, job["id"], status=status, result=result, build_id=result.get("build_id"),
               cost_usd=result.get("cost_usd", 0.0), attempts=result.get("attempts", 0))
        bv = result.get("build_version")
        print(f"worker job={job['id']} section={job['section_key']} attempts={result.get('attempts', 0)} pass={result.get('pass')} "
              f"cost=${float(result.get('cost_usd', 0.0)):.2f} build={'b' + str(bv) if bv else '-'} status={status}")
        return True


def serve(cfg: Config, *, poll: float = 2.0, once: bool = False) -> None:
    print(f"worker 시작 — poll {poll}s, 예산 상한 ${cfg.model_agent_budget_usd:.2f} (Ctrl+C 로 종료)")
    while True:
        did = run_once(cfg)
        if once and did:
            return
        if not did:
            time.sleep(poll)
```

`worker/src/m3d/cli.py` — `publish_model` 뒤에:
```python
@app.command()
def worker(
    once: bool = typer.Option(False, "--once", help="잡 1건만 처리하고 종료"),
    poll: float = typer.Option(2.0, "--poll", help="큐 폴링 간격(초)"),
) -> None:
    """[11] 모델링 에이전트 워커 데몬 — jobs 큐를 집어 LLM 코드 생성·실행·채점·업로드 (M5 §5). API 과금 발생(MODEL_AGENT_BUDGET_USD 상한)."""
    from m3d.agent import worker as agent_worker
    cfg = load_config()
    agent_worker.serve(cfg, poll=poll, once=once)
```

- [ ] **Step 4: 통과 확인·커밋**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_agent_loop.py worker/tests/test_agent_worker.py -q` → PASS (loop 테스트는 정답 빌드·재실측 포함 ~1~2분)
Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests -q` → 전건 PASS
```bash
git add worker/src/m3d/agent/loop.py worker/src/m3d/agent/worker.py worker/src/m3d/cli.py worker/tests/test_agent_loop.py worker/tests/test_agent_worker.py
git commit -m "feat(agent): 잡 루프(시도≤4·피드백·예산·에이전트 빌드 디렉터리·publish) + m3d worker 데몬" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: 웹 — 잡 생성·폴링·패널, 에이전트 빌드 채점·assumptions·questions·코드 링크·수정 요청, LLM 배지

**Files:**
- Create: `web/src/lib/jobs.ts`, `web/src/lib/jobs.test.ts`, `web/src/components/JobPanel.tsx`
- Modify: `web/src/routes/Model.tsx`, `web/src/components/VerifyPanel.tsx`

**Interfaces:**
- Consumes: `contracts/db.types.ts` `jobs`·`job_events`·`JobResult`·`AgentScoreSummary`(Task 1), `lib/models.ts` 함수, `useSession`.
- Produces (`lib/jobs.ts`): `AGENT_SECTIONS = ['DIA']`, `JobRow`, `JobEventRow`, `jobPayload({projectId, sectionKey, request, parentJobId}) -> JobInsert`(request trim ≤ 2000자, sectionKey `^[A-Z0-9]+/[A-Z0-9]+$` 아니면 RangeError), `jobSummary(job) -> string`(예 `실행 중 · 시도 2 · $0.31`), `isActive(job)`, `createJob(client, payload)`, `fetchJobs(client, projectId, limit=5)`, `fetchEvents(client, jobId)`.
- Produces (`JobPanel`): props `{ jobs: JobRow[]; events: Record<string, JobEventRow[]>; onToggle(jobId): void; open: string | null }`.
- `VerifyPanel` props 추가: `agentResult?: JobResult | null; onRevise?(request: string): void`.

- [ ] **Step 1: 실패 테스트**

`web/src/lib/jobs.test.ts`:
```ts
import { describe, expect, it } from 'vitest';
import { AGENT_SECTIONS, isActive, jobPayload, jobSummary, type JobRow } from './jobs';

const job = (over: Partial<JobRow>): JobRow => ({
  id: 'j', project_id: 'p', kind: 'model-section', section_key: 'P4P5/DIA', request: '', parent_job_id: null, status: 'queued',
  attempts: 0, cost_usd: 0, budget_usd: 5, result: null, build_id: null, user_id: 'u',
  created_at: '2026-09-06T10:00:00+00:00', updated_at: '2026-09-06T10:00:00+00:00', ...over,
});

describe('jobPayload', () => {
  it('정상 — request trim, parent 선택', () => {
    expect(jobPayload({ projectId: 'p', sectionKey: 'P4P5/DIA', request: ' 개구 1.4 ', parentJobId: null }))
      .toEqual({ project_id: 'p', kind: 'model-section', section_key: 'P4P5/DIA', request: '개구 1.4', parent_job_id: null });
    expect(jobPayload({ projectId: 'p', sectionKey: 'P4P5/DIA', request: '', parentJobId: 'j0' }).parent_job_id).toBe('j0');
  });
  it('섹션 키 형식·요청 길이 검증', () => {
    expect(() => jobPayload({ projectId: 'p', sectionKey: 'dia', request: '', parentJobId: null })).toThrow(RangeError);
    expect(() => jobPayload({ projectId: 'p', sectionKey: 'P4P5/DIA', request: 'x'.repeat(2001), parentJobId: null })).toThrow(RangeError);
  });
  it('M5 는 격벽만', () => { expect(AGENT_SECTIONS).toEqual(['DIA']); });
});

describe('jobSummary / isActive', () => {
  it('상태·시도·비용 문자열', () => {
    expect(jobSummary(job({ status: 'running', attempts: 2, cost_usd: 0.31 }))).toBe('실행 중 · 시도 2 · $0.31');
    expect(jobSummary(job({ status: 'done', attempts: 3, cost_usd: 0.4, result: { pass: true, attempts: 3, cost_usd: 0.4, build_version: 7 } })))
      .toBe('완료 · 시도 3 · $0.40 · PASS · b7');
    expect(jobSummary(job({ status: 'failed', result: { pass: false, reason: 'budget', attempts: 0, cost_usd: 0 } }))).toBe('실패 · 시도 0 · $0.00 · 예산 상한');
  });
  it('queued/running 만 활성', () => {
    expect(isActive(job({ status: 'queued' }))).toBe(true);
    expect(isActive(job({ status: 'done' }))).toBe(false);
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `npm --prefix web test` → FAIL(`./jobs` 없음)

- [ ] **Step 3: 구현**

`web/src/lib/jobs.ts`:
```ts
// 모델링 에이전트 잡 — 생성·조회·요약 (M5 설계서 §6). 로그인 세션의 RLS 아래에서만.
import type { Database, JobResult } from '../../../contracts/db.types';
import type { Client } from './models';

export const AGENT_SECTIONS = ['DIA'];                       // M5: 격벽만
export type JobStatus = 'queued' | 'running' | 'done' | 'failed';
export type JobRow = Database['public']['Tables']['jobs']['Row'];
export type JobEventRow = Database['public']['Tables']['job_events']['Row'];
export type JobInsert = Database['public']['Tables']['jobs']['Insert'];

const SECTION_RE = /^[A-Z0-9]+\/[A-Z0-9]+$/;
const REASON_LABEL: Record<string, string> = { budget: '예산 상한', no_run: '실행 실패', unsupported_section: '지원 안 함', no_reference: '정답 빌드 없음', error: '오류' };
const STATUS_LABEL: Record<JobStatus, string> = { queued: '대기', running: '실행 중', done: '완료', failed: '실패' };

export function jobPayload(p: { projectId: string; sectionKey: string; request: string; parentJobId: string | null }): JobInsert {
  if (!SECTION_RE.test(p.sectionKey)) throw new RangeError(`섹션 키 형식 오류: ${p.sectionKey}`);
  const request = p.request.trim();
  if (request.length > 2000) throw new RangeError('요청은 2,000자 이내');
  return { project_id: p.projectId, kind: 'model-section', section_key: p.sectionKey, request, parent_job_id: p.parentJobId };
}

export function isActive(job: JobRow): boolean {
  return job.status === 'queued' || job.status === 'running';
}

export function jobSummary(job: JobRow): string {
  const parts = [STATUS_LABEL[job.status], `시도 ${job.attempts}`, `$${Number(job.cost_usd).toFixed(2)}`];
  const r: JobResult | null = job.result;
  if (job.status === 'done' && r) parts.push(r.pass ? 'PASS' : 'FAIL', r.build_version ? `b${r.build_version}` : '');
  if (job.status === 'failed' && r?.reason) parts.push(REASON_LABEL[r.reason] ?? r.reason);
  return parts.filter(Boolean).join(' · ');
}

export async function createJob(client: Client, payload: JobInsert): Promise<JobRow> {
  const { data, error } = await client.from('jobs').insert(payload as never).select('*').single();
  if (error) throw new Error(error.message);
  return data as unknown as JobRow;
}

export async function fetchJobs(client: Client, projectId: string, limit = 5): Promise<JobRow[]> {
  const { data, error } = await client.from('jobs').select('*').eq('project_id', projectId).order('created_at', { ascending: false }).limit(limit);
  if (error) throw new Error(error.message);
  return (data ?? []) as unknown as JobRow[];
}

export async function fetchEvents(client: Client, jobId: string): Promise<JobEventRow[]> {
  const { data, error } = await client.from('job_events').select('*').eq('job_id', jobId).order('id', { ascending: true });
  if (error) throw new Error(error.message);
  return (data ?? []) as unknown as JobEventRow[];
}
```

`web/src/components/JobPanel.tsx`:
```tsx
// 잡 패널 — 최근 잡 상태·시도·비용, 펼치면 이벤트 로그 (M5 설계서 §6)
import { Badge, Button, Group, ScrollArea, Stack, Text } from '@mantine/core';

import { isActive, jobSummary, type JobEventRow, type JobRow } from '../lib/jobs';

export function JobPanel({ jobs, events, open, onToggle }: {
  jobs: JobRow[]; events: Record<string, JobEventRow[]>; open: string | null; onToggle(jobId: string): void;
}) {
  if (jobs.length === 0) return null;
  const color = (s: JobRow['status']) => (s === 'done' ? 'green' : s === 'failed' ? 'red' : s === 'running' ? 'blue' : 'gray');
  return (
    <Stack gap={4}>
      <Text size="xs" fw={600}>LLM 모델링 잡</Text>
      {jobs.map((j) => (
        <Stack key={j.id} gap={2}>
          <Group gap={6} wrap="nowrap">
            <Badge size="xs" color={color(j.status)}>{j.section_key}</Badge>
            <Text size="xs" style={{ flex: 1 }}>{jobSummary(j)}{isActive(j) ? ' …' : ''}</Text>
            <Button size="compact-xs" variant="subtle" onClick={() => onToggle(j.id)}>{open === j.id ? '접기' : '로그'}</Button>
          </Group>
          {open === j.id && (
            <ScrollArea h={120} style={{ background: 'var(--mantine-color-gray-0)', borderRadius: 4 }} p={4}>
              {(events[j.id] ?? []).map((e) => (
                <Text key={e.id} size="xs" c={e.level === 'error' ? 'red' : e.level === 'warn' ? 'orange' : undefined}>
                  {e.ts.slice(11, 19)} {e.message}
                </Text>
              ))}
            </ScrollArea>
          )}
        </Stack>
      ))}
    </Stack>
  );
}
```

`web/src/routes/Model.tsx` 변경:
- import: `Modal, Textarea` 추가; `JobPanel`; `AGENT_SECTIONS, createJob, fetchEvents, fetchJobs, isActive, jobPayload, type JobEventRow, type JobRow` from `../lib/jobs`.
- 상태: `jobs: JobRow[]`, `events: Record<string, JobEventRow[]>`, `openJob: string | null`, `askSection: SectionRow | null`(모달), `askRequest: string`, `revising: boolean`.
- 잡 로드: project 확정 후 `fetchJobs(supabase, project.id)`; 폴링 `useEffect`: `jobs.some(isActive)` 이면 2초 간격 `fetchJobs` + 열린 잡의 `fetchEvents`; 활성 잡이 `done/failed` 로 바뀌면 `fetchBuilds` 재조회 후 `job.build_id` 가 있으면 `setBuildId(job.build_id)`.
- 격벽 행(`AGENT_SECTIONS.includes(s.code)`)에 `<Button size="compact-xs" onClick={() => { setAskSection(s); setAskRequest(''); }}>LLM 으로 만들기</Button>`; 섹션 `s.source === 'agent'` 면 `<Badge size="xs" color="violet">LLM</Badge>`.
- 모달: `Modal opened={askSection !== null}` → Textarea(요청, 선택) + 버튼 "잡 생성" → `createJob(supabase, jobPayload({ projectId: project.id, sectionKey: askSection.section_key, request: askRequest, parentJobId: null }))` → `setJobs((prev) => [row, ...prev])`, 닫기.
- 우 패널: `<JobPanel jobs={jobs} events={events} open={openJob} onToggle={...} />` 를 VerifyPanel 위에; `VerifyPanel` 에 `agentResult={jobs.find((j) => j.build_id === build.id)?.result ?? null}`, `onRevise={(request) => createJob(...jobPayload({ ..., parentJobId: jobs.find((j) => j.build_id === build.id)?.id ?? null }))}`.
- `agent/` 다운로드 키는 `build.files.agent ?? []` 를 `fileKeys` 에 추가(코드 링크 표시).

`web/src/components/VerifyPanel.tsx` 변경:
- props `agentResult?: JobResult | null; onRevise?(request: string): void`.
- `build.kind === 'agent'` 이면 상단에 채점 블록: `st.agent` 가 있으면 `Badge PASS/FAIL`, `노드 누락 {only_ref} · 초과 {only_ours} · bbox {bbox_dev_max_m*1000 mm} · 결합 fail {assembled_fail} · 재실측 fail {measure_fail} · 시도 {attempts}`; `agentResult?.assumptions` → "가정" 목록, `agentResult?.questions` → "질문" 목록(각 `Text size="xs"`); 다운로드 목록에 `agent/code.py` 가 자연히 포함된다.
- 승인 블록 아래 "수정 요청" `Textarea` + `Button`(`onRevise` 있을 때만, `build.kind==='agent'`): 클릭 → `onRevise(text)` 후 비움.

- [ ] **Step 4: 타입·테스트·브라우저(잡 생성만, 워커 없이)**

Run: `npm --prefix web run typecheck && npm --prefix web test` → 0 / PASS(+5)
브라우저(로그인): `/p/ab1-p4p5/model` → 격벽 행 "LLM 으로 만들기" → 모달 → "잡 생성" → 잡 패널에 `대기 · 시도 0 · $0.00 …` 표시, DB `jobs 1`. (워커는 Task 7 에서 실행.) `read_console_messages onlyErrors` 0.

- [ ] **Step 5: 커밋**

```bash
git add web/src/lib/jobs.ts web/src/lib/jobs.test.ts web/src/components/JobPanel.tsx web/src/routes/Model.tsx web/src/components/VerifyPanel.tsx
git commit -m "feat(web): LLM 모델링 잡 생성·폴링·패널 + 에이전트 빌드 채점·가정·질문·코드 링크·수정 요청" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: 실증(실 LLM, 상한 $5)·합격 판정·README·통합

**Files:**
- Create: `data/derived/ab1-p4p5/model/acceptance-m5.md`(gitignore)
- Modify: `README.md`("LLM 모델링 (M5)" 절), 메모리 `m5-*.md` + `MEMORY.md`

- [ ] **Step 1: 사전 점검(무과금)**

```
PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli build ab1-p4p5 | tail -1     # 정답 섹션 10 (model/sections) 최신
PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli db check | grep -E "^builds|^jobs"
```
heredoc: `loop.spent_usd(cfg, "ab1-p4p5")` → 0.0 확인, `crops.fetch_evidence` 12행, `section_crops` 크롭 수(≤6) 확인 + 크롭 1장 Read 육안.

- [ ] **Step 2: 실증 1 — 웹에서 잡 생성 → `m3d worker --once` (실호출)**

브라우저(로그인): 격벽 "LLM 으로 만들기"(요청 없음) → 잡 생성. 터미널: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli worker --once` (시도 ≤4, 각 ~1~2분: LLM 호출·실행·채점·렌더·업로드). 콘솔 `worker job=… attempts=N pass=… cost=$… build=bN`.
브라우저: 잡 패널 `완료 · 시도 N · $x.xx · PASS|FAIL · bN`, 에이전트 빌드 자동 선택, 격벽 행 "LLM" 배지, 우 패널 채점·가정·질문·`agent/code.py` 링크, 캔버스에서 격벽 단독 + z 단면으로 육안. 스크린샷 소견 기록.
DB: `jobs 1(done)`, `job_events ≥ 6`, `builds +1(kind agent)`, `build_sections +10(source agent 1)`.

- [ ] **Step 3: 실증 2 — 수정 요청 1회 (실호출)**

우 패널 "수정 요청": 채점 결과에 따라 — PASS 면 "격벽 개구 보강재를 −z 면에도 붙여 줘"(정답과 달라지므로 FAIL 이 정상인 요청, 루프 동작 확인용), FAIL 이면 채점 피드백의 첫 항목을 요청으로. → 잡 2 → `m3d worker --once` → 잡 패널·새 에이전트 빌드 확인(`parent_job_id` 채워짐 확인: `select id, parent_job_id, status, attempts, cost_usd from jobs`).
비용 확인: heredoc `spent_usd` → ≤ $5. 넘을 위험이 보이면(1잡 > $1.5) 잡 2 를 생략하고 판정서에 기록.

- [ ] **Step 4: 익명 거부·테스트**

heredoc: publishable 키로 `POST /rest/v1/jobs` → 401, `GET /rest/v1/jobs?select=id` → 200 `[]`. `pytest` 전건·`vitest`·`typecheck`.

- [ ] **Step 5: 판정서·README·메모리·커밋**

`acceptance-m5.md`: §1 ①~⑤ 표(실제 수치: 잡별 시도·비용·채점 요약·빌드 버전), 실증 소견(브라우저), 프롬프트 크기(입력 토큰·이미지 수, usage.jsonl 에서), LLM 이 낸 assumptions·questions 원문, 실패했다면 원인 분석(코드 발췌)과 다음 개선 후보, 결함 메모.
README 끝에:
```markdown

## LLM 모델링 (M5)

웹 검수 화면에서 섹션의 "LLM 으로 만들기"를 누르면 `jobs` 큐에 잡이 생기고, 내 PC 의 워커가 Sonnet 5 로 섹션 빌더 코드를 받아
샌드박스에서 실행·채점(정답 대조 + 레고식 결합 재실측)한 뒤 에이전트 빌드로 올린다. **API 과금 발생** — `.env` 의 `MODEL_AGENT_BUDGET_USD`(기본 5) 누적 상한.

```powershell
$env:PYTHONUTF8='1'
.\worker\.venv\Scripts\m3d.exe worker --once     # 큐의 잡 1건 처리 (--once 없이 데몬으로)
```

M5 범위: 격벽(P4P5/DIA) 1섹션. 산출물 `data/derived/ab1-p4p5/model/agent/<job>/`(코드·시도·채점·프롬프트). 판정: `model/acceptance-m5.md`.
```
```bash
git add README.md
git commit -m "docs: README LLM 모델링 (M5) 절 + M5 합격 판정" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```
메모리 `m5-modeling-agent.md`(결과·비용·교훈) + `MEMORY.md` 한 줄. 그 다음 `superpowers:finishing-a-development-branch`.

---

## 계획 자체 검토

- **스펙 커버리지**: §1 ①(T5 worker + T6 웹 + T7 실증) ②(T4 채점 + T7) ③(T5 parent code + T6 수정 요청 + T7) ④(T5 예산·usage stage + T7 원장) ⑤(T7 익명·테스트). §2 D1(T2 schema·계약) D2(T2 BoxContext) D3(T3) D4(T5 real_llm) D5(T2) D6(T4) D7(T5 루프) D8(T1 config + T5) D9(T5 build_agent_dir + T4 publish) D10(T1 SQL + T5 worker + T6 폴링) D11(T7 범위). §3 모듈 전부 T2~T5 에 있음. §6 웹 요소 T6. §7 테스트 목록 T1~T6 + 실증 T7.
- **플레이스홀더**: 없음. T2 의 `visual.kind` 조건은 구현 시 실제 값으로 확정한다고 명시.
- **타입 일관성**: `AgentOut(code, assumptions, questions)` T2→T5; `RunResult.ok/glb/error/node_names` T2→T5; `score_section(code, agent_glb, spec, ref_dir, *, work_dir)`·`summary`·`feedback_text` T4→T5(테스트 fake 도 같은 시그니처); `run_publish_model(cfg, dataset, *, out_dir=, kind=, force=)` T4→T5; `run_job` 결과 키 `pass/reason/attempts/cost_usd/build_version/build_id/assumptions/questions/score` T5→worker→`JobResult`(T1 TS)→T6 `jobSummary`; 이벤트 level `info|warn|error` T1 SQL·T5·T6; `build_sections.source` T1→T4 insert→T5 meta→T6 배지; `collect_files` 의 `AGENT_FILES` 고정(T4/T5 주의 문단).
- **비용 안전장치**: T1~T6 무과금(가짜 LLM). T7 만 실호출, 호출 전 `spent_usd + 0.15 > budget` 검사, 잡당 시도 ≤ 4.
