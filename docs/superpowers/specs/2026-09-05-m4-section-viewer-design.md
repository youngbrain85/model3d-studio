# M4 설계 — 섹션 단위 산출·검수·레고식 결합: 섹션 GLB · Storage 산출 · 웹 3D 검수 화면 · 승인 게이트 (아키텍처 [8] + [7] 게이트)

작성 2026-09-05. 사용자 결정: 다음 마일스톤 = "산출·웹 3D 뷰어 [8]", 검수 범위 "내부 검수 가능", 뷰어 스택 "three.js 직접",
섹션 단위 "구간 × 부재그룹 2단". 사용자 방향: **섹션 하나하나를 따로 모델링해 화면에 띄우고, 완성된 것들을 레고식으로 결합**한다.
선행: M3(`m3d modelspec → build → measure → render → compare-model`, 515 메시, 3중 검증 통과). 비용 원칙: LLM 호출 0, 구독 세션에서 직접 구현.

## 1. 목표와 합격 기준

P4~P5 정밀 모델을 **섹션(구간/부재그룹) 단위 GLB** 로 나눠 만들고, 섹션과 결합본·렌더·검증 JSON 을 Storage 에 올려, 웹 검수 화면에서
섹션을 따로 띄워 내부까지 살펴보고 **승인/반려를 기록**한다. 결합본은 섹션들을 좌표 변환 없이 합친 것이며 기존 통짜 빌드와 노드 단위로 동일해야 한다.

| # | 기준 | 판정 |
|---|---|---|
| ① | `m3d build` 가 섹션 GLB 10개(`P4P5/BOX…BRG`)와 결합본을 쓰고, 결합본 노드 집합·면 수 = 섹션 합 = 기존 통짜 빌드(`compare_glb` bbox 편차 0) | PASS/FAIL |
| ② | 섹션별 self-check 전건 PASS(그룹 태그 기준), 결합본 재실측·참조대조는 M3 결과 불변(47/0/2, 836/0) | PASS/FAIL |
| ③ | `m3d publish-model` 이 파일 전건(섹션 GLB 10 + 결합본 1 + 렌더 PNG 4 + views.json + JSON 6: build·selfcheck·selfcheck_sections·modelspec·measure·compare)을 버킷 `models` 에 올리고 `builds`·`build_sections` 행을 만들며, 재실행은 skip(버전 불변), `--force` 재업로드 | PASS/FAIL |
| ④ | 웹 `/p/<slug>/model`: 로그인 후 섹션 트리·단독 보기·표시 토글·클릭 노드명·단면 클리핑·뷰 프리셋·검증 패널·렌더·다운로드가 동작하고 승인/반려가 `approvals` 행 + status 갱신으로 남는다 — 브라우저 패널 스크린샷 대조 | 육안+DB |
| ⑤ | 익명 접근 거부: `models` 오브젝트 400/403, `approvals` insert 401 | PASS/FAIL |
| ⑥ | pytest·vitest·typecheck 전건 통과, LLM 호출 0 | PASS |

## 2. 결정 사항

