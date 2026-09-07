# M8 정답 없는 합격 규칙 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 정답 빌더가 없는 교량에서도 섹션 산출을 판정할 수 있게 기하 건전성 검사와 스펙 유도 재실측을 채우고, 합격 규칙을 정답 무관으로 바꾼다.

**Architecture:** 설계서 `docs/superpowers/specs/2026-09-07-m8-reference-free-rule-design.md`. 재실측(`model/measure.py`)의 각 행에 섹션 코드를 찍어 "이 섹션의 항목만" 판정할 수 있게 하고, 비어 있던 섹션(이음판·수평보강재)과 얕던 섹션(가로보·외측빔·프레임·받침·슬래브)의 항목을 ModelSpec 에서 유도해 채운다. 스펙과 무관한 기하 건전성 3종을 `model/sanity.py` 에 새로 만든다. 채점(`agent/score.py`)의 `pass` 에서 정답 대조를 빼고 참고 정보로 옮긴다. 규칙이 쓸모 있는지는 이미 쌓인 에이전트 산출 33건에 돌려 혼동표로 증명한다(무과금).

**Tech Stack:** Python 3.12 (`worker/.venv`), trimesh, numpy, pydantic 2, typer, pytest; React 18 + Mantine 8 + vitest.

## Global Constraints

- 실증 API 지출 ≤ **$5** — `usage.jsonl` stage `model-agent` 누적 상한 **$20.03**(현재 $15.03). 잡은 웹에서 예산 20.03 으로 만든다.
- 재실측 기대값은 **ModelSpec 에서 유도**한다. `measure.py`·`sanity.py` 는 `builder.py`·`builder_full.py` 를 import 하지 않는다(KB §6-2, 자기참조 검증 방지).
- 허용오차는 현행 유지: 길이 5 mm(`TOL`/`TOL_MM`), 개수 0, 각도 0.5°(`TOL_ANG`).
- 합격 규칙(D4): `pass = 건전성 fail 0 ∧ 섹션 self-check fail 0 ∧ 결합 self-check fail 0 ∧ 그 섹션 재실측 fail 0`. 정답 대조는 `score["reference"]` 로만 남긴다.
- 모델·시도 수·예산 구조는 바꾸지 않는다: `claude-sonnet-5`, thinking 비활성, `max_tokens` 16000, `MAX_ATTEMPTS` 4.
- **Bash heredoc 은 백슬래시를 소비한다** — 정규식·`\n` 이 든 파일은 Write 툴로 쓰거나 `chr(92)` 로 조립한다. 검증과 커밋을 한 명령에 묶을 때는 `set -o pipefail`. 항상 `cd /d/Projects/model3d-studio` 부터 시작한다.
- 테스트: 워커 `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest -q`, 웹 `cd /d/Projects/model3d-studio/web && npm test -- --run` 과 `npm run typecheck`.
- 브랜치 `feat/m8-reference-free-rule`(main 12564d2 분기). 커밋 메시지 끝에 `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- 완료 주장 전 실제 실행 출력으로 검증한다.

## 파일 구조

| 파일 | 책임 | 작업 |
|---|---|---|
| `worker/src/m3d/model/measure.py` | 독립 재실측 — 행에 섹션 태그, 섹션별 항목 보강 | Task 1·2 |
| `worker/src/m3d/model/sanity.py` (신규) | 기하 건전성 3종(외곽·부유·중복), 스펙 무관 | Task 3 |
| `worker/src/m3d/agent/score.py` | 합격 규칙 전환·피드백 재구성 | Task 4 |
| `worker/src/m3d/model/verify_rule.py` (신규), `cli.py` | 기존 산출에 새 규칙을 돌려 혼동표 | Task 5 |
| `contracts/db.types.ts`, `web/src/components/VerifyPanel.tsx` | 요약 필드 확장·판정 블록 분리 | Task 6 |
| `worker/tests/test_model_measure.py`, `test_model_sanity.py`(신규), `test_agent_score.py`, `test_model_verify_rule.py`(신규) | 검증 | 각 Task |
| `data/derived/.../acceptance-m8.md`, `README.md` | 실증·판정 | Task 7 |

---

### Task 1: 재실측 행에 섹션 태그

**Files:**
- Modify: `worker/src/m3d/model/measure.py` (`Checks`, `SECTIONS`, `run`)
- Test: `worker/tests/test_model_measure.py`

**Interfaces:**
- Produces: `Checks.group: str | None`; `Checks.add(name, exp, meas, tol, unit="", group=None)`, `add_info(name, meas, note, unit="", group=None)`, `add_missing(name, detail, group=None)` — 모두 행에 `"섹션"` 키를 남긴다.
  `SECTIONS: list[tuple[str, str, callable]]` = (라벨, 섹션코드, 함수).
  `measure.run()` 결과에 `"섹션별": {코드: {"PASS": n, "FAIL": n, "INFO": n}}`.

- [ ] **Step 1: 실패하는 테스트 작성**

`worker/tests/test_model_measure.py` 상단 import 에 `import pytest`, `from m3d.model.builder import Builder`,
`from m3d.model.spec import ModelSpec` 가 없으면 더한다. 그리고 파일 끝에 추가:

```python
def test_every_measure_row_carries_a_section_tag(ref_glb, spec):
    """섹션별 판정(M8 D1)을 하려면 행마다 귀속 섹션이 있어야 한다."""
    from m3d.model import sections as X
    r = measure.run(ref_glb, spec)
    codes = set(X.CODES) | {"ASSEMBLY"}
    missing = [c["항목"] for c in r["대조"] if not c.get("섹션")]
    assert missing == [], f"섹션 태그 없는 행: {missing}"
    assert {c["섹션"] for c in r["대조"]} <= codes
    agg = r["섹션별"]
    assert agg["DIA"]["PASS"] >= 1 and agg["BRG"]["PASS"] >= 1
    assert sum(v["PASS"] + v["FAIL"] + v["INFO"] for v in agg.values()) == len(r["대조"])
```

이 테스트가 쓰는 `ref_glb`·`spec` 픽스처가 파일에 없으면 파일 상단에 추가한다:

```python
@pytest.fixture(scope="module")
def spec():
    return ModelSpec()


@pytest.fixture(scope="module")
def ref_glb(tmp_path_factory, spec):
    d = tmp_path_factory.mktemp("m")
    b = Builder(spec)
    glb = d / "ref.glb"
    b.export(b.build(pilot=False), glb)
    return glb
```

- [ ] **Step 2: 실패 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_model_measure.py -q`
Expected: FAIL — `섹션 태그 없는 행: [...]` 또는 `KeyError: '섹션별'`

- [ ] **Step 3: Checks 에 group 추가**

`worker/src/m3d/model/measure.py` 의 `Checks` 를 고친다.

```python
class Checks:
    def __init__(self):
        self.rows: list[dict] = []
        self.group: str | None = None          # run() 이 섹션마다 설정 (M8 D1)

    def _row(self, row: dict, group: str | None) -> dict:
        row["섹션"] = group or self.group or "ASSEMBLY"
        self.rows.append(row)
        return row

    def add(self, name, exp, meas, tol, unit="", group=None):
        e = np.atleast_1d(np.asarray(exp, dtype=float))
        m = np.atleast_1d(np.asarray(meas, dtype=float))
        if len(e) != len(m):
            ok, dev = False, None
        else:
            dev = float(np.max(np.abs(e - m))) if len(e) else 0.0
            ok = bool(np.isfinite(dev)) and dev <= tol + 1e-9

        def val(a):
            return [round(float(v), 4) for v in a] if len(a) != 1 else round(float(a[0]), 4)
        self._row({"항목": name, "단위": unit, "기대": val(e), "실측": val(m),
                   "허용오차": tol, "최대편차": None if dev is None or not np.isfinite(dev) else round(dev, 4),
                   "판정": "PASS" if ok else "FAIL"}, group)
        return ok

    def add_info(self, name, meas, note, unit="", group=None):
        self._row({"항목": name, "단위": unit, "기대": "사양 미기재(" + note + ")",
                   "실측": meas, "허용오차": None, "최대편차": None, "판정": "INFO"}, group)

    def add_missing(self, name, detail, group=None):
        self._row({"항목": name, "단위": "", "기대": "노드 존재", "실측": detail,
                   "허용오차": None, "최대편차": None, "판정": "FAIL"}, group)

    def summary(self):
        n_pass = sum(1 for c in self.rows if c["판정"] == "PASS")
        n_fail = sum(1 for c in self.rows if c["판정"] == "FAIL")
        n_info = sum(1 for c in self.rows if c["판정"] == "INFO")
        return {"검증항목": len(self.rows), "PASS": n_pass, "FAIL": n_fail, "INFO": n_info}

    def by_section(self) -> dict[str, dict]:
        agg: dict[str, dict] = {}
        for c in self.rows:
            g = agg.setdefault(c["섹션"], {"PASS": 0, "FAIL": 0, "INFO": 0})
            g[c["판정"]] += 1
        return agg
```

