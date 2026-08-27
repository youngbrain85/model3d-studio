\set ON_ERROR_STOP on
\pset pager off

create or replace function t_reject(p_sql text, p_label text) returns text
language plpgsql as $f$
begin
  begin
    execute p_sql;
    raise exception using errcode = 'ZZ001';
  exception
    when sqlstate 'ZZ001' then return 'FAIL  거부되어야 하는데 통과: ' || p_label;
    when others then return 'ok    거부됨: ' || p_label;
  end;
end $f$;

-- RLS 는 UPDATE/DELETE 를 예외가 아니라 "영향 행 0" 으로 차단한다.
create or replace function t_zero_rows(p_sql text, p_label text) returns text
language plpgsql as $f$
declare n integer;
begin
  begin
    execute p_sql;
    get diagnostics n = row_count;
    raise exception using errcode = 'ZZ002', message = n::text;
  exception
    when sqlstate 'ZZ002' then
      if sqlerrm::integer = 0 then return 'ok    차단됨(0행): ' || p_label;
      else return 'FAIL  ' || sqlerrm || '행이 영향받음: ' || p_label; end if;
    when others then return 'ok    거부됨: ' || p_label;
  end;
end $f$;

create or replace function t_accept(p_sql text, p_label text) returns text
language plpgsql as $f$
begin
  execute p_sql;
  return 'ok    허용됨: ' || p_label;
exception when others then
  return 'FAIL  허용되어야 하는데 거부: ' || p_label || ' [' || sqlstate || ' ' || sqlerrm || ']';
end $f$;

-- ── 기준 데이터 ─────────────────────────────────────────────────────────────
insert into auth.users (id, email) values
  ('11111111-1111-1111-1111-111111111111','owner@example.com'),
  ('22222222-2222-2222-2222-222222222222','viewer@example.com'),
  ('33333333-3333-3333-3333-333333333333','outsider@example.com');

insert into public.projects (id, owner_id, name, structure_code, status, up_axis,
                             axes, origin_reference, coordinate_system_locked_at)
values ('aaaaaaaa-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111',
        '원산안면대교 접속1교','AB1','active','Y',
        '{"x":{"meaning":"교축직각","positive_direction":"+동측","assumed":false},
          "y":{"meaning":"EL−오프셋","positive_direction":"+상방","assumed":false},
          "z":{"meaning":"STA−오프셋","positive_direction":"+종점","assumed":false}}'::jsonb,
        '{"description":"P4 받침선 중심"}'::jsonb, now());

insert into public.projects (id, owner_id, name, structure_code, status)
values ('aaaaaaaa-0000-0000-0000-000000000002','11111111-1111-1111-1111-111111111111',
        '타 프로젝트','AB2','active');

insert into public.sheets (id, project_id, file_name, page,
       sheet_no_from_titleblock, sheet_no_from_filename, titleblock_match, title, scale,
       coverage_station_from, coverage_source, source_format)
values ('bbbbbbbb-0000-0000-0000-000000000001','aaaaaaaa-0000-0000-0000-000000000001',
        'AB1_S5.pdf', 1, 'S-105','S-105','match','접속1교 일반도','1/100',
        'STA 1+240','keyplan_hatch','pdf');

insert into public.structural_members (id, project_id, code, structure, segment, member_type, member_index, side)
values ('cccccccc-0000-0000-0000-000000000001','aaaaaaaa-0000-0000-0000-000000000001',
        'AB1_S5_DIA07','AB1','S5','DIA',7,null);

insert into public.ambiguities (id, project_id, item, question, primary_sheet_id, sheet_refs, options, model_impact)
values ('dddddddd-0000-0000-0000-000000000001','aaaaaaaa-0000-0000-0000-000000000001',
        '다이아프램 열수','S5 구간 다이아프램은 3열인가 8열인가?',
        'bbbbbbbb-0000-0000-0000-000000000001',
        '[{"sheet_no":"S-105","page":1,"bbox_px":[100,200,400,300],"crop_path":"aaaaaaaa-0000-0000-0000-000000000001/ambiguities/dddddddd-0000-0000-0000-000000000001/1.png"}]'::jsonb,
        '[{"label":"구간별 병존(3열+8열)","rationale":"S-105 본문 좌표 표기와 S-112 상세도가 서로 다른 존을 가리킴","model_impact":"전이 구간 분절 스윕 필요","recommended":true},
          {"label":"전 구간 8열","rationale":"S-112 상세도만 근거","model_impact":"단일 배열 규칙","recommended":false}]'::jsonb,
        '다이아프램 개수와 전이 구간 처리 방식이 달라진다');

