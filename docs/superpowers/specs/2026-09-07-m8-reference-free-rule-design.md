# M8 설계 — 정답 없는 합격 규칙: 기하 건전성 + 스펙 유도 재실측으로 판정한다

작성 2026-09-07. M7 결과(`data/derived/ab1-p4p5/model/acceptance-m7.md`): 8섹션 중 2개만 PASS.
그런데 나머지 6섹션도 **섹션 self-check·결합 self-check·재실측은 거의 전건 통과**한다 — 유일한 판별력이 정답 빌더와의 bbox 대조였다.
사용자 결정: 범위 "전 섹션 검사 보강 + 규칙 전환, 상한 $5".

## 0. 지금 상태 — 정답을 빼면 무엇이 남는가

M7 의 섹션별 최선 산출을 정답 대조 없이 판정하면 이렇게 된다.

| 섹션 | 재실측 항목 | 섹션 self-check(일반 제외) | M7 최선 bbox 편차 | 정답 없이 판정하면 |
|---|---|---|---|---|
| BOX | 18 | 12 | — (범위 밖) | 촘촘함 |
| RIB 종리브 | 8 | 0 | 186 mm | 재실측 1건 FAIL → 걸림 |
| DIA 격벽 | 5 | 2 | 5 mm | 통과(정당) |
| SLAB 슬래브·방호벽 | 5 | 0 | 9.5 mm | 재실측 1건 FAIL → 걸림 |
| WG 외측가로보 | 4 | 1 | **1,688 mm** | **전건 통과 — 거짓 합격** |
| BRG 받침 | 4 | 5 | 14 mm | 통과 |
| FRM 개방 프레임 | 3 | 1 | 165 mm | 통과 |
| CS 외측빔 | 1 | 1 | 21 mm | 통과 |
| HST 수평보강재 | **0** | 0 | 5 mm | **검사 자체가 없음** |
| SP04 이음판 | **0** | 0 | 0.4 mm | **검사 자체가 없음** |

정착대가 1.7 m 어긋난 가로보가 통과하고, 이음판·수평보강재는 검사할 항목조차 없다.
**M8 은 규칙을 바꾸는 일이 아니라 정답 없는 검사를 실제로 만드는 일이다.**

## 1. 목표와 합격 기준

판정을 세 겹으로 만든다: **기하 건전성**(스펙 무관) → **스펙 유도 재실측**(빌더 무관) → **사람 승인**(기존).
정답 빌더 대조는 합격 조건에서 빼고 참고 정보로 남긴다.

| # | 기준 | 판정 |
|---|---|---|
| ① | 새 규칙을 기존 에이전트 산출 **33건**에 돌려, 정답 대비 편차 **≥ 100 mm 를 전부 불합격**(거짓 합격 0)하고 **≤ 5 mm 를 전부 합격**(거짓 불합격 0). 5~100 mm 구간은 혼동표로 보고 | `m3d verify-rule` 출력 |
| ② | 섹션마다 재실측 항목 **≥ 4개**, 전 섹션 합계 **≥ 75항목**(현행 49). HST·SP04 의 0건을 없앤다 | measure.json |
| ③ | 기하 건전성 3종(외곽 이탈·부유 부재·중복 배치)이 인위적 결함을 잡는다 | 단위 테스트 |
| ④ | 웹 검증 패널이 정답 무관 판정과 참고용 정답 대조를 나눠 보여 준다 | 육안 |
| ⑤ | 실증 지출 ≤ **$5**(누적 상한 $20.03), pytest·vitest·typecheck 전건 | 원장·PASS |

①이 M8 의 본체다. 규칙이 쓸모 있으려면 **틀린 것을 걸러야** 하고, 지나치게 엄해서 맞는 것을 떨어뜨려도 안 된다.
33건은 이미 만들어져 있으므로 이 검증에 API 비용이 들지 않는다.

## 2. 결정 사항

