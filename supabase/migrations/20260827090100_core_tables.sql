-- ============================================================================
-- model3d-studio — 02. 코어 테이블
--
-- 아키텍처 §4 데이터 모델 초안의 전개.
-- 테이블명 주의: 초안의 `members` 는 **부재(structural member)** 를 뜻하므로
--   `structural_members` 로 명명한다. 사용자 멤버십은 `project_members` 다.
--   (`members` 라는 이름은 RLS 정책·헬퍼에서 사용자 멤버십으로 오독될 소지가 크다.)
-- ============================================================================

-- ── 1. projects — 구조물·좌표계 정의 (규칙 §1) ──────────────────────────────
create table public.projects (
  id                  uuid primary key default gen_random_uuid(),
  owner_id            uuid not null references auth.users (id) on delete restrict,
  name                text not null check (length(btrim(name)) > 0),
  -- 구조물 코드. 부재 code 의 <구조물> 성분과 같은 어휘. 예: AB1(접속1교)
  structure_code      text check (structure_code ~ '^[A-Z][A-Z0-9]{0,7}$'),
  description         text,
  status              text not null default 'draft'
                        check (status in ('draft','active','archived')),

  -- 좌표계 (coordinate_system.schema.json). 규칙 §1 — 최우선 확정 대상.
  up_axis             text check (up_axis in ('X','Y','Z')),
  model_unit          text not null default 'm'  check (model_unit = 'm'),
  drawing_unit        text not null default 'mm' check (drawing_unit = 'mm'),
  axes                jsonb check (public.m3d_axes_valid(axes)),
  origin_reference    jsonb,
  assumptions         jsonb not null default '[]'::jsonb
                        check (public.m3d_assumptions_valid(assumptions)),
  -- 좌표계를 확정한 시각. 확정 후에는 축·원점이 모두 있어야 한다.
  coordinate_system_locked_at timestamptz,

  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),

  constraint projects_origin_reference_shape check (
    origin_reference is null
    or (jsonb_typeof(origin_reference) = 'object'
        and coalesce(origin_reference ->> 'description', '') <> '')
  ),
  -- 규칙 §1 — 좌표계 확정 선언은 축·원점·상방축이 모두 채워진 뒤에만 가능하다.
  constraint projects_locked_requires_full_coordinate_system check (
    coordinate_system_locked_at is null
    or (up_axis is not null and axes is not null and origin_reference is not null)
  ),
  -- 규칙 §1 — 가정한 축이 있으면 뒤집기 검증 항목이 등재되어 있어야 한다.
  constraint projects_assumed_axes_registered check (
    public.m3d_assumed_axes_are_registered(axes, assumptions)
  ),
  -- 부재 code 의 구조물 성분과 맞물리므로 활성 프로젝트는 구조물 코드가 있어야 한다.
  constraint projects_active_requires_structure_code check (
    status = 'draft' or structure_code is not null
  ),
  constraint projects_id_owner_uniq unique (id, owner_id)
);

comment on table public.projects is '프로젝트 = 구조물 1건 + 전역 좌표계 (규칙 §1).';
comment on column public.projects.coordinate_system_locked_at is
  '규칙 §1 — 좌표계 확정 시각. 확정 전에는 모델링 착수 금지(파이프라인 게이트).';

create index projects_owner_id_idx on public.projects (owner_id);
create index projects_status_idx on public.projects (status);

create trigger projects_set_updated_at
  before update on public.projects
  for each row execute function public.m3d_set_updated_at();


-- ── 2. project_members — 사용자 멤버십 (RLS 근간) ───────────────────────────
-- 판단: 필요하다. 질문 응답자(reviewer)·승인자(approver)·판독 편집자가 서로 다른
-- 사람일 수 있고(규칙 §4·§5 승인 게이트), 소유자 단독 접근으로는 표현할 수 없다.
create table public.project_members (
  project_id  uuid not null references public.projects (id) on delete cascade,
  user_id     uuid not null references auth.users (id) on delete cascade,
  role        text not null check (role in ('owner','editor','reviewer','viewer')),
  invited_by  uuid references auth.users (id) on delete set null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  primary key (project_id, user_id)
);

