# M3 설계 — P4~P5 정밀 모델 재현: ModelSpec · 결정론 빌더 · 3중 검증 · 참조 대조 (아키텍처 [6][7])

작성 2026-09-05. 사용자 승인: 범위 "전체 재현(참조 v2 수준)", 접근 A(결정론 빌더 + ModelSpec 분리, LLM 호출 없음), 이 세션에서 직접 구현.
선행: M2a(판독 282·애매성 63), M2b(decisions·`m3d ssot` → `ssot.json` v2). 참조(읽기 전용): `D:\Projects\Inspection\mbi_app_v2\models_3d\ab1\{SPEC_v2.md, build_ab1_p4p5_v2.py, measure_ab1_p4p5_v2.py, render_ab1_p4p5.py, AB1_P4P5_v2.glb, measure_ab1_p4p5_v2.json, renders/}`.

## 1. 목표와 합격 기준 (v0 = 아키텍처 §5 M3)

접속1교 P4~P5 를 **서비스 파이프라인 산출물(SSOT+결정)만으로** 파라미터화해 3D 모델(GLB)을 만들고, 3중 검증(self-check → 독립 재실측 → 렌더)을 거쳐 기존 정답(SPEC_v2·measure v2·renders)과 대조한다.

| # | 기준 | 판정 |
|---|---|---|
| ① | `modelspec.json` 의 파라미터 출처 통계: `ssot`·`decision` 비율과 `default`(참조 차용) 목록을 전건 명시 | 보고(수치) — 차용이 있어도 실격 아님, 은폐만 실격 |
| ② | 빌더 self-check 전건 PASS(H 8점·격벽 26·프레임 25·WG 52·CS 52·리브 존·받침 EL·수밀·노드명 중복 0) | PASS/FAIL |
| ③ | 독립 재실측(`measure.json`) 전건 PASS — 기대값은 modelspec 에서 자체 유도, 허용오차 길이 5mm·개수 0·각도 0.5° | PASS/FAIL |
| ④ | 참조 대조(`compare.json`): 참조 measure v2 의 같은 항목과 대조해 불일치 전건을 나열하고 원인을 사양차/판독차/빌더차 로 분류 | 보고 |
| ⑤ | 렌더 4장(측면 맥락·정면 단면·저면·내부 격실) 실척 정사영 — 참조 렌더와 나란히 육안 대조 | 육안 소견 기록 |
| ⑥ | pytest 전건 통과, LLM 호출 0 | PASS |

## 2. 결정 사항

| # | 결정 | 이유 |
|---|---|---|
| D1 | 빌더는 저장소 안 결정론 파이썬(`worker/src/m3d/model/`). 참조 v2 의 기하 기법·노드 명명·색상·[A1]~[A21] 단순화를 그대로 계승하되 **모든 치수는 ModelSpec 에서 읽는다** | 재현성·무과금. 아키텍처 [6]의 "모델링 에이전트" 는 v0 에서 코드로 대체 |
| D2 | ModelSpec 은 SPEC_v2 §0~§10 의 구조를 필드로 옮긴 Pydantic 모델. 값마다 `source` 를 붙인다: `ssot:<ord>/<item>` · `decision:<ambiguity item>` · `default:SPEC_v2 §n` · `derived:<식>` | 파이프라인이 사양을 얼마나 채웠는지가 성적표(①) |
| D3 | 추출 규칙(`spec_rules.py`)은 SSOT 판독 항목명·값 표기를 정규식으로 해석한다(예 `9@70,000=630,000`, `38(0~6,300) → 26`). 규칙이 못 채운 필드는 `default` 로 채우고 사유를 기록 | 은폐 금지(지식베이스 §5) |
| D4 | 결정 매핑: Q1 형고=내공 → `box.h_is_clear=True`; Q2 슬래브 순두께 → `slab.thickness_is_net=True`; Q3 보도 2,950+방호벽 450 → `slab.walk_width/center_barrier`; Q4 면진 → `bearing.kind='isolation'`. 결정이 없으면 참조와 같은 잠정값 + `default` | SPEC_v2 §0·§12 와 동일한 잠정 처리 |
| D5 | 독립 재실측은 빌더 함수를 import 하지 않는다(자기참조 금지). 기대값은 `modelspec.json` 에서 재유도 | 지식베이스 §6-2 |
| D6 | 참조 대조는 항목 이름을 참조 measure v2 와 맞춰(한글 키 그대로) 자동 비교; 없는 항목은 "비교 불가" | ④ |
| D7 | 시범→게이트→확산: 본체+격벽만 빌드·렌더(시범) → 사용자 승인 → 전 부재 | 지식베이스 §5 |
| D8 | 산출물은 `data/derived/<dataset>/model/`(gitignore): `modelspec.json`, `AB1_P4P5.glb`, `selfcheck.json`, `measure.json`, `renders/*.png`, `compare.json`, `acceptance-m3.md` | Storage 업로드·뷰어는 범위 밖 |