\echo '━━━ 1. readings — 근거·검산 규칙 (규칙 §2·§8) ━━━'
select t_reject($q$insert into public.readings (project_id,item,value_num,unit,source_sheets,status,derived)
  values ('aaaaaaaa-0000-0000-0000-000000000001','근거없는수치',1200,'mm','{}','confirmed',false)$q$,
  '근거 도면번호 없는 수치 (source_sheets 빈 배열)');
select t_reject($q$insert into public.readings (project_id,item,value_num,unit,source_sheets,status,derived)
  values ('aaaaaaaa-0000-0000-0000-000000000001','널근거',1200,'mm','{NULL}','confirmed',false)$q$,
  'source_sheets 에 NULL 원소');
select t_reject($q$insert into public.readings (project_id,item,value_num,unit,source_sheets,status,derived,derivation_formula,derivation_inputs)
  values ('aaaaaaaa-0000-0000-0000-000000000001','검산없는파생',1200,'mm','{S-105}','confirmed',true,'a+b','{a,b}')$q$,
  '파생값인데 검산 없음');
select t_reject($q$insert into public.readings (project_id,item,value_num,unit,source_sheets,status,derived,
    cross_check_formula,cross_check_expected,cross_check_actual,cross_check_tolerance,cross_check_result)
  values ('aaaaaaaa-0000-0000-0000-000000000001','검산FAIL확정',1200,'mm','{S-105}','confirmed',false,
    '구간합=전장',1200,1150,5,'FAIL')$q$,
  '검산 FAIL 인데 status=confirmed');
select t_reject($q$insert into public.readings (project_id,item,value_num,unit,source_sheets,cross_source_confirmed,status,derived)
  values ('aaaaaaaa-0000-0000-0000-000000000001','교차확인위조',1200,'mm','{S-105}',true,'confirmed',false)$q$,
  '근거 1개인데 cross_source_confirmed=true');
select t_reject($q$insert into public.readings (project_id,item,value_num,value_text,unit,source_sheets,status,derived)
  values ('aaaaaaaa-0000-0000-0000-000000000001','값중복',1200,'천이백','mm','{S-105}','confirmed',false)$q$,
  'value_num 과 value_text 동시 지정');
select t_reject($q$insert into public.readings (project_id,item,value_num,unit,source_sheets,status,derived,cross_check_formula)
  values ('aaaaaaaa-0000-0000-0000-000000000001','검산부분',1200,'mm','{S-105}','confirmed',false,'식만있음')$q$,
  '검산 필드 일부만 채움');
select t_accept($q$insert into public.readings (project_id,item,value_num,unit,source_sheets,cross_source_confirmed,status,derived,
    derivation_formula,derivation_inputs,cross_check_formula,cross_check_expected,cross_check_actual,cross_check_tolerance,cross_check_result)
  values ('aaaaaaaa-0000-0000-0000-000000000001','S5 전장',48000,'mm','{S-105,S-112}',true,'confirmed',true,
    '구간합',' {seg1,seg2}',' 구간합=전장',48000,48000,5,'PASS')$q$,
  '근거2개+파생+검산PASS 인 확정값');

\echo '━━━ 2. ambiguities — 선택지 2~4개·권장안·근거 (규칙 §3·§4) ━━━'
select t_reject($q$insert into public.ambiguities (project_id,item,question,sheet_refs,options,model_impact)
  values ('aaaaaaaa-0000-0000-0000-000000000001','x','q?','[{"sheet_no":"S-105","bbox_px":[0,0,10,10]}]',
  '[{"label":"a","rationale":"r","model_impact":"m","recommended":true}]','mi')$q$,
  '선택지 1개');
