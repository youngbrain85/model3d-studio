# M6 설계 — 격벽 PASS: 에이전트가 보강재까지 정답과 같게 만들도록 스펙 의미·규약·피드백·자기 렌더를 보강한다

작성 2026-09-07. M5 결과(`data/derived/ab1-p4p5/model/acceptance-m5.md`): 루프는 끝까지 돌았으나 채점 ② PASS 0.
최선 b4 는 판·개구·체인·재실측이 전부 맞고 **보강재 3D 배치만** 틀렸다(지점 격벽 잭업보강재 돌출 0.35 m 가 z 가 아니라 x, 일반 격벽 +z 면 개구보강재 없음).
사용자 결정: 범위 "격벽 PASS 집중, M6 API 상한 $8", 접근 "A — 정보 보강 + 자기 렌더 피드백, 추가 LLM 호출 없음"(정답 렌더는 보여주지 않는다).

## 0. 왜 틀렸나 (M5 실증 진단)

| 노드 | 정답 z 범위 | b4 z 범위 | 원인 |
|---|---|---|---|
| DIA01 (지점, P4) | −525.00 ~ −524.61 | −525.00 ~ −524.94 | 잭업보강재(0.35)·수직보강재(0.24)의 "돌출" 을 x 폭으로 해석 |
| DIA02 (일반) | −522.207 ~ −522.095 | −522.205 ~ −522.195 | +z 면 개구보강재(돌출 0.100) 없음 |

LLM 에게 없던 정보 세 가지: (1) 스펙 튜플의 **의미** — `support_jack = [0.022, 0.35, 1.15]` 가 (두께 x, 돌출 z, 높이 y) 라는 것;
(2) 정답 빌더의 **편측 부착 규약** — 지점 격벽 보강재는 경간 안쪽 면만, 일반 격벽 개구보강재는 +z 면만(builder.py [A4]·[A5]);
(3) 피드백 숫자의 **뜻** — "정답 z 범위 0.39 m" 는 판+보강재 전체 범위인데 잡 3 은 판 두께로 읽어 판을 0.39 m 로 만들었다(체인·재실측 후퇴).
숫자만으로는 방향 오류를 못 고친다(b4 4시도 내내 bbox 324 mm 고정).

## 1. 목표와 합격 기준

| # | 기준 | 판정 |
|---|---|---|
| ① | 격벽 섹션 채점 **PASS ≥ 1회**(잡 ≤ 3, 잡당 시도 ≤ 4): `score.json` pass=true, 화면 채점 블록 PASS·bbox ≤ 5 mm·fail 0 | 채점 JSON + 화면 |
| ② | 실패 시도의 다음 프롬프트에 의미 문장·축별 델타·자기 렌더 3장이 들어가고 `prompt.md`·`attempts.json`·`critique<n>/` 에 남는다 | 파일 |
| ③ | M6 API 지출 ≤ **$8**(`usage.jsonl` stage `model-agent` 증분; M5 누적 $1.39 → 상한 $9.39), 웹에서 넣은 예산이 `jobs.budget_usd` 에 반영 | 원장·DB |
| ④ | pytest·vitest·`tsc -b --noEmit` 전건 통과 | PASS |

①을 못 채우면 **실패로 정직하게 보고**(잡별 시도·비용·채점·렌더를 판정서에). 최종 판정은 사용자.

## 2. 결정 사항