- [ ] **Step 4: SECTIONS 표에 코드, run() 에서 group 설정**

`SECTIONS` 를 3튜플로 바꾼다:

```python
SECTIONS = [("bbox", "ASSEMBLY", sec_bbox), ("내공 H", "BOX", sec_h_profile), ("강상판 상면", "BOX", sec_deck_top),
            ("격벽", "DIA", sec_diaphragms), ("프레임", "FRM", sec_frames), ("종리브", "RIB", sec_ribs),
            ("WG·CS", "WG", sec_wg_cs), ("받침", "BRG", sec_bearings), ("슬래브·방호벽", "SLAB", sec_slab),
            ("메시 수", "ASSEMBLY", sec_mesh_count)]
```

`run()` 의 루프를 고친다:

```python
    for label, code, fn in SECTIONS:
        ck.group = code
        try:
            fn(W, E, ck, out)
        except KeyError as exc:
            ck.add_missing("%s 섹션 — 노드 누락" % label, "KeyError: %s" % exc)
        except Exception as exc:                               # noqa: BLE001 — 임의 형상에서도 재실측은 끝까지 간다
            ck.add_missing("%s 섹션 — 실측 오류" % label, "%s: %s" % (type(exc).__name__, exc))
    ck.group = None
```

그리고 결과에 집계를 더한다: `result["섹션별"] = ck.by_section()` (`result["집계"] = agg` 다음 줄).

`sec_wg_cs` 안의 CS 관련 두 호출에 `group="CS"` 를 붙인다 — `"CS 세그 수 ..."` 행 하나가 대상이다.

- [ ] **Step 5: 통과 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_model_measure.py tests/test_model_compare.py tests/test_agent_score.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd /d/Projects/model3d-studio && git add worker/src/m3d/model/measure.py worker/tests/test_model_measure.py
git commit -m "feat(measure): 재실측 행에 섹션 태그 + 섹션별 집계 — 섹션 단위 판정의 전제(M8 D1)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: 섹션별 재실측 항목 보강

**Files:**
- Modify: `worker/src/m3d/model/measure.py` (`Expect`, `sec_sp04` 신규, `sec_hstiff` 신규, `sec_wg_cs`·`sec_frames`·`sec_bearings`·`sec_slab`·`sec_ribs` 확장, `SECTIONS`)
- Test: `worker/tests/test_model_measure.py`

**Interfaces:**
- Consumes: Task 1 의 `Checks.add(..., group=)`, `SECTIONS` 3튜플, `ck.group`.
- Produces: `sec_sp04(W, E, ck, out)`, `sec_hstiff(W, E, ck, out)`; `Expect` 새 속성 `Z_JOINT`, `HST_UP_Z`, `BRACKET_Y`, `STRUT_PTS`, `CS_XC`, `BARRIER_X`.

- [ ] **Step 1: 실패하는 테스트 작성**

`worker/tests/test_model_measure.py` 끝에 추가:

```python
MIN_ITEMS = {"BOX": 4, "DIA": 4, "FRM": 4, "RIB": 4, "HST": 4, "WG": 4, "CS": 4, "SLAB": 4, "SP04": 4, "BRG": 4}


def test_every_section_has_real_coverage(ref_glb, spec):
    """정답을 빼면 이 항목들만 남는다 — 섹션마다 최소 4개, 합계 75개 이상(M8 ②)."""
    r = measure.run(ref_glb, spec)
    agg = r["섹션별"]
    thin = {c: n for c, n in MIN_ITEMS.items() if agg.get(c, {"PASS": 0, "FAIL": 0, "INFO": 0}).get("PASS", 0)
            + agg.get(c, {}).get("FAIL", 0) + agg.get(c, {}).get("INFO", 0) < n}
    assert thin == {}, f"항목이 모자란 섹션: {thin}"
    assert len(r["대조"]) >= 75, len(r["대조"])
    assert r["집계"]["FAIL"] == 0, [c["항목"] for c in r["대조"] if c["판정"] == "FAIL"]


def test_moved_sp04_plate_fails_only_its_section(ref_glb, spec, tmp_path):
    """이음판 상면판을 20mm 내리면 SP04 항목만 걸린다."""
    from m3d.agent.score import load_named
    named = load_named(ref_glb)
    named["AB1_S5_SP04_TF"].apply_translation([0, -0.02, 0])
    glb = tmp_path / "moved.glb"
    Builder(spec).export(named, glb)
    r = measure.run(glb, spec)
    failed = {c["섹션"] for c in r["대조"] if c["판정"] == "FAIL"}
    assert failed == {"SP04"}, [(c["섹션"], c["항목"]) for c in r["대조"] if c["판정"] == "FAIL"]


def test_moved_wg_bracket_is_caught(ref_glb, spec, tmp_path):
    """M7 에서 정답 대조로만 잡히던 1.7m 정착대 오류를 재실측이 잡는다."""
    from m3d.agent.score import load_named
    named = load_named(ref_glb)
    for nm in [n for n in named if n.endswith("_BR")]:
        named[nm].apply_translation([0, 1.688, 0])
    glb = tmp_path / "wgbr.glb"
    Builder(spec).export(named, glb)
    r = measure.run(glb, spec)
    assert "WG" in {c["섹션"] for c in r["대조"] if c["판정"] == "FAIL"}
```

- [ ] **Step 2: 실패 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_model_measure.py -q`
Expected: FAIL — `항목이 모자란 섹션: {'HST': 4, 'SP04': 4, 'CS': 4}` 등

- [ ] **Step 3: Expect 에 유도값 추가**

`Expect.__init__` 끝(`self.N_MESH = ...` 앞)에 추가:

```python
        w = s.wg
        self.Z_JOINT = c.z_p4 + b.z_sp04_offset                       # §9 현장이음선
        self.HST_UP_Z = [c.z_p4 + s.hstiff.upper_span, c.z_p5 - s.hstiff.upper_span]
        self.BRACKET_X = [b.x_web, b.x_web + w.bracket[0]]            # §6 정착대 x 범위(+측)
        self.BRACKET_Y_REL = [-w.bracket[2], -w.bracket[1]]           # y_deck_top 기준 아래 깊이
        self.STRUT_LO_REL = (b.x_web + w.strut_lower[0], -w.strut_lower[1])
        self.STRUT_HI_REL = (b.x_web + w.knee[0], -w.knee[1])
        self.CS_XC = b.x_web + w.length                               # §7 세그 x 중심
        hw, bw = sl.half_width, sl.barrier[0]
        inner = c.walk_side_sign * (hw - bw - sl.walk_width)
        self.BARRIER_X = {"L": [-hw, -hw + bw], "R": [hw - bw, hw],
                          "CTR": sorted((inner, inner - c.walk_side_sign * sl.center_barrier))}
```

`Expect` 에 헬퍼 메서드를 더한다(클래스 끝, `h_stations` 뒤):

```python
    def deck_top(self, z):
        """강상판 상면 y — 정착대·스트럿·이음판 기준면."""
        return self.top_y(z)

    def bot_out(self, z):
        """하판 하면 y = 상면 − 상판두께 − 내공 − 하판두께."""
        return self.top_y(z) - (self.t_of(self.s.box.top_t, z - self.Z_P4) + self.h_at_z(z) / 1000.0
                                + self.t_of(self.s.box.bot_t, z - self.Z_P4))

    def web_bot(self, z):
        """하판 상면 y."""
        return self.top_y(z) - self.t_of(self.s.box.top_t, z - self.Z_P4) - self.h_at_z(z) / 1000.0

    def web_top(self, z):
        """강상판 하면 y."""
        return self.top_y(z) - self.t_of(self.s.box.top_t, z - self.Z_P4)