comment on table public.project_members is
  '사용자 멤버십. 부재 테이블은 structural_members 이며 이 테이블과 무관하다.';
comment on column public.project_members.role is
  'owner=권한관리·삭제, editor=판독/모델 데이터 쓰기, reviewer=질문응답·승인, viewer=읽기.';

create index project_members_user_id_idx on public.project_members (user_id);

create trigger project_members_set_updated_at
  before update on public.project_members
  for each row execute function public.m3d_set_updated_at();


-- ── 3. sheets — 도면 시트 카탈로그 (규칙 §3) ────────────────────────────────
create table public.sheets (
  id                        uuid primary key default gen_random_uuid(),
  project_id                uuid not null references public.projects (id) on delete cascade,

  -- 편철 오류 검출: 파일명 유래 도면번호와 표제란 유래 도면번호를 분리 보관한다.
  file_name                 text not null check (length(btrim(file_name)) > 0),
  page                      integer not null check (page >= 1),
  sheet_no_from_titleblock  text,   -- 시트 내부 표제란 텍스트 — 정본
  sheet_no_from_filename    text,   -- 파일명/폴더명 유추 — 참고값일 뿐 근거가 아니다
  titleblock_match          text not null
                              check (titleblock_match in
                                     ('match','mismatch','unreadable','filename_only')),
  titleblock_checked_at     timestamptz,
  titleblock_raw_text       text,   -- 대조 근거 원문 (사람이 mismatch 를 볼 때 필요)

  -- 정본 도면번호. readings.source_sheets 가 이 값을 참조한다.
  sheet_no                  text generated always as
                              (coalesce(sheet_no_from_titleblock, sheet_no_from_filename)) stored,

  title                     text,
  scale                     text,          -- 예: 1/100, NONE
  classification            text,          -- 부재·섹션별 분류 (파이프라인 [3])

  -- 커버리지 (규칙 §3 — 키플랜 해치 또는 본문 좌표 표기만 근거로 인정)
  coverage_station_from     text,
  coverage_station_to       text,
  coverage_description      text,
  coverage_source           text check (coverage_source in ('keyplan_hatch','body_annotation')),

  -- Storage 경로 (버킷 규약은 04 마이그레이션 주석 참조)
  source_path               text,   -- drawings 버킷: 원본 PDF/DXF/DWG
  image_path                text,   -- sheet-images 버킷: 고해상 PNG
  text_path                 text,   -- sheet-images 버킷: sheet_text
  source_format             text check (source_format in ('pdf','dxf','dwg','image')),
  width_px                  integer check (width_px > 0),
  height_px                 integer check (height_px > 0),

  created_at                timestamptz not null default now(),
  updated_at                timestamptz not null default now(),

  constraint sheets_project_file_page_uniq unique (project_id, file_name, page),
  constraint sheets_id_project_uniq unique (id, project_id),

  -- 규칙 §3 — 대조 결과와 실제 도면번호 상태가 모순되면 안 된다.
  constraint sheets_titleblock_match_consistent check (
    case titleblock_match
      when 'match' then
        sheet_no_from_titleblock is not null
        and sheet_no_from_filename is not null
        and sheet_no_from_titleblock = sheet_no_from_filename
      when 'mismatch' then
        sheet_no_from_titleblock is not null
        and sheet_no_from_filename is not null
        and sheet_no_from_titleblock <> sheet_no_from_filename
      when 'unreadable' then
        sheet_no_from_titleblock is null
      when 'filename_only' then
        sheet_no_from_titleblock is null
        and sheet_no_from_filename is not null
      else false
    end
  ),
  -- 커버리지를 적었다면 근거 출처가 있어야 한다 (요약도 라벨은 오탐이라 허용 안 함).
  constraint sheets_coverage_requires_source check (
    (coverage_station_from is null
     and coverage_station_to is null
     and coverage_description is null)
    or coverage_source is not null
  )
);

comment on table public.sheets is
  '규칙 §3 — 표제란 전수 대조 먼저. 파일명은 내용을 보장하지 않는다(편철 오류 실례).';
comment on column public.sheets.titleblock_match is
  'match/mismatch/unreadable/filename_only. mismatch 만 사람이 본다.';