select t_reject($q$insert into public.ambiguities (project_id,item,question,sheet_refs,options,model_impact)
  values ('aaaaaaaa-0000-0000-0000-000000000001','x','q?','[{"sheet_no":"S-105","bbox_px":[0,0,10,10]}]',
  '[{"label":"a","rationale":"r","model_impact":"m","recommended":true},
    {"label":"b","rationale":"r","model_impact":"m","recommended":false},
    {"label":"c","rationale":"r","model_impact":"m","recommended":false},
    {"label":"d","rationale":"r","model_impact":"m","recommended":false},
    {"label":"e","rationale":"r","model_impact":"m","recommended":false}]','mi')$q$,
  '선택지 5개');
select t_reject($q$insert into public.ambiguities (project_id,item,question,sheet_refs,options,model_impact)
  values ('aaaaaaaa-0000-0000-0000-000000000001','x','q?','[{"sheet_no":"S-105","bbox_px":[0,0,10,10]}]',
  '[{"label":"a","rationale":"r","model_impact":"m","recommended":false},
    {"label":"b","rationale":"r","model_impact":"m","recommended":true}]','mi')$q$,
  '권장안이 첫 번째가 아님');
select t_reject($q$insert into public.ambiguities (project_id,item,question,sheet_refs,options,model_impact)
  values ('aaaaaaaa-0000-0000-0000-000000000001','x','q?','[{"sheet_no":"S-105","bbox_px":[0,0,10,10]}]',
  '[{"label":"a","model_impact":"m","recommended":true},
    {"label":"b","rationale":"r","model_impact":"m","recommended":false}]','mi')$q$,
  '근거(rationale) 없는 선택지');
select t_reject($q$insert into public.ambiguities (project_id,item,question,sheet_refs,options,model_impact)
  values ('aaaaaaaa-0000-0000-0000-000000000001','x','q?','[{"sheet_no":"S-105","bbox_px":[0,0,10,10]}]',
  '[{"label":"a","rationale":"r","recommended":true},
    {"label":"b","rationale":"r","model_impact":"m","recommended":false}]','mi')$q$,
  '모델 영향 없는 선택지');
select t_reject($q$insert into public.ambiguities (project_id,item,question,sheet_refs,options,model_impact)
  values ('aaaaaaaa-0000-0000-0000-000000000001','x','q?','[]',
  '[{"label":"a","rationale":"r","model_impact":"m","recommended":true},
    {"label":"b","rationale":"r","model_impact":"m","recommended":false}]','mi')$q$,
  '크롭 참조 없는 질문');
select t_reject($q$insert into public.ambiguities (project_id,item,question,sheet_refs,options,model_impact)
  values ('aaaaaaaa-0000-0000-0000-000000000001','x','q?','[{"sheet_no":"S-105","bbox_px":[0,0,10]}]',
  '[{"label":"a","rationale":"r","model_impact":"m","recommended":true},
    {"label":"b","rationale":"r","model_impact":"m","recommended":false}]','mi')$q$,
  'bbox_px 원소 3개 (x,y,w,h 아님)');
select t_reject($q$insert into public.ambiguities (project_id,item,question,sheet_refs,options,model_impact,allow_unknown)
  values ('aaaaaaaa-0000-0000-0000-000000000001','x','q?','[{"sheet_no":"S-105","bbox_px":[0,0,10,10]}]',
  '[{"label":"a","rationale":"r","model_impact":"m","recommended":true},
    {"label":"b","rationale":"r","model_impact":"m","recommended":false}]','mi',false)$q$,
  '"모르겠다" 선택지 비허용 (allow_unknown=false)');

\echo '━━━ 3. decisions — 잠정 규칙 (규칙 §4) ━━━'
select t_reject($q$insert into public.decisions (project_id,ambiguity_id,choice_unknown,provisional,responder)
  values ('aaaaaaaa-0000-0000-0000-000000000001','dddddddd-0000-0000-0000-000000000001',true,false,'user')$q$,
  '"모르겠다"인데 provisional=false');
select t_reject($q$insert into public.decisions (project_id,ambiguity_id,choice_index,choice_unknown,provisional,responder)
  values ('aaaaaaaa-0000-0000-0000-000000000001','dddddddd-0000-0000-0000-000000000001',0,true,true,'user')$q$,
  'choice_index 와 choice_unknown 동시 지정');
select t_reject($q$insert into public.decisions (project_id,ambiguity_id,choice_index,provisional,responder)
  values ('aaaaaaaa-0000-0000-0000-000000000001','dddddddd-0000-0000-0000-000000000001',3,false,'user')$q$,
  '선택지 2개인데 choice_index=3 (범위 초과)');