```

- [ ] **Step 4: sec_sp04·sec_hstiff 작성**

`sec_slab` 뒤, `sec_mesh_count` 앞에 추가:

```python
def sec_sp04(W, E: Expect, ck: Checks, out: dict):
    """§9 이음판 4매 — 부착면·이음선 z·폭 (M8 D2)."""
    sp = E.s.sp04
    names = [nm for nm in sorted(W) if "_SP04_" in nm]
    ck.add("이음판 매수 (§9 상·하면 + 복부 좌·우 = 4)", 4, len(names), 0, "매")
    zj = E.Z_JOINT
    tf, bf, wb = W["AB1_S5_SP04_TF"], W["AB1_S5_SP04_BF"], W["AB1_S5_SP04_WEB_L"]
    ck.add("이음판 z 중심 4매 (§9 이음선 P4+%g)" % E.s.box.z_sp04_offset, [zj] * 4,
           [float((W[nm].bounds[0][2] + W[nm].bounds[1][2]) / 2) for nm in
            ("AB1_S5_SP04_TF", "AB1_S5_SP04_BF", "AB1_S5_SP04_WEB_L", "AB1_S5_SP04_WEB_R")], TOL, "m")
    ck.add("상면판 상면 y (§9 강상판 상면 + 두께 %s)" % _fmt(sp.tf[2] * 1000), E.deck_top(zj) + sp.tf[2],
           float(tf.bounds[1][1]), TOL, "m")
    ck.add("하면판 하면 y (§9 하판 하면 − 두께 %s)" % _fmt(sp.bf[2] * 1000), E.bot_out(zj) - sp.bf[2],
           float(bf.bounds[0][1]), TOL, "m")
    ck.add("복부판 외면 x (§9 웹 외면 %g + 두께 %s)" % (E.s.box.x_web, _fmt(sp.web[2] * 1000)),
           -(E.s.box.x_web + sp.web[2]), float(wb.bounds[0][0]), TOL, "m")


def sec_hstiff(W, E: Expect, ck: Checks, out: dict):
    """§5 복부 수평보강재 — 열별 y·z 범위·내민 길이 (M8 D2)."""
    hs = E.s.hstiff
    names = [nm for nm in sorted(W) if "_HST_" in nm]
    ck.add("수평보강재 부재 수 (§5 상단 2 + 하단 %d)" % (E.N_HST - 2), E.N_HST, len(names), 0, "개")
    up = [W["AB1_S5_HST_UP_L"], W["AB1_S5_HST_UP_R"]]
    zc = (E.HST_UP_Z[0] + E.HST_UP_Z[1]) / 2
    ck.add("상단열 y 중심 (§5 강상판 하면 − %s)" % _fmt(hs.upper_drop * 1000), [E.web_top(zc) - hs.upper_drop] * 2,
           [float((m.bounds[0][1] + m.bounds[1][1]) / 2) for m in up], TOL, "m")
    ck.add("상단열 z 범위 (§5 받침선 ±%g 안쪽)" % hs.upper_span, E.HST_UP_Z,
           [float(up[0].bounds[0][2]), float(up[0].bounds[1][2])], TOL, "m")
    lo = W["AB1_S5_HST_P4_LO1_L"]
    z0 = E.Z_P4
    ck.add("하단 1열 y @P4 (§5 하판 상면 + %g·H)" % hs.lower_factors[0],
           E.web_bot(z0) + hs.lower_factors[0] * E.h_at_z(z0) / 1000.0, float((lo.bounds[0][1] + lo.bounds[1][1]) / 2),
           0.02, "m")
    ck.add("내민 길이 x (§5 웹 내면에서 %s)" % _fmt(hs.h * 1000), hs.h * 1000.0,
           float(lo.bounds[1][0] - lo.bounds[0][0]) * 1000.0, TOL_MM, "mm")
```

`SECTIONS` 에 두 줄을 더한다(`("슬래브·방호벽", "SLAB", sec_slab)` 다음):

```python
            ("이음판", "SP04", sec_sp04), ("수평보강재", "HST", sec_hstiff),
```

- [ ] **Step 5: 기존 섹션 확장**

`sec_wg_cs` 끝에 추가(정착대·스트럿·CS):

```python
    brs = [nm for nm in names if nm.endswith("_BR")]
    ck.add("정착대 수 (§6 가로보마다 1)", E.N_WG, len(brs), 0, "개")
    br = W["AB1_S5_%s_BR" % tag]
    zc_br = float((br.bounds[0][2] + br.bounds[1][2]) / 2)
    yd = E.deck_top(zc_br)
    ck.add("정착대 y 범위 %s_BR (§6 강상판 상면 −%g…−%g)" % (tag, E.s.wg.bracket[2], E.s.wg.bracket[1]),
           [yd + E.BRACKET_Y_REL[0], yd + E.BRACKET_Y_REL[1]],
           [float(br.bounds[0][1]), float(br.bounds[1][1])], TOL, "m")
    ck.add("정착대 x 바깥 끝 %s_BR (§6 웹 외면 + %g)" % (tag, E.s.wg.bracket[0]), -E.BRACKET_X[1],
           float(br.bounds[0][0]), TOL, "m")
    st = W["AB1_S5_%s_ST" % tag]
    zc_st = float((st.bounds[0][2] + st.bounds[1][2]) / 2)
    yd_st = E.deck_top(zc_st)
    ck.add("스트럿 x 범위 %s_ST (§6 하단 작업점 웹+%g … 상단 작업점 웹+%g)" % (tag, E.s.wg.strut_lower[0], E.s.wg.knee[0]),
           [-E.STRUT_HI_REL[0], -E.STRUT_LO_REL[0]], [float(st.bounds[0][0]), float(st.bounds[1][0])], 0.10, "m")
    ck.add("스트럿 y 범위 %s_ST (§6 강상판 상면 아래 %g…%g)" % (tag, E.s.wg.knee[1], E.s.wg.strut_lower[1]),
           [yd_st + E.STRUT_LO_REL[1], yd_st + E.STRUT_HI_REL[1]],
           [float(st.bounds[0][1]), float(st.bounds[1][1])], 0.10, "m")
    cs_tag = "AB1_S5_CS%03dL" % E.WG_NO
    cs = W[cs_tag]
    ck.add("%s z 중심 (§7 가로보 체인 중심)" % cs_tag, E.Z_P4 + E.s.diaphragm.spacing,
           float((cs.bounds[0][2] + cs.bounds[1][2]) / 2), TOL, "m", group="CS")
    ck.add("%s x 중심 (§7 가로보 선단 %g)" % (cs_tag, E.CS_XC), -E.CS_XC,
           float((cs.bounds[0][0] + cs.bounds[1][0]) / 2), TOL, "m", group="CS")
    ck.add("%s 춤 (§7 %s)" % (cs_tag, _fmt(E.s.cs.depth * 1000)), E.s.cs.depth * 1000.0,
           float(cs.bounds[1][1] - cs.bounds[0][1]) * 1000.0, TOL_MM, "mm", group="CS")