| # | 결정 | 이유 |
|---|---|---|
| D1 | 재실측 행에 섹션 코드를 찍는다: `Checks.group` 을 `run()` 이 섹션 표에서 설정하고 `add`·`add_info`·`add_missing` 이 행에 `"섹션"` 키로 남긴다. 여러 섹션을 다루는 함수는 호출마다 `group=` 로 덮는다 | "이 섹션의 재실측 항목만" 판정하려면 귀속이 필요하다. 자기 진단 그룹 태그(M4 D3)와 같은 방식 |
| D2 | 섹션별 재실측 항목을 스펙에서 유도해 채운다(§3.2). 새 함수 `sec_hstiff`·`sec_sp04`, 기존 `sec_wg_cs`·`sec_frames`·`sec_bearings`·`sec_slab`·`sec_ribs` 확장 | ②의 실체. 기대값은 ModelSpec 필드에서 유도하고 빌더를 import 하지 않는다(KB §6-2) |
| D3 | `model/sanity.py` 신규 — 스펙과 무관한 기하 건전성 3종: **외곽 이탈**(노드 bbox 가 교량 외곽 밖), **부유 부재**(다른 노드와 닿지 않음), **중복 배치**(두 노드의 bbox 겹침이 작은 쪽 부피의 50% 초과). bbox 연산만 쓴다 | 540 m 어긋남 같은 큰 사고를 스펙 해석 없이 즉시 잡는다. 메시 불리언은 느려서 쓰지 않는다 |
| D4 | 합격 규칙: `pass = 건전성 fail 0 ∧ 섹션 self-check fail 0 ∧ 결합 self-check fail 0 ∧ 그 섹션 재실측 fail 0`. 정답 대조는 `score["reference"]` 로 남기되 `pass` 에 넣지 않는다 | 사용자 결정. 새 교량에 쓸 수 없는 조건을 합격에서 뺀다 |
| D5 | 피드백을 정답 무관으로 재구성: 실패한 재실측 항목의 **항목명·기대·실측·허용오차**와 건전성 위반을 먼저 싣고, 정답이 있을 때만 축별 델타를 뒤에 덧붙인다 | 새 교량에서도 같은 피드백이 나와야 한다 |
| D6 | `m3d verify-rule [--dataset]` — `model/agent/*/` 를 훑어 섹션마다 새 규칙을 적용하고 (편차 구간 × 합격) 혼동표와 어긋난 건의 사유를 낸다. 무과금 | ①의 도구. 규칙을 고칠 때마다 다시 돌린다 |
| D7 | 실증은 재실측 항목이 0건이던 **HST·SP04 두 섹션**을 새 규칙으로 다시 돌린다 | 검사 없이 통과하던 둘이 진짜 검사를 통과하는지가 규칙의 실전 시험 |
| D8 | 모델·시도 수·예산 구조는 그대로 | 변수는 판정 규칙만 |

## 3. 변경 명세

### 3.1 섹션 태그 (`model/measure.py`)

```python
class Checks:
    def __init__(self):
        self.rows: list[dict] = []
        self.group: str | None = None          # run() 이 섹션마다 설정

    def add(self, name, exp, meas, tol, unit="", group=None): ...   # 행에 "섹션": group or self.group
```

`SECTIONS` 표를 `(label, code, fn)` 3튜플로 바꾼다: `("이음판", "SP04", sec_sp04)` 등.
`sec_bbox`·`sec_mesh_count` 는 `ASSEMBLY`, `sec_h_profile`·`sec_deck_top` 은 `BOX`, `sec_wg_cs` 는 호출마다 `group="WG"` / `group="CS"`.
`measure.run()` 결과에 `"섹션별"` 집계(코드 → {PASS, FAIL, INFO})를 더한다.

### 3.2 섹션별 재실측 항목 (D2)

전부 ModelSpec 에서 유도한다. 허용오차는 길이 5 mm·개수 0·각도 0.5°(현행).

| 섹션 | 새로 넣는 항목 |
|---|---|
| SP04 (0 → 5) | 판 4매 존재 / 상면판 하면 y = `y_deck_top(z_j)` / 하면판 상면 y = `y_bot_out(z_j)` / 복부판 내면 x = ±`x_web` / 네 판의 z 중심 = 이음선 `z_p4 + box.z_sp04_offset` |
| HST (0 → 5) | 부재 10개 / 상단열 y 중심 = `y_web_top(z) − hstiff.upper_drop` / 상단열 z 범위 = `[z_p4+upper_span, z_p5−upper_span]` / 하단열 y = `y_web_bot(z) + factor·H(z)`(2열×양측 8개) / 내민 길이 x = `hstiff.h` |
| WG (4 → 8) | 정착대 52개의 y 범위 = `y_deck_top − bracket[2] … − bracket[1]` / 정착대 x 범위 = `x_web … x_web + bracket[0]` / 스트럿 하단 작업점 = (`x_web + strut_lower[0]`, `y_deck_top − strut_lower[1]`) / 스트럿 상단 작업점 = (`x_web + knee[0]`, `y_deck_top − knee[1]`) |
| CS (1 → 4) | 세그 z 중심 = 가로보 체인 위치 / 세그 x 중심 = `x_web + wg.length` / 춤 = `cs.depth` |
| FRM (3 → 6) | 상부 플랜지 z 폭 = `top_web[1]` / 하부 플랜지 y = `y_web_bot + bot_web[1]` / 수직보강재 y 길이 = `vstiff[2]` |
| BRG (4 → 7) | 솔플레이트 두께 = `sole[3]` / 모르타르 두께 = `mortar[0]` / 블록 한 변 = `block[0]` |
| SLAB (5 → 7) | 방호벽 3조의 x 범위(연단 2조 = `±(half_width−barrier[0]) … ±half_width`, 중앙 1조 = 보도 경계에서 유도) / 방호벽 높이 = `barrier[1]` |
| RIB (8 → 9) | 존별 리브 높이 = `zone.h` |

합계 49 → 80 안팎.

### 3.3 기하 건전성 (`model/sanity.py` 신규)

