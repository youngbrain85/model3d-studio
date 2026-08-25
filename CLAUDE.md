# model3d-studio — AI 도면 기반 3D 모델링 웹서비스

도면(CAD·PDF)+사진을 입력하면 AI 에이전트들이 부재·섹션별로 병렬 판독·3D 모델링·
검수하고, 도면상 구분이 어려운 부분은 **도면 크롭과 함께 사용자에게 질문**(한 질문=
한 요소)하는 웹 서비스. 원산안면대교 프로젝트에서 확립한 모델링 방법론의 제품화.

## 0. 전역 규칙 상속

`C:\Users\parkj\.claude\CLAUDE.md` (superpowers 필수·검증 없는 완료 보고 금지·한국어)
전부 적용.

## 1. 정본 문서 (작업 전 필독)

- **docs/모델링규칙_지식베이스_v0.md** — 판독·질문·모델링·검증 규칙. 에이전트
  프롬프트와 검증기는 이 규칙의 구현이어야 한다.
- **docs/아키텍처_MCP구성_v0.md** — 파이프라인 8단계·기술 스택·MCP 구성·데이터
  모델·마일스톤(M0~M3).

## 2. 참조 원본 (읽기 전용 — 수정 금지)

| 경로 | 내용 |
|---|---|
| `D:\Projects\Inspection\mbi_app_v2\docs\지식베이스_교훈.md` | 실수·교훈 83항 원본 |
| `D:\Projects\Inspection\mbi_app_v2\models_3d\ab1\` | 방법론 실례: SPEC_v2.md·빌더·독립 재실측·렌더 |
| `D:\Projects\Inspection\mbi_app_v2\assets\drawings_organized\_정밀조사패키지_P4P5\` | 샘플 도면 세트(테스트베드) — **정답 데이터**(SPEC·재실측 JSON) 보유 |
| `D:\Projects\Inspection\mbi-web-app\web-app-v2\` | 웹 스택 재사용원(three.js 뷰어·뷰 계약·Supabase 패턴) |

## 3. 작업 규칙

- 판독 에이전트는 애매값을 추정으로 확정하지 않는다 — ambiguity 구조로 분리
  (지식베이스 §3·§4). 사용자 질문은 한 번에 한 요소, 크롭 동반.
- 모델 산출은 3중 검증(self-check → 독립 재실측 → 렌더 육안) 없이 완료 선언 금지.
- 시범(대표 구간) → 사용자 승인 게이트 → 확산 순서를 지킨다.
- v0 합격 기준: 접속1교 P4~P5를 서비스 파이프라인만으로 재현해 기존
  SPEC_v2·재실측 결과와 대조 일치(M3).
- 비밀키(Supabase service key 등)는 로컬 `.env` 전용, 커밋·번들 금지.
