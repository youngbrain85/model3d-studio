# M2b 설계 — 질문 카드 UI · decisions · SSOT 문서 (아키텍처 [5] 질문 루프)

작성 2026-09-05. 사용자 승인: 범위 "카드 + 결정 저장 + SSOT 문서", 사용 환경 "나 혼자, 내 PC", 접근 A.
선행: M2a(판독·크롭, main 병합 ecfb877) — DB 에 readings 282·ambiguities 63(크롭 63/63)이 있다.

## 1. 목표와 합격 기준

M2a 가 만든 애매성(ambiguity) 63건을 **한 질문 = 한 요소** 카드로 보여 주고(지식베이스 §4),
사용자의 결정을 이력으로 저장하며, 판독값·결정을 합친 **치수 정본(실측정리) 문서**를 생성한다
(지식베이스 §2·§7). M3 빌더는 이 문서(JSON)를 입력으로 쓴다.

합격 기준(전부 실측·화면 캡처 대조):
1. 로그인 후 `/p/ab1-p4p5/questions` 에 63장 카드가 뜨고, 각 카드에 Storage 의 크롭 이미지·선택지(권장안 첫 번째, 각 근거)·모델 영향·"모르겠다" 선택지가 보인다.
2. 결정 버튼 → `decisions` 행 1건 삽입 → `ambiguities.status` 가 `결정`(또는 "모르겠다" 면 `잠정`) 으로 바뀐다. 같은 카드를 다시 답하면 새 행이 추가되고 화면은 최신 행을 보여 준다.
3. `m3d ssot ab1-p4p5` 가 `실측정리_v1.md` + `ssot.json` 을 만들고, 결정 2건 이상이 결정/잠정 절에 나타난다. 내용이 같으면 재실행해도 새 버전이 생기지 않는다.
4. 익명(로그인 전) 요청은 ambiguities·decisions·Storage 읽기/쓰기 모두 거부된다(RLS 실증).
5. 재판독·재검토(`replace_region` 경유)에도 결정이 달린 ambiguity 는 id·내용이 보존된다(pytest + `review --region B --cache-only` 실DB 1회 실증, $0).
6. `pytest` 전건 통과 + `npm run typecheck` + vitest 통과. 브라우저 E2E 스크린샷 3장 이상(카드·결정 후·SSOT 절).

## 2. 결정 사항

| # | 결정 | 이유 |
|---|---|---|
| D1 | 서버 코드 없음. 웹은 supabase-js 로 RLS 아래 읽기·쓰기, 상태 갱신은 DB 트리거, 업로드·SSOT 는 `m3d` CLI | 혼자 쓰는 v0. 기존 스택 그대로 |
| D2 | `decisions` 는 **추가 전용 이력** — 재답변은 새 행, 최신 행이 현재 결정 | 지식베이스 §2 "정정 이력을 남긴다" |
| D3 | 결정이 달린 ambiguity 는 재판독(`replace_region`)에서 **삭제·덮어쓰기 금지(보존)** | M2a 최종 검토가 지적한 FK 충돌 해소. 사용자 답변은 재판독보다 우선 |
| D4 | 결정은 판독값(readings)을 자동으로 고치지 않는다 — SSOT 문서의 "결정" 절로 병기 | 선택안→치수 반영은 의미 해석이 필요. M3 빌더가 결정 목록을 읽어 적용 |
| D5 | 인증: Supabase 이메일/비밀번호 1계정(대시보드에서 1회 생성). 로그인 화면은 참조 앱 AuthGate·LoginScreen 패턴 이식 | RLS `authenticated` 정책을 그대로 씀 |
| D6 | 크롭은 비공개 Storage 버킷 `crops` 에 CLI 가 업로드, 웹은 서명 URL(1시간)로 표시 | 도면은 고객 자료 — 공개 버킷 금지 |
| D7 | "모르겠다 — 권장대로 진행, 나중에 확인" 은 항상 표시되는 고정 선택지: `choice_index=0`(권장안) + `provisional=true` → 상태 `잠정` | 지식베이스 §4 |
| D8 | SSOT 는 파일(`data/derived/<dataset>/ssot/`)로만, 내용 해시가 바뀔 때만 버전 증가 | M3 입력. DB 테이블은 YAGNI |

## 3. 데이터 모델 — `supabase/migrations/0004_decisions.sql`

