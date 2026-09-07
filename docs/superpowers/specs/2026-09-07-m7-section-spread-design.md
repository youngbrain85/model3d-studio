# M7 설계 — 8섹션 확산: 격벽 외 전 부재를 LLM 이 만든다

작성 2026-09-07. M6 결과(`data/derived/ab1-p4p5/model/acceptance-m6.md`): 격벽 1섹션이 4잡 14시도 $1.78 로 PASS(b9).
남은 문제는 커버리지다 — 10섹션 중 9섹션을 아직 결정론 빌더가 만든다. 사용자 결정: 범위 "BOX 를 뺀 8섹션 전부, 상한 $25", 실행 "웹 일괄 큐 + 워커 순차 처리".

## 0. 지금 상태와 확산 난이도

| 섹션 | 노드 | 참조 코드 | 판독 근거 | 섹션 self-check | 특이점 |
|---|---|---|---|---|---|
| SP04 이음판 | 4 | 24줄 | 4건 | 일반뿐 | 가장 단순, 4매 평판 |
| HST 수평보강재 | 10 | 24줄 | **0건** | 일반뿐 | 크롭 근거 없음, 존 로프트 |
| SLAB 슬래브·방호벽 | 4 | 43줄 | 13건 | 일반뿐 | 콘크리트 색, 캔틸레버 단면 |
| BRG 받침 | 16 | 75줄 | 33건 | 8개 | 부품 4종 × 4기, EL 검산 |
| FRM 개방 프레임 | 150 | 36줄 | 6건 | 4개 | 6부재 × 25, 타입 표 |
| RIB 종리브 | 93 | 50줄 | 4건 | 일반뿐 | 존 분할 로프트, 열·전이 |
| CS 외측빔 | 52 | 21줄 | 12건 | 4개 | WG 기하에서 위치 유도 |
| WG 외측가로보 | 156 | 106줄 | 9건 | 4개 | 절선·니치 원호·스트럿 각도 |

(범위 밖) BOX 본체 4노드 — `ctx` 가 본체 프로파일 자체라 같은 방식으로 채점할 수 없다.

세 가지 결함이 확산을 막는다.
1. `ctx`(D2, M5)가 본체 기하만 준다. WG·SLAB 은 강상판 상면·크라운이, BRG 는 판두께가, RIB·HST 는 존 분절 로프트가 필요하다.
2. 섹션별 정보(근거 정규식·렌더 뷰·역할 라벨·노드명)가 코드 세 곳에 흩어져 DIA 만 채워져 있다.
3. 스펙 `description`(M6 D1, 성공의 최대 요인)이 격벽·받침 x 에만 있다. 나머지 9개 하위 모델 약 70필드가 비어 있다.

## 1. 목표와 합격 기준

웹 섹션 목록에서 여러 섹션을 골라 한 번에 큐에 넣으면 워커가 순차로 LLM 모델링·채점·업로드하고, 마지막에 **본체만 정답인 결합 모델**(10섹션 중 9섹션이 LLM 산출)을 검증한다.

| # | 기준 | 판정 |
|---|---|---|
| ① | 8섹션 중 **6 이상**이 채점 PASS(노드명 일치, bbox ≤ 5 mm + 반올림 여유, 섹션·결합 self-check·재실측 fail 0) | 채점 JSON |
| ② | 웹에서 N섹션 선택 → `jobs` N행 → `m3d worker --poll --drain` 이 순차 처리 → 잡 패널에 대기·진행·완료가 보인다 | 육안 + DB |
| ③ | 전집 결합 빌드(BOX 정답 + 에이전트 9섹션: M6 격벽 + M7 통과분) self-check fail 0·재실측 fail 0·렌더 4장, 웹 뷰어 표시 | 판정 JSON + 육안 |
| ④ | M7 지출 ≤ **$25**(stage `model-agent` 증분; 누적 상한 $28.17 = 기존 $3.17 + 25) | 원장 |
| ⑤ | pytest·vitest·`tsc -b --noEmit` 전건 | PASS |

①에서 6에 못 미치면 **실패한 섹션을 그대로 보고**하고(코드·채점·렌더는 화면에 남는다) ②③④⑤로 M7 을 판정한다. ③은 통과한 섹션만으로 구성한다 — 실패 섹션은 정답 빌더 산출로 채우고 그 사실을 판정서에 적는다.

## 2. 결정 사항