```python
def envelope(spec: ModelSpec) -> tuple[np.ndarray, np.ndarray]   # 스펙에서 유도한 외곽 (여유 0.5 m)
def run(named: dict[str, trimesh.Trimesh], spec: ModelSpec) -> dict
    # {"pass": n, "fail": n, "checks": [{"label", "ok", "detail", "nodes"}]}
```

세 가지만 본다(전부 bbox 연산).

1. **외곽 이탈** — 노드 bbox 가 외곽 밖. 외곽은 x ±(`slab.half_width`+0.5), y [`받침 블록 하면`−0.5, `방호벽 상단`+0.5], z [`z_p4`−0.5, `z_p5`+0.5].
2. **부유 부재** — 어떤 다른 노드의 bbox 와도 0.05 m 안에서 만나지 않는 노드. 섹션 단독 채점에서는 결합 모델 기준으로 본다.
3. **중복 배치** — 두 노드 bbox 의 겹침 부피가 작은 쪽 bbox 부피의 50% 초과. 같은 자리에 두 부재를 놓은 실수를 잡는다.

### 3.4 합격 규칙·피드백 (`agent/score.py`, D4·D5)

```python
def score_section(code, agent_glb, spec, ref_dir=None, *, work_dir) -> dict
```

- `ref_dir` 이 None 이면 정답 대조를 건너뛴다(새 교량 경로).
- 결과 키: `sanity`, `section_selfcheck`, `assembled_selfcheck`, `measure`(그 섹션 행만 + 전체 집계), `reference`(있을 때만: 기존 `compare` 내용).
- `pass` 는 D4 식. `summary()` 에 `sanity_fail`·`measure_section_fail` 을 넣고 `bbox_dev_max_m` 은 `reference` 가 있을 때만 채운다.
- `feedback_text` 순서: 건전성 위반 → 실패한 재실측 항목(항목명·기대·실측·허용오차) → self-check 실패 → (정답이 있으면) 축별 델타.

### 3.5 회귀 검증 도구 (`model/verify_rule.py` + `cli.verify_rule`, D6)

```python
def collect(cfg, dataset) -> list[dict]      # 잡 디렉터리 → {job_id, code, glb, ref_dev_m}
def run_rule(cfg, dataset, *, ref_dir) -> dict   # 각 산출에 새 규칙 적용 → 혼동표
```

출력: 구간(`≤5mm`, `5~100mm`, `≥100mm`) × (합격/불합격) 표, 그리고 어긋난 건마다 사유 한 줄.
`m3d verify-rule` 은 거짓 합격이 하나라도 있으면 종료코드 1.

### 3.6 웹 (`components/VerifyPanel.tsx`, `lib/models.ts`, D4)

채점 블록을 두 줄로 나눈다: **정답 무관 판정**(건전성·self-check·재실측, 합격 여부) / **참고: 정답 대조**(노드 일치·bbox 편차, 있을 때만).
`AgentScoreSummary` 타입에 `sanity_fail`·`measure_section_fail` 을 더하고 `bbox_dev_max_m` 을 선택 필드로 바꾼다.

## 4. 테스트

| 파일 | 검증 |
|---|---|
| `tests/test_model_sanity.py` (신규) | 정답 결합 모델은 건전성 fail 0; 노드 하나를 100 m 옮기면 외곽 이탈+부유로 잡힌다; 노드를 복제해 같은 자리에 두면 중복 배치로 잡힌다 |
| `tests/test_model_measure.py` | 섹션 태그가 모든 행에 있다; 섹션별 항목 수 ≥ 4·합계 ≥ 75; 정답 모델은 FAIL 0; SP04 상면판을 20 mm 내리면 그 섹션만 FAIL |
| `tests/test_agent_score.py` | `ref_dir=None` 이면 `reference` 없이 판정한다; 정답 그대로면 PASS; WG 정착대를 1.7 m 올리면 재실측이 잡는다; 피드백에 항목명·기대·실측이 나온다 |
| `tests/test_model_verify_rule.py` (신규) | 가짜 잡 3건(0 mm·50 mm·1 m)으로 혼동표가 구간별로 채워지고 거짓 합격 시 실패 종료 |
| `web/src/lib/models.test.ts` | 새 요약 필드 파싱 |

## 5. 실증 절차 (브랜치 `feat/m8-reference-free-rule`)

1. 전건 테스트 → 커밋.
2. `m3d verify-rule` — 기존 33건 혼동표. 거짓 합격이 있으면 그 섹션의 재실측 항목을 보강하고 다시 돌린다(무과금 반복).
3. 웹에서 HST·SP04 두 섹션을 새 규칙으로 실행(예산 20.03) → `m3d worker --poll --drain`.
4. 화면에서 정답 무관 판정 블록 확인.
5. 판정서 `data/derived/ab1-p4p5/model/acceptance-m8.md`: 기준 ①~⑤, 혼동표, 섹션별 항목 수 변화, 한계, 다음 후보.
6. README 절, 메모리, finishing-a-development-branch.

## 6. 범위 밖

두 번째 도면 세트 검증, M7 미달 6섹션 재도전, 판독 확장, 워커 배포, 사람 승인 UI 변경(기존 승인/반려 그대로), BOX 본체 생성.
