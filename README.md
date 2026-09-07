# model3d-studio

도면(CAD·PDF)과 사진을 넣으면 AI 에이전트가 부재·섹션별로 병렬 판독·3D 모델링·
검수하고, 도면상 구분이 어려운 부분은 도면 크롭과 함께 사용자에게 질문하는 웹 서비스.

- 규칙 정본: [모델링규칙 지식베이스](docs/모델링규칙_지식베이스_v0.md)
- 아키텍처 정본: [아키텍처·MCP 구성](docs/아키텍처_MCP구성_v0.md)
- M0 설계서: [리포 부트스트랩](docs/superpowers/specs/2026-08-27-m0-repo-bootstrap-design.md)

## 구조

| 경로 | 내용 |
|---|---|
| `worker/` | Python 파이프라인 (`m3d` CLI). 판독·모델링·검증 |
| `web/` | React + Vite 프론트 |
| `contracts/` | web·worker 공유 DB 타입 (빌드 도구 없는 파일 디렉터리) |
| `supabase/migrations/` | 스키마 정본 |
| `data/manifests/` | 샘플 SHA256 매니페스트 (커밋) |
| `data/fixtures/` | 정답지·카탈로그 사본 (커밋) |
| `data/samples/` | 도면 원본 사본 413MB (**gitignore**) |
| `data/derived/` | 변환 산출물 — 페이지 PNG·sheet_text·리포트 (**gitignore**) |

## 시작하기

1. `.env.example` 을 `.env` 로 복사하고 값을 채운다 (설계서 §12).
2. venv 생성·설치:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
   ```

3. 샘플 수집·DB 적용:

   ```powershell
   .\worker\.venv\Scripts\m3d.exe samples collect
   .\worker\.venv\Scripts\m3d.exe db apply
   .\worker\.venv\Scripts\m3d.exe seed ab1-p4p5
   .\worker\.venv\Scripts\m3d.exe convert ab1-p4p5
   .\worker\.venv\Scripts\m3d.exe catalog ab1-p4p5
   ```

   아래 2개는 Anthropic API 비용이 발생한다(설계서 §2-1·§8 — 도면 판독·검토):

   ```powershell
   .\worker\.venv\Scripts\m3d.exe read ab1-p4p5
   .\worker\.venv\Scripts\m3d.exe review ab1-p4p5
   ```

   크롭 생성은 LLM 을 부르지 않는다 — 이미 DB 에 있는 ambiguity 좌표로 PNG 를
   잘라낼 뿐이라 무과금이다:

   ```powershell
   .\worker\.venv\Scripts\m3d.exe crops ab1-p4p5
   ```

4. 웹:

   ```powershell
   npm --prefix web ci
   npm --prefix web run dev
   ```

## 검증

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-m0.ps1
powershell -ExecutionPolicy Bypass -File scripts\verify-m2a.ps1
```

`verify-m2a.ps1` 은 `--cache-only` 로만 돌아 LLM 실호출을 하지 않는다(무과금 멱등 검증).
로컬 캐시(`data/derived/ab1-p4p5/llm-cache`, gitignore)가 없으면 실패로 끝난다 — 정상이다.

`make` 는 이 환경에 없다. `m3d` CLI 가 태스크 러너를 겸한다.

## 주의

- `SAMPLE_SOURCE_DIR` · `REFERENCE_MODELS_DIR` 아래 참조 원본은 **읽기 전용**이다.
- `SUPABASE_SERVICE_KEY` · `SUPABASE_DB_URL` · `ANTHROPIC_API_KEY` · `ANTHROPIC_WORKSPACE_ID` 는
  worker 전용 — 웹 번들·커밋 금지. 값 목록은 `.env.example` 참고.
- `m3d read` · `m3d review` 의 전제는 두 값(`ANTHROPIC_API_KEY`·`ANTHROPIC_WORKSPACE_ID`)이 채워진 `.env` 다.
- 검증 없이 완료를 주장하지 않는다. 실패는 출력과 함께 실패로 보고한다.

## 질문 카드 (M2b)

판독이 끝난 뒤 애매성을 웹에서 답하고, 결정을 포함한 치수 정본을 만든다. 아래는 모두 **Anthropic API 비용 없음**.

