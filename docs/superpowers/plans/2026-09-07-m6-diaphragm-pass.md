# M6 격벽 PASS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 모델링 에이전트가 격벽 섹션을 정답과 같게(보강재 3D 배치까지) 만들어 채점 PASS 를 내도록, 프롬프트 정보(스펙 필드 의미·KB 규약·의미 있는 피드백·자기 렌더)와 잡 예산 입력을 보강한다.

**Architecture:** 설계서 `docs/superpowers/specs/2026-09-07-m6-diaphragm-pass-design.md`. 변경은 M5 에이전트 모듈(`worker/src/m3d/agent/`)의 입력 정보 4곳(스펙 발췌 doc·KB §5·피드백 문장·자기 렌더 3장)과 웹 모달의 예산 입력 1곳이다. 루프·샌드박스·채점 기준·모델·시도 수는 그대로 둔다(D6). 정답 렌더·정답 코드는 LLM 에 주지 않는다(D4·D8).

**Tech Stack:** Python 3.12 (`worker/.venv`), pydantic 2, trimesh, matplotlib(Agg), anthropic SDK(Sonnet 5), pytest; React 18 + Mantine 8 + vitest; Supabase(Postgres `jobs`).

## Global Constraints

- 실증 API 지출: M6 증분 ≤ **$8** — `usage.jsonl` stage `model-agent` 누적 상한 **$9.39**(M5 $1.39 포함). 잡은 웹에서 예산 9.39 로 만든다. 잡 ≤ 3(D7), 잡당 시도 ≤ 4.
- 모델 `claude-sonnet-5`, thinking 비활성, `max_tokens` 16,000, `MAX_ATTEMPTS` 4 — 바꾸지 않는다(D6).
- LLM 에 정답 렌더·정답 코드를 주지 않는다. 자기 렌더는 **에이전트 섹션 GLB 만**으로 만든다.
- 비밀값(`.env`·키)은 출력·커밋 금지. 참조 원본 `D:\Projects\Inspection\...` 읽기 전용.
- 한국어 주석·문서. 새 파일은 UTF-8. 워커 명령은 `export PYTHONUTF8=1` 뒤에 실행.
- 테스트 명령: 워커 `cd worker && .venv/Scripts/python.exe -m pytest -q`, 웹 `cd web && npm test -- --run` 과 `npm run typecheck`. 실증 워커 `cd worker && .venv/Scripts/m3d.exe worker --once`.
- 브랜치 `feat/m6-diaphragm-pass`(main a42ee50 분기). 커밋 메시지 끝에 `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- 완료 주장 전 실제 실행 출력으로 검증(전역 규칙 2).

## 파일 구조

| 파일 | 책임 | 작업 |
|---|---|---|
| `worker/src/m3d/model/spec.py` | ModelSpec — 격벽·받침 필드에 description | Task 1 |
| `worker/src/m3d/agent/context.py` | 프롬프트 묶음 — 발췌 doc, 계약 문구, critique 이미지 블록 | Task 1·5 |
| `docs/모델링규칙_지식베이스_v0.md` | 정본 규칙 — §5 보강재 규약 2줄 | Task 2 |
| `worker/src/m3d/agent/score.py` | 채점 — 축별 델타 `axes`, 피드백 문장 | Task 3 |
| `worker/src/m3d/agent/critique.py` (신규) | 자기 렌더 — 섹션별 뷰 표, `render_views` | Task 4 |
| `worker/src/m3d/agent/loop.py` | 잡 루프 — FAIL 뒤 critique 생성·다음 번들 전달·attempts 기록 | Task 5 |
| `web/src/lib/jobs.ts`, `web/src/routes/Model.tsx` | 잡 생성 payload 예산, 모달 NumberInput | Task 6 |
| `worker/tests/test_model_spec.py`, `test_agent_context.py`, `test_agent_score.py`, `test_agent_critique.py`(신규), `test_agent_loop.py`, `web/src/lib/jobs.test.ts` | 검증 | 각 Task |
| `data/derived/ab1-p4p5/model/acceptance-m6.md`(gitignored), `README.md` | 판정서·문서 | Task 7 |

---

### Task 1: 스펙 필드 설명 + 발췌 `doc` + 계약 문구

**Files:**
- Modify: `worker/src/m3d/model/spec.py:52-70` (Diaphragm), `:174-176` (Bearing.x)
- Modify: `worker/src/m3d/agent/context.py:30-40` (CODE_CONTRACT), `:66-71` (spec_excerpt), `:82-83` (발췌 안내문)
- Test: `worker/tests/test_model_spec.py`, `worker/tests/test_agent_context.py`

**Interfaces:**
- Produces: `Diaphragm.model_fields[k].description: str` (13 필드), `Bearing.model_fields["x"].description`; `context.spec_excerpt(spec_dict, sources) -> dict` 의 각 항목이 `{"value", "source", "doc"?}` (description 없는 필드는 `doc` 키 없음).

- [ ] **Step 1: 실패하는 테스트 작성**

`worker/tests/test_model_spec.py` 끝에 추가:

```python
from m3d.model.spec import Bearing, Diaphragm


def test_diaphragm_and_bearing_fields_carry_descriptions():
    """프롬프트 발췌가 튜플 필드의 의미(축·방향)를 보여줄 수 있어야 한다(M6 D1)."""
    for name, f in Diaphragm.model_fields.items():
        assert f.description, f"Diaphragm.{name} description 없음"
    assert Bearing.model_fields["x"].description
    vs, jk, os_ = (Diaphragm.model_fields[k].description for k in ("support_vstiff", "support_jack", "open_stiff"))
    assert "[x 방향]" in vs and "경간 안쪽 z" in vs and "[A4]" in vs
    assert "t 두께[x]" in jk and "h 높이[y]" in jk
    assert "+z 면에만" in os_ and "[A5]" in os_
