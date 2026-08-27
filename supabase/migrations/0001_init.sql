-- M0 초기 스키마 (설계서 §4).
-- 지식베이스 규칙을 주석이 아니라 컬럼·제약으로 강제하는 것이 설계 원칙이다.

create extension if not exists pgcrypto;

-- ── projects ────────────────────────────────────────────────────────────
-- §1 "프로젝트마다 전역 좌표계를 최우선 확정" → coord_system NOT NULL 로 강제
create table projects (
  id                 uuid primary key default gen_random_uuid(),
  slug               text not null unique,
  name               text not null,
  structure          text,
  coord_system       jsonb not null,
  coord_assumptions  text[] not null default '{}',   -- §1 미확정 가정·정정 메모
  created_at         timestamptz not null default now()
);

-- ── sheets ──────────────────────────────────────────────────────────────
-- §3 "파일명·폴더명은 내용을 보장하지 않는다" → 출처별 컬럼 분리
create table sheets (
  id                        uuid primary key default gen_random_uuid(),
  project_id                uuid not null references projects(id) on delete cascade,
  ord                       text not null,
  drawing_no_from_filename  text not null,
  drawing_no_from_content   text,
  title_from_filename       text not null,
  title_from_content        text,
  scale_from_content        text,
  grade                     text not null check (grade in ('핵심','참고')),
  catalog_status            text not null default 'unverified'
                              check (catalog_status in
                                ('unverified','match','mismatch','unreadable')),
  page_count                int  not null check (page_count > 0),
  created_at                timestamptz not null default now(),
  unique (project_id, ord),
  unique (project_id, drawing_no_from_filename)
);

-- ── sheet_pages ─────────────────────────────────────────────────────────
-- §4 질문 크롭은 원본 픽셀 좌표를 쓴다 → 페이지 픽셀 크기를 필수 보관
create table sheet_pages (
  id         uuid primary key default gen_random_uuid(),
  sheet_id   uuid not null references sheets(id) on delete cascade,
  page_no    int  not null check (page_no > 0),
  width_px   int,
  height_px  int,
  created_at timestamptz not null default now(),
  unique (sheet_id, page_no)
);

-- ── assets ──────────────────────────────────────────────────────────────
-- role: source = [1] 업로드 입력 / derived = [2] 변환 산출물(= 회귀 정답)
create table assets (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references projects(id) on delete cascade,
  sheet_id      uuid references sheets(id) on delete cascade,
  sheet_page_id uuid references sheet_pages(id) on delete cascade,
  kind          text not null check (kind in ('dxf','pdf','png','photo')),
  role          text not null check (role in ('source','derived')),
  rel_path      text not null,
  bytes         bigint not null check (bytes > 0),
  sha256        text not null check (char_length(sha256) = 64),
  storage_path  text,
  created_at    timestamptz not null default now(),
  unique (project_id, rel_path)
);

create index on sheets(project_id);
create index on sheets(project_id, catalog_status);
create index on sheet_pages(sheet_id);
create index on assets(project_id, kind);
create index on assets(sheet_id);

-- ── RLS ─────────────────────────────────────────────────────────────────
-- anon 은 0행을 본다. worker 는 service key / DB 직결이라 우회한다.
-- 이 비대칭이 §9 검증에서 RLS 작동의 증거가 된다.
alter table projects    enable row level security;
alter table sheets      enable row level security;
alter table sheet_pages enable row level security;
alter table assets      enable row level security;

create policy "authenticated read" on projects
  for select to authenticated using (true);
create policy "authenticated read" on sheets
  for select to authenticated using (true);
create policy "authenticated read" on sheet_pages
  for select to authenticated using (true);
create policy "authenticated read" on assets
  for select to authenticated using (true);
