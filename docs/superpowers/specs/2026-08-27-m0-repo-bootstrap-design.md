# M0 — 리포 부트스트랩 설계 (2026-08-27)

`docs/아키텍처_MCP구성_v0.md` §5의 마일스톤 M0("리포 부트스트랩: 모노레포(worker
Python + web React), Supabase 프로젝트, 샘플 도면 1세트")의 확정 설계다.

- 규칙 정본: `docs/모델링규칙_지식베이스_v0.md` — 본 설계의 스키마·CLI는 이 규칙의 구현이다.
- 아키텍처 정본: `docs/아키텍처_MCP구성_v0.md`
- 다음 단계: 본 설계 → 구현 계획(writing-plans) → 구현

## 0. M0의 목적

M0는 기능을 만들지 않는다. **뒤 마일스톤이 딛고 설 바닥이 실제로 서 있는지 실행으로
증명**하는 것이 목적이다. 구체적으로 세 가지를 증명한다.

1. Python 기하·CAD 스택이 이 머신에서 설치·import 된다 (M3까지 쓸 도구가 실재하는가)
2. Supabase에 마이그레이션이 적용되고 RLS가 실제로 데이터를 막는다
3. 샘플 도면 세트 112파일이 무결하게 로컬에 있고 DB에 등재되어 있다

세 가지가 실행 출력으로 확인되지 않으면 M0는 완료가 아니다(전역 규칙 §2).

## 1. 사전 조사 결과 (설계 근거)

### 1-1. 샘플 세트 실측