```sql
-- decisions: 질문 응답 이력 (아키텍처 §4). 추가 전용 — update/delete 정책 없음.
create table decisions (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references projects(id) on delete cascade,
  ambiguity_id  uuid not null references ambiguities(id) on delete restrict,
  choice_index  int  not null check (choice_index >= 0),      -- options[] 인덱스
  choice_label  text not null,                                 -- 선택 당시 label 스냅샷
  provisional   boolean not null default false,               -- "모르겠다" → true
  note          text not null default '',
  decided_by    uuid not null default auth.uid(),
  decided_at    timestamptz not null default now()
);
create index on decisions (ambiguity_id, decided_at desc);
alter table decisions enable row level security;
create policy "authenticated read"   on decisions for select to authenticated using (true);
create policy "authenticated insert" on decisions for insert to authenticated
  with check (decided_by = auth.uid());

-- 삽입 트리거: 선택지 범위 검증 + ambiguities.status 갱신 (security definer — authenticated 에 update 정책 없음)
create function apply_decision() returns trigger
language plpgsql security definer set search_path = public as $$
declare n int;
begin
  select jsonb_array_length(options) into n from ambiguities where id = new.ambiguity_id;
  if n is null then raise exception 'ambiguity 없음: %', new.ambiguity_id; end if;
  if new.choice_index >= n then raise exception 'choice_index % 범위 밖 (선택지 %개)', new.choice_index, n; end if;
  update ambiguities set status = case when new.provisional then '잠정' else '결정' end
   where id = new.ambiguity_id;
  return new;
end $$;
create trigger decisions_apply after insert on decisions
  for each row execute function apply_decision();

-- Storage: 비공개 버킷 + 로그인 사용자 읽기 (서명 URL 발급에 필요)
insert into storage.buckets (id, name, public) values ('crops', 'crops', false)
  on conflict (id) do nothing;
create policy "authenticated read crops" on storage.objects
  for select to authenticated using (bucket_id = 'crops');
```

- `contracts/db.types.ts` 에 `decisions` Row/Insert 를 수기 추가(README 규약: SQL 이 정본).
- `assets.storage_path`(M0 스키마)에 업로드 경로 `crops/<slug>/<ambiguity_id>.png` 를 채운다.
- 현재 결정 = `ambiguity_id` 별 `decided_at desc` 첫 행. 웹은 프로젝트의 decisions 전체(수십 건)를 받아 클라이언트에서 축약한다.

## 4. worker CLI

### 4-1. `m3d publish <dataset> [--force]` — 크롭 업로드
- 대상: `ambiguities.crop_rel_path is not null` 인 행. 경로 `crops/<project.slug>/<ambiguity_id>.png` (버킷 `crops`, 오브젝트 키 `<slug>/<id>.png`).
- 스킵 규칙: `assets.storage_path` 가 채워져 있고 `assets.sha256 == sha256(파일)` 이면 스킵(`--force` 시 재업로드). 파일 없음 → 실패 집계.
- 전송: `httpx` 로 `POST {SUPABASE_URL}/storage/v1/object/crops/<slug>/<id>.png`, 헤더 `Authorization: Bearer <service_key>`, `apikey: <service_key>`, `x-upsert: true`, `content-type: image/png`. 성공 시 `assets.storage_path` update(한 트랜잭션).
- 출력: `uploaded=N skipped=N failures=N total=N`(ASCII 한 줄 + 한글 요약), 실패 있으면 exit 1. service key 는 로그·출력에 절대 나오지 않는다.
- 테스트: 가짜 `httpx.Client`(요청 기록) + 가짜 커서 — 업로드 헤더·경로·skip 규칙·실패 집계·storage_path update SQL.

### 4-2. `m3d ssot <dataset>` — 치수 정본 문서
- 입력(DB 읽기): projects(coord_system, coord_assumptions), readings(전건, sheets.ord·page_no 조인), ambiguities(전건, 최신 decision 조인).
- 출력: `data/derived/<dataset>/ssot/실측정리_v<N>.md`, `ssot.json`(같은 내용, M3 입력), `index.json`(`[{version, sha256, generated_at, counts}]`).
- 버전 규칙: 문서 본문(생성 시각 제외)의 sha256 이 `index.json` 마지막과 같으면 "변경 없음" 출력·파일 미생성; 다르면 N+1.
- 마크다운 절 순서: 0 좌표계·가정 / 1 확정(계열별 표: 항목·값·단위·근거 ord/p·검산 요약) / 2 추정 / 3 검토지적 / 4 결정(항목·근거 ord/p·선택안 label·근거·모델 영향·결정/잠정·메모·시각) / 5 미결(대기 애매성: 항목·선택지·모델 영향) / 6 통계. 모든 수치에 근거 도면(ord·page)을 병기한다(지식베이스 §2).
- `ssot.json` 스키마: `{version, generated_at, project:{slug,name,coord_system,coord_assumptions}, readings:[{region,ord,page_no,item,value_raw,unit,status,mm_bbox,crosscheck}], decisions:[{ambiguity_id,ord,page_no,item,choice_index,choice_label,basis,provisional,model_impact,note,decided_at}], open:[{ambiguity_id,ord,page_no,item,options,model_impact}]}`.
- 테스트: 가짜 커서로 고정 데이터 → 마크다운 절·표 행 수·JSON 키·버전 증가/불변 규칙.