create index sheets_project_id_idx on public.sheets (project_id);
create index sheets_sheet_no_idx on public.sheets (project_id, sheet_no);
create index sheets_classification_idx on public.sheets (project_id, classification);
-- 편철 오류 워크큐: mismatch/unreadable 만 뽑는다.
create index sheets_titleblock_followup_idx on public.sheets (project_id, titleblock_match)
  where titleblock_match in ('mismatch','unreadable');

create trigger sheets_set_updated_at
  before update on public.sheets
  for each row execute function public.m3d_set_updated_at();


-- ── 4. structural_members — 부재 트리 (규칙 §5) ─────────────────────────────
create table public.structural_members (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references public.projects (id) on delete cascade,

  -- 노드명이 곧 객체 DB·망도 연결 키다. 패턴은 contracts 의 MEMBER_CODE_PATTERN 과 동일.
  code          text not null check (code ~ '^[A-Z][A-Z0-9]{0,7}_S[0-9]{1,3}_[A-Z]{2,4}[0-9]{1,4}[LRCTB]?$'),
  parent_id     uuid,

  structure     text not null check (structure ~ '^[A-Z][A-Z0-9]{0,7}$'),
  segment       text not null check (segment ~ '^S[0-9]{1,3}$'),
  member_type   text not null check (member_type ~ '^[A-Z]{2,4}$'),
  -- JSON 계약의 `index`. index 는 Postgres 키워드와 겹쳐 혼동을 부르므로 개명.
  member_index  integer not null check (member_index >= 0),
  side          text check (side in ('L','R','C','T','B')),

  -- 규칙 §5 — 반복 부재는 존(zone) 모델로: 간격·개수를 데이터로 두고 빌더가 전개.
  zone          jsonb check (public.m3d_member_zone_valid(zone)),
  spec_refs     text[] not null default '{}'::text[],
  notes         text,

  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),

  constraint structural_members_code_uniq unique (project_id, code),
  constraint structural_members_id_project_uniq unique (id, project_id),
  constraint structural_members_no_self_parent check (parent_id is distinct from id),
  -- code 문자열과 분해 성분이 어긋나면 노드명이 조용히 오염된다.
  constraint structural_members_code_matches_fields check (
    public.m3d_member_code_matches(code, structure, segment, member_type, member_index, side)
  ),
  -- 부모는 같은 프로젝트 안에 있어야 한다.
  constraint structural_members_parent_same_project
    foreign key (parent_id, project_id)
    references public.structural_members (id, project_id) on delete cascade
);

comment on table public.structural_members is
  '부재(structural member) 트리. 규칙 §5 — 부재 = 독립 노드, 명명 규칙 일관 적용. 사용자 멤버십은 project_members.';

create index structural_members_project_id_idx on public.structural_members (project_id);
create index structural_members_parent_id_idx on public.structural_members (parent_id);
create index structural_members_group_idx
  on public.structural_members (project_id, structure, segment, member_type);

create trigger structural_members_set_updated_at
  before update on public.structural_members
  for each row execute function public.m3d_set_updated_at();

-- 부재 트리에 순환이 생기면 빌더가 무한루프에 빠진다. 복합 FK 로는 막을 수 없어 트리거로 막는다.
create or replace function public.m3d_assert_member_tree_acyclic()
returns trigger
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  v_cursor uuid := new.parent_id;
  v_depth  integer := 0;
begin
  while v_cursor is not null loop
    if v_cursor = new.id then
      raise exception '부재 트리 순환: % (code %)', new.id, new.code
        using errcode = 'check_violation';
    end if;
    v_depth := v_depth + 1;
    if v_depth > 64 then
      raise exception '부재 트리 깊이 초과(>64): code %', new.code
        using errcode = 'check_violation';
    end if;
    select m.parent_id into v_cursor
    from public.structural_members m
    where m.id = v_cursor;
  end loop;
  return new;
end;
$fn$;

create trigger structural_members_acyclic
  after insert or update of parent_id on public.structural_members
  for each row when (new.parent_id is not null)
  execute function public.m3d_assert_member_tree_acyclic();


