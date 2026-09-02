-- M2a: 판독 결과와 애매성 (설계서 §5).
-- readings 는 치수 SSOT 초안, ambiguities 는 질문 카드의 원천이다.

create table readings (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null references projects(id) on delete cascade,
  region         text not null,                     -- 계열 A~F
  item           text not null,
  value_raw      text not null,                     -- 원문 표기 그대로 (지식베이스 §2)
  unit           text,
  basis_sheet_id uuid not null references sheets(id) on delete cascade,
  basis_page_id  uuid references sheet_pages(id) on delete set null,
  basis_mm_bbox  jsonb not null,                    -- [x0,y0,x1,y1] 용지 mm
  crosscheck     jsonb,                             -- {expr, result, ok} 검산 (§2)
  status         text not null
                   check (status in ('확정','추정','검토지적')),
  round          int  not null default 1,           -- 1 시트판독 2 통합 3 검토
  created_at     timestamptz not null default now()
);

create table ambiguities (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null references projects(id) on delete cascade,
  item           text not null,
  basis_sheet_id uuid not null references sheets(id) on delete cascade,
  sheet_page_id  uuid references sheet_pages(id) on delete set null,
  mm_bbox        jsonb not null,                    -- 크롭 원천 (§4 원본 픽셀 좌표)
  options        jsonb not null,                    -- [{label, basis}] 2~4개
  model_impact   text not null,                     -- 선택에 따른 모델 차이
  crop_rel_path  text,                              -- crops 실행 후 채움
  status         text not null default '대기'
                   check (status in ('대기','결정','잠정')),
  created_at     timestamptz not null default now()
);

create index on readings(project_id, region);
create index on readings(project_id, status);
create index on ambiguities(project_id, status);

alter table readings    enable row level security;
alter table ambiguities enable row level security;

create policy "authenticated read" on readings
  for select to authenticated using (true);
create policy "authenticated read" on ambiguities
  for select to authenticated using (true);