```

`worker/tests/test_agent_context.py` 의 `test_spec_excerpt_marks_sources_and_limits_fields` 를 다음으로 교체하고, 파일 상단 import 에 `from m3d.model.spec import Bearing, Diaphragm, ModelSpec` 을 쓴다:

```python
def test_spec_excerpt_marks_sources_docs_and_limits_fields():
    ex = C.spec_excerpt(ModelSpec().model_dump(), SOURCES)
    assert set(ex) == {"coord", "box", "diaphragm", "bearing"}
    assert ex["diaphragm"]["spacing"] == {"value": 2.8, "source": "ssot:C01/다이아프램 간격",
                                          "doc": Diaphragm.model_fields["spacing"].description}
    assert ex["diaphragm"]["support_t"]["source"].startswith("default:")
    assert ex["diaphragm"]["support_jack"]["doc"].startswith("(t 두께[x]")
    assert ex["bearing"]["x"] == {"value": 1.55, "source": "default", "doc": Bearing.model_fields["x"].description}
    assert "doc" not in ex["coord"]["z_p4"]                      # 설명 없는 필드는 키 생략
```

같은 파일 `test_section_bundle_composes_system_and_user_with_feedback` 의 `assert '"source": "ssot:C01/다이아프램 간격"' in text and "참조 차용" in text` 줄 뒤에 추가:

```python
    assert '"doc": "(t 두께[x]' in text and "출처·의미 표시용" in b["system"] and "doc 은 필드 의미" in text
```

- [ ] **Step 2: 실패 확인**

Run: `cd worker && .venv/Scripts/python.exe -m pytest tests/test_model_spec.py::test_diaphragm_and_bearing_fields_carry_descriptions tests/test_agent_context.py -q`
Expected: FAIL — `Diaphragm.spacing description 없음`, `KeyError: 'doc'`/AssertionError.

- [ ] **Step 3: spec.py 에 description**

`worker/src/m3d/model/spec.py` 의 `class Diaphragm` 본문을 다음으로 교체(값은 그대로):

```python
class Diaphragm(BaseModel):
    """§2 격벽 26면 — P4 + spacing·k. description 은 에이전트 프롬프트의 스펙 발췌 doc 이 된다(M6 D1)."""
    spacing: float = Field(2.8, description="격벽 간격(m) — 전역 체인 z = z_p4 + k·spacing")
    n_cell: int = Field(25, description="격실 수 — 격벽 수 = n_cell + 1 (01 = P4 받침선, 마지막 = P5 받침선)")
    support_t: float = Field(0.038, description="지점 격벽(01·마지막) 판 두께(m, z 방향) — 판면 한쪽이 받침선 z 에 놓이고 두께는 경간 안쪽으로")
    support_open: tuple[float, float] = Field((0.7, 0.7), description="(폭 x, 높이 y) 지점 격벽 개구(m), 개구는 x 중심")
    support_sill: float = Field(0.45, description="지점 격벽 개구 문턱 높이(m) — 하판 상면 y_web_bot(z) 기준")
    support_vstiff: tuple[float, float, int] = Field(
        (0.026, 0.24, 12),
        description="(t 두께[x 방향], w 돌출[판면에서 경간 안쪽 z], n 총 개수) 지점 격벽 수직보강재 — 내공 전 높이; "
                    "참조 단순화 [A4]: 경간 안쪽 면에만 받침 x·x±0.2 의 3열 × 좌우 = 6")
    support_jack: tuple[float, float, float] = Field(
        (0.022, 0.35, 1.15),
        description="(t 두께[x], w 돌출[판면에서 경간 안쪽 z], h 높이[y]) 지점 격벽 잭업보강재 — 받침 x 직상(상판 밑 h)·직하(하판 위 h) 각 1 × 좌우 = 4, "
                    "경간 안쪽 면에만")
    interior_t: float = Field(0.010, description="일반 격벽 판 두께(m, z) — 두께 중심을 체인 위치에")
    interior_open: tuple[float, float] = Field((1.4, 1.4), description="(폭 x, 높이 y) 일반 격벽 개구(m), x 중심")
    sill_cl: float = Field(0.45, description="CL 계열 일반 격벽 개구 문턱(m, y_web_bot 기준)")
    sill_cx: float = Field(0.40, description="CX 계열 일반 격벽 개구 문턱(m)")
    h_table: list[tuple[float, float]] = Field(
        [(2.8, 3.739), (5.6, 3.349), (8.4, 3.063), (11.2, 2.881), (14.0, 2.803)],
        description="(받침선으로부터 거리 d, 격벽 높이) 판독 대조값 — 판 높이는 ctx 내공(y_web_bot~y_web_top)에서 유도하고 이 표는 검산용")
    type_map: list[tuple[float, str]] = Field(
        [(2.8, "CL"), (5.6, "CL3"), (8.4, "CL6"), (11.2, "CL7"), (14.0, "CX"), (16.8, "CX1"), (19.6, "CX1"), (22.4, "CX1")],
        description="(받침선으로부터 거리 d, 타입명) — dmin = 양 받침선까지 최소 거리; CX 로 시작하는 타입의 d 범위(min−0.1 < dmin < max+0.1) 이면 sill_cx, "
                    "아니면 sill_cl")
    open_stiff: tuple[float, float, float, float] = Field(
        (0.010, 0.100, 0.090, 1.56),
        description="(t 판두께, h_h 상·하변 돌출[z], h_v 좌·우변 돌출[z], l 길이) 일반 격벽 개구보강재 — 개구 4변 바깥에 붙여 판의 +z 면에만 돌출(참조 단순화 [A5]); "
                    "상·하변은 x 중심 길이 l·두께 t 를 y 로, 좌·우변은 y 중심 길이 l·두께 t 를 x 로")
```

`class Bearing` 의 `x: float = 1.55` 를 `x: float = Field(1.55, description="받침 중심 x(m) — 좌우 대칭 ±x")` 로.

- [ ] **Step 4: context.py 발췌 doc + 계약·안내 문구**

`worker/src/m3d/agent/context.py`: import 에 `from m3d.model.spec import ModelSpec` 추가. `spec_excerpt` 를 교체:

```python
def _field_doc(sec: str, key: str) -> str | None:
    """ModelSpec 하위 모델의 Field description — 프롬프트 발췌의 doc(M6 D1)."""
    sub = ModelSpec.model_fields[sec].annotation
    f = getattr(sub, "model_fields", {}).get(key)
    return f.description if f is not None else None


def _entry(sec: str, key: str, value, sources: dict) -> dict:
    entry = {"value": value, "source": sources.get(f"{sec}.{key}", "default")}
    doc = _field_doc(sec, key)
    if doc:
        entry["doc"] = doc
    return entry