select t_reject($q$insert into public.decisions (project_id,ambiguity_id,choice_index,provisional,responder)
  values ('aaaaaaaa-0000-0000-0000-000000000002','dddddddd-0000-0000-0000-000000000001',0,false,'user')$q$,
  '다른 프로젝트의 ambiguity 참조 (테넌트 격리)');
select t_accept($q$insert into public.decisions (id,project_id,ambiguity_id,choice_index,provisional,responder,responder_id)
  values ('eeeeeeee-0000-0000-0000-000000000001','aaaaaaaa-0000-0000-0000-000000000001',
          'dddddddd-0000-0000-0000-000000000001',0,false,'박준영','11111111-1111-1111-1111-111111111111')$q$,
  '정상 결정 (권장안 채택)');
select '  → ambiguity.status = ' || status || ' (기대: decided)' from public.ambiguities
  where id='dddddddd-0000-0000-0000-000000000001';
select t_reject($q$insert into public.readings (project_id,item,value_num,unit,source_sheets,status,derived,provisional_from_decision)
  values ('aaaaaaaa-0000-0000-0000-000000000001','잠정확정',1,'mm','{S-105}','confirmed',false,'eeeeeeee-0000-0000-0000-000000000001')$q$,
  '잠정 결정 유래 값을 confirmed 로');

\echo '━━━ 4. sheets — 표제란 대조 (규칙 §3) ━━━'
select t_reject($q$insert into public.sheets (project_id,file_name,page,sheet_no_from_titleblock,sheet_no_from_filename,titleblock_match)
  values ('aaaaaaaa-0000-0000-0000-000000000001','x.pdf',1,'S-101','S-999','match')$q$,
  'match 인데 도면번호가 다름');
select t_reject($q$insert into public.sheets (project_id,file_name,page,sheet_no_from_titleblock,sheet_no_from_filename,titleblock_match)
  values ('aaaaaaaa-0000-0000-0000-000000000001','y.pdf',1,'S-101','S-101','mismatch')$q$,
  'mismatch 인데 도면번호가 같음');
select t_reject($q$insert into public.sheets (project_id,file_name,page,sheet_no_from_titleblock,titleblock_match)
  values ('aaaaaaaa-0000-0000-0000-000000000001','z.pdf',1,'S-101','unreadable')$q$,
  'unreadable 인데 표제란 번호가 있음');
select t_reject($q$insert into public.sheets (project_id,file_name,page,sheet_no_from_filename,titleblock_match,coverage_station_from)
  values ('aaaaaaaa-0000-0000-0000-000000000001','w.pdf',1,'S-101','filename_only','STA 1+200')$q$,
  '커버리지를 적었는데 근거 출처(coverage_source) 없음');
select t_accept($q$insert into public.sheets (project_id,file_name,page,sheet_no_from_titleblock,sheet_no_from_filename,titleblock_match)
  values ('aaaaaaaa-0000-0000-0000-000000000001','편철오류.pdf',1,'S-112','S-105','mismatch')$q$,
  '편철 오류 기록 (mismatch)');

\echo '━━━ 5. structural_members — 명명 규칙·트리 (규칙 §5) ━━━'
select t_reject($q$insert into public.structural_members (project_id,code,structure,segment,member_type,member_index)
  values ('aaaaaaaa-0000-0000-0000-000000000001','ab1_s5_dia08','AB1','S5','DIA',8)$q$,
  '명명 규칙 위반 (소문자)');
select t_reject($q$insert into public.structural_members (project_id,code,structure,segment,member_type,member_index)
  values ('aaaaaaaa-0000-0000-0000-000000000001','AB1_S5_DIA08','AB1','S5','DIA',9)$q$,
  'code 와 member_index 불일치');
select t_reject($q$insert into public.structural_members (project_id,code,structure,segment,member_type,member_index,side)
  values ('aaaaaaaa-0000-0000-0000-000000000001','AB1_S5_WG097L','AB1','S5','WG',97,'R')$q$,
  'code 의 측면(L)과 side(R) 불일치');
