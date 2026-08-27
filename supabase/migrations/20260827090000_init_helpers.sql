-- ============================================================================
-- model3d-studio — 01. 확장·스키마·검증 헬퍼
--
-- 정본: docs/모델링규칙_지식베이스_v0.md, docs/아키텍처_MCP구성_v0.md §4
-- 이 파일의 함수들은 "규칙을 스키마로 강제한다"는 원칙의 구현체다.
-- CHECK 제약에서 호출하므로 전부 IMMUTABLE 이어야 한다.
--
-- 주의: 캐스트가 들어가는 검증은 AND/OR 대신 CASE 를 쓴다.
--       Postgres 는 AND/OR 의 평가 순서를 보장하지 않으므로
--       (x is number) and (x::numeric > 0) 형태는 타입 오류를 낼 수 있다.
--
-- 함정 2: jsonb_typeof(없는 키) 는 NULL 이다. `<> 'number'` 는 NULL 이 되고
--       CASE 는 ELSE 로 빠져 **검증이 통째로 건너뛰어진다**.
--       키 부재를 잡으려면 반드시 IS DISTINCT FROM 을 쓴다.
-- 함정 3: array_length(빈 배열, 1) 은 0 이 아니라 NULL 이다. CHECK 는 NULL 을
--       통과로 취급하므로 `array_length(a,1) >= 1` 은 빈 배열을 막지 못한다.
--       개수 제약에는 cardinality() 를 쓴다.
-- ============================================================================

create extension if not exists pgcrypto;

-- RLS 헬퍼 전용 스키마. PostgREST 에 노출되지 않는다.
create schema if not exists private;

comment on schema private is
  'RLS 정책이 쓰는 security definer 헬퍼. PostgREST 노출 금지(재귀 정책 회피용).';

-- ── updated_at 자동 갱신 ────────────────────────────────────────────────────
create or replace function public.m3d_set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $fn$
begin
  new.updated_at := now();
  return new;
end;
$fn$;

comment on function public.m3d_set_updated_at() is 'updated_at 자동 갱신 트리거 함수.';

-- ── 좌표계 (규칙 §1) ────────────────────────────────────────────────────────
-- axes = {x:{meaning,positive_direction,assumed}, y:{...}, z:{...}}
create or replace function public.m3d_axes_valid(axes jsonb)
returns boolean
language sql
immutable
parallel safe
set search_path = ''
as $fn$
  select case
    when axes is null then true
    when jsonb_typeof(axes) <> 'object' then false
    when not (axes ? 'x' and axes ? 'y' and axes ? 'z') then false
    else not exists (
      select 1
      from jsonb_each(axes) as e(k, v)
      where jsonb_typeof(v) is distinct from 'object'
         or coalesce(v ->> 'meaning', '') = ''
         or coalesce(v ->> 'positive_direction', '') = ''
         or jsonb_typeof(v -> 'assumed') is distinct from 'boolean'
    )
  end;
$fn$;

-- assumptions = [{item, assumed_value, reason, flip_test, resolved?}]
-- 규칙 §1 — 방위 미확정이면 가정임을 표기하고 "뒤집기 검증"(flip_test) 을 등재한다.
create or replace function public.m3d_assumptions_valid(assumptions jsonb)
returns boolean
language sql
immutable
parallel safe
set search_path = ''
as $fn$
  select case
    when assumptions is null then true
    when jsonb_typeof(assumptions) <> 'array' then false
    else not exists (
      select 1
      from jsonb_array_elements(assumptions) as a
      where jsonb_typeof(a) is distinct from 'object'
         or coalesce(a ->> 'item', '') = ''
         or coalesce(a ->> 'assumed_value', '') = ''
         or coalesce(a ->> 'reason', '') = ''
         or coalesce(a ->> 'flip_test', '') = ''
    )
  end;
$fn$;

-- 규칙 §1 — assumed=true 인 축이 있으면 assumptions 에 대응 항목이 최소 1개 있어야 한다.
create or replace function public.m3d_assumed_axes_are_registered(axes jsonb, assumptions jsonb)
returns boolean
language sql
immutable
parallel safe
set search_path = ''
as $fn$
  select case
    when axes is null then true
    when jsonb_typeof(axes) <> 'object' then true      -- 형식 검증은 m3d_axes_valid 담당
    when not exists (
      select 1 from jsonb_each(axes) as e(k, v) where v -> 'assumed' = 'true'::jsonb
    ) then true
    when assumptions is null then false
    when jsonb_typeof(assumptions) <> 'array' then false
    else jsonb_array_length(assumptions) >= 1
  end;
$fn$;