```

`sec_frames` 끝에 추가:

```python
    fid = frm_ids[0]
    trw, trf = W["AB1_S5_FRM%s_TRW" % fid], W["AB1_S5_FRM%s_TRF" % fid]
    brw, brf = W["AB1_S5_FRM%s_BRW" % fid], W["AB1_S5_FRM%s_BRF" % fid]
    row = E.s.frame.rows[0]
    ck.add("프레임 상부 플랜지 z 폭 (§3 [A6] 상부 웹 높이 %s)" % _fmt(row.top_web[1] * 1000), row.top_web[1] * 1000.0,
           float(trf.bounds[1][2] - trf.bounds[0][2]) * 1000.0, TOL_MM, "mm")
    zc = float((trw.bounds[0][2] + trw.bounds[1][2]) / 2)
    ck.add("프레임 하부 웹 상단 y (§3 하판 상면 + %s)" % _fmt(row.bot_web[1] * 1000), E.web_bot(zc) + row.bot_web[1],
           float(brw.bounds[1][1]), TOL, "m")
    ck.add("프레임 하부 플랜지 z 폭 (§3 [A6] 하부 웹 높이 %s)" % _fmt(row.bot_web[1] * 1000), row.bot_web[1] * 1000.0,
           float(brf.bounds[1][2] - brf.bounds[0][2]) * 1000.0, TOL_MM, "mm")
    vsl = W["AB1_S5_FRM%s_VSL" % fid]
    ck.add("프레임 수직보강재 y 길이 (§3 [A7] %s)" % _fmt(row.vstiff[2] * 1000), row.vstiff[2] * 1000.0,
           float(vsl.bounds[1][1] - vsl.bounds[0][1]) * 1000.0, TOL_MM, "mm")
```

`sec_bearings` 끝에 추가:

```python
    br = E.s.bearing
    sole = W["AB1_S5_BRG_P4_1_SOLE"]
    mort = W["AB1_S5_BRG_P4_1_MORTAR"]
    blk = W["AB1_S5_BRG_P4_1_BLOCK"]
    ck.add("솔플레이트 두께 (§10 %s)" % _fmt(br.sole[3] * 1000), br.sole[3] * 1000.0,
           float(sole.bounds[1][1] - sole.bounds[0][1]) * 1000.0, 5.0, "mm")
    ck.add("무수축 모르타르 두께 (§10 %s)" % _fmt(br.mortar[0] * 1000), br.mortar[0] * 1000.0,
           float(mort.bounds[1][1] - mort.bounds[0][1]) * 1000.0, 5.0, "mm")
    ck.add("받침 블록 한 변 (§10 %s)" % _fmt(br.block[0] * 1000), [br.block[0] * 1000.0] * 2,
           [float(blk.bounds[1][0] - blk.bounds[0][0]) * 1000.0, float(blk.bounds[1][2] - blk.bounds[0][2]) * 1000.0],
           TOL_MM, "mm")
```

`sec_slab` 끝에 추가:

```python
    for b_ in ("L", "R", "CTR"):
        m = W["AB1_S5_BARRIER_" + b_]
        ck.add("방호벽 %s x 범위 (§8 보도측 %g·폭 %g)" % (b_, E.s.slab.walk_width, E.s.slab.barrier[0]),
               E.BARRIER_X[b_], [float(m.bounds[0][0]), float(m.bounds[1][0])], TOL, "m")
```

`sec_ribs` 끝에 추가:

```python
    for nm, zone, lbl in (("AB1_S5_RIB_TP4_1", r.top_pier, "지점존 상판"), ("AB1_S5_RIB_BP4A_1", r.bot_pier, "지점존 하판")):
        m = W.get(nm)
        if m is not None:
            ck.add("종리브 %s 높이 (§4 %s)" % (lbl, _fmt(zone.h * 1000)), zone.h * 1000.0,
                   float(m.bounds[1][1] - m.bounds[0][1]) * 1000.0, TOL_MM, "mm")
```

- [ ] **Step 6: 통과 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_model_measure.py -q`
Expected: PASS. 실패하면 기대식과 정답 산출의 차이를 읽고 **기대식을 스펙에 맞게** 고친다(정답 GLB 에 맞추려고 허용오차를 늘리지 않는다 — 늘려야 한다면 그 사유를 주석에 적는다).

- [ ] **Step 7: Commit**

```bash
cd /d/Projects/model3d-studio && git add worker/src/m3d/model/measure.py worker/tests/test_model_measure.py
git commit -m "feat(measure): 섹션별 재실측 항목 보강 — 이음판·수평보강재 신규, 가로보 정착대/스트럿·외측빔·프레임·받침·슬래브·종리브 확장

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: 기하 건전성 `model/sanity.py`

**Files:**
- Create: `worker/src/m3d/model/sanity.py`
- Test: `worker/tests/test_model_sanity.py` (신규)

**Interfaces:**
- Produces: `sanity.envelope(spec) -> tuple[np.ndarray, np.ndarray]`;
  `sanity.run(named: dict[str, trimesh.Trimesh], spec: ModelSpec) -> dict` — `{"pass": int, "fail": int, "checks": [{"label": str, "ok": bool, "detail": str, "nodes": list[str]}]}`.
- Consumes: `ModelSpec` 만. 빌더를 import 하지 않는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`worker/tests/test_model_sanity.py` (신규):

```python
"""기하 건전성 (M8 D3) — 스펙과 무관하게 큰 사고를 잡는다: 외곽 이탈·부유 부재·중복 배치."""

import pytest

from m3d.model import sanity
from m3d.model.builder import Builder
from m3d.model.spec import ModelSpec


@pytest.fixture(scope="module")
def spec():
    return ModelSpec()


@pytest.fixture(scope="module")
def named(spec):
    return Builder(spec).build(pilot=False)


def test_reference_model_is_healthy(named, spec):
    r = sanity.run(named, spec)
    assert r["fail"] == 0, [c["label"] + " " + c["detail"] for c in r["checks"] if not c["ok"]]
    assert r["pass"] == 3


def test_node_far_outside_is_caught(named, spec):
    bad = {k: v.copy() for k, v in named.items()}
    bad["AB1_S5_DIA13"].apply_translation([0, 0, 500.0])
    r = sanity.run(bad, spec)
    labels = [c["label"] for c in r["checks"] if not c["ok"]]
    assert "외곽 이탈" in labels and "부유 부재" in labels
    assert "AB1_S5_DIA13" in [n for c in r["checks"] if not c["ok"] for n in c["nodes"]]


def test_duplicate_placement_is_caught(named, spec):
    bad = {k: v.copy() for k, v in named.items()}
    bad["AB1_S5_DIA13_DUP"] = bad["AB1_S5_DIA13"].copy()
    r = sanity.run(bad, spec)
    assert "중복 배치" in [c["label"] for c in r["checks"] if not c["ok"]]


def test_envelope_comes_from_spec(spec):
    lo, hi = sanity.envelope(spec)
    assert lo[0] < -spec.slab.half_width and hi[0] > spec.slab.half_width
    assert lo[2] < spec.coord.z_p4 and hi[2] > spec.coord.z_p5
```

- [ ] **Step 2: 실패 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_model_sanity.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'm3d.model.sanity'`

- [ ] **Step 3: 구현**

`worker/src/m3d/model/sanity.py`:

```python
"""기하 건전성 (M8 D3) — 스펙 해석 없이 큰 사고만 잡는다.

정답 빌더가 없는 교량에서도 쓰는 첫 관문이다. bbox 연산만 쓴다(메시 불리언은 느리다).
1) 외곽 이탈 — 노드가 교량 외곽 밖에 있다.  2) 부유 부재 — 어떤 부재와도 닿지 않는다.
3) 중복 배치 — 두 부재가 같은 자리를 절반 넘게 차지한다.
"""

from __future__ import annotations

import numpy as np
import trimesh

from m3d.model.spec import ModelSpec

MARGIN = 0.5          # 외곽 여유(m)
TOUCH = 0.05          # 이 거리 안에서 만나면 닿은 것으로 본다(m)
OVERLAP_RATIO = 0.5   # 작은 쪽 bbox 부피의 이 비율을 넘게 겹치면 중복


def envelope(spec: ModelSpec) -> tuple[np.ndarray, np.ndarray]:
    """스펙에서 유도한 교량 외곽 — 여유 MARGIN."""
    c, sl, br = spec.coord, spec.slab, spec.bearing
    y_low = min(br.el_check.values()) - c.y_datum - br.mortar[0] - br.block[1]
    y_high = c.el0 + c.grade * (max(c.z_p4, c.z_p5) - c.z_sta3400) - c.y_datum + sl.barrier[1]
    lo = np.array([-sl.half_width - MARGIN, y_low - MARGIN, min(c.z_p4, c.z_p5) - MARGIN])
    hi = np.array([sl.half_width + MARGIN, y_high + MARGIN, max(c.z_p4, c.z_p5) + MARGIN])
    return lo, hi


def _bounds(named: dict[str, trimesh.Trimesh]) -> dict[str, np.ndarray]:
    return {n: np.asarray(m.bounds, dtype=float) for n, m in named.items()}


def _overlap_volume(a: np.ndarray, b: np.ndarray) -> float:
    d = np.minimum(a[1], b[1]) - np.maximum(a[0], b[0])
    return float(np.prod(d)) if np.all(d > 0) else 0.0


def _box_volume(a: np.ndarray) -> float:
    return float(np.prod(np.maximum(a[1] - a[0], 1e-6)))


def run(named: dict[str, trimesh.Trimesh], spec: ModelSpec) -> dict:
    """세 가지 건전성 검사 — 결과는 self-check 와 같은 모양."""
    B = _bounds(named)
    lo, hi = envelope(spec)
    checks: list[dict] = []

    outside = sorted(n for n, b in B.items() if np.any(b[0] < lo - 1e-9) or np.any(b[1] > hi + 1e-9))
    checks.append({"label": "외곽 이탈", "ok": not outside, "nodes": outside[:10],
                   "detail": "외곽 x[%.1f,%.1f] y[%.1f,%.1f] z[%.1f,%.1f] 밖 %d개" %
                             (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2], len(outside))})

    keys = sorted(B)
    grown = {n: np.array([B[n][0] - TOUCH, B[n][1] + TOUCH]) for n in keys}
    floating = []
    for n in keys:
        g = grown[n]
        if not any(m != n and _overlap_volume(g, B[m]) > 0 for m in keys):
            floating.append(n)
    checks.append({"label": "부유 부재", "ok": not floating, "nodes": floating[:10],
                   "detail": "%dmm 안에서 다른 부재와 닿지 않는 노드 %d개" % (int(TOUCH * 1000), len(floating))})

    dup = []
    for i, n in enumerate(keys):
        for m in keys[i + 1:]:
            ov = _overlap_volume(B[n], B[m])
            if ov <= 0:
                continue
            if ov > OVERLAP_RATIO * min(_box_volume(B[n]), _box_volume(B[m])):
                dup.append("%s↔%s" % (n, m))
    checks.append({"label": "중복 배치", "ok": not dup, "nodes": dup[:10],
                   "detail": "bbox 겹침이 작은 쪽 부피의 %d%% 초과인 쌍 %d개" % (int(OVERLAP_RATIO * 100), len(dup))})

    n_fail = sum(1 for c in checks if not c["ok"])
    return {"pass": len(checks) - n_fail, "fail": n_fail, "checks": checks}
```

- [ ] **Step 4: 통과 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_model_sanity.py -q`
Expected: PASS. 정답 모델이 "중복 배치"에 걸리면(INS 관통이나 감싸는 부재 탓) `OVERLAP_RATIO` 를 올리지 말고 **감싸는 관계는 제외**하는 규칙을 더한다: 한쪽 bbox 가 다른 쪽을 완전히 포함하면 건너뛴다.

- [ ] **Step 5: Commit**

```bash
cd /d/Projects/model3d-studio && git add worker/src/m3d/model/sanity.py worker/tests/test_model_sanity.py
git commit -m "feat(model): 기하 건전성 검사 — 외곽 이탈·부유 부재·중복 배치(M8 D3)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: 합격 규칙 전환·피드백 재구성

**Files:**
- Modify: `worker/src/m3d/agent/score.py`
- Test: `worker/tests/test_agent_score.py`

**Interfaces:**
- Consumes: Task 1 의 `measure.run()["섹션별"]` 과 행의 `"섹션"`, Task 3 의 `sanity.run(named, spec)`.
- Produces: `score_section(code, agent_glb, spec, ref_dir=None, *, work_dir) -> dict` —
  키 `pass`, `sanity`, `section_selfcheck`, `assembled_selfcheck`, `measure`(`{"PASS","FAIL","INFO","section_fail","failed"}`), `reference`(ref_dir 이 있을 때만), `assembled_glb`.
  `summary(score, attempts) -> dict` — `{"pass", "sanity_fail", "section_fail", "assembled_fail", "measure_section_fail", "measure_fail", "attempts", "bbox_dev_max_m"(없으면 None), "only_ours", "only_ref"}`.
  `feedback_text(score) -> str`.

- [ ] **Step 1: 실패하는 테스트 작성**

`worker/tests/test_agent_score.py` 끝에 추가:

```python
def test_reference_free_pass_without_ref_dir(ref_dir, tmp_path):
    """정답 없이도 판정한다 — 새 교량 경로(M8 D4)."""
    spec = ModelSpec()
    sc = S.score_section("DIA", ref_dir / "sections" / "P4P5" / "DIA.glb", spec, None, work_dir=tmp_path / "a")
    assert sc["pass"] is True and "reference" not in sc
    assert sc["sanity"]["fail"] == 0 and sc["measure"]["section_fail"] == 0
    summ = S.summary(sc, attempts=1)
    assert summ["bbox_dev_max_m"] is None and summ["sanity_fail"] == 0 and summ["measure_section_fail"] == 0


def test_reference_is_informational_only(ref_dir, tmp_path):
    """정답이 있으면 참고로 싣되 합격 여부에는 넣지 않는다."""
    spec = ModelSpec()
    named = S.load_named(ref_dir / "sections" / "P4P5" / "DIA.glb")
    named["AB1_S5_DIA13"].apply_translation([0, 0, 0.02])          # 20mm — 정답 대비 어긋남
    glb = tmp_path / "shift.glb"
    Builder(spec).export(named, glb)
    sc = S.score_section("DIA", glb, spec, ref_dir, work_dir=tmp_path / "b")
    assert sc["reference"]["bbox_dev_max_m"] > 0.005               # 정답 대조는 어긋났다고 말하고
    assert sc["section_selfcheck"]["fail"] >= 1                    # 합격 여부는 정답 무관 검사가 정한다
    assert sc["pass"] is False


def test_feedback_leads_with_reference_free_findings(ref_dir, tmp_path):
    spec = ModelSpec()
    named = S.load_named(ref_dir / "sections" / "P4P5" / "SP04.glb")
    named["AB1_S5_SP04_TF"].apply_translation([0, -0.02, 0])
    glb = tmp_path / "sp04.glb"
    Builder(spec).export(named, glb)
    sc = S.score_section("SP04", glb, spec, None, work_dir=tmp_path / "c")
    fb = S.feedback_text(sc)
    assert sc["pass"] is False and "재실측 실패" in fb
    assert "상면판 상면 y" in fb and "기대" in fb and "실측" in fb
    assert "정답" not in fb                                        # 정답이 없으면 정답 얘기를 하지 않는다
```

- [ ] **Step 2: 실패 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_agent_score.py -q`
Expected: FAIL — `score_section() missing ... 'ref_dir'` 또는 `KeyError: 'sanity'`

- [ ] **Step 3: score.py 구현**

import 에 `from m3d.model import sanity` 를 더하고, `score_section` 을 교체한다.

```python
def score_section(code: str, agent_glb: Path, spec: ModelSpec, ref_dir=None, *, work_dir: Path) -> dict:
    """정답 무관 판정 (M8 D4) — 건전성·섹션 self-check·결합 self-check·그 섹션 재실측.

    ref_dir 을 주면 정답 대조를 참고 정보로 덧붙인다(합격 여부에는 넣지 않는다).
    """
    segment = spec.coord.segment
    b = Builder(spec)
    agent_named = load_named(agent_glb)
    sec = selfcheck.run(agent_named, b, section=code)
    named: dict[str, trimesh.Trimesh] = {}
    if ref_dir is None:
        # 정답 섹션이 없는 교량 — 재실측이 기준면을 잡으려면 본체(BOX)는 있어야 한다.
        # BOX 는 에이전트 대상이 아니고(M7 D1) 스펙에서 결정론으로 나오므로 빌더에서 가져온다.
        named.update({n: m for n, m in b.build(pilot=True).items() if sections.group_of(n) == "BOX"})
    for c in sections.CODES:
        if c == code:
            named.update(agent_named)
        elif ref_dir is not None:
            named.update(load_named(Path(ref_dir) / "sections" / segment / f"{c}.glb"))
    full = selfcheck.run(named, b, pilot=False) if ref_dir is not None else {"pass": 0, "fail": 0, "checks": []}
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    assembled = work_dir / "assembled.glb"
    b.export(named, assembled)
    san = sanity.run(named, spec)
    meas = measure.run(assembled, spec)
    sec_rows = [c for c in meas["대조"] if c.get("섹션") == code]
    failed_meas = [_meas_line(c) for c in sec_rows if c["판정"] == "FAIL"]
    passed = (san["fail"] == 0 and sec["fail"] == 0 and full["fail"] == 0 and not failed_meas)
    out = {
        "pass": bool(passed),
        "sanity": san,
        "section_selfcheck": _sc(sec), "assembled_selfcheck": _sc(full),
        "measure": {"PASS": meas["집계"]["PASS"], "FAIL": meas["집계"]["FAIL"], "INFO": meas["집계"]["INFO"],
                    "section_fail": len(failed_meas), "failed": failed_meas},
        "assembled_glb": str(assembled),
    }
    if ref_dir is not None:
        out["reference"] = _reference(code, agent_glb, agent_named, spec, Path(ref_dir))
    return out


