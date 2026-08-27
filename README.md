# model3d-studio

도면(CAD·PDF)과 사진을 입력하면 AI 에이전트들이 부재·섹션별로 병렬 판독·3D 모델링·
검수하고, 도면상 구분이 어려운 부분은 **도면 크롭과 함께 사용자에게 질문**하는 웹 서비스.

정본 문서:
- [`docs/모델링규칙_지식베이스_v0.md`](docs/모델링규칙_지식베이스_v0.md) — 판독·질문·모델링·검증 규칙
- [`docs/아키텍처_MCP구성_v0.md`](docs/아키텍처_MCP구성_v0.md) — 파이프라인 8단계·기술 스택·마일스톤
- [`docs/M0_부트스트랩.md`](docs/M0_부트스트랩.md) — 지금 무엇이 있고 무엇이 검증되었는가

**현재 상태: M0 (부트스트랩).** 파이프라인 8단계는 아직 구현되지 않았다.

## 빠른 시작

필요한 것: Node 22+, [pnpm](https://pnpm.io) 10, [uv](https://docs.astral.sh/uv/).
Python 인터프리터는 uv 가 `.python-version` 을 보고 알아서 받아온다.

```bash
pnpm install
uv sync --project apps/worker

cp .env.example .env        # 값을 채운다 — .env 는 커밋하지 않는다

pnpm run dev                                  # 웹 개발 서버
uv run --project apps/worker m3d doctor       # 워커 환경 점검
```

## 구조

| 경로 | 내용 |
|---|---|
| `apps/web` | React 19 + Vite 8 + three.js — 뷰어·질문 카드 UI |
| `apps/worker` | Python 3.13 + uv — 파이프라인 워커, `m3d` CLI |
| `packages/contracts` | 워커와 웹이 공유하는 데이터 계약 — **JSON Schema 가 정본** |
| `supabase/` | 스키마 마이그레이션 · RLS · Storage · 도메인 규칙 SQL 테스트 |
| `samples/` | 샘플 도면 세트 정의와 매니페스트 (원본 파일은 커밋하지 않는다) |
| `scripts/` | `verify-supabase.sh` |

## 검증

규칙 §6 — 검증 없이 완료를 주장하지 않는다. 각 명령은 실패를 실패로 보고한다.

```bash
pnpm run check                                   # 포맷·린트·타입·테스트·빌드
uv run --project apps/worker pytest              # 워커 테스트
uv run --project apps/worker m3d contracts check # 계약이 실제로 강제되는지
scripts/verify-supabase.sh                       # 마이그레이션 + 도메인 규칙 (PG 필요)
```

`m3d contracts check` 는 "거부되어야 하는 문서"를 실제로 거부하는지 확인한다 —
규칙이 문서가 아니라 코드로 강제되고 있다는 증거다.

## CI

`ci/workflows/ci.yml` 을 `.github/workflows/` 로 옮기면 켜집니다 — GitHub App 의
`workflows` 권한 부족으로 자동 설치가 막혀 있습니다. 자세한 내용은 [`ci/README.md`](ci/README.md).

## 샘플 도면 세트

원본은 사용자 로컬에만 있고 읽기 전용이다. 리포에는 매니페스트만 커밋한다.
자세한 내용은 [`samples/README.md`](samples/README.md).

```bash
# .env 에 M3D_SAMPLE_SOURCE_AB1_P4P5=<원본 경로> 를 넣은 뒤
uv run --project apps/worker m3d samples ingest ab1_p4p5
uv run --project apps/worker m3d samples verify ab1_p4p5
```

## 비밀키

`.env` 전용이며 커밋·번들 금지 (CLAUDE.md §3).
- 웹은 **publishable key** 만 쓴다 — service key 형태가 들어오면 앱이 거부한다.
- 워커는 service key 로 RLS 를 우회하며, 값은 `SecretStr` 로만 다룬다.
