# M2a — 판독 파이프라인 [4] + 크롭 생성 설계 (2026-08-30)

`docs/아키텍처_MCP구성_v0.md` §5 M2("[4][5]: 판독 에이전트+ambiguity → 질문 카드 웹
UI")의 **전반부**다. M2는 두 스펙으로 분해한다(사용자 결정 2026-08-29):

- **M2a (본 설계)**: [4] 병렬 판독 → readings·ambiguities → 적대적 검토 + 크롭 생성 — CLI 완결
- **M2b (후속 스펙)**: [5] 질문 카드 웹 UI → decisions → SSOT 반영

- 규칙 정본: `docs/모델링규칙_지식베이스_v0.md` §1~§4·§8 — 본 설계의 프롬프트·스키마·
  검증기는 이 규칙의 구현이다.
- 전제: M1 완료 — 페이지 PNG 61(8000px)·sheet_text JSON 61(용지 mm 좌표)·
  catalog 49/0/1이 DB와 `data/derived/`에 있다.

## 0. M2a의 목적

시트 내용에서 **치수 SSOT 초안(readings)** 을 만들고, 애매한 값을 추정으로 확정하지
않고 **ambiguity로 분리**해 크롭 이미지까지 준비한다 — M2b 질문 카드의 원천.
합격의 핵심은 "원 프로젝트에서 사람이 물어야 했던 것을 파이프라인이 스스로 찾아내는가"다.

## 1. 정답지 (합격 판정의 근거 — 전부 리포 fixtures 에 있음)

| 자료 | 내용 | 용도 |
|---|---|---|
| `SPEC_v2.md` §0~ | **사용자 결정 4건**: Q1 형고 4,000/2,800=내공(C계열) · Q2 슬래브 기입두께=순두께(B) · Q3 보도 2,950+방호벽 450(B) · Q4 면진받침 표현(A) | **ambiguity 검출의 정답** — 파이프라인이 이 4건에 대응하는 질문을 스스로 만들어야 한다 |
| `접속1교_실측정리.md` §9 | 미결 12건(전 34건 중 핵심) — 받침 표기 상충, "3열 vs 8열"=존 병존, 곡선 계수 3종 등 | ambiguity 의 실제 형태·해소 경로 참조 |
| `접속1교_실측정리.md` §1~§8 | 검산 동반 치수 정본 | readings 표본 대조의 정답 |

## 2. 확정된 결정

| # | 결정 | 사유 |
|---|---|---|
| D1 | **M2 분해**: M2a 판독+크롭 / M2b 카드 UI | 사용자 선택. 시범→게이트→확산 리듬 유지 |
| D2 | **LLM = Anthropic API 직접** (`anthropic` SDK 1.2.0), 구독(Agent SDK) 아님 | 사용자 결정 2026-08-29("그냥 api로 하자"). 플랜 한도와 분리, 비용 가시화 |
| D2a | 아키텍처 §2·§3의 "Claude Agent SDK" 편차 기록 | 시트 판독은 **단발 구조화 호출**이라 대화형 하네스가 과잉. Agent SDK 는 서버 측 워크플로(후속) 후보로 남김 |
| D3 | **3단 파이프라인**: 시트 판독 → 계열 통합 → 적대적 검토 (각 단계 단발 호출) | 원 프로젝트 "5영역 병렬 판독(wf_b4a9a9f2)" 패턴의 제품화. 캐시 가능·재시도 단위 최소·비결정성 최소 |
| D4 | 모델: 판독·통합 `claude-sonnet-5`, 검토 `claude-fable-5` | 아키텍처 §2 정본 그대로 |
| D5 | **판독 캐시** — `(입력 sha, 프롬프트 버전, 모델)` 키로 결과 저장, 동일하면 무호출 | 재실행 비용 ~$0. 개발 중 수십 회 재실행이 전제 |
| D6 | **시범 = B계열(슬래브 3장 6페이지) → 사용자 승인 게이트 → 전 계열 확산** | 지식베이스 §5. 게이트가 프롬프트·스키마 조정의 마지막 저비용 지점 |
| D7 | Batch API 는 후순위 | 캐시가 재실행을 없애 50% 할인 실익이 완주 2~3회분. 확산 재실행이 잦아지면 도입 |
| D8 | 크롭 좌표는 **용지 mm** 로 받는다 (LLM 출력) → px 변환은 결정론 | sheet_text 가 mm 좌표라 LLM 이 근거 좌표를 mm 로 아는 것이 자연스럽다. px 변환은 M1 `SheetFrame` 재사용 |

### 2-1. API 구성 (실측 확정, 2026-08-30)

- 키: identity-linked(개인)·모든 워크스페이스 범위 → **요청마다 `anthropic-workspace-id`
  헤더 필수**. SDK 의 `ANTHROPIC_WORKSPACE_ID` env 자동 인식은 api_key 경로에서
  동작하지 않음을 실측 — **`Anthropic(default_headers={"anthropic-workspace-id": ws})`
  로 명시**한다.
- `.env`: `ANTHROPIC_API_KEY` + `ANTHROPIC_WORKSPACE_ID=wrkspc_01LQBBtz8JEJyFUwF4KnVGN8`
  (워크스페이스 `model3d-studio`, 콘솔에서 생성 완료). 키는 worker 전용, 커밋 금지.
- 도달 확인 완료: sonnet-5 실호출 성공 (2026-08-30).
- 비용: 완주 ~$8±, 시범 <$1, 재실행 ~$0(D5). 크레딧 $20.28 보유.

## 3. CLI — 기존 `m3d`에 3개 명령 추가

```
m3d read ab1-p4p5 [--region B] [--sheet B01] [--force]   # 1·2단: 판독+계열 통합
m3d review ab1-p4p5 [--region B] [--force]               # 3단: 적대적 검토 반영
m3d crops ab1-p4p5                                       # ambiguity → 크롭 PNG (결정론)
```

- 캐시 히트 시 무호출·무과금. `--force` 는 해당 범위 캐시 무시.
- 실패 수집 패턴(M1 확립): 시트 하나의 실패가 전체를 멈추지 않는다.
- 모든 LLM 호출은 사용량 로그(`data/derived/ab1-p4p5/usage.jsonl`)에
  모델·in/out 토큰·비용 추정·캐시 히트 여부를 적재 — 지출 가시화.

## 4. 3단 파이프라인

### 4-1. 시트 판독 (sonnet-5, 페이지 단위 61회)

- 입력: ① 페이지 PNG 리사이즈(긴 변 1568px) + **표제란·고밀도 영역 타일 2~3장**
  ② sheet_text JSON(용지 mm) ③ 지식베이스 §1~§4 발췌 + 계열별 판독 지침
- 출력(구조화 — `client.messages.parse()` + pydantic):

```
reading: {region, item, value_raw, unit, basis_sheet, basis_page, basis_mm_bbox,
          crosscheck(검산식·결과|null), status: 확정|추정}
ambiguity: {item, sheet, page, mm_bbox, options[2..4]{label, basis}, model_impact}
```

- **근거 없는 수치는 pydantic 에서 반려** → 반려 사유를 붙여 1회 재시도(지식베이스 §8).
  재시도도 실패하면 해당 시트를 실패 수집.

### 4-2. 계열 통합 (sonnet-5, 계열 단위 6회: A·B·C·D·E·F)

- 계열 내 시트 판독 전부를 입력으로 중복 병합, **교차확인**(§3: 중요 치수는 2개 이상
  뷰·시트) — 단일 소스 수치는 `추정` 강등, 상충은 ambiguity 승격("3열 vs 8열"류는
  존 병존 가능성을 선택지로 제시).

### 4-3. 적대적 검토 (fable-5, 계열 단위 6회)

- 통합 SSOT 를 반박 시도: 검산 실패·단일 소스·존 경계 의심·표기 상충.
- 지적은 readings 상태 변경(`검토지적`) 또는 신규 ambiguity 로 반영하고,
  기각된 지적도 사유와 함께 기록(§3: FAIL 지적은 원문 재현으로 재확인 후에만 수용).

## 5. DB — migration `0003_readings.sql`

```
readings:    id, project_id, region, item, value_raw, unit,
             basis_sheet_id, basis_page_id, basis_mm_bbox jsonb,
             crosscheck jsonb, status check(확정|추정|검토지적), round int, created_at
ambiguities: id, project_id, item, sheet_page_id, mm_bbox jsonb not null,
             options jsonb not null,        -- [{label, basis}] 2..4 — 앱에서 pydantic 검증
             model_impact text not null,
             crop_rel_path text,            -- crops 실행 후 채움
             status check(대기|결정|잠정) default 대기, created_at
```

- RLS: M0 패턴 그대로 (authenticated select only).
- `decisions` 는 M2b(카드 UI가 쓰는 테이블). 크롭 PNG 는 assets(kind `png`, role
  `derived`)로 등재 — kind 확장 없음.

## 6. 크롭 생성 (결정론 — M1 자산 회수)

ambiguity `mm_bbox` → `SheetFrame.paper_to_world` → M1 렌더 PNG 픽셀로 변환
(sheet_pages.width_px 사용) → 여백(주변 맥락 40mm) 포함 크롭 + 필요시 2× 확대 저장.
지식베이스 §4 "원본 픽셀 좌표 크롭"의 구현이며, **M1 이 width_px/height_px 를 깔아둔
이유가 여기서 회수된다.** 폴백 시트(A03)는 mm=world 스케일 그대로 변환.

## 7. 진행 순서 (시범→게이트→확산, M2a 안에 포함)

1. **인프라 태스크들**: 0003 적용, 캐시·클라이언트·pydantic 스키마, 크롭 변환 (LLM 무호출)
2. **시범**: `m3d read ab1-p4p5 --region B` → review → crops — B계열 완주 (<$1)
3. **사용자 승인 게이트**: B 결과(readings 표·ambiguities·크롭)를 보고 프롬프트/스키마
   조정 기회. **여기서 멈춰 사용자에게 보고한다.**
4. **확산**: 전 계열 실행 → 합격 판정(§8)

## 8. M2a 완료 기준 (전부 실행 출력·DB 로 확인)

| # | 확인 | 기대 |
|---|---|---|
| 1 | `pytest` | 기존 144 + 신규 전부 통과 (LLM 경로는 녹화 응답 픽스처로) |
| 2 | 시범 B계열 완주 + 게이트 승인 | 사용자 승인 기록 |
| 3 | 전 계열 read·review·crops 완주 | 실패 0, usage.jsonl 에 비용 합계 |
| 4 | **결정 4건(Q1~Q4) 대응 ambiguity 검출** | 4/4 — 항목 매칭은 사람이 판정(같은 요소를 묻는가), 미검출 건은 원인 분석 보고 |
| 5 | readings 표본 대조 | 실측정리 §1~§8에서 뽑은 **표본 20건과 값 일치** — 불일치는 실측정리 오류 가능성 포함 분석(§9-2 사례처럼 실측정리가 틀린 경우도 있다) |
| 6 | 적대적 검토 기록 | 지적 전건이 반영 또는 사유付 기각으로 종결 |
| 7 | 크롭 | ambiguity 전건에 crop_rel_path + 파일 실재 + assets 등재 |
| 8 | 멱등 재실행 | read·review 2회차 캐시 히트로 무과금 완주 |

- 4·5의 수치가 기대와 다르면 **기대값을 고치지 말고** 원인을 판독한다. LLM 출력의
  비결정성이 원인일 수 있는 항목(4)은 프롬프트 조정 → 재실행 이력을 남긴다.

## 9. 범위 밖

| 제외 | 담당 |
|---|---|
| 질문 카드 UI·decisions·SSOT 문서 생성 | M2b |
| 부재·섹션 분류, 커버리지 맵 | M2b 또는 M3 직전 |
| Batch API | 후순위 (D7) |
| Workload Identity Federation | M3+ 배포 워커에서 검토 (키 없는 인증) |
| 뷰 크롭(제목 기반 분할) | 불요 — ambiguity mm_bbox 가 대체 |
| 사진 대조([1]의 사진 입력) | M3+ |

## 10. 리스크

| 리스크 | 대응 |
|---|---|
| LLM 출력 비결정성으로 합격 기준(Q1~Q4) 재현 흔들림 | 온도 낮춤 + 구조화 출력 + 프롬프트 버전 관리(캐시 키에 포함) + 게이트에서 조정 |
| 8000px→1568px 리사이즈로 미세 치수 소실 | 표제란·고밀도 타일 동반 + sheet_text(무손실 텍스트)가 1차 소스, 이미지는 배치·형상 확인용 (원 교훈: "기준 소스는 sheet.png + sheet_text") |
| 대형 sheet_text(A03 6,628행 ≈ 수십 k 토큰) | 컨텍스트 1M(sonnet-5)로 수용 가능. 초과 시 계열 지침에 따라 y-밴드 분할 |
| 과금 폭주 | 캐시 + usage.jsonl 실시간 합계 + 시범 게이트 + 호출당 max_tokens 캡 |
| API 장애·429 | SDK 기본 재시도(2회) + 실패 수집·재실행 멱등 |

## 11. 사용자 선행 작업

**완료됨** (2026-08-30): API 키 발급·`.env` 기입, 워크스페이스 생성·ID 기입, 도달 확인.
M2a 실행 전 남은 선행 작업 없음. 시범 게이트(§7-3)에서 승인 1회 필요.