```powershell
$env:PYTHONUTF8='1'
.\worker\.venv\Scripts\m3d.exe publish ab1-p4p5   # 크롭 PNG → 비공개 Storage 버킷 crops (SUPABASE_URL·SUPABASE_SERVICE_KEY 필요)
.\worker\.venv\Scripts\m3d.exe ssot ab1-p4p5      # data/derived/ab1-p4p5/ssot/실측정리_v<N>.md + ssot.json (내용이 바뀔 때만 버전 증가)
cd web; npm run dev                                   # http://localhost:5173 — Supabase 대시보드(Authentication → Users)에서 만든 계정으로 로그인
```

카드: 숫자키 `1`~`4` 선택, `0` 모르겠다(권장안을 잠정 채택), `Enter` 결정, `←`/`→` 이동. 결정은 `decisions` 에 이력으로 쌓이고
`ambiguities.status` 가 결정/잠정으로 바뀐다. 재판독(`read`/`review`)은 결정이 달린 애매성을 보존한다.

## 3D 모델 (M3)

SSOT(+결정)를 `ModelSpec` 으로 옮겨 P4~P5 정밀 모델(GLB)을 결정론 빌더로 만들고 3중 검증(self-check → 독립 재실측 → 렌더)한 뒤
참조 정답(measure v2·GLB)과 대조한다. 아래 5개 명령은 **LLM 을 부르지 않는다**(무과금). 산출물은 `data/derived/<dataset>/model/`(gitignore).

```powershell
$env:PYTHONUTF8='1'
.\worker\.venv\Scripts\m3d.exe modelspec ab1-p4p5       # ssot.json → modelspec.json (필드별 출처 ssot/decision/default/derived 통계)
.\worker\.venv\Scripts\m3d.exe build ab1-p4p5 --pilot   # 시범: 본체·격벽만 → model/pilot/{sections/,AB1_P4P5.glb,selfcheck*.json,build.json} (승인 게이트)
.\worker\.venv\Scripts\m3d.exe build ab1-p4p5           # 전 부재 → model/{sections/P4P5/<그룹>.glb ×10, AB1_P4P5.glb(결합본), selfcheck.json, selfcheck_sections.json, build.json}
.\worker\.venv\Scripts\m3d.exe measure ab1-p4p5         # 독립 재실측(빌더 미참조, 5mm/0/0.5°) → measure.json (fail>0 → exit 1)
.\worker\.venv\Scripts\m3d.exe render ab1-p4p5          # 실척 정사영 4장 → renders/{side_context,front_section,bottom_iso,interior_cells}.png
.\worker\.venv\Scripts\m3d.exe compare-model ab1-p4p5   # 참조 measure v2·GLB 대조 → compare.json (--ref 생략 시 REFERENCE_MODELS_DIR)
.\worker\.venv\Scripts\m3d.exe publish-model ab1-p4p5   # 섹션·결합본·렌더·검증 JSON → 비공개 버킷 models + builds/build_sections (내용 같으면 skip, --force, --pilot)
```

`ModelSpec` 스키마가 바뀌면 `modelspec.json` 을 다시 만든다 — `build` 는 저장 파일에 없는 필드를 발견하면 경고한다.
합격 판정은 `data/derived/ab1-p4p5/model/acceptance-m3.md`(설계서 §1 ①~⑥).

## 3D 검수 (M4)

모델을 섹션(구간/부재그룹) GLB 10개 + 결합본으로 산출해 비공개 버킷 `models` 에 올리고, 웹에서 섹션을 따로 띄워 내부까지 검수한 뒤 승인/반려를 기록한다. 모두 **LLM 호출 없음**.

```powershell
$env:PYTHONUTF8='1'
.\worker\.venv\Scripts\m3d.exe build ab1-p4p5            # model/sections/P4P5/<그룹>.glb ×10 + AB1_P4P5.glb(결합본) + selfcheck_sections.json + build.json
.\worker\.venv\Scripts\m3d.exe render ab1-p4p5           # renders/*.png + renders/views.json(뷰 계약)
.\worker\.venv\Scripts\m3d.exe publish-model ab1-p4p5    # Storage 업로드 + builds/build_sections (내용 같으면 skip · --force · --pilot)
cd web; npm run dev                                       # http://localhost:5173/p/ab1-p4p5/model
```