| # | 결정 | 이유 |
|---|---|---|
| D1 | `ModelSpec.Diaphragm` 13 필드와 `Bearing.x` 에 pydantic `Field(description=…)` 를 달고, 프롬프트의 스펙 발췌를 `{"value", "source", "doc"}` 로 확장한다(§3.1). 계약 문구 "포장은 출처·의미 표시용" | 튜플 필드의 의미는 스펙(SSOT)의 일부다. 튜플 뜻이 없는 스펙은 스펙 결함이지 LLM 결함이 아니다 |
| D2 | KB §5 에 보강재 규약 2줄을 추가한다(§3.2). `kb_excerpt` 가 §5 를 시스템 프롬프트에 넣으므로 자동 반영 | 편측 부착은 정답 빌더의 단순화 규약이라 도면만으로는 알 수 없다 — 규칙으로 줘야 공정하다 |
| D3 | 피드백 문장 재작성(§3.3): bbox 정의 한 줄, 축별 델타 문장("정답이 +z 쪽으로 326 mm 더 뻗음"), 판 검사 통과 시 "판을 바꾸지 말 것" 힌트, 체인 실패 시 판 위치 힌트 | 잡 3 의 오독(범위→두께)을 막는다. 숫자에 의미를 붙인다 |
| D4 | 자기 렌더 피드백: 채점 FAIL 뒤 에이전트 섹션 GLB 만으로 3장 렌더해 다음 시도 프롬프트에 캡션과 함께 첨부(§3.4). **정답 렌더는 주지 않는다**. 추가 LLM 호출 없음 | 방향 오류는 그림이면 보인다. 호출당 +3 이미지(≈800×500, ≈$0.01) |
| D5 | 웹 "LLM 으로 만들기" 모달에 "예산 상한 ($)" 입력(기본 5, 0.5~50) → `jobs.budget_usd`. 루프의 상한 = 잡 행 `budget_usd`(현행) | DB 기본 5 는 M5 상한. 사용자가 잡마다 상한을 정한다. M6 실증은 9.39 |
| D6 | 시도 수 4·모델 Sonnet 5·thinking 비활성·max_tokens 16,000 유지 | 변수는 정보뿐이어야 원인이 보인다 |
| D7 | 실증 정지 규칙: 잡 3개(≈$1.8)까지 돌리고도 FAIL 이면 남은 예산을 더 쓰지 않고 사용자에게 보고한다 | 같은 실패를 예산으로 밀어붙이지 않는다 |
| D8 | 정답 대조 정보의 공개 범위는 판정서에 명시한다(필드 설명·KB 규약·bbox 델타·자기 렌더까지; 정답 렌더·정답 코드는 아님) | "도면+규칙으로 만들었는가" 를 사용자가 판단할 수 있게 |

## 3. 변경 명세

### 3.1 스펙 필드 설명 (`worker/src/m3d/model/spec.py`, `agent/context.py`)

`Diaphragm` 필드 설명(값은 그대로, description 만 추가):

| 필드 | description |
|---|---|
| spacing | 격벽 간격(m) — 전역 체인 z = z_p4 + k·spacing |
| n_cell | 격실 수 — 격벽 수 = n_cell + 1 (01 = P4 받침선, 마지막 = P5 받침선) |
| support_t | 지점 격벽(01·마지막) 판 두께(m, z 방향) — 판면 한쪽이 받침선 z 에 놓이고 두께는 경간 안쪽으로 |
| support_open | (폭 x, 높이 y) 지점 격벽 개구(m), 개구는 x 중심 |
| support_sill | 지점 격벽 개구 문턱 높이(m) — 하판 상면 y_web_bot(z) 기준 |
| support_vstiff | (t 두께[x 방향], w 돌출[판면에서 경간 안쪽 z], n 총 개수) 지점 격벽 수직보강재 — 내공 전 높이; 참조 단순화 [A4]: 경간 안쪽 면에만 받침 x·x±0.2 의 3열 × 좌우 = 6 |
| support_jack | (t 두께[x], w 돌출[판면에서 경간 안쪽 z], h 높이[y]) 지점 격벽 잭업보강재 — 받침 x 직상(상판 밑 h)·직하(하판 위 h) 각 1 × 좌우 = 4, 경간 안쪽 면에만 |
| interior_t | 일반 격벽 판 두께(m, z) — 두께 중심을 체인 위치에 |
| interior_open | (폭 x, 높이 y) 일반 격벽 개구(m), x 중심 |
| sill_cl | CL 계열 일반 격벽 개구 문턱(m, y_web_bot 기준) |
| sill_cx | CX 계열 일반 격벽 개구 문턱(m) |
| h_table | (받침선으로부터 거리 d, 격벽 높이) 판독 대조값 — 판 높이는 ctx 내공(y_web_bot~y_web_top)에서 유도하고 이 표는 검산용 |
| type_map | (받침선으로부터 거리 d, 타입명) — dmin = 양 받침선까지 최소 거리; CX 로 시작하는 타입의 d 범위(min−0.1 < dmin < max+0.1) 이면 sill_cx, 아니면 sill_cl |
| open_stiff | (t 판두께, h_h 상·하변 돌출[z], h_v 좌·우변 돌출[z], l 길이) 일반 격벽 개구보강재 — 개구 4변 바깥에 붙여 판의 +z 면에만 돌출(참조 단순화 [A5]); 상·하변은 x 중심 길이 l·두께 t 를 y 로, 좌·우변은 y 중심 길이 l·두께 t 를 x 로 |

`Bearing.x`: "받침 중심 x(m) — 좌우 대칭 ±x".

