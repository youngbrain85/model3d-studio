# M3 P4~P5 정밀 모델 재현 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (이 세션에서 컨트롤러가 직접 실행) or superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SSOT+결정에서 ModelSpec 을 만들고, 결정론 빌더로 P4~P5 GLB 를 생성해 3중 검증(self-check·독립 재실측·렌더)을 거쳐 참조(SPEC_v2·measure v2)와 대조한다.

**Architecture:** `worker/src/m3d/model/` 패키지 — `spec.py`(Pydantic ModelSpec) · `spec_rules.py`(SSOT → 필드 추출·출처) · `geom.py`(로프트·압출·미러) · `builder.py`(참조 v2 기하 기법 포팅, 값은 spec) · `selfcheck.py` · `measure.py`(자기참조 금지) · `render.py`(matplotlib 정사영) · `compare.py`. CLI 5개(`modelspec`·`build`·`measure`·`render`·`compare-model`). 산출물 `data/derived/<ds>/model/`.

**Tech Stack:** Python 3.12 · pydantic 2 · numpy · trimesh 5 · matplotlib · psycopg(ssot.json 은 파일이므로 DB 불필요).

설계서: `docs/superpowers/specs/2026-09-05-m3-model-build-design.md`. 참조(읽기 전용): `D:\Projects\Inspection\mbi_app_v2\models_3d\ab1\` 의 `SPEC_v2.md`·`build_ab1_p4p5_v2.py`·`measure_ab1_p4p5_v2.py`·`render_ab1_p4p5.py`·`AB1_P4P5_v2.glb`·`measure_ab1_p4p5_v2.json`·`renders/`.

## Global Constraints

- venv `.\worker\.venv\Scripts\python.exe`, `PYTHONUTF8=1`. pytest 시작 **302 passed**(실측 우선). LLM 호출 0. 참조 원본 수정 금지(읽기·복사만).
- 단위: 내부 m(참조와 동일), 표기 mm. 좌표 x=교축직각·y=EL−4.871·z=STA−4190(Y-up). 노드명 `AB1_S5_<부재>_<번호>`(참조 §11), 버텍스 컬러 필수, 접합부 관통 삽입 5mm(KB §2-13·17), 대소문자만 다른 노드명 금지.
- 빌더 헤더에 단순화 [A1]~[A21] 전 항목 명기(참조 문구 계승). 사양 모순은 재해석하지 않고 참조와 같은 우선순위(§1 H식·격벽표 우선 등) + 주석.
- `measure.py` 는 `builder.py`·`geom.py` 를 import 하지 않는다. 기대값은 `modelspec.json` 에서 재유도.
- 산출물은 `data/derived/<dataset>/model/`(gitignore). 커밋 트레일러 두 줄:

  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01AZoYNTVPox7g1d6oJd5Wo1
  ```
- 브랜치 `feat/m3-model-build`(main bfe6931+ 분기). 컨트롤러 직접 구현, 부재 그룹 단위 커밋.

---

### Task 1: ModelSpec 스키마 + SSOT 추출 규칙 + `m3d modelspec`

**Files:** Create `worker/src/m3d/model/__init__.py`, `spec.py`, `spec_rules.py`; `worker/tests/test_model_spec.py`; Modify `worker/src/m3d/cli.py`.

**Interfaces (Produces):**
- `spec.ModelSpec`(pydantic) — 아래 필드. `ModelSpec.model_validate_json(path.read_text())` 로 로드.
- `spec_rules.build_modelspec(ssot: dict) -> tuple[ModelSpec, dict]` — (spec, sources) ; `sources` 는 `{"필드경로": "ssot:B01/전체 폭원" | "decision:슬래브 두께 표기…" | "default:SPEC_v2 §8" | "derived:..."}`; `spec_rules.source_stats(sources) -> {"ssot": n, "decision": n, "default": n, "derived": n}`.
- 파서: `parse_at_chain("9@70,000=630,000") -> (9, 70000.0, 630000.0)`, `parse_thickness_zones("38(0~6,300) → 26(~16,100) → 16(~53,900) → 26 → 38", total=70000) -> [(0,6300,38),(6300,16100,26),(16100,53900,16),(53900,63700,26),(63700,70000,38)]`(뒤쪽 미기재 경계는 대칭으로 보완), `parse_pair("450×330") -> (450.0, 330.0)`, `parse_number("15,700") -> 15700.0`.
- CLI `m3d modelspec <ds>` → `data/derived/<ds>/model/modelspec.json`(`{"spec": {...}, "sources": {...}, "stats": {...}}`), 콘솔 `spec_sources ssot=n decision=n default=n derived=n`.