-- ── 5. ambiguities — 판독 애매값 = 질문 카드 원천 (규칙 §3·§4) ──────────────
create table public.ambiguities (
  id                uuid primary key default gen_random_uuid(),
  project_id        uuid not null references public.projects (id) on delete cascade,

  -- 규칙 §4 — 한 질문 = 한 요소. 여러 애매점을 묶지 않는다.
  item              text not null check (length(btrim(item)) > 0),
  question          text not null check (length(btrim(question)) > 0),

  -- 대표 시트(인덱싱·조인용). 상세 크롭 목록은 sheet_refs 가 정본.
  primary_sheet_id  uuid,
  -- [{sheet_no, page, bbox_px:[x,y,w,h], crop_path, caption}] — 최소 1개
  sheet_refs        jsonb not null check (public.m3d_sheet_refs_valid(sheet_refs)),

  -- 2~4개. [0] 은 반드시 권장안. 각 선택지에 근거·모델 영향 필수.
  options           jsonb not null check (public.m3d_ambiguity_options_valid(options)),
  model_impact      text not null check (length(btrim(model_impact)) > 0),

  -- 규칙 §4 — "모르겠다 — 권장대로 진행" 은 항상 허용한다.
  allow_unknown     boolean not null default true check (allow_unknown),

  status            text not null default 'pending'
                      check (status in ('pending','decided','provisional')),
  conflicts_with    uuid[] not null default '{}'::uuid[],
  -- 규칙 §4 — 모순 시 즉시 재질문하지 않고 근거를 갖춰 1회만 재확인한다.
  reconfirm_count   integer not null default 0 check (reconfirm_count between 0 and 1),
  raised_by         text,          -- 판독 에이전트 식별자
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),

  constraint ambiguities_id_project_uniq unique (id, project_id),
  constraint ambiguities_primary_sheet_same_project
    foreign key (primary_sheet_id, project_id)
    references public.sheets (id, project_id) on delete set null
);

comment on table public.ambiguities is
  '규칙 §3 — 판독 에이전트는 애매값을 추정으로 확정하지 않고 이 구조로 분리한다. 질문 카드의 원천.';

create index ambiguities_project_id_idx on public.ambiguities (project_id);
create index ambiguities_primary_sheet_idx on public.ambiguities (primary_sheet_id);
-- 질문 카드 큐: 대기중인 것만.
create index ambiguities_pending_idx on public.ambiguities (project_id, created_at)
  where status = 'pending';
create index ambiguities_sheet_refs_gin on public.ambiguities using gin (sheet_refs);

create trigger ambiguities_set_updated_at
  before update on public.ambiguities
  for each row execute function public.m3d_set_updated_at();


-- ── 6. decisions — 질문 응답 로그 (규칙 §4) ─────────────────────────────────
-- 추가(append-only) 로그다. 재확인(1회)은 새 행 + supersedes 로 남는다.
create table public.decisions (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references public.projects (id) on delete cascade,
  ambiguity_id  uuid not null,

  -- choice = 선택지 인덱스(0..3) 또는 "모르겠다"(choice_unknown)
  choice_index  integer check (choice_index between 0 and 3),
  choice_unknown boolean not null default false,
  -- 규칙 §4 — "모르겠다 — 권장대로 진행" 은 반드시 잠정으로 기록한다.
  provisional   boolean not null,

  responder     text not null check (length(btrim(responder)) > 0),
  responder_id  uuid references auth.users (id) on delete set null,
  decided_at    timestamptz not null default now(),
  note          text,
  supersedes    uuid references public.decisions (id) on delete set null,
  created_at    timestamptz not null default now(),

  constraint decisions_id_project_uniq unique (id, project_id),
  constraint decisions_ambiguity_same_project
    foreign key (ambiguity_id, project_id)
    references public.ambiguities (id, project_id) on delete cascade,
  -- 인덱스 선택과 "모르겠다" 는 정확히 하나만 성립한다.
  constraint decisions_choice_exactly_one check (
    (choice_unknown and choice_index is null)
    or (not choice_unknown and choice_index is not null)
  ),
  constraint decisions_unknown_is_provisional check (not choice_unknown or provisional)
);

comment on table public.decisions is
  '규칙 §4 — 질문 응답 로그(SSOT 반영 이력). 추가 전용: 정정은 새 행 + supersedes.';

create index decisions_project_id_idx on public.decisions (project_id);
create index decisions_ambiguity_idx on public.decisions (ambiguity_id, decided_at desc);
create index decisions_responder_idx on public.decisions (responder_id);


