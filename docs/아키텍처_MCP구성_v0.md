# 서비스 아키텍처 + MCP·커넥터 구성 v0

도면(CAD/PDF)과 사진을 넣으면 AI 에이전트들이 부재별로 병렬 3D 모델링하고,
애매한 부분은 도면 크롭과 함께 사용자에게 질문하는 웹 서비스.
규칙 정본: `모델링규칙_지식베이스_v0.md` (전 단계가 이 규칙을 구현).

## 1. 파이프라인 (8단계)

```
[1] 업로드            도면(PDF·DWG·DXF·이미지) + 현장 사진 (+선택: 기존 3D 자산)
[2] 변환·정규화       PDF→페이지 이미지+텍스트(pypdfium2/pdftoppm), DXF 파싱(ezdxf),
                      시트별 고해상 PNG + sheet_text 생성 (AI가 읽을 수 있는 형태)
[3] 카탈로그·분류     표제란 판독(도면번호·제목·척도) → 전수 대조(편철 오류 검출)
                      → 부재·섹션별 시트 분류 + 커버리지 맵 (LLM)
[4] 병렬 판독         영역(계열)별 판독 에이전트 → 치수 SSOT 초안 + ambiguity 수집
                      → 적대적 검토 에이전트 통과 후 확정
[5] 질문 루프         ambiguity → 도면 크롭 자동 생성 → 질문 카드 큐
                      (한 카드 = 한 요소, 크롭 + 선택지 + 모델 영향) → 결정을 SSOT 반영
[6] 병렬 모델링       부재 그룹별 모델링 에이전트가 파라메트릭 빌더(Python+trimesh)
                      생성·실행 → 부재 노드 명명 규칙 적용 → GLB 병합
[7] 3중 검증          빌더 self-check → 독립 재실측 에이전트 → 렌더 세트 생성
                      → 사용자 승인 게이트 (시범 구간 → 확산)
[8] 산출·연동         GLB + SPEC + 재실측 리포트 + 뷰 계약(2D 연동용) 다운로드/API
```

- 사진의 역할: 도면-실물 교차 확인(형상·부속 존재 여부), 도면에 없는 요소의
  미확인 등재. 사진 단독으로 치수를 확정하지 않는다.
- 모든 단계 산출물은 프로젝트 저장소에 버전으로 남긴다(재실행 가능).

## 2. 시스템 구성

| 계층 | 선택 | 근거 |
|---|---|---|
| 오케스트레이션 | **Claude Agent SDK** (Python) | 본 프로젝트에서 검증한 패턴 그대로: 병렬 판독 워크플로·구조화 출력 스키마·독립 검증관. 서브에이전트+Workflow 개념을 서버 측에서 재현 |
| LLM | Claude (claude-fable-5 / claude-sonnet-5) | 판독·분류는 sonnet, 애매성 판정·검토는 fable 상향 |
| 기하 엔진 | Python: trimesh + numpy (+ manifold3d) | GLB 산출·수밀 검사·슬라이스 실측 전부 검증된 조합 |
| CAD 파싱 | ezdxf (DXF), **pypdfium2**·pdftoppm (PDF) | DWG는 ODA File Converter로 DXF 변환 후 처리(라이선스 프리 원칙). PyMuPDF는 AGPL-3.0/상용 듀얼 라이선스라 서버측 래스터화 SaaS에 제약 — M0에서 pypdfium2(BSD/Apache)로 교체 |
| 렌더 검수 | matplotlib 정사영(painter) + three.js 웹 뷰어 | 정사영 실척 렌더는 검증용, 웹 뷰어는 사용자 게이트용 |
| 웹 프론트 | React + Vite + Three.js (WebGL) | 기존 web-app-v2 스택 재사용 — 뷰 계약·GLB 로더 이식 |
| DB·인증·저장소 | Supabase (PostgreSQL + Auth + Storage, RLS) | 검증된 스택. 프로젝트/시트/ambiguity/결정/모델 버전 테이블 |
| 배포 | Vercel (프론트) + 워커 서버(파이프라인, GPU 불요) | 파이프라인은 큐 기반 비동기(작업당 수 분~수십 분) |

## 3. 개발 세션에서 쓸 MCP·커넥터·플러그인

**필수 (개발·운영 공통)**
| 도구 | 용도 |
|---|---|
| filesystem MCP | 도면·산출물 로컬 파이프라인 개발 |
| GitHub MCP (또는 gh CLI) | 레포·PR·이슈. 질문 카드 큐의 개발 중 대용으로 이슈 활용 가능 |
| Supabase (REST — 자체 스크립트 `_db.py` 패턴) | 스키마·시딩·검증 쿼리. service key는 로컬 전용, 앱은 publishable key |
| Claude in Chrome / Browser 패널 | 웹 UI E2E 검증(질문 카드·뷰어), 스크린샷 증적 |
| Vercel CLI(커넥터 아님, 로컬) | 배포. `vercel deploy`는 반드시 프로젝트 링크 확인 후(폴더명 신규 프로젝트 함정) |

**권장 (있으면 활용)**
| 도구 | 용도 |
|---|---|
| superpowers 플러그인 | 프로세스 스킬(브레인스토밍→계획→TDD→검증) — 전역 규칙 그대로 상속 |
| context7 / 공식문서 MCP | Agent SDK·three.js·ezdxf 최신 API 조회 |
| Figma MCP | 질문 카드·검수 화면 UI 설계 시 |

**의도적으로 쓰지 않는 것**
- 해외 상용 CAD SDK(Autodesk Platform Services 등) — 라이선스 프리 원칙, DXF/개방
  포맷 경로로 대체
- 범용 OCR SaaS — 표제란·치수 판독은 LLM 비전으로 충분함을 실증(필요 시 후순위 검토)

## 4. 데이터 모델 초안 (Supabase)

- projects(구조물·좌표계 정의) / sheets(도면번호·제목·척도·분류·커버리지·이미지 경로)
- readings(판독 결과: 항목·값·근거 시트·검산·상태 확정/추정)
- ambiguities(항목·크롭 경로·선택지 JSON·모델 영향·상태 대기/결정/잠정)
- decisions(질문 응답: 선택·응답자·시각 — SSOT 반영 로그)
- members(부재 트리·명명 규칙) / builds(모델 버전·GLB 경로·self-check JSON)
- verifications(재실측 리포트) / renders(렌더 세트) / approvals(게이트 이력)

## 5. 첫 마일스톤 제안 (별도 세션에서 착수)

1. M0 — 리포 부트스트랩: 모노레포(worker Python + web React), Supabase 프로젝트,
   샘플 도면 1세트(접속1교 P4~P5 패키지 재사용 — 정답지가 이미 있는 최고의 테스트베드)
2. M1 — 파이프라인 [2][3]: 변환·카탈로그·표제란 대조를 CLI로
3. M2 — [4][5]: 판독 에이전트+ambiguity → 질문 카드 웹 UI (한 요소·크롭·선택지)
4. M3 — [6][7]: P4~P5를 서비스 파이프라인만으로 재현 → 기존 SPEC_v2/재실측과 대조
   (정답 대조가 가능한 유일한 구간 — 이것이 v0의 합격 기준)