**ModelSpec 필드(값은 m, 참조 §0~§10 기본값 — `default` 출처):**

```python
class Coord(BaseModel):
    z_p4: float = -525.0; z_p5: float = -455.0          # §0 받침선
    el0: float = 18.694; grade: float = 0.0236; z_sta3400: float = -790.0
    y_datum: float = 4.871; deck_drop: float = 0.398; t_slab_crown: float = 0.348
    walk_side_sign: int = -1                            # 보도측 = −x

class Box(BaseModel):
    half_flange: float = 2.35; x_web: float = 2.25       # §1 [A21]
    h_pier: float = 4.0; h_mid: float = 2.8; l_flat: float = 1.25; l_para: float = 13.45
    a_dwg: float = 0.00663; h_is_clear: bool = True      # [Q1]
    top_t: list[tuple[float, float, float]]; bot_t: list[...]; web_t: list[...]   # (d0,d1,t) m
    z_sp04_offset: float = 18.9

class Diaphragm(BaseModel):
    spacing: float = 2.8; n_cell: int = 25
    support_t: float = 0.038; support_open: tuple[float, float] = (0.7, 0.7); support_sill: float = 0.45
    support_vstiff: tuple[float, float, int] = (0.026, 0.24, 12); support_jack: tuple[float, float, float] = (0.022, 0.35, 1.15)
    interior_t: float = 0.010; interior_open: tuple[float, float] = (1.4, 1.4)
    sill_cl: float = 0.45; sill_cx: float = 0.40
    h_table: list[tuple[float, float]] = [(2.8, 3.739), (5.6, 3.349), (8.4, 3.063), (11.2, 2.881), (14.0, 2.803)]
    type_map: list[tuple[float, str]] = [(2.8,"CL"),(5.6,"CL3"),(8.4,"CL6"),(11.2,"CL7"),(14.0,"CX"),(16.8,"CX1"),(19.6,"CX1"),(22.4,"CX1")]  # 그외 CU
    open_stiff: tuple[float, float, float, float] = (0.010, 0.100, 0.090, 1.56)

class FrameRow(BaseModel):
    d_list: list[float]; name: str; top_web: tuple[float, float]; bot_web: tuple[float, float]; vstiff: tuple[float, float, float]
class Frame(BaseModel):
    offset: float = 1.4
    rows: list[FrameRow]   # §3 표 7행 (F, F3, F6, F9, F10, G1, D)

class RibZone(BaseModel):
    cols: int; pitch: float; t: float; h: float; from_web: float | None = None
class Rib(BaseModel):
    top_pier: RibZone; top_mid: RibZone; top_switch: tuple[float, float] = (12.594, 15.753)
    bot_pier: RibZone; bot_mid: RibZone; bot_switch: tuple[float, float] = (22.118, 25.205)

class HStiff(BaseModel):
    t: float = 0.012; h: float = 0.150; upper_drop: float = 0.560; upper_span: float = 12.6
    lower_span: float = 25.2; lower_factors: tuple[float, float] = (0.14, 0.36)

class WG(BaseModel):
    length: float = 4.45; flange_slope: float = 0.0195; flange_flat0: float = 0.1; flange_flat1: float = 4.3
    depth0: float = 0.3; web_t: float = 0.012; fl_t: float = 0.012; fl_w: float = 0.3
    niche_r: float = 0.3; knee: tuple[float, float] = (3.9, 0.482); tip_depth: float = 0.424
    strut_size: float = 0.3; strut_angle_deg: float = 28.222; strut_lower: tuple[float, float] = (0.302, 2.413)
    bracket: tuple[float, float, float] = (0.35, 2.17, 2.70)

class CS(BaseModel):
    depth: float = 0.424; web_t: float = 0.012; fl_w: float = 0.3; fl_t: float = 0.012; seg: float = 2.8

class Slab(BaseModel):
    half_width: float = 7.85; slope: float = 0.02; t_edge: float = 0.25; t_web: float = 0.30; t_crown: float = 0.348
    thickness_is_net: bool = True                        # [Q2]
    cant_drop: list[tuple[float, float]] = [(2.35, 0.330), (6.55, 0.418), (7.85, 0.398)]
    walk_width: float = 2.95; center_barrier: float = 0.45  # [Q3]
    barrier: tuple[float, float, float] = (0.45, 0.33, 0.03)

class SP04(BaseModel):
    tf: tuple[float, float, float] = (4.386, 0.58, 0.010); bf: tuple[float, float, float] = (4.7, 0.78, 0.012)
    web: tuple[float, float, float] = (2.68, 0.58, 0.010); setback: float = 0.157

class Bearing(BaseModel):
    x: float = 1.55; kind: str = "isolation"             # [Q4]
    sole: tuple[float, float, float, float] = (1.37, 0.022, 0.054, 0.038)
    body_h: float = 0.337; base: float = 0.825; body_d: float = 0.65
    mortar: tuple[float, float] = (0.05, 0.9); block: tuple[float, float] = (1.3, 0.105)
    el_check: dict[str, float] = {"P4": 20.137, "P5": 21.789}

class ModelSpec(BaseModel):
    coord: Coord; box: Box; diaphragm: Diaphragm; frame: Frame; rib: Rib; hstiff: HStiff
    wg: WG; cs: CS; slab: Slab; sp04: SP04; bearing: Bearing
```

