# M5 설계 — 모델링 에이전트(격벽 1섹션): LLM 이 섹션 빌더 코드를 쓰고, 워커가 실행·검증·채점하고, 웹에서 시작·반복·승인 (아키텍처 [6]·[7])

작성 2026-09-06. 사용자 방향: **"이 프로젝트의 목적은 3D 를 만들어내는 게 아니라 3D 를 LLM 을 통해 만들 수 있는 웹앱을 만드는 것"**.
M3·M4 는 [6] 모델링을 결정론 코드로 대체한 채 레일(ModelSpec·섹션·3중 검증·Storage·검수 화면·승인)만 깔았다 — M5 부터 그 레일 위에서 LLM 이 실제로 만든다.
사용자 결정: 산출 형태 "섹션 빌더 코드 생성·실행", 입력 "ModelSpec + 규칙 + 툴킷 + 자기 섹션 도면 크롭(비전)", 실행 "웹 버튼 → 잡 큐 → 로컬 워커 데몬",
범위 "격벽(P4P5/DIA) 1섹션으로 M5 마감, API 상한 $5", 루프 "A1 생성 + 결정론 검증 루프(LLM 자기검토·다중 후보 없음)".

## 1. 목표와 합격 기준

웹에서 격벽 섹션의 "LLM 으로 만들기"를 누르면 로컬 워커가 잡을 집어 Sonnet 5 로 격벽 빌더 코드를 받아 샌드박스에서 실행하고,
섹션 self-check·정답 대조·**레고식 결합**(정답 9섹션 + 에이전트 격벽) 재실측으로 채점해, 결과를 에이전트 빌드로 올리고 화면에 띄운다.
사용자는 수정 요청을 보내 다시 만들게 하거나 승인한다.

| # | 기준 | 판정 |
|---|---|---|
| ① | 웹 "LLM 으로 만들기" → `jobs` 행 → `m3d worker` 가 집어 실행 → 에이전트 빌드(builds.kind='agent')가 빌드 목록에 나타나고 자동 선택된다. 잡 패널에 상태·시도·비용·로그가 2초 폴링으로 보인다 | 육안+DB |
| ② | 에이전트 격벽 섹션이 정답(결정론 `sections/P4P5/DIA.glb`)과 노드명 26 일치(only_ours=only_ref=[]), 노드별 bbox 최대 편차 ≤ 5 mm, 섹션 self-check(DIA 태그) fail 0; 결합 모델(정답 9 + 에이전트 격벽) self-check fail 0·독립 재실측 fail 0 | PASS/FAIL(채점 JSON) |
| ③ | 수정 요청 1회("…로 고쳐 줘")가 parent_job 을 잇는 새 잡으로 실행되고 이전 코드+요청이 프롬프트에 들어간다 | 육안+DB |
| ④ | M5 전체 누적 API 비용 ≤ $5, 모든 실호출이 `usage.jsonl`(stage `model-agent`)에 기록, 상한 도달 시 잡이 `failed(예산)` 로 마감 | 원장 |
| ⑤ | 익명 접근 거부(jobs insert 401), pytest·vitest·typecheck 전건 통과 | PASS |

②는 "LLM 이 도면 크롭과 규칙만 보고 정답과 같은 격벽을 만들었는가"의 채점이다. 4회 시도 안에 ②를 못 채우면 **실패로 정직하게 보고**하고(결과·코드·채점은 그대로 화면에), M5 는 루프·화면·원장이 동작했는지(①③④⑤)로 판정한다. 최종 판정은 사용자.

## 2. 결정 사항