원본: `D:\Projects\Inspection\mbi_app_v2\assets\drawings_organized\`

| 형태 | 수량 | 용량 | 파이프라인 위치 |
|---|---|---|---|
| DXF 원본 (`_dxf/`) | 50 | 263 MB | **[1] 입력 — 벡터 정본** |
| 통합 PDF (`_정밀조사패키지_P4P5/`) | 1 (61p) | 47 MB | **[1] 입력 — 래스터 경로** |
| PNG 원본해상도 (동상) | 61 | 103 MB | **[2] 변환 산출물 = 회귀 정답** |
| **합계** | **112** | **413 MB** | |

- `_정밀조사패키지_P4P5/_manifest.txt` 50행 = 도면 50종 (핵심 43 / 참고 7), 탭 구분
  `접두 / 등급 / 도면번호_제목 / 페이지수`.
- **P4P5 패키지 50개 도면번호가 `_dxf/`에 50/50 전부 존재**한다(AC1032 ASCII DXF).
  즉 이 테스트베드는 [1] 업로드 입력을 벡터·래스터 양쪽으로 모두 보유한다.

### 1-2. 정답지 (M3 합격 판정용)

전부 텍스트, 합계 약 55KB — 리포에 커밋한다.

| 파일 | 크기 | 용도 |
|---|---|---|
| `models_3d/ab1/SPEC_v2.md` | 8.4 KB | 확정 사양 — [4][6] 대조 정답 |
| `models_3d/ab1/measure_ab1_p4p5_v2.json` | 24.9 KB | 독립 재실측 결과 — [7] 대조 정답 |
| `_참고/접속1교_실측정리.md` | 14.6 KB | 치수 SSOT v1.1.4 |
| `_정밀조사패키지_P4P5/README.md` | 3.6 KB | 섹션 정의·선정 사유 |
| `_정밀조사패키지_P4P5/_manifest.txt` | 3.3 KB | 카탈로그 정답 |

참조 빌더(`build_ab1_p4p5_v2.py` 등)가 실제 사용하는 파이썬 스택은
`trimesh · numpy · matplotlib` 뿐이다(불리언 회피 설계라 manifold3d 미사용).

### 1-3. 로컬 툴체인 실측

| 도구 | 상태 |
|---|---|
| node 22.16 / npm 10.9 | 있음 |
| gh 2.90 | 있음 |
| python | 기본이 Anaconda 3.9 — `py -3.12`(3.12.6) / `py -3.14` 별도 존재 |
| uv · supabase CLI · docker | **없음** |
| make · mingw32-make | **없음** |

- Docker가 없어 `supabase start`(로컬 스택)는 불가. 마이그레이션 경로를 이에 맞춰 설계한다.
- **`make`가 없어 Makefile을 쓰지 않는다.** `m3d` CLI 자체가 태스크 러너 역할을 하고,
  venv 생성처럼 CLI보다 앞서는 단계만 `scripts/bootstrap.ps1`이 맡는다
  (PowerShell이 이 환경의 주 셸이다).
- Windows 콘솔이 기본 cp949라 한국어 출력이 깨진다 → 파이썬 진입점은 `PYTHONUTF8=1`
  전제로 실행한다(부트스트랩 스크립트가 설정).

### 1-4. 파일명 규칙 (전수 검증 완료)

`collect`가 통째로 의존하므로 50행 전수로 확인했다. 여분·누락 0건.

| 대상 | 규칙 | 검증 |
|---|---|---|
| DXF | `{도면번호}.dxf` | 50/50 존재 |
| PNG (page_count = 1) | `{ord}_{name}.png` — **접미사 없음** | 61/61 일치 |
| PNG (page_count > 1) | `{ord}_{name}_p{i}.png` (i = 1..n) | (동상) |
| `_manifest.txt` | UTF-8, BOM 없음, 탭 4필드 | 50행 파싱 성공 |

여기서 `name` 은 `_manifest.txt` 3번째 필드 전체(`{도면번호}_{제목}`)다.

## 2. 확정된 결정

| # | 결정 | 사유 |
|---|---|---|
| D1 | **Supabase 클라우드 신규 프로젝트** | 기존 mbi 프로젝트와 RLS·마이그레이션이 얽히지 않게 분리. Docker 없어 로컬 스택 불가 |
| D2 | **샘플은 로컬 복사** (`data/samples/`, gitignore) | 참조 원본 수정 위험이 구조적으로 0. 413MB 디스크 중복은 수용 |
| D3 | **스키마는 M1 사용분 4테이블만** | 검증할 수 없는 설계를 지금 확정하지 않는다(YAGNI). 나머지는 마일스톤별 마이그레이션 |
| D4 | **구조 A — 2-루트 단순 분리** | 프론트 앱이 1개뿐이라 워크스페이스는 순수 오버헤드. A→B 승격 비용은 나중에도 낮음 |
| D5 | **venv에 전체 스택 설치** | manifold3d 등 Windows 휠 리스크를 M3가 아니라 M0에서 터뜨리는 것이 부트스트랩의 목적 |

## 3. 디렉터리 구조

```
model3d-studio/
├─ CLAUDE.md  README.md  .gitignore  .env.example
├─ docs/
│  ├─ 모델링규칙_지식베이스_v0.md          # 정본 (기존)
│  ├─ 아키텍처_MCP구성_v0.md               # 정본 (기존)
│  └─ superpowers/specs/                   # 설계서
├─ contracts/
│  ├─ db.types.ts                          # web용 DB 타입
│  └─ README.md                            # 계약 갱신 절차
├─ supabase/
│  └─ migrations/0001_init.sql
├─ worker/
│  ├─ pyproject.toml
│  ├─ .venv/                               # gitignore
│  ├─ src/m3d/
│  │  ├─ __init__.py
│  │  ├─ cli.py                            # typer 엔트리
│  │  ├─ config.py                         # .env 로딩·경로 해석
│  │  ├─ db.py                             # psycopg 연결·마이그레이션 러너
│  │  ├─ models.py                         # Pydantic — 0001_init.sql 미러
│  │  ├─ samples/
│  │  │  ├─ manifest.py                    # 매니페스트 생성·로드·대조
│  │  │  ├─ collect.py                     # 원본 → data/samples 복사
│  │  │  └─ source_manifest.py             # `_manifest.txt` 파서
│  │  └─ seed/ab1_p4p5.py
│  └─ tests/
├─ web/
│  ├─ package.json  vite.config.ts  tsconfig*.json  index.html
│  └─ src/{main.tsx, App.tsx, lib/supabase.ts, routes/Health.tsx}
├─ data/
│  ├─ manifests/ab1-p4p5.json              # 커밋 — 112파일 SHA256·출처경로
│  ├─ fixtures/ab1-p4p5/                   # 커밋 — 정답지 55KB (§1-2)
│  └─ samples/ab1-p4p5/{dxf,pdf,png}/      # gitignore — 413MB
└─ scripts/
   ├─ bootstrap.ps1                        # venv 생성·설치 (m3d 이전 단계)
   └─ verify-m0.ps1                       # §9의 1~7 일괄 실행