def spec_excerpt(spec_dict: dict, sources: dict) -> dict:
    out = {sec: {k: _entry(sec, k, v, sources) for k, v in spec_dict[sec].items()} for sec in SPEC_SECTIONS}
    out["bearing"] = {"x": _entry("bearing", "x", spec_dict["bearing"]["x"], sources)}
    return out
```

`CODE_CONTRACT` 의 두 줄

```
- 코드 인자 spec 에는 **값만** 들어 있다: … h_table == [[2.8, 3.739], ...].
  아래 'ModelSpec 발췌' 의 {"value", "source"} 포장은 출처 표시용이며 코드에서는 ["value"] 로 접근하지 않는다.
```

의 둘째 줄을 다음으로:

```
  아래 'ModelSpec 발췌' 의 {"value", "source", "doc"} 포장은 출처·의미 표시용이며 코드에서는 ["value"] 로 접근하지 않는다. doc 의 [x]·[y]·[z] 는 그 성분이 뻗는 축이다.
```

`section_bundle` 의 발췌 안내문을 `"ModelSpec 발췌 (m 단위; source 가 ssot: 이면 판독 확정값, default 는 참조 차용 — 도면으로 확인할 것; doc 은 필드 의미):\n"` 로.

- [ ] **Step 5: 통과 확인**

Run: `cd worker && .venv/Scripts/python.exe -m pytest tests/test_model_spec.py tests/test_agent_context.py tests/test_model_builder.py tests/test_model_compare.py -q`
Expected: 전부 PASS (Field 로 바꿔도 기본값·빌드 결과 불변 — `test_model_builder` 가 정답 GLB 대조로 보증).

- [ ] **Step 6: Commit**

```bash
git add worker/src/m3d/model/spec.py worker/src/m3d/agent/context.py worker/tests/test_model_spec.py worker/tests/test_agent_context.py
git commit -m "feat(agent): 스펙 격벽·받침 필드 description → 프롬프트 발췌 doc (튜플 의미·축·편측 규약)"
```

---

### Task 2: KB §5 보강재 규약

**Files:**
- Modify: `docs/모델링규칙_지식베이스_v0.md:63-64` (§5 마지막 항목 뒤)
- Test: `worker/tests/test_agent_context.py`

**Interfaces:**
- Produces: 시스템 프롬프트(`section_bundle()["system"]`)에 "보강재 방향 규약"·"편측 부착 단순화" 문단(`kb_excerpt` 가 §5 를 그대로 싣는다).

- [ ] **Step 1: 실패하는 테스트**

`worker/tests/test_agent_context.py` 끝에:

```python
def test_bundle_system_carries_stiffener_conventions_from_kb():
    """KB §5 의 보강재 규약(M6 D2)이 실제 파일에서 시스템 프롬프트로 들어온다."""
    b = C.section_bundle("P4P5/DIA", spec_dict=ModelSpec().model_dump(), sources={}, evidence=[], crops=[])
    assert "보강재 방향 규약" in b["system"] and "편측 부착 단순화" in b["system"]
    assert "[A4]·[A5]" in b["system"] and "노드 bbox 는 판+보강재 전체 범위" in b["system"]
```

- [ ] **Step 2: 실패 확인**

Run: `cd worker && .venv/Scripts/python.exe -m pytest tests/test_agent_context.py::test_bundle_system_carries_stiffener_conventions_from_kb -q`
Expected: FAIL (AssertionError).

- [ ] **Step 3: KB 에 두 항목 추가**

`docs/모델링규칙_지식베이스_v0.md` §5 의 줄

```
- **세그먼트 단위 진행 + 승인 게이트**: 대표 구간 시범 → 사용자 승인 → 확산.
  내부(격실·보강재)까지 모델링하는 것이 기본이다.
```

바로 뒤(빈 줄 앞)에 삽입:

```
- **보강재 방향 규약**: 판 보강재는 두께 t 를 판면 안 방향(격벽이면 x), 돌출 w 를 판면 법선
  방향(격벽이면 z)으로 판면에서 뻗는다. 판 두께는 스펙값 그대로 두고, 보강재는 별도 솔리드로
  판면에 INS 만큼 물려 같은 노드에 합친다.
- **편측 부착 단순화**: 지점 격벽의 수직·잭업보강재는 경간 안쪽 면에만, 일반 격벽의 개구보강재는
  +z 면에만 둔다(참조 빌더 [A4]·[A5]). 노드 bbox 는 판+보강재 전체 범위다.
```

- [ ] **Step 4: 통과 확인**

Run: `cd worker && .venv/Scripts/python.exe -m pytest tests/test_agent_context.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/모델링규칙_지식베이스_v0.md worker/tests/test_agent_context.py
git commit -m "docs(kb): §5 보강재 방향 규약·편측 부착 단순화 — 에이전트 프롬프트에 자동 반영"
```

---

### Task 3: 피드백 문장 — 축별 델타 `axes` + 의미 표기

**Files:**
- Modify: `worker/src/m3d/agent/score.py:42-49` (worst_detail), `:70-91` (feedback_text)
- Test: `worker/tests/test_agent_score.py`

**Interfaces:**
- Consumes: `score_section()` 결과 dict(현행 키).
- Produces: `worst_detail[i]["axes"] = [{"axis": "x|y|z", "bound": "min|max", "ours": float, "ref": float, "delta_mm": int}]` (|정답−우리| > 5 mm 인 것만); `feedback_text(score) -> str` 형식은 설계서 §3.3.

- [ ] **Step 1: 실패하는 테스트**

`worker/tests/test_agent_score.py` 의 `test_missing_and_shifted_nodes_fail_with_feedback` 마지막 `json.dumps(sc)` 앞에 추가:

```python
    wd = sc["compare"]["worst_detail"]
    assert wd[0]["node"] == "AB1_S5_DIA03"
    assert {(a["axis"], a["bound"], a["delta_mm"]) for a in wd[0]["axes"]} == {("z", "min", -20), ("z", "max", -20)}
    assert "노드 bbox = 그 노드에 합친 모든 솔리드" in fb
    assert "AB1_S5_DIA03: z 최소" in fb and "정답이 -z 쪽으로 20mm 더 뻗음" in fb and "우리가 +z 쪽으로 20mm 더 뻗음(초과)" in fb
    assert "판면 정점이 체인 위치 ±10mm 에 없다" in fb and "바꾸지 말 것" not in fb