-- ── 7. readings — 치수 정본(SSOT) 항목 (규칙 §2) ────────────────────────────
create table public.readings (
  id                  uuid primary key default gen_random_uuid(),
  project_id          uuid not null references public.projects (id) on delete cascade,

  item                text not null check (length(btrim(item)) > 0),
  -- 값은 수치 또는 문자열. 정확히 하나만 채운다(부동소수 오차 회피 위해 numeric).
  value_num           numeric,
  value_text          text,
  unit                text not null check (unit in ('mm','m','deg','ea','-')),

  -- ★ 규칙 §8 — 근거(도면번호) 없는 수치는 반려. 최소 1개.
  source_sheets       text[] not null
                        check (cardinality(source_sheets) >= 1
                               and array_position(source_sheets, null) is null
                               and not ('' = any (source_sheets))),
  -- 규칙 §3 — 중요 치수는 2개 이상 뷰·시트에서 교차 확인한다.
  cross_source_confirmed boolean not null default false,

  status              text not null check (status in ('confirmed','estimated','open')),

  -- 규칙 §2 — 파생 계산은 원문값과 구분 표기하고 검산을 동반한다.
  derived             boolean not null default false,
  derivation_formula  text,
  derivation_inputs   text[],

  -- 검산(cross_check): 식·기대·실측·허용오차·판정
  cross_check_formula   text,
  cross_check_expected  numeric,
  cross_check_actual    numeric,
  cross_check_tolerance numeric check (cross_check_tolerance >= 0),
  cross_check_result    text check (cross_check_result in ('PASS','FAIL')),

  -- 잠정값의 출처 결정 (규칙 §4 — 미결 목록과 연동)
  provisional_from_decision uuid references public.decisions (id) on delete set null,
  structural_member_id  uuid references public.structural_members (id) on delete set null,

  -- 정정 이력 [{version, changed_at, previous_value, reason}]
  revisions           jsonb not null default '[]'::jsonb
                        check (jsonb_typeof(revisions) = 'array'),
  read_by             text,     -- 판독 에이전트 식별자
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),

  -- SSOT: 한 프로젝트에서 한 항목은 하나의 정본 값을 갖는다.
  constraint readings_project_item_uniq unique (project_id, item),
  constraint readings_id_project_uniq unique (id, project_id),

  constraint readings_value_exactly_one check (
    (value_num is null) <> (value_text is null)
  ),
  -- 규칙 §3 — 교차 확인 표기는 근거 시트가 2개 이상일 때만 성립한다.
  constraint readings_cross_source_needs_two_sheets check (
    not cross_source_confirmed or cardinality(source_sheets) >= 2
  ),
  -- 검산은 전부 있거나 전부 없거나.
  constraint readings_cross_check_all_or_nothing check (
    num_nonnulls(cross_check_formula, cross_check_expected,
                 cross_check_actual, cross_check_tolerance, cross_check_result)
    in (0, 5)
  ),
  -- 규칙 §2 — 파생값은 유도식과 검산을 반드시 동반한다("검산 없는 수치는 싣지 않는다").
  constraint readings_derived_requires_derivation_and_cross_check check (
    not derived
    or (derivation_formula is not null
        and derivation_inputs is not null
        and cardinality(derivation_inputs) >= 1
        and cross_check_result is not null)
  ),
  -- 규칙 §2 — 검산 FAIL 인 수치는 확정될 수 없다.
  constraint readings_failed_cross_check_not_confirmed check (
    cross_check_result is distinct from 'FAIL' or status <> 'confirmed'
  ),
  -- 규칙 §4 — "모르겠다 — 권장대로" 에서 유래한 값은 확정이 아니라 잠정이다.
  constraint readings_provisional_not_confirmed check (
    provisional_from_decision is null or status <> 'confirmed'
  )
);

comment on table public.readings is
  '치수 정본(SSOT) 한 항목. 규칙 §2 — 모든 수치에 근거 도면번호, 확정/추정/미결 분리, 파생값은 검산 동반.';
comment on column public.readings.source_sheets is
  '근거 도면번호 배열. 규칙 §8 — 근거 없는 수치는 반려. sheets.sheet_no 와 대응(느슨한 참조).';