| # | 결정 | 이유 |
|---|---|---|
| D1 | `sandbox.BoxContext` → `SectionContext`: 기존(`x_web·z_p4·z_p5·y_web_top·y_web_bot·h_box·t_web·COL_STEEL·INS·geom`)에 `y_deck_top(z)`·`y_crown(z)`·`y_bot_out(z)`·`t_top(z)`·`t_bot(z)`·`el_road(z)`·`span`·`zone_loft(z0, z1, poly_fn)`·`COL_CONC`·`COL_BRG`·`COL_SOLE` 를 더한다. 격벽 전용 도우미(`dia_z`·`dia_half_w`)는 계속 주지 않는다 | 본체는 전 섹션의 주어진 조건이다(M5 D2 와 같은 논리). BOX 를 범위에서 뺐으므로 답을 주는 것이 아니다. `zone_loft` 는 `breaks·para_ranges·checks` 를 묶은 바인딩 메서드로 준다 — 세 목록을 날로 주면 오용이 쉽다 |
| D2 | 섹션 메타를 `agent/sections_meta.py` 한 곳에: `SectionMeta(code, label, pattern, rep_nodes, roles, node_names)`. `crops.SECTION_PATTERNS`·`critique.VIEWS`·`score.node_role`·웹 `AGENT_SECTIONS` 가 여기서 나온다 | 섹션 추가 = 표 한 줄. 다음 교량에도 같은 구조로 옮긴다 |
| D3 | 노드명 **전체 목록**을 계약에 싣는다(참조 섹션 GLB 에서 생성, 정렬·쉼표 구분, 최대 156개 ≈ 3 KB). "이 목록과 정확히 같은 키를 만들라"고 명시 | 채점이 노드 집합 일치를 요구한다 — 이름 없이는 어떤 섹션도 통과할 수 없다. 노드명은 객체 DB 연결 키 규약(KB §5)이지 형상이 아니다. 부재 개수가 드러나는 것은 사용자 승인 아래 감수한다 |
| D4 | `ModelSpec` 의 9개 하위 모델(coord·box·frame·rib·hstiff·wg·cs·slab·sp04·bearing) 전 필드에 `description`. 형식은 M6: 튜플은 성분마다 뻗는 축 `[x]·[y]·[z]`, 배치 규칙, 참조 단순화 번호 | M6 실증에서 doc 한 줄이 326 mm → 8 mm 를 만들었다. 확산의 최대 지렛대 |
| D5 | 자기 렌더를 메타에서 생성: ① 대표 노드 정면 아이소 ② 대표 노드 측면(체인선) ③ **섹션 전체 아이소**(전 노드). DIA 의 세 번째 뷰도 전체 아이소로 바꾼다 | M6 잡 4 시도 1 의 17.8 m 배치 오류는 전체 뷰였으면 즉시 보였다. 개수·간격·좌우 오류는 전체 뷰에서만 드러난다 |
| D6 | 웹: 섹션 행에 선택 체크(뷰어 표시 체크와 별개, 보라색), 헤더에 "선택 N개 LLM 모델링" 버튼 → 모달(요청·예산 공통) → `jobs` N행 insert. 워커: `m3d worker --poll [--drain]`, `--drain` 은 큐가 비면 종료 | 사용자 결정(일괄 큐). `--drain` 이 있어야 배치 실행이 스스로 끝난다 |
| D7 | 채점·합격 규칙은 M6 그대로(`score_section`, `within_bbox_tol`). 섹션별 예외 없음 | 규칙을 섹션마다 손보기 시작하면 채점이 의미를 잃는다 |
| D8 | 전집 결합: `m3d agent-assemble [--out-dir]` — 섹션마다 **가장 좋은 에이전트 산출**(통과분 우선, 없으면 정답 빌더)을 골라 결합 빌드를 만들고 self-check·재실측·렌더 후 `publish-model --kind agent` | ③의 산출물. 결정론 작업이라 무과금이고 LLM 이 필요 없다 |
| D9 | HST 는 판독 근거 0건이다. 크롭 없이 스펙·규칙만으로 시도한다. 실패 원인이 정보 부족이면 판독 확장이 아니라 `hstiff` 필드 `description` 으로 메운다 | 판독 재실행은 과금이고 범위 밖 |
| D10 | 섹션당 잡 ≤ 3, 잡당 시도 ≤ 4(현행). 3잡 후에도 실패면 그 섹션은 실패로 확정하고 다음 섹션으로 넘어간다. 실패 잡을 워커가 자동 재요청하지 않는다 | 예산 보호. M6 에서 잡 1개는 $0.25~0.5 |
| D11 | 실행 순서 SP04 → HST → SLAB → BRG → FRM → RIB → CS → WG. 첫 배치는 SP04·HST·SLAB·BRG 4섹션을 한 큐에 넣어 ②를 실증하고, 결과를 보고 다음 배치를 만든다 | 쉬운 것으로 인프라를 먼저 검증한다. 배치 사이에 doc 을 고칠 여지를 남긴다 |
| D12 | 모델 `claude-sonnet-5`·thinking 비활성·max_tokens 16,000 유지 | 변수를 정보에만 두어야 원인이 보인다(M6 D6) |