-- ── 애매성 선택지 (규칙 §3·§4) ──────────────────────────────────────────────
-- 2~4개, 첫 번째가 권장안, 각 선택지에 근거와 모델 영향이 붙어야 한다.
create or replace function public.m3d_ambiguity_options_valid(options jsonb)
returns boolean
language sql
immutable
parallel safe
set search_path = ''
as $fn$
  select case
    when options is null then false
    when jsonb_typeof(options) <> 'array' then false
    when jsonb_array_length(options) < 2 then false
    when jsonb_array_length(options) > 4 then false
    when (options -> 0 -> 'recommended') is distinct from 'true'::jsonb then false
    else not exists (
      select 1
      from jsonb_array_elements(options) as o
      where jsonb_typeof(o) is distinct from 'object'
         or coalesce(o ->> 'label', '') = ''
         or coalesce(o ->> 'rationale', '') = ''       -- 근거 없는 선택지는 반려 (§8)
         or coalesce(o ->> 'model_impact', '') = ''    -- 모델 영향 명시 필수 (§4)
         or jsonb_typeof(o -> 'recommended') is distinct from 'boolean'
    )
  end;
$fn$;

comment on function public.m3d_ambiguity_options_valid(jsonb) is
  '규칙 §3·§4 — 해석 선택지는 2~4개, [0]은 권장안, 각 선택지에 근거·모델 영향 필수.';

-- ── 크롭 참조 (규칙 §4) ─────────────────────────────────────────────────────
-- sheet_refs = [{sheet_no, page?, bbox_px:[x,y,w,h], crop_path?, caption?}]
create or replace function public.m3d_sheet_refs_valid(refs jsonb)
returns boolean
language sql
immutable
parallel safe
set search_path = ''
as $fn$
  select case
    when refs is null then false
    when jsonb_typeof(refs) <> 'array' then false
    when jsonb_array_length(refs) < 1 then false       -- 크롭 없는 질문은 금지 (§4)
    else not exists (
      select 1
      from jsonb_array_elements(refs) as r
      where jsonb_typeof(r) is distinct from 'object'
         or coalesce(r ->> 'sheet_no', '') = ''
         or case
              when jsonb_typeof(r -> 'bbox_px') is distinct from 'array' then true
              when jsonb_array_length(r -> 'bbox_px') <> 4 then true
              else exists (
                select 1
                from jsonb_array_elements(r -> 'bbox_px') as b
                where jsonb_typeof(b) <> 'number'
              )
            end
    )
  end;
$fn$;

comment on function public.m3d_sheet_refs_valid(jsonb) is
  '규칙 §4 — 질문에는 반드시 도면 크롭이 따른다. 최소 1개, bbox_px=[x,y,w,h] 픽셀 좌표.';

-- ── 부재 명명 규칙 (규칙 §5) ────────────────────────────────────────────────
-- packages/contracts/src/memberName.ts 의 MEMBER_CODE_PATTERN 과 문자열이 일치해야 한다.
create or replace function public.m3d_member_code_pattern()
returns text
language sql
immutable
parallel safe
as $fn$
  select '^[A-Z][A-Z0-9]{0,7}_S[0-9]{1,3}_[A-Z]{2,4}[0-9]{1,4}[LRCTB]?$'
$fn$;

-- code 와 분해 성분이 서로 모순되지 않는지 (memberCodeMatchesFields 의 DB 판)
create or replace function public.m3d_member_code_matches(
  p_code text,
  p_structure text,
  p_segment text,
  p_member_type text,
  p_index integer,
  p_side text
)
returns boolean
language sql
immutable
parallel safe
set search_path = ''
as $fn$
  select case
    when m is null then false
    when m[1] is distinct from p_structure then false
    when m[2] is distinct from p_segment then false
    when m[3] is distinct from p_member_type then false
    when m[4]::integer is distinct from p_index then false
    when coalesce(m[5], '') is distinct from coalesce(p_side, '') then false
    else true
  end
  from (
    select regexp_match(
      p_code,
      '^([A-Z][A-Z0-9]{0,7})_(S[0-9]{1,3})_([A-Z]{2,4})([0-9]{1,4})([LRCTB])?$'
    ) as m
  ) t;
$fn$;

comment on function public.m3d_member_code_matches(text, text, text, text, integer, text) is
  '규칙 §5 — 부재 code 와 분해 성분(structure/segment/member_type/index/side)의 정합성.';

-- zone = {name, spacing_mm>0, count>=1, start_station?, transition_note?}
create or replace function public.m3d_member_zone_valid(zone jsonb)
returns boolean
language sql
immutable
parallel safe
set search_path = ''
as $fn$
  select case
    when zone is null then true
    when jsonb_typeof(zone) <> 'object' then false
    when coalesce(zone ->> 'name', '') = '' then false
    when jsonb_typeof(zone -> 'spacing_mm') is distinct from 'number' then false
    when jsonb_typeof(zone -> 'count') is distinct from 'number' then false
    when (zone ->> 'spacing_mm')::numeric <= 0 then false
    when (zone ->> 'count')::numeric < 1 then false
    else true
  end;