create index readings_project_id_idx on public.readings (project_id);
create index readings_status_idx on public.readings (project_id, status);
-- 미결 목록 워크큐 (규칙 §2·§4)
create index readings_open_idx on public.readings (project_id, updated_at)
  where status in ('estimated','open');
create index readings_source_sheets_gin on public.readings using gin (source_sheets);
create index readings_member_idx on public.readings (structural_member_id);
create index readings_decision_idx on public.readings (provisional_from_decision);

create trigger readings_set_updated_at
  before update on public.readings
  for each row execute function public.m3d_set_updated_at();


-- ── 8. builds — 모델 버전 (규칙 §5·§6-1) ────────────────────────────────────
create table public.builds (
  id                 uuid primary key default gen_random_uuid(),
  project_id         uuid not null references public.projects (id) on delete cascade,

  version            text not null check (length(btrim(version)) > 0),
  parent_build_id    uuid references public.builds (id) on delete set null,
  scope              text not null default 'pilot'
                       check (scope in ('pilot','rollout','full')),
  segment_codes      text[] not null default '{}'::text[],

  builder_agent      text not null check (length(btrim(builder_agent)) > 0),
  builder_code_path  text,   -- models 버킷: 빌더 파이썬 코드
  glb_path           text,   -- models 버킷: 산출 GLB
  -- 규칙 §5 — 단순화는 숨기지 않는다: [A1]~[An] 항목을 사유와 함께 남긴다.
  simplifications    jsonb not null default '[]'::jsonb
                       check (jsonb_typeof(simplifications) = 'array'),

  -- 규칙 §6-1 — 빌더 self-check 는 실행 출력으로 PASS/FAIL 을 남긴다.
  self_check         jsonb,
  self_check_result  text check (self_check_result in ('PASS','FAIL')),
  watertight         boolean,

  status             text not null default 'queued'
                       check (status in ('queued','running','succeeded','failed')),
  error_message      text,
  started_at         timestamptz,
  finished_at        timestamptz,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),

  constraint builds_project_version_uniq unique (project_id, version),
  constraint builds_id_project_uniq unique (id, project_id),
  -- 규칙 §6 — self-check PASS 와 산출물 없이 성공을 선언할 수 없다.
  constraint builds_success_requires_self_check check (
    status <> 'succeeded'
    or (glb_path is not null and self_check_result = 'PASS' and watertight is not false)
  ),
  constraint builds_failed_requires_reason check (
    status <> 'failed' or error_message is not null
  )
);

comment on table public.builds is
  '모델 빌드 버전. 규칙 §6-1 — self-check PASS 없이는 succeeded 로 둘 수 없다.';

create index builds_project_id_idx on public.builds (project_id);
create index builds_status_idx on public.builds (project_id, status);
create index builds_parent_idx on public.builds (parent_build_id);

create trigger builds_set_updated_at
  before update on public.builds
  for each row execute function public.m3d_set_updated_at();


-- ── 9. verifications — 3중 검증 리포트 (규칙 §6) ────────────────────────────
create table public.verifications (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null references public.projects (id) on delete cascade,
  build_id       uuid not null,

  stage          text not null
                   check (stage in ('self_check','independent_remeasure','render_review')),
  -- 규칙 §8 — 판독·모델링·검증은 서로 다른 에이전트가 맡는다(자기 검증 금지).
  performed_by   text not null check (length(btrim(performed_by)) > 0),
  builder_agent  text,
  performed_at   timestamptz not null default now(),

  -- [{name, kind, expected, measured, tolerance, unit, expected_derived_from, method, result}]
  checks         jsonb not null check (public.m3d_verification_checks_valid(checks)),
  overall        text not null check (overall in ('PASS','FAIL')),
  notes          text,
  created_at     timestamptz not null default now(),

  constraint verifications_id_project_uniq unique (id, project_id),
  constraint verifications_build_same_project
    foreign key (build_id, project_id)
    references public.builds (id, project_id) on delete cascade,

  -- 규칙 §6 — 실패는 실패로 보고. FAIL 항목이 하나라도 있으면 overall 은 PASS 일 수 없다.
  constraint verifications_overall_matches_checks check (
    overall = 'FAIL' or public.m3d_verification_fail_count(checks) = 0
  ),
  -- 규칙 §6-2 — 독립 재실측은 빌더와 다른 주체가, 사양서에서 자체 유도한 기대값으로 한다.
  constraint verifications_independent_not_self check (
    stage <> 'independent_remeasure'
    or (builder_agent is not null and performed_by <> builder_agent)
  ),
  constraint verifications_independent_expectations_not_from_builder_code check (
    stage <> 'independent_remeasure'
    or public.m3d_checks_free_of_builder_code(checks)
  )
);

