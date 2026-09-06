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
```

`ModelSpec` 스키마가 바뀌면 `modelspec.json` 을 다시 만든다 — `build` 는 저장 파일에 없는 필드를 발견하면 경고한다.
합격 판정은 `data/derived/ab1-p4p5/model/acceptance-m3.md`(설계서 §1 ①~⑥).