| # | 결정 | 이유 |
|---|---|---|
| D1 | 섹션 키 = `<구간>/<부재그룹>` (예 `P4P5/DIA`). 구간은 `ModelSpec.coord.segment`(기본 `P4P5`, `default:SPEC_v2 §0`), 부재그룹은 빌더 §1~§10 의 10개 코드 `BOX·DIA·FRM·RIB·HST·WG·CS·SLAB·SP04·BRG`. 노드→그룹은 노드명 정규식 `AB1_S5_(BOX|DIA|FRM|RIB|HST|WG|CS|SLAB|BARRIER|SP04|BRG)` (BARRIER 는 SLAB 그룹) | 노드명이 이미 그룹을 담고 있어 빌더 기하는 손대지 않는다(지식베이스 §5 노드명 = 연결 키). 구간 키는 P5~P6 등 확산 때 그대로 쓴다 |
| D2 | 결합 = 섹션 GLB 를 같은 좌표계에 그대로 합치기(변환 없음). `m3d build` 가 섹션과 결합본을 동시에 쓰고, `assemble(sections) == monolithic` 을 테스트로 고정. 웹 뷰어의 결합도 같은 원리(섹션별 로드 → 한 씬) | 전 부재가 전역 체인(받침선 + n×간격) 좌표에 놓여 있어 레고식 결합이 자연스럽다(KB §2-18) |
| D3 | self-check 항목에 `group` 태그를 붙여 섹션별 판정(`selfcheck.run(..., section=)`): BOX 계획고·bbox·내공 H 8점 / DIA 26·z 체인 / FRM 150 / WG 52 / CS 52 / BRG 16·받침 하면 y / 공통 메시 수·수밀·컬러(섹션 범위). 결합본 self-check 는 기존 그대로 | 섹션 승인에 그 섹션의 증적이 필요하다(KB §6-1) |
| D4 | 산출 디렉터리: 전 부재 `model/`, 시범 `model/pilot/` — 같은 파일명(`AB1_P4P5.glb`, `sections/…`, `selfcheck.json`, `renders/`). 기존 `_pilot` 접미 파일은 폐기(README 갱신) | 시범·전체가 같은 코드 경로를 타고, publish 가 디렉터리 하나를 통째로 올린다 |
| D5 | DB 3표: `builds`, `build_sections`, `approvals`(append-only, decisions 와 같은 패턴 + 트리거로 status 갱신). 아키텍처 §4 초안의 `verifications`·`renders`·`members` 표는 만들지 않고 `builds.stats`(jsonb) + Storage 경로로 대신한다 | YAGNI. 파일이 Storage 에 있고 집계만 DB 에 있으면 화면·다운로드에 충분 |
| D6 | Storage 비공개 버킷 `models`, 키 `<slug>/b<version>/…`. 업로드는 service key(CLI)만, 웹은 로그인 세션 서명 URL(`createSignedUrls` 일괄). `crops` 와 같은 정책 | M2b 에서 검증된 패턴 재사용 |
| D7 | 버전: `builds.version` 은 프로젝트별 1부터 증가(종류 무관 최대 버전 + 1). 내용 해시 = sha256(결합본 GLB sha256 ‖ modelspec.json sha256). 같은 해시의 빌드가 종류·버전 무관 하나라도 있으면 skip(그 버전 보고), `--force` 면 같은 내용이라도 새 버전 | `m3d ssot` 의 "내용이 바뀔 때만 버전 증가" 와 같은 규칙. 시범/전체가 번갈아 올라가도 중복 버전이 생기지 않아야 한다(실증 중 발견해 정정) |
| D8 | 뷰어는 three.js 0.184 직접(GLTFLoader·OrbitControls·Raycaster·클리핑 평면). React 는 캔버스 컨테이너·패널만. BVH·meshopt 불사용(30k 삼각형) | 참조 web-app-v2 에서 검증된 조합, 의존성 1개 |
| D9 | 렌더 뷰 계약 `renders/views.json`(렌더별 origin·u/v 축·extent·eye·up) 을 render.py 가 함께 쓴다. 2D 연동 자체는 범위 밖 | KB §7 "뷰 계약을 함께 산출" — 몇 줄로 끝나고 나중 연동의 전제 |
| D10 | 시범→게이트→확산: 워커(섹션·publish) → 웹 최소 뷰어(섹션 트리 + 캔버스 로드) 시점에 사용자 확인 게이트 → 클리핑·피킹·검증 패널·승인 | KB §5 |

## 3. 섹션 모델 (worker)

- `model/sections.py`: `GROUPS = [("BOX","본체"),("DIA","격벽"),("FRM","개방 프레임"),("RIB","종리브"),("HST","수평보강재"),("WG","외측가로보"),("CS","외측빔"),("SLAB","슬래브·방호벽"),("SP04","이음판"),("BRG","받침")]`,
  `group_of(node_name) -> code`, `split(named) -> dict[section_key, dict[name, mesh]]`, `assemble(sections) -> dict[name, mesh]`(이름 중복 assert),
  `section_key(segment, code)`.
- `Builder.export_sections(named, out_dir)` → `sections/<segment>/<CODE>.glb` 10개 + `AB1_P4P5.glb`(결합본, 기존 `export`). 빌드 결과 요약 `build.json`
  `{segment, sections:[{key, code, label, meshes, triangles, bytes, sha256, selfcheck:{pass,fail}}], assembled:{meshes, triangles, sha256}, kind}`.
- `selfcheck.run(named, b, *, pilot, section=None)`: 각 check 에 `group` 필드(`BOX|DIA|FRM|WG|CS|BRG|ALL`). `section=` 이면 그 그룹 + ALL(메시 수 범위는 섹션 크기로) 만 실행하고 `named` 도 그 섹션만 받는다.
- `m3d build <ds> [--pilot]` 출력: `model/` 또는 `model/pilot/` 아래 `sections/…`, `AB1_P4P5.glb`, `selfcheck.json`(결합본), `selfcheck_sections.json`, `build.json`. 콘솔 `sections=10 assembled=515 selfcheck pass= fail=`.
  `render --pilot` 은 `model/pilot/` 을 읽는다; `measure`·`compare-model` 은 전체(`model/`) 전용이라 `--pilot` 이 없다.