comment on table public.verifications is
  '3중 검증 리포트 (규칙 §6). 추가 전용 — 재검증은 새 행으로 남긴다.';

create index verifications_project_id_idx on public.verifications (project_id);
create index verifications_build_stage_idx on public.verifications (build_id, stage, performed_at desc);
create index verifications_checks_gin on public.verifications using gin (checks);


-- ── 10. renders — 렌더 세트 (규칙 §6-3·§7) ──────────────────────────────────
create table public.renders (
  id               uuid primary key default gen_random_uuid(),
  project_id       uuid not null references public.projects (id) on delete cascade,
  build_id         uuid not null,
  verification_id  uuid,

  -- 규칙 §6-3 — 실척 정사영 / 맥락(인접 구간 스텁 포함) / 내부 컷
  kind             text not null check (kind in ('orthographic','context','interior_cut')),
  path             text not null check (length(btrim(path)) > 0),   -- renders 버킷
  note             text,
  width_px         integer check (width_px > 0),
  height_px        integer check (height_px > 0),
  -- 규칙 §6-3 — 정사영은 실척(set_aspect equal)이어야 검증에 쓸 수 있다.
  true_scale       boolean not null default false,
  -- 규칙 §7 — 2D 연동용 뷰 계약 (origin·u/v축·extent·왕복검산)
  view_contract    jsonb check (public.m3d_view_contract_valid(view_contract)),
  created_at       timestamptz not null default now(),

  constraint renders_id_project_uniq unique (id, project_id),
  constraint renders_build_same_project
    foreign key (build_id, project_id)
    references public.builds (id, project_id) on delete cascade,
  constraint renders_verification_same_project
    foreign key (verification_id, project_id)
    references public.verifications (id, project_id) on delete set null,
  constraint renders_build_kind_path_uniq unique (build_id, kind, path),
  -- 정사영 렌더는 실척이어야 한다. 실척 아닌 정사영은 검증 증적이 될 수 없다.
  constraint renders_orthographic_is_true_scale check (
    kind <> 'orthographic' or true_scale
  )
);

comment on table public.renders is
  '렌더 세트 (규칙 §6-3). 정사영·맥락·내부컷 3종이 승인 게이트의 전제다.';

create index renders_project_id_idx on public.renders (project_id);
create index renders_build_kind_idx on public.renders (build_id, kind);
create index renders_verification_idx on public.renders (verification_id);


-- ── 11. approvals — 승인 게이트 이력 (규칙 §5·§6) ───────────────────────────
create table public.approvals (
  id           uuid primary key default gen_random_uuid(),
  project_id   uuid not null references public.projects (id) on delete cascade,

  target_type  text not null
                 check (target_type in ('build','ssot','spec','render_set','coordinate_system')),
  target_id    uuid,
  -- build 대상일 때 채운다. 3중 검증 게이트 트리거가 이 값을 본다.
  build_id     uuid,
  -- 규칙 §5 — 대표 구간 시범 → 사용자 승인 → 확산
  gate         text not null default 'pilot'
                 check (gate in ('pilot','rollout','final')),

  approver_id  uuid not null references auth.users (id) on delete restrict,
  approver     text not null check (length(btrim(approver)) > 0),
  result       text not null check (result in ('approved','rejected','changes_requested')),
  decided_at   timestamptz not null default now(),
  note         text,
  created_at   timestamptz not null default now(),

  constraint approvals_build_same_project
    foreign key (build_id, project_id)
    references public.builds (id, project_id) on delete cascade,
  constraint approvals_build_target_needs_build_id check (
    target_type <> 'build' or build_id is not null
  ),
  -- 반려·수정요청에는 사유를 남긴다.
  constraint approvals_rejection_requires_note check (
    result = 'approved' or note is not null
  )
);