**추출 규칙(`spec_rules.py`) — SSOT 판독 item 에 대한 키워드/정규식, 계열 우선순위(B 슬래브·C 강상자·A 일반·D 가로보·E 부속·F 하부):**

| 필드 | 규칙 | 없으면 |
|---|---|---|
| `box.h_pier/h_mid` | C계열 item 에 "형고" 포함 & value_raw 가 `4,000`/`2,800` 또는 `4,000/2,800` | default §1 |
| `box.h_is_clear` | decision item 에 "형고" & "내공" 포함 → 선택 label 에 "내공" 이면 True | default True(Q1 참조 잠정) |
| `diaphragm.spacing/n_cell` | item 에 "다이아프램\|격벽" & value_raw `240@2,800` 등 → pitch=2.8 (n_cell 은 지간/pitch=25) | default §2 |
| `slab.half_width` | item "전체 폭원" `15,700` → 7.85 | default §8 |
| `slab.t_web/t_crown/t_edge` | item "슬래브 콘크리트 두께" `300` → t_web; crown/edge 는 default | default §8 |
| `slab.thickness_is_net` | decision item 에 "슬래브 두께" 포함 → label 에 "순" 이면 True, "포장" 이면 False | default True(Q2 잠정) |
| `slab.walk_width/center_barrier` | decision item 에 "보도" & ("2,950"\|"분할") → label 에서 2,950·450 파싱 | default §8(Q3 잠정) |
| `slab.barrier` | item "방호벽 하부 폭" 450 & "방호벽 높이 구간" 330 | default |
| `bearing.kind` | decision item 에 "받침" & "면진\|방향" → label 에 "면진" 이면 isolation, "고정\|가동" 이면 fixed | default isolation(Q4 잠정) |
| `bearing.x` | item "받침 간격" `3,100` → 1.55 | default §10 |
| `coord.z_p4/z_p5` | projects.coord_system.datums P4_bearing_z/P5_bearing_z | default |
| `box.top_t/bot_t/web_t` | item "상판\|하판\|복부판 판두께 구간" value_raw 체인 → `parse_thickness_zones` | default §1 |
| 나머지(프레임표·리브 존·WG·CS·SP04·받침 적층) | 규칙 없음 — default(참조 §3~§10), 사유 "SSOT 에 항목 없음" | default |

`sources` 에는 규칙이 성공한 필드는 `ssot:<ord>/<item>` 또는 `decision:<item>`, 그 외 `default:SPEC_v2 §n`. `derived` 는 `a_eff`(계수 정규화)·`n_cell`(지간/pitch) 같은 계산값.