## 3. 변경 명세

### 3.1 `agent/sections_meta.py` (신규)

```python
@dataclass(frozen=True)
class SectionMeta:
    code: str                  # 'FRM'
    label: str                 # '개방 프레임'
    pattern: str | None        # 판독 근거 정규식 (None = 크롭 없음)
    rep_nodes: tuple[str, ...] # 대표 노드(렌더 근접 뷰) 1~2개
    roles: tuple[tuple[str, str], ...]  # (노드명 정규식, 역할 라벨) — 앞에서부터 첫 일치
    spec_keys: tuple[str, ...] # 프롬프트 스펙 발췌에 넣을 ModelSpec 하위 모델 (공통 coord·box 는 항상 포함)

SECTIONS: dict[str, SectionMeta]     # DIA 포함 9개 (BOX 제외)
def meta(code) -> SectionMeta
def node_names(ref_dir, segment, code) -> list[str]   # 참조 섹션 GLB → 정렬된 노드명
def role_of(code, node) -> str | None
```

섹션별 값(정규식은 M2a 판독 항목명 기준, 조사 결과 근거 건수를 괄호에):

| code | pattern | rep_nodes | roles 예 |
|---|---|---|---|
| DIA | `다이아프램\|격벽\|DIAP\|개구\|문턱\|잭업\|수직보강` (12) | `AB1_S5_DIA01` | 01·26 → 지점 격벽, 그 외 → 일반 격벽 |
| SP04 | `이음판\|SP-?04\|현장이음\|스플라이스` (4) | `AB1_S5_SP04_TF` | `_TF` 상면판, `_BF` 하면판, `_WEB_[LR]` 복부판 |
| HST | `None` (0) | `AB1_S5_HST_UP_L` | `_UP_` 상단열, `_LO1_` 하단 1열, `_LO2_` 하단 2열 |
| SLAB | `슬래브\|바닥판\|방호벽\|포장\|콘크리트` (13) | `AB1_S5_SLAB` | `SLAB` 바닥판, `BARRIER_[LR]` 연단 방호벽, `BARRIER_CTR` 중앙 방호벽 |
| BRG | `받침\|솔플레이트\|무수축\|모르타르\|교좌` (33) | `AB1_S5_BRG_P4_1_BODY` | `_SOLE` 솔플레이트, `_BODY` 받침 본체, `_MORTAR` 무수축 모르타르, `_BLOCK` 받침 블록 |
| FRM | `프레임\|개방\|가로보\|수직보강재\|FRAME\|브레이싱` (6) | `AB1_S5_FRM01_TRW` | `_TRW` 상부 웹, `_TRF` 상부 플랜지, `_BRW` 하부 웹, `_BRF` 하부 플랜지, `_VS[LR]` 수직보강재 |
| RIB | `종리브\|리브\|U-?리브\|RIB` (4) | `AB1_S5_RIB_TP4_1` | `_T` 상판 리브, `_B` 하판 리브 (접두 3~4자로 존 구분) |
| CS | `외측빔\|연단\|CS\|가로보 선단` (12) | `AB1_S5_CS096L` | `L` 좌(보도측), `R` 우 |
| WG | `외측가로보\|가로보\|캔틸레버\|스트럿\|니치\|WG` (9) | `AB1_S5_WG096L` | 접미 없음 → 본체, `_BR` 브래킷, `_ST` 스트럿 |

`spec_keys`: DIA `diaphragm`+`bearing` / SP04 `sp04` / HST `hstiff`+`diaphragm`(패널 절선) / SLAB `slab` / BRG `bearing` / FRM `frame`+`diaphragm`(체인 간격) / RIB `rib` / CS `cs`+`wg` / WG `wg`+`slab`. 공통 `coord`·`box` 는 항상 붙는다.


`crops.SECTION_PATTERNS` 는 이 표를 읽는 얇은 래퍼로 남기고, `pattern is None` 이면 `fetch_evidence` 를 건너뛰고 빈 목록을 준다(HST).

### 3.2 `sandbox.SectionContext` (D1)