```

파일 끝에 순수 형식 테스트:

```python
def test_feedback_hints_plate_ok_when_checks_pass():
    """판 검사(체인·결합·재실측)가 통과했으면 '판을 바꾸지 말 것' 힌트, 체인 힌트는 없음(M6 D3)."""
    sc = {"pass": False,
          "compare": {"only_ours": [], "only_ref": [], "common": 26, "bbox_dev_max_m": 0.326, "bbox_dev_over_1mm": 2, "faces_equal": False,
                      "worst": [{"node": "AB1_S5_DIA01", "dev_m": 0.326}],
                      "worst_detail": [{"node": "AB1_S5_DIA01", "ours": [[-2.239, 15.636, -525.0], [2.239, 19.646, -524.936]],
                                        "ref": [[-2.239, 15.636, -525.0], [2.239, 19.646, -524.61]],
                                        "axes": [{"axis": "z", "bound": "max", "ours": -524.936, "ref": -524.61, "delta_mm": 326}]}]},
          "section_selfcheck": {"pass": 5, "fail": 0, "failed": []}, "assembled_selfcheck": {"pass": 24, "fail": 0, "failed": []},
          "measure": {"PASS": 47, "FAIL": 0, "INFO": 2, "failed": []}}
    fb = S.feedback_text(sc)
    assert fb.splitlines()[0] == "채점: FAIL"
    assert "(노드 bbox = 그 노드에 합친 모든 솔리드 — 판+보강재 — 의 전체 범위이며 판 두께가 아니다)" in fb
    assert "  AB1_S5_DIA01: z 최대 -524.936 → 정답 -524.61 — 정답이 +z 쪽으로 326mm 더 뻗음" in fb
    assert "판 두께·위치는 검사를 통과했으니 바꾸지 말 것" in fb and "체인 위치 ±10mm 에 없다" not in fb
```

- [ ] **Step 2: 실패 확인**

Run: `cd worker && .venv/Scripts/python.exe -m pytest tests/test_agent_score.py -q`
Expected: 2 FAIL (`KeyError: 'axes'`, AssertionError).

- [ ] **Step 3: score.py 구현**

`score_section` 의 `worst_detail` 루프를 교체:

```python
    ref_named = load_named(ref_glb)
    worst_detail = []
    for w in cmp["worst"][:4]:
        if w["dev_m"] <= BBOX_TOL_M or w["node"] not in agent_named or w["node"] not in ref_named:
            continue
        a, r = agent_named[w["node"]].bounds, ref_named[w["node"]].bounds
        axes = []
        for i, ax in enumerate("xyz"):
            for bound, idx in (("min", 0), ("max", 1)):
                o, rf = float(a[idx][i]), float(r[idx][i])
                if abs(rf - o) > BBOX_TOL_M:
                    axes.append({"axis": ax, "bound": bound, "ours": round(o, 3), "ref": round(rf, 3), "delta_mm": int(round((rf - o) * 1000))})
        worst_detail.append({"node": w["node"], "ours": [[round(float(v), 3) for v in a[0]], [round(float(v), 3) for v in a[1]]],
                             "ref": [[round(float(v), 3) for v in r[0]], [round(float(v), 3) for v in r[1]]], "axes": axes})
```

`feedback_text` 를 교체:

```python
BBOX_NOTE = "(노드 bbox = 그 노드에 합친 모든 솔리드 — 판+보강재 — 의 전체 범위이며 판 두께가 아니다)"
PLATE_OK_HINT = "판 두께·위치는 검사를 통과했으니 바꾸지 말 것 — 차이는 판면에 붙는 부속 솔리드(보강재 등)의 유무·방향·돌출 크기에서 난다."
CHAIN_HINT = "판면 정점이 체인 위치 ±10mm 에 없다 — 판 두께 중심(지점 격벽은 받침선 쪽 판면)을 체인 z 에 두고 두께는 스펙값만큼만."


def _delta_phrase(e: dict) -> str:
    """축별 델타 한 구절 — 누가 어느 쪽으로 얼마나 더 뻗었는지(설계서 §3.3)."""
    d, ax = e["delta_mm"], e["axis"]
    if e["bound"] == "max":
        return f"정답이 +{ax} 쪽으로 {d}mm 더 뻗음" if d > 0 else f"우리가 +{ax} 쪽으로 {-d}mm 더 뻗음(초과)"
    return f"정답이 -{ax} 쪽으로 {-d}mm 더 뻗음" if d < 0 else f"우리가 -{ax} 쪽으로 {d}mm 더 뻗음(초과)"


def feedback_text(score: dict) -> str:
    """다음 시도 프롬프트용 — 무엇이 어긋났는지 노드명·축·mm 로, 숫자마다 의미를 붙여서(M6 D3)."""
    c = score["compare"]
    if score["pass"]:
        return "채점: PASS"
    lines = ["채점: FAIL", BBOX_NOTE]
    if c["only_ref"]:
        lines.append("빠진 노드(정답에는 있음): " + ", ".join(c["only_ref"][:30]))
    if c["only_ours"]:
        lines.append("남는 노드(정답에 없음): " + ", ".join(c["only_ours"][:30]))
    worst = [w for w in c["worst"] if w["dev_m"] > BBOX_TOL_M]
    if worst:
        lines.append("정답 대비 bbox 편차 상위: " + ", ".join(f"{w['node']} {w['dev_m'] * 1000:.0f}mm" for w in worst[:8]))
    for d in c.get("worst_detail", []):
        for e in d.get("axes", [])[:6]:
            lines.append(f"  {d['node']}: {e['axis']} {'최대' if e['bound'] == 'max' else '최소'} {e['ours']} → 정답 {e['ref']} — {_delta_phrase(e)}")
    failed = score["section_selfcheck"]["failed"] + score["assembled_selfcheck"]["failed"]
    checks_ok = (score["section_selfcheck"]["fail"] == 0 and score["assembled_selfcheck"]["fail"] == 0 and score["measure"]["FAIL"] == 0)
    if worst and checks_ok:
        lines.append(PLATE_OK_HINT)
    if any("z 체인" in f for f in failed):
        lines.append(CHAIN_HINT)
    for key, label in (("section_selfcheck", "섹션 self-check 실패"), ("assembled_selfcheck", "결합 self-check 실패")):
        if score[key]["failed"]:
            lines.append(label + ": " + " | ".join(score[key]["failed"][:8]))
    if score["measure"]["failed"]:
        lines.append("재실측 실패 항목: " + " | ".join(score["measure"]["failed"][:8]))
    return "\n".join(lines)
