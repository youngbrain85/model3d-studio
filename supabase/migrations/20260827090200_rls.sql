-- ============================================================================
-- model3d-studio — 03. RLS (Supabase auth 기반)
--
-- 접근 모델: 프로젝트 멤버십(project_members) 기반.
--   owner    — 멤버 관리·프로젝트 삭제 + editor 전체 권한
--   editor   — 판독/시트/부재/빌드/렌더 등 데이터 쓰기
--   reviewer — 읽기 + 질문 응답(decisions) + 승인(approvals)
--   viewer   — 읽기 전용
--
-- 재귀 회피: 정책이 project_members 를 직접 조인하면 42P17(무한 재귀)이 난다.
--   → private 스키마의 security definer 함수로 소유 관계를 읽는다.
-- 성능: auth.uid() 와 헬퍼 호출은 (select ...) 로 감싸 initPlan 캐시를 태운다.
-- 워커(service_role)는 BYPASSRLS 이므로 정책의 영향을 받지 않는다.
-- ============================================================================

-- ── 멤버십 헬퍼 (security definer — 호출자 RLS 를 우회해 재귀를 끊는다) ─────
create or replace function private.member_project_ids()
returns setof uuid
language sql
security definer
stable
set search_path = ''
as $fn$
  select pm.project_id
  from public.project_members pm
  where pm.user_id = (select auth.uid())
$fn$;

create or replace function private.editor_project_ids()
returns setof uuid
language sql
security definer
stable
set search_path = ''
as $fn$
  select pm.project_id
  from public.project_members pm
  where pm.user_id = (select auth.uid())
    and pm.role in ('owner','editor')
$fn$;

create or replace function private.reviewer_project_ids()
returns setof uuid
language sql
security definer
stable
set search_path = ''
as $fn$
  select pm.project_id
  from public.project_members pm
  where pm.user_id = (select auth.uid())
    and pm.role in ('owner','editor','reviewer')
$fn$;

create or replace function private.owner_project_ids()
returns setof uuid
language sql
security definer
stable
set search_path = ''
as $fn$
  select pm.project_id
  from public.project_members pm
  where pm.user_id = (select auth.uid())
    and pm.role = 'owner'
$fn$;

-- Storage 경로 첫 세그먼트(project_id) 추출. uuid 가 아니면 null → 접근 거부.
create or replace function private.path_project_id(object_name text)
returns uuid
language sql
immutable
parallel safe
set search_path = ''
as $fn$
  select case
    when split_part(object_name, '/', 1)
         ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    then split_part(object_name, '/', 1)::uuid
    else null
  end
$fn$;

revoke all on schema private from public;
revoke execute on function private.member_project_ids()   from public;
revoke execute on function private.editor_project_ids()   from public;
revoke execute on function private.reviewer_project_ids() from public;
revoke execute on function private.owner_project_ids()    from public;
revoke execute on function private.path_project_id(text)  from public;

grant usage on schema private to authenticated;
grant execute on function private.member_project_ids()   to authenticated;
grant execute on function private.editor_project_ids()   to authenticated;
grant execute on function private.reviewer_project_ids() to authenticated;
grant execute on function private.owner_project_ids()    to authenticated;
grant execute on function private.path_project_id(text)  to authenticated;

-- 프로젝트 생성자를 즉시 owner 멤버로 등록한다.
-- 이게 없으면 생성자가 자기 프로젝트를 못 읽는 고전적 함정에 빠진다.
create or replace function public.m3d_add_owner_membership()
returns trigger
language plpgsql
security definer
set search_path = ''
as $fn$
begin
  insert into public.project_members (project_id, user_id, role)
  values (new.id, new.owner_id, 'owner')
  on conflict (project_id, user_id) do update set role = 'owner';
  return new;
end;
$fn$;

create trigger projects_add_owner_membership
  after insert on public.projects
  for each row execute function public.m3d_add_owner_membership();

-- ── RLS 활성화 ──────────────────────────────────────────────────────────────
alter table public.projects            enable row level security;
alter table public.project_members     enable row level security;
alter table public.sheets              enable row level security;
alter table public.structural_members  enable row level security;
alter table public.ambiguities         enable row level security;
alter table public.decisions           enable row level security;
alter table public.readings            enable row level security;
alter table public.builds              enable row level security;
alter table public.verifications       enable row level security;
alter table public.renders             enable row level security;
alter table public.approvals           enable row level security;

-- ── projects ────────────────────────────────────────────────────────────────
create policy projects_select on public.projects
  for select to authenticated
  using (
    id in (select private.member_project_ids())
    or owner_id = (select auth.uid())
  );

create policy projects_insert on public.projects
  for insert to authenticated
  with check (owner_id = (select auth.uid()));

create policy projects_update on public.projects
  for update to authenticated
  using (id in (select private.editor_project_ids()))
  with check (id in (select private.editor_project_ids()));

create policy projects_delete on public.projects
  for delete to authenticated
  using (id in (select private.owner_project_ids()));

-- ── project_members ─────────────────────────────────────────────────────────
create policy project_members_select on public.project_members
  for select to authenticated
  using (
    project_id in (select private.member_project_ids())
    or user_id = (select auth.uid())
  );

create policy project_members_insert on public.project_members
  for insert to authenticated
  with check (project_id in (select private.owner_project_ids()));

create policy project_members_update on public.project_members
  for update to authenticated
  using (project_id in (select private.owner_project_ids()))
  with check (project_id in (select private.owner_project_ids()));

create policy project_members_delete on public.project_members
  for delete to authenticated
  using (project_id in (select private.owner_project_ids()));