def _meas_line(c: dict) -> str:
    return "%s — 기대 %s / 실측 %s (허용 %s)" % (c["항목"], c["기대"], c["실측"], c["허용오차"])
```

`_reference` 는 기존 `compare`·`worst_detail` 코드를 그대로 옮긴 것이다.

```python
def _reference(code, agent_glb, agent_named, spec, ref_dir: Path) -> dict:
    """참고용 정답 대조 — 합격 여부에는 쓰지 않는다(M8 D4)."""
    ref_glb = ref_dir / "sections" / spec.coord.segment / f"{code}.glb"
    cmp = compare.compare_glb(Path(agent_glb), ref_glb)
    ref_named = load_named(ref_glb)
    worst_detail = []
    for w in cmp["worst"][:4]:
        if within_bbox_tol(w["dev_m"]) or w["node"] not in agent_named or w["node"] not in ref_named:
            continue
        a, r = agent_named[w["node"]].bounds, ref_named[w["node"]].bounds
        axes = []
        for i, ax in enumerate("xyz"):
            for bound, idx in (("min", 0), ("max", 1)):
                o, rf = float(a[idx][i]), float(r[idx][i])
                if not within_bbox_tol(abs(rf - o)):
                    axes.append({"axis": ax, "bound": bound, "ours": round(o, 3), "ref": round(rf, 3),
                                 "delta_mm": int(round((rf - o) * 1000))})
        worst_detail.append({"node": w["node"], "role": node_role(code, w["node"], spec),
                             "ours": [[round(float(v), 3) for v in a[0]], [round(float(v), 3) for v in a[1]]],
                             "ref": [[round(float(v), 3) for v in r[0]], [round(float(v), 3) for v in r[1]]], "axes": axes})
    return {**{k: cmp[k] for k in ("only_ours", "only_ref", "common", "bbox_dev_max_m", "bbox_dev_over_1mm",
                                   "faces_equal", "worst")}, "worst_detail": worst_detail}
```

`summary` 를 교체한다.

```python
def summary(score: dict, attempts: int) -> dict:
    ref = score.get("reference")
    return {"pass": score["pass"], "sanity_fail": score["sanity"]["fail"],
            "section_fail": score["section_selfcheck"]["fail"], "assembled_fail": score["assembled_selfcheck"]["fail"],
            "measure_section_fail": score["measure"]["section_fail"], "measure_fail": score["measure"]["FAIL"],
            "attempts": attempts,
            "bbox_dev_max_m": ref["bbox_dev_max_m"] if ref else None,
            "only_ours": len(ref["only_ours"]) if ref else 0, "only_ref": len(ref["only_ref"]) if ref else 0}
```

`feedback_text` 를 교체한다 — 정답 무관 소견이 먼저다.

```python
def feedback_text(score: dict) -> str:
    """다음 시도 프롬프트용 — 정답 없이도 나오는 소견을 먼저, 정답 대조는 있을 때만 뒤에(M8 D5)."""
    if score["pass"]:
        return "채점: PASS"
    lines = ["채점: FAIL"]
    bad_san = [c for c in score["sanity"]["checks"] if not c["ok"]]
    if bad_san:
        lines.append("기하 건전성 위반: " + " | ".join("%s — %s (%s)" % (c["label"], c["detail"], ", ".join(c["nodes"][:5]))
                                                       for c in bad_san))
    if score["measure"]["failed"]:
        lines.append("재실측 실패(스펙에서 유도한 기대값 대비):")
        lines += ["  " + f for f in score["measure"]["failed"][:8]]
    for key, label in (("section_selfcheck", "섹션 self-check 실패"), ("assembled_selfcheck", "결합 self-check 실패")):
        if score[key]["failed"]:
            lines.append(label + ": " + " | ".join(score[key]["failed"][:8]))
    ref = score.get("reference")
    if ref:
        lines.append("(참고 — 이 교량은 정답 모델이 있어 대조도 싣는다. 합격 여부는 위 항목으로 정한다.)")
        lines.append(BBOX_NOTE)
        if ref["only_ref"]:
            lines.append("빠진 노드: " + ", ".join(ref["only_ref"][:30]))
        if ref["only_ours"]:
            lines.append("남는 노드: " + ", ".join(ref["only_ours"][:30]))
        worst = [w for w in ref["worst"] if not within_bbox_tol(w["dev_m"])]
        if worst:
            lines.append("정답 대비 bbox 편차 상위: " + ", ".join("%s %.0fmm" % (w["node"], w["dev_m"] * 1000) for w in worst[:8]))
        for d in ref.get("worst_detail", []):
            for e in d.get("axes", [])[:6]:
                name = "%s(%s)" % (d["node"], d["role"]) if d.get("role") else d["node"]
                lines.append("  %s: %s %s %s → 정답 %s — %s" % (name, e["axis"], "최대" if e["bound"] == "max" else "최소",
                                                               e["ours"], e["ref"], _delta_phrase(e)))
    return "\n".join(lines)
```

- [ ] **Step 4: 호출부 정리**

`worker/src/m3d/agent/loop.py` 의 `scorer(code, res.glb, spec, ref_dir, work_dir=...)` 호출은 그대로 둔다(위치 인자 호환). `emit` 메시지를 새 요약에 맞춘다:

```python
        emit("info", f"시도 {attempt}: 채점 {'PASS' if sc['pass'] else 'FAIL'} — 건전성 fail {sc['sanity']['fail']}·"
                     f"섹션 fail {sc['section_selfcheck']['fail']}·결합 fail {sc['assembled_selfcheck']['fail']}·"
                     f"재실측 fail {sc['measure']['section_fail']}")
```

- [ ] **Step 5: 통과 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_agent_score.py tests/test_agent_loop.py tests/test_model_publish.py -q`
Expected: PASS. 기존 테스트가 옛 키(`compare`)를 보면 `reference` 로 고친다.

- [ ] **Step 6: Commit**

```bash
cd /d/Projects/model3d-studio && git add worker/src/m3d/agent/score.py worker/src/m3d/agent/loop.py worker/tests/test_agent_score.py worker/tests/test_agent_loop.py
git commit -m "feat(agent): 합격 규칙을 정답 무관으로 — 건전성·self-check·섹션 재실측; 정답 대조는 참고 정보로(M8 D4·D5)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: 회귀 검증 `m3d verify-rule`

**Files:**
- Create: `worker/src/m3d/model/verify_rule.py`
- Modify: `worker/src/m3d/cli.py`
- Test: `worker/tests/test_model_verify_rule.py` (신규)

**Interfaces:**
- Consumes: Task 4 의 `score.score_section(code, glb, spec, ref_dir, work_dir=)`, `score.summary`.
- Produces: `verify_rule.collect(cfg, dataset) -> list[dict]` (`{"job_id", "code", "glb"}`);
  `verify_rule.run_rule(cfg, dataset, *, ref_dir=None, out_dir=None) -> dict` — `{"rows": [...], "matrix": {...}, "false_pass": [...], "false_fail": [...]}`.
  구간 이름은 `"≤5mm"`, `"5~100mm"`, `"≥100mm"`.

- [ ] **Step 1: 실패하는 테스트 작성**

`worker/tests/test_model_verify_rule.py` (신규):

```python
"""회귀 검증 (M8 D6) — 기존 에이전트 산출에 새 규칙을 돌려 혼동표를 낸다. LLM·업로드 없음."""