`context.spec_excerpt(spec_dict, sources)` 는 각 필드에 `"doc": <description>` 을 더한다(description 이 없으면 키 생략).
`CODE_CONTRACT` 의 포장 문장: `{"value", "source", "doc"} 포장은 출처·의미 표시용이며 코드에서는 ["value"] 로 접근하지 않는다`.

### 3.2 KB §5 보강재 규약 (`docs/모델링규칙_지식베이스_v0.md`)

§5 "내부(격실·보강재)까지 모델링하는 것이 기본이다" 뒤에 두 항목:

```
- **보강재 방향 규약**: 판 보강재는 두께 t 를 판면 안 방향(격벽이면 x), 돌출 w 를 판면 법선
  방향(격벽이면 z)으로 판면에서 뻗는다. 판 두께는 스펙값 그대로 두고, 보강재는 별도 솔리드로
  판면에 INS 만큼 물려 같은 노드에 합친다.
- **편측 부착 단순화**: 지점 격벽의 수직·잭업보강재는 경간 안쪽 면에만, 일반 격벽의 개구보강재는
  +z 면에만 둔다(참조 빌더 [A4]·[A5]). 노드 bbox 는 판+보강재 전체 범위다.
```

### 3.3 피드백 문장 (`agent/score.py`)

`score_section` 의 `worst_detail` 항목에 축별 델타를 더한다:
`"axes": [{"axis": "z", "bound": "max", "ours": -524.936, "ref": -524.61, "delta_mm": 326}, …]` — |ref − ours| > 5 mm 인 (축, min/max) 만.

`feedback_text` 출력(순서 고정):

```
채점: FAIL
(노드 bbox = 그 노드에 합친 모든 솔리드 — 판+보강재 — 의 전체 범위이며 판 두께가 아니다)
빠진 노드(정답에는 있음): …                       ← 있을 때만
남는 노드(정답에 없음): …                         ← 있을 때만
정답 대비 bbox 편차 상위: AB1_S5_DIA26 326mm, AB1_S5_DIA01 326mm, …
  AB1_S5_DIA01: z 최대 -524.936 → 정답 -524.61 — 정답이 +z 쪽으로 326mm 더 뻗음
  AB1_S5_DIA26: z 최소 -455.064 → 정답 -455.39 — 정답이 -z 쪽으로 326mm 더 뻗음
판 두께·위치는 검사를 통과했으니 바꾸지 말 것 — 차이는 판면에 붙는 부속 솔리드(보강재 등)의 유무·방향·돌출 크기에서 난다.
                                                   ← 섹션·결합 self-check fail 0 ∧ 재실측 fail 0 일 때
판면 정점이 체인 위치 ±10mm 에 없다 — 판 두께 중심(지점 격벽은 받침선 쪽 판면)을 체인 z 에 두고 두께는 스펙값만큼만.
                                                   ← 실패 항목에 "격벽 z 체인" 이 있을 때
섹션 self-check 실패: … | 결합 self-check 실패: … | 재실측 실패 항목: …   ← 있을 때만
```

델타 문장 규칙(축 a ∈ x,y,z; Δ = 정답 − 우리, mm 반올림): max 에서 Δ > 0 → "정답이 +a 쪽으로 Δmm 더 뻗음", Δ < 0 → "우리가 +a 쪽으로 |Δ|mm 더 뻗음(초과)";
min 에서 Δ < 0 → "정답이 −a 쪽으로 |Δ|mm 더 뻗음", Δ > 0 → "우리가 −a 쪽으로 Δmm 더 뻗음(초과)". 노드 ≤ 4, 노드당 줄 ≤ 6.

### 3.4 자기 렌더 (`agent/critique.py` 신규)

`render_views(agent_glb: Path, spec: ModelSpec, code: str, out_dir: Path) -> list[dict]` → `[{"path": Path, "caption": str}]`.
`render.load_nodes`·`to_tris`·`render()` 재사용, `size=(8, 5)`, `dpi=100`(≈800×500 px), Y-up. 노드가 없는 뷰는 건너뛴다. 섹션별 뷰 표(M6 는 DIA 만):

| 이름 | 노드 | eye | 캡션(그림 제목과 동일) |
|---|---|---|---|
| dia01_front | AB1_S5_DIA01 | (0, 0, 1) | 이전 시도 DIA01 정면 — +z(경간 안쪽)에서 본 판면·개구·보강재, 화면 좌 = −x |
| dia01_side | AB1_S5_DIA01 | (1, 0, 0) | 이전 시도 DIA01 측면 — +x 에서, 화면 좌 = +z(경간 안쪽), 점선 = 체인 z_p4; 보강재 돌출은 판면에서 왼쪽으로 보여야 한다 |
| dia13_iso | AB1_S5_DIA13 | (0.7, 0.45, 0.85) | 이전 시도 DIA13 아이소 — +x+y+z 에서, 개구보강재는 +z 면 |