화면: 좌 섹션 트리(표시 체크·단독 보기·상태 배지·빌드 버전), 중앙 three.js 캔버스(프리셋 4·z/x 단면 클리핑·부재 클릭 → 노드명),
우 검증 패널(섹션 self-check·재실측·참조대조 집계·렌더·다운로드·승인/반려 기록). 승인은 `approvals` 에 이력으로 쌓이고 트리거가
`build_sections.status`/`builds.status` 를 갱신한다. 합격 판정: `data/derived/ab1-p4p5/model/acceptance-m4.md`.

## LLM 모델링 (M5)

웹 검수 화면에서 섹션의 "LLM 으로 만들기"를 누르면 `jobs` 큐에 잡이 생기고, 내 PC 의 워커가 Sonnet 5 로 섹션 빌더 코드를 받아
샌드박스에서 실행·채점(정답 대조 + 레고식 결합 재실측)한 뒤 에이전트 빌드로 올린다. **API 과금 발생** — `.env` 의 `MODEL_AGENT_BUDGET_USD`(기본 5) 누적 상한.

```powershell
$env:PYTHONUTF8='1'
.\worker\.venv\Scripts\m3d.exe worker --once     # 큐의 잡 1건 처리 (--once 없이 데몬으로)
```

M5 범위: 격벽(P4P5/DIA) 1섹션. 산출물 `data/derived/ab1-p4p5/model/agent/<job>/`(코드·시도·채점·프롬프트·크롭). 판정: `model/acceptance-m5.md`.

### M6 — 격벽 PASS: 정보 보강 + 자기 렌더 (2026-09-07)

M5 의 최선(b4)은 판·개구·체인·재실측이 맞고 보강재 3D 배치만 틀렸다. M6 는 LLM 에게 없던 정보를 채우고 숫자에 의미를 붙였다
(설계서 `docs/superpowers/specs/2026-09-07-m6-diaphragm-pass-design.md`, 판정서 `data/derived/ab1-p4p5/model/acceptance-m6.md`).

- **스펙 필드 의미**: `ModelSpec` 격벽·받침 필드의 `description` 이 프롬프트 발췌의 `doc` 으로 들어간다 — 튜플의 각 성분이 뻗는 축(`[x]·[y]·[z]`), 편측 부착 규약, 개구 밖 배치, 웹 내면 정의.
- **KB §5 보강재 규약** 2줄(두께는 판면 안 방향·돌출은 판면 법선 방향 / 지점 격벽 보강재는 경간 안쪽 면만·개구보강재는 +z 면만) — `kb_excerpt` 로 시스템 프롬프트에 자동 반영.
- **채점 피드백**: "노드 bbox = 판+보강재 전체 범위" 정의, 축별 델타 문장("정답이 +z 쪽으로 90mm 더 뻗음"), 노드 역할 라벨(지점/일반 격벽), 판 유지·체인·돌출≠두께 힌트.
- **자기 렌더**: 채점 실패 뒤 에이전트 섹션 GLB 만으로 3장(DIA01 정면 아이소·측면 체인선·DIA13 아이소)을 다음 시도 프롬프트에 붙인다(`model/agent/<job>/agent/critique<n>/`). 정답 렌더는 주지 않는다.
- **예산 입력**: 웹 모달 "예산 상한 ($)"(기본 5, 0.5~50) → `jobs.budget_usd` = stage 누적 상한. 잡 `cost_usd` 는 재시도 호출 포함. bbox 판정에 float32 반올림 여유 0.1 mm.

실증(요청 없는 잡 4건 · 14시도 · 17호출 · $1.78, 상한 $8): 최대 bbox 편차 326 mm(M5) → **8 mm**(잡 1) → 90 mm(잡 2, 개구보강재 돌출을 두께로 해석) → **5.001 mm**(잡 3, 모든 검사 0 fail·삼각형 수 정답과 동일) → **잡 4 시도 2 PASS**(b9, bbox 5.001 mm·검사 0 fail).
잡 1~3 은 실행 당시 규칙(≤ 5.000 mm)으로 FAIL 이었고, 잡 3 의 5.001 mm 가 정확히 5 mm(INS)의 float32 반올림임을 확인해 판정에 여유 0.1 mm 를 둔 뒤(잡 3 오프라인 재채점 PASS, `model/agent/rescore/`) 사용자 결정으로 잡 4 를 돌려 화면·DB 에서 PASS 를 확인했다. b8 은 실행 당시 규칙대로 FAIL 로 남아 있다.

