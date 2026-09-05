-- 0004_decisions — 질문 응답 이력 + 상태 갱신 트리거 + 크롭 Storage (M2b 설계서 §3)
-- decisions 는 추가 전용 이력이다: 재답변은 새 행, 최신 행이 현재 결정 (지식베이스 §2 정정 이력).

create table decisions (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references projects(id) on delete cascade,
  ambiguity_id  uuid not null references ambiguities(id) on delete restrict,
  choice_index  int  not null check (choice_index >= 0),      -- options[] 인덱스
  choice_label  text not null,                                 -- 선택 당시 label 스냅샷
  provisional   boolean not null default false,               -- "모르겠다" → true → 잠정
  note          text not null default '',
  decided_by    uuid not null default auth.uid(),
  decided_at    timestamptz not null default now()
);
create index on decisions (ambiguity_id, decided_at desc);

alter table decisions enable row level security;
create policy "authenticated read"   on decisions for select to authenticated using (true);
create policy "authenticated insert" on decisions for insert to authenticated
  with check (decided_by = auth.uid());

-- 삽입 트리거: 선택지 범위 검증 + ambiguities.status 갱신
-- (security definer — authenticated 에는 ambiguities update 정책이 없다)
create function apply_decision() returns trigger
language plpgsql security definer set search_path = public as $$
declare n int;
begin
  select jsonb_array_length(options) into n from ambiguities where id = new.ambiguity_id;
  if n is null then
    raise exception 'ambiguity 없음: %', new.ambiguity_id;
  end if;
  if new.choice_index >= n then
    raise exception 'choice_index % 범위 밖 (선택지 %개)', new.choice_index, n;
  end if;
  update ambiguities
     set status = case when new.provisional then '잠정' else '결정' end
   where id = new.ambiguity_id;
  return new;
end $$;
create trigger decisions_apply after insert on decisions
  for each row execute function apply_decision();

-- Storage: 비공개 버킷 + 로그인 사용자 읽기 (서명 URL 발급에 필요). 업로드는 service key(CLI)만.
insert into storage.buckets (id, name, public) values ('crops', 'crops', false)
  on conflict (id) do nothing;
create policy "authenticated read crops" on storage.objects
  for select to authenticated using (bucket_id = 'crops');