dia01_side 는 `extra` 훅으로 체인선(화면 x = −z_p4, 점선)과 "경간 안쪽 +z →" 텍스트를 그린다.
루프(`loop.run_job`): 채점 FAIL 이면 `critic(res.glb, spec, out.code, work/"agent"/f"critique{attempt}")`(주입 가능, 기본 `critique.render_views`)
→ `attempts[-1]["critique"] = [파일명…]` → 다음 `section_bundle(..., critique=…)`.
`section_bundle` 은 피드백 뒤에 텍스트 "이전 시도 결과 렌더(자기검토용): 도면 크롭·규칙과 비교해 판면 방향·보강재 돌출 방향과 크기·개구 위치를 스스로 확인하고 고쳐라."
+ (캡션 텍스트, 이미지 블록)×n 을 넣고 digest·`n_images` 에 포함한다. 실행 오류 시도(GLB 없음)는 렌더 없음.

### 3.5 웹 예산 입력 (`web/src/lib/jobs.ts`, `routes/Model.tsx`)

`jobPayload({…, budgetUsd})` → `budget_usd`(0.5 ≤ v ≤ 50 아니면 RangeError). 모달에 Mantine `NumberInput` "예산 상한 ($)" 기본 5, step 0.5.
잡 패널 요약은 현행(비용·시도)을 유지한다.

## 4. 테스트

| 파일 | 검증 |
|---|---|
| `tests/test_model_spec.py` | Diaphragm 13 필드·Bearing.x 에 description 이 있고, vstiff·jack 설명에 "[x" 와 "z" 가 있다 |
| `tests/test_agent_context.py` | 발췌에 `doc` 이 붙는다; 번들 시스템 프롬프트(실제 KB 발췌)에 "보강재 방향 규약"·"편측 부착 단순화" 가 있다; `critique` 3장이 이미지·캡션으로 들어가고 `n_images`·digest 에 반영된다 |
| `tests/test_agent_score.py` | DIA03 을 +z 20 mm 민 케이스: `worst_detail[0]["axes"]` 에 z min/max 델타, 피드백에 bbox 정의 줄·"정답이 -z 쪽으로 20mm"·"우리가 +z 쪽으로 20mm"·체인 힌트; 정답 그대로면 PASS 줄만 |
| `tests/test_agent_critique.py` | 정답 DIA.glb → PNG 3장(긴 변 ≤ 1,000 px)·캡션; DIA13 만 있는 GLB → 1장 |
| `tests/test_agent_loop.py` | FAIL → 다음 호출 번들에 이미지 3장(크롭 0)·"자기검토용" 문구, `attempts.json[…]["critique"]` 3개, `critique1/` 파일 존재 |
| `web/src/lib/jobs.test.ts` | payload 에 `budget_usd`; 0·60 은 RangeError |

## 5. 실증 절차 (브랜치 `feat/m6-diaphragm-pass`)

1. `pytest`·`vitest`·typecheck 전건 → 커밋.
2. 웹 모달에서 예산 9.39 로 잡 1(요청 없음) → `m3d worker --once`. 채점 PASS 면 종료.
3. FAIL 이면 프롬프트·렌더·피드백을 읽고, 정보 결함이면 고쳐(코드) 잡 2, 아니면 수정 요청(부모 잡) 으로 잡 2. 최대 잡 3(D7).
4. 판정서 `data/derived/ab1-p4p5/model/acceptance-m6.md`: 기준 ①~④, 잡별 시도·비용·채점, 공개 정보 범위(D8), 화면 확인(DOM 읽기), 교훈.
5. README "LLM 모델링 (M5)" 절에 M6 항목, 메모리 갱신, finishing-a-development-branch(병합은 사용자 선택).

비용 근거: 호출당 입력 ≈ 22~27k 토큰(크롭 8 + 렌더 3)·출력 4~6k → $0.11~0.14; 잡당 ≤ $0.6; 잡 3 ≤ $1.8 ≪ $8.

## 6. 범위 밖

나머지 9섹션 확산, thinking 활성, Fable 검토 호출, 다중 후보, 정답 렌더·정답 코드 노출, 지점 격벽 보강재 규격의 판독 확장(SSOT 승격), 잡 패널 렌더 표시.
