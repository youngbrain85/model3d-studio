# M2b 질문 카드 · decisions · SSOT 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** M2a 가 만든 애매성 63건을 로그인한 사용자가 웹 카드로 답하고, 그 결정을 이력으로 저장하며, 판독값·결정을 합친 치수 정본(실측정리) 문서를 CLI 로 생성한다.

**Architecture:** 서버 코드 없음. 웹(React·Mantine·supabase-js)은 RLS 아래에서 읽고 `decisions` 에 삽입만 한다. 삽입 트리거가 `ambiguities.status` 를 갱신한다. 크롭 업로드(`m3d publish`)와 SSOT 생성(`m3d ssot`)은 worker CLI 가 service key/DB URL 로 수행한다. 재판독은 결정이 달린 ambiguity 를 보존한다.

**Tech Stack:** Python 3.12(typer·psycopg 3·urllib) / PostgreSQL(Supabase, RLS·trigger·Storage) / React 18·Vite 6·Mantine 8·supabase-js 2.110·react-router-dom 6·vitest 2.

설계서: `docs/superpowers/specs/2026-09-05-m2b-question-cards-design.md` (정본).

## Global Constraints

- **venv Python**: `.\worker\.venv\Scripts\python.exe`, `PYTHONUTF8=1` 필수. pytest: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests -q` (시작 **277 passed**, 실측 우선).
- **웹**: `web/` 에서 `npm run typecheck`·`npm run test`(vitest, Task 4 에서 추가). 패키지 설치는 `cd web && npm install <pkg>` (인자 없는 `npm --prefix web install` 은 이 환경에서 실패한 이력 있음).
- **비밀키**: `SUPABASE_SERVICE_KEY`·`SUPABASE_DB_URL`·`ANTHROPIC_*` 값을 코드·로그·출력·보고서·커밋에 절대 노출하지 않는다. 웹 번들에는 `VITE_SUPABASE_URL`·`VITE_SUPABASE_PUBLISHABLE_KEY` 만 들어간다. 비밀번호는 Claude 가 다루지 않는다 — 계정 생성·로그인은 사용자가 직접(Task 6).
- **LLM 실호출 0건**. `--force` 와 `--cache-only` 는 상충한다. 재판독 실증은 `review … --cache-only` 로만(캐시 히트, $0).
- **DB 쓰기 범위**: 0004 적용, `decisions` 삽입(웹·트리거), `assets.storage_path` update(publish), `ambiguities.status` update(트리거만). 기존 행 삭제 금지. 결정이 달린 ambiguity 는 `replace_region` 에서 보존.
- **Storage**: 비공개 버킷 `crops`, 오브젝트 키 `<slug>/<ambiguity_id>.png`, `assets.storage_path = "crops/<slug>/<id>.png"`.
- **테스트는 전부 가짜**(가짜 커서·가짜 HTTP·vitest 순수 로직). 실DB·Storage·브라우저 실증은 지정된 Step 에서만.
- **긴 명령은 포그라운드 timeout 600000, 백그라운드 금지.** 파일 편집이 "shared checkout" 가드로 거부되면 임시 워크트리에서 작업 후 `main` 이 아닌 작업 브랜치에 fast-forward 병합(아래 브랜치 참조).
- **브랜치**: `feat/m2b-question-cards` (main ecfb877+ 에서 분기). 커밋 메시지 말미 두 줄:

  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01AZoYNTVPox7g1d6oJd5Wo1
  ```
- 주석·CLI 출력·UI 문구 한국어. `cli.py` 기존 구조 보존(명령 추가만).

---

### Task 1: 0004 마이그레이션 · 타입 계약 · db check 확장

**Files:**
- Create: `supabase/migrations/0004_decisions.sql`
- Create: `worker/tests/test_migration_0004.py`
- Modify: `contracts/db.types.ts` (readings·ambiguities·decisions 추가)
- Modify: `worker/src/m3d/db.py` (`TABLES`, `check()`)
- Modify: `worker/src/m3d/cli.py` (`db_check` 출력 1줄)

**Interfaces:**
- Produces: 테이블 `decisions(id, project_id, ambiguity_id, choice_index, choice_label, provisional, note, decided_by, decided_at)`; 트리거 `decisions_apply`; 버킷 `crops` + storage.objects select 정책; `db_mod.check()` 반환 키 `decisions_total`·`decisions_provisional`·`published`; `Database['public']['Tables']['decisions']` 타입.

- [ ] **Step 1: 실패하는 마이그레이션 테스트**

`worker/tests/test_migration_0004.py`:

```python
"""0004_decisions — 결정 이력·트리거·Storage 정책이 회귀로 사라지지 않게 고정한다."""

import re

import pytest

from m3d.config import REPO_ROOT
from m3d.db import discover_migrations


@pytest.fixture
def norm() -> str:
    path = REPO_ROOT / "supabase" / "migrations" / "0004_decisions.sql"
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_discovered_in_order():
    versions = [m.version for m in discover_migrations(REPO_ROOT / "supabase" / "migrations")]
    assert versions[:4] == ["0001_init", "0002_convert", "0003_readings", "0004_decisions"]


def test_decisions_table_and_restrict_fk(norm):
    assert "create table decisions (" in norm
    assert "references ambiguities(id) on delete restrict" in norm
    assert "choice_index int not null check (choice_index >= 0)" in norm
    assert "provisional boolean not null default false" in norm
    assert "decided_by uuid not null default auth.uid()" in norm


def test_rls_select_and_own_insert_only(norm):
    assert "alter table decisions enable row level security" in norm
    assert 'create policy "authenticated read" on decisions for select to authenticated using (true)' in norm
    assert "for insert to authenticated with check (decided_by = auth.uid())" in norm
    assert "for update" not in norm and "for delete" not in norm
    assert "to anon" not in norm


def test_trigger_applies_status_and_checks_range(norm):
    assert "create function apply_decision() returns trigger" in norm
    assert "security definer" in norm
    assert "jsonb_array_length(options)" in norm
    assert "case when new.provisional then '잠정' else '결정' end" in norm
    assert "create trigger decisions_apply after insert on decisions" in norm


def test_private_bucket_and_authenticated_read(norm):
    assert "insert into storage.buckets (id, name, public) values ('crops', 'crops', false)" in norm
    assert "on storage.objects for select to authenticated using (bucket_id = 'crops')" in norm
```

- [ ] **Step 2: 실패 확인**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_migration_0004.py -q`
Expected: 5 failed (`FileNotFoundError` / 순서 단언 실패).

- [ ] **Step 3: 마이그레이션 SQL 작성**

`supabase/migrations/0004_decisions.sql`:

```sql
-- 0004_decisions — 질문 응답 이력 + 상태 갱신 트리거 + 크롭 Storage (M2b 설계서 §3)
-- decisions 는 추가 전용 이력이다: 재답변은 새 행, 최신 행이 현재 결정 (지식베이스 §2 정정 이력).

create table decisions (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references projects(id) on delete cascade,
  ambiguity_id  uuid not null references ambiguities(id) on delete restrict,
  choice_index  int  not null check (choice_index >= 0),      -- options[] 인덱스
  choice_label  text not null,                                 -- 선택 당시 label 스냅샷
  provisional   boolean not null default false,               -- "모르겠다" → true → 잠정
  note          text not null default '',
  decided_by    uuid not null default auth.uid(),
  decided_at    timestamptz not null default now()
);
create index on decisions (ambiguity_id, decided_at desc);

alter table decisions enable row level security;
create policy "authenticated read"   on decisions for select to authenticated using (true);
create policy "authenticated insert" on decisions for insert to authenticated
  with check (decided_by = auth.uid());

-- 삽입 트리거: 선택지 범위 검증 + ambiguities.status 갱신
-- (security definer — authenticated 에는 ambiguities update 정책이 없다)
create function apply_decision() returns trigger
language plpgsql security definer set search_path = public as $$
declare n int;
begin
  select jsonb_array_length(options) into n from ambiguities where id = new.ambiguity_id;
  if n is null then
    raise exception 'ambiguity 없음: %', new.ambiguity_id;
  end if;
  if new.choice_index >= n then
    raise exception 'choice_index % 범위 밖 (선택지 %개)', new.choice_index, n;
  end if;
  update ambiguities
     set status = case when new.provisional then '잠정' else '결정' end
   where id = new.ambiguity_id;
  return new;
end $$;
create trigger decisions_apply after insert on decisions
  for each row execute function apply_decision();

-- Storage: 비공개 버킷 + 로그인 사용자 읽기 (서명 URL 발급에 필요). 업로드는 service key(CLI)만.
insert into storage.buckets (id, name, public) values ('crops', 'crops', false)
  on conflict (id) do nothing;
create policy "authenticated read crops" on storage.objects
  for select to authenticated using (bucket_id = 'crops');
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_migration_0004.py -q`
Expected: 5 passed.

- [ ] **Step 5: 타입 계약 추가**

`contracts/db.types.ts` 의 `assets: { … };` 블록 **뒤**(같은 `Tables` 객체 안)에 추가:

```ts
      readings: {
        Row: {
          id: string;
          project_id: string;
          region: string;
          item: string;
          value_raw: string;
          unit: string | null;
          basis_sheet_id: string;
          basis_page_id: string | null;
          basis_mm_bbox: Json;
          crosscheck: Json | null;
          status: '확정' | '추정' | '검토지적';
          round: number;
          created_at: string;
        };
        Insert: never;
        Update: never;
      };
      ambiguities: {
        Row: {
          id: string;
          project_id: string;
          item: string;
          basis_sheet_id: string;
          sheet_page_id: string | null;
          mm_bbox: Json;
          options: Json;
          model_impact: string;
          crop_rel_path: string | null;
          status: '대기' | '결정' | '잠정';
          created_at: string;
        };
        Insert: never;
        Update: never;
      };
      decisions: {
        Row: {
          id: string;
          project_id: string;
          ambiguity_id: string;
          choice_index: number;
          choice_label: string;
          provisional: boolean;
          note: string;
          decided_by: string;
          decided_at: string;
        };
        Insert: {
          id?: string;
          project_id: string;
          ambiguity_id: string;
          choice_index: number;
          choice_label: string;
          provisional?: boolean;
          note?: string;
          decided_by?: string;
          decided_at?: string;
        };
        Update: never;
      };