select t_reject($q$insert into public.structural_members (project_id,code,structure,segment,member_type,member_index)
  values ('aaaaaaaa-0000-0000-0000-000000000001','AB1_S5_DIA07','AB1','S5','DIA',7)$q$,
  '같은 프로젝트 내 code 중복');
select t_reject($q$insert into public.structural_members (project_id,code,structure,segment,member_type,member_index,zone)
  values ('aaaaaaaa-0000-0000-0000-000000000001','AB1_S5_DIA09','AB1','S5','DIA',9,'{"name":"z","spacing_mm":0,"count":3}')$q$,
  'zone.spacing_mm = 0');
select t_accept($q$insert into public.structural_members (id,project_id,code,parent_id,structure,segment,member_type,member_index,side,zone)
  values ('cccccccc-0000-0000-0000-000000000002','aaaaaaaa-0000-0000-0000-000000000001','AB1_S5_WG097L',
          'cccccccc-0000-0000-0000-000000000001','AB1','S5','WG',97,'L',
          '{"name":"S5 웨브보강재","spacing_mm":500,"count":24,"transition_note":"전이구간 유력안 채택"}')$q$,
  '정상 부재 (부모 지정 + zone)');
select t_reject($q$update public.structural_members set parent_id='cccccccc-0000-0000-0000-000000000002'
  where id='cccccccc-0000-0000-0000-000000000001'$q$,
  '부재 트리 순환 (A→B→A)');
select t_reject($q$update public.structural_members set parent_id=id where id='cccccccc-0000-0000-0000-000000000001'$q$,
  '자기 자신을 부모로');

\echo '━━━ 6. builds / verifications — 3중 검증 (규칙 §6) ━━━'
insert into public.builds (id,project_id,version,builder_agent,status)
  values ('ffffffff-0000-0000-0000-000000000001','aaaaaaaa-0000-0000-0000-000000000001','v1.0.0','builder-agent-A','queued');
select t_reject($q$update public.builds set status='succeeded' where id='ffffffff-0000-0000-0000-000000000001'$q$,
  'self-check PASS·GLB 없이 succeeded 선언');
select t_accept($q$update public.builds set status='succeeded', glb_path='aaaaaaaa-0000-0000-0000-000000000001/builds/ffffffff-0000-0000-0000-000000000001/model.glb',
  self_check_result='PASS', self_check='{"grid":"PASS","watertight":true}', watertight=true
  where id='ffffffff-0000-0000-0000-000000000001'$q$, 'self-check PASS 후 succeeded');
select t_reject($q$insert into public.verifications (project_id,build_id,stage,performed_by,builder_agent,checks,overall)
  values ('aaaaaaaa-0000-0000-0000-000000000001','ffffffff-0000-0000-0000-000000000001','independent_remeasure',
  'builder-agent-A','builder-agent-A',
  '[{"name":"c","kind":"count","expected":24,"measured":24,"tolerance":0,"unit":"ea","expected_derived_from":"spec","method":"node_count","result":"PASS"}]','PASS')$q$,
  '독립 재실측인데 빌더가 자기 검증');
select t_reject($q$insert into public.verifications (project_id,build_id,stage,performed_by,builder_agent,checks,overall)
  values ('aaaaaaaa-0000-0000-0000-000000000001','ffffffff-0000-0000-0000-000000000001','independent_remeasure',
  'verifier-B','builder-agent-A',
  '[{"name":"c","kind":"count","expected":24,"measured":24,"tolerance":0,"unit":"ea","expected_derived_from":"builder_code","method":"node_count","result":"PASS"}]','PASS')$q$,
  '독립 재실측 기대값을 빌더 코드에서 가져옴');
select t_reject($q$insert into public.verifications (project_id,build_id,stage,performed_by,builder_agent,checks,overall)
  values ('aaaaaaaa-0000-0000-0000-000000000001','ffffffff-0000-0000-0000-000000000001','self_check','builder-agent-A','builder-agent-A',
  '[{"name":"c","kind":"count","expected":24,"measured":23,"tolerance":0,"unit":"ea","expected_derived_from":"spec","method":"node_count","result":"FAIL"}]','PASS')$q$,
  'FAIL 항목이 있는데 overall=PASS (실패 은폐)');