- `ModelSpec.coord.segment` 필드가 추가되므로 계획에 `m3d modelspec` 재생성 단계를 넣는다(저장 JSON 드리프트 — M3 판정 메모 1).

## 4. 데이터 모델 (마이그레이션 `0005_builds.sql`)

```sql
create table builds (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null references projects(id) on delete cascade,
  version        int  not null,                       -- 프로젝트별 1,2,3…
  kind           text not null check (kind in ('pilot','full')),
  segment        text not null,                       -- 'P4P5'
  content_sha256 text not null,                       -- D7
  glb_path       text not null,                       -- models/<slug>/b<v>/AB1_P4P5.glb
  files          jsonb not null,                      -- {renders:[…], json:[…], views:'…'} Storage 키
  stats          jsonb not null,                      -- {meshes, triangles, selfcheck:{pass,fail}, measure:{pass,fail,info}, compare:{match,mismatch,na}}
  status         text not null default '대기' check (status in ('대기','승인','반려')),
  git_sha        text,
  created_at     timestamptz not null default now(),
  unique (project_id, version)
);
create table build_sections (
  id          uuid primary key default gen_random_uuid(),
  build_id    uuid not null references builds(id) on delete cascade,
  section_key text not null,                          -- 'P4P5/DIA'
  code        text not null, label text not null,
  glb_path    text not null, bytes int not null, sha256 text not null,
  meshes      int not null, triangles int not null,
  selfcheck   jsonb not null,                         -- {pass, fail, checks:[{label, ok, detail}]}
  status      text not null default '대기' check (status in ('대기','승인','반려')),
  unique (build_id, section_key)
);
create table approvals (                              -- append-only 이력 (decisions 패턴)
  id          uuid primary key default gen_random_uuid(),
  project_id  uuid not null references projects(id) on delete cascade,
  build_id    uuid not null references builds(id) on delete cascade,
  section_id  uuid references build_sections(id) on delete cascade,   -- null = 결합본 전체
  user_id     uuid not null default auth.uid(),
  verdict     text not null check (verdict in ('승인','반려')),
  note        text not null default '',
  created_at  timestamptz not null default now()
);
-- RLS: 세 표 authenticated select; approvals insert 는 user_id = auth.uid() 인 행만. 트리거 apply_approval()(security definer):
--   section_id 가 있으면 build_sections.status, 없으면 builds.status 를 verdict 로.
-- Storage: bucket 'models'(비공개) + "authenticated read models" select 정책.
```

`contracts/db.types.ts` 에 세 표 추가. `db.TABLES` 에 세 표 추가, `db check` 에 `builds`·`build_sections`·`approvals` 건수.

## 5. 산출·업로드 (`m3d publish-model <ds> [--pilot] [--force]`)

1. 디렉터리(`model/` 또는 `model/pilot/`)에서 `build.json`·결합본·섹션 GLB·`selfcheck.json`·`selfcheck_sections.json`·`modelspec.json`(전체 빌드 때 복사)·`renders/*.png`·`renders/views.json` 필수, `measure.json`·`compare.json` 은 있으면 포함(pilot 은 없음).
2. 내용 해시(D7) 계산 → 최신 `builds` 행과 같고 `--force` 아니면 `skipped` 로 종료.
3. version = max+1. 모든 파일을 `models/<slug>/b<version>/<상대경로>` 로 업로드(x-upsert, 표준 라이브러리 HTTP, `publish.py` 의 `_upload` 재사용). 실패 파일이 하나라도 있으면 DB 행을 만들지 않고 실패 목록 출력(exit 1).
4. 업로드 전건 성공 후 한 트랜잭션으로 `builds` + `build_sections` insert. 콘솔 `publish-model version=N files=M skipped=…`.
- 오브젝트 키 규칙은 워커 `model/publish.py::object_key(slug, version, rel)` 와 웹 `lib/models.ts::modelObjectKey` 가 같은 문자열을 내야 한다(양쪽 테스트).

## 6. 웹 검수 화면 `/p/:slug/model`

