-- M1: sheet_text JSON 을 assets 로 등재하기 위해 kind 에 'text' 추가 (설계서 §7).
-- 0001 의 inline check 는 assets_kind_check 로 자동 명명되었다.

alter table assets drop constraint assets_kind_check;
alter table assets add constraint assets_kind_check
  check (kind in ('dxf','pdf','png','photo','text'));