- [ ] **Step 1: 파서·규칙 테스트** — `worker/tests/test_model_spec.py`: `parse_at_chain`, `parse_thickness_zones`(대칭 보완 포함), `parse_pair`, `parse_number`; 소형 SSOT 픽스처(readings 6건·decisions 2건)로 `build_modelspec` → `box.h_pier==4.0`(ssot), `slab.thickness_is_net`(decision), `wg.length`(default) 출처 문자열 검증, `source_stats` 합계 = 필드 수.
- [ ] **Step 2: 구현** — `spec.py`, `spec_rules.py`(규칙 표 그대로), CLI `modelspec`.
- [ ] **Step 3: 실행** — `m3d modelspec ab1-p4p5` → 통계 출력. 기대: ssot·decision 합이 0 보다 크고(형고·폭원·격벽·슬래브·방호벽·받침 간격 등), default 목록이 콘솔에 요약된다.
- [ ] **Step 4: 커밋** `feat(model): ModelSpec 스키마 + SSOT 추출 규칙 + m3d modelspec`.

---

### Task 2: geom.py — 로프트·압출·미러 (참조 v2 §"기하 유틸" 포팅)

**Files:** Create `worker/src/m3d/model/geom.py`; `worker/tests/test_model_geom.py`.

- 참조 `build_ab1_p4p5_v2.py` 193~306행(`_ear_clip`, `loft`, `extrude`, `rect`, `box_prism`, `mirror_poly`, `mirror_mesh`, `paint`, `stations`, `zone_split`, `zone_loft`)을 옮긴다. 상수 의존(`Z_P4`, `BREAKS_Z`, `H_CHECK`)은 인자로 받도록 시그니처를 바꾼다: `stations(z0, z1, *, breaks, checks, para_ranges, n_sub=12)`, `zone_split(z0, z1, breaks)`, `zone_loft(z0, z1, poly_fn, breaks, stations_fn)`.
- 테스트: `extrude(rect, z0, z1)` 부피 = 면적×길이(±1e-9)·`is_watertight`; `box_prism` bounds; `mirror_mesh` 가 x 부호를 뒤집고 면 법선 방향 유지(부피 양수); `loft` 로 사다리꼴 스테이션 3개 → 수밀; `_ear_clip` 오목 다각형 삼각화 면적 보존.
- 커밋 `feat(model): 기하 유틸(로프트·압출·미러) 포팅`.

---

### Task 3: 시범 빌드 — 본체 + 격벽 26 + self-check + 렌더 2장 → 승인 게이트

**Files:** Create `worker/src/m3d/model/builder.py`, `selfcheck.py`, `render.py`; `worker/tests/test_model_builder.py`; Modify `cli.py`(`build`, `render`).

