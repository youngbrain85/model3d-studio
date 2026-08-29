# M1 — 변환·정규화 [2] + 카탈로그 대조 [3] 설계 (2026-08-29)

`docs/아키텍처_MCP구성_v0.md` §5의 M1("파이프라인 [2][3]: 변환·카탈로그·표제란 대조를
CLI로")의 확정 설계다.

- 규칙 정본: `docs/모델링규칙_지식베이스_v0.md` §3(도면 판독 프로세스)이 이 설계의 근거다.
- 전제: [M0 완료](2026-08-27-m0-repo-bootstrap-design.md) — DB 시딩됨(sheets 50 전부
  `catalog_status='unverified'`, `*_from_content` NULL), 샘플 112파일 무결.
- 방향 결정(사용자 지시): **외관조사망도(mbi_app_v2) 프로젝트에서 확립한 방식 그대로** —
  추출·분류는 결정론, LLM은 검증 전용.

## 0. M1의 목적

50개 시트의 `*_from_content` 빈칸을 **시트 내부에서 독립적으로 읽어** 채우고, 파일명
유래 값과 기계 대조해 편철 오류 검출이 실제로 작동함을 증명한다(M0가 깔아둔 시험지).
동시에 M2 판독의 입력(고해상 PNG + 구조화 sheet_text)을 파이프라인 산출물로 만든다.

## 1. 사전 조사 결과 (설계 근거 — 전부 실측)

### 1-1. 입력 실측

| 사실 | 실측값 | 함의 |
|---|---|---|
| 통합 PDF 텍스트 레이어 | 61p 중 첫 5p **0자** (이미지 기반, 4000px 축소판) | PyMuPDF 텍스트 추출 무의미. PDF는 PNG로부터 제작된 열람본 |
| DXF 표제란 | 도곽 블록 `CXBLKA1-구조`의 **ATTRIB** — `DI_DRWNO`(도면번호)·`DI_TITLE`·`DI_SUBTITLE`(제목)·`DA_HSCALE`(척도) | **완전 결정론적 판독 가능** — LLM 불요 |
| `DI_DRWNO` == 파일명 | **49/50** (전수 스캔 108초) | 대조 기대값의 근거 |
| 예외 1건 | `C0050302-001`(A03 종평면도): 도곽 블록·도면번호 텍스트 모두 부재 (INSERT 296·TEXT 6,571 전수 확인) | `unreadable` 판정 대상. 원 프로젝트의 `C0050202-001`(사장교 종평면도, 도곽 미검출 → 폴백 렌더)과 동일 계열로 이미 수용된 한계 |
| 제목 표기 | 전각·공백 산재 (`슬 래 브 일 반 도 (4)` / `(접 속 1 교)`) | 대조 전 공백 정규화 필수 |
| 척도 표기 | `H=1:100` / `H=NONE` / 빈 문자열 혼재 | 원문 그대로 저장, 판정에 쓰지 않음 |
| 기존 PNG 61장 | **전부 긴 변 8000px** | 원 파이프라인 `SHEET_PX=8000` 산출물 — 같은 설정으로 렌더하면 직접 회귀 대조 성립 |
| 다페이지 시트 구조 | 2p 시트의 DXF 안에 **도곽 INSERT 2개** (3건 표본 + 1p·도곽부재 각 1건 실측) | 도곽 총합 60 + 폴백 1 = **61페이지** — `page_count` 합 61과 검산 일치. PNG·sheet_text 는 **페이지 단위 61건** |

### 1-2. 계승하는 원 파이프라인 (정본: `mbi_app_v2/assets/drawings_organized/_scripts/render_pipeline.py`, 읽기 전용)

원 프로젝트가 DWG 528장 중 323장을 처리하며 확립·검증한 로직( `_검증보고서.md` 근거):

1. **시트(도곽) 감지**: modelspace의 `CXBLK*` INSERT → 블록 정의 bbox(ATTDEF/TEXT 제외)
   ≥200mm(용지)만 도곽 인정 → 삽입점·스케일·회전(90° 단위만)으로 world rect 산출.
   **미검출 시 전체 범위 폴백 렌더**(fallback 플래그).
2. **렌더**: ezdxf drawing add-on(matplotlib Agg), 흰 배경 + `set_colors("#FFFFFF")` —
   **ACI-7 가드**(원 프로젝트에서 배경 미지정 시 흑백 자동색이 흰색으로 그려져 238파일
   텍스트 비가시화된 실사고의 해법). HATCH/SOLID/WIPEOUT **선행 드로우**(텍스트 덮임
   방지). 긴 변 8000px. malgun.ttf 강제 + 깨진 style 참조 → Standard 수리.
   `ezdxf.readfile` 실패 시 `recover` 폴백. 드로우 실패 시 엔티티 개별 재시도(PARTIAL).
3. **밝은 색 어둡게**: ACI {2,3,4,6,8,9} → 흰 배경 가독 RGB (DARKEN 맵 그대로 계승).
4. **sheet_text**: TEXT/MTEXT + DIMENSION 지오메트리 블록 내 텍스트를 **용지좌표 mm·
   글자높이 mm·종류(TEXT/DIM)** 와 함께 덤프. `%%c` 등 제어코드 제거.
   원 교훈: "치수 판독의 기준 소스는 항상 sheet.png + sheet_text".
5. **LLM의 자리**: 원 프로젝트는 추출·분류를 전부 결정론(ATTRIB·정규식 규칙)으로 하고,
   Opus 검증 에이전트 38개는 **렌더 육안 검토에만** 썼다. M1도 같은 역할 분리를 따른다.

### 1-3. 버리는 것 (원 파이프라인 중 M1 밖)

- 뷰 크롭(제목 기반 시트 분할) — M2 판독 직전에 도입
- 부재·섹션별 분류(정규식 규칙 테이블)·커버리지 맵 — M2
- LLM 육안 검증 게이트 — M2 (M1 검증은 기존 PNG 대조로 결정론적으로 대체)
- DWG→DXF 변환(accoreconsole) — 샘플이 이미 DXF 보유. 실서비스의 DWG 입로는 후순위

## 2. 확정된 결정

| # | 결정 | 사유 |
|---|---|---|
| D1 | **추출은 결정론, LLM은 검증 전용** | 사용자 지시 "외관조사망도 방식 그대로". 49/50이 ATTRIB 로 끝나고 비용 0 |
| D2 | **범위 = convert + catalog** (뷰 크롭·분류·LLM 게이트 제외) | 사용자 선택. M1이 작을수록 시범→승인→확산 리듬 유지 |
| D3 | **원 로직을 모듈로 이식·정리** (vendored 복사 아님) | 430줄 단일 함수는 테스트 불가. 검증된 교훈(ACI-7 등)은 코드째 계승하되 책임별 분리 |
| D4 | **판정 기준은 도면번호 하나** — 제목·척도는 저장+노트 | 지식베이스 §3 "도면번호를 시트 내부 텍스트와 기계 대조". 제목은 표기 편차(공백·차수 접미)가 커서 판정 기준으로 부적합 |
| D5 | **PDF 변환 경로는 M1 제외** | 이 세트의 PDF는 PNG로부터 만든 4000px 열람본 — 렌더해봤자 열화 사본. 래스터 입력 일반화는 비전 판독(M2+)과 함께 |
| D6 | **sheet_text는 JSON** (원 .txt 개선) | M2 판독 에이전트의 구조화 입력. 스키마 강제 가능 |

## 3. CLI — 기존 `m3d`에 2개 명령 추가

```
m3d convert ab1-p4p5      # [2] DXF 50 → 도곽 감지 → PNG 렌더 + sheet_text JSON
                          #     → sheet_pages.width_px/height_px 갱신
                          #     → derived assets 등재 (png·text)
m3d catalog ab1-p4p5      # [3] 표제란 ATTRIB → sheets.*_from_content 채움
                          #     → drawing_no 기계 대조 → catalog_status 판정
                          #     → 대조 리포트 (CLI 표 + JSON)
```

- 둘 다 **멱등**: 산출물 sha256이 DB 등재값과 같으면 스킵. `--force` 로 재생성.
- `convert`가 실패한 시트가 있어도 나머지는 계속 처리하고 실패 목록을 마지막에 보고
  (전체 중단은 안 한다 — 원 파이프라인의 PARTIAL 정신).
- 산출물 위치: `data/derived/ab1-p4p5/{png,text}/` (**gitignore** — 재생성 가능물).

## 4. 모듈 구조

```
worker/src/m3d/
├─ convert/
│  ├─ __init__.py
│  ├─ frames.py        # 도곽 감지 (§1-2의 1) — 순수: DXF doc → list[SheetFrame]
│  ├─ render.py        # 렌더 (§1-2의 2·3) — SheetFrame → PNG (ACI-7 가드 포함)
│  ├─ sheet_text.py    # 텍스트 추출 (§1-2의 4) — SheetFrame → SheetText(JSON 직렬화)
│  └─ run.py           # convert 오케스트레이션: 파일 순회·DB 반영·멱등·실패 수집
├─ catalog/
│  ├─ __init__.py
│  ├─ titleblock.py    # ATTRIB 추출 — DXF doc → TitleBlock | None
│  ├─ reconcile.py     # 대조 판정 — 순수: (TitleBlock|None, SheetRow) → Verdict
│  └─ run.py           # catalog 오케스트레이션: DB 갱신·리포트
└─ compare.py          # 회귀 대조 — 지각 해시(dHash, PIL+numpy 자체 구현) 쌍 비교
```

- `frames.py`·`reconcile.py`·`compare.py`는 **순수 로직** — 단위테스트 대상.
- 좌표 변환(world↔용지 mm)은 `frames.py`의 `SheetFrame` 메서드로 —
  sheet_text 좌표와 M2 크롭이 같은 변환을 쓴다.

## 5. sheet_text JSON 스키마 (M2 판독의 입력 계약)

```json
{
  "schema": 1,
  "drawing_no": "C0050304-030",
  "page_no": 1,
  "paper_mm": [1189.0, 841.0],
  "scale": 200.0,
  "rotation_deg": 0,
  "fallback": false,
  "texts": [
    {"x_mm": 102.3, "y_mm": 780.1, "h_mm": 5.0, "kind": "TEXT", "text": "S=1:100"},
    {"x_mm": 210.0, "y_mm": 455.2, "h_mm": 3.5, "kind": "DIM",  "text": "2,800"}
  ]
}
```

- `fallback=true`(도곽 미검출)면 `paper_mm`은 world bbox 크기, `scale`은 null.
- 좌표는 **용지 mm** — 지식베이스 §4의 "원본 픽셀 좌표" 크롭은 M2에서
  `SheetFrame` 변환(mm→px)으로 유도한다. PNG 픽셀과 mm의 환산 계수는
  JSON의 `paper_mm`과 PNG 크기에서 나온다. 회전 시트(rotation_deg 90/270)는 PNG 가
  world 방향이므로 paper_mm 축이 **전치**된다 — M2 크롭은 SheetFrame.paper_to_world
  를 쓰면 이 문제가 없다(현 데이터셋 61페이지는 전부 rotation 0).

## 6. 대조 판정 (`reconcile.py`) — 지식베이스 §3의 구현

| 조건 | catalog_status | 비고 |
|---|---|---|
| `DI_DRWNO` 가진 도곽 0개 | `unreadable` | 예상 1건 (`C0050302-001`) |
| **모든 도곽**의 `DI_DRWNO` == `drawing_no_from_filename` | `match` | 예상 49건 |
| 하나라도 다름 | `mismatch` | 예상 0건 — 나오면 편철 오류 검출 성공 사례 |

다페이지 시트(도곽 2개)는 표제란도 페이지마다 있으므로 **전 도곽을 검사**한다 —
페이지 간 도면번호 불일치도 편철 오류의 일종이다.

- 제목: `DI_TITLE + DI_SUBTITLE`을 공백(전각 포함) 제거 정규화 후
  `title_from_filename` 정규화본과 **포함 관계** 확인. 불일치는 판정에 반영하지 않고
  리포트의 `notes` 에만 남긴다(파일명에는 차수 접미 `(7차변경)` 등이 더 붙는 것이 정상).
- 저장: `drawing_no_from_content`·`title_from_content`(TITLE+SUB 원문 결합)·
  `scale_from_content`(`DA_HSCALE` 원문) — **원문 그대로**, 정규화본을 저장하지 않는다
  (지식베이스 §2: 원문값과 파생값 구분).
- `unreadable`의 `*_from_content`는 NULL 유지.

## 7. DB 변경 — `0002_convert.sql`

```sql
-- assets.kind 에 'text' 추가 (sheet_text JSON 등재용)
alter table assets drop constraint assets_kind_check;
alter table assets add constraint assets_kind_check
  check (kind in ('dxf','pdf','png','photo','text'));
```

- 신규 테이블 없음. M0의 `*_from_content`·`catalog_status`·`width_px/height_px`가
  정확히 이 마일스톤을 위해 깔아둔 빈칸이다.
- `sheet_pages.width_px/height_px`는 **M1 신규 렌더 기준**으로 채운다(파이프라인
  일관성 — 이후 크롭의 기준은 파이프라인 산출 PNG). 기존 샘플 PNG는 회귀 대조
  전용으로 남는다.
- 신규 렌더 PNG·sheet_text JSON은 assets에 `role='derived'`로 등재
  (`rel_path`가 `data/derived/...`라 기존 샘플 등재와 충돌 없음 —
  `unique(project_id, rel_path)`).

## 8. 검증 (3중)

1. **단위테스트** (TDD 대상 — 순수 로직):
   - `frames.py`: 합성 DXF(도곽 1개·2개·회전 90°·도곽 없음)로 감지·폴백·좌표 변환 왕복
   - `reconcile.py`: match/mismatch/unreadable 3분기 + 제목 정규화(전각 공백) 포함 판정
   - `compare.py`: 동일 이미지 거리 0, 1픽셀 변조 저거리, 다른 시트 고거리
   - `sheet_text` 스키마: 직렬화 왕복 + fallback 시 scale null
   - 실 DXF 픽스처: `C0050304-030`(정상)·`C0050302-001`(도곽 부재) 2장으로 통합 확인
     — 이 2장은 이미 `data/samples`에 있으므로 테스트는 존재할 때만 실행(skipif)
2. **회귀 대조** (M1의 핵심 증명): 신규 렌더 61장 vs 기존 PNG 61장 지각 해시(dHash)
   쌍 비교. **임계값은 구현 단계에서 대표 5장으로 실측해 확정**하고 근거를 기록한다.
   임계 초과 건은 나란히 저장해 육안 보고 — 0건이 목표이나 matplotlib 버전 차이로
   인한 미세 편차는 육안 승인으로 수용 가능.
3. **DB 검증**: `m3d db check` 확장 — catalog_status 분포·`*_from_content` 채움 수·
   `sheet_pages` 크기 채움률 출력.

## 9. M1 완료 기준 (전부 실행 출력으로 확인)

| # | 명령 | 기대 |
|---|---|---|
| 1 | `m3d convert ab1-p4p5` | DXF 50건 처리(폴백 1 포함), 페이지 단위 PNG 61장 + sheet_text 61건 생성, 실패 0 |
| 2 | (convert 내·후) 회귀 대조 | 61쌍 지각 대조 — 임계 초과 0건 또는 초과 건 육안 승인 |
| 3 | `m3d catalog ab1-p4p5` | **49 match / 0 mismatch / 1 unreadable** |
| 4 | `m3d db check` | `*_from_content` 49건 채움 · unreadable 1건 NULL 유지 · sheet_pages 61행 크기 채움 |
| 5 | `pytest` | 기존 91 + 신규 전부 통과 |
| 6 | 멱등 재실행 | convert·catalog 2회차가 스킵으로 완주 |

- 3의 결과가 49/0/1과 다르면 **기대값을 고치지 말고** 원인을 판독한다 — mismatch가
  나오면 그것이 편철 오류 검출의 실증이므로 실패가 아니라 보고 대상이다.

## 10. 범위 밖 (명시적 제외)

| 제외 항목 | 담당 | 사유 |
|---|---|---|
| 뷰 크롭·부재 분류·커버리지 맵 | M2 | D2 |
| LLM 육안 검증 게이트 | M2 | D1 — M1 검증은 기존 PNG 대조로 결정론화 |
| PDF→이미지 변환 경로 | M2+ | D5 |
| DWG→DXF 변환(accoreconsole) | 후순위 | 샘플이 DXF 보유 |
| Supabase Storage 업로드 | 후순위 | 로컬 파이프라인 우선 (M0 결정 계승) |
| `C0050302-001` 표제란의 비전 판독 | M2 | unreadable 1건은 M1에선 상태로만 기록 |

## 11. 리스크

| 리스크 | 대응 |
|---|---|
| 렌더 61장 소요 시간 (원 로그상 장당 수십 초~수 분) | 멱등 스킵 + 실패 수집으로 재시도 비용 최소화. 병렬화는 필요 시 계획 단계에서 판단 |
| matplotlib/ezdxf 버전 차이로 기존 PNG와 편차 | 지각 해시 임계 실측 + 초과 건 육안 승인 절차 (§8-2) |
| 도곽 블록명이 `CXBLKA1-구조` 외 변형 존재 | 원 로직대로 `CXBLK*` + bbox ≥200mm 휴리스틱 — 이름 완전일치에 걸지 않는다 |
| ATTRIB 태그가 시트별로 다를 가능성 | 전수 스캔에서 `DI_DRWNO` 49건 확인 완료. 나머지 태그는 없으면 NULL 저장 |
| 8000px 렌더의 메모리 (PIL 한계) | 원 로직의 `Image.MAX_IMAGE_PIXELS=None` 계승 |