| # | 결정 | 이유 |
|---|---|---|
| D1 | 에이전트 산출 = 파이썬 코드(구조화 출력 `{code, assumptions[], questions[]}`), 계약 `build_section(spec: dict, ctx) -> dict[str, trimesh.Trimesh]`. 노드명 `AB1_S5_DIA01~26`, 격벽 위치는 전역 체인(받침선 + n×간격)에서 유도(KB §2-18) | 사용자 결정(코드 생성). 노드명·체인 규칙은 채점·결합의 전제 |
| D2 | `ctx` 는 **본체(BOX) 기하만** 제공: `y_web_top(z)·y_web_bot(z)·h_box(z)·t_web(z)·x_web·z_p4·z_p5`, 색 `COL_STEEL`, 삽입 `INS`, 툴킷 `geom`(loft·extrude·rect·box_prism·mirror_poly·mirror_mesh·paint·zone_loft). 격벽 전용 도우미(`dia_z` 등)는 주지 않는다 | 격벽은 본체 안에 들어앉는 부재라 본체 프로파일은 주어진 조건이지만, 격벽의 위치·형상·개구·보강재는 LLM 이 규칙과 도면에서 스스로 낸다 |
| D3 | 입력 묶음: KB §1·§2·§5 규칙 발췌 + 툴킷 API 문서(함수 서명·의미) + ModelSpec 의 `coord`·`box`·`diaphragm`·`bearing.x`(필드마다 출처 ssot/default 표시) + 격벽 판독 근거 크롭(readings 항목 정규식 `다이아프램|격벽|DIAP|개구|문턱|잭업|수직보강` 의 basis 시트·mm_bbox 로 자동 크롭, 최대 6장, 컨텍스트 120 mm) + 해당 판독값 텍스트 + 이전 시도의 오류/채점 요약 + 수정 요청. `default` 출처 값은 "참조 차용 — 도면으로 확인할 것"으로 표시 | 사용자 결정(비전 포함). 크롭은 M2a 판독 근거를 재사용해 무과금으로 만든다 |
| D4 | 모델 `claude-sonnet-5`, `call_structured`(기존) 재사용, thinking 비활성(구조화 출력 규약), max_tokens 16,000. stage `model-agent`, extra `{job_id, attempt, section}` | M2a 검증된 호출 경로. 사고 활성은 M6 튜닝 후보 |
| D5 | 샌드박스: 코드는 AST 검사(허용 import: `math·numpy·trimesh·m3d.model.geom`; `open/exec/eval/__import__/subprocess/socket/os/sys` 금지) 후 별도 프로세스(`python -I -m m3d.agent.runner code.py spec.json out.glb`, 120 s 타임아웃, cwd=임시 디렉터리)에서 실행. 러너가 `ctx` 를 만들고 반환 dict 를 검증(이름 패턴·Trimesh·수밀·컬러)해 GLB 로 내보낸다 | LLM 코드 실행의 안전선. 러너는 워커 코드라 Builder 를 써서 ctx 를 만들되 에이전트 코드에는 노출하지 않는다 |
| D6 | 채점 `score.json`: `compare_glb`(에이전트 DIA vs 정답 DIA: only_ours/only_ref/bbox_dev_max/faces), 섹션 self-check(DIA), 결합 모델(정답 섹션 9 + 에이전트 DIA → assemble) self-check 전체 + `measure.run`. `pass = 노드 집합 동일 ∧ bbox_dev ≤ 0.005 ∧ 세 검사 fail 0`. 실패 항목은 다음 시도 프롬프트에 그대로 | 결정론 빌더가 정답지. 결합 채점이 "레고식 결합" 자체를 검증 |
| D7 | 루프: 시도 ≤ 4. 시도마다 (LLM → AST → 실행 → 채점) 이벤트 로그. pass 면 종료, 아니면 오류·채점을 피드백. 4회 후에도 실패면 마지막 시도를 결과로 올리고 잡 `done`(score.pass=false) — 화면에서 판단 | 예산·정직한 보고 |
| D8 | 예산: `.env` `MODEL_AGENT_BUDGET_USD`(기본 5). 매 호출 전 `usage.jsonl` 의 stage `model-agent` 누적 + 이번 호출 예상치가 상한을 넘으면 호출하지 않고 잡 `failed`(`result.reason='budget'`). 잡 행에 `cost_usd` 누적 | 사용자 상한 $5 |
| D9 | 에이전트 빌드 = 정답 빌드 디렉터리를 복제한 뒤 격벽만 교체: `model/agent/<job_id>/` 에 `sections/P4P5/*.glb`(9 복사 + DIA 에이전트), 결합본, `selfcheck*.json`, `build.json(kind='agent')`, `modelspec.json`, `renders/`(재렌더 4장+views), `measure.json`, `agent/{code.py, attempts.json, score.json, prompt.md}` → 기존 `publish-model` 경로로 업로드(`run_publish_model(cfg, dataset, *, out_dir=…, kind='agent', section_sources=…)` 로 일반화, 버킷 키 `<slug>/b<version>/…`). `build_sections.source='agent'` 로 격벽 표시. `builds.kind` 제약에 `'agent'` 추가 | M4 산출·검수 화면을 그대로 재사용. 정답 섹션과 나란히 비교 가능 |
| D10 | 잡 큐: 마이그레이션 0006 `jobs`·`job_events`(§4). 웹은 `jobs` insert(RLS: 본인) 후 2초 폴링. 워커 `m3d worker [--once] [--poll 2]` 는 DB URL 로 `for update skip locked` 로 잡을 집는다(RLS 우회 — 워커는 service 경로) | 아키텍처 "큐 기반 비동기", 서버 배포 없이 내 PC 데몬 |
| D11 | 시범→게이트→확산: M5 는 격벽 1섹션. 나머지 9섹션·Fable 검토·다중 후보·사고 활성은 M6 | 사용자 결정(상한 $5) |

