-- ============================================================================
-- model3d-studio — 04. Storage 버킷 + 정책
--
-- 버킷 분리 방침 — 4가지 축이 서로 다르기 때문에 하나로 합치지 않는다:
--   (1) 크기·MIME 한도   원본 CAD 200MB vs 크롭 PNG 10MB
--   (2) 수명주기         원본은 불변·콜드, 크롭/렌더는 핫·재생성 가능
--   (3) 재생성 가능성    sheet-images·crops·renders 는 파이프라인 재실행으로 복원되지만
--                        drawings·photos 는 소실 시 복구 불가 → 백업 등급이 다르다
--   (4) 공유 범위        렌더는 승인 게이트에서 서명 URL 로 외부 공유될 수 있고
--                        원본 도면은 절대 그러면 안 된다
--
-- 경로 규약 — **첫 세그먼트는 반드시 project_id(uuid)** 다. RLS 정책이 이 값만 보고
-- 소유 프로젝트를 판정하므로(private.path_project_id), 규약을 어기면 접근이 거부된다.
--
--   drawings      {project_id}/source/{sha256}.{ext}
--                 └ 내용 주소화. 같은 도면 재업로드 시 중복 저장을 피하고,
--                   sheets.source_path 가 이 경로를 가리킨다.
--   photos        {project_id}/photos/{photo_id}.{ext}
--   sheet-images  {project_id}/sheets/{sheet_id}/page.png
--                 {project_id}/sheets/{sheet_id}/text.txt        (sheet_text)
--   crops         {project_id}/ambiguities/{ambiguity_id}/{seq}.png
--                 └ 질문 카드 1장 = 크롭 1~2개(두 시트 대조). ambiguities.sheet_refs[].crop_path
--   models        {project_id}/builds/{build_id}/model.glb
--                 {project_id}/builds/{build_id}/builder.py
--   renders       {project_id}/builds/{build_id}/{kind}/{name}.png
--                 └ kind ∈ orthographic|context|interior_cut (renders.kind 와 동일 어휘)
--
-- 전 버킷 비공개(public=false). 웹은 서명 URL 로만 읽는다.
-- ============================================================================

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('drawings', 'drawings', false, 209715200,   -- 200 MB: 대형 PDF·DWG 세트
   array['application/pdf','application/acad','image/vnd.dwg','image/vnd.dxf',
         'application/dxf','application/zip','image/png','image/jpeg',
         'application/octet-stream']),
  ('photos', 'photos', false, 52428800,        -- 50 MB: 고해상 현장 사진
   array['image/jpeg','image/png','image/heic','image/webp']),
  ('sheet-images', 'sheet-images', false, 104857600,  -- 100 MB: 고해상 시트 PNG
   array['image/png','image/jpeg','image/webp','text/plain']),
  ('crops', 'crops', false, 10485760,          -- 10 MB: 질문 카드 크롭
   array['image/png','image/jpeg','image/webp']),
  ('models', 'models', false, 524288000,       -- 500 MB: GLB + 빌더 코드
   array['model/gltf-binary','model/gltf+json','application/octet-stream','text/x-python']),
  ('renders', 'renders', false, 26214400,      -- 25 MB: 정사영·맥락·내부컷 렌더
   array['image/png','image/jpeg','image/webp','application/pdf'])
on conflict (id) do update
set file_size_limit    = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types,
    public             = excluded.public;

-- ── storage.objects 정책 ────────────────────────────────────────────────────
-- 주의: storage.objects 는 supabase_storage_admin 소유다. `supabase db push` 는
-- postgres 로 실행되며 정책 생성 권한이 있다. 권한 오류가 나면 대시보드에서 실행한다.

drop policy if exists m3d_objects_select on storage.objects;
drop policy if exists m3d_objects_insert on storage.objects;
drop policy if exists m3d_objects_update on storage.objects;
drop policy if exists m3d_objects_delete on storage.objects;

-- 읽기: 프로젝트 멤버 전원
create policy m3d_objects_select on storage.objects
  for select to authenticated
  using (
    bucket_id in ('drawings','photos','sheet-images','crops','models','renders')
    and private.path_project_id(name) in (select private.member_project_ids())
  );

-- 쓰기: editor 이상
create policy m3d_objects_insert on storage.objects
  for insert to authenticated
  with check (
    bucket_id in ('drawings','photos','sheet-images','crops','models','renders')
    and private.path_project_id(name) in (select private.editor_project_ids())
  );

-- 덮어쓰기: 원본(drawings·photos)은 불변으로 둔다 — 재업로드는 새 경로로.
create policy m3d_objects_update on storage.objects
  for update to authenticated
  using (
    bucket_id in ('sheet-images','crops','models','renders')
    and private.path_project_id(name) in (select private.editor_project_ids())
  )
  with check (
    bucket_id in ('sheet-images','crops','models','renders')
    and private.path_project_id(name) in (select private.editor_project_ids())
  );

-- 삭제: 파생물은 editor, 원본은 owner 만 (소실 시 복구 불가)
create policy m3d_objects_delete on storage.objects
  for delete to authenticated
  using (
    case
      when bucket_id in ('sheet-images','crops','models','renders')
        then private.path_project_id(name) in (select private.editor_project_ids())
      when bucket_id in ('drawings','photos')
        then private.path_project_id(name) in (select private.owner_project_ids())
      else false
    end
  );