```

- [ ] **Step 4: 통과 확인**

Run: `cd worker && .venv/Scripts/python.exe -m pytest tests/test_agent_score.py tests/test_agent_loop.py -q`
Expected: PASS (루프 테스트의 가짜 채점 dict 에는 `worst_detail` 이 없어도 `.get` 으로 동작).

- [ ] **Step 5: Commit**

```bash
git add worker/src/m3d/agent/score.py worker/tests/test_agent_score.py
git commit -m "feat(agent): 채점 피드백에 축별 델타·bbox 의미·판 유지/체인 힌트 — 범위를 두께로 오독하지 않게"
```

---

### Task 4: 자기 렌더 `agent/critique.py`

**Files:**
- Create: `worker/src/m3d/agent/critique.py`
- Test: `worker/tests/test_agent_critique.py`

**Interfaces:**
- Consumes: `m3d.model.render.load_nodes(glb) -> [(name, mesh, color)]`, `render.to_tris(nodes) -> (V, F, C)`, `render.render(V, F, C, eye, up, out, title, size=, dpi=, extra=) -> Path`, `render.Y_UP`.
- Produces: `render_views(agent_glb: Path, spec: ModelSpec, code: str, out_dir: Path) -> list[dict]` — 각 `{"path": Path, "caption": str}`; 뷰 표 `VIEWS[code]`; 노드 없는 뷰는 건너뛰고 미등록 섹션은 `[]`.

- [ ] **Step 1: 실패하는 테스트**

`worker/tests/test_agent_critique.py`:

```python
"""자기 렌더 (M6 D4) — 에이전트 섹션 GLB 만으로 뷰 표대로 PNG 를 만든다. 정답 렌더가 아니다."""

import pytest
from PIL import Image

from m3d.agent import critique as K
from m3d.agent.score import load_named
from m3d.model import sections as X
from m3d.model.builder import Builder
from m3d.model.spec import ModelSpec


@pytest.fixture(scope="module")
def dia_glb(tmp_path_factory):
    d = tmp_path_factory.mktemp("ref")
    spec = ModelSpec()
    b = Builder(spec)
    b.export_sections(X.split(b.build(pilot=False), spec.coord.segment), d)
    return d / "sections" / "P4P5" / "DIA.glb"


def test_dia_views_render_three_pngs_with_captions(dia_glb, tmp_path):
    out = K.render_views(dia_glb, ModelSpec(), "DIA", tmp_path / "crit")
    assert [v["path"].name for v in out] == ["dia01_front.png", "dia01_side.png", "dia13_iso.png"]
    for v in out:
        assert v["path"].is_file() and v["caption"].startswith("이전 시도")
        with Image.open(v["path"]) as im:
            assert max(im.size) <= 1100
    assert "경간 안쪽" in out[1]["caption"] and "+z 면" in out[2]["caption"]


def test_views_skip_missing_nodes_and_unknown_section(dia_glb, tmp_path):
    only13 = {"AB1_S5_DIA13": load_named(dia_glb)["AB1_S5_DIA13"]}
    glb = tmp_path / "one.glb"
    Builder(ModelSpec()).export(only13, glb)
    out = K.render_views(glb, ModelSpec(), "DIA", tmp_path / "crit1")
    assert [v["path"].name for v in out] == ["dia13_iso.png"]
    assert K.render_views(dia_glb, ModelSpec(), "FRM", tmp_path / "crit2") == []