comment on table public.approvals is
  '승인 게이트 이력 (규칙 §5·§6). 추가 전용. build 승인은 3중 검증 트리거를 통과해야 한다.';

create index approvals_project_id_idx on public.approvals (project_id);
create index approvals_target_idx on public.approvals (project_id, target_type, target_id);
create index approvals_build_idx on public.approvals (build_id, decided_at desc);


-- ── 승인 게이트: 3중 검증 없이 "완료" 선언 금지 (규칙 §6, CLAUDE.md §3) ─────
create or replace function public.m3d_assert_build_gate()
returns trigger
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  v_self_check_result text;
  v_ok                boolean;
begin
  if new.result <> 'approved' or new.target_type <> 'build' then
    return new;
  end if;

  select b.self_check_result into v_self_check_result
  from public.builds b
  where b.id = new.build_id;

  if not found then
    raise exception '승인 대상 빌드를 찾을 수 없습니다: %', new.build_id
      using errcode = 'foreign_key_violation';
  end if;

  -- (1) 빌더 self-check
  if v_self_check_result is distinct from 'PASS' then
    raise exception '규칙 §6-1 위반: 빌더 self-check PASS 없이 빌드 % 를 승인할 수 없습니다.', new.build_id
      using errcode = 'check_violation';
  end if;

  -- (2) 독립 재실측 (자기 검증 금지)
  select exists (
    select 1 from public.verifications v
    where v.build_id = new.build_id
      and v.stage = 'independent_remeasure'
      and v.overall = 'PASS'
      and v.builder_agent is not null
      and v.performed_by <> v.builder_agent
  ) into v_ok;
  if not v_ok then
    raise exception '규칙 §6-2 위반: 독립 재실측 PASS 없이 빌드 % 를 승인할 수 없습니다.', new.build_id
      using errcode = 'check_violation';
  end if;

  -- (3) 렌더 육안 — 정사영·맥락·내부컷 3종이 모두 있어야 한다.
  select exists (
    select 1 from public.verifications v
    where v.build_id = new.build_id and v.stage = 'render_review' and v.overall = 'PASS'
  ) and (
    select count(distinct r.kind) = 3 from public.renders r where r.build_id = new.build_id
  ) into v_ok;
  if not v_ok then
    raise exception '규칙 §6-3 위반: 렌더 육안 검수(정사영·맥락·내부컷 3종) PASS 없이 빌드 %  를 승인할 수 없습니다.', new.build_id
      using errcode = 'check_violation';
  end if;

  return new;
end;
$fn$;

comment on function public.m3d_assert_build_gate() is
  '규칙 §6 — 3중 검증(self-check → 독립 재실측 → 렌더 육안) 없이 빌드 승인 불가.';

create trigger approvals_build_gate
  before insert on public.approvals
  for each row execute function public.m3d_assert_build_gate();


-- ── 결정 → 애매성 상태 반영 (규칙 §4 "결정을 SSOT 반영") ────────────────────
create or replace function public.m3d_apply_decision_to_ambiguity()
returns trigger
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  v_option_count integer;
begin
  select jsonb_array_length(a.options) into v_option_count
  from public.ambiguities a
  where a.id = new.ambiguity_id;

  -- 선택 인덱스가 실제 선택지 범위를 벗어나면 안 된다.
  if new.choice_index is not null and new.choice_index >= v_option_count then
    raise exception '선택지 범위 초과: choice_index=% 인데 선택지는 %개입니다.',
      new.choice_index, v_option_count
      using errcode = 'check_violation';
  end if;

  update public.ambiguities a
  set status = case when new.provisional then 'provisional' else 'decided' end,
      -- 규칙 §4 — 재확인은 1회로 제한. supersedes 가 있으면 재확인 1회로 센다.
      reconfirm_count = case
        when new.supersedes is not null then a.reconfirm_count + 1
        else a.reconfirm_count
      end
  where a.id = new.ambiguity_id;

  return new;
end;
$fn$;

create trigger decisions_apply_to_ambiguity
  after insert on public.decisions
  for each row execute function public.m3d_apply_decision_to_ambiguity();