## 3. ModelSpec (요약 — 필드는 계획서에 전체 기재)

`m3d modelspec <dataset>` → `ssot.json`(최신) 을 읽어 `ModelSpec` 생성.

- `coord`: 원점 규약(x 교축직각·y EL−4.871·z STA−4190), P4/P5 받침선 STA·z, 계획고식 계수(18.694, 0.0236, 3400), 강상판 상면 오프셋 0.398, 보도측 부호.
- `box`: 상·하판 폭 4,700, 웹 외면 x, H 등고(4,000/2,800)·포물선 구간(1,250~14,700)·계수, 판두께 존 3종(`[(d0,d1,t)]`), SP04 위치, `h_is_clear`.
- `diaphragm`: 간격 2,800·개수 26, 지점 격벽(38t, 개구 700×700, 문턱 450, 보강재 규격), 일반 격벽(10t, 개구 1,400×1,400, 문턱 450/400, 높이표 5점, 타입 매핑).
- `frame`: 25개 위치 규칙(격벽 사이 1,400)·타입표 7행(상·하 T리브 웹×h, V-STIFF).
- `rib`: 상·하판 존(열수·간격·평강 규격·존 경계), 전이 구간, SP04 분절.
- `hstiff`: 평강 12×150, 상단 1열(560), 하단 2열(0.14H/0.36H, ±25.2 구간).
- `wg`: 26쌍 위치·전장 4,450·플랜지 경사 1.95%·niche R300·knee(3,900,482)·선단 424·스트럿 300×300·28.222°·정착대.
- `cs`: I형 424(웹 400×12·플랜지 300×12)·세그 2,800.
- `slab`: 폭 15,700, 상면 −2.0%, 순두께(250/300/348), 캔틸레버 하면 절선, 보도 2,950·중앙방호벽 450·연단 방호벽 450×330(모따기 30), `thickness_is_net`.
- `sp04`: 외면판 4매 치수.
- `bearing`: x ±1,550, 솔플레이트 1,370 테이퍼 22→54(중앙 38), 본체 337(베이스 825·Ø650), 몰탈 50(900), 블록 1,300×105, 검증 EL P4 20.137/P5 21.789, `kind`.
- `sources`: 필드 경로 → `source` 문자열 dict + 통계.

## 4. 명령과 산출물

| 명령 | 입력 | 출력 |
|---|---|---|
| `m3d modelspec <ds>` | `ssot/ssot.json` | `model/modelspec.json`(값+출처+통계), 콘솔 `spec_sources ssot=n decision=n default=n derived=n` |
| `m3d build <ds> [--pilot]` | `modelspec.json` | `model/AB1_P4P5.glb`(+`--pilot` 는 본체·격벽만 `AB1_P4P5_pilot.glb`), `model/selfcheck.json`, 콘솔 `selfcheck pass=n fail=n` (fail>0 → exit 1) |
| `m3d measure <ds>` | GLB + `modelspec.json` | `model/measure.json`(참조 v2 와 같은 항목명), 콘솔 `measure pass=n fail=n info=n` |
| `m3d render <ds>` | GLB | `model/renders/{side_context,front_section,bottom_iso,interior_cells}.png` |
| `m3d compare-model <ds> --ref <dir>` | `measure.json`, 참조 `measure_ab1_p4p5_v2.json`, 두 GLB | `model/compare.json`(항목별 우리/참조/차이/판정/원인분류 빈칸), 콘솔 `compare match=n mismatch=n na=n` |

## 5. 테스트

- `spec_rules`: 표기 파서(`9@70,000=630,000` → (9, 70000, 630000); `38(0~6,300) → 26(~16,100)` → 존 리스트; `450×330` → (450, 330)), SSOT 픽스처로 필드 추출·출처 표기·default 폴백.
- `geom`: extrude/loft/box_prism 부피·수밀, mirror.
- `builder`: 시범(본체+격벽) 빌드 시 노드 수·이름 규칙·수밀·격벽 z 체인; 전체 빌드 시 부재 수(격벽 26·프레임 25×6·WG 26×2×3·CS 52·받침 4×4).
- `selfcheck`·`measure`: 가짜/소형 GLB 로 PASS·FAIL 판정 경로. `compare`: 항목 매칭·허용오차·비교 불가.
- 실행 증적: 시범 렌더 육안 → 게이트 → 전체 빌드·measure·render·compare 출력과 `acceptance-m3.md`.

## 6. 범위 밖
교각·코핑·기초(맥락 렌더 스텁만), 웹 3D 뷰어, GLB/렌더 Storage 업로드, 사진 대조, 모델링 에이전트(코드 생성), 사장교·타 경간.