- `builder.py`: 헤더 docstring 에 [A1]~[A21] 전문(참조 문구 계승). `Builder(spec: ModelSpec)` 클래스가 참조의 모듈 상수를 `spec` 필드에서 계산해 속성으로 둔다(`Z_P4=spec.coord.z_p4`, `A_EFF=(h_pier-h_mid)/l_para**2`, `BREAKS_Z`, `H_CHECK` 8점 = `(z_p4, h_pier),(z_p4+l_flat,h_pier),(z_p4+7.975, 3.1),(z_p4+l_flat+l_para, h_mid),(mid, h_mid)` 대칭). 참조 함수 `el_road/y_deck_top/y_crown/t_top/t_bot/t_web/h_box/y_web_top/y_web_bot/y_bot_out/build_box_*/dia_half_w/_dia_panels/build_dia_support/build_dia_interior` 를 메서드로 포팅(상수 → `self.` 필드). 검산 assert(계획고 P4 24.948/P5 26.600, 포물선 계수, 변단면 사슬, 판두께 존 사슬·대칭)는 `Builder.__init__` 에서 수행.
- `Builder.build(pilot: bool) -> dict[str, trimesh.Trimesh]`(노드명 → 메시, `add` 중복 검사). pilot=True 면 §1 본체 4 + §2 격벽 26 만.
- `selfcheck.run(named, spec, glb_path) -> dict`: 참조 main 의 self-check 항목을 함수화(계획고 2·bbox 2·H 8·개수 5·받침 y 4·메시 수·수밀 수). pilot 에서는 개수·받침 항목을 `skipped` 로 표시. 결과 `{"checks":[{"label","ok","detail"}], "pass":n, "fail":n, "skipped":n, "meshes":n, "watertight":n, "triangles":n}`.
- CLI `m3d build <ds> [--pilot]`: `modelspec.json` 로드 → build → 색상·노드명 가드 → `scene.export` → self-check → `selfcheck.json` 저장 → 콘솔 `[PASS]/[FAIL]` 줄 + `selfcheck pass=n fail=n skipped=n meshes=n`; fail>0 → exit 1.
- `render.py`: 참조 `render_ab1_p4p5.py` 의 정사영 방식 이식 — trimesh 로 GLB 로드·월드 전개 → matplotlib `set_aspect('equal')`: `side_context`(xz 평면 측면 + 인접 경간 스텁·교각 개략 사각), `front_section`(z=중앙 단면 슬라이스 폴리곤), `bottom_iso`(저면), `interior_cells`(y 슬라이스로 격실). 시범에서는 `side_context`·`front_section` 2장. CLI `m3d render <ds> [--pilot]` → `model/renders/*.png`.
- 테스트: 소형 spec(기본값)으로 pilot 빌드 → 노드 30개(`BOX_*` 4 + `DIA01~26`), 이름 규칙, 격벽 z = z_p4 + 2.8k, 전 메시 수밀·색상, self-check pilot 에서 계획고·H 8점 PASS.
- 실행: `m3d modelspec` → `m3d build ab1-p4p5 --pilot` → `m3d render ab1-p4p5 --pilot` → 렌더 2장을 Read 로 열어 참조 `renders/ab1_p4p5_side_context.png`·`front_section.png` 과 대조 소견 → **사용자 승인 게이트(STOP)**.
- 커밋 `feat(model): 시범 빌더(본체·격벽) + self-check + 렌더`.

---

### Task 4: 전 부재 빌드 — 프레임·리브·수평보강재·WG·CS·슬래브·방호벽·SP04·받침

**Files:** Modify `builder.py`, `selfcheck.py`; `worker/tests/test_model_builder.py`.

- 참조 §3~§10 함수(`frame_type/build_frame_parts`, `build_rib_top/bot/rib_layout`, `build_hst_upper/lower`, `wg_u/_wg_solve_niche/wg_bottom_polyline/build_wg_main/strut/bracket`, `build_cs_seg`, `slab_poly/build_slab/barrier_poly/build_barrier`, `build_sp04_*`, `bearing_parts`)을 메서드로 포팅. 상수 → spec 필드: 프레임표 `spec.frame.rows`, 리브 존 `spec.rib`, WG `spec.wg`, CS `spec.cs`, 슬래브 `spec.slab`(보도측 부호 `coord.walk_side_sign`, 방호벽 x 위치는 `half_width`·`walk_width`·`center_barrier` 로 유도: 좌 연단 [−7.85,−7.40], 중앙 [−(7.85−0.45−2.95)−0.45… = −4.45,−4.00], 우 연단 [7.40,7.85]), SP04, 받침(`el_check` 로 y 검증).
- `Builder.build(pilot=False)` 조립 순서·노드명은 참조 main 과 동일(`FRM%02d_{TRW,TRF,BRW,BRF,VSL,VSR}`, `RIB_<sfx>`, `HST_UP_R/L`, `HST_P4_LO1_R`…, `WG096R/_ST/_BR`…, `CS096R`…, `SLAB`, `BARRIER_L/R/CTR`, `SP04_TF/BF/WEB_R/L`, `BRG_P4_1_{SOLE,BODY,MORTAR,BLOCK}`…).
- self-check 전 항목 활성(개수 5·받침 y 4·메시 수 500~700).
- 테스트: 전체 빌드 → 격벽 26·프레임 150·WG 52(+ST 52+BR 52)·CS 52·받침 16·방호벽 3·SP04 4, 노드명 중복 0, 수밀·색상 전건, self-check fail 0.
- 실행: `m3d build ab1-p4p5` → self-check 전건 PASS, `AB1_P4P5.glb`.
- 커밋 `feat(model): 전 부재 빌드 — 프레임·리브·보강재·WG·CS·슬래브·SP04·받침`.