$fn$;

-- ── 검증 리포트 (규칙 §6) ───────────────────────────────────────────────────
create or replace function public.m3d_verification_checks_valid(checks jsonb)
returns boolean
language sql
immutable
parallel safe
set search_path = ''
as $fn$
  select case
    when checks is null then false
    when jsonb_typeof(checks) <> 'array' then false
    when jsonb_array_length(checks) < 1 then false
    else not exists (
      select 1
      from jsonb_array_elements(checks) as c
      where jsonb_typeof(c) is distinct from 'object'
         or coalesce(c ->> 'name', '') = ''
         or coalesce(c ->> 'kind', '') not in ('grid','count','elevation','watertight','dimension')
         or coalesce(c ->> 'unit', '') not in ('mm','m','ea','-')
         or coalesce(c ->> 'expected_derived_from', '') not in ('spec','builder_code','drawing')
         or coalesce(c ->> 'method', '') not in ('slice','bbox','node_count','mesh_query','visual')
         or coalesce(c ->> 'result', '') not in ('PASS','FAIL')
         or (c -> 'expected') is null
         or (c -> 'measured') is null
         or case
              when jsonb_typeof(c -> 'tolerance') is distinct from 'number' then true  -- 허용오차 명시 필수 (§6)
              else (c ->> 'tolerance')::numeric < 0
            end
    )
  end;
$fn$;

comment on function public.m3d_verification_checks_valid(jsonb) is
  '규칙 §6 — 검증 항목마다 기대값·측정값·허용오차·판정·측정방법·기대값 출처가 모두 있어야 한다.';

create or replace function public.m3d_verification_fail_count(checks jsonb)
returns integer
language sql
immutable
parallel safe
set search_path = ''
as $fn$
  select count(*)::integer
  from jsonb_array_elements(
    case when jsonb_typeof(checks) = 'array' then checks else '[]'::jsonb end
  ) as c
  where c ->> 'result' = 'FAIL';
$fn$;

-- 규칙 §6-2 — 독립 재실측의 기대값은 빌더 코드가 아니라 사양서에서 자체 유도해야 한다.
create or replace function public.m3d_checks_free_of_builder_code(checks jsonb)
returns boolean
language sql
immutable
parallel safe
set search_path = ''
as $fn$
  select not exists (
    select 1
    from jsonb_array_elements(
      case when jsonb_typeof(checks) = 'array' then checks else '[]'::jsonb end
    ) as c
    where c ->> 'expected_derived_from' = 'builder_code'
  );
$fn$;

-- ── 뷰 계약 (규칙 §7) ───────────────────────────────────────────────────────
create or replace function public.m3d_is_vec3(v jsonb)
returns boolean
language sql
immutable
parallel safe
set search_path = ''
as $fn$
  select case
    when jsonb_typeof(v) is distinct from 'array' then false
    when jsonb_array_length(v) <> 3 then false
    else not exists (
      select 1 from jsonb_array_elements(v) as e where jsonb_typeof(e) <> 'number'
    )
  end;
$fn$;

create or replace function public.m3d_view_contract_valid(vc jsonb)
returns boolean
language sql
immutable
parallel safe
set search_path = ''
as $fn$
  select case
    when vc is null then true
    when jsonb_typeof(vc) <> 'object' then false
    when coalesce(vc ->> 'unit', '') <> 'm' then false
    when not public.m3d_is_vec3(vc -> 'origin') then false
    when not public.m3d_is_vec3(vc -> 'u_axis') then false
    when not public.m3d_is_vec3(vc -> 'v_axis') then false
    when jsonb_typeof(vc -> 'u_extent') is distinct from 'number' then false
    when jsonb_typeof(vc -> 'v_extent') is distinct from 'number' then false
    when (vc ->> 'u_extent')::numeric <= 0 then false
    when (vc ->> 'v_extent')::numeric <= 0 then false
    -- 규칙 §7 — 왕복 검산이 실려 있다면 PASS 여야 한다. 검산 없는 뷰 계약은 싣지 않는다.
    when (vc -> 'roundtrip_check') is null then true
    when (vc -> 'roundtrip_check') = 'null'::jsonb then true
    when jsonb_typeof(vc -> 'roundtrip_check') is distinct from 'object' then false
    when coalesce(vc -> 'roundtrip_check' ->> 'result', '') <> 'PASS' then false
    else true
  end;
$fn$;

comment on function public.m3d_view_contract_valid(jsonb) is
  '규칙 §7 — 뷰 계약(origin·u/v축·extent·왕복검산). 검산이 실렸다면 PASS 여야 한다.';