select t_reject($q$insert into public.verifications (project_id,build_id,stage,performed_by,checks,overall)
  values ('aaaaaaaa-0000-0000-0000-000000000001','ffffffff-0000-0000-0000-000000000001','self_check','builder-agent-A',
  '[{"name":"c","kind":"count","expected":24,"measured":24,"unit":"ea","expected_derived_from":"spec","method":"node_count","result":"PASS"}]','PASS')$q$,
  '허용오차(tolerance) 없는 검증 항목');

\echo '━━━ 7. approvals — 승인 게이트 (규칙 §6) ━━━'
select t_reject($q$insert into public.approvals (project_id,target_type,build_id,approver_id,approver,result)
  values ('aaaaaaaa-0000-0000-0000-000000000001','build','ffffffff-0000-0000-0000-000000000001',
  '11111111-1111-1111-1111-111111111111','박준영','approved')$q$,
  '3중 검증 전에 빌드 승인');
insert into public.verifications (project_id,build_id,stage,performed_by,builder_agent,checks,overall)
  values ('aaaaaaaa-0000-0000-0000-000000000001','ffffffff-0000-0000-0000-000000000001','independent_remeasure','verifier-B','builder-agent-A',
  '[{"name":"다이아프램 개수","kind":"count","expected":24,"measured":24,"tolerance":0,"unit":"ea","expected_derived_from":"spec","method":"node_count","result":"PASS"}]','PASS');
select t_reject($q$insert into public.approvals (project_id,target_type,build_id,approver_id,approver,result)
  values ('aaaaaaaa-0000-0000-0000-000000000001','build','ffffffff-0000-0000-0000-000000000001',
  '11111111-1111-1111-1111-111111111111','박준영','approved')$q$,
  '렌더 육안 검수 전에 빌드 승인');
select t_reject($q$insert into public.renders (project_id,build_id,kind,path,true_scale)
  values ('aaaaaaaa-0000-0000-0000-000000000001','ffffffff-0000-0000-0000-000000000001','orthographic','p.png',false)$q$,
  '실척 아닌 정사영 렌더');
insert into public.renders (project_id,build_id,kind,path,true_scale) values
  ('aaaaaaaa-0000-0000-0000-000000000001','ffffffff-0000-0000-0000-000000000001','orthographic','aaaaaaaa-0000-0000-0000-000000000001/builds/ffffffff-0000-0000-0000-000000000001/orthographic/side.png',true),
  ('aaaaaaaa-0000-0000-0000-000000000001','ffffffff-0000-0000-0000-000000000001','context','aaaaaaaa-0000-0000-0000-000000000001/builds/ffffffff-0000-0000-0000-000000000001/context/ctx.png',false),
  ('aaaaaaaa-0000-0000-0000-000000000001','ffffffff-0000-0000-0000-000000000001','interior_cut','aaaaaaaa-0000-0000-0000-000000000001/builds/ffffffff-0000-0000-0000-000000000001/interior_cut/cut.png',false);
insert into public.verifications (project_id,build_id,stage,performed_by,checks,overall)
  values ('aaaaaaaa-0000-0000-0000-000000000001','ffffffff-0000-0000-0000-000000000001','render_review','reviewer-C',
  '[{"name":"형상 육안","kind":"dimension","expected":0,"measured":0,"tolerance":0,"unit":"-","expected_derived_from":"drawing","method":"visual","result":"PASS"}]','PASS');
select t_accept($q$insert into public.approvals (project_id,target_type,build_id,approver_id,approver,result)
  values ('aaaaaaaa-0000-0000-0000-000000000001','build','ffffffff-0000-0000-0000-000000000001',
  '11111111-1111-1111-1111-111111111111','박준영','approved')$q$,
  '3중 검증 완료 후 빌드 승인');

\echo '━━━ 8. projects — 좌표계 확정 (규칙 §1) ━━━'
select t_reject($q$insert into public.projects (owner_id,name,structure_code,coordinate_system_locked_at)
  values ('11111111-1111-1111-1111-111111111111','축없이확정','AB3',now())$q$,
  '축·원점 없이 좌표계 확정 선언');
select t_reject($q$insert into public.projects (owner_id,name,structure_code,up_axis,axes,origin_reference)
  values ('11111111-1111-1111-1111-111111111111','가정미등재','AB4','Y',
  '{"x":{"meaning":"교축직각","positive_direction":"+동측","assumed":true},
    "y":{"meaning":"EL","positive_direction":"+상방","assumed":false},
    "z":{"meaning":"STA","positive_direction":"+종점","assumed":false}}','{"description":"o"}')$q$,
  '방위를 가정했는데 뒤집기 검증 항목 미등재');