### M7 — 8섹션 확산 (2026-09-07)

격벽 외 8섹션(SP04·HST·SLAB·BRG·FRM·RIB·CS·WG)을 LLM 이 만들 수 있게 인프라를 일반화했다
(설계서 `docs/superpowers/specs/2026-09-07-m7-section-spread-design.md`, 판정서 `data/derived/ab1-p4p5/model/acceptance-m7.md`).

- **섹션 메타 한 표** `agent/sections_meta.py`: 판독 근거 정규식·대표 노드·역할 라벨·스펙 발췌 키·섹션 규약(notes)을 한 곳에. 새 부재 그룹은 여기 한 줄이면 대상이 된다.
- **ctx 확장** `SectionContext`: 강상판 상면·crown·하판 하면·판두께·색 4종·`zone_loft` 까지 본체 프로파일 전체. 본체(BOX)는 ctx 가 곧 그 기하라 확산 대상이 아니다.
- **스펙 전 필드 설명**: `ModelSpec` 10개 하위 모델의 모든 필드에 축·단위·배치 규칙. 참조 빌더가 형상에 쓰지 않는 값은 그렇다고 밝힌다.
- **노드명 계약**: 섹션마다 정답 노드명 전체를 계약에 싣는다(채점이 노드 집합 일치를 요구한다).
- **자기 렌더 3뷰**: 대표 부재 정면·측면 + **섹션 전체 아이소**. 개수·간격·좌우 배치 오류는 전체 뷰에서만 보인다.
- **일괄 큐**: 섹션 다중 선택 → "선택 N개 LLM 모델링" → `m3d worker --poll --drain` 이 순차 처리.
- **전집 결합**: `m3d agent-assemble` 이 섹션마다 통과한 에이전트 산출을 모아 결합 빌드를 만들고 검증·업로드한다.

사용법: 웹 `/p/<slug>/model` 에서 섹션을 고르고 예산을 정해 잡을 만든 뒤 `m3d worker --poll 2 --drain`, 끝나면 `m3d agent-assemble`.

### M8 — 정답 없는 합격 규칙 (2026-09-07)

M7 까지의 합격 판정은 결정론 빌더 산출과의 bbox 대조에 기대고 있었다. 새 교량에는 그 정답이 없다.
M8 은 판정을 세 겹으로 바꿨다: **기하 건전성 → 스펙 유도 재실측 → 사람 승인**
(설계서 `docs/superpowers/specs/2026-09-07-m8-reference-free-rule-design.md`, 판정서 `data/derived/ab1-p4p5/model/acceptance-m8.md`).

- **기하 건전성** `model/sanity.py`: 외곽 이탈·부유 부재·중복 배치. 스펙 해석 없이 큰 사고를 잡는다.
- **재실측 보강**: 재실측 행에 섹션 태그를 붙이고 항목을 49 → 95개로 늘렸다. 0건이던 이음판·수평보강재를 채우고, z 로 긴 부재는 bbox 대신 단면 슬라이스로 잰다.
- **합격 규칙**: `건전성 fail 0 ∧ 섹션 self-check fail 0 ∧ 결합 self-check fail 0 ∧ 그 섹션 재실측 fail 0`. 정답 대조는 참고 정보로만 남는다(`score.reference`). `ref_dir=None` 으로 부르면 정답 없이 판정한다.
- **회귀 검증** `m3d verify-rule`: 이미 쌓인 에이전트 산출에 새 규칙을 돌려 (편차 구간 × 합격) 혼동표를 낸다. 무과금이라 규칙을 고칠 때마다 다시 돌린다.

결과: 기존 산출 32건에서 **거짓 합격 0 · 거짓 불합격 0**(≥100 mm 21건 전부 불합격, ≤5 mm 4건 전부 합격).
가로보 정착대 1.7 m·격벽 보강재 326 mm·이음판 157 mm 처럼 M6·M7 에서 정답 대조로만 잡히던 오류가 이제 정답 없이 잡힌다.
실증: 재실측이 0건이던 수평보강재·이음판 두 섹션이 새 규칙에서 첫 시도에 통과($0.28).