```

`contracts/`는 npm 패키지가 아니라 **빌드 도구 없는 파일 디렉터리**다. `db.types.ts`와
worker의 `models.py`가 둘 다 `0001_init.sql`을 정본으로 미러링한다. 타입 생성은
구현 시 `npx supabase@latest gen types`를 먼저 시도하고, 실패하면 수기 작성하되
실패 사실과 사유를 `contracts/README.md`에 남긴다(숨기지 않는다).

## 4. Supabase 스키마 — `0001_init.sql`

지식베이스 규칙을 주석이 아니라 **컬럼·제약으로 강제**하는 것이 설계 원칙이다.

```sql
create extension if not exists pgcrypto;

-- ── projects ────────────────────────────────────────────────────────────
-- §1 "프로젝트마다 전역 좌표계를 최우선 확정" → coord_system NOT NULL 로 강제
create table projects (
  id                 uuid primary key default gen_random_uuid(),
  slug               text not null unique,
  name               text not null,
  structure          text,
  coord_system       jsonb not null,
  coord_assumptions  text[] not null default '{}',   -- §1 미확정 가정·정정 메모
  created_at         timestamptz not null default now()
);

-- ── sheets ──────────────────────────────────────────────────────────────
-- §3 "파일명·폴더명은 내용을 보장하지 않는다" → 출처별 컬럼 분리
create table sheets (
  id                        uuid primary key default gen_random_uuid(),
  project_id                uuid not null references projects(id) on delete cascade,
  ord                       text not null,              -- 열람 순서 접두 'A01','C04'
  drawing_no_from_filename  text not null,              -- 미검증
  drawing_no_from_content   text,                       -- M1 [3] 표제란 판독이 채움
  title_from_filename       text not null,
  title_from_content        text,
  scale_from_content        text,
  grade                     text not null check (grade in ('핵심','참고')),
  catalog_status            text not null default 'unverified'
                              check (catalog_status in
                                ('unverified','match','mismatch','unreadable')),
  page_count                int  not null check (page_count > 0),
  created_at                timestamptz not null default now(),
  unique (project_id, ord),
  unique (project_id, drawing_no_from_filename)
);

-- ── sheet_pages ─────────────────────────────────────────────────────────
-- §4 질문 크롭은 원본 픽셀 좌표를 쓴다 → 페이지 픽셀 크기를 필수 보관
create table sheet_pages (
  id         uuid primary key default gen_random_uuid(),
  sheet_id   uuid not null references sheets(id) on delete cascade,
  page_no    int  not null check (page_no > 0),
  width_px   int,
  height_px  int,
  created_at timestamptz not null default now(),
  unique (sheet_id, page_no)
);

-- ── assets ──────────────────────────────────────────────────────────────
-- role: source = [1] 업로드 입력 / derived = [2] 변환 산출물(= 회귀 정답)
create table assets (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references projects(id) on delete cascade,
  sheet_id      uuid references sheets(id) on delete cascade,
  sheet_page_id uuid references sheet_pages(id) on delete cascade,
  kind          text not null check (kind in ('dxf','pdf','png','photo')),
  role          text not null check (role in ('source','derived')),
  rel_path      text not null,
  bytes         bigint not null check (bytes > 0),
  sha256        text not null check (char_length(sha256) = 64),
  storage_path  text,                                   -- M1 Storage 이관 시
  created_at    timestamptz not null default now(),
  unique (project_id, rel_path)
);