### 4-3. 기존 명령 변경
- `store.replace_region`: 삭제 전 `select ambiguity_id from decisions where project_id=%s` 로 **보호 집합**을 만들고, 그 id 는 삭제·재삽입 대상에서 제외(기존 행 그대로). 반환 dict 에 `protected` 추가, CLI 출력에 `보호 n`. 테스트: 보호 행은 delete SQL 파라미터에 없고 새 결과의 같은 자연키 행도 삽입되지 않는다.
- `db check`: `decisions=<n> provisional=<m> published=<storage_path 채워진 수>/<crop 수>` 한 줄 추가.
- `crops`: 보호 행의 크롭은 그대로(고아 스윕 대상 아님 — ambiguity 가 남으므로 자연히 제외).

## 5. 웹 (React 18 · Vite · Mantine 8 · supabase-js · react-router-dom 6)

```
web/src/
  main.tsx            MantineProvider + BrowserRouter
  App.tsx             routes: /login, /, /p/:slug/questions, /health
  auth/AuthGate.tsx   세션 없으면 LoginScreen (참조 앱 이식, useSession 훅)
  auth/LoginScreen.tsx 이메일/비밀번호 signInWithPassword, 오류 표시
  routes/Projects.tsx  projects 목록 → /p/<slug>/questions 링크
  routes/Questions.tsx 좌: 목록(계열·상태 필터, 배지) / 우: QuestionCard
  components/QuestionCard.tsx  카드 본문(아래)
  lib/questions.ts    fetchQuestions(slug) → {ambiguities+sheet ord/page, latestDecision} / submitDecision() / cropUrl()
  lib/decisions.ts    순수 로직: 최신 결정 축약, 선택지 정렬(권장안 첫 번째 = options[0]), "모르겠다" 페이로드 → vitest 대상
```

- QuestionCard: 항목명, `ord p<page>` 배지, 크롭(`storage.from('crops').createSignedUrl('<slug>/<id>.png', 3600)`, 클릭 시 Modal 확대), 선택지 Radio 그룹(`options[i].label` + 근거 소문자 텍스트), 고정 항목 "모르겠다 — 권장대로 진행, 나중에 확인", 모델 영향 문단, 메모 Textarea, `결정` 버튼(선택 전 비활성), 현재 결정 배지(결정/잠정 + 시각) 와 이력 접기. 키보드: `1`~`4` 선택, `0` 모르겠다, `Enter` 결정, `←/→` 이전/다음.
- 데이터 접근: `ambiguities` select `id,item,options,model_impact,status,mm_bbox,sheet_page_id,basis_sheet_id,sheets(ord),sheet_pages(page_no)` where project_id; `decisions` select where project_id order by decided_at desc. 삽입: `{project_id, ambiguity_id, choice_index, choice_label, provisional, note}` (`decided_by` 는 DB 기본값).
- 에러: 서명 URL 실패 시 "이미지 없음 — `m3d publish` 실행" 안내, 삽입 실패(트리거 예외 포함)는 카드 상단 Alert.
- 스타일은 Mantine 기본 + 최소 커스텀. 반응형은 데스크톱 우선(혼자 PC).

## 6. 테스트·검증 계획

- worker pytest: publish(4)·ssot(6)·replace_region 보호(2)·db check(1) — 전부 가짜 HTTP/커서, 실DB·실호출 없음.
- web: `npm run typecheck`; vitest + jsdom 로 `lib/decisions.ts` 순수 로직 4건(최신 축약·정렬·모르겠다 페이로드·범위 검증). 컴포넌트 렌더 테스트는 두지 않는다(브라우저 E2E 로 대체).
- 실증 순서: `db apply`(0004) → `publish ab1-p4p5`(63장 업로드) → 대시보드에서 계정 생성(사용자) → `npm run dev` → Claude 브라우저 패널로 로그인·카드·결정 2건(1건은 모르겠다)·재답변 → DB 조회로 decisions 3행·status 확인 → `ssot ab1-p4p5` → 재실행 "변경 없음" → 익명 curl 로 RLS 거부 확인 → `review ab1-p4p5 --region B --cache-only` 로 보호 실증(캐시 히트, `replace_region` 이 결정 행을 건너뛰는지 DB 대조, $0).
- 과금: 이 마일스톤은 LLM 호출이 없다(`--force` 와 `--cache-only` 는 상충하므로 재판독 실증은 `review --cache-only` 로만).

## 7. 범위 밖 (백로그)
다중 사용자·초대·프로젝트 권한, 결정의 판독값 자동 반영, 두 시트 대조 크롭, 부재·커버리지 맵, Q4 계열 간 상충 결정론 후처리, 비밀번호 재설정 UI, Storage 이관(원본 DXF·PNG).