\echo '━━━ 8.5 회귀 — NULL 의미론 함정 (빈 배열 / 없는 키) ━━━'
select t_reject($q$insert into public.readings (project_id,item,value_num,unit,source_sheets,status,derived)
  values ('aaaaaaaa-0000-0000-0000-000000000001','빈문자근거',1,'mm','{""}','confirmed',false)$q$,
  'source_sheets 에 빈 문자열 (근거처럼 보이는 공백)');
select t_reject($q$insert into public.ambiguities (project_id,item,question,sheet_refs,options,model_impact)
  values ('aaaaaaaa-0000-0000-0000-000000000001','x','q?','[{"sheet_no":"S-105"}]',
  '[{"label":"a","rationale":"r","model_impact":"m","recommended":true},
    {"label":"b","rationale":"r","model_impact":"m","recommended":false}]','mi')$q$,
  'bbox_px 키 자체가 없음');
select t_reject($q$insert into public.structural_members (project_id,code,structure,segment,member_type,member_index,zone)
  values ('aaaaaaaa-0000-0000-0000-000000000001','AB1_S5_DIA11','AB1','S5','DIA',11,'{"name":"z","count":3}')$q$,
  'zone 에 spacing_mm 키 없음');
select t_reject($q$insert into public.verifications (project_id,build_id,stage,performed_by,checks,overall)
  values ('aaaaaaaa-0000-0000-0000-000000000001','ffffffff-0000-0000-0000-000000000001','self_check','a',
  '[]','PASS')$q$, '검증 항목 배열이 빔');
select t_reject($q$insert into public.renders (project_id,build_id,kind,path,view_contract)
  values ('aaaaaaaa-0000-0000-0000-000000000001','ffffffff-0000-0000-0000-000000000001','context','vc.png',
  '{"unit":"m","origin":[0,0,0],"u_axis":[1,0,0],"v_axis":[0,1,0],"v_extent":10}')$q$,
  '뷰 계약에 u_extent 키 없음');
select t_reject($q$insert into public.renders (project_id,build_id,kind,path,view_contract)
  values ('aaaaaaaa-0000-0000-0000-000000000001','ffffffff-0000-0000-0000-000000000001','context','vc2.png',
  '{"unit":"m","origin":[0,0],"u_axis":[1,0,0],"v_axis":[0,1,0],"u_extent":10,"v_extent":10}')$q$,
  '뷰 계약 origin 이 2성분 (vec3 아님)');
select t_reject($q$insert into public.renders (project_id,build_id,kind,path,view_contract)
  values ('aaaaaaaa-0000-0000-0000-000000000001','ffffffff-0000-0000-0000-000000000001','context','vc3.png',
  '{"unit":"m","origin":[0,0,0],"u_axis":[1,0,0],"v_axis":[0,1,0],"u_extent":10,"v_extent":10,
    "roundtrip_check":{"sample_count":9,"max_error_m":0.5,"tolerance_m":1e-9,"result":"FAIL"}}')$q$,
  '왕복 검산 FAIL 인 뷰 계약');
select t_accept($q$insert into public.renders (project_id,build_id,kind,path,view_contract)
  values ('aaaaaaaa-0000-0000-0000-000000000001','ffffffff-0000-0000-0000-000000000001','context','vc4.png',
  '{"unit":"m","origin":[0,0,0],"u_axis":[1,0,0],"v_axis":[0,1,0],"u_extent":10,"v_extent":10,
    "roundtrip_check":{"sample_count":9,"max_error_m":0,"tolerance_m":1e-9,"result":"PASS"}}')$q$,
  '왕복 검산 PASS 인 정상 뷰 계약');

\echo '━━━ 9. RLS ━━━'
select '  owner 멤버십 자동 생성: ' || count(*)::text || ' (기대: 1)'
  from public.project_members
  where project_id='aaaaaaaa-0000-0000-0000-000000000001' and role='owner';