-- ── 편집자 쓰기 / 멤버 읽기 테이블 ──────────────────────────────────────────
-- sheets
create policy sheets_select on public.sheets
  for select to authenticated
  using (project_id in (select private.member_project_ids()));
create policy sheets_write on public.sheets
  for insert to authenticated
  with check (project_id in (select private.editor_project_ids()));
create policy sheets_update on public.sheets
  for update to authenticated
  using (project_id in (select private.editor_project_ids()))
  with check (project_id in (select private.editor_project_ids()));
create policy sheets_delete on public.sheets
  for delete to authenticated
  using (project_id in (select private.editor_project_ids()));

-- structural_members
create policy structural_members_select on public.structural_members
  for select to authenticated
  using (project_id in (select private.member_project_ids()));
create policy structural_members_write on public.structural_members
  for insert to authenticated
  with check (project_id in (select private.editor_project_ids()));
create policy structural_members_update on public.structural_members
  for update to authenticated
  using (project_id in (select private.editor_project_ids()))
  with check (project_id in (select private.editor_project_ids()));
create policy structural_members_delete on public.structural_members
  for delete to authenticated
  using (project_id in (select private.editor_project_ids()));

-- ambiguities
create policy ambiguities_select on public.ambiguities
  for select to authenticated
  using (project_id in (select private.member_project_ids()));
create policy ambiguities_write on public.ambiguities
  for insert to authenticated
  with check (project_id in (select private.editor_project_ids()));
-- reviewer 도 상태를 바꿀 수 있어야 질문 루프가 돈다.
create policy ambiguities_update on public.ambiguities
  for update to authenticated
  using (project_id in (select private.reviewer_project_ids()))
  with check (project_id in (select private.reviewer_project_ids()));
create policy ambiguities_delete on public.ambiguities
  for delete to authenticated
  using (project_id in (select private.editor_project_ids()));

-- readings
create policy readings_select on public.readings
  for select to authenticated
  using (project_id in (select private.member_project_ids()));
create policy readings_write on public.readings
  for insert to authenticated
  with check (project_id in (select private.editor_project_ids()));
create policy readings_update on public.readings
  for update to authenticated
  using (project_id in (select private.editor_project_ids()))
  with check (project_id in (select private.editor_project_ids()));
create policy readings_delete on public.readings
  for delete to authenticated
  using (project_id in (select private.editor_project_ids()));

-- builds
create policy builds_select on public.builds
  for select to authenticated
  using (project_id in (select private.member_project_ids()));
create policy builds_write on public.builds
  for insert to authenticated
  with check (project_id in (select private.editor_project_ids()));
create policy builds_update on public.builds
  for update to authenticated
  using (project_id in (select private.editor_project_ids()))
  with check (project_id in (select private.editor_project_ids()));
create policy builds_delete on public.builds
  for delete to authenticated
  using (project_id in (select private.editor_project_ids()));

-- renders
create policy renders_select on public.renders
  for select to authenticated
  using (project_id in (select private.member_project_ids()));
create policy renders_write on public.renders
  for insert to authenticated
  with check (project_id in (select private.editor_project_ids()));
create policy renders_update on public.renders
  for update to authenticated
  using (project_id in (select private.editor_project_ids()))
  with check (project_id in (select private.editor_project_ids()));
create policy renders_delete on public.renders
  for delete to authenticated
  using (project_id in (select private.editor_project_ids()));

-- ── 추가 전용(append-only) 감사 테이블 ──────────────────────────────────────
-- decisions: 질문 응답은 reviewer 이상. 정정은 새 행(supersedes)으로만.
create policy decisions_select on public.decisions
  for select to authenticated
  using (project_id in (select private.member_project_ids()));
create policy decisions_insert on public.decisions
  for insert to authenticated
  with check (
    project_id in (select private.reviewer_project_ids())
    and (responder_id is null or responder_id = (select auth.uid()))
  );
-- UPDATE/DELETE 정책 없음 → 누구도 수정·삭제할 수 없다(로그 불변).

-- verifications: 검증 리포트는 editor(에이전트 대행) 가 기록. 수정 불가.
create policy verifications_select on public.verifications
  for select to authenticated
  using (project_id in (select private.member_project_ids()));
create policy verifications_insert on public.verifications
  for insert to authenticated
  with check (project_id in (select private.editor_project_ids()));

-- approvals: 승인은 reviewer 이상. 본인 명의로만. 수정 불가.
create policy approvals_select on public.approvals
  for select to authenticated
  using (project_id in (select private.member_project_ids()));
create policy approvals_insert on public.approvals
  for insert to authenticated
  with check (
    project_id in (select private.reviewer_project_ids())
    and approver_id = (select auth.uid())
  );

-- ── 권한(GRANT) ─────────────────────────────────────────────────────────────
-- RLS 는 행을 거르지만, 테이블 권한이 없으면 애초에 접근이 안 된다.
-- anon 에는 아무것도 주지 않는다 — 전 데이터가 비공개다.
grant usage on schema public to authenticated;

grant select, insert, update, delete on
  public.projects,
  public.project_members,
  public.sheets,
  public.structural_members,
  public.ambiguities,
  public.readings,
  public.builds,
  public.renders
to authenticated;

-- 감사 로그는 추가·조회만. UPDATE/DELETE 권한 자체를 주지 않는다.
grant select, insert on
  public.decisions,
  public.verifications,
  public.approvals
to authenticated;

revoke all on all tables in schema public from anon;

-- Supabase 는 public 스키마에 대해 anon/authenticated 로의 기본 권한을 걸어 둔다.
-- 앞으로 추가되는 테이블이 자동으로 anon 에 노출되지 않도록 기본값을 되돌린다.
alter default privileges in schema public revoke all on tables from anon;
alter default privileges in schema public revoke all on sequences from anon;