## 3. 에이전트 계약 (worker `m3d/agent/`)

- `agent/context.py`: `section_bundle(cfg, dataset, section_code, *, spec, feedback, request, prev_code) -> {"system": str, "messages": [...], "images": [...], "digest": str}`.
  system = KB 발췌(`docs/모델링규칙_지식베이스_v0.md` §1·§2·§5 원문 중 좌표·노드명·전역 체인·수밀·삽입 규칙) + 툴킷 문서(`geom.py` 독스트링에서 생성) + `ctx` 목록 + 코드 계약 + 출력 형식.
  user = ModelSpec 발췌(JSON, 출처 표시) + 판독값 텍스트 + 크롭 이미지 블록 + (이전 시도: 코드·오류·채점 요약) + (수정 요청).
- `agent/schema.py`: `AgentOut(code: str, assumptions: list[str], questions: list[str])`, post_validate: `def build_section(` 포함, AST 화이트리스트 통과.
- `agent/sandbox.py`: `check_code(code) -> list[str]`(위반 목록), `run_code(code, spec, out_glb, timeout=120) -> RunResult(ok, node_names, meshes, stdout, stderr, traceback)`.
- `agent/runner.py`(서브프로세스 진입점): 인자 `code.py spec.json out.glb`; `ctx = BoxContext(Builder(spec))`(D2 목록만 노출), `exec` 제한 globals, `build_section` 호출, 반환 검증, `Builder.export` 로 GLB, 결과 JSON stdout.
- `agent/score.py`: `score_section(cfg, dataset, section_code, agent_glb, spec) -> dict` (D6), 정답 섹션은 `model/sections/<segment>/<CODE>.glb`, 결합은 `sections.assemble` 로.
- `agent/loop.py`: `run_job(cfg, dataset, job, emit) -> dict` — 시도 루프(D7)·예산(D8)·산출 디렉터리 구성(D9)·`publish.run_publish_model(dir=…)` 호출·결과 반환. `emit(level, message)` 로 `job_events` 기록.
- `agent/crops.py`: 판독 근거 → 크롭 PNG(`model/agent/crops/<CODE>/…png`, 기존 `reading.crops.mm_bbox_to_px/render_crop` 재사용, 컨텍스트 120 mm, 긴 변 ≤ 1,400 px).

## 4. 데이터 (마이그레이션 `0006_jobs.sql`)

```sql
create table jobs (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references projects(id) on delete cascade,
  kind          text not null check (kind in ('model-section')),
  section_key   text not null,                       -- 'P4P5/DIA'
  request       text not null default '',            -- 사용자 요청(수정 요청 포함)
  parent_job_id uuid references jobs(id) on delete set null,
  status        text not null default 'queued' check (status in ('queued','running','done','failed')),
  attempts      int  not null default 0,
  cost_usd      numeric(8,4) not null default 0,
  budget_usd    numeric(8,2) not null default 5,
  result        jsonb,                               -- {pass, score, build_version, reason, assumptions, questions}
  build_id      uuid references builds(id) on delete set null,
  user_id       uuid not null default auth.uid(),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create table job_events (
  id      bigserial primary key,
  job_id  uuid not null references jobs(id) on delete cascade,
  ts      timestamptz not null default now(),
  level   text not null check (level in ('info','warn','error')),
  message text not null
);
-- RLS: jobs select authenticated / insert authenticated with check (user_id = auth.uid()); job_events select authenticated.
-- 워커는 DB URL(psycopg)로 update/insert — RLS 비적용 경로. update/delete 정책 없음.
alter table builds drop constraint builds_kind_check;   -- pg 자동 명명 <표>_<열>_check (계획 단계에서 pg_constraint 로 확인)
alter table builds add constraint builds_kind_check check (kind in ('pilot','full','agent'));
alter table build_sections add column source text not null default 'builder' check (source in ('builder','agent'));
```
`contracts/db.types.ts` 에 `jobs`·`job_events` 추가, `builds.kind` 에 `'agent'`, `build_sections.source`. `db.TABLES` 에 두 표.