---

### Task 5: 독립 재실측 `m3d measure` (참조 measure v2 포팅, 자기참조 금지)

**Files:** Create `worker/src/m3d/model/measure.py`; `worker/tests/test_model_measure.py`; Modify `cli.py`.

- 참조 `measure_ab1_p4p5_v2.py` 를 포팅하되 기대값 유도부(`H_mm/H_at_z/t_top_mm/t_bot_mm`, EL식, 격벽 z 체인, 프레임 위치, WG/CS 개수·위치, 리브 존, 받침 EL)는 **`modelspec.json` 에서** 계산한다(빌더 import 금지 — 테스트가 `sys.modules` 로 확인). 월드 전개는 scene graph 순회(`world_meshes`), 슬라이스 `sect_z/sect_y`, `x_gap_at`.
- 항목명·구조는 참조 JSON 과 동일(`bbox.전체/상부구조`, `내공_H_프로파일`(8점), `격벽`(26 z), `프레임`(25), `WG`(52), `CS`(52), `리브_존`, `받침_EL`, `판두께_존` …). `add(name, exp, meas, tol)` → PASS/FAIL, `add_info`.
- CLI `m3d measure <ds>` → `model/measure.json`, 콘솔 `measure pass=n fail=n info=n`; fail>0 → exit 1.
- 테스트: `geom.box_prism` 로 만든 소형 GLB(상판·하판 2개, 알려진 H) + 최소 spec 으로 H 프로파일 1점 PASS/FAIL 경로, `world_meshes` 노드 이름 보존, 빌더 미참조.
- 커밋 `feat(model): 독립 재실측 m3d measure`.

---

### Task 6: 렌더 4장 · 참조 대조 `m3d compare-model` · 합격 판정

**Files:** Modify `render.py`, `cli.py`; Create `worker/src/m3d/model/compare.py`, `worker/tests/test_model_compare.py`; `data/derived/ab1-p4p5/model/acceptance-m3.md`(gitignore), `README.md`.

- `render.py` 4장 완성(`bottom_iso`, `interior_cells` 추가). 참조 `renders/` 와 나란히 Read 로 열어 소견.
- `compare.py`: `compare(ours: dict, ref: dict, tol_len_mm=5.0) -> dict` — 같은 키 경로의 `실측_mm`/`기대_mm`/값을 재귀 대조. 결과 항목 `{"path","ours","ref","diff","verdict": "match|mismatch|na","cause": ""}`; GLB 대조(`trimesh.load` 두 GLB → 노드 수·bbox·삼각형 수). CLI `m3d compare-model <ds> --ref <dir>` → `model/compare.json`, 콘솔 `compare match=n mismatch=n na=n`.
- 테스트: 소형 dict 2개로 match/mismatch/na 판정과 tol 경계.
- 실행: `m3d measure` → `m3d render` → `m3d compare-model ab1-p4p5 --ref D:\Projects\Inspection\mbi_app_v2\models_3d\ab1` → mismatch 항목마다 원인 분류(사양차/판독차/빌더차)를 `acceptance-m3.md` 에 기입(설계 §1 ①~⑥ 표).
- README "3D 모델 (M3)" 절: 5개 명령 순서(무과금). 커밋 `feat(model): 렌더 4장 + 참조 대조 + M3 합격 판정`.

---

## 계획 자체 검토
- 스펙 커버리지: §1 ①(T1 통계) ②(T3·T4 self-check) ③(T5) ④(T6 compare) ⑤(T3·T6 렌더) ⑥(각 태스크 테스트). §2 D1~D8 반영(D5 자기참조 금지 = T5 테스트, D7 게이트 = T3 STOP). §4 명령 5개 = T1/T3/T5/T6. §6 범위 밖 미포함.
- 플레이스홀더: 포팅 지시는 참조 파일의 함수명·행 범위를 명시했고 상수→필드 매핑을 적었다(참조 코드가 정본).
- 타입 일관성: `ModelSpec` 필드명은 T1 정의를 T3~T5 가 그대로 참조; `selfcheck.run(named, spec, glb_path)`; `measure` 는 `modelspec.json`·GLB 경로만 입력; `compare(ours, ref)`.