begin;
set local role authenticated;
set local request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
select '  비멤버가 보는 프로젝트 수: ' || count(*)::text || ' (기대: 0)' from public.projects;
select '  비멤버가 보는 판독 수: ' || count(*)::text || ' (기대: 0)' from public.readings;
select '  비멤버가 보는 시트 수: ' || count(*)::text || ' (기대: 0)' from public.sheets;
commit;

insert into public.project_members (project_id,user_id,role)
  values ('aaaaaaaa-0000-0000-0000-000000000001','22222222-2222-2222-2222-222222222222','viewer');

begin;
set local role authenticated;
set local request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
select '  viewer 가 보는 프로젝트 수: ' || count(*)::text || ' (기대: 1)' from public.projects;
select t_reject($q$insert into public.readings (project_id,item,value_num,unit,source_sheets,status,derived)
  values ('aaaaaaaa-0000-0000-0000-000000000001','viewer가쓴값',1,'mm','{S-105}','confirmed',false)$q$,
  'viewer 가 판독값 쓰기');
select t_reject($q$insert into public.decisions (project_id,ambiguity_id,choice_index,provisional,responder)
  values ('aaaaaaaa-0000-0000-0000-000000000001','dddddddd-0000-0000-0000-000000000001',0,false,'viewer')$q$,
  'viewer 가 질문 응답');
select t_zero_rows($q$delete from public.projects where id='aaaaaaaa-0000-0000-0000-000000000001'$q$,
  'viewer 의 프로젝트 삭제가 0행에 그침');
commit;

update public.project_members set role='reviewer'
  where project_id='aaaaaaaa-0000-0000-0000-000000000001' and user_id='22222222-2222-2222-2222-222222222222';

begin;
set local role authenticated;
set local request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
select t_accept($q$insert into public.decisions (project_id,ambiguity_id,choice_unknown,provisional,responder,responder_id)
  values ('aaaaaaaa-0000-0000-0000-000000000001','dddddddd-0000-0000-0000-000000000001',true,true,'reviewer',
  '22222222-2222-2222-2222-222222222222')$q$, 'reviewer 가 "모르겠다" 응답');
select t_reject($q$insert into public.readings (project_id,item,value_num,unit,source_sheets,status,derived)
  values ('aaaaaaaa-0000-0000-0000-000000000001','reviewer가쓴값',1,'mm','{S-105}','confirmed',false)$q$,
  'reviewer 가 판독값 쓰기');
select t_reject($q$insert into public.approvals (project_id,target_type,approver_id,approver,result,note)
  values ('aaaaaaaa-0000-0000-0000-000000000001','spec','11111111-1111-1111-1111-111111111111','남명의','rejected','x')$q$,
  '남의 명의로 승인');
select t_reject($q$insert into public.decisions (project_id,ambiguity_id,choice_index,provisional,responder,responder_id)
  values ('aaaaaaaa-0000-0000-0000-000000000001','dddddddd-0000-0000-0000-000000000001',0,false,'가장',
  '11111111-1111-1111-1111-111111111111')$q$, '남의 명의로 질문 응답');
select t_reject($q$delete from public.decisions where responder='reviewer'$q$, '결정 로그 삭제 (추가 전용)');
select t_reject($q$update public.decisions set note='조작' where responder='reviewer'$q$, '결정 로그 수정 (추가 전용)');
select t_reject($q$update public.verifications set overall='PASS' where overall='PASS'$q$, '검증 리포트 수정 (추가 전용)');
select t_reject($q$insert into public.readings (project_id,item,value_num,unit,source_sheets,status,derived)
  values ('aaaaaaaa-0000-0000-0000-000000000002','타프로젝트침입',1,'mm','{S-1}','confirmed',false)$q$,
  '멤버가 아닌 다른 프로젝트에 쓰기');
commit;

select '  → "모르겠다" 후 ambiguity.status = ' || status || ' (기대: provisional)'
  from public.ambiguities where id='dddddddd-0000-0000-0000-000000000001';

\echo '━━━ 10. Storage 경로 규약 ━━━'
select '  path_project_id 정상: ' ||
  coalesce(private.path_project_id('aaaaaaaa-0000-0000-0000-000000000001/source/abc.pdf')::text,'NULL');
select '  path_project_id 규약위반(uuid 아님): ' ||
  coalesce(private.path_project_id('drawings/abc.pdf')::text,'NULL (접근 거부)');