import dataclasses
import json

import pytest

from m3d.agent.score import load_named
from m3d.config import load_config
from m3d.model import sections as X
from m3d.model import verify_rule
from m3d.model.builder import Builder
from m3d.model.spec import ModelSpec


@pytest.fixture(scope="module")
def ref_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("ref")
    spec = ModelSpec()
    b = Builder(spec)
    b.export_sections(X.split(b.build(pilot=False), spec.coord.segment), d)
    (d / "modelspec.json").write_text(json.dumps({"spec": spec.model_dump(), "sources": {}, "stats": {}}), encoding="utf-8")
    return d


@pytest.fixture
def cfg(tmp_path, monkeypatch, ref_dir):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    c = dataclasses.replace(load_config(env_file=tmp_path / "absent.env"), repo_root=tmp_path)
    model = c.derived_dir / "ds" / "model"
    model.mkdir(parents=True)
    (model / "modelspec.json").write_text((ref_dir / "modelspec.json").read_text(encoding="utf-8"), encoding="utf-8")
    return c


def _job(cfg, job_id, code, ref_dir, shift):
    d = cfg.derived_dir / "ds" / "model" / "agent" / job_id
    (d / "agent").mkdir(parents=True)
    (d / "sections" / "P4P5").mkdir(parents=True)
    named = load_named(ref_dir / "sections" / "P4P5" / f"{code}.glb")
    if shift:
        list(named.values())[0].apply_translation([0, shift, 0])
    Builder(ModelSpec()).export(named, d / "sections" / "P4P5" / f"{code}.glb")
    (d / "build.json").write_text(json.dumps({"kind": "agent", "segment": "P4P5",
                                              "sections": [{"code": code, "source": "agent"}]}), encoding="utf-8")
    (d / "agent" / "score.json").write_text(json.dumps({"summary": {"pass": False}}), encoding="utf-8")


def test_collect_finds_agent_outputs(cfg, ref_dir):
    _job(cfg, "j1", "SP04", ref_dir, 0.0)
    _job(cfg, "j2", "DIA", ref_dir, 0.02)
    got = verify_rule.collect(cfg, "ds")
    assert sorted((g["job_id"], g["code"]) for g in got) == [("j1", "SP04"), ("j2", "DIA")]


def test_matrix_buckets_by_reference_deviation(cfg, ref_dir, tmp_path):
    _job(cfg, "ok", "SP04", ref_dir, 0.0)          # 편차 0 → ≤5mm
    _job(cfg, "mid", "SP04", ref_dir, 0.05)        # 50mm → 5~100mm
    _job(cfg, "big", "SP04", ref_dir, 1.0)         # 1m → ≥100mm
    r = verify_rule.run_rule(cfg, "ds", ref_dir=ref_dir, out_dir=tmp_path)
    m = r["matrix"]
    assert m["≤5mm"]["합격"] == 1 and m["≤5mm"]["불합격"] == 0
    assert m["≥100mm"]["합격"] == 0 and m["≥100mm"]["불합격"] == 1
    assert r["false_pass"] == [] and r["false_fail"] == []
```

- [ ] **Step 2: 실패 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_model_verify_rule.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'm3d.model.verify_rule'`

- [ ] **Step 3: 구현**

`worker/src/m3d/model/verify_rule.py`:

```python
"""회귀 검증 (M8 D6) — 이미 쌓인 에이전트 산출에 새 합격 규칙을 돌려 본다. LLM 호출·업로드 없음.

규칙이 쓸모 있으려면 (1) 정답 대비 크게 어긋난 산출을 불합격시키고 (2) 정답과 같은 산출을 합격시켜야 한다.
"""

from __future__ import annotations

import json
from pathlib import Path

from m3d.agent import score as agent_score
from m3d.config import Config
from m3d.model import io as model_io
from m3d.model.spec import ModelSpec

BUCKETS = ("≤5mm", "5~100mm", "≥100mm")
BIG_M = 0.100
SMALL_M = 0.005


def bucket_of(dev_m) -> str:
    if dev_m is None:
        return "≥100mm"
    if dev_m <= SMALL_M + 1e-4:
        return "≤5mm"
    return "5~100mm" if dev_m < BIG_M else "≥100mm"


def collect(cfg: Config, dataset: str) -> list[dict]:
    """에이전트 잡 디렉터리 → [{job_id, code, glb}]."""
    root = model_io.model_dir(cfg, dataset) / "agent"
    out: list[dict] = []
    if not root.is_dir():
        return out
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        build = d / "build.json"
        if not build.is_file():
            continue
        try:
            meta = json.loads(build.read_text(encoding="utf-8"))
        except ValueError:
            continue
        code = next((s["code"] for s in meta.get("sections", []) if s.get("source") == "agent"), None)
        if code is None:
            continue
        glb = d / "sections" / meta.get("segment", "P4P5") / f"{code}.glb"
        if glb.is_file():
            out.append({"job_id": d.name, "code": code, "glb": glb})
    return out


def run_rule(cfg: Config, dataset: str, *, ref_dir=None, out_dir=None) -> dict:
    """각 산출에 새 규칙을 적용하고 (편차 구간 × 합격) 혼동표를 낸다."""
    raw = model_io.load_modelspec_raw(cfg, dataset)
    spec = ModelSpec.model_validate(raw["spec"])
    ref_dir = Path(ref_dir) if ref_dir else model_io.model_dir(cfg, dataset)
    out_dir = Path(out_dir) if out_dir else model_io.model_dir(cfg, dataset) / "verify-rule"
    out_dir.mkdir(parents=True, exist_ok=True)
    matrix = {b: {"합격": 0, "불합격": 0} for b in BUCKETS}
    rows, false_pass, false_fail = [], [], []
    for item in collect(cfg, dataset):
        try:
            sc = agent_score.score_section(item["code"], item["glb"], spec, ref_dir,
                                           work_dir=out_dir / item["job_id"])
        except Exception as exc:                      # noqa: BLE001 — 임의 산출물에서도 끝까지 돈다
            rows.append({**{k: str(v) for k, v in item.items()}, "error": "%s: %s" % (type(exc).__name__, exc),
                         "pass": False, "bucket": "≥100mm"})
            matrix["≥100mm"]["불합격"] += 1
            continue
        dev = (sc.get("reference") or {}).get("bbox_dev_max_m")
        bucket = bucket_of(dev)
        matrix[bucket]["합격" if sc["pass"] else "불합격"] += 1
        row = {"job_id": item["job_id"], "code": item["code"], "bbox_dev_m": dev, "bucket": bucket,
               "pass": sc["pass"], "sanity_fail": sc["sanity"]["fail"],
               "section_fail": sc["section_selfcheck"]["fail"], "assembled_fail": sc["assembled_selfcheck"]["fail"],
               "measure_section_fail": sc["measure"]["section_fail"],
               "measure_failed": sc["measure"]["failed"][:3]}
        rows.append(row)
        if bucket == "≥100mm" and sc["pass"]:
            false_pass.append(row)
        if bucket == "≤5mm" and not sc["pass"]:
            false_fail.append(row)
    result = {"rows": rows, "matrix": matrix, "false_pass": false_pass, "false_fail": false_fail,
              "총건수": len(rows)}
    (out_dir / "verify_rule.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return result
```

`worker/src/m3d/cli.py` 의 `agent-assemble` 명령 앞에 추가:

```python
@app.command("verify-rule")
def verify_rule_cmd(
    dataset: str = typer.Option("ab1-p4p5", "--dataset"),
) -> None:
    """[13] 회귀 검증 — 기존 에이전트 산출에 정답 무관 합격 규칙을 돌려 혼동표를 낸다 (M8 D6). 무과금."""
    from m3d.model import verify_rule
    cfg = load_config()
    r = verify_rule.run_rule(cfg, dataset)
    typer.echo("총 %d건" % r["총건수"])
    typer.echo("%-10s %6s %8s" % ("정답편차", "합격", "불합격"))
    for b, v in r["matrix"].items():
        typer.echo("%-10s %6d %8d" % (b, v["합격"], v["불합격"]))
    for label, key in (("거짓 합격(크게 틀렸는데 통과)", "false_pass"), ("거짓 불합격(맞는데 탈락)", "false_fail")):
        if r[key]:
            typer.echo("\n%s %d건:" % (label, len(r[key])))
            for row in r[key]:
                typer.echo("  %s %s dev=%s · 건전성 %s · 섹션 %s · 결합 %s · 재실측 %s %s" %
                           (row["job_id"][:8], row["code"], row["bbox_dev_m"], row["sanity_fail"],
                            row["section_fail"], row["assembled_fail"], row["measure_section_fail"],
                            row["measure_failed"][:1]))
    raise typer.Exit(code=1 if r["false_pass"] else 0)
```

- [ ] **Step 4: 통과 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_model_verify_rule.py -q && .venv/Scripts/m3d.exe verify-rule --help`
Expected: PASS, 도움말 표시.

- [ ] **Step 5: Commit**

```bash
cd /d/Projects/model3d-studio && git add worker/src/m3d/model/verify_rule.py worker/src/m3d/cli.py worker/tests/test_model_verify_rule.py
git commit -m "feat(model): m3d verify-rule — 기존 산출에 정답 무관 규칙을 돌려 혼동표(M8 D6)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: 웹 판정 블록 분리

**Files:**
- Modify: `contracts/db.types.ts` (`AgentScoreSummary`), `web/src/components/VerifyPanel.tsx:67-78`
- Test: `web/src/lib/models.test.ts`

**Interfaces:**
- Consumes: Task 4 의 `summary()` 키.
- Produces: `AgentScoreSummary` 에 `sanity_fail: number`, `measure_section_fail: number` 추가, `bbox_dev_max_m: number | null` 유지, `only_ours`·`only_ref` 유지.

- [ ] **Step 1: 실패하는 테스트 작성**

`web/src/lib/models.test.ts` 끝에 추가:

```ts
describe('AgentScoreSummary (M8)', () => {
  it('정답 무관 필드와 참고용 정답 대조 필드가 함께 온다', () => {
    const s = {
      pass: false, sanity_fail: 1, section_fail: 0, assembled_fail: 0,
      measure_section_fail: 2, measure_fail: 2, attempts: 3,
      bbox_dev_max_m: null, only_ours: 0, only_ref: 0,
    };
    expect(s.sanity_fail + s.measure_section_fail).toBe(3);
    expect(s.bbox_dev_max_m).toBeNull();          // 정답 없는 교량
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd /d/Projects/model3d-studio/web && npm run typecheck`
Expected: FAIL — `Object literal may only specify known properties, and 'sanity_fail' does not exist in type ...` (테스트는 `AgentScoreSummary` 타입을 명시하지 않으면 통과할 수 있으므로, 타입을 붙여 쓴다: `const s: AgentScoreSummary = {...}` 로 시작하고 `import type { AgentScoreSummary } from '../../../contracts/db.types';` 를 파일 상단에 더한다.)

- [ ] **Step 3: 타입·화면 수정**

`contracts/db.types.ts`:

```ts
export interface AgentScoreSummary {
  pass: boolean; sanity_fail: number; section_fail: number; assembled_fail: number;
  measure_section_fail: number; measure_fail: number | null; attempts: number;
  bbox_dev_max_m: number | null; only_ours: number; only_ref: number;
}
```

`web/src/components/VerifyPanel.tsx` 의 채점 블록(69~78행)을 두 줄로 나눈다.

```tsx
              {agent ? (
                <Stack gap={2}>
                  <Text size="xs">
                    정답 무관 판정 — 건전성 fail {agent.sanity_fail} · 섹션 fail {agent.section_fail}
                    {' '}· 결합 fail {agent.assembled_fail} · 재실측 fail {agent.measure_section_fail} · 시도 {agent.attempts}
                  </Text>
                  {agent.bbox_dev_max_m !== null && (
                    <Text size="xs" c="dimmed">
                      참고: 정답 대조 — 노드 누락 {agent.only_ref} · 초과 {agent.only_ours}
                      {' '}· bbox {(agent.bbox_dev_max_m * 1000).toFixed(0)}mm
                    </Text>
                  )}
                </Stack>
              ) : <Text size="xs" c="dimmed">채점 정보 없음</Text>}
```

- [ ] **Step 4: 통과 확인**

Run: `cd /d/Projects/model3d-studio/web && npm test -- --run && npm run typecheck`
Expected: vitest 전건 PASS, tsc 오류 0

- [ ] **Step 5: Commit**

```bash
cd /d/Projects/model3d-studio && git add contracts/db.types.ts web/src/components/VerifyPanel.tsx web/src/lib/models.test.ts
git commit -m "feat(web): 검증 패널에 정답 무관 판정과 참고용 정답 대조를 나눠 표시(M8 D4)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: 실증(≤ $5)·판정서·README·통합

**Files:**
- Create: `data/derived/ab1-p4p5/model/acceptance-m8.md` (gitignored)
- Modify: `README.md`, 메모리 `C:\Users\parkj\.claude\projects\D--Projects-model3d-studio\memory\`

- [ ] **Step 1: 전건 테스트**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest -q` 그리고 `cd /d/Projects/model3d-studio/web && npm test -- --run && npm run typecheck`
Expected: pytest 436 → 455 안팎 전건 PASS, vitest 24, tsc 0. 실패가 있으면 여기서 멈추고 고친다.

- [ ] **Step 2: 회귀 검증 (무과금, 기준 ①)**

```bash
cd /d/Projects/model3d-studio/worker && export PYTHONUTF8=1 && .venv/Scripts/m3d.exe verify-rule
```

혼동표를 읽는다. **거짓 합격(≥100 mm 인데 통과)이 하나라도 있으면** 그 섹션의 재실측 항목이 모자란다는 뜻이니 Task 2 로 돌아가 항목을 더하고(테스트·커밋) 다시 돌린다. 무과금이므로 필요한 만큼 반복한다.
**거짓 불합격(≤5 mm 인데 탈락)**은 기대식이 지나치게 엄하거나 틀렸다는 뜻이니 그 항목을 고친다.

- [ ] **Step 3: 실증 잡 2건**

웹(`/p/ab1-p4p5/model`)에서 **HST·SP04** 두 섹션을 골라 예산 20.03 으로 잡을 만들고:

```bash
cd /d/Projects/model3d-studio/worker && export PYTHONUTF8=1 && .venv/Scripts/m3d.exe worker --poll 2 --drain
```

재실측 항목이 0건이던 두 섹션이 이제 진짜 검사를 통과하는지 본다. 결과를 표로 기록한다.

- [ ] **Step 4: 화면 확인**

브라우저에서 새 빌드를 열어 채점 블록이 "정답 무관 판정"과 "참고: 정답 대조" 두 줄로 나뉘어 보이는지 DOM 텍스트로 확인한다.

- [ ] **Step 5: 판정서**

`data/derived/ab1-p4p5/model/acceptance-m8.md`: 기준 ①~⑤ 결과·근거, 혼동표 전문, 섹션별 재실측 항목 수 변화(전/후), 건전성 검사가 잡은 사례, 실증 잡 결과, **한계**(우리 기대식은 이 교량의 관례를 따라 검증되었다 — 다른 교량에서는 기대식도 고쳐야 한다), 다음 후보.

- [ ] **Step 6: README·메모리**

README "## LLM 모델링 (M5)" 절에 "### M8 — 정답 없는 합격 규칙" 소절: 무엇을 바꿨나(섹션 태그·재실측 보강·건전성·규칙 전환·verify-rule), 혼동표 결과 한 줄, 사용법(`m3d verify-rule`). 메모리에 M8 파일과 `MEMORY.md` 한 줄.

- [ ] **Step 7: 통합**

```bash
cd /d/Projects/model3d-studio && git add README.md && git commit -m "docs: README M8 정답 없는 합격 규칙 절

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

그다음 superpowers:finishing-a-development-branch — 전건 테스트 → 병합 방식은 사용자 선택.
