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

4. 웹:

   ```powershell
   npm --prefix web ci
   npm --prefix web run dev
   ```

## 검증

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-m0.ps1
```

`make` 는 이 환경에 없다. `m3d` CLI 가 태스크 러너를 겸한다.

## 주의

- `SAMPLE_SOURCE_DIR` · `REFERENCE_MODELS_DIR` 아래 참조 원본은 **읽기 전용**이다.
- `SUPABASE_SERVICE_KEY` · `SUPABASE_DB_URL` 은 worker 전용 — 웹 번들·커밋 금지.
- 검증 없이 완료를 주장하지 않는다. 실패는 출력과 함께 실패로 보고한다.
