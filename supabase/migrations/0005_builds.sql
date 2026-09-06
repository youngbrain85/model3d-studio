-- 0005_builds — 빌드 버전·섹션·승인 이력 + Storage 버킷 models (M4 설계서 §4)
-- approvals 는 추가 전용 이력이다(decisions 패턴): 최신 행이 현재 상태, 트리거가 status 를 갱신한다.

create table builds (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null references projects(id) on delete cascade,
  version        int  not null,
  kind           text not null check (kind in ('pilot','full')),
  segment        text not null,
  content_sha256 text not null,
  glb_path       text not null,
  files          jsonb not null,
  stats          jsonb not null,
  status         text not null default '대기' check (status in ('대기','승인','반려')),
  git_sha        text,
  created_at     timestamptz not null default now(),
  unique (project_id, version)
);
create table build_sections (
  id          uuid primary key default gen_random_uuid(),
  build_id    uuid not null references builds(id) on delete cascade,
  section_key text not null,
  code        text not null,
  label       text not null,
  glb_path    text not null,
  bytes       int  not null,
  sha256      text not null,
  meshes      int  not null,
  triangles   int  not null,
  selfcheck   jsonb not null,
  status      text not null default '대기' check (status in ('대기','승인','반려')),
  unique (build_id, section_key)
);
create table approvals (
  id          uuid primary key default gen_random_uuid(),
  project_id  uuid not null references projects(id) on delete cascade,
  build_id    uuid not null references builds(id) on delete cascade,
  section_id  uuid references build_sections(id) on delete cascade,
  user_id     uuid not null default auth.uid(),
  verdict     text not null check (verdict in ('승인','반려')),
  note        text not null default '',
  created_at  timestamptz not null default now()
);
create index on approvals (build_id, created_at desc);

alter table builds         enable row level security;
alter table build_sections enable row level security;
alter table approvals      enable row level security;
create policy "authenticated read"   on builds         for select to authenticated using (true);
create policy "authenticated read"   on build_sections for select to authenticated using (true);
create policy "authenticated read"   on approvals      for select to authenticated using (true);
create policy "authenticated insert" on approvals      for insert to authenticated
  with check (user_id = auth.uid());

-- 삽입 트리거: 섹션 승인이면 build_sections.status, 결합본 승인이면 builds.status
-- (security definer — authenticated 에는 두 표의 update 정책이 없다)
create function apply_approval() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.section_id is null then
    update builds set status = new.verdict where id = new.build_id;
  else
    update build_sections set status = new.verdict where id = new.section_id;
  end if;
  return new;
end $$;
create trigger approvals_apply after insert on approvals
  for each row execute function apply_approval();

-- Storage: 비공개 버킷 + 로그인 사용자 읽기(서명 URL). 업로드는 service key(CLI)만.
insert into storage.buckets (id, name, public) values ('models', 'models', false)
  on conflict (id) do nothing;
create policy "authenticated read models" on storage.objects
  for select to authenticated using (bucket_id = 'models');
