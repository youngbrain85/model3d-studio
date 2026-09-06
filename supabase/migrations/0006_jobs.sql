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