```

`readings`/`ambiguities` 의 `Insert: never` 는 웹이 쓰지 않는다는 계약이다(worker 만 씀). 파일 머리 주석의 "0001_init.sql 미러" 를 "0001~0004 미러" 로 고친다.

- [ ] **Step 6: db.py — TABLES·check 확장**

`worker/src/m3d/db.py`:
- `TABLES = ("projects", "sheets", "sheet_pages", "assets")` → `TABLES = ("projects", "sheets", "sheet_pages", "assets", "readings", "ambiguities", "decisions")`.
- `check()` 에서 `crops_assets = cur.fetchone()[0]` 다음에 추가:

```python
        cur.execute("select count(*), count(*) filter (where provisional) from decisions")
        decisions_total, decisions_provisional = cur.fetchone()

        cur.execute("select count(*) from assets where role = 'derived' "
                    "and rel_path like '%%/crops/%%' and storage_path is not null")
        published = cur.fetchone()[0]
```

- 반환 dict 에 `"decisions_total": decisions_total, "decisions_provisional": decisions_provisional, "published": published` 추가.

`worker/src/m3d/cli.py` `db_check` 의 마지막 `typer.echo(f"crops_ready=…")` 다음에:

```python
    # M2b: 결정·업로드 현황 (ASCII 고정 — 스크립트가 읽는다)
    typer.echo(f"decisions={result['decisions_total']} provisional={result['decisions_provisional']} "
               f"published={result['published']}/{result['crops_assets']}")
```

`worker/tests/test_migration_sql.py` 의 `TABLES = ("projects", "sheets", "sheet_pages", "assets")` 는 0001 전용이므로 그대로 둔다(그 파일이 `db.TABLES` 를 import 해 비교한다면 0001 4개만 비교하도록 `db.TABLES[:4]` 로 고친다 — grep 으로 확인).

- [ ] **Step 7: 전체 테스트 + 실DB 적용**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests -q`
Expected: **282 passed** (277 + 5). 실측 우선.

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli db apply`
Expected: `적용 1건: 0004_decisions`. 재실행 시 `적용할 마이그레이션이 없습니다`.

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli db check`
Expected: 표에 `readings`·`ambiguities`·`decisions` 행이 RLS `on` 으로 나오고, 마지막 줄 `decisions=0 provisional=0 published=0/63`.

Run(트리거 실증, 읽기 전용 확인만 — 삽입은 웹에서): heredoc 으로 `select tgname from pg_trigger where tgname='decisions_apply'`, `select id, public from storage.buckets where id='crops'` 조회 → 각 1행.

- [ ] **Step 8: 커밋**

```bash
git add supabase/migrations/0004_decisions.sql worker/tests/test_migration_0004.py contracts/db.types.ts worker/src/m3d/db.py worker/src/m3d/cli.py
git commit -m "feat(db): 0004_decisions — 결정 이력·상태 트리거·crops 버킷 + 타입 계약

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AZoYNTVPox7g1d6oJd5Wo1"
```

---

### Task 2: 결정 보존(replace_region) + `m3d publish` 크롭 업로드

**Files:**
- Modify: `worker/src/m3d/reading/store.py` (`replace_region`)
- Modify: `worker/tests/test_reading_store.py` (FakeDb·FakeCursor·테스트 2건)
- Modify: `worker/src/m3d/cli.py` (`read`·`review` 출력에 `보호`, `publish` 명령)
- Modify: `worker/tests/test_cli_reading.py` (가짜 replace_region 반환에 `protected`)
- Create: `worker/src/m3d/reading/publish.py`
- Create: `worker/tests/test_reading_publish.py`

**Interfaces:**
- Consumes: `store.replace_region(cfg, dataset, region, rows_r, rows_a) -> dict`(기존), `samples.manifest.sha256_file(path)`, `Config.supabase_url`/`supabase_service_key`/`require_db_url()`/`repo_root`.
- Produces: `replace_region` 반환 dict 에 `protected: int`; `publish.run_publish(cfg, dataset, *, force=False) -> {"uploaded","skipped","failures","total"}`; `publish.object_key(slug, amb_id) -> "<slug>/<id>.png"`; `publish._upload(url, headers, data) -> (status, body)`; CLI `m3d publish <dataset> [--force]`.

- [ ] **Step 1: 보존 테스트 (실패)**

`worker/tests/test_reading_store.py`:
- `FakeDb.__init__(self, ambiguities=(), decisions=())` 로 확장하고 `self.decisions = list(decisions)` 저장.
- `FakeCursor.execute` 분기에 추가(기존 `select id, basis_sheet_id` 분기 **앞**):

```python
        elif s.startswith("select distinct ambiguity_id from decisions"):
            self._rows = [(d,) for d in self.db.decisions]
```

- `delete from ambiguities` 분기를 보호 id 를 남기도록 바꾼다:

```python
        elif s.startswith("delete from ambiguities"):
            protected = set(params[2]) if params and len(params) > 2 else set()
            self.db.ambiguities = [a for a in self.db.ambiguities if a[0] in protected]
```

- 테스트 2건 추가:

```python
def test_decided_ambiguity_is_protected_from_delete_and_reinsert(cfg, monkeypatch):
    """결정이 달린 ambiguity 는 재판독이 지우지도 덮어쓰지도 않는다 (M2b 설계 D3)."""
    db = FakeDb(ambiguities=[("kept-id", "s-b01", "p-b01-1", "해석", BBOX,
                              "data/derived/ds/crops/kept-id.png")],
                decisions=["kept-id"])
    _patch(monkeypatch, db)
    _rows_r, rows_a = build_rows("B", [], [_a("해석")], round_no=3)
    res = store.replace_region(cfg, "ds", "B", [], rows_a)
    assert res["protected"] == 1 and res["ambiguities"] == 0 and res["kept"] == 0
    delete_sql, delete_params = next((s, p) for s, p in db.sql
                                     if s.startswith("delete from ambiguities"))
    assert "id <> all(%s::uuid[])" in delete_sql and delete_params[2] == ["kept-id"]
    assert db.inserted_a == []                      # 같은 자연키 행도 재삽입하지 않는다
    assert db.ambiguities[0][0] == "kept-id"        # 원래 행 그대로


def test_undecided_rows_still_replaced_when_others_protected(cfg, monkeypatch):
    db = FakeDb(ambiguities=[("kept-id", "s-b01", "p-b01-1", "해석", BBOX, None),
                             ("old-id", "s-b02", "p-b02-1", "다른", BBOX, None)],
                decisions=["kept-id"])
    _patch(monkeypatch, db)
    _rows_r, rows_a = build_rows("B", [], [_a("해석"), _a("다른", ord_="B02")], round_no=3)
    res = store.replace_region(cfg, "ds", "B", [], rows_a)
    assert res["protected"] == 1 and res["ambiguities"] == 1 and res["kept"] == 1
    assert [p[0] for p in db.inserted_a] == ["old-id"]  # 미결정 행만 자연키로 id 승계 재삽입
```

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_reading_store.py -q`
Expected: 2 failed (`KeyError: 'protected'` 등), 나머지 통과.

- [ ] **Step 2: replace_region 수정**

`worker/src/m3d/reading/store.py` `replace_region`:
- 시그니처 docstring 에 한 줄 추가: "결정(decisions)이 달린 ambiguity 는 삭제·재삽입하지 않는다 — 사용자 답변이 재판독보다 우선(M2b 설계 D3)."
- `kept = failed = 0` → `kept = failed = protected = 0`.
- keep-맵 SELECT **앞**에:

```python
            # 보호 집합: 결정이 달린 ambiguity (M2b D3) — 삭제·덮어쓰기 금지
            cur.execute("select distinct ambiguity_id from decisions where project_id = %s",
                        (project_id,))
            protected_ids = [str(r[0]) for r in cur.fetchall()]
```

- keep-맵 생성 직후:

```python
            protected_keys = {k for k, (aid, _crop) in keep.items() if str(aid) in protected_ids}
```

- ambiguities DELETE 를 다음으로 교체:

```python
            # rows_a 가 비어도 무조건 실행한다 — 옛 행 잔존이 멱등을 깬다. 보호 id 는 남긴다.
            cur.execute(
                "delete from ambiguities where project_id = %s and basis_sheet_id = any(%s) "
                "and id <> all(%s::uuid[])",
                (project_id, region_sheet_ids, protected_ids))
```

- ambiguity 삽입 루프에서 `old = keep.get(...)` **앞**에:

```python
                if _natural_key(sid, pid, a.item, a.mm_bbox) in protected_keys:
                    protected += 1
                    continue
```

- 반환: `{"readings": n_r, "ambiguities": n_a, "kept": kept, "failed": failed, "protected": protected}`.

`worker/src/m3d/cli.py`: `read`·`review` 가 `replace_region` 결과를 출력하는 f-string 두 곳에서 `미해석` 항목 앞에 ` / 보호 {res['protected']}` 를 넣는다(변수명은 해당 코드의 결과 dict 이름을 따른다). `worker/tests/test_cli_reading.py` 의 가짜 `replace_region` 이 돌려주는 dict 마다 `"protected": 0` 을 추가한다.

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_reading_store.py worker/tests/test_cli_reading.py -q`
Expected: 전부 통과.

- [ ] **Step 3: publish 테스트 (실패)**

`worker/tests/test_reading_publish.py`:

```python
"""m3d publish — 크롭 PNG 를 비공개 Storage 버킷에 올리고 assets.storage_path 를 채운다."""

import dataclasses

import pytest

from m3d.config import load_config
from m3d.reading import publish
from m3d.samples.manifest import sha256_file

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class FakeDb:
    def __init__(self, rows=()):
        self.rows = list(rows)          # (amb_id, crop_rel_path, assets.sha256, assets.storage_path)
        self.sql = []
        self.committed = False


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self._rows = []

    def execute(self, sql, params=None):
        s = " ".join(sql.split())
        self.db.sql.append((s, params))
        self._rows = []
        if s.startswith("select id from projects"):
            self._rows = [("proj-1",)]
        elif s.startswith("select a.id, a.crop_rel_path"):
            self._rows = list(self.db.rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

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
        self.db.committed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://fake/none")
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-test-key")
    cfg = load_config(env_file=tmp_path / "absent.env")
    return dataclasses.replace(cfg, repo_root=tmp_path)


def _crop(cfg, amb_id):
    rel = f"data/derived/ds/crops/{amb_id}.png"
    path = cfg.repo_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG)
    return rel, sha256_file(path)


def _patch(monkeypatch, db, status=200):
    calls = []

    def fake_upload(url, headers, data):
        calls.append((url, headers, data))
        return status, "{}"

    monkeypatch.setattr(publish.psycopg, "connect", lambda *a, **k: FakeConn(db))
    monkeypatch.setattr(publish, "_upload", fake_upload)
    return calls


def test_uploads_with_service_key_headers_and_updates_storage_path(cfg, monkeypatch):
    rel, sha = _crop(cfg, "amb-1")
    db = FakeDb(rows=[("amb-1", rel, sha, None)])
    calls = _patch(monkeypatch, db)
    r = publish.run_publish(cfg, "ds")
    assert r == {"uploaded": 1, "skipped": 0, "failures": [], "total": 1}
    url, headers, data = calls[0]
    assert url == "https://fake.supabase.co/storage/v1/object/crops/ds/amb-1.png"
    assert headers["Authorization"] == "Bearer service-test-key"
    assert headers["apikey"] == "service-test-key"
    assert headers["x-upsert"] == "true" and headers["Content-Type"] == "image/png"
    assert data == PNG
    upd = next((s, p) for s, p in db.sql if s.startswith("update assets set storage_path"))
    assert upd[1] == ("crops/ds/amb-1.png", "proj-1", rel)
    assert db.committed


def test_skips_when_already_published_with_same_sha(cfg, monkeypatch):
    rel, sha = _crop(cfg, "amb-1")
    db = FakeDb(rows=[("amb-1", rel, sha, "crops/ds/amb-1.png")])
    calls = _patch(monkeypatch, db)
    r = publish.run_publish(cfg, "ds")
    assert r["skipped"] == 1 and r["uploaded"] == 0 and calls == []


def test_force_reuploads_even_if_published(cfg, monkeypatch):
    rel, sha = _crop(cfg, "amb-1")
    db = FakeDb(rows=[("amb-1", rel, sha, "crops/ds/amb-1.png")])
    calls = _patch(monkeypatch, db)
    r = publish.run_publish(cfg, "ds", force=True)
    assert r["uploaded"] == 1 and len(calls) == 1


def test_http_error_counts_as_failure_without_db_update(cfg, monkeypatch):
    rel, sha = _crop(cfg, "amb-1")
    db = FakeDb(rows=[("amb-1", rel, sha, None)])
    _patch(monkeypatch, db, status=403)
    r = publish.run_publish(cfg, "ds")
    assert r["uploaded"] == 0 and len(r["failures"]) == 1 and "HTTP 403" in r["failures"][0][1]
    assert not any(s.startswith("update assets") for s, _ in db.sql)


def test_missing_file_counts_as_failure(cfg, monkeypatch):
    db = FakeDb(rows=[("amb-1", "data/derived/ds/crops/amb-1.png", "0" * 64, None)])
    calls = _patch(monkeypatch, db)
    r = publish.run_publish(cfg, "ds")
    assert calls == [] and r["failures"] == [("amb-1", "크롭 파일 없음 — crops 먼저")]


def test_requires_url_and_service_key(cfg, monkeypatch):
    monkeypatch.setattr(publish.psycopg, "connect", lambda *a, **k: FakeConn(FakeDb()))
    bad = dataclasses.replace(cfg, supabase_service_key=None)
    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        publish.run_publish(bad, "ds")
```

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_reading_publish.py -q`
Expected: 수집 오류 `ImportError: cannot import name 'publish'`.

- [ ] **Step 4: publish.py 작성**

`worker/src/m3d/reading/publish.py`:

```python
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
```

- [ ] **Step 5: CLI `publish` 명령**

`worker/src/m3d/cli.py`: import 블록에 `from m3d.reading import publish as publish_run` 추가(명령 함수 `publish` 와 이름 충돌 회피). `crops` 명령 뒤에:

```python
@app.command()
def publish(
    dataset: str = typer.Argument(..., help="데이터셋 슬러그"),
    force: bool = typer.Option(False, "--force", help="이미 올라가 있어도 재업로드"),
) -> None:
    """[5] 크롭 PNG 를 비공개 Storage 버킷 crops 에 업로드 — 질문 카드 이미지 (M2b 설계 §4-1)."""
    cfg = load_config()
    try:
        r = publish_run.run_publish(cfg, dataset, force=force)
    except RuntimeError as exc:
        typer.echo(f"실패: {exc}")
        raise typer.Exit(code=1) from None
    typer.echo(f"업로드 {r['uploaded']}건 / 스킵 {r['skipped']}건 / 실패 {len(r['failures'])}건 / 전체 {r['total']}건")
    typer.echo(f"uploaded={r['uploaded']} skipped={r['skipped']} failures={len(r['failures'])} total={r['total']}")
    for aid, err in r["failures"]:
        typer.echo(f"  실패 {aid}: {err}")
    raise typer.Exit(code=1 if r["failures"] else 0)
```

- [ ] **Step 6: 테스트 전건 + 실업로드**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests -q`
Expected: **290 passed** (282 + store 2 + publish 6). 실측 우선.

Run(실Storage, 63장 ≈ 수십 초): `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli publish ab1-p4p5`
Expected: `uploaded=63 skipped=0 failures=0 total=63`. 재실행 → `uploaded=0 skipped=63`. `db check` 마지막 줄 `published=63/63`.

Run(보존 실증, $0): `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli review ab1-p4p5 --region B --cache-only`
Expected: 출력에 `보호 0`(아직 결정 없음) 이 포함되고 `합계 비용 $0.0000 / 실패 0건`.

- [ ] **Step 7: 커밋**

```bash
git add worker/src/m3d/reading/store.py worker/src/m3d/reading/publish.py worker/src/m3d/cli.py worker/tests/test_reading_store.py worker/tests/test_reading_publish.py worker/tests/test_cli_reading.py
git commit -m "feat(reading): 결정 보존 replace_region + m3d publish 크롭 Storage 업로드

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AZoYNTVPox7g1d6oJd5Wo1"
```

---

### Task 3: `m3d ssot` 치수 정본 문서

**Files:**
- Create: `worker/src/m3d/reading/ssot.py`
- Create: `worker/tests/test_reading_ssot.py`
- Modify: `worker/src/m3d/cli.py` (`ssot` 명령)

**Interfaces:**
- Consumes: DB 테이블 projects·readings·ambiguities·decisions·sheets·sheet_pages; `Config.derived_dir`.
- Produces: `ssot.fetch_ssot_inputs(conn, dataset) -> (project, readings, ambiguities)`; `ssot.build_ssot(project, readings, ambiguities) -> (body_md: str, doc: dict)` (순수); `ssot.run_ssot(cfg, dataset) -> {"changed", "version", "path", "counts"}`; 파일 `data/derived/<dataset>/ssot/{실측정리_v<N>.md, ssot.json, index.json}`; CLI `m3d ssot <dataset>`. `ssot.json` 최상위 키: `version, generated_at, project, readings, decisions, open, counts`.

- [ ] **Step 1: 테스트 (실패)**

`worker/tests/test_reading_ssot.py`:

```python
"""m3d ssot — 판독값·결정을 합친 치수 정본 문서(실측정리) 생성."""

import dataclasses
import json

import pytest

from m3d.config import load_config
from m3d.reading import ssot

PROJECT = {"slug": "ds", "name": "테스트교", "coord_system": {"unit": "m"},
           "coord_assumptions": ["P4 STA 정정"]}
READINGS = [
    {"region": "B", "ord": "B01", "page_no": 1, "item": "전체 폭원", "value_raw": "15,700",
     "unit": "mm", "status": "확정", "mm_bbox": [1.0, 2.0, 3.0, 4.0], "crosscheck": {"expr": "5,600+4,500+5,600=15,700"}},
    {"region": "B", "ord": "B01", "page_no": 1, "item": "교량 총길이", "value_raw": "684,280",
     "unit": "mm", "status": "추정", "mm_bbox": [1, 2, 3, 4], "crosscheck": None},
    {"region": "C", "ord": "C01", "page_no": 1, "item": "형고", "value_raw": "4,000",
     "unit": "mm", "status": "검토지적", "mm_bbox": [1, 2, 3, 4], "crosscheck": None},
]
OPTS = [{"label": "순두께", "basis": "단면 C-C"}, {"label": "포장 포함", "basis": "표기 관례"}]
AMBS = [
    {"id": "amb-1", "ord": "B01", "page_no": 1, "item": "슬래브 두께 의미", "options": OPTS,
     "model_impact": "자중 44% 차이", "status": "결정", "choice_index": 1, "choice_label": "포장 포함",
     "provisional": False, "note": "현장 확인", "decided_at": "2026-09-05T10:00:00+00:00"},
    {"id": "amb-2", "ord": "B02", "page_no": 2, "item": "방호벽 대칭", "options": OPTS,
     "model_impact": "패밀리 1종", "status": "잠정", "choice_index": 0,
     "choice_label": "모르겠다 — 권장대로 진행, 나중에 확인", "provisional": True, "note": "",
     "decided_at": "2026-09-05T10:05:00+00:00"},
    {"id": "amb-3", "ord": "C01", "page_no": 1, "item": "형고 의미", "options": OPTS,
     "model_impact": "내공/전강고", "status": "대기", "choice_index": None, "choice_label": None,
     "provisional": None, "note": None, "decided_at": None},
]


def test_build_ssot_sections_and_counts():
    body, doc = ssot.build_ssot(PROJECT, READINGS, AMBS)
    for head in ("## 0. 좌표계·가정", "## 1. 확정 (1건)", "## 2. 추정 (1건)", "## 3. 검토지적 (1건)",
                 "## 4. 결정 (2건 — 잠정 1건)", "## 5. 미결 (1건)", "## 6. 통계"):
        assert head in body, head
    assert "| 전체 폭원 | 15,700 | mm | B01 p1 [1, 2, 3, 4] | 5,600+4,500+5,600=15,700 |" in body
    assert "### [결정] 슬래브 두께 의미 — B01 p1" in body and "- 선택: 포장 포함 — 근거: 표기 관례" in body
    assert "### [잠정] 방호벽 대칭 — B02 p2" in body
    assert "- (0) 순두께 — 단면 C-C" in body            # 미결 절은 선택지 전부 나열
    assert doc["counts"] == {"readings": {"확정": 1, "추정": 1, "검토지적": 1},
                             "decided": 2, "provisional": 1, "open": 1}
    assert doc["decisions"][0]["basis"] == "표기 관례" and doc["open"][0]["ambiguity_id"] == "amb-3"
    assert "generated" not in body                       # 본문은 시각을 담지 않는다(해시 안정)


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self._rows = []

    def execute(self, sql, params=None):
        s = " ".join(sql.split())
        self.db.sql.append(s)
        self._rows = []
        if s.startswith("select id, slug, name, coord_system, coord_assumptions from projects"):
            p = self.db.project
            self._rows = [("proj-1", p["slug"], p["name"], p["coord_system"], p["coord_assumptions"])]
        elif s.startswith("select r.region, s.ord, sp.page_no"):
            self._rows = [tuple(r[k] for k in ("region", "ord", "page_no", "item", "value_raw",
                                                 "unit", "status", "mm_bbox", "crosscheck"))
                          for r in self.db.readings]
        elif s.startswith("select a.id, s.ord, sp.page_no"):
            self._rows = [tuple(a[k] for k in ("id", "ord", "page_no", "item", "options", "model_impact",
                                                 "status", "choice_index", "choice_label", "provisional",
                                                 "note", "decided_at"))
                          for a in self.db.ambiguities]

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeDb:
    def __init__(self, project, readings, ambiguities):
        self.project, self.readings, self.ambiguities = project, list(readings), list(ambiguities)
        self.sql = []


class FakeConn:
    def __init__(self, db):
        self.db = db

    def cursor(self):
        return FakeCursor(self.db)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://fake/none")
    cfg = load_config(env_file=tmp_path / "absent.env")
    return dataclasses.replace(cfg, repo_root=tmp_path)


def test_run_ssot_writes_v1_then_no_change_then_v2(cfg, monkeypatch):
    db = FakeDb(PROJECT, READINGS, AMBS)
    monkeypatch.setattr(ssot.psycopg, "connect", lambda *a, **k: FakeConn(db))
    out = cfg.derived_dir / "ds" / "ssot"

    r1 = ssot.run_ssot(cfg, "ds")
    assert r1["changed"] is True and r1["version"] == 1
    assert (out / "실측정리_v1.md").is_file() and (out / "ssot.json").is_file()
    doc = json.loads((out / "ssot.json").read_text(encoding="utf-8"))
    assert doc["version"] == 1 and set(doc) >= {"generated_at", "project", "readings", "decisions", "open", "counts"}

    r2 = ssot.run_ssot(cfg, "ds")
    assert r2["changed"] is False and r2["version"] == 1
    assert not (out / "실측정리_v2.md").exists()

    db.ambiguities[2] = {**AMBS[2], "status": "결정", "choice_index": 0, "choice_label": "순두께",
                         "provisional": False, "note": "", "decided_at": "2026-09-05T11:00:00+00:00"}
    r3 = ssot.run_ssot(cfg, "ds")
    assert r3["changed"] is True and r3["version"] == 2
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert [i["version"] for i in index] == [1, 2] and index[1]["counts"]["open"] == 0


def test_run_ssot_requires_project(cfg, monkeypatch):
    class NoProjectCursor(FakeCursor):
        def execute(self, sql, params=None):
            super().execute(sql, params)
            if sql.lstrip().startswith("select id, slug"):
                self._rows = []

    db = FakeDb(PROJECT, [], [])

    class Conn(FakeConn):
        def cursor(self):
            return NoProjectCursor(self.db)

    monkeypatch.setattr(ssot.psycopg, "connect", lambda *a, **k: Conn(db))
    with pytest.raises(RuntimeError, match="없음"):
        ssot.run_ssot(cfg, "ds")
```

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_reading_ssot.py -q`
Expected: 수집 오류 `ImportError: cannot import name 'ssot'`.

- [ ] **Step 2: ssot.py 작성**

`worker/src/m3d/reading/ssot.py`:

```python
"""m3d ssot — 치수 정본(실측정리) 문서 생성 (M2b 설계서 §4-2, 지식베이스 §2·§7).

판독값(확정/추정/검토지적)과 사용자 결정(결정/잠정)·미결을 한 문서로 묶는다. 모든 수치에
근거 도면(ord·page·mm_bbox)을 병기한다. 본문 해시가 바뀔 때만 버전이 오른다 — 재실행이
문서를 늘리지 않는다. 결정은 판독값을 고치지 않고 병기한다(설계 D4).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import psycopg

from m3d.config import Config

STATUS_ORDER = ("확정", "추정", "검토지적")
READING_KEYS = ("region", "ord", "page_no", "item", "value_raw", "unit", "status", "mm_bbox", "crosscheck")
AMB_KEYS = ("id", "ord", "page_no", "item", "options", "model_impact", "status",
            "choice_index", "choice_label", "provisional", "note", "decided_at")


def fetch_ssot_inputs(conn, dataset: str) -> tuple[dict, list[dict], list[dict]]:
    """DB 에서 프로젝트·판독·애매성(최신 결정 조인)을 읽는다."""
    with conn.cursor() as cur:
        cur.execute("select id, slug, name, coord_system, coord_assumptions from projects where slug = %s",
                    (dataset,))
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(f"프로젝트 '{dataset}' 없음 — seed 먼저")
        project_id, slug, name, coord_system, coord_assumptions = row
        project = {"slug": slug, "name": name, "coord_system": coord_system,
                   "coord_assumptions": list(coord_assumptions or [])}

        cur.execute(
            "select r.region, s.ord, sp.page_no, r.item, r.value_raw, r.unit, r.status, "
            "       r.basis_mm_bbox, r.crosscheck "
            "from readings r join sheets s on s.id = r.basis_sheet_id "
            "left join sheet_pages sp on sp.id = r.basis_page_id "
            "where r.project_id = %s order by r.region, s.ord, sp.page_no, r.item", (project_id,))
        readings = [dict(zip(READING_KEYS, r)) for r in cur.fetchall()]

        cur.execute(
            "select a.id, s.ord, sp.page_no, a.item, a.options, a.model_impact, a.status, "
            "       d.choice_index, d.choice_label, d.provisional, d.note, d.decided_at "
            "from ambiguities a join sheets s on s.id = a.basis_sheet_id "
            "left join sheet_pages sp on sp.id = a.sheet_page_id "
            "left join lateral (select choice_index, choice_label, provisional, note, decided_at "
            "                   from decisions where ambiguity_id = a.id "
            "                   order by decided_at desc limit 1) d on true "
            "where a.project_id = %s order by s.ord, sp.page_no, a.item", (project_id,))
        ambiguities = [dict(zip(AMB_KEYS, r)) for r in cur.fetchall()]
    return project, readings, ambiguities


def _bbox(b) -> str:
    return "[" + ", ".join(f"{float(v):g}" for v in (b or [])) + "]"


def _crosscheck(c) -> str:
    if not c:
        return ""
    return str(c.get("expr", "")) if isinstance(c, dict) else str(c)


def _iso(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


def build_ssot(project: dict, readings: list[dict], ambiguities: list[dict]) -> tuple[str, dict]:
    """(마크다운 본문, JSON dict). 본문에는 생성 시각을 넣지 않는다 — 해시가 안정돼야 한다."""
    lines = [f"# 실측정리 — {project['name']} ({project['slug']})", ""]
    lines += ["## 0. 좌표계·가정", "", "```json",
              json.dumps(project["coord_system"], ensure_ascii=False, indent=2), "```", ""]
    lines += [f"- 가정·정정: {note}" for note in project["coord_assumptions"]]
    lines.append("")

    for n, status in enumerate(STATUS_ORDER, start=1):
        rows = [r for r in readings if r["status"] == status]
        lines += [f"## {n}. {status} ({len(rows)}건)", ""]
        for region in sorted({r["region"] for r in rows}):
            lines += [f"### {region} 계열", "", "| 항목 | 값 | 단위 | 근거 | 검산 |", "|---|---|---|---|---|"]
            for r in (x for x in rows if x["region"] == region):
                lines.append(f"| {r['item']} | {r['value_raw']} | {r['unit'] or ''} | "
                             f"{r['ord']} p{r['page_no']} {_bbox(r['mm_bbox'])} | {_crosscheck(r['crosscheck'])} |")
            lines.append("")

    decided = [a for a in ambiguities if a["choice_index"] is not None]
    open_ = [a for a in ambiguities if a["choice_index"] is None]
    provisional_n = sum(1 for a in decided if a["provisional"])
    lines += [f"## 4. 결정 ({len(decided)}건 — 잠정 {provisional_n}건)", ""]
    for a in decided:
        opt = a["options"][a["choice_index"]]
        kind = "잠정" if a["provisional"] else "결정"
        lines += [f"### [{kind}] {a['item']} — {a['ord']} p{a['page_no']}",
                  f"- 선택: {a['choice_label']} — 근거: {opt.get('basis', '')}",
                  f"- 모델 영향: {a['model_impact']}"]
        if a["note"]:
            lines.append(f"- 메모: {a['note']}")
        lines += [f"- 결정 시각: {_iso(a['decided_at'])}", ""]

    lines += [f"## 5. 미결 ({len(open_)}건)", ""]
    for a in open_:
        lines.append(f"### {a['item']} — {a['ord']} p{a['page_no']}")
        lines += [f"- ({i}) {o['label']} — {o['basis']}" for i, o in enumerate(a["options"])]
        lines += [f"- 모델 영향: {a['model_impact']}", ""]

    counts = {"readings": {s: sum(1 for r in readings if r["status"] == s) for s in STATUS_ORDER},
              "decided": len(decided), "provisional": provisional_n, "open": len(open_)}
    lines += ["## 6. 통계", "",
              f"- 판독 {len(readings)}건: " + ", ".join(f"{s} {counts['readings'][s]}" for s in STATUS_ORDER),
              f"- 결정 {counts['decided']}건(잠정 {counts['provisional']}), 미결 {counts['open']}건", ""]

    doc = {
        "project": project,
        "readings": [{k: r[k] for k in READING_KEYS} for r in readings],
        "decisions": [{"ambiguity_id": str(a["id"]), "ord": a["ord"], "page_no": a["page_no"],
                       "item": a["item"], "choice_index": a["choice_index"],
                       "choice_label": a["choice_label"],
                       "basis": a["options"][a["choice_index"]].get("basis", ""),
                       "provisional": bool(a["provisional"]), "model_impact": a["model_impact"],
                       "note": a["note"] or "", "decided_at": _iso(a["decided_at"])} for a in decided],
        "open": [{"ambiguity_id": str(a["id"]), "ord": a["ord"], "page_no": a["page_no"],
                  "item": a["item"], "options": a["options"], "model_impact": a["model_impact"]}
                 for a in open_],
        "counts": counts,
    }
    return "\n".join(lines), doc


def run_ssot(cfg: Config, dataset: str) -> dict:
    """문서를 생성한다. 본문 해시가 마지막 버전과 같으면 아무것도 쓰지 않는다."""
    with psycopg.connect(cfg.require_db_url()) as conn:
        project, readings, ambiguities = fetch_ssot_inputs(conn, dataset)
    body, doc = build_ssot(project, readings, ambiguities)

    out_dir = cfg.derived_dir / dataset / "ssot"
    out_dir.mkdir(parents=True, exist_ok=True)
    index_path = out_dir / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else []
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if index and index[-1]["sha256"] == sha:
        v = index[-1]["version"]
        return {"changed": False, "version": v, "path": str(out_dir / f"실측정리_v{v}.md"),
                "counts": doc["counts"]}

    version = (index[-1]["version"] + 1) if index else 1
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    md_path = out_dir / f"실측정리_v{version}.md"
    md_path.write_text(f"<!-- version {version} · generated {generated_at} -->\n" + body, encoding="utf-8")
    (out_dir / "ssot.json").write_text(
        json.dumps({"version": version, "generated_at": generated_at, **doc},
                   ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    index.append({"version": version, "sha256": sha, "generated_at": generated_at, "counts": doc["counts"]})
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"changed": True, "version": version, "path": str(md_path), "counts": doc["counts"]}
```

- [ ] **Step 3: CLI `ssot` 명령**

`worker/src/m3d/cli.py`: import 에 `from m3d.reading import ssot as ssot_run`. `publish` 명령 뒤에:

```python
@app.command()
def ssot(dataset: str = typer.Argument(..., help="데이터셋 슬러그")) -> None:
    """[5] 치수 정본(실측정리) 문서 생성 — 판독값 + 결정 + 미결 (M2b 설계 §4-2)."""
    cfg = load_config()
    try:
        r = ssot_run.run_ssot(cfg, dataset)
    except RuntimeError as exc:
        typer.echo(f"실패: {exc}")
        raise typer.Exit(code=1) from None
    c = r["counts"]
    typer.echo(f"실측정리 v{r['version']} {'생성' if r['changed'] else '변경 없음'}: {r['path']}")
    typer.echo(f"ssot_version={r['version']} changed={str(r['changed']).lower()} "
               f"readings={sum(c['readings'].values())} decided={c['decided']} "
               f"provisional={c['provisional']} open={c['open']}")
```

- [ ] **Step 4: 테스트 전건 + 실행**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests -q`
Expected: **293 passed** (290 + 3). 실측 우선.

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli ssot ab1-p4p5`
Expected: `실측정리 v1 생성: …/ssot/실측정리_v1.md`, `ssot_version=1 changed=true readings=282 decided=0 provisional=0 open=63`. 재실행 → `변경 없음`, `changed=false`. `실측정리_v1.md` 를 열어 §1 표에 B01 전체 폭원 15,700 이 근거와 함께 있는지 확인.

- [ ] **Step 5: 커밋**

```bash
git add worker/src/m3d/reading/ssot.py worker/tests/test_reading_ssot.py worker/src/m3d/cli.py
git commit -m "feat(reading): m3d ssot — 치수 정본(실측정리) 문서 생성

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AZoYNTVPox7g1d6oJd5Wo1"
```

---

### Task 4: 웹 기반 — 라우터·인증·데이터 접근·순수 로직(vitest)

**Files:**
- Modify: `web/package.json` (deps·scripts), `web/src/main.tsx`, `web/src/App.tsx`
- Create: `web/vitest.config.ts`, `web/src/auth/AuthGate.tsx`, `web/src/auth/LoginScreen.tsx`, `web/src/lib/decisions.ts`, `web/src/lib/decisions.test.ts`, `web/src/lib/questions.ts`, `web/src/routes/Projects.tsx`, `web/src/routes/Questions.tsx`(자리표시 — Task 5 가 채움)

**Interfaces:**
- Consumes: `web/src/lib/supabase.ts` 의 `supabase: SupabaseClient<Database> | null`, `missingEnv`; `contracts/db.types.ts` 의 `decisions` 타입(Task 1).
- Produces: `useSession()`; `decisions.ts` 의 `Option, Choice, DecisionRow, DecisionInsert, UNSURE_LABEL, latestByAmbiguity, decisionPayload, choiceFromKey`; `questions.ts` 의 `Question, ProjectRef, fetchProject, fetchQuestions, submitDecision, cropSignedUrl, cropObjectKey`; 경로 `/`(Projects)·`/p/:slug/questions`·`/health`.

- [ ] **Step 1: 의존성 설치·스크립트**

Run(웹 디렉터리에서): `cd web && npm install react-router-dom@^6.28 && npm install -D vitest@^2.1`
Expected: `package.json` dependencies 에 `react-router-dom`, devDependencies 에 `vitest`. `package-lock.json` 갱신.

`web/package.json` scripts 에 `"test": "vitest run"` 추가.

`web/vitest.config.ts`:

```ts
import { defineConfig } from 'vitest/config';

// 순수 로직(lib/*.test.ts)만 돌린다 — 컴포넌트 렌더 테스트는 브라우저 E2E 로 대체 (설계서 §6)
export default defineConfig({
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
});
```

- [ ] **Step 2: 순수 로직 테스트 (실패)**

`web/src/lib/decisions.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { choiceFromKey, decisionPayload, latestByAmbiguity, UNSURE_LABEL, type DecisionRow } from './decisions';

const OPTS = [{ label: '순두께', basis: '단면 C-C' }, { label: '포장 포함', basis: '표기 관례' }];
const row = (over: Partial<DecisionRow>): DecisionRow => ({
  id: 'd', ambiguity_id: 'a', choice_index: 0, choice_label: '순두께', provisional: false,
  note: '', decided_at: '2026-09-05T10:00:00+00:00', ...over,
});

describe('latestByAmbiguity', () => {
  it('입력 순서와 무관하게 decided_at 최신 행을 고른다', () => {
    const m = latestByAmbiguity([
      row({ id: 'old', decided_at: '2026-09-05T10:00:00+00:00' }),
      row({ id: 'new', decided_at: '2026-09-05T11:00:00+00:00' }),
      row({ id: 'other', ambiguity_id: 'b' }),
    ]);
    expect(m.get('a')?.id).toBe('new');
    expect(m.get('b')?.id).toBe('other');
  });
});

describe('decisionPayload', () => {
  it('선택지 인덱스 → label 스냅샷, provisional false', () => {
    const p = decisionPayload({ projectId: 'p', ambiguityId: 'a', options: OPTS, choice: 1, note: '메모' });
    expect(p).toEqual({ project_id: 'p', ambiguity_id: 'a', choice_index: 1, choice_label: '포장 포함', provisional: false, note: '메모' });
  });
  it('"모르겠다" 는 권장안(0번) + provisional true + 고정 label', () => {
    const p = decisionPayload({ projectId: 'p', ambiguityId: 'a', options: OPTS, choice: 'unsure' });
    expect(p.choice_index).toBe(0);
    expect(p.provisional).toBe(true);
    expect(p.choice_label).toBe(UNSURE_LABEL);
    expect(p.note).toBe('');
  });
  it('범위 밖 인덱스는 RangeError', () => {
    expect(() => decisionPayload({ projectId: 'p', ambiguityId: 'a', options: OPTS, choice: 2 })).toThrow(RangeError);
    expect(() => decisionPayload({ projectId: 'p', ambiguityId: 'a', options: [], choice: 0 })).toThrow(RangeError);
  });
});

describe('choiceFromKey', () => {
  it('1~4 → 인덱스, 0 → unsure, 범위 밖·기타 → null', () => {
    expect(choiceFromKey('1', 3)).toBe(0);
    expect(choiceFromKey('3', 3)).toBe(2);
    expect(choiceFromKey('4', 3)).toBeNull();
    expect(choiceFromKey('0', 3)).toBe('unsure');
    expect(choiceFromKey('a', 3)).toBeNull();
  });
});
```

Run: `cd web && npm run test`
Expected: FAIL — `./decisions` 모듈 없음.

- [ ] **Step 3: decisions.ts**

`web/src/lib/decisions.ts`:

```ts
// 결정 페이로드·축약 — 순수 로직 (M2b 설계서 §5, 지식베이스 §4).
// 권장안은 항상 options[0] 이다(판독 프롬프트가 그렇게 낸다). "모르겠다" 는 권장안을 잠정 채택한다.

export interface Option {
  label: string;
  basis: string;
}

export type Choice = number | 'unsure';

export const UNSURE_LABEL = '모르겠다 — 권장대로 진행, 나중에 확인';

export interface DecisionRow {
  id: string;
  ambiguity_id: string;
  choice_index: number;
  choice_label: string;
  provisional: boolean;
  note: string;
  decided_at: string;
}

export interface DecisionInsert {
  project_id: string;
  ambiguity_id: string;
  choice_index: number;
  choice_label: string;
  provisional: boolean;
  note: string;
}

/** ambiguity 별 최신 결정 (decided_at 최대). 입력 정렬에 의존하지 않는다. */
export function latestByAmbiguity(rows: DecisionRow[]): Map<string, DecisionRow> {
  const latest = new Map<string, DecisionRow>();
  for (const r of rows) {
    const cur = latest.get(r.ambiguity_id);
    if (!cur || r.decided_at > cur.decided_at) latest.set(r.ambiguity_id, r);
  }
  return latest;
}

export function decisionPayload(p: {
  projectId: string;
  ambiguityId: string;
  options: Option[];
  choice: Choice;
  note?: string;
}): DecisionInsert {
  if (p.options.length === 0) throw new RangeError('선택지가 없습니다');
  const base = { project_id: p.projectId, ambiguity_id: p.ambiguityId, note: p.note ?? '' };
  if (p.choice === 'unsure') {
    return { ...base, choice_index: 0, choice_label: UNSURE_LABEL, provisional: true };
  }
  if (!Number.isInteger(p.choice) || p.choice < 0 || p.choice >= p.options.length) {
    throw new RangeError(`choice_index ${String(p.choice)} 범위 밖 (선택지 ${p.options.length}개)`);
  }
  return { ...base, choice_index: p.choice, choice_label: p.options[p.choice].label, provisional: false };
}

/** 키보드: '1'~'4' → 선택지 인덱스, '0' → 모르겠다, 그 외 null. */
export function choiceFromKey(key: string, optionCount: number): Choice | null {
  if (key === '0') return 'unsure';
  const n = Number(key);
  if (Number.isInteger(n) && n >= 1 && n <= Math.min(optionCount, 4)) return n - 1;
  return null;
}
```

Run: `cd web && npm run test`
Expected: 4 test files? — 1 file, 5 tests passed.

- [ ] **Step 4: questions.ts (데이터 접근)**

`web/src/lib/questions.ts`:

```ts
// Supabase 데이터 접근 — 로그인 세션의 RLS 아래에서만 동작한다 (M2b 설계서 §5).
import type { SupabaseClient } from '@supabase/supabase-js';

import type { Database } from '../../../contracts/db.types';
import { latestByAmbiguity, type DecisionInsert, type DecisionRow, type Option } from './decisions';

export type Client = SupabaseClient<Database>;
export type AmbiguityStatus = '대기' | '결정' | '잠정';

export interface ProjectRef {
  id: string;
  slug: string;
  name: string;
}

export interface Question {
  id: string;
  item: string;
  options: Option[];
  modelImpact: string;
  status: AmbiguityStatus;
  ord: string;
  pageNo: number | null;
  region: string;
  latest: DecisionRow | null;
  history: DecisionRow[];
}

interface AmbiguityJoined {
  id: string;
  item: string;
  options: Option[];
  model_impact: string;
  status: AmbiguityStatus;
  sheets: { ord: string } | null;
  sheet_pages: { page_no: number } | null;
}

export function cropObjectKey(slug: string, ambiguityId: string): string {
  // worker publish.object_key 와 같은 규칙
  return `${slug}/${ambiguityId}.png`;
}

export async function fetchProjects(client: Client): Promise<ProjectRef[]> {
  const { data, error } = await client.from('projects').select('id,slug,name').order('slug');
  if (error) throw new Error(error.message);
  return data ?? [];
}

export async function fetchProject(client: Client, slug: string): Promise<ProjectRef> {
  const { data, error } = await client.from('projects').select('id,slug,name').eq('slug', slug).maybeSingle();
  if (error) throw new Error(error.message);
  if (!data) throw new Error(`프로젝트 없음: ${slug}`);
  return data;
}

export async function fetchQuestions(client: Client, project: ProjectRef): Promise<Question[]> {
  const amb = await client
    .from('ambiguities')
    .select('id,item,options,model_impact,status,sheets(ord),sheet_pages(page_no)')
    .eq('project_id', project.id);
  if (amb.error) throw new Error(amb.error.message);
  const dec = await client
    .from('decisions')
    .select('id,ambiguity_id,choice_index,choice_label,provisional,note,decided_at')
    .eq('project_id', project.id)
    .order('decided_at', { ascending: false });
  if (dec.error) throw new Error(dec.error.message);

  const rows = (amb.data ?? []) as unknown as AmbiguityJoined[];
  const decisions = (dec.data ?? []) as DecisionRow[];
  const latest = latestByAmbiguity(decisions);
  const questions = rows.map<Question>((r) => ({
    id: r.id,
    item: r.item,
    options: r.options,
    modelImpact: r.model_impact,
    status: r.status,
    ord: r.sheets?.ord ?? '?',
    pageNo: r.sheet_pages?.page_no ?? null,
    region: (r.sheets?.ord ?? '?')[0],
    latest: latest.get(r.id) ?? null,
    history: decisions.filter((d) => d.ambiguity_id === r.id),
  }));
  return questions.sort((a, b) => a.ord.localeCompare(b.ord) || (a.pageNo ?? 0) - (b.pageNo ?? 0) || a.item.localeCompare(b.item));
}

export async function submitDecision(client: Client, payload: DecisionInsert): Promise<DecisionRow> {
  const { data, error } = await client
    .from('decisions')
    .insert(payload)
    .select('id,ambiguity_id,choice_index,choice_label,provisional,note,decided_at')
    .single();
  if (error) throw new Error(error.message);
  return data as DecisionRow;
}

export async function cropSignedUrl(client: Client, slug: string, ambiguityId: string): Promise<string> {
  const { data, error } = await client.storage.from('crops').createSignedUrl(cropObjectKey(slug, ambiguityId), 3600);
  if (error || !data) throw new Error(error?.message ?? '서명 URL 실패');
  return data.signedUrl;
}
```

- [ ] **Step 5: 인증 게이트·로그인 화면**

`web/src/auth/AuthGate.tsx`:

```tsx
// 인증 게이트 — 세션이 없으면 로그인 화면만 보인다 (참조 앱 web-app-v2 패턴 이식).
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import type { Session } from '@supabase/supabase-js';
import { Alert, Center, Code, Loader } from '@mantine/core';

import { missingEnv, supabase } from '../lib/supabase';
import { LoginScreen } from './LoginScreen';

const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error('useSession 은 AuthGate 하위에서만 사용할 수 있습니다');
  return session;
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (supabase === null) return;
    void supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setReady(true);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      setReady(true);
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  if (supabase === null) {
    return (
      <Alert m="xl" color="yellow" title="환경변수 미설정">
        .env 에 <Code>{missingEnv.join(', ')}</Code> 가 필요합니다.
      </Alert>
    );
  }
  if (!ready) {
    return (
      <Center h="100vh">
        <Loader size="sm" />
      </Center>
    );
  }
  if (!session) return <LoginScreen />;
  return <SessionContext.Provider value={session}>{children}</SessionContext.Provider>;
}
```

`web/src/auth/LoginScreen.tsx`:

```tsx
// 로그인 화면 — 이메일/비밀번호 (Supabase Auth). 성공 시 AuthGate 가 세션을 받아 자동 전환된다.
import { useState, type FormEvent } from 'react';
import { Button, Center, Paper, PasswordInput, Stack, Text, TextInput } from '@mantine/core';

import { supabase } from '../lib/supabase';

function toKoreanError(message: string): string {
  const m = message.toLowerCase();
  if (m.includes('invalid login credentials')) return '이메일 또는 비밀번호가 올바르지 않습니다';
  if (m.includes('email not confirmed')) return '이메일 인증이 완료되지 않은 계정입니다';
  if (m.includes('rate limit')) return '로그인 시도가 너무 잦습니다. 잠시 후 다시 시도해 주세요';
  if (m.includes('failed to fetch') || m.includes('network')) return '네트워크 오류 — 연결 상태를 확인해 주세요';
  return `로그인에 실패했습니다 (${message})`;
}

export function LoginScreen() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (supabase === null) return;
    if (!email.trim() || !password) {
      setError('이메일과 비밀번호를 입력해 주세요');
      return;
    }
    setBusy(true);
    setError(null);
    const { error: err } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    setBusy(false);
    if (err) setError(toKoreanError(err.message));
  }

  return (
    <Center h="100vh">
      <Paper w={360} p="lg" withBorder>
        <Text fw={700}>model3d-studio</Text>
        <Text size="xs" c="dimmed" mb="md">도면 판독 질문 카드 — 승인된 계정만 접근할 수 있습니다</Text>
        <form onSubmit={handleSubmit}>
          <Stack gap="sm">
            <TextInput label="이메일" type="email" autoComplete="username" value={email}
              onChange={(e) => setEmail(e.currentTarget.value)} data-autofocus />
            <PasswordInput label="비밀번호" autoComplete="current-password" value={password}
              onChange={(e) => setPassword(e.currentTarget.value)} />
            {error ? <Text size="xs" c="red" role="alert">{error}</Text> : null}
            <Button type="submit" fullWidth loading={busy}>로그인</Button>
          </Stack>
        </form>
      </Paper>
    </Center>
  );
}
```

- [ ] **Step 6: 라우팅·프로젝트 목록·자리표시 Questions**

`web/src/routes/Projects.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Alert, Anchor, Button, Card, Group, Stack, Text, Title } from '@mantine/core';

import { supabase } from '../lib/supabase';
import { fetchProjects, type ProjectRef } from '../lib/questions';

export function Projects() {
  const [projects, setProjects] = useState<ProjectRef[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (supabase === null) return;
    fetchProjects(supabase).then(setProjects).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <Stack m="xl" maw={720}>
      <Group justify="space-between">
        <Title order={3}>프로젝트</Title>
        <Button variant="subtle" onClick={() => void supabase?.auth.signOut()}>로그아웃</Button>
      </Group>
      {error && <Alert color="red">{error}</Alert>}
      {projects?.length === 0 && <Text c="dimmed">프로젝트가 없습니다 — worker 에서 `m3d seed` 를 실행하세요.</Text>}
      {projects?.map((p) => (
        <Card key={p.id} withBorder>
          <Text fw={600}>{p.name}</Text>
          <Anchor component={Link} to={`/p/${p.slug}/questions`}>질문 카드 열기 →</Anchor>
        </Card>
      ))}
    </Stack>
  );
}
```

`web/src/routes/Questions.tsx` (Task 5 가 교체하는 자리표시):

```tsx
import { useParams } from 'react-router-dom';
import { Text } from '@mantine/core';

export function Questions() {
  const { slug } = useParams();
  return <Text m="xl">질문 카드 — {slug} (Task 5 에서 구현)</Text>;
}
```

`web/src/App.tsx`:

```tsx
import { Route, Routes } from 'react-router-dom';

import { AuthGate } from './auth/AuthGate';
import { Health } from './routes/Health';
import { Projects } from './routes/Projects';
import { Questions } from './routes/Questions';

export function App() {
  return (
    <Routes>
      <Route path="/health" element={<Health />} />
      <Route
        path="/*"
        element={
          <AuthGate>
            <Routes>
              <Route path="/" element={<Projects />} />
              <Route path="p/:slug/questions" element={<Questions />} />
            </Routes>
          </AuthGate>
        }
      />
    </Routes>
  );
}
```

`web/src/main.tsx`: `import { BrowserRouter } from 'react-router-dom';` 추가하고 `<App />` 을 `<BrowserRouter><App /></BrowserRouter>` 로 감싼다.

- [ ] **Step 7: typecheck·test·dev 서버 기동 확인**

Run: `cd web && npm run typecheck && npm run test`
Expected: 오류 0, vitest 5 passed.

Run: `.claude/launch.json` 이 없으면 생성:

```json
{
  "version": "0.0.1",
  "configurations": [
    { "name": "web", "runtimeExecutable": "npm", "runtimeArgs": ["--prefix", "web", "run", "dev"], "port": 5173 }
  ]
}
```

브라우저 패널(`preview_start name=web`)로 `/` 를 열어 로그인 화면이 뜨는지, `/health` 가 기존 화면인지 확인(스크린샷 1장). 로그인은 하지 않는다(계정은 Task 6 에서 사용자가 만든다).

- [ ] **Step 8: 커밋**

```bash
git add web/package.json web/package-lock.json web/vitest.config.ts web/src/main.tsx web/src/App.tsx web/src/auth web/src/lib/decisions.ts web/src/lib/decisions.test.ts web/src/lib/questions.ts web/src/routes/Projects.tsx web/src/routes/Questions.tsx .claude/launch.json
git commit -m "feat(web): 라우터·이메일 로그인 게이트·질문 데이터 접근·결정 로직(vitest)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AZoYNTVPox7g1d6oJd5Wo1"
```

---

### Task 5: 질문 카드 화면

**Files:**
- Modify: `web/src/routes/Questions.tsx` (교체)
- Create: `web/src/components/QuestionCard.tsx`

**Interfaces:**
- Consumes: Task 4 의 `fetchProject, fetchQuestions, submitDecision, cropSignedUrl, Question, DecisionRow`, `decisionPayload, choiceFromKey, UNSURE_LABEL, Choice`, `useSession`.
- Produces: 경로 `/p/:slug/questions` 완성. `QuestionCard` props `{ question, slug, projectId, onDecided(row: DecisionRow) }`.

- [ ] **Step 1: QuestionCard**

`web/src/components/QuestionCard.tsx`:

```tsx
// 질문 카드 — 한 질문 = 한 요소 (지식베이스 §4): 크롭·선택지(권장안 첫 번째, 근거)·모델 영향·"모르겠다"·메모.
import { useEffect, useState } from 'react';
import {
  Alert, Badge, Box, Button, Collapse, Group, Image, Modal, Radio, Stack, Text, Textarea, Title,
} from '@mantine/core';

import { decisionPayload, type Choice, type DecisionRow, UNSURE_LABEL } from '../lib/decisions';
import { cropSignedUrl, submitDecision, type Question } from '../lib/questions';
import { supabase } from '../lib/supabase';

interface Props {
  question: Question;
  slug: string;
  projectId: string;
  choice: Choice | null;
  onChoice: (c: Choice | null) => void;
  onDecided: (row: DecisionRow) => void;
}

export function QuestionCard({ question: q, slug, projectId, choice, onChoice, onDecided }: Props) {
  const [url, setUrl] = useState<string | null>(null);
  const [imgError, setImgError] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    setUrl(null);
    setImgError(null);
    setNote('');
    setError(null);
    if (supabase === null) return;
    cropSignedUrl(supabase, slug, q.id)
      .then(setUrl)
      .catch((e: Error) => setImgError(`이미지 없음 — worker 에서 \`m3d publish\` 를 실행하세요 (${e.message})`));
  }, [q.id, slug]);

  async function decide() {
    if (supabase === null || choice === null) return;
    setBusy(true);
    setError(null);
    try {
      const row = await submitDecision(
        supabase,
        decisionPayload({ projectId, ambiguityId: q.id, options: q.options, choice, note }),
      );
      onDecided(row);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const radioValue = choice === null ? null : choice === 'unsure' ? 'unsure' : String(choice);

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-start">
        <Title order={4}>{q.item}</Title>
        <Group gap="xs">
          <Badge variant="light">{q.ord} p{q.pageNo ?? '?'}</Badge>
          <Badge color={q.status === '대기' ? 'gray' : q.status === '결정' ? 'green' : 'yellow'}>{q.status}</Badge>
        </Group>
      </Group>

      {imgError ? (
        <Alert color="yellow">{imgError}</Alert>
      ) : (
        <Box style={{ cursor: 'zoom-in' }} onClick={() => setZoom(true)}>
          <Image src={url ?? undefined} alt={q.item} radius="sm" fit="contain" mah={420} />
        </Box>
      )}
      <Modal opened={zoom} onClose={() => setZoom(false)} size="90%" title={q.item}>
        <Image src={url ?? undefined} alt={q.item} fit="contain" />
      </Modal>

      <Radio.Group value={radioValue ?? ''} onChange={(v) => onChoice(v === 'unsure' ? 'unsure' : Number(v))}>
        <Stack gap="xs">
          {q.options.map((o, i) => (
            <Radio
              key={i}
              value={String(i)}
              label={
                <span>
                  <Text span fw={600}>{i + 1}. {o.label}</Text>
                  {i === 0 && <Badge ml="xs" size="xs" color="blue">권장</Badge>}
                  <Text span size="sm" c="dimmed"> — {o.basis}</Text>
                </span>
              }
            />
          ))}
          <Radio value="unsure" label={<Text span c="dimmed">0. {UNSURE_LABEL}</Text>} />
        </Stack>
      </Radio.Group>

      <Alert color="blue" title="모델 영향" variant="light">{q.modelImpact}</Alert>

      <Textarea label="메모" placeholder="근거·현장 확인 사항" value={note} onChange={(e) => setNote(e.currentTarget.value)} autosize minRows={2} />

      {error && <Alert color="red">{error}</Alert>}
      <Group>
        <Button id="decide-button" onClick={() => void decide()} disabled={choice === null} loading={busy}>결정 (Enter)</Button>
        {q.latest && (
          <Text size="sm" c="dimmed">
            현재: {q.latest.provisional ? '잠정' : '결정'} · {q.latest.choice_label} · {new Date(q.latest.decided_at).toLocaleString('ko-KR')}
          </Text>
        )}
      </Group>
      {q.history.length > 0 && (
        <>
          <Button variant="subtle" size="xs" onClick={() => setShowHistory((v) => !v)}>
            이력 {q.history.length}건 {showHistory ? '접기' : '펼치기'}
          </Button>
          <Collapse in={showHistory}>
            <Stack gap={4}>
              {q.history.map((h) => (
                <Text key={h.id} size="xs" c="dimmed">
                  {new Date(h.decided_at).toLocaleString('ko-KR')} · {h.provisional ? '잠정' : '결정'} · {h.choice_label}{h.note ? ` · ${h.note}` : ''}
                </Text>
              ))}
            </Stack>
          </Collapse>
        </>
      )}
    </Stack>
  );
}
```

- [ ] **Step 2: Questions 화면(목록 + 카드 + 키보드)**

`web/src/routes/Questions.tsx` 교체:

```tsx
// 질문 큐 — 좌: 목록(계열·상태 필터) / 우: 카드. 키보드 1~4 선택, 0 모르겠다, Enter 결정, ←/→ 이동.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Alert, Anchor, Badge, Box, Group, Loader, NavLink, Paper, ScrollArea, SegmentedControl, Select, Stack, Text, Title,
} from '@mantine/core';

import { QuestionCard } from '../components/QuestionCard';
import { choiceFromKey, type Choice, type DecisionRow } from '../lib/decisions';
import { fetchProject, fetchQuestions, type ProjectRef, type Question } from '../lib/questions';
import { supabase } from '../lib/supabase';

type StatusFilter = '전체' | '대기' | '결정' | '잠정';

export function Questions() {
  const { slug = '' } = useParams();
  const [project, setProject] = useState<ProjectRef | null>(null);
  const [questions, setQuestions] = useState<Question[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusFilter>('전체');
  const [region, setRegion] = useState<string | null>(null);
  const [current, setCurrent] = useState<string | null>(null);
  const [choice, setChoice] = useState<Choice | null>(null);

  const load = useCallback(async () => {
    if (supabase === null) return;
    try {
      const p = await fetchProject(supabase, slug);
      setProject(p);
      setQuestions(await fetchQuestions(supabase, p));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [slug]);

  useEffect(() => { void load(); }, [load]);

  const regions = useMemo(() => Array.from(new Set((questions ?? []).map((q) => q.region))).sort(), [questions]);
  const visible = useMemo(
    () => (questions ?? []).filter((q) => (status === '전체' || q.status === status) && (region === null || q.region === region)),
    [questions, status, region],
  );
  const currentQ = visible.find((q) => q.id === current) ?? visible[0] ?? null;

  const move = useCallback((delta: number) => {
    if (!currentQ) return;
    const i = visible.findIndex((q) => q.id === currentQ.id);
    const next = visible[Math.min(Math.max(i + delta, 0), visible.length - 1)];
    if (next) { setCurrent(next.id); setChoice(null); }
  }, [currentQ, visible]);

  function onDecided(row: DecisionRow) {
    setQuestions((prev) => (prev ?? []).map((q) => q.id === row.ambiguity_id
      ? { ...q, status: row.provisional ? '잠정' : '결정', latest: row, history: [row, ...q.history] }
      : q));
    setChoice(null);
    // 다음 대기 항목으로
    const i = visible.findIndex((q) => q.id === row.ambiguity_id);
    const next = visible.slice(i + 1).find((q) => q.status === '대기');
    if (next) setCurrent(next.id);
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')) return;
      if (!currentQ) return;
      if (e.key === 'ArrowLeft') { move(-1); return; }
      if (e.key === 'ArrowRight') { move(1); return; }
      if (e.key === 'Enter' && choice !== null) { document.getElementById('decide-button')?.click(); return; }
      const c = choiceFromKey(e.key, currentQ.options.length);
      if (c !== null) setChoice(c);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [currentQ, move, choice]);

  if (error) return <Alert m="xl" color="red">{error}</Alert>;
  if (!project || !questions) return <Loader m="xl" />;

  const counts = { 대기: questions.filter((q) => q.status === '대기').length, 결정: questions.filter((q) => q.status === '결정').length, 잠정: questions.filter((q) => q.status === '잠정').length };

  return (
    <Group align="stretch" gap={0} h="100vh" wrap="nowrap">
      <Paper w={360} p="md" withBorder radius={0} style={{ overflow: 'hidden' }}>
        <Stack gap="sm" h="100%">
          <Anchor component={Link} to="/" size="sm">← 프로젝트</Anchor>
          <Title order={5}>{project.name}</Title>
          <Text size="xs" c="dimmed">대기 {counts.대기} · 결정 {counts.결정} · 잠정 {counts.잠정} / 전체 {questions.length}</Text>
          <SegmentedControl size="xs" value={status} onChange={(v) => setStatus(v as StatusFilter)} data={['전체', '대기', '결정', '잠정']} />
          <Select size="xs" placeholder="계열 전체" clearable value={region} onChange={setRegion} data={regions.map((r) => ({ value: r, label: `${r} 계열` }))} />
          <ScrollArea style={{ flex: 1 }}>
            {visible.map((q) => (
              <NavLink
                key={q.id}
                active={currentQ?.id === q.id}
                onClick={() => { setCurrent(q.id); setChoice(null); }}
                label={<Text size="sm" lineClamp={2}>{q.item}</Text>}
                description={`${q.ord} p${q.pageNo ?? '?'}`}
                rightSection={<Badge size="xs" color={q.status === '대기' ? 'gray' : q.status === '결정' ? 'green' : 'yellow'}>{q.status}</Badge>}
              />
            ))}
          </ScrollArea>
        </Stack>
      </Paper>
      <Box style={{ flex: 1, overflow: 'auto' }} p="xl">
        {currentQ ? (
          <QuestionCard key={currentQ.id} question={currentQ} slug={project.slug} projectId={project.id}
            choice={choice} onChoice={setChoice} onDecided={onDecided} />
        ) : (
          <Text c="dimmed">필터에 해당하는 질문이 없습니다.</Text>
        )}
      </Box>
    </Group>
  );
}
```

Enter 로 결정은 위 코드에 이미 들어 있다(`onKey` 의 Enter 분기가 `id="decide-button"` 버튼을 클릭한다).

- [ ] **Step 3: typecheck·test·화면 확인**

Run: `cd web && npm run typecheck && npm run test`
Expected: 오류 0, 5 passed.

브라우저 패널로 `/p/ab1-p4p5/questions` 를 열면 로그인 화면(세션 없음)이 뜬다 — 카드 렌더 확인은 Task 6(사용자 로그인 후). 여기서는 typecheck 와 `/health` 회귀만 확인.

- [ ] **Step 4: 커밋**

```bash
git add web/src/routes/Questions.tsx web/src/components/QuestionCard.tsx
git commit -m "feat(web): 질문 카드 화면 — 목록·필터·크롭·선택지·모르겠다·메모·키보드

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AZoYNTVPox7g1d6oJd5Wo1"
```

---

### Task 6: 실증(E2E)·RLS 검증·문서

**Files:**
- Create: `data/derived/ab1-p4p5/acceptance-m2b.md` (gitignore)
- Modify: `README.md` (publish·ssot·웹 사용법), `docs/superpowers/plans/2026-09-05-m2a-backlog.md` (M2b 결과 1줄)

**Interfaces:**
- Consumes: Task 1~5 전부, 실DB·Storage·dev 서버.

- [ ] **Step 1: 사용자 선행 작업 (컨트롤러가 요청)**

사용자가 Supabase 대시보드 → Authentication → Users → "Add user" 로 이메일/비밀번호 계정을 1개 만든다("Auto Confirm User" 체크). Claude 는 비밀번호를 다루지 않는다. 계정이 준비되면 진행.

- [ ] **Step 2: 로그인 → 카드 → 결정 실증 (브라우저 패널)**

1. `preview_start name=web` 으로 dev 서버를 열고 `/` 로 이동. **사용자가 브라우저 패널에서 직접 로그인**한다.
2. 프로젝트 목록 → "질문 카드 열기" → 목록 63건·첫 카드에 크롭 이미지가 보이는지 스크린샷(①).
3. 카드 1: 선택지 `2` 키 → Enter → 상태 배지 `결정`, "현재: 결정 · <label>" 표시. 스크린샷(②).
4. 카드 2: `0` 키(모르겠다) → 메모 입력 → 결정 → 배지 `잠정`.
5. 카드 1 로 돌아가 다른 선택지로 재답변 → 이력 2건 펼치기 스크린샷(③).
6. DB 확인(heredoc, 읽기 전용): `select count(*) from decisions` = 3, `select status, count(*) from ambiguities group by 1` = 대기 61 / 결정 1 / 잠정 1.
7. `db check` 마지막 줄 `decisions=3 provisional=1 published=63/63`.

- [ ] **Step 3: SSOT·보존·RLS 실증**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli ssot ab1-p4p5`
Expected: `실측정리 v2 생성`(Task 3 의 v1 이후 결정이 생겼으므로) 또는 v1(Task 3 에서 생성 안 했으면). §4 결정 절에 2건(결정 1·잠정 1), §5 미결 61건. 재실행 → `변경 없음`.

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli review ab1-p4p5 --region <결정한 카드의 계열> --cache-only`
Expected: `보호 2`(결정·잠정 2건) 포함, 합계 비용 $0.0000, DB 재조회로 두 ambiguity 의 id·status 불변.

익명 RLS(Bash, publishable key 는 `.env` 에서 읽어 셸 변수로만 — 출력 금지):
```bash
set -a; . ./.env; set +a
curl -s -o /dev/null -w "%{http_code}\n" "$SUPABASE_URL/rest/v1/ambiguities?select=id&limit=1" -H "apikey: $SUPABASE_PUBLISHABLE_KEY"
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$SUPABASE_URL/rest/v1/decisions" -H "apikey: $SUPABASE_PUBLISHABLE_KEY" -H "Content-Type: application/json" -d '{"project_id":"00000000-0000-0000-0000-000000000000","ambiguity_id":"00000000-0000-0000-0000-000000000000","choice_index":0,"choice_label":"x"}'
curl -s -o /dev/null -w "%{http_code}\n" "$SUPABASE_URL/storage/v1/object/crops/ab1-p4p5/<임의 ambiguity id>.png" -H "apikey: $SUPABASE_PUBLISHABLE_KEY"
```
Expected: 첫 요청은 200 이되 본문이 `[]`(행 0 — RLS 로 필터) 이거나 401, 두 번째 401/403(삽입 거부), 세 번째 400/403(비공개 버킷). 세 결과를 acceptance 에 기록. (`.env` 를 `source` 하면 백슬래시 경로 변수가 깨질 수 있으나 여기서는 SUPABASE_* 두 값만 쓴다.)

- [ ] **Step 4: acceptance-m2b.md · README · 백로그 갱신**

`data/derived/ab1-p4p5/acceptance-m2b.md`: 설계서 §1 합격 기준 1~6 각각 결과·근거(스크린샷 파일명, SQL 결과, 명령 출력). 스크린샷은 `data/derived/ab1-p4p5/screens/m2b-*.png` 에 저장.

`README.md`: "시작하기" 에 `m3d publish ab1-p4p5` / `m3d ssot ab1-p4p5`(둘 다 무과금) 와 웹 실행(`cd web && npm run dev`, 계정 생성 안내) 3줄. `docs/superpowers/plans/2026-09-05-m2a-backlog.md` §3 M2b 설계 메모 아래에 "M2b 구현: decisions FK restrict + replace_region 보호로 해소(2026-09-05)" 1줄.

- [ ] **Step 5: 커밋**

```bash
git add README.md docs/superpowers/plans/2026-09-05-m2a-backlog.md
git commit -m "docs(m2b): 실증 결과 반영 — README 사용법·백로그 갱신

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AZoYNTVPox7g1d6oJd5Wo1"
```

---

## 계획 자체 검토

1. **스펙 커버리지**: §1 합격 1(Task 5·6) 2(Task 1 트리거·Task 5·6) 3(Task 3·6) 4(Task 6 curl) 5(Task 2·6) 6(각 태스크 테스트·Task 6 스크린샷). §3 SQL → Task 1. §4-1 publish → Task 2. §4-2 ssot → Task 3. §4-3 replace_region 보호·db check → Task 2·1. §5 웹 구조 → Task 4·5(파일 목록 일치). §6 테스트 → 각 태스크. §7 백로그 → 미구현(의도).
2. **플레이스홀더**: Task 4 Step 6 의 `Questions.tsx` 자리표시는 Task 5 가 교체한다고 명시. Task 6 Step 3 의 `<임의 ambiguity id>` 는 실행자가 DB 에서 고른다.
3. **타입 일관성**: `replace_region` 반환 키 `protected`(Task 2 ↔ CLI 출력), `publish.object_key(slug, amb_id)` ↔ `questions.cropObjectKey(slug, id)` 같은 규칙 `<slug>/<id>.png`, `assets.storage_path = "crops/<slug>/<id>.png"`; `DecisionRow` 필드 = `decisions` select 컬럼 = `contracts` Row; `Choice`/`choiceFromKey` ↔ `QuestionCard` radio 값; `fetchQuestions(client, project: ProjectRef)`; `run_ssot` 반환 키 `changed/version/path/counts` ↔ CLI 출력.
4. **테스트 수 누적**: 277 → 282(T1) → 290(T2) → 293(T3); 웹 vitest 5. 실측 우선.