```

- [ ] **Step 2: 실패 확인**

Run: `cd worker && .venv/Scripts/python.exe -m pytest tests/test_agent_critique.py -q`
Expected: FAIL — `ModuleNotFoundError: m3d.agent.critique`.

- [ ] **Step 3: 구현**

`worker/src/m3d/agent/critique.py`:

```python
"""자기 렌더 피드백 (M6 D4) — 채점에 실패한 시도의 섹션 GLB 만으로 몇 장 렌더해 다음 시도 프롬프트에 붙인다.

정답 렌더는 주지 않는다. LLM 은 자기 결과 그림을 도면 크롭·규칙과 비교해 방향·돌출·개구를 스스로 고친다.
그림 제목은 짧게(figure), 프롬프트 캡션은 길게(caption) — 긴 제목은 tight bbox 로 그림 폭만 키운다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from m3d.model import render
from m3d.model.spec import ModelSpec

DPI = 100
VIEWS: dict[str, list[dict]] = {
    "DIA": [
        {"name": "dia01_front", "nodes": ("AB1_S5_DIA01",), "eye": (0, 0, 1), "size": (8, 6),
         "title": "DIA01 정면(+z 에서, 좌=−x)",
         "caption": "이전 시도 DIA01 정면 — +z(경간 안쪽)에서 본 판면·개구·보강재, 화면 좌 = −x"},
        {"name": "dia01_side", "nodes": ("AB1_S5_DIA01",), "eye": (1, 0, 0), "size": (5, 10), "chain": "z_p4",
         "title": "DIA01 측면(+x 에서, 좌=+z)",
         "caption": "이전 시도 DIA01 측면 — +x 에서, 화면 좌 = +z(경간 안쪽), 점선 = 체인 z_p4; 보강재 돌출은 판면에서 왼쪽으로 보여야 한다"},
        {"name": "dia13_iso", "nodes": ("AB1_S5_DIA13",), "eye": (0.7, 0.45, 0.85), "size": (8, 6),
         "title": "DIA13 아이소(+x+y+z 에서)",
         "caption": "이전 시도 DIA13 아이소 — +x+y+z 에서, 개구보강재는 +z 면"},
    ],
}


def _chain_marker(z_chain: float, y_lo: float, y_hi: float):
    """측면 뷰에 체인 위치 점선과 경간 안쪽 방향 표시 — render() 의 extra(ax, right, upv) 훅."""
    def extra(ax, right, upv):
        x = float(np.dot(np.array([0.0, 0.0, z_chain]), right))
        ax.plot([x, x], [y_lo - 0.2, y_hi + 0.2], "--", color="#c0392b", linewidth=0.9)
        ax.text(x, y_hi + 0.25, "← 경간 안쪽(+z)   체인 z_p4", fontsize=8, color="#c0392b", ha="center")
    return extra


def render_views(agent_glb: Path, spec: ModelSpec, code: str, out_dir: Path) -> list[dict]:
    """섹션 코드의 뷰 표대로 PNG 를 만들고 [{"path", "caption"}] 를 돌려준다. 노드가 없는 뷰는 건너뛴다."""
    views = VIEWS.get(code, [])
    if not views:
        return []
    by_name = {n: (n, m, c) for n, m, c in render.load_nodes(Path(agent_glb))}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []
    for v in views:
        sel = [by_name[n] for n in v["nodes"] if n in by_name]
        if not sel:
            continue
        V, F, C = render.to_tris(sel)
        extra = None
        if v.get("chain") == "z_p4":
            extra = _chain_marker(spec.coord.z_p4, float(V[:, 1].min()), float(V[:, 1].max()))
        path = render.render(V, F, C, v["eye"], render.Y_UP, out_dir / (v["name"] + ".png"), v["title"],
                             size=v["size"], dpi=DPI, extra=extra)
        out.append({"path": Path(path), "caption": v["caption"]})
    return out
```

- [ ] **Step 4: 통과 확인 + 육안**

Run: `cd worker && .venv/Scripts/python.exe -m pytest tests/test_agent_critique.py -q`
Expected: PASS. 이어서 실제 정답 격벽으로 한 번 그려 눈으로 본다(측면 뷰에서 보강재가 판면 왼쪽(+z)으로 돌출해야 정상):

```bash
cd worker && export PYTHONUTF8=1 && .venv/Scripts/python.exe -c "
from pathlib import Path
from m3d.agent.critique import render_views
from m3d.model.spec import ModelSpec
print(render_views(Path('../data/derived/ab1-p4p5/model/sections/P4P5/DIA.glb'), ModelSpec(), 'DIA', Path('../data/derived/ab1-p4p5/model/agent/critique-preview')))"
```

Read 툴로 3장을 열어 확인(제목·방향·점선). 확인 결과를 커밋 메시지에 한 줄로.

- [ ] **Step 5: Commit**

```bash
git add worker/src/m3d/agent/critique.py worker/tests/test_agent_critique.py
git commit -m "feat(agent): 자기 렌더 critique — 실패 시도의 격벽 3뷰(정면·측면 체인선·아이소) PNG"
```

---

### Task 5: 루프·번들에 자기 렌더 통합

**Files:**
- Modify: `worker/src/m3d/agent/context.py:74-103` (section_bundle)
- Modify: `worker/src/m3d/agent/loop.py:12-16` (import), `:110-166` (run_job)
- Test: `worker/tests/test_agent_context.py`, `worker/tests/test_agent_loop.py`

**Interfaces:**
- Consumes: Task 4 `critique.render_views(agent_glb, spec, code, out_dir) -> [{"path", "caption"}]`.
- Produces: `section_bundle(..., critique: list[dict] | None = None)` — 피드백 뒤에 안내문 + (캡션, 이미지)×n, `n_images` = 크롭 + 렌더, digest 에 렌더 파일 해시 포함; `run_job(..., critic=None)` — FAIL 시도 뒤 `work/agent/critique<n>/` 렌더, `attempts[i]["critique"] = [파일명]`, 다음 번들에 전달; 실행 오류 시도 뒤에는 렌더 없음.

- [ ] **Step 1: 실패하는 테스트**

`worker/tests/test_agent_context.py` 의 `test_section_bundle_composes_system_and_user_with_feedback` 에서 `b = C.section_bundle(...)` 호출 앞에 렌더 파일을 만들고 인자를 추가:

```python
    crit_img = tmp_path / "dia01_side.png"
    Image.new("RGB", (500, 900), "white").save(crit_img)
    critique = [{"path": crit_img, "caption": "이전 시도 DIA01 측면 — +x 에서, 화면 좌 = +z(경간 안쪽)"}]
    b = C.section_bundle("P4P5/DIA", spec_dict=ModelSpec().model_dump(), sources=SOURCES, evidence=[], crops=crops,
                         feedback="only_ref: AB1_S5_DIA26", request="개구를 1.4×1.4 로", prev_code="def build_section(spec, ctx):\n    return {}",
                         critique=critique)
```

그리고 기존 단언 `assert kinds.count("image") == 1 and b["n_images"] == 1` 을 `== 2` 로 바꾸고, 뒤에 추가:

```python
    assert "이전 시도 결과 렌더(자기검토용)" in text and "렌더: 이전 시도 DIA01 측면" in text
    assert text.index("이전 시도의 실행 오류·채점") < text.index("이전 시도 결과 렌더(자기검토용)") < text.index("사용자 요청")
    b3 = C.section_bundle("P4P5/DIA", spec_dict=ModelSpec().model_dump(), sources=SOURCES, evidence=[], crops=crops,
                          feedback="only_ref: AB1_S5_DIA26", request="개구를 1.4×1.4 로", prev_code="def build_section(spec, ctx):\n    return {}")
    assert b3["digest"] != b["digest"] and b3["n_images"] == 1
```

`worker/tests/test_agent_loop.py` 의 `test_loop_retries_with_feedback_then_passes_and_builds_agent_dir` 에서 `assert "AB1_S5_DIA26" in calls[2]["text"] ...` 줄 뒤에 추가:

```python
    assert calls[1]["n_images"] == 0 and calls[2]["n_images"] == 3                    # 실행 오류 뒤엔 렌더 없음, 채점 실패 뒤엔 3장
    assert "이전 시도 결과 렌더(자기검토용)" in calls[2]["text"] and "렌더: 이전 시도 DIA01 측면" in calls[2]["text"]
    crit_dir = cfg.derived_dir / "ds" / "model" / "agent" / "job-1" / "agent" / "critique2"
    assert sorted(p.name for p in crit_dir.glob("*.png")) == ["dia01_front.png", "dia01_side.png", "dia13_iso.png"]
```

같은 테스트의 `attempts` 단언 뒤에:

```python
    assert "critique" not in attempts[0] and attempts[1]["critique"] == ["dia01_front.png", "dia01_side.png", "dia13_iso.png"] and "critique" not in attempts[2]
```

- [ ] **Step 2: 실패 확인**

Run: `cd worker && .venv/Scripts/python.exe -m pytest tests/test_agent_context.py tests/test_agent_loop.py -q`
Expected: FAIL — `TypeError: section_bundle() got an unexpected keyword argument 'critique'`, `n_images` 0 ≠ 3.

- [ ] **Step 3: context.py — critique 블록**

`section_bundle` 서명에 `critique: list[dict] | None = None` 을 `prev_code` 뒤에 추가하고, `if feedback:` 블록 뒤·`if request:` 앞에:

```python
    if critique:
        parts.append({"type": "text", "text": "이전 시도 결과 렌더(자기검토용): 도면 크롭·규칙과 비교해 판면 방향·보강재 돌출 방향과 크기·개구 위치를 "
                                              "스스로 확인하고 고쳐라. 정답 렌더가 아니라 방금 만든 결과다."})
        for c in critique:
            parts.append({"type": "text", "text": "렌더: " + c["caption"]})
            parts.append(image_block(Path(c["path"])))
```

digest 루프 `for c in crops: h.update(sha256_file(...))` 뒤에 `for c in (critique or []): h.update(sha256_file(Path(c["path"])).encode("ascii"))`, 반환의 `"n_images": len(crops) + len(critique or [])`.

- [ ] **Step 4: loop.py — critic 주입·기록**

import 에 `from m3d.agent import critique as agent_critique`. `run_job` 서명에 `critic=None` 을 `do_render` 앞에 추가하고 본문 첫 줄들에 `critic = critic or agent_critique.render_views`. 루프 변수 초기화를 `feedback, critique, attempts, cost, last, bundle = None, None, [], 0.0, None, None` 로. `section_bundle(...)` 호출에 `critique=critique` 추가. 실행 실패 분기(`if not res.ok:`)의 `feedback = ...` 다음에 `critique = None`. 채점 실패 뒤 `feedback = agent_score.feedback_text(sc)` 다음에:

```python
        critique = critic(res.glb, spec, code, work / "agent" / f"critique{attempt}")
        if critique:
            attempts[-1]["critique"] = [Path(c["path"]).name for c in critique]
        emit("info", f"시도 {attempt}: 자기 렌더 {len(critique)}장")
```

- [ ] **Step 5: 통과 확인**

Run: `cd worker && .venv/Scripts/python.exe -m pytest tests/test_agent_context.py tests/test_agent_loop.py tests/test_agent_worker.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add worker/src/m3d/agent/context.py worker/src/m3d/agent/loop.py worker/tests/test_agent_context.py worker/tests/test_agent_loop.py
git commit -m "feat(agent): 채점 실패 뒤 자기 렌더 3장을 다음 시도 프롬프트에 첨부 — attempts.json·critique<n>/ 기록"
```

---

### Task 6: 웹 예산 입력

**Files:**
- Modify: `web/src/lib/jobs.ts:17-22` (jobPayload), `web/src/routes/Model.tsx:5-6` (import), `:51` (state), `:148-157` (submitJob), `:261-263` (onRevise), `:269-279` (modal)
- Test: `web/src/lib/jobs.test.ts`

**Interfaces:**
- Produces: `DEFAULT_BUDGET_USD = 5`; `jobPayload({..., budgetUsd?: number}) -> JobInsert` 가 `budget_usd`(0.5~50, 아니면 RangeError) 포함.

- [ ] **Step 1: 실패하는 테스트**

`web/src/lib/jobs.test.ts` 의 `describe('jobPayload')` 첫 테스트를 교체하고 하나 추가:

```ts
  it('정상 — request trim, parent 선택, 예산 기본 5', () => {
    expect(jobPayload({ projectId: 'p', sectionKey: 'P4P5/DIA', request: ' 개구 1.4 ', parentJobId: null }))
      .toEqual({ project_id: 'p', kind: 'model-section', section_key: 'P4P5/DIA', request: '개구 1.4', parent_job_id: null, budget_usd: 5 });
    expect(jobPayload({ projectId: 'p', sectionKey: 'P4P5/DIA', request: '', parentJobId: 'j0', budgetUsd: 9.39 }))
      .toMatchObject({ parent_job_id: 'j0', budget_usd: 9.39 });
  });
  it('예산 상한은 0.5~50 달러', () => {
    expect(() => jobPayload({ projectId: 'p', sectionKey: 'P4P5/DIA', request: '', parentJobId: null, budgetUsd: 0 })).toThrow(RangeError);
    expect(() => jobPayload({ projectId: 'p', sectionKey: 'P4P5/DIA', request: '', parentJobId: null, budgetUsd: 60 })).toThrow(RangeError);
    expect(() => jobPayload({ projectId: 'p', sectionKey: 'P4P5/DIA', request: '', parentJobId: null, budgetUsd: Number.NaN })).toThrow(RangeError);
  });
```

import 줄에 `DEFAULT_BUDGET_USD` 를 추가하고 `it('M5 는 격벽만', …)` 뒤에 `it('기본 예산 5', () => { expect(DEFAULT_BUDGET_USD).toBe(5); });`.

- [ ] **Step 2: 실패 확인**

Run: `cd web && npm test -- --run src/lib/jobs.test.ts`
Expected: FAIL (`budget_usd` 없음, RangeError 아님, DEFAULT_BUDGET_USD undefined).

- [ ] **Step 3: jobs.ts**

```ts
export const DEFAULT_BUDGET_USD = 5;                          // DB 기본값과 같다(0006_jobs.sql)
const BUDGET_RANGE: [number, number] = [0.5, 50];

export function jobPayload(p: { projectId: string; sectionKey: string; request: string; parentJobId: string | null; budgetUsd?: number }): JobInsert {
  if (!SECTION_RE.test(p.sectionKey)) throw new RangeError(`섹션 키 형식 오류: ${p.sectionKey}`);
  const request = p.request.trim();
  if (request.length > 2000) throw new RangeError('요청은 2,000자 이내');
  const budget = p.budgetUsd ?? DEFAULT_BUDGET_USD;
  if (!Number.isFinite(budget) || budget < BUDGET_RANGE[0] || budget > BUDGET_RANGE[1]) throw new RangeError(`예산 상한은 ${BUDGET_RANGE[0]}~${BUDGET_RANGE[1]} 달러`);
  return { project_id: p.projectId, kind: 'model-section', section_key: p.sectionKey, request, parent_job_id: p.parentJobId, budget_usd: budget };
}
```

- [ ] **Step 4: Model.tsx**

- Mantine import 에 `NumberInput` 추가; jobs import 에 `DEFAULT_BUDGET_USD` 추가.
- 상태: `const [askBudget, setAskBudget] = useState<number>(DEFAULT_BUDGET_USD);` (askRequest 아래).
- `submitJob(section, request, parentJobId, budgetUsd: number)` 로 서명 확장, `jobPayload({ ..., parentJobId, budgetUsd })`.
- `onRevise`: `void submitJob(target, request, buildJob?.id ?? null, buildJob?.budget_usd ?? askBudget);` (수정 요청은 부모 잡 예산 승계).
- 모달 Textarea 아래:

```tsx
          <NumberInput label="예산 상한 ($)" description="이 잡을 포함한 stage 누적 지출이 넘으면 호출 없이 실패 처리" value={askBudget} min={0.5} max={50} step={0.5}
            decimalScale={2} onChange={(v) => setAskBudget(typeof v === 'number' ? v : Number(v) || DEFAULT_BUDGET_USD)} id="job-budget-input" />
```

- 잡 생성 버튼 onClick: `void submitJob(askSection, askRequest, null, askBudget)`.

- [ ] **Step 5: 통과 확인**

Run: `cd web && npm test -- --run && npm run typecheck`
Expected: vitest 전건 PASS(19 → 21), tsc 오류 0.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/jobs.ts web/src/lib/jobs.test.ts web/src/routes/Model.tsx
git commit -m "feat(web): LLM 잡 모달에 예산 상한 입력(기본 5, 0.5~50) → jobs.budget_usd"
```

---

### Task 7: 실증(≤ $8)·판정서·README·통합

**Files:**
- Create: `data/derived/ab1-p4p5/model/acceptance-m6.md` (gitignored)
- Modify: `README.md` "## LLM 모델링 (M5)" 절
- Modify: 메모리 `C:\Users\parkj\.claude\projects\D--Projects-model3d-studio\memory\m5-modeling-agent.md`(+ `MEMORY.md` 한 줄)

- [ ] **Step 1: 전건 테스트**

Run: `cd worker && .venv/Scripts/python.exe -m pytest -q` 그리고 `cd web && npm test -- --run && npm run typecheck`
Expected: pytest 385 → 391 안팎 전건 PASS, vitest 21, tsc 0. 실패가 있으면 여기서 멈추고 고친다.

- [ ] **Step 2: 프롬프트 검토(호출 전, 무과금)**

```bash
cd worker && export PYTHONUTF8=1 && .venv/Scripts/python.exe -c "
from m3d.agent import context as C
from m3d.model import io as model_io
from m3d.config import load_config
cfg = load_config(); raw = model_io.load_modelspec_raw(cfg, 'ab1-p4p5')
b = C.section_bundle('P4P5/DIA', spec_dict=raw['spec'], sources=raw.get('sources', {}), evidence=[], crops=[])
print(len(b['system'])); print('\n'.join(p['text'] for p in b['messages'][0]['content'] if p['type']=='text')[:6000])"
```

시스템 프롬프트에 규약 2줄, 발췌에 `doc` 이 보이는지 확인. 잡 실행 중 프롬프트 문자 수(≈ 16.4k → 19k)를 판정서에 적는다.

- [ ] **Step 3: 잡 1 (요청 없음, 예산 9.39)**

웹(`/p/ab1-p4p5/model`, 로그인 세션)에서 격벽 "LLM 으로 만들기" → 예산 9.39 → 잡 생성. 워커:

```bash
cd worker && export PYTHONUTF8=1 && .venv/Scripts/m3d.exe worker --once
```

이벤트 로그에서 시도별 "채점 PASS/FAIL — … bbox …mm" 와 "자기 렌더 3장" 을 확인. 결과 `model/agent/<job_id>/agent/{score.json, attempts.json, prompt.md, critique*/}` 를 읽는다. PASS 면 Step 5 로.

- [ ] **Step 4: FAIL 이면 원인 분류 후 잡 2·3 (D7)**

- 프롬프트 정보 결함(LLM 이 못 알 수 있는 것) → 코드/문서 수정 + 테스트 + 커밋 후 새 잡(요청 없음).
- 모델의 실수(정보는 있는데 틀림) → 화면 "수정 요청" 으로 부모 잡을 잇는 잡(예산 승계 9.39).
- 잡 3개 뒤에도 FAIL 이면 남은 예산을 쓰지 않고 사용자에게 보고(판정서에 정직 기록).

- [ ] **Step 5: 화면 확인**

브라우저 패널에서 잡 패널 요약(`완료 · 시도 n · $x · PASS · b#`)과 채점 블록(bbox ≤ 5 mm·fail 0)을 DOM 텍스트로 읽는다(스크린샷이 타임아웃이면 JS 로 읽기). 예산 입력이 `jobs.budget_usd` 에 들어갔는지 DB 조회(`select id, budget_usd, cost_usd, attempts, status from jobs order by created_at`).

- [ ] **Step 6: 판정서 `acceptance-m6.md`**

표: 기준 ①~④ 결과·근거. 잡별 표(요청·시도·비용·최종 채점·bbox). 공개 정보 범위(D8): 필드 doc·KB 규약·bbox 델타·자기 렌더 — 정답 렌더·코드는 아님. 비용: `usage.jsonl` stage `model-agent` 증분(호출 수·토큰·$). 교훈·다음 후보(9섹션 확산 등).

- [ ] **Step 7: README·메모리**

README "## LLM 모델링 (M5)" 절 끝에 "### M6 — 격벽 PASS" 소절: 무엇을 바꿨나(4+1), 실증 결과 한 줄, 예산 입력 사용법, `critique<n>/` 산출. 메모리 파일 갱신(결과·비용·병합 상태는 통합 뒤).

- [ ] **Step 8: 통합**

`git add README.md && git commit -m "docs: README M6 격벽 PASS 절 + 판정"` 뒤 superpowers:finishing-a-development-branch — 전건 테스트 → 병합 방식은 사용자 선택(지금까지는 main 로컬 병합, push 안 함).