`BoxContext` 를 개명·확장한다. 추가 항목은 전부 `Builder` 의 기존 메서드·상수를 그대로 묶는다.

```python
class SectionContext:
    def __init__(self, b: Builder):
        ...M5 항목(x_web·z_p4·z_p5·y_web_top·y_web_bot·h_box·t_web·COL_STEEL·INS·geom) 그대로...
        self.span = b.SPAN
        self.el_road, self.y_deck_top, self.y_crown, self.y_bot_out = b.el_road, b.y_deck_top, b.y_crown, b.y_bot_out
        self.t_top, self.t_bot = b.t_top, b.t_bot
        self.COL_CONC, self.COL_BRG, self.COL_SOLE = list(COL_CONC), list(COL_BRG), list(COL_SOLE)
        self._b = b
    def zone_loft(self, z0, z1, poly_fn):
        """판두께 전이점에서 분절해 로프트한다(전이 계단면 캡 포함)."""
        return self._b._zone_loft(z0, z1, poly_fn)
```

`_b` 는 밑줄 이름이라 계약에 싣지 않는다. 러너의 노드명 검증(`^AB1_S5_[A-Z0-9_]+$`)과 수밀·컬러 검사는 그대로 두되, 컬러 검사는 네 색 중 무엇이든 통과한다(현행 `visual.kind` 검사가 이미 색을 가리지 않는다).

### 3.3 프롬프트 (`agent/context.py`)

- `CTX_DOC` 에 새 항목을 축·의미와 함께 적는다(예: `ctx.y_deck_top(z)`: 강상판 상면 y — 슬래브·이음판·받침이 여기서 유도한다).
- `CODE_CONTRACT` 의 격벽 전용 문장 3개(노드명 규칙·반복 판 두께·지점 격벽 보강재)를 **섹션 무관 문장 + 섹션별 블록**으로 나눈다. 섹션별 블록은 `sections_meta` 에서 만든다:

```
## 이 섹션의 노드 (정확히 이 이름들만, 빠짐없이)
AB1_S5_FRM01_BRF, AB1_S5_FRM01_BRW, … (150개)
역할: _TRW 상부 웹 / _TRF 상부 플랜지 / …
```

- 반복 판·보강재 규칙(M6 에서 격벽으로 검증된 문장)은 일반 문장으로 남긴다 — 프레임·리브에도 그대로 맞는다.
- `spec_excerpt` 의 `SPEC_SECTIONS` 를 섹션별로 고른다: 공통(`coord`·`box`) + 그 섹션의 하위 모델 + 필요한 이웃(CS 는 `wg`, BRG 는 `bearing`+`box`). 표는 `sections_meta` 에 `spec_keys` 로 둔다.

### 3.4 자기 렌더 (`agent/critique.py`, D5)

`VIEWS` 상수를 없애고 메타에서 생성한다.

```python
def views_for(code) -> list[dict]:
    rep = meta(code).rep_nodes
    return [
        {"name": "rep_front", "nodes": rep, "eye": (0.3, 0.2, 1.0), "size": (8, 6), ...},
        {"name": "rep_side",  "nodes": rep, "eye": (1, 0, 0), "size": (5, 10), "chain": "z_p4", ...},
        {"name": "section_all", "nodes": None, "eye": (0.7, 0.45, 0.85), "size": (10, 6), ...},  # None = 전 노드
    ]
```

캡션은 섹션 라벨을 넣어 만든다("이전 시도 개방 프레임 전체 — +x+y+z 에서 본 배치·개수·좌우").

### 3.5 채점 피드백 (`agent/score.py`)

`node_role` 을 `sections_meta.role_of(code, node)` 로 바꾼다. 나머지(축별 델타·힌트·`within_bbox_tol`)는 그대로.

### 3.6 워커·웹 (D6)

- `cli.worker` 에 `--drain` 옵션. `worker.serve(cfg, poll, once, drain)`: `drain` 이면 큐가 비었을 때 `return`.
- 웹 `lib/jobs.ts`: `AGENT_SECTIONS` 를 9섹션으로. `jobPayloads(sectionKeys, …) -> JobInsert[]`, `createJobs(supabase, rows) -> JobRow[]`.
- `routes/Model.tsx`: 섹션 행에 선택 체크(`picked` 상태), 헤더에 "선택 N개 LLM 모델링" 버튼, 모달은 요청·예산을 공통 적용하고 잡 N개를 만든다. 섹션 하나짜리 기존 버튼은 유지한다.