create index on sheets(project_id);
create index on sheets(project_id, catalog_status);
create index on sheet_pages(sheet_id);
create index on assets(project_id, kind);
create index on assets(sheet_id);
```

**RLS** — 4테이블 전부 활성화하고 정책은 `authenticated`의 select만 둔다.
anon은 0행을 본다. worker는 service key / DB 직결이라 RLS를 우회한다.
이 비대칭이 §9 검증에서 RLS 작동의 증거가 된다.

```sql
alter table projects    enable row level security;
alter table sheets      enable row level security;
alter table sheet_pages enable row level security;
alter table assets      enable row level security;

create policy "authenticated read" on projects
  for select to authenticated using (true);
-- sheets · sheet_pages · assets 동일
```

**마이그레이션 이력** — `m3d db apply`가 아래를 스스로 만들고 관리한다.

```sql
create table if not exists schema_migrations (
  version    text primary key,      -- '0001_init'
  sha256     text not null,         -- 적용 시점 파일 해시 (사후 변조 검출)
  applied_at timestamptz not null default now()
);
```

## 5. 마이그레이션·시딩 경로

supabase CLI도 Docker도 없으므로 **`psycopg[binary]`로 Session pooler에 직결**한다
(`SUPABASE_DB_URL`). 대시보드 수동 붙여넣기 대비 장점: 재현 가능하고, 적용 여부를
명령 출력으로 검증할 수 있으며, 이력이 `schema_migrations`에 남는다.

- `m3d db apply` — `supabase/migrations/*.sql`을 버전 순으로 트랜잭션 적용.
  이미 적용된 버전은 건너뛰되, 파일 해시가 기록과 다르면 **에러로 정지**한다
  (적용 후 수정된 마이그레이션을 조용히 무시하지 않는다).
- web은 예정대로 `supabase-js` + publishable key를 쓴다.

## 6. worker CLI (`m3d`)

```
m3d doctor                # venv 전체 스택 import 결과표 (PASS/FAIL)
m3d samples collect       # 원본 → data/samples/ 복사 + 매니페스트 생성
m3d samples verify        # 112파일 SHA256 대조
m3d db apply              # 마이그레이션 적용
m3d db check              # 테이블 존재 + 행 수 + 좌표계 출력
m3d seed ab1-p4p5         # 매니페스트 + _manifest.txt → 4테이블 시딩
```

### 6-1. `doctor`가 하드페일하지 않는 이유

각 패키지의 import 결과를 **표로 보고**하고 종료 코드는 0을 유지한다. 휠 문제를
전체 실패로 뭉개면 "무엇이 되고 무엇이 안 되는가"를 잃는다. §5 "단순화는 숨기지
않는다"와 같은 태도다.

| 구분 | 패키지 | FAIL 시 |
|---|---|---|
| **필수 6종** | `ezdxf` `fitz`(PyMuPDF) `trimesh` `numpy` `matplotlib` `psycopg` | **M0 미완료** — 사용자에게 보고하고 대안(py3.11 등) 검토 |
| **선택 1종** | `manifold3d` | 경고로 기록하고 M0는 통과. §1-2에서 확인했듯 참조 빌더는 불리언을 회피해 이 패키지를 쓰지 않는다. M2·M3에서 불리언이 실제로 필요해지는 시점에 재검토 |

### 6-2. `collect`의 원본 보호

원본은 **읽기만** 한다. 복사 후 원본·사본 양쪽 해시를 대조하고 불일치 시 정지한다.
원본 경로는 `.env`의 `SAMPLE_SOURCE_DIR`로만 주입하고 코드에 하드코딩하지 않는다.
(`CLAUDE.md` §2 참조 원본 수정 금지)

### 6-3. `seed`와 편철 오류 회귀 테스트

`_manifest.txt`에서 읽은 도면번호·제목·등급·페이지수는 **전부 `*_from_filename`
컬럼**으로 들어가고 `catalog_status = 'unverified'`로 남는다. M1 [3]이 시트 내부
텍스트에서 도면번호를 **독립적으로** 판독해 `*_from_content`를 채운 뒤 대조한다.
즉 §3의 "표제란 전수 대조 → 편철 오류 검출" 회귀 테스트가 M0 시딩 시점에 이미
성립한다. M0는 정답을 채우지 않는다 — 그게 M1의 시험 문제다.

### 6-4. 시딩되는 좌표계 (`projects.coord_system`)

`SPEC_v2.md` §0에서 가져온다.

```json
{
  "up": "Y", "unit": "m",
  "axes": {
    "x": "교축직각 (상자 중심 x=0, 보도측 = x 음/서측)",
    "y": "EL − 4.871",
    "z": "STA − 4190"
  },
  "datums": {
    "P4_bearing_z": -525.0, "P4_sta": "3+665.000",
    "P5_bearing_z": -455.0, "P5_sta": "3+735.000"
  },
  "source": "models_3d/ab1/SPEC_v2.md §0"
}
```

`coord_assumptions`에는 알려진 정정 1건을 넣는다:
"패키지 README의 P4 STA '3+665.45'는 오기 — SPEC_v2 §0의 3+665.000이 정본
(상세도 M.L STA 역산)".

## 7. web 스켈레톤

`D:\Projects\Inspection\mbi-web-app\web-app-v2`와 **버전까지 일치**시킨다:
React 18.3 · Vite 6 · TypeScript 5.6 · Mantine 8 · `@supabase/supabase-js` 2.
M2·M3에서 뷰 계약·GLB 로더를 이식할 때 버전 차이로 생기는 잡음을 없애기 위함이다.
**three.js는 M0에 넣지 않는다.**

화면은 헬스 1개(`routes/Health.tsx`):

- Supabase 도달 여부
- 익명 세션 상태
- `select from projects` 결과 행 수 — **0행이 정상**(RLS 차단). 에러 없이 0행이면
  "연결 OK · RLS 차단 정상"으로 표시한다.

기대 동작이 "권한 에러"가 아니라 "빈 결과"인 이유: Supabase는 `public` 스키마에
`anon`·`authenticated` 역할의 테이블 권한을 기본 부여하므로 SELECT 자체는 통과하고,
RLS 정책이 행을 걸러 빈 배열이 돌아온다. 따라서 헬스 화면은 **에러 없음 + 0행**을
동시에 확인해야 의미가 있다(둘 중 하나만으로는 연결 실패와 구분되지 않는다).

## 8. 비밀키 취급

`.env` (gitignore, `.env.example`만 커밋):

| 키 | 소비자 |
|---|---|
| `SUPABASE_URL` / `VITE_SUPABASE_URL` | worker / web |
| `SUPABASE_PUBLISHABLE_KEY` / `VITE_SUPABASE_PUBLISHABLE_KEY` | worker / web |
| `SUPABASE_SERVICE_KEY` | **worker 전용** |
| `SUPABASE_DB_URL` | **worker 전용** |
| `SAMPLE_SOURCE_DIR` | worker |

`VITE_` 접두 2개(URL·publishable)만 web 번들에 들어간다. service key와 DB URL은
번들·커밋 금지(`CLAUDE.md` §3).

## 9. M0 완료 기준

전부 **실행 출력으로 확인**한다. 하나라도 미확인이면 완료로 선언하지 않는다.

| # | 명령 | 기대 결과 |
|---|---|---|
| 1 | `m3d doctor` | py3.12 venv, **필수 6종 FAIL 0** + 선택 결과 기록 |
| 2 | `m3d samples collect` | 112파일 복사, `data/manifests/ab1-p4p5.json` 생성 |
| 3 | `m3d samples verify` | **112/112 SHA256 일치 PASS** |
| 4 | `m3d db apply` | 4테이블 + `schema_migrations` 생성 |
| 5 | `m3d seed ab1-p4p5` | projects 1 · sheets 50 · sheet_pages 61 · assets 112 |
| 6 | `m3d db check` | 위 행 수 + 좌표계 JSON 출력 |
| 7 | `pytest` | 매니페스트·`_manifest.txt` 파서 단위테스트 통과 |
| 8 | `npm run dev` | 헬스 화면 "도달 OK / projects 0행(RLS 차단)" → **스크린샷 캡처** |

5·6(service key로 다수 행이 보임)과 8(anon으로 0행)을 나란히 두면 RLS가 실제로
막고 있음이 증명된다. 8의 스크린샷은 전역 규칙 §2("검증 시 영상/화면 캡처 대조")의 이행이다.

### 테스트 (TDD 대상)

단위테스트 대상은 아래 네 가지다.

- `_manifest.txt` 파서: 50행 파싱, 탭 4필드, 도면번호 추출(`^C\d{7}-\d{3}`), 등급 검증
- 매니페스트: 생성 → 로드 → 대조 왕복, 해시 불일치·파일 누락·여분 파일 각각 FAIL 검출.
  **실데이터가 한글 파일명이므로 비ASCII 왕복 회귀 방어를 포함한다**
- `config`: 필수 env 누락 시 명확한 에러
- **복사 경로(`_copy_one`)**: `tmp_path` 합성 파일로 최초 복사·스킵·동일 크기 손상 복구·
  원본 변경 감지·원본 누락을 각각 검증

마지막 항목은 2026-08-27 Task 4 검토에서 추가했다. 원본 보호 가드는 **되돌릴 수 없는
참조 자산 옆에서 도는 코드**라 회귀 방어가 없으면 안 된다. `tmp_path` 합성 파일이라
실데이터 413MB를 건드리지 않고 수 ms에 끝나므로, 아래에서 배제하는 '무거운 통합테스트'에
해당하지 않는다.

**실데이터를 쓰는** DB·복사·CLI 통합 동작은 §9 표의 실행으로 검증한다(별도 통합테스트를
M0에 만들지 않는다).

## 10. 범위 밖 (명시적 제외)

M0가 **하지 않는** 것 — 각각의 담당 마일스톤을 병기한다.

| 제외 항목 | 담당 |
|---|---|
| PDF→이미지·DXF 파싱 실행 | M1 [2] |
| 표제란 판독·`*_from_content` 채우기 | M1 [3] |
| Supabase Storage 업로드 (`assets.storage_path`) | M1 |
| 판독·ambiguity·decisions 테이블 | M2 |
| 질문 카드 UI, three.js 뷰어 | M2 / M3 |
| members·builds·verifications·renders·approvals 테이블 | M2 / M3 |
| 인증(로그인) 플로우 | M2 |
| 배포(Vercel·워커 서버) | M3 이후 |

## 11. 리스크

| 리스크 | 대응 |
|---|---|
| 필수 6종 중 Windows/py3.12 휠 부재 | `doctor`가 표로 보고. **M0 미완료 처리**하고 대안(py3.11 등) 검토 |
| manifold3d(선택) 휠 부재 | 경고 기록 후 M0 통과. M2·M3에서 불리언이 필요해질 때 재검토 |
| Session pooler 연결 차단(방화벽·IPv6) | 실패 시 direct connection 문자열로 폴백, 그래도 안 되면 대시보드 SQL Editor 수동 적용 + 그 사실을 명시 보고 |
| `npx supabase gen types`가 Docker 요구 | 수기 타입 작성으로 폴백하고 사유를 `contracts/README.md`에 기록 |
| 413MB 복사 중단 | `collect`는 재실행 가능(멱등) — 해시 일치 파일은 건너뜀 |
| 참조 원본 오염 | `collect`는 읽기 전용, 사후 원본 해시 재확인 |

## 12. 사용자 선행 작업 (블로커)

§9의 4·5·6·8은 Supabase 프로젝트 없이는 실행할 수 없다. 계정 생성과 키 발급은
대리 수행하지 않는다.

1. supabase.com에서 프로젝트 생성 (이름 예: `model3d-studio`, 리전 서울 권장)
2. Project Settings → API에서 **Project URL** · **publishable(anon) key** · **service_role key**
3. Project Settings → Database에서 **Session pooler connection string**
4. 위 4개를 로컬 `.env`에 기입

1~3이 준비되기 전에도 §9의 1·2·3·7과 web 스켈레톤 빌드까지는 진행 가능하다.