- 라우트·링크: `App.tsx` 에 `p/:slug/model`, `Projects.tsx` 카드에 "3D 검수 열기 →". 의존성 `three@^0.184`, `@types/three`.
- `lib/models.ts`: `fetchBuilds(client, project)`, `fetchSections(client, buildId)`, `signedUrls(client, keys)`(일괄), `fetchApprovals(client, buildId)`, `submitApproval(client, payload)`, `modelObjectKey`, 순수 함수 `latestApprovals(rows)`(대상별 최신 1건)·`approvalPayload(...)`(검증) (vitest).
- `lib/viewer/scene.ts`(three 전용, React 무관): `createViewer(canvas) -> {loadSection(key, url), setVisible(key, on), solo(key|null), setClip({axis, value, enabled}), preset('side'|'front'|'bottom'|'iso'), onPick(cb), dispose()}`.
  GLTFLoader 결과 메시에 `userData.section`·`userData.node`; 재질 `vertexColors` 유지·`DoubleSide`·`clippingPlanes`; `renderer.localClippingEnabled`. 피킹은 Raycaster(pointerdown). 카메라 프리셋은 전체 bbox 에 맞춤. 클리핑 z 슬라이더 값은 "받침선(P4) 기준 거리 m" 로 표시(z = z_p4 + d).
- `routes/Model.tsx` 레이아웃: 좌 280px 패널(빌드 버전 Select, 섹션 트리 — 구간 그룹 아래 10행: 체크박스·라벨·메시 수·상태 배지·"단독" 버튼), 중앙 캔버스(상단 툴바: 뷰 프리셋 4, 클리핑 z/x 스위치+슬라이더, 선택 노드명 표시), 우 340px 검증 패널(선택 섹션 self-check 표, 결합본 집계 3줄, 렌더 썸네일 4장 → 클릭 시 Modal 확대, 다운로드 링크, 승인/반려 SegmentedControl + 메모 + 기록 버튼, 최근 승인 이력).
- 오류 처리: 서명 URL·GLB 로드 실패 → 해당 섹션 행에 빨간 배지·재시도 버튼, 나머지 섹션 계속. `supabase === null` 이면 기존 화면과 같은 env 안내. WebGL 컨텍스트 실패 → Alert.
- 성능: 섹션 GLB 총 0.5MB, 삼각형 30k → BVH 불필요. 캔버스 리사이즈는 ResizeObserver.

## 7. 테스트

- worker pytest: `test_model_sections.py`(group_of·split 10그룹·assemble 노드 집합 = 원본·이름 중복 assert), `test_model_builder.py` 확장(export_sections 파일 10 + 결합본 compare_glb 편차 0·faces_equal), `test_model_selfcheck_sections`(섹션별 fail 0, BOX 에만 내공 H), `test_model_publish.py`(가짜 `_upload`: 파일 목록·키·해시 skip·`--force`·업로드 실패 시 DB 미기록), `test_db.py`(TABLES·check 키), `test_model_render.py`(views.json 왕복: origin + u·extent 로 bbox 모서리 복원).
- web vitest: `models.test.ts`(modelObjectKey 규칙 = 워커 테스트와 같은 예시 문자열, sectionStatus 최신 우선, approvalPayload 검증), `viewer/scene.test.ts` 는 three 를 jsdom 에서 못 돌리므로 순수 함수(클립 값 ↔ z 변환, 프리셋 카메라 위치 계산)만 분리해 테스트.
- 실증(브라우저 패널, 사용자 로그인 후): 섹션 트리 로드 → DIA 단독 보기 → z 클리핑으로 격실 내부 → 노드 클릭 → 승인 기록 → DB 확인(`db check`·`select … from approvals`). 스크린샷은 세션 내 육안 확인.
- 익명 거부: publishable 키만으로 `GET /storage/v1/object/models/...` 400/403, `POST /rest/v1/approvals` 401.

## 8. 명령 순서 (무과금)

`m3d modelspec` → `m3d build [--pilot]` → `m3d measure` → `m3d render [--pilot]` → `m3d compare-model` → `m3d publish-model [--pilot]` → 웹 `/p/ab1-p4p5/model`.

## 9. 범위 밖

모델링 에이전트(코드 생성), 2D 도면 연동(뷰 계약 JSON 산출까지만), 타 구간 빌더(P5~P6·교각 — 키 구조만 준비), 배포(Vercel), 사진 대조, 결합본 승인이 섹션 승인을 강제하는 규칙(둘은 독립 기록).