### 3.7 전집 결합 (`model/assemble_agent.py` + `cli.agent_assemble`, D8)

```python
def pick_sources(cfg, dataset, *, ref_dir) -> dict[str, dict]   # code → {glb, source, job_id, pass}
def run_agent_assemble(cfg, dataset, *, out_dir, publish) -> dict
```

`model/agent/<job>/agent/score.json` 을 훑어 섹션마다 최신 PASS 산출을 고르고(없으면 정답 빌더), 결합 GLB·`selfcheck*.json`·`measure.json`·렌더 4장·`build.json(kind='agent')` 을 만들어 `run_publish_model(kind='agent', force=True)` 로 올린다. `build_sections.source` 는 섹션마다 실제 출처를 쓴다.

## 4. 테스트

| 파일 | 검증 |
|---|---|
| `tests/test_agent_sections_meta.py` (신규) | 9섹션 메타가 있고 `code`·`label` 이 `model.sections.GROUPS` 와 일치; `role_of` 가 대표 노드에 라벨을 준다; `HST.pattern is None`; `node_names` 가 참조 GLB 에서 섹션 노드를 정렬해 돌려준다 |
| `tests/test_agent_sandbox.py` | `SectionContext` 가 새 프로파일·색·`zone_loft` 를 노출하고 `zone_loft` 가 두께 전이 구간에서 수밀 솔리드를 만든다; `_b` 같은 밑줄 속성은 계약 문서에 없다 |
| `tests/test_agent_context.py` | 섹션별 번들이 그 섹션 노드명 전체와 역할 표를 싣는다; `spec_excerpt` 가 섹션별 키만 고른다(CS 는 `wg` 포함, SP04 는 미포함); 새 ctx 항목이 `CTX_DOC` 에 있다 |
| `tests/test_model_spec.py` | 10개 하위 모델 전 필드에 `description`; 튜플 필드 설명에 축 표기(`[x]`·`[y]`·`[z]`)가 있다 |
| `tests/test_agent_critique.py` | 섹션별 3뷰가 나오고 세 번째가 전 노드를 담는다(노드 수 ≥ 대표 노드 수); 미등록 섹션은 `[]` |
| `tests/test_agent_score.py` | `role_of` 경유 라벨이 피드백 문장에 붙는다(FRM·BRG 예) |
| `tests/test_agent_worker.py` | `--drain`: 큐가 비면 `serve` 가 돌아온다; 큐에 2건이면 2건 다 처리한다 |
| `tests/test_model_assemble_agent.py` (신규) | `pick_sources` 가 PASS 산출을 고르고 없으면 정답으로 대체; `run_agent_assemble` 이 결합 GLB·판정 파일·`build.json(kind=agent)` 을 만들고 `build_sections.source` 가 섹션별로 맞다 |
| `web/src/lib/jobs.test.ts` | `AGENT_SECTIONS` 9개; `jobPayloads` 가 선택 수만큼 행을 만들고 예산·요청을 공통 적용; 빈 선택은 `RangeError` |

## 5. 실증 절차 (브랜치 `feat/m7-section-spread`)

1. 전건 테스트 → 커밋. 프롬프트를 호출 없이 출력해 섹션마다 노드명·doc·ctx 문서를 눈으로 확인한다(무과금).
2. 배치 1: SP04·HST·SLAB·BRG 를 웹에서 한 번에 큐에 넣고 `m3d worker --poll 2 --drain`. 결과를 읽고 실패 원인이 정보 부족이면 `description` 을 고쳐 재요청(섹션당 잡 ≤ 3).
3. 배치 2: FRM·RIB·CS·WG 를 같은 방식으로.
4. `m3d agent-assemble` → 결합 빌드 publish → 웹 뷰어·검증 패널 확인.
5. 판정서 `data/derived/ab1-p4p5/model/acceptance-m7.md`: 기준 ①~⑤, 섹션별 잡·시도·비용·채점, 공개 정보 범위(노드명 목록 포함), 화면 확인, 교훈.
6. README 절 갱신, 메모리 갱신, finishing-a-development-branch(병합은 사용자 선택).

비용 근거: M6 잡당 $0.25~0.5(시도 2~4). 섹션 8개 × 잡 1~3 → $4~12 예상, 상한 $25.

## 6. 범위 밖

BOX 본체 생성, 정답 없는 합격 규칙(M8 후보), 두 번째 도면 세트, 결합 빌드의 웹 버튼(지금은 CLI), 판독 확장·재실행, thinking 활성, Fable 검토, 다중 후보, 워커 서버 배포.