## 5. 워커 데몬 `m3d worker`

- `m3d worker [--once] [--poll 2.0]`: 큐에서 잡 1건 claim(`update jobs set status='running', updated_at=now() where id = (select id from jobs where status='queued' order by created_at limit 1 for update skip locked) returning …`) → `agent.loop.run_job` → `done/failed` + `result`·`build_id`·`cost_usd`·`attempts` 갱신. 예외는 `failed` + 이벤트 `error`. `--once` 는 잡 1건 처리 후 종료(테스트·실증용).
- 콘솔 한 줄 요약: `worker job=<id> section=P4P5/DIA attempts=N pass=true|false cost=$x.xx build=bN`.

## 6. 웹

- `lib/jobs.ts`: `createJob(client, {projectId, sectionKey, request, parentJobId})`, `fetchJobs(client, projectId)`, `fetchEvents(client, jobId)`, 순수 함수 `jobSummary(job)`(상태·시도·비용 문자열), `jobPayload(...)`(검증: request ≤ 2,000자).
- `routes/Model.tsx`: 격벽(=`source==='builder'` 인 섹션) 행에 "LLM 으로 만들기" 버튼 → 요청 입력 모달 → `createJob`. 우 패널 상단에 **잡 패널**(최근 잡 5건: 상태 배지·시도·비용·"로그 보기") — 2초 폴링(`queued/running` 이 있을 때만). 잡이 `done` 되면 빌드 목록 재조회 + 그 빌드 자동 선택.
- `VerifyPanel`: 에이전트 빌드(`kind==='agent'`)면 채점 요약(`stats.agent`: pass·노드 일치·bbox 편차·결합 재실측)과 `assumptions`·`questions` 목록, 코드 다운로드 링크(`agent/code.py`), "수정 요청" textarea + 버튼(→ `createJob(parentJobId=…)`). 섹션 행의 `source==='agent'` 는 "LLM" 배지.

## 7. 테스트·실증

- worker pytest: `test_agent_context.py`(번들 구성 — 규칙·툴킷·스펙 발췌·출처 표시·크롭 목록·피드백 삽입, 이미지는 가짜 PNG), `test_agent_sandbox.py`(AST 위반 검출 — `import os`·`open(`·`__import__`; 정상 코드 실행 → GLB·노드명; 타임아웃; 예외 traceback 수집), `test_agent_score.py`(정답 DIA 를 그대로 넣으면 pass, 노드 하나 빼면 only_ref 검출·pass false), `test_agent_loop.py`(가짜 LLM: 1차 실패 코드 → 2차 정답 코드 → attempts 2·pass; 예산 초과 → failed reason budget; 이벤트 순서), `test_worker.py`(claim SQL·상태 전이, 가짜 DB), `test_migration_0006.py`.
- web vitest: `jobs.test.ts`(jobSummary·jobPayload 검증).
- 실증(브라우저, 로그인): 격벽 "LLM 으로 만들기" → 터미널 `m3d worker --once` → 잡 패널 진행 → 에이전트 빌드 자동 선택 → 채점·assumptions 표시 → "수정 요청" 1회 → 두 번째 잡 → 승인. `usage.jsonl` stage `model-agent` 합계 ≤ $5. 익명 `POST /rest/v1/jobs` 401.
- 판정서 `data/derived/ab1-p4p5/model/acceptance-m5.md`: 시도별 비용·채점·프롬프트 크기, 정답 대조 결과, 실패했으면 실패 원인.

## 8. 명령 순서

`m3d modelspec → build → render → publish-model`(정답 빌드, M4) → 웹 `/p/ab1-p4p5/model` 에서 격벽 "LLM 으로 만들기" → 터미널 `m3d worker --once`(또는 데몬) → 웹에서 결과·수정 요청·승인.

## 9. 범위 밖

나머지 9섹션(M6), Fable 검토·다중 후보·사고 활성, 에이전트가 판독 자체를 고치는 것(질문은 `questions` 로만 표면화), 서버 배포, 정답 없는 구간(P5~P6)의 채점 방식.
