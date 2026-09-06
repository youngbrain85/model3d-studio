# M4 섹션 단위 산출·검수·레고식 결합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> 이 프로젝트 규칙: 서브에이전트 없이 **이 세션에서 직접** 실행한다(비용 원칙). 각 태스크는 TDD(실패 테스트 → 구현 → 통과 → 커밋).

**Goal:** P4~P5 모델을 섹션(구간/부재그룹) GLB 10개 + 결합본으로 산출해 Storage 에 올리고, 웹 `/p/<slug>/model` 에서 섹션을 따로 띄워 내부까지 검수하고 승인/반려를 기록한다 (설계서 `docs/superpowers/specs/2026-09-05-m4-section-viewer-design.md`).

**Architecture:** worker 는 기존 빌더 결과(`named`)를 노드명 접두로 섹션 분할·결합(`model/sections.py`)하고 그룹 태그 self-check 로 섹션별 판정을 낸 뒤 `m3d publish-model` 로 버킷 `models` 에 올리고 `builds`·`build_sections` 행을 만든다. 웹은 three.js 직접(`lib/viewer/scene.ts`)으로 섹션 GLB 를 서명 URL 로 각각 로드해 한 씬에 얹고(레고식 결합), 검증 패널·승인(`approvals` append-only + 트리거)을 붙인다.

**Tech Stack:** Python 3.12(trimesh 5·numpy·psycopg 3·typer·pydantic 2), Supabase(PostgreSQL RLS·Storage), React 18 + Vite 6 + Mantine 8 + supabase-js 2 + three 0.184, pytest·vitest.

## Global Constraints

- LLM 호출 0. Anthropic API 를 부르는 코드 경로를 M4 에서 추가하지 않는다.
- 비밀값(`SUPABASE_SERVICE_KEY`·`SUPABASE_DB_URL`)은 로그·출력·보고서에 남기지 않는다. 웹 번들에는 `VITE_` 2개만.
- 참조 원본 `D:\Projects\Inspection\...` 은 읽기 전용.
- 실행 명령: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests -q` (Bash 에서 리포 루트 기준) / `npm --prefix web run typecheck` / `npm --prefix web test`. python 인라인 코드는 heredoc 으로.
- 섹션 키 = `<segment>/<CODE>`, `segment` 는 `ModelSpec.coord.segment`(기본 `"P4P5"`), CODE ∈ `BOX DIA FRM RIB HST WG CS SLAB SP04 BRG`(이 순서). 노드→그룹 정규식 `^[A-Z0-9]+_[A-Z0-9]+_(BOX|DIA|FRM|RIB|HST|WG|CS|SLAB|BARRIER|SP04|BRG)(?:_|\d|$)`, BARRIER → SLAB.
- 산출 디렉터리: 전체 `data/derived/<ds>/model/`, 시범 `data/derived/<ds>/model/pilot/` — 안의 파일명은 동일(`AB1_P4P5.glb`, `sections/<segment>/<CODE>.glb`, `selfcheck.json`, `selfcheck_sections.json`, `build.json`, `modelspec.json`, `renders/*.png`, `renders/views.json`). `_pilot` 접미 파일은 폐기.
- Storage 버킷 `models`(비공개). 오브젝트 키 `<slug>/b<version>/<상대경로 posix>`. 워커 `model/publish.py::object_key` 와 웹 `lib/models.ts::modelObjectKey` 는 같은 문자열을 내야 한다(양쪽 테스트에 같은 예시: `("ab1-p4p5", 3, "sections/P4P5/DIA.glb") → "ab1-p4p5/b3/sections/P4P5/DIA.glb"`).
- 버전 규칙(D7): `content_sha256 = sha256(hex(glb) + hex(modelspec))` 문자열 해시. 최신 빌드와 같고 `--force` 아니면 skip.
- DB 3표 `builds`·`build_sections`·`approvals`, 상태값 `'대기'|'승인'|'반려'`, 승인 verdict `'승인'|'반려'`. approvals 는 append-only(update/delete 정책 없음), insert 는 `user_id = auth.uid()` 만.
- 검증 없는 완료 보고 금지: 각 태스크 마지막에 실제 실행 출력을 확인한다. 커밋 메시지 끝: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- 브랜치 `feat/m4-section-viewer`(main b495464 분기). 시범 게이트(D10): Task 5 끝에서 사용자 확인 후 Task 6.

## File Structure

| 경로 | 책임 |
|---|---|
| `worker/src/m3d/model/sections.py` (신규) | 그룹 코드·라벨, `group_of`, `section_key`, `split`, `assemble` — 순수 함수, trimesh 만 |
| `worker/src/m3d/model/spec.py` (수정) | `Coord.segment` |
| `worker/src/m3d/model/selfcheck.py` (수정) | 항목별 `group` 태그, `section=` 필터, 수밀 전건 검사 |
| `worker/src/m3d/model/builder.py` (수정) | `export_sections(sections, out_dir)` |
| `worker/src/m3d/model/io.py` (수정) | `model_dir(cfg, ds, *, pilot=False)`, `write_build_json` |
| `worker/src/m3d/model/render.py` (수정) | `render(..., frame_out=)`, `views.json` |
| `worker/src/m3d/model/publish.py` (신규) | `m3d publish-model` 본체 — 파일 수집·해시·업로드·DB 행 |
| `worker/src/m3d/cli.py` (수정) | `build`·`render` 경로 재편, `publish-model` 명령 |
| `worker/src/m3d/db.py` (수정) | `TABLES` 3표 추가 |
| `supabase/migrations/0005_builds.sql` (신규) | 3표·RLS·트리거·버킷 |
| `contracts/db.types.ts` (수정) | 3표 타입 |
| `web/src/lib/models.ts` (신규) | 데이터 접근 + 순수 함수(`modelObjectKey`·`latestApprovals`·`approvalPayload`) |
| `web/src/lib/viewer/math.ts` (신규) | 순수 계산: 클리핑 평면·프리셋 카메라·거리↔z |
| `web/src/lib/viewer/scene.ts` (신규) | three.js 뷰어(React 무관): 로드·표시·단독·클리핑·프리셋·피킹 |
| `web/src/routes/Model.tsx` (신규) | 검수 화면 레이아웃·상태·패널 |
| `web/src/App.tsx`·`web/src/routes/Projects.tsx` (수정) | 라우트·링크 |
| 테스트 | `worker/tests/test_model_sections.py`, `test_model_builder.py`(확장), `test_model_render.py`(확장), `test_migration_0005.py`, `test_db_tables.py`, `test_model_publish.py`; `web/src/lib/models.test.ts`, `web/src/lib/viewer/math.test.ts` |

---

### Task 1: 섹션 분할·결합 + 그룹 태그 self-check + 산출 디렉터리 재편

**Files:**
- Create: `worker/src/m3d/model/sections.py`, `worker/tests/test_model_sections.py`
- Modify: `worker/src/m3d/model/spec.py` (Coord), `worker/src/m3d/model/selfcheck.py`, `worker/src/m3d/model/builder.py` (export_sections), `worker/src/m3d/model/io.py`, `worker/src/m3d/cli.py` (`build`·`render`·`measure`·`compare_model`), `worker/tests/test_model_builder.py`, `README.md`(3D 모델 절 경로 2줄)

**Interfaces:**
- Consumes: `Builder.build(pilot) -> dict[name, Trimesh]`, `Builder.export(named, glb_path)`, `selfcheck.run(named, b, *, pilot)`, `model_io.model_dir(cfg, ds)`.
- Produces: `sections.GROUPS: list[tuple[code, label]]`, `sections.CODES`, `sections.group_of(name) -> str`, `sections.section_key(segment, code) -> str`, `sections.split(named, segment) -> dict[key, dict[name, mesh]]`(비어 있는 그룹 제외), `sections.assemble(sections) -> dict[name, mesh]`;
  `selfcheck.run(named, b, *, pilot=False, section: str | None = None)` — 결과 checks 항목에 `"group"` 필드;
  `Builder.export_sections(sections, out_dir) -> list[dict]` (`{key, code, label, file, meshes, triangles, bytes, sha256}`; file = `sections/<segment>/<CODE>.glb` posix);
  `model_io.model_dir(cfg, ds, *, pilot=False) -> Path`, `model_io.write_build_json(out_dir, data) -> Path`;
  `build.json` 형식: `{"kind": "pilot"|"full", "segment", "assembled": {"file": "AB1_P4P5.glb", "meshes", "triangles", "bytes", "sha256"}, "sections": [...위 dict + "selfcheck": {"pass","fail"}], "selfcheck": {"pass","fail","skipped"}, "git_sha": str|None}`.

- [ ] **Step 1: 실패 테스트 — sections 순수 함수**

`worker/tests/test_model_sections.py`:
```python
"""섹션 = 구간/부재그룹 — 노드명→그룹, 분할, 결합 (M4 설계 D1·D2)."""

import pytest

from m3d.model import sections as S
from m3d.model.builder import Builder
from m3d.model.spec import ModelSpec


@pytest.fixture(scope="module")
def full():
    return Builder(ModelSpec()).build(pilot=False)


def test_group_of_covers_every_naming_pattern():
    cases = {"AB1_S5_BOX_TOP": "BOX", "AB1_S5_DIA01": "DIA", "AB1_S5_FRM01_TRW": "FRM", "AB1_S5_RIB_TP4_1": "RIB",
             "AB1_S5_HST_UP_R": "HST", "AB1_S5_WG096R": "WG", "AB1_S5_WG096R_ST": "WG", "AB1_S5_CS121L": "CS",
             "AB1_S5_SLAB": "SLAB", "AB1_S5_BARRIER_CTR": "SLAB", "AB1_S5_SP04_TF": "SP04", "AB1_S5_BRG_P4_1_SOLE": "BRG"}
    for name, code in cases.items():
        assert S.group_of(name) == code, name
    with pytest.raises(ValueError):
        S.group_of("AB1_S5_UNKNOWN_1")
    assert S.section_key("P4P5", "DIA") == "P4P5/DIA"
    assert S.CODES == ["BOX", "DIA", "FRM", "RIB", "HST", "WG", "CS", "SLAB", "SP04", "BRG"]


def test_split_full_build_into_ten_sections_with_expected_counts(full):
    secs = S.split(full, "P4P5")
    assert list(secs) == [f"P4P5/{c}" for c in S.CODES]
    counts = {k.split("/")[1]: len(v) for k, v in secs.items()}
    assert counts == {"BOX": 4, "DIA": 26, "FRM": 150, "RIB": 93, "HST": 10, "WG": 156, "CS": 52, "SLAB": 4, "SP04": 4, "BRG": 16}


def test_split_pilot_has_only_box_and_dia():
    named = Builder(ModelSpec()).build(pilot=True)
    assert list(S.split(named, "P4P5")) == ["P4P5/BOX", "P4P5/DIA"]


def test_assemble_restores_node_set_and_rejects_duplicates(full):
    secs = S.split(full, "P4P5")
    back = S.assemble(secs)
    assert set(back) == set(full) and all(back[n] is full[n] for n in full)
    dup = {"P4P5/A": {"AB1_S5_DIA01": full["AB1_S5_DIA01"]}, "P4P5/B": {"AB1_S5_DIA01": full["AB1_S5_DIA01"]}}
    with pytest.raises(AssertionError):
        S.assemble(dup)
```

- [ ] **Step 2: 실패 확인**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_model_sections.py -q`
Expected: FAIL — `ModuleNotFoundError: m3d.model.sections`

- [ ] **Step 3: sections.py 구현 + Coord.segment**

`worker/src/m3d/model/sections.py`:
```python
"""섹션 = 구간/부재그룹 (M4 설계 D1·D2) — 노드명 → 그룹, 분할, 결합. 순수 함수(빌더·DB 무관).

전 부재가 전역 체인 좌표(받침선 + n×간격)에 놓여 있어 결합은 좌표 변환 없는 합치기다(KB §2-18).
"""

from __future__ import annotations

import re

import trimesh

GROUPS: list[tuple[str, str]] = [
    ("BOX", "본체"), ("DIA", "격벽"), ("FRM", "개방 프레임"), ("RIB", "종리브"), ("HST", "수평보강재"),
    ("WG", "외측가로보"), ("CS", "외측빔"), ("SLAB", "슬래브·방호벽"), ("SP04", "이음판"), ("BRG", "받침"),
]
CODES = [c for c, _ in GROUPS]
LABELS = dict(GROUPS)
_NODE = re.compile(r"^[A-Z0-9]+_[A-Z0-9]+_(BOX|DIA|FRM|RIB|HST|WG|CS|SLAB|BARRIER|SP04|BRG)(?:_|\d|$)")


def group_of(name: str) -> str:
    """노드명 → 그룹 코드. BARRIER 는 슬래브 그룹."""
    m = _NODE.match(name)
    if m is None:
        raise ValueError("그룹을 알 수 없는 노드명: %s" % name)
    code = m.group(1)
    return "SLAB" if code == "BARRIER" else code


def section_key(segment: str, code: str) -> str:
    return f"{segment}/{code}"


def split(named: dict[str, trimesh.Trimesh], segment: str) -> dict[str, dict[str, trimesh.Trimesh]]:
    """노드 dict → {섹션 키: {노드명: 메시}} (CODES 순서, 빈 그룹 제외 — 시범은 BOX·DIA 만)."""
    out: dict[str, dict[str, trimesh.Trimesh]] = {section_key(segment, c): {} for c in CODES}
    for name, mesh in named.items():
        out[section_key(segment, group_of(name))][name] = mesh
    return {k: v for k, v in out.items() if v}


def assemble(sections: dict[str, dict[str, trimesh.Trimesh]]) -> dict[str, trimesh.Trimesh]:
    """레고식 결합 — 변환 없이 합친다. 노드명 중복은 결함(KB §2-15)."""
    named: dict[str, trimesh.Trimesh] = {}
    for key in sections:
        for name, mesh in sections[key].items():
            assert name not in named, "결합 중 노드명 중복: %s (%s)" % (name, key)
            named[name] = mesh
    return named
```

`worker/src/m3d/model/spec.py` `Coord` 에 추가(`walk_side_sign` 다음 줄):
```python
    segment: str = "P4P5"               # 구간 키 — 섹션 키 접두 (M4 D1)
```

- [ ] **Step 4: 통과 확인**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_model_sections.py worker/tests/test_model_spec.py -q`
Expected: PASS (spec 테스트의 `default` 통계는 `> 0` 조건이라 필드 추가에 영향 없음)

- [ ] **Step 5: 실패 테스트 — 그룹 태그 self-check·export_sections·결합 동일성**

`worker/tests/test_model_builder.py` 끝에 추가:
```python


# ── 섹션 (M4 Task 1) ──────────────────────────────────────────────────────────────
def test_selfcheck_has_group_tags_and_section_filter(full):
    from m3d.model import sections as S
    b, named = full
    r_all = selfcheck.run(named, b, pilot=False)
    groups = {c["label"]: c["group"] for c in r_all["checks"]}
    assert groups["격벽 26"] == "DIA" and groups["프레임 부재 25×6=150"] == "FRM"
    assert groups["bbox x(상부구조)"] == "ASSEMBLY" and groups["수밀 전건"] == "COMMON"
    assert any(l.startswith("내공 H") and g == "BOX" for l, g in groups.items())
    secs = S.split(named, "P4P5")
    r_dia = selfcheck.run(secs["P4P5/DIA"], b, section="DIA")
    labels = {c["label"] for c in r_dia["checks"]}
    assert r_dia["fail"] == 0 and r_dia["skipped"] == 0
    assert "격벽 26" in labels and "수밀 전건" in labels and "메시 수 ≥1" in labels
    assert not any(l.startswith("bbox") or l.startswith("내공 H") for l in labels)
    r_box = selfcheck.run(secs["P4P5/BOX"], b, section="BOX")
    assert r_box["fail"] == 0 and sum(1 for c in r_box["checks"] if c["label"].startswith("내공 H")) == 8
    for key, meshes in secs.items():
        assert selfcheck.run(meshes, b, section=key.split("/")[1])["fail"] == 0, key


def test_export_sections_and_assembly_equal_monolithic(full, tmp_path):
    from m3d.model import compare as C
    from m3d.model import sections as S
    b, named = full
    secs = S.split(named, "P4P5")
    meta = b.export_sections(secs, tmp_path)
    assert [m["code"] for m in meta] == S.CODES
    assert all((tmp_path / m["file"]).is_file() and m["bytes"] > 0 and len(m["sha256"]) == 64 for m in meta)
    assert meta[1] == {**meta[1], "key": "P4P5/DIA", "label": "격벽", "meshes": 26, "file": "sections/P4P5/DIA.glb"}
    assembled = tmp_path / "AB1_P4P5.glb"
    b.export(S.assemble(secs), assembled)
    mono = tmp_path / "mono.glb"
    b.export(named, mono)
    g = C.compare_glb(assembled, mono)
    assert g["only_ours"] == [] and g["only_ref"] == [] and g["common"] == 515
    assert g["bbox_dev_max_m"] == 0.0 and g["faces_equal"] is True
```

- [ ] **Step 6: 실패 확인**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_model_builder.py -q -k "group_tags or export_sections"`
Expected: FAIL — `KeyError: 'group'` / `AttributeError: export_sections`

- [ ] **Step 7: selfcheck.py 재작성(그룹 태그·section 필터·수밀)**

`worker/src/m3d/model/selfcheck.py` 전체를 아래로 교체:
```python
"""빌더 self-check (지식베이스 §6-1) — 계획고·bbox·내공 H 8점·부재 개수·받침 EL·수밀·컬러.

항목마다 `group` 태그(BOX·DIA·FRM·WG·CS·BRG·ASSEMBLY·COMMON)를 붙인다. `section=` 을 주면 그 섹션 메시만 받아
그룹이 section 또는 COMMON 인 항목만 실행한다(M4 D3). pilot(본체·격벽만) 이면 개수·받침 항목은 skipped.
"""

from __future__ import annotations

import re

import numpy as np
import trimesh

from m3d.model.builder import Builder


def run(named: dict[str, trimesh.Trimesh], b: Builder, *, pilot: bool = False, section: str | None = None) -> dict:
    s = b.s
    checks: list[dict] = []

    def want(group):
        return section is None or group in (section, "COMMON")

    def check(label, ok, detail, group):
        if want(group):
            checks.append({"label": label, "ok": bool(ok), "detail": detail, "group": group})

    def skip(label, group):
        if want(group):
            checks.append({"label": label, "ok": None, "detail": "pilot — skipped", "group": group})

    def cnt(pat):
        return sum(1 for n in named if re.match(pat, n))

    # 0) 계획고 기준 검산 — EL(P4)/EL(P5) 는 계획고 식에서 유도(정보 + 단조 증가)
    el4, el5 = b.el_road(b.Z_P4), b.el_road(b.Z_P5)
    check("계획고 P4<P5(종단경사 부호)", el5 > el4, "EL(P4)=%.3f EL(P5)=%.3f" % (el4, el5), "BOX")

    # 1) bbox — 상부구조(받침 제외), 결합본에서만 의미 있음
    if want("ASSEMBLY"):
        sup = trimesh.util.concatenate([m for n, m in named.items() if not n.startswith("AB1_S5_BRG_")])
        bb = sup.bounds
        x_exp = s.slab.half_width if not pilot else s.box.half_flange
        check("bbox x(상부구조)", abs(bb[0][0] + x_exp) < 0.01 and abs(bb[1][0] - x_exp) < 0.01,
              "x[%.3f, %.3f] (기대 ±%.2f)" % (bb[0][0], bb[1][0], x_exp), "ASSEMBLY")
        z_lo_exp, z_hi_exp = (b.Z_P4, b.Z_P5) if pilot else (b.Z_P4 - 0.15, b.Z_P5 + 0.15)
        check("bbox z(상부구조)", abs(bb[0][2] - z_lo_exp) < 0.05 and abs(bb[1][2] - z_hi_exp) < 0.16,
              "z[%.3f, %.3f] (기대 [%.2f, %.2f])" % (bb[0][2], bb[1][2], z_lo_exp, z_hi_exp), "ASSEMBLY")

    # 2) 내공 H 8점 — BOX_TOP 하면 − BOX_BOT 상면 슬라이스 실측
    if want("BOX"):
        vt = np.asarray(named["AB1_S5_BOX_TOP"].vertices)
        vb = np.asarray(named["AB1_S5_BOX_BOT"].vertices)
        for (zc, h_exp) in b.H_CHECK:
            st = vt[np.abs(vt[:, 2] - zc) < 1e-6]
            sb = vb[np.abs(vb[:, 2] - zc) < 1e-6]
            ok = len(st) > 0 and len(sb) > 0
            h_meas = float(st[:, 1].min() - sb[:, 1].max()) if ok else float("nan")
            check("내공 H @P4%+0.3f" % (zc - b.Z_P4), ok and abs(h_meas - h_exp) < 0.002,
                  "실측 %.4f (기대 %.3f)" % (h_meas, h_exp), "BOX")

    # 3) 격벽 z 체인 (KB §2-18) + 개수
    if want("DIA"):
        n_cell = s.diaphragm.n_cell
        dia = sorted(n for n in named if re.match(r"^AB1_S5_DIA\d{2}$", n))
        check("격벽 %d" % (n_cell + 1), len(dia) == n_cell + 1, "%d" % len(dia), "DIA")
        chain_ok = True
        for k, name in enumerate(dia):
            zs = np.asarray(named[name].vertices)[:, 2]
            zc = b.dia_z(k)
            # 판면 정점이 체인 위치 ±10mm 에 있고, 보강재까지 포함한 노드 전체가 ±0.4m 안 (지점 격벽 잭업 350)
            if np.min(np.abs(zs - zc)) > 0.01 or zs.min() < zc - 0.4 or zs.max() > zc + 0.4:
                chain_ok = False
        check("격벽 z 체인 P4+%.1fk" % s.diaphragm.spacing, chain_ok, "판면 정점이 체인 위치 ±10mm", "DIA")

    if pilot and section is None:
        skip("프레임 부재 25×6=150", "FRM"); skip("WG 부재 그룹 52", "WG"); skip("CS 52", "CS")
        skip("받침 부품 16", "BRG"); skip("받침 하면 y", "BRG")
    elif not pilot:
        n_frm = cnt(r"^AB1_S5_FRM\d{2}_(TRW|TRF|BRW|BRF|VSL|VSR)$")
        check("프레임 부재 25×6=150", n_frm == 150, "%d" % n_frm, "FRM")
        n_wg = cnt(r"^AB1_S5_WG\d{3}[LR]$")
        check("WG 부재 그룹 52", n_wg == 52, "%d" % n_wg, "WG")
        n_cs = cnt(r"^AB1_S5_CS\d{3}[LR]$")
        check("CS 52", n_cs == 52, "%d" % n_cs, "CS")
        n_brg = cnt(r"^AB1_S5_BRG_P[45]_[12]_(SOLE|BODY|MORTAR|BLOCK)$")
        check("받침 부품 16", n_brg == 16, "%d" % n_brg, "BRG")
        for pier, el in s.bearing.el_check.items():
            y_exp = el - s.coord.y_datum
            for i in (1, 2):
                m = named.get("AB1_S5_BRG_%s_%d_BODY" % (pier, i))
                y_meas = float(np.asarray(m.vertices)[:, 1].min()) if m is not None else float("nan")
                check("받침 하면 y %s_%d" % (pier, i), m is not None and abs(y_meas - y_exp) < 0.01,
                      "실측 %.4f (기대 %.3f)" % (y_meas, y_exp), "BRG")

    # 4) 메시 수·수밀·색상
    n_mesh = len(named)
    if section is None:
        lo, hi = (25, 40) if pilot else (500, 700)
        check("메시 수 %d~%d" % (lo, hi), lo <= n_mesh <= hi, "%d" % n_mesh, "ASSEMBLY")
    else:
        check("메시 수 ≥1", n_mesh >= 1, "%d" % n_mesh, "COMMON")
    n_wt = sum(1 for m in named.values() if m.is_watertight)
    check("수밀 전건", n_wt == n_mesh, "%d/%d" % (n_wt, n_mesh), "COMMON")
    n_col = sum(1 for m in named.values() if np.asarray(m.visual.face_colors).shape[0] == len(m.faces))
    check("버텍스 컬러 전건", n_col == n_mesh, "%d/%d" % (n_col, n_mesh), "COMMON")
    tris = sum(len(m.faces) for m in named.values())

    passed = sum(1 for c in checks if c["ok"] is True)
    failed = sum(1 for c in checks if c["ok"] is False)
    skipped = sum(1 for c in checks if c["ok"] is None)
    return {"checks": checks, "pass": passed, "fail": failed, "skipped": skipped,
            "meshes": n_mesh, "watertight": n_wt, "triangles": tris, "pilot": pilot, "section": section}
```
주의: 기존 `test_pilot_selfcheck_passes` 는 `skipped == 5`·`pass >= 12` 를 단언한다 — 수밀 항목이 1개 늘어 여전히 만족(pass 16).

- [ ] **Step 8: builder.export_sections + io.model_dir(pilot)·write_build_json**

`worker/src/m3d/model/builder.py` 의 `export` 아래에 추가:
```python
    def export_sections(self, sections: dict[str, dict[str, trimesh.Trimesh]], out_dir) -> list[dict]:
        """섹션별 GLB — out_dir/sections/<segment>/<CODE>.glb. 메타(파일·메시·삼각형·바이트·sha256) 목록을 돌려준다."""
        from pathlib import Path
        from m3d.model.sections import LABELS
        from m3d.samples.manifest import sha256_file
        out = []
        for key, meshes in sections.items():
            segment, code = key.split("/")
            rel = f"sections/{segment}/{code}.glb"
            path = Path(out_dir) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            self.export(meshes, path)
            out.append({"key": key, "code": code, "label": LABELS[code], "file": rel, "meshes": len(meshes),
                        "triangles": int(sum(len(m.faces) for m in meshes.values())),
                        "bytes": path.stat().st_size, "sha256": sha256_file(path)})
        return out
```

`worker/src/m3d/model/io.py`: `model_dir` 를 교체하고 `write_build_json` 추가:
```python
def model_dir(cfg: Config, dataset: str, *, pilot: bool = False) -> Path:
    """산출 디렉터리 — 전체 model/, 시범 model/pilot/ (같은 파일명, M4 D4)."""
    d = cfg.derived_dir / dataset / "model"
    if pilot:
        d = d / "pilot"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_build_json(out_dir: Path, data: dict) -> Path:
    path = Path(out_dir) / "build.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
```
(`save_modelspec`·`load_modelspec`·`modelspec_drift` 는 그대로 `model_dir(cfg, dataset)` = 전체 디렉터리를 쓴다.)

- [ ] **Step 9: CLI build·render 재편**

`worker/src/m3d/cli.py` 의 `build` 본문을 아래로 교체:
```python
@app.command()
def build(
    dataset: str = typer.Argument(..., help="데이터셋 슬러그"),
    pilot: bool = typer.Option(False, "--pilot", help="시범: 본체·격벽만 → model/pilot/ (승인 게이트용)"),
) -> None:
    """[6] ModelSpec → 섹션 GLB(구간/부재그룹) + 결합본 + self-check (M3 §4, M4 D2·D3·D4)."""
    import json as _json
    import shutil
    import subprocess
    from m3d.model import sections as model_sections
    from m3d.model import selfcheck as model_selfcheck
    from m3d.model.builder import Builder
    from m3d.samples.manifest import sha256_file
    cfg = load_config()
    try:
        spec = model_io.load_modelspec(cfg, dataset)
        drift = model_io.modelspec_drift(cfg, dataset)
        if drift:
            typer.echo(f"경고: modelspec.json 에 없는 필드 {len(drift)}개에 기본값 적용 — `m3d modelspec {dataset}` 재실행 권장: "
                       + ", ".join(drift[:6]) + (" …" if len(drift) > 6 else ""))
        b = Builder(spec)
        named = b.build(pilot=pilot)
        out_dir = model_io.model_dir(cfg, dataset, pilot=pilot)
        sections = model_sections.split(named, spec.coord.segment)
        sec_meta = b.export_sections(sections, out_dir)
        glb = out_dir / "AB1_P4P5.glb"
        b.export(model_sections.assemble(sections), glb)
        if pilot:
            shutil.copyfile(model_io.model_dir(cfg, dataset) / "modelspec.json", out_dir / "modelspec.json")
    except (RuntimeError, AssertionError) as exc:
        typer.echo(f"실패: {exc}")
        raise typer.Exit(code=1) from None
    r = model_selfcheck.run(named, b, pilot=pilot)
    (out_dir / "selfcheck.json").write_text(_json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    sec_results = {}
    for meta in sec_meta:
        rs = model_selfcheck.run(sections[meta["key"]], b, pilot=pilot, section=meta["code"])
        sec_results[meta["key"]] = rs
        meta["selfcheck"] = {"pass": rs["pass"], "fail": rs["fail"]}
        typer.echo(f"[{'PASS' if rs['fail'] == 0 else 'FAIL'}] 섹션 {meta['key']} ({meta['label']}) 메시 {meta['meshes']} "
                   f"pass={rs['pass']} fail={rs['fail']}")
    (out_dir / "selfcheck_sections.json").write_text(_json.dumps(sec_results, ensure_ascii=False, indent=2), encoding="utf-8")
    for c in r["checks"]:
        tag = "PASS" if c["ok"] else ("SKIP" if c["ok"] is None else "FAIL")
        typer.echo(f"[{tag}] {c['label']} — {c['detail']}")
    try:
        git_sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=cfg.repo_root,
                                 check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        git_sha = None
    model_io.write_build_json(out_dir, {
        "kind": "pilot" if pilot else "full", "segment": spec.coord.segment,
        "assembled": {"file": "AB1_P4P5.glb", "meshes": r["meshes"], "triangles": r["triangles"],
                      "bytes": glb.stat().st_size, "sha256": sha256_file(glb)},
        "sections": sec_meta, "selfcheck": {"pass": r["pass"], "fail": r["fail"], "skipped": r["skipped"]},
        "git_sha": git_sha})
    sec_fail = sum(rs["fail"] for rs in sec_results.values())
    typer.echo(f"섹션 {len(sec_meta)} / 메시 {r['meshes']}개 (수밀 {r['watertight']}) / 삼각형 {r['triangles']} / 출력: {out_dir}")
    typer.echo(f"selfcheck pass={r['pass']} fail={r['fail']} skipped={r['skipped']} meshes={r['meshes']} "
               f"sections={len(sec_meta)} section_fail={sec_fail}")
    raise typer.Exit(code=1 if (r["fail"] or sec_fail) else 0)
```

`render` 본문의 두 줄을 바꾼다:
```python
    out_dir = model_io.model_dir(cfg, dataset, pilot=pilot)
    glb = out_dir / "AB1_P4P5.glb"
```
(`measure`·`compare_model` 은 그대로 — 전체 디렉터리 전용.)

`README.md` "3D 모델 (M3)" 코드블록의 두 줄을 교체:
```
.\worker\.venv\Scripts\m3d.exe build ab1-p4p5 --pilot   # 시범: 본체·격벽만 → model/pilot/{sections/,AB1_P4P5.glb,selfcheck*.json,build.json} (승인 게이트)
.\worker\.venv\Scripts\m3d.exe build ab1-p4p5           # 전 부재 → model/{sections/P4P5/<그룹>.glb ×10, AB1_P4P5.glb(결합본), selfcheck.json, selfcheck_sections.json, build.json}
```

- [ ] **Step 10: 전체 테스트·실행 확인**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests -q`
Expected: 전건 PASS (기존 336 + 4 + 2)

Run(스키마 변경 → 재생성 먼저):
```
PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli modelspec ab1-p4p5
PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli build ab1-p4p5 --pilot
PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli build ab1-p4p5
ls data/derived/ab1-p4p5/model/sections/P4P5 data/derived/ab1-p4p5/model/pilot/sections/P4P5
```
Expected: `spec_sources … default=95`; 시범 `sections=2 section_fail=0`; 전체 `[PASS] 섹션 P4P5/BOX … P4P5/BRG` 10줄, `selfcheck pass=24 fail=0 skipped=0 meshes=515 sections=10 section_fail=0`, 드리프트 경고 없음. 옛 `AB1_P4P5_pilot.glb`·`selfcheck_pilot.json` 은 `rm` 으로 정리.

- [ ] **Step 11: 커밋**

```bash
git add worker/src/m3d/model/sections.py worker/src/m3d/model/spec.py worker/src/m3d/model/selfcheck.py worker/src/m3d/model/builder.py worker/src/m3d/model/io.py worker/src/m3d/cli.py worker/tests/test_model_sections.py worker/tests/test_model_builder.py README.md
git commit -m "feat(model): 섹션 분할·결합(구간/부재그룹) + 그룹 태그 self-check + model/pilot 디렉터리" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: 렌더 뷰 계약 `renders/views.json`

**Files:**
- Modify: `worker/src/m3d/model/render.py` (`render` 에 `frame_out=`, `view_contract`, `run_render` 가 views.json 기록), `worker/tests/test_model_render.py`

**Interfaces:**
- Consumes: `render(V, F, C, eye, up, out, title, ...)`, `run_render(glb, out_dir, spec, *, pilot)`.
- Produces: `render(..., frame_out: dict | None = None)` — 주어지면 `{"eye","up","right","xlim","ylim"}` 을 채움(단위 벡터 list, m);
  `view_contract(frame, center) -> {"origin": [x,y,z], "u_axis": [...], "v_axis": [...], "normal": [...], "extent": [w,h]}` (KB §7: P = origin + u·extent[0]·u_axis + v·extent[1]·v_axis);
  `run_render` 가 `out_dir/views.json` = `{"<파일명 stem>": {"file": "<stem>.png", "title": str, **contract}}` 를 쓰고 반환 목록에 그 경로를 포함(시범 2+1, 전체 4+1).

- [ ] **Step 1: 실패 테스트**

`worker/tests/test_model_render.py` 끝에 추가:
```python


def test_view_contract_roundtrips_bbox_corners(tmp_path):
    """뷰 계약: 장면 bbox 모서리가 (u,v)∈[0,1] 로 들어오고 origin 이 좌하단 한계와 일치한다."""
    a = box_prism(-1, -2, -3, 1, 0, 4)
    nodes = [("A", a, np.array([0, 150, 168, 255.0]))]
    V, F, C = R.to_tris(nodes)
    frame = {}
    R.render(V, F, C, (0.55, -1.0, 0.4), R.Y_UP, tmp_path / "v.png", "", size=(3, 3), dpi=40, frame_out=frame)
    assert set(frame) == {"eye", "up", "right", "xlim", "ylim"}
    c = R.view_contract(frame, center=V.mean(axis=0))
    o, u, v, n = (np.asarray(c[k]) for k in ("origin", "u_axis", "v_axis", "normal"))
    assert abs(np.dot(u, v)) < 1e-9 and abs(np.linalg.norm(n) - 1) < 1e-9
    for corner in [V.min(axis=0), V.max(axis=0), [V[:, 0].min(), V[:, 1].max(), V[:, 2].min()]]:
        d = np.asarray(corner, float) - o
        uu, vv = np.dot(d, u) / c["extent"][0], np.dot(d, v) / c["extent"][1]
        assert 0.0 <= uu <= 1.0 and 0.0 <= vv <= 1.0, (uu, vv)
    assert abs(np.dot(o, np.asarray(frame["right"])) - frame["xlim"][0]) < 1e-9


def test_run_render_pilot_writes_views_json(tmp_path):
    import json
    from m3d.model.builder import Builder
    from m3d.model.spec import ModelSpec
    spec = ModelSpec()
    b = Builder(spec)
    glb = tmp_path / "p.glb"
    b.export(b.build(pilot=True), glb)
    paths = R.run_render(glb, tmp_path / "renders", spec, pilot=True)
    assert [p.name for p in paths] == ["side_context.png", "front_section.png", "views.json"]
    views = json.loads((tmp_path / "renders" / "views.json").read_text(encoding="utf-8"))
    assert set(views) == {"side_context", "front_section"}
    assert views["front_section"]["file"] == "front_section.png" and len(views["front_section"]["extent"]) == 2
```

- [ ] **Step 2: 실패 확인**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_model_render.py -q`
Expected: FAIL — `TypeError: render() got an unexpected keyword argument 'frame_out'`

- [ ] **Step 3: render.py 수정**

`render()` 서명과 끝부분:
```python
def render(V, F, C, eye, up, out: Path, title, size=(12, 7), dpi=140, edge_alpha=0.18, extra=None, frame_out=None):
    ...(기존 본문 그대로: eye/right/upv 계산 → PolyCollection → extra → set_xlim/ylim → aspect/axis/title)...
    if frame_out is not None:
        frame_out.update({"eye": [float(v) for v in eye], "up": [float(v) for v in upv], "right": [float(v) for v in right],
                          "xlim": [float(v) for v in ax.get_xlim()], "ylim": [float(v) for v in ax.get_ylim()]})
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out), dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def view_contract(frame: dict, center) -> dict:
    """정사영 뷰 계약(KB §7) — origin 은 화면 좌하단 한계점을 장면 중심 깊이의 뷰 평면에 놓은 월드점."""
    right, upv, eye = (np.asarray(frame[k], float) for k in ("right", "up", "eye"))
    depth = float(np.dot(np.asarray(center, float), eye))
    x0, x1 = frame["xlim"]
    y0, y1 = frame["ylim"]
    origin = right * x0 + upv * y0 + eye * depth
    return {"origin": [float(v) for v in origin], "u_axis": [float(v) for v in right], "v_axis": [float(v) for v in upv],
            "normal": [float(v) for v in eye], "extent": [float(x1 - x0), float(y1 - y0)]}
```
`run_render()`: 각 `render(...)` 호출 직전에 `fr = {}` 를 만들고 `frame_out=fr` 를 넘긴 뒤 `views[stem] = {"file": stem + ".png", "title": <같은 제목 문자열>, **view_contract(fr, V.mean(axis=0))}` 를 모은다(4곳 동일 패턴; 절편 렌더는 그 절편의 V). 마지막에 공통 헬퍼로 기록:
```python
def _write_views(out_dir: Path, views: dict, written: list[Path]) -> list[Path]:
    vpath = out_dir / "views.json"
    vpath.write_text(json.dumps(views, ensure_ascii=False, indent=2), encoding="utf-8")
    written.append(vpath)
    return written
```
pilot 조기 return 은 `return _write_views(out_dir, views, written)`, 함수 끝도 동일. 모듈 상단에 `import json`.

- [ ] **Step 4: 통과 확인 + 실행**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_model_render.py -q` → PASS 4건
Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli render ab1-p4p5 && PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli render ab1-p4p5 --pilot`
Expected: `renders=5` / `renders=3`; `model/renders/views.json` 키 4개, `model/pilot/renders/views.json` 키 2개. 렌더는 M3 과 동일해야 하므로 `bottom_iso.png` 1장 Read 로 육안 재확인.

- [ ] **Step 5: 커밋**

```bash
git add worker/src/m3d/model/render.py worker/tests/test_model_render.py
git commit -m "feat(model): 렌더 뷰 계약 renders/views.json (origin·u/v 축·extent)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: 마이그레이션 0005 (builds·build_sections·approvals·버킷 models) + db.TABLES + 타입

**Files:**
- Create: `supabase/migrations/0005_builds.sql`, `worker/tests/test_migration_0005.py`, `worker/tests/test_db_tables.py`
- Modify: `worker/src/m3d/db.py` (`TABLES`), `contracts/db.types.ts`

**Interfaces:**
- Produces: 표 `builds(id, project_id, version, kind, segment, content_sha256, glb_path, files jsonb, stats jsonb, status, git_sha, created_at)`, `build_sections(id, build_id, section_key, code, label, glb_path, bytes, sha256, meshes, triangles, selfcheck jsonb, status)`, `approvals(id, project_id, build_id, section_id?, user_id, verdict, note, created_at)`; 트리거 `apply_approval()`; 버킷 `models`; `db.TABLES` 끝에 `"builds", "build_sections", "approvals"`; TS `Database.public.Tables.{builds, build_sections, approvals}` + 보조 타입 `BuildFiles`·`BuildStats`·`SectionSelfcheck`.

- [ ] **Step 1: 실패 테스트**

`worker/tests/test_migration_0005.py`:
```python
"""0005_builds — 빌드·섹션·승인 표, RLS, 트리거, Storage 버킷이 회귀로 사라지지 않게 고정한다."""

import re

import pytest

from m3d.config import REPO_ROOT
from m3d.db import discover_migrations


@pytest.fixture
def norm() -> str:
    path = REPO_ROOT / "supabase" / "migrations" / "0005_builds.sql"
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_discovered_after_0004():
    versions = [m.version for m in discover_migrations(REPO_ROOT / "supabase" / "migrations")]
    assert versions[:5] == ["0001_init", "0002_convert", "0003_readings", "0004_decisions", "0005_builds"]


def test_tables_columns_and_constraints(norm):
    assert "create table builds (" in norm and "unique (project_id, version)" in norm
    assert "kind text not null check (kind in ('pilot','full'))" in norm
    assert "status text not null default '대기' check (status in ('대기','승인','반려'))" in norm
    assert "create table build_sections (" in norm and "unique (build_id, section_key)" in norm
    assert "references builds(id) on delete cascade" in norm
    assert "create table approvals (" in norm
    assert "section_id uuid references build_sections(id) on delete cascade" in norm
    assert "user_id uuid not null default auth.uid()" in norm
    assert "verdict text not null check (verdict in ('승인','반려'))" in norm


def test_rls_read_all_and_own_insert_only(norm):
    for t in ("builds", "build_sections", "approvals"):
        assert f"alter table {t} enable row level security" in norm
        assert f'create policy "authenticated read" on {t} for select to authenticated using (true)' in norm
    assert "for insert to authenticated with check (user_id = auth.uid())" in norm
    assert norm.count("for insert") == 1 and "for update" not in norm and "for delete" not in norm
    assert "to anon" not in norm


def test_trigger_applies_status(norm):
    assert "create function apply_approval() returns trigger" in norm and "security definer" in norm
    assert "if new.section_id is null then update builds set status = new.verdict where id = new.build_id;" in norm
    assert "else update build_sections set status = new.verdict where id = new.section_id;" in norm
    assert "create trigger approvals_apply after insert on approvals" in norm


def test_private_bucket_models(norm):
    assert "insert into storage.buckets (id, name, public) values ('models', 'models', false)" in norm
    assert "on storage.objects for select to authenticated using (bucket_id = 'models')" in norm
```

`worker/tests/test_db_tables.py`:
```python
"""db.TABLES — db check 가 세는 표 목록에 M4 표가 들어간다."""

from m3d.db import TABLES


def test_tables_include_m4_tables_in_order():
    assert TABLES[-3:] == ("builds", "build_sections", "approvals")
    assert len(TABLES) == len(set(TABLES)) == 10
```

- [ ] **Step 2: 실패 확인**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_migration_0005.py worker/tests/test_db_tables.py -q`
Expected: FAIL — 파일 없음 / `TABLES[-3:]` 불일치

- [ ] **Step 3: 마이그레이션·TABLES·타입 작성**

`supabase/migrations/0005_builds.sql` (줄끝 LF):
```sql
-- 0005_builds — 빌드 버전·섹션·승인 이력 + Storage 버킷 models (M4 설계서 §4)
-- approvals 는 추가 전용 이력이다(decisions 패턴): 최신 행이 현재 상태, 트리거가 status 를 갱신한다.

create table builds (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null references projects(id) on delete cascade,
  version        int  not null,
  kind           text not null check (kind in ('pilot','full')),
  segment        text not null,
  content_sha256 text not null,
  glb_path       text not null,
  files          jsonb not null,
  stats          jsonb not null,
  status         text not null default '대기' check (status in ('대기','승인','반려')),
  git_sha        text,
  created_at     timestamptz not null default now(),
  unique (project_id, version)
);
create table build_sections (
  id          uuid primary key default gen_random_uuid(),
  build_id    uuid not null references builds(id) on delete cascade,
  section_key text not null,
  code        text not null,
  label       text not null,
  glb_path    text not null,
  bytes       int  not null,
  sha256      text not null,
  meshes      int  not null,
  triangles   int  not null,
  selfcheck   jsonb not null,
  status      text not null default '대기' check (status in ('대기','승인','반려')),
  unique (build_id, section_key)
);
create table approvals (
  id          uuid primary key default gen_random_uuid(),
  project_id  uuid not null references projects(id) on delete cascade,
  build_id    uuid not null references builds(id) on delete cascade,
  section_id  uuid references build_sections(id) on delete cascade,
  user_id     uuid not null default auth.uid(),
  verdict     text not null check (verdict in ('승인','반려')),
  note        text not null default '',
  created_at  timestamptz not null default now()
);
create index on approvals (build_id, created_at desc);

alter table builds         enable row level security;
alter table build_sections enable row level security;
alter table approvals      enable row level security;
create policy "authenticated read"   on builds         for select to authenticated using (true);
create policy "authenticated read"   on build_sections for select to authenticated using (true);
create policy "authenticated read"   on approvals      for select to authenticated using (true);
create policy "authenticated insert" on approvals      for insert to authenticated
  with check (user_id = auth.uid());

-- 삽입 트리거: 섹션 승인이면 build_sections.status, 결합본 승인이면 builds.status
-- (security definer — authenticated 에는 두 표의 update 정책이 없다)
create function apply_approval() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.section_id is null then
    update builds set status = new.verdict where id = new.build_id;
  else
    update build_sections set status = new.verdict where id = new.section_id;
  end if;
  return new;
end $$;
create trigger approvals_apply after insert on approvals
  for each row execute function apply_approval();

-- Storage: 비공개 버킷 + 로그인 사용자 읽기(서명 URL). 업로드는 service key(CLI)만.
insert into storage.buckets (id, name, public) values ('models', 'models', false)
  on conflict (id) do nothing;
create policy "authenticated read models" on storage.objects
  for select to authenticated using (bucket_id = 'models');
```

`worker/src/m3d/db.py`:
```python
TABLES = ("projects", "sheets", "sheet_pages", "assets", "readings", "ambiguities", "decisions",
          "builds", "build_sections", "approvals")
```

`contracts/db.types.ts` — 파일 상단(`export interface Database` 앞)에 보조 타입:
```ts
export interface BuildFiles { renders: string[]; json: string[]; views: string | null }
export interface BuildStats {
  meshes: number; triangles: number;
  selfcheck: { pass: number; fail: number; skipped: number };
  measure: { pass: number; fail: number; info: number } | null;
  compare: { match: number; mismatch: number; na: number } | null;
}
export interface SectionSelfcheck {
  pass: number; fail: number;
  checks: Array<{ label: string; ok: boolean | null; detail: string; group: string }>;
}
```
`decisions` 블록 뒤에 세 표:
```ts
      builds: {
        Row: {
          id: string; project_id: string; version: number; kind: 'pilot' | 'full'; segment: string;
          content_sha256: string; glb_path: string; files: BuildFiles; stats: BuildStats;
          status: '대기' | '승인' | '반려'; git_sha: string | null; created_at: string;
        };
        Insert: never;
        Update: never;
      };
      build_sections: {
        Row: {
          id: string; build_id: string; section_key: string; code: string; label: string; glb_path: string;
          bytes: number; sha256: string; meshes: number; triangles: number; selfcheck: SectionSelfcheck;
          status: '대기' | '승인' | '반려';
        };
        Insert: never;
        Update: never;
      };
      approvals: {
        Row: {
          id: string; project_id: string; build_id: string; section_id: string | null; user_id: string;
          verdict: '승인' | '반려'; note: string; created_at: string;
        };
        Insert: {
          id?: string; project_id: string; build_id: string; section_id?: string | null; user_id?: string;
          verdict: '승인' | '반려'; note?: string; created_at?: string;
        };
        Update: never;
      };
```

- [ ] **Step 4: 테스트·적용·확인**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests -q` → 전건 PASS
Run: `npm --prefix web run typecheck` → 오류 0
Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli db apply && PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli db check | head -14`
Expected: `0005_builds` 적용 1건; 표 목록에 `builds 0 on`, `build_sections 0 on`, `approvals 0 on`.

- [ ] **Step 5: 커밋**

```bash
git add supabase/migrations/0005_builds.sql worker/src/m3d/db.py contracts/db.types.ts worker/tests/test_migration_0005.py worker/tests/test_db_tables.py
git commit -m "feat(db): 0005 builds·build_sections·approvals + 트리거 + 버킷 models" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: `m3d publish-model` — 섹션·결합본·렌더·JSON 업로드 + builds·build_sections 행

**Files:**
- Create: `worker/src/m3d/model/publish.py`, `worker/tests/test_model_publish.py`
- Modify: `worker/src/m3d/cli.py` (명령 추가), `README.md` (명령 1줄)

**Interfaces:**
- Consumes: `model_io.model_dir(cfg, ds, *, pilot)`, `reading.publish._upload(url, headers, data) -> (status, body)`, `samples.manifest.sha256_file(path)`, `build.json`·`selfcheck.json`·`selfcheck_sections.json`·`measure.json`·`compare.json` 형식(Task 1·M3).
- Produces: `publish.BUCKET = "models"`, `publish.REQUIRED`, `publish.OPTIONAL`, `publish.object_key(slug, version, rel) -> str`, `publish.collect_files(out_dir) -> list[str]`(posix 상대경로, 결정적 순서), `publish.content_sha256(out_dir) -> str`, `publish.build_stats(out_dir) -> dict`(TS `BuildStats` 형식),
  `publish.run_publish_model(cfg, dataset, *, pilot=False, force=False) -> {"skipped": bool, "version": int|None, "files": int, "uploaded": int, "failures": list[tuple[str, str]], "build_id": str|None}`.
  DB 에 저장하는 경로는 **버킷 접두 없는 오브젝트 키**(`ab1-p4p5/b1/...`) — 웹 `createSignedUrls` 가 키만 받는다(설계서 §4 의 `models/...` 표기는 이 규칙으로 확정).
  CLI `m3d publish-model <ds> [--pilot] [--force]` → 콘솔 마지막 줄 `publish-model version=N files=M uploaded=K skipped=true|false`, 실패 있으면 exit 1.

- [ ] **Step 1: 실패 테스트**

`worker/tests/test_model_publish.py`:
```python
"""m3d publish-model — 산출물 수집·해시·업로드·builds/build_sections 행 (M4 §5). 실호출 없음(가짜 업로드·DB)."""

import dataclasses
import json

import pytest
from typer.testing import CliRunner

from m3d.cli import app
from m3d.config import load_config
from m3d.model import publish as P

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class FakeDb:
    def __init__(self, latest=None):
        self.latest = latest            # (version, content_sha256) | None
        self.sql = []
        self.committed = False


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self._rows = []

    def execute(self, sql, params=None):
        s = " ".join(sql.split())
        self.db.sql.append((s, params))
        self._rows = []
        if s.startswith("select id from projects"):
            self._rows = [("proj-1",)]
        elif s.startswith("select version, content_sha256 from builds"):
            self._rows = [self.db.latest] if self.db.latest else []
        elif s.startswith("insert into builds"):
            self._rows = [("build-1",)]

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, db):
        self.db = db

    def cursor(self):
        return FakeCursor(self.db)

    def commit(self):
        self.db.committed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://fake/none")
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-test-key")
    cfg = load_config(env_file=tmp_path / "absent.env")
    return dataclasses.replace(cfg, repo_root=tmp_path)


def _model_dir(cfg, *, with_measure=True):
    d = cfg.derived_dir / "ds" / "model"
    (d / "sections" / "P4P5").mkdir(parents=True)
    (d / "renders").mkdir()
    (d / "sections" / "P4P5" / "BOX.glb").write_bytes(b"glTF-box")
    (d / "sections" / "P4P5" / "DIA.glb").write_bytes(b"glTF-dia")
    (d / "AB1_P4P5.glb").write_bytes(b"glTF-all")
    build = {"kind": "full", "segment": "P4P5", "git_sha": "abc",
             "assembled": {"file": "AB1_P4P5.glb", "meshes": 30, "triangles": 100, "bytes": 8, "sha256": "x"},
             "sections": [
                 {"key": "P4P5/BOX", "code": "BOX", "label": "본체", "file": "sections/P4P5/BOX.glb", "meshes": 4,
                  "triangles": 40, "bytes": 8, "sha256": "b", "selfcheck": {"pass": 9, "fail": 0}},
                 {"key": "P4P5/DIA", "code": "DIA", "label": "격벽", "file": "sections/P4P5/DIA.glb", "meshes": 26,
                  "triangles": 60, "bytes": 8, "sha256": "d", "selfcheck": {"pass": 5, "fail": 0}}],
             "selfcheck": {"pass": 15, "fail": 0, "skipped": 5}}
    (d / "build.json").write_text(json.dumps(build), encoding="utf-8")
    (d / "selfcheck.json").write_text(json.dumps({"pass": 15, "fail": 0, "skipped": 5, "checks": []}), encoding="utf-8")
    (d / "selfcheck_sections.json").write_text(json.dumps({
        "P4P5/BOX": {"pass": 9, "fail": 0, "checks": [{"label": "수밀 전건", "ok": True, "detail": "4/4", "group": "COMMON"}]},
        "P4P5/DIA": {"pass": 5, "fail": 0, "checks": []}}), encoding="utf-8")
    (d / "modelspec.json").write_text('{"spec": {}}', encoding="utf-8")
    (d / "renders" / "side_context.png").write_bytes(PNG)
    (d / "renders" / "views.json").write_text("{}", encoding="utf-8")
    if with_measure:
        (d / "measure.json").write_text(json.dumps({"집계": {"PASS": 47, "FAIL": 0, "INFO": 2}}), encoding="utf-8")
        (d / "compare.json").write_text(json.dumps({"summary": {"match": 836, "mismatch": 0, "na": 0}}), encoding="utf-8")
    return d


def _patch(monkeypatch, db, fail_rel=None):
    calls = []

    def fake_upload(url, headers, data):
        calls.append((url, headers, data))
        return (500, "boom") if fail_rel and url.endswith(fail_rel) else (200, "{}")
    monkeypatch.setattr(P.psycopg, "connect", lambda *a, **k: FakeConn(db))
    monkeypatch.setattr(P, "_upload", fake_upload)
    return calls


def test_object_key_matches_web_rule():
    assert P.object_key("ab1-p4p5", 3, "sections/P4P5/DIA.glb") == "ab1-p4p5/b3/sections/P4P5/DIA.glb"


def test_collect_files_required_sections_renders_optional(cfg):
    d = _model_dir(cfg)
    files = P.collect_files(d)
    assert files[:6] == list(P.REQUIRED)
    assert "sections/P4P5/BOX.glb" in files and "sections/P4P5/DIA.glb" in files
    assert "renders/side_context.png" in files and files[-2:] == ["measure.json", "compare.json"]
    assert len(files) == 11
    (d / "selfcheck_sections.json").unlink()
    with pytest.raises(RuntimeError, match="selfcheck_sections.json"):
        P.collect_files(d)


def test_build_stats_folds_summaries(cfg):
    d = _model_dir(cfg)
    st = P.build_stats(d)
    assert st == {"meshes": 30, "triangles": 100, "selfcheck": {"pass": 15, "fail": 0, "skipped": 5},
                  "measure": {"pass": 47, "fail": 0, "info": 2}, "compare": {"match": 836, "mismatch": 0, "na": 0}}
    assert P.build_stats(_model_dir(dataclasses.replace(cfg, repo_root=cfg.repo_root / "b"), with_measure=False))["measure"] is None


def test_publish_uploads_all_files_and_inserts_rows(cfg, monkeypatch):
    d = _model_dir(cfg)
    db = FakeDb(latest=None)
    calls = _patch(monkeypatch, db)
    r = P.run_publish_model(cfg, "ds")
    assert r == {"skipped": False, "version": 1, "files": 11, "uploaded": 11, "failures": [], "build_id": "build-1"}
    urls = [u for (u, _h, _d) in calls]
    assert all(u.startswith("https://fake.supabase.co/storage/v1/object/models/ds/b1/") for u in urls)
    types = {u.rsplit(".", 1)[1]: h["Content-Type"] for (u, h, _d) in calls}
    assert types == {"glb": "model/gltf-binary", "png": "image/png", "json": "application/json"}
    assert all(h["x-upsert"] == "true" for (_u, h, _d) in calls)
    inserts = [s for s, _p in db.sql if s.startswith("insert into")]
    assert len(inserts) == 1 + 2 and inserts[0].startswith("insert into builds")
    b_params = [p for s, p in db.sql if s.startswith("insert into builds")][0]
    assert b_params[:6] == ("proj-1", 1, "full", "P4P5", P.content_sha256(d), "ds/b1/AB1_P4P5.glb")
    s_params = [p for s, p in db.sql if s.startswith("insert into build_sections")]
    assert s_params[0][:5] == ("build-1", "P4P5/BOX", "BOX", "본체", "ds/b1/sections/P4P5/BOX.glb")
    assert db.committed is True
    assert "service-test-key" not in json.dumps(r)


def test_publish_skips_same_content_unless_force(cfg, monkeypatch):
    d = _model_dir(cfg)
    db = FakeDb(latest=(2, P.content_sha256(d)))
    calls = _patch(monkeypatch, db)
    r = P.run_publish_model(cfg, "ds")
    assert r["skipped"] is True and r["version"] == 2 and r["uploaded"] == 0 and calls == []
    assert not any(s.startswith("insert") for s, _p in db.sql)
    r2 = P.run_publish_model(cfg, "ds", force=True)
    assert r2["skipped"] is False and r2["version"] == 3 and r2["uploaded"] == 11
    assert calls[0][0].startswith("https://fake.supabase.co/storage/v1/object/models/ds/b3/")


def test_upload_failure_blocks_db_rows(cfg, monkeypatch):
    _model_dir(cfg)
    db = FakeDb(latest=None)
    _patch(monkeypatch, db, fail_rel="sections/P4P5/DIA.glb")
    r = P.run_publish_model(cfg, "ds")
    assert r["version"] is None and r["build_id"] is None and r["uploaded"] == 10
    assert r["failures"] == [("sections/P4P5/DIA.glb", "HTTP 500: boom")]
    assert not any(s.startswith("insert") for s, _p in db.sql) and db.committed is False


def test_cli_prints_summary_and_exit_code(cfg, monkeypatch):
    monkeypatch.setattr(P, "run_publish_model",
                        lambda cfg, ds, *, pilot=False, force=False:
                        {"skipped": False, "version": 4, "files": 11, "uploaded": 11, "failures": [], "build_id": "b"})
    res = CliRunner().invoke(app, ["publish-model", "ds"])
    assert res.exit_code == 0 and "publish-model version=4 files=11 uploaded=11 skipped=false" in res.output
    monkeypatch.setattr(P, "run_publish_model",
                        lambda cfg, ds, *, pilot=False, force=False:
                        {"skipped": False, "version": None, "files": 11, "uploaded": 10,
                         "failures": [("renders/views.json", "HTTP 500: boom")], "build_id": None})
    res = CliRunner().invoke(app, ["publish-model", "ds", "--pilot"])
    assert res.exit_code == 1 and "실패: renders/views.json — HTTP 500: boom" in res.output
```

- [ ] **Step 2: 실패 확인**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests/test_model_publish.py -q`
Expected: FAIL — `ModuleNotFoundError: m3d.model.publish`

- [ ] **Step 3: publish.py 구현**

`worker/src/m3d/model/publish.py`:
```python
"""m3d publish-model — 섹션 GLB·결합본·렌더·검증 JSON 을 비공개 버킷 `models` 에 올리고 builds·build_sections 행을 만든다 (M4 설계서 §5).

업로드는 service key(RLS 우회)로만 하며 값은 어떤 출력에도 남기지 않는다. HTTP 는 reading.publish._upload(표준 라이브러리) 재사용.
버전 규칙(D7): content_sha256 = sha256(결합본 sha256 ‖ modelspec sha256). 최신 빌드와 같으면 skip(--force 예외).
업로드가 하나라도 실패하면 DB 행을 만들지 않는다. DB 에 저장하는 경로는 버킷 접두 없는 오브젝트 키다(웹 createSignedUrls 규칙).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from m3d.config import Config
from m3d.model import io as model_io
from m3d.reading.publish import _upload
from m3d.samples.manifest import sha256_file

BUCKET = "models"
REQUIRED = ("build.json", "AB1_P4P5.glb", "selfcheck.json", "selfcheck_sections.json", "modelspec.json", "renders/views.json")
OPTIONAL = ("measure.json", "compare.json")
CONTENT_TYPES = {".glb": "model/gltf-binary", ".png": "image/png", ".json": "application/json"}


def object_key(slug: str, version: int, rel: str) -> str:
    """버킷 안 오브젝트 키 — 웹(lib/models.ts modelObjectKey)과 같은 규칙."""
    return f"{slug}/b{version}/{rel}"


def _load(out_dir: Path, rel: str) -> dict:
    return json.loads((Path(out_dir) / rel).read_text(encoding="utf-8"))


def collect_files(out_dir: Path) -> list[str]:
    """필수 6 + 섹션 GLB(build.json 순서) + renders/*.png(이름순) + 선택 JSON — posix 상대경로."""
    out_dir = Path(out_dir)
    missing = [r for r in REQUIRED if not (out_dir / r).is_file()]
    if missing:
        raise RuntimeError("필수 산출물 없음: " + ", ".join(missing) + " — `m3d build`·`m3d render` 먼저")
    build = _load(out_dir, "build.json")
    files = list(REQUIRED) + [s["file"] for s in build["sections"]]
    files += sorted(p.relative_to(out_dir).as_posix() for p in (out_dir / "renders").glob("*.png"))
    files += [r for r in OPTIONAL if (out_dir / r).is_file()]
    absent = [rel for rel in files if not (out_dir / rel).is_file()]
    if absent:
        raise RuntimeError("산출물 없음: " + ", ".join(absent))
    return files


def content_sha256(out_dir: Path) -> str:
    out_dir = Path(out_dir)
    return hashlib.sha256((sha256_file(out_dir / "AB1_P4P5.glb") + sha256_file(out_dir / "modelspec.json")).encode("ascii")).hexdigest()


def build_stats(out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    build, sc = _load(out_dir, "build.json"), _load(out_dir, "selfcheck.json")
    stats = {"meshes": build["assembled"]["meshes"], "triangles": build["assembled"]["triangles"],
             "selfcheck": {"pass": sc["pass"], "fail": sc["fail"], "skipped": sc["skipped"]}, "measure": None, "compare": None}
    if (out_dir / "measure.json").is_file():
        agg = _load(out_dir, "measure.json")["집계"]
        stats["measure"] = {"pass": agg["PASS"], "fail": agg["FAIL"], "info": agg["INFO"]}
    if (out_dir / "compare.json").is_file():
        stats["compare"] = dict(_load(out_dir, "compare.json")["summary"])
    return stats


def run_publish_model(cfg: Config, dataset: str, *, pilot: bool = False, force: bool = False) -> dict:
    if not cfg.supabase_url or not cfg.supabase_service_key:
        raise RuntimeError("SUPABASE_URL·SUPABASE_SERVICE_KEY 미설정 — .env 를 확인하세요")
    out_dir = model_io.model_dir(cfg, dataset, pilot=pilot)
    files = collect_files(out_dir)
    build = _load(out_dir, "build.json")
    content = content_sha256(out_dir)
    base, key = cfg.supabase_url.rstrip("/"), cfg.supabase_service_key

    with psycopg.connect(cfg.require_db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute("select id from projects where slug = %s", (dataset,))
            row = cur.fetchone()
            if row is None:
                raise RuntimeError(f"프로젝트 '{dataset}' 없음 — seed 먼저")
            project_id = row[0]
            cur.execute("select version, content_sha256 from builds where project_id = %s order by version desc limit 1",
                        (project_id,))
            latest = cur.fetchone()
        if latest is not None and latest[1] == content and not force:
            return {"skipped": True, "version": latest[0], "files": len(files), "uploaded": 0, "failures": [], "build_id": None}
        version = (latest[0] + 1) if latest is not None else 1

        uploaded, failures = 0, []
        for rel in files:
            path = out_dir / rel
            status, body = _upload(
                f"{base}/storage/v1/object/{BUCKET}/{object_key(dataset, version, rel)}",
                {"Authorization": f"Bearer {key}", "apikey": key, "x-upsert": "true",
                 "Content-Type": CONTENT_TYPES.get(path.suffix, "application/octet-stream")},
                path.read_bytes())
            if 200 <= status < 300:
                uploaded += 1
            else:
                failures.append((rel, f"HTTP {status}: {body[:120]}"))
        if failures:
            return {"skipped": False, "version": None, "files": len(files), "uploaded": uploaded, "failures": failures, "build_id": None}

        keyed = {rel: object_key(dataset, version, rel) for rel in files}
        file_index = {"renders": [keyed[r] for r in files if r.startswith("renders/") and r.endswith(".png")],
                      "json": [keyed[r] for r in files if r.endswith(".json") and r != "renders/views.json"],
                      "views": keyed["renders/views.json"]}
        sec_checks = _load(out_dir, "selfcheck_sections.json")
        with conn.cursor() as cur:
            cur.execute("insert into builds (project_id, version, kind, segment, content_sha256, glb_path, files, stats, git_sha) "
                        "values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning id",
                        (project_id, version, build["kind"], build["segment"], content, keyed["AB1_P4P5.glb"],
                         Jsonb(file_index), Jsonb(build_stats(out_dir)), build.get("git_sha")))
            build_id = cur.fetchone()[0]
            for s in build["sections"]:
                rs = sec_checks.get(s["key"], {"pass": 0, "fail": 0, "checks": []})
                cur.execute("insert into build_sections (build_id, section_key, code, label, glb_path, bytes, sha256, meshes, triangles, selfcheck) "
                            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                            (build_id, s["key"], s["code"], s["label"], keyed[s["file"]], s["bytes"], s["sha256"],
                             s["meshes"], s["triangles"], Jsonb({"pass": rs["pass"], "fail": rs["fail"], "checks": rs.get("checks", [])})))
        conn.commit()
    return {"skipped": False, "version": version, "files": len(files), "uploaded": uploaded, "failures": [], "build_id": str(build_id)}
```

`worker/src/m3d/cli.py` — `compare_model` 뒤, `if __name__` 앞에:
```python
@app.command("publish-model")
def publish_model(
    dataset: str = typer.Argument(..., help="데이터셋 슬러그"),
    pilot: bool = typer.Option(False, "--pilot", help="model/pilot/ 산출물을 올린다"),
    force: bool = typer.Option(False, "--force", help="내용이 같아도 새 버전으로 재업로드"),
) -> None:
    """[10] 섹션 GLB·결합본·렌더·검증 JSON → Storage 버킷 models + builds·build_sections (M4 설계서 §5)."""
    from m3d.model import publish as model_publish
    cfg = load_config()
    try:
        r = model_publish.run_publish_model(cfg, dataset, pilot=pilot, force=force)
    except RuntimeError as exc:
        typer.echo(f"실패: {exc}")
        raise typer.Exit(code=1) from None
    for rel, reason in r["failures"]:
        typer.echo(f"실패: {rel} — {reason}")
    typer.echo(f"publish-model version={r['version']} files={r['files']} uploaded={r['uploaded']} skipped={str(r['skipped']).lower()}")
    raise typer.Exit(code=1 if r["failures"] else 0)
```

`README.md` 3D 모델 코드블록 마지막에:
```
.\worker\.venv\Scripts\m3d.exe publish-model ab1-p4p5   # 섹션·결합본·렌더·검증 JSON → 비공개 버킷 models + builds/build_sections (내용 같으면 skip, --force, --pilot)
```

- [ ] **Step 4: 테스트·실행**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests -q` → 전건 PASS
Run(실 DB·Storage, 시범 → 전체):
```
PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli publish-model ab1-p4p5 --pilot
PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli publish-model ab1-p4p5
PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli publish-model ab1-p4p5
PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli db check | grep -E "builds|build_sections|approvals"
```
Expected: `version=1 files=10 uploaded=10 skipped=false`(시범: 필수 6 + 섹션 2 + 렌더 2; measure/compare 없음), `version=2 files=21 uploaded=21 skipped=false`(전체: 6+10+4+1 정정 → 필수 6 + 섹션 10 + 렌더 4 + measure·compare 2 = 22), 세 번째 `version=2 … skipped=true`; `builds 2`, `build_sections 12`, `approvals 0`. (파일 수는 실행 출력으로 확정해 acceptance 에 기록.)

- [ ] **Step 5: 커밋**

```bash
git add worker/src/m3d/model/publish.py worker/src/m3d/cli.py worker/tests/test_model_publish.py README.md
git commit -m "feat(model): m3d publish-model — 섹션·결합본·렌더·JSON → 버킷 models + builds/build_sections" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: 웹 데이터 계층 + three.js 뷰어 최소(섹션 로드·트리·오빗) → 시범 게이트

**Files:**
- Create: `web/src/lib/models.ts`, `web/src/lib/models.test.ts`, `web/src/lib/viewer/math.ts`, `web/src/lib/viewer/math.test.ts`, `web/src/lib/viewer/scene.ts`, `web/src/routes/Model.tsx`
- Modify: `web/package.json`(의존성), `web/src/App.tsx`, `web/src/routes/Projects.tsx`

**Interfaces:**
- Consumes: `contracts/db.types.ts` 3표 타입(Task 3), `lib/questions.ts` 의 `ProjectRef`·`fetchProject`, `lib/supabase.ts` 의 `supabase`, `auth/AuthGate.tsx` 의 `useSession`.
- Produces (`lib/models.ts`): `BUCKET='models'`, `CODES`(워커와 같은 10개 순서), `modelObjectKey(slug, version, rel)`, `targetKey(sectionId|null)`(`'BUILD'` 또는 id), `latestApprovals(rows) -> Map<targetKey, ApprovalRow>`, `approvalPayload({projectId, buildId, sectionId, verdict, note}) -> ApprovalInsert`, `fetchBuilds(client, project) -> BuildRow[]`(version desc), `fetchSections(client, buildId) -> SectionRow[]`(CODES 순), `fetchApprovals(client, buildId) -> ApprovalRow[]`, `signedUrls(client, keys) -> {urls: Map<key, url>, failed: string[]}`, `submitApproval(client, payload) -> ApprovalRow`, `fetchJson<T>(url) -> T`.
- Produces (`lib/viewer/math.ts`): `zFromDistance(zP4, d)`, `distanceFromZ(zP4, z)`, `clipPlane(axis, value, keep) -> {normal, constant}`, `presetCamera(preset, box) -> {position, target}`.
- Produces (`lib/viewer/scene.ts`): `createViewer(canvas) -> Viewer` — `loadSection(key, url)`, `setVisible(key, on)`, `solo(key|null)`, `setClip(axis, {enabled, value, keep})`, `preset(p)`, `highlight(node|null)`, `onPick(cb)`, `bounds()`, `dispose()`.

- [ ] **Step 1: 의존성**

Run: `npm --prefix web install three@^0.184.0 && npm --prefix web install -D @types/three@^0.184.0`
Expected: `web/package.json` dependencies 에 `three`, devDependencies 에 `@types/three`.

- [ ] **Step 2: 실패 테스트 — 순수 함수**

`web/src/lib/models.test.ts`:
```ts
import { describe, expect, it } from 'vitest';
import { approvalPayload, CODES, latestApprovals, modelObjectKey, targetKey, type ApprovalRow } from './models';

const row = (over: Partial<ApprovalRow>): ApprovalRow => ({
  id: 'a', build_id: 'b', section_id: null, user_id: 'u', verdict: '승인', note: '', created_at: '2026-09-05T10:00:00+00:00', ...over,
});

describe('modelObjectKey', () => {
  it('워커 publish.object_key 와 같은 문자열', () => {
    expect(modelObjectKey('ab1-p4p5', 3, 'sections/P4P5/DIA.glb')).toBe('ab1-p4p5/b3/sections/P4P5/DIA.glb');
  });
  it('CODES 는 워커 sections.CODES 와 같은 순서', () => {
    expect(CODES).toEqual(['BOX', 'DIA', 'FRM', 'RIB', 'HST', 'WG', 'CS', 'SLAB', 'SP04', 'BRG']);
  });
});

describe('latestApprovals', () => {
  it('대상(섹션 id 또는 BUILD)별 created_at 최신 행, 입력 순서 무관', () => {
    const m = latestApprovals([
      row({ id: 'old', section_id: 's1', created_at: '2026-09-05T10:00:00+00:00' }),
      row({ id: 'new', section_id: 's1', verdict: '반려', created_at: '2026-09-05T11:00:00+00:00' }),
      row({ id: 'whole', section_id: null }),
    ]);
    expect(m.get('s1')?.id).toBe('new');
    expect(m.get(targetKey(null))?.id).toBe('whole');
    expect(m.size).toBe(2);
  });
});

describe('approvalPayload', () => {
  it('정상 페이로드 — 메모 trim, section_id null 허용', () => {
    expect(approvalPayload({ projectId: 'p', buildId: 'b', sectionId: null, verdict: '승인', note: ' ok ' }))
      .toEqual({ project_id: 'p', build_id: 'b', section_id: null, verdict: '승인', note: 'ok' });
  });
  it('verdict 범위 밖·메모 500자 초과는 RangeError', () => {
    expect(() => approvalPayload({ projectId: 'p', buildId: 'b', sectionId: 's', verdict: '보류' as never })).toThrow(RangeError);
    expect(() => approvalPayload({ projectId: 'p', buildId: 'b', sectionId: 's', verdict: '반려', note: 'x'.repeat(501) })).toThrow(RangeError);
  });
});
```

`web/src/lib/viewer/math.test.ts`:
```ts
import { describe, expect, it } from 'vitest';
import { clipPlane, distanceFromZ, presetCamera, zFromDistance } from './math';

const BOX = { min: [-7.85, 15.1, -525.7] as [number, number, number], max: [7.85, 21.9, -454.3] as [number, number, number] };

describe('z ↔ 받침선 거리', () => {
  it('왕복', () => {
    expect(zFromDistance(-525, 10)).toBe(-515);
    expect(distanceFromZ(-525, -490)).toBe(35);
  });
});

describe('clipPlane', () => {
  // three.js: normal·p + constant < 0 인 조각은 잘린다
  const vis = (pl: { normal: number[]; constant: number }, p: number[]) => pl.normal[0] * p[0] + pl.normal[1] * p[1] + pl.normal[2] * p[2] + pl.constant >= 0;
  it("z 'below' 는 값보다 작은 z 만 남긴다", () => {
    const pl = clipPlane('z', -500, 'below');
    expect(vis(pl, [0, 0, -510])).toBe(true);
    expect(vis(pl, [0, 0, -490])).toBe(false);
  });
  it("x 'above' 는 값보다 큰 x 만 남긴다", () => {
    const pl = clipPlane('x', 0, 'above');
    expect(vis(pl, [1, 0, 0])).toBe(true);
    expect(vis(pl, [-1, 0, 0])).toBe(false);
  });
});

describe('presetCamera', () => {
  it('측면은 +x 에서 중심을 보고, 아이소는 위·앞·옆 모두 양의 오프셋', () => {
    const c = [0, 18.5, -490];
    const side = presetCamera('side', BOX);
    expect(side.target).toEqual(c);
    expect(side.position[0]).toBeGreaterThan(BOX.max[0]);
    expect(side.position[1]).toBeCloseTo(c[1]);
    const iso = presetCamera('iso', BOX);
    expect(iso.position[0] > c[0] && iso.position[1] > c[1] && iso.position[2] > c[2]).toBe(true);
    const bottom = presetCamera('bottom', BOX);
    expect(bottom.position[1]).toBeLessThan(BOX.min[1]);
  });
});
```

- [ ] **Step 3: 실패 확인**

Run: `npm --prefix web test`
Expected: FAIL — 모듈 없음(`./models`, `./math`)

- [ ] **Step 4: models.ts·math.ts 구현**

`web/src/lib/models.ts`:
```ts
// 빌드·섹션·승인 데이터 접근 + 순수 함수 (M4 설계서 §6). 로그인 세션의 RLS 아래에서만 동작한다.
import type { SupabaseClient } from '@supabase/supabase-js';

import type { BuildFiles, BuildStats, Database, SectionSelfcheck } from '../../../contracts/db.types';
import type { ProjectRef } from './questions';

export type Client = SupabaseClient<Database>;
export type Status = '대기' | '승인' | '반려';
export type Verdict = '승인' | '반려';
export const BUCKET = 'models';
/** 워커 sections.CODES 와 같은 순서 — 섹션 트리 정렬 */
export const CODES = ['BOX', 'DIA', 'FRM', 'RIB', 'HST', 'WG', 'CS', 'SLAB', 'SP04', 'BRG'];
export const BUILD_TARGET = 'BUILD';

export interface BuildRow {
  id: string; version: number; kind: 'pilot' | 'full'; segment: string; glb_path: string;
  files: BuildFiles; stats: BuildStats; status: Status; git_sha: string | null; created_at: string;
}
export interface SectionRow {
  id: string; section_key: string; code: string; label: string; glb_path: string; bytes: number;
  meshes: number; triangles: number; selfcheck: SectionSelfcheck; status: Status;
}
export interface ApprovalRow {
  id: string; build_id: string; section_id: string | null; user_id: string; verdict: Verdict; note: string; created_at: string;
}
export interface ApprovalInsert {
  project_id: string; build_id: string; section_id: string | null; verdict: Verdict; note: string;
}

export function modelObjectKey(slug: string, version: number, rel: string): string {
  // worker model/publish.object_key 와 같은 규칙
  return `${slug}/b${version}/${rel}`;
}

export function targetKey(sectionId: string | null): string {
  return sectionId ?? BUILD_TARGET;
}

/** 대상(섹션 또는 결합본)별 최신 승인 — created_at 최대. 입력 정렬에 의존하지 않는다. */
export function latestApprovals(rows: ApprovalRow[]): Map<string, ApprovalRow> {
  const latest = new Map<string, ApprovalRow>();
  for (const r of rows) {
    const k = targetKey(r.section_id);
    const cur = latest.get(k);
    if (!cur || r.created_at > cur.created_at) latest.set(k, r);
  }
  return latest;
}

export function approvalPayload(p: {
  projectId: string; buildId: string; sectionId: string | null; verdict: Verdict; note?: string;
}): ApprovalInsert {
  if (p.verdict !== '승인' && p.verdict !== '반려') throw new RangeError(`verdict 범위 밖: ${String(p.verdict)}`);
  const note = (p.note ?? '').trim();
  if (note.length > 500) throw new RangeError('메모는 500자 이내');
  return { project_id: p.projectId, build_id: p.buildId, section_id: p.sectionId, verdict: p.verdict, note };
}

const BUILD_COLS = 'id,version,kind,segment,glb_path,files,stats,status,git_sha,created_at';
const SECTION_COLS = 'id,section_key,code,label,glb_path,bytes,meshes,triangles,selfcheck,status';
const APPROVAL_COLS = 'id,build_id,section_id,user_id,verdict,note,created_at';

export async function fetchBuilds(client: Client, project: ProjectRef): Promise<BuildRow[]> {
  const { data, error } = await client.from('builds').select(BUILD_COLS).eq('project_id', project.id).order('version', { ascending: false });
  if (error) throw new Error(error.message);
  return (data ?? []) as unknown as BuildRow[];
}

export async function fetchSections(client: Client, buildId: string): Promise<SectionRow[]> {
  const { data, error } = await client.from('build_sections').select(SECTION_COLS).eq('build_id', buildId);
  if (error) throw new Error(error.message);
  const rows = (data ?? []) as unknown as SectionRow[];
  return rows.sort((a, b) => CODES.indexOf(a.code) - CODES.indexOf(b.code));
}

export async function fetchApprovals(client: Client, buildId: string): Promise<ApprovalRow[]> {
  const { data, error } = await client.from('approvals').select(APPROVAL_COLS).eq('build_id', buildId).order('created_at', { ascending: false });
  if (error) throw new Error(error.message);
  return (data ?? []) as unknown as ApprovalRow[];
}

/** 서명 URL 일괄 발급 — 실패한 키는 failed 로 돌려주고 나머지는 계속(설계서 §6 오류 처리). */
export async function signedUrls(client: Client, keys: string[]): Promise<{ urls: Map<string, string>; failed: string[] }> {
  if (keys.length === 0) return { urls: new Map(), failed: [] };
  const { data, error } = await client.storage.from(BUCKET).createSignedUrls(keys, 3600);
  if (error || !data) throw new Error(error?.message ?? '서명 URL 실패');
  const urls = new Map<string, string>();
  const failed: string[] = [];
  data.forEach((d, i) => {
    if (d.signedUrl && !d.error) urls.set(d.path ?? keys[i], d.signedUrl);
    else failed.push(d.path ?? keys[i]);
  });
  return { urls, failed };
}

export async function submitApproval(client: Client, payload: ApprovalInsert): Promise<ApprovalRow> {
  const { data, error } = await client
    .from('approvals')
    // 수기 작성 타입에는 Relationships 가 없어 supabase-js 가 Insert 를 never 로 접는다 — questions.ts 와 같은 캐스팅.
    .insert(payload as never)
    .select(APPROVAL_COLS)
    .single();
  if (error) throw new Error(error.message);
  return data as unknown as ApprovalRow;
}

export async function fetchJson<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`fetch ${r.status}`);
  return (await r.json()) as T;
}
```

`web/src/lib/viewer/math.ts`:
```ts
// 뷰어 순수 계산 — three 에 의존하지 않아 vitest(node)에서 검증한다.
export type Axis = 'x' | 'z';
export type Keep = 'below' | 'above';
export type Preset = 'side' | 'front' | 'bottom' | 'iso';
export type Vec3 = [number, number, number];
export interface Box { min: Vec3; max: Vec3 }

/** 받침선(P4) 기준 거리 d(m) ↔ 월드 z */
export function zFromDistance(zP4: number, d: number): number { return zP4 + d; }
export function distanceFromZ(zP4: number, z: number): number { return z - zP4; }

/** three.Plane(normal, constant): normal·p + constant < 0 이면 잘린다. below = 값보다 작은 좌표만 남김. */
export function clipPlane(axis: Axis, value: number, keep: Keep): { normal: Vec3; constant: number } {
  const n: Vec3 = axis === 'x' ? [1, 0, 0] : [0, 0, 1];
  const s = keep === 'below' ? -1 : 1;
  return { normal: [n[0] * s, n[1] * s, n[2] * s], constant: -s * value };
}

const FOV_DEG = 45;

/** 프리셋 카메라 — bbox 중심을 보며 전체가 화면에 들어오는 거리. side=+x, front=+z, bottom=아래·앞·옆, iso=위·앞·옆 */
export function presetCamera(preset: Preset, box: Box): { position: Vec3; target: Vec3 } {
  const c: Vec3 = [(box.min[0] + box.max[0]) / 2, (box.min[1] + box.max[1]) / 2, (box.min[2] + box.max[2]) / 2];
  const size = Math.max(box.max[0] - box.min[0], box.max[1] - box.min[1], box.max[2] - box.min[2]);
  const dist = (size / 2) / Math.tan((FOV_DEG * Math.PI) / 360) * 1.15;
  const dir: Record<Preset, Vec3> = {
    side: [1, 0, 0], front: [0, 0, 1], bottom: [0.35, -1, 0.25], iso: [0.6, 0.45, 0.65],
  };
  const d = dir[preset];
  const len = Math.hypot(d[0], d[1], d[2]);
  return { position: [c[0] + (d[0] / len) * dist, c[1] + (d[1] / len) * dist, c[2] + (d[2] / len) * dist], target: c };
}
```

- [ ] **Step 5: 통과 확인**

Run: `npm --prefix web test` → PASS (기존 5 + 7)

- [ ] **Step 6: scene.ts (three.js 뷰어)**

`web/src/lib/viewer/scene.ts`:
```ts
// three.js 뷰어 — React 무관. 섹션 GLB 를 각각 로드해 한 씬에 얹는다(레고식 결합, 좌표 변환 없음).
// 버텍스 컬러 유지·양면·클리핑 평면. 피킹은 Raycaster(30k 삼각형이라 BVH 불요).
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { clipPlane, presetCamera, type Axis, type Keep, type Preset, type Vec3 } from './math';

export interface PickInfo { node: string; section: string; point: Vec3 }
export interface Viewer {
  loadSection(key: string, url: string): Promise<{ meshes: number }>;
  setVisible(key: string, on: boolean): void;
  solo(key: string | null): void;
  setClip(axis: Axis, opts: { enabled: boolean; value: number; keep: Keep }): void;
  preset(p: Preset): void;
  highlight(node: string | null): void;
  onPick(cb: (info: PickInfo | null) => void): void;
  bounds(): { min: Vec3; max: Vec3 } | null;
  dispose(): void;
}

export function createViewer(canvas: HTMLCanvasElement): Viewer {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.localClippingEnabled = true;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xf4f4f2);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8c8c86, 1.1));
  const sun = new THREE.DirectionalLight(0xffffff, 1.4);
  sun.position.set(30, 60, 40);
  scene.add(sun);
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
  const controls = new OrbitControls(camera, canvas);
  controls.addEventListener('change', () => (dirty = true));

  const sections = new Map<string, THREE.Group>();
  const visible = new Map<string, boolean>();
  let soloKey: string | null = null;
  const planes: Record<Axis, THREE.Plane | null> = { x: null, z: null };
  const materials: THREE.MeshStandardMaterial[] = [];
  let highlighted: THREE.Mesh | null = null;
  let pickCb: ((info: PickInfo | null) => void) | null = null;
  let dirty = true;
  let disposed = false;

  const loader = new GLTFLoader();

  function applyVisibility() {
    for (const [key, g] of sections) g.visible = soloKey ? key === soloKey : (visible.get(key) ?? true);
    dirty = true;
  }
  function activePlanes(): THREE.Plane[] {
    return [planes.x, planes.z].filter((p): p is THREE.Plane => p !== null);
  }
  function applyPlanes() {
    const ps = activePlanes();
    for (const m of materials) { m.clippingPlanes = ps; m.needsUpdate = true; }
    dirty = true;
  }
  function fit(p: Preset) {
    const b = bounds();
    if (!b) return;
    const { position, target } = presetCamera(p, b);
    camera.position.set(...position);
    controls.target.set(...target);
    camera.near = 0.1; camera.far = 5000; camera.updateProjectionMatrix();
    controls.update();
    dirty = true;
  }
  function bounds(): { min: Vec3; max: Vec3 } | null {
    const box = new THREE.Box3();
    let any = false;
    for (const g of sections.values()) { box.expandByObject(g); any = true; }
    return any ? { min: box.min.toArray() as Vec3, max: box.max.toArray() as Vec3 } : null;
  }
  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (w === 0 || h === 0) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    dirty = true;
  }
  const ro = new ResizeObserver(resize);
  ro.observe(canvas);
  resize();

  function frame() {
    if (disposed) return;
    requestAnimationFrame(frame);
    if (!dirty) return;
    dirty = false;
    renderer.render(scene, camera);
  }
  frame();

  // 피킹 — 드래그(회전)와 구분: pointerdown/up 거리 4px 이내만 클릭
  const ray = new THREE.Raycaster();
  let down: [number, number] | null = null;
  canvas.addEventListener('pointerdown', (e) => { down = [e.clientX, e.clientY]; });
  canvas.addEventListener('pointerup', (e) => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;
    const r = canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const targets: THREE.Object3D[] = [];
    for (const g of sections.values()) if (g.visible) targets.push(g);
    const hits = ray.intersectObjects(targets, true).filter((h) => {
      const p = h.point;
      return activePlanes().every((pl) => pl.distanceToPoint(p) >= 0);      // 잘린 면은 피킹 제외
    });
    const hit = hits[0];
    const mesh = hit?.object as THREE.Mesh | undefined;
    pickCb?.(mesh ? { node: mesh.userData.node as string, section: mesh.userData.section as string, point: hit!.point.toArray() as Vec3 } : null);
  });

  return {
    async loadSection(key, url) {
      const gltf = await loader.loadAsync(url);
      let n = 0;
      gltf.scene.traverse((o) => {
        const mesh = o as THREE.Mesh;
        if (!mesh.isMesh) return;
        n += 1;
        const src = mesh.material as THREE.MeshStandardMaterial;
        const mat = new THREE.MeshStandardMaterial({
          vertexColors: true, side: THREE.DoubleSide, metalness: 0.05, roughness: 0.85,
          color: src?.color ?? new THREE.Color(0xffffff),
        });
        mat.clippingPlanes = activePlanes();
        mesh.material = mat;
        materials.push(mat);
        mesh.userData.node = mesh.name;
        mesh.userData.section = key;
      });
      const group = new THREE.Group();
      group.name = key;
      group.add(gltf.scene);
      const first = sections.size === 0;
      sections.set(key, group);
      if (!visible.has(key)) visible.set(key, true);
      scene.add(group);
      applyVisibility();
      if (first) fit('iso');
      return { meshes: n };
    },
    setVisible(key, on) { visible.set(key, on); applyVisibility(); },
    solo(key) { soloKey = key; applyVisibility(); },
    setClip(axis, { enabled, value, keep }) {
      if (!enabled) planes[axis] = null;
      else { const p = clipPlane(axis, value, keep); planes[axis] = new THREE.Plane(new THREE.Vector3(...p.normal), p.constant); }
      applyPlanes();
    },
    preset(p) { fit(p); },
    highlight(node) {
      if (highlighted) { (highlighted.material as THREE.MeshStandardMaterial).emissive.setHex(0x000000); highlighted = null; }
      if (node) {
        for (const g of sections.values()) g.traverse((o) => { if ((o as THREE.Mesh).isMesh && o.name === node) highlighted = o as THREE.Mesh; });
        if (highlighted) (highlighted.material as THREE.MeshStandardMaterial).emissive.setHex(0x3355ff);
      }
      dirty = true;
    },
    onPick(cb) { pickCb = cb; },
    bounds,
    dispose() {
      disposed = true;
      ro.disconnect();
      controls.dispose();
      for (const m of materials) m.dispose();
      scene.traverse((o) => { const g = (o as THREE.Mesh).geometry; g?.dispose?.(); });
      renderer.dispose();
    },
  };
}
```

- [ ] **Step 7: Model.tsx 최소 화면 + 라우트·링크**

`web/src/routes/Model.tsx` (Task 5 판 — 좌 패널 + 캔버스, 우 패널은 자리만):
```tsx
// 3D 검수 화면 — 좌: 빌드·섹션 트리 / 중: three.js 캔버스 / 우: 검증·승인 패널 (M4 설계서 §6)
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Alert, Anchor, Badge, Box, Button, Checkbox, Group, Loader, Paper, ScrollArea, Select, Stack, Text, Title } from '@mantine/core';

import { fetchProject, type ProjectRef } from '../lib/questions';
import { fetchBuilds, fetchSections, signedUrls, type BuildRow, type SectionRow } from '../lib/models';
import { supabase } from '../lib/supabase';
import { createViewer, type PickInfo, type Viewer } from '../lib/viewer/scene';

type LoadState = 'loading' | 'ok' | 'error';

export function Model() {
  const { slug = '' } = useParams();
  const [project, setProject] = useState<ProjectRef | null>(null);
  const [builds, setBuilds] = useState<BuildRow[] | null>(null);
  const [buildId, setBuildId] = useState<string | null>(null);
  const [sections, setSections] = useState<SectionRow[]>([]);
  const [load, setLoad] = useState<Record<string, LoadState>>({});
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [solo, setSolo] = useState<string | null>(null);
  const [picked, setPicked] = useState<PickInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const viewerRef = useRef<Viewer | null>(null);

  const build = useMemo(() => builds?.find((b) => b.id === buildId) ?? null, [builds, buildId]);

  useEffect(() => {
    if (supabase === null) return;
    (async () => {
      try {
        const p = await fetchProject(supabase, slug);
        setProject(p);
        const bs = await fetchBuilds(supabase, p);
        setBuilds(bs);
        setBuildId(bs[0]?.id ?? null);
      } catch (e) { setError((e as Error).message); }
    })();
  }, [slug]);

  // 뷰어 생성·해제
  useEffect(() => {
    if (!canvasRef.current) return;
    const v = createViewer(canvasRef.current);
    v.onPick((info) => { setPicked(info); v.highlight(info?.node ?? null); });
    viewerRef.current = v;
    return () => { v.dispose(); viewerRef.current = null; };
  }, []);

  // 빌드가 바뀌면 섹션 로드(프로그레시브)
  const loadBuild = useCallback(async (b: BuildRow) => {
    if (supabase === null || !viewerRef.current) return;
    const secs = await fetchSections(supabase, b.id);
    setSections(secs);
    setLoad(Object.fromEntries(secs.map((s) => [s.section_key, 'loading' as LoadState])));
    setVisible(Object.fromEntries(secs.map((s) => [s.section_key, true])));
    const { urls, failed } = await signedUrls(supabase, secs.map((s) => s.glb_path));
    for (const s of secs) {
      const url = urls.get(s.glb_path);
      if (!url || failed.includes(s.glb_path)) { setLoad((m) => ({ ...m, [s.section_key]: 'error' })); continue; }
      viewerRef.current.loadSection(s.section_key, url)
        .then(() => setLoad((m) => ({ ...m, [s.section_key]: 'ok' })))
        .catch(() => setLoad((m) => ({ ...m, [s.section_key]: 'error' })));
    }
  }, []);
  useEffect(() => { if (build) void loadBuild(build); }, [build, loadBuild]);

  if (error) return <Alert m="xl" color="red">{error}</Alert>;
  if (!project || !builds) return <Loader m="xl" />;

  const statusColor = (s: string) => (s === '승인' ? 'green' : s === '반려' ? 'red' : 'gray');

  return (
    <Group align="stretch" gap={0} h="100vh" wrap="nowrap">
      <Paper w={300} p="md" withBorder radius={0} style={{ overflow: 'hidden' }}>
        <Stack gap="sm" h="100%">
          <Anchor component={Link} to="/" size="sm">← 프로젝트</Anchor>
          <Title order={5}>{project.name} — 3D 검수</Title>
          {builds.length === 0 && <Text c="dimmed" size="sm">빌드가 없습니다 — worker 에서 `m3d publish-model` 을 실행하세요.</Text>}
          <Select size="xs" label="빌드" value={buildId} onChange={setBuildId}
            data={builds.map((b) => ({ value: b.id, label: `b${b.version} · ${b.kind} · ${b.stats.meshes} 메시 · ${b.status}` }))} />
          {build && (
            <Text size="xs" c="dimmed">구간 {build.segment} · 결합본 <Badge size="xs" color={statusColor(build.status)}>{build.status}</Badge></Text>
          )}
          <ScrollArea style={{ flex: 1 }}>
            <Stack gap={4}>
              {sections.map((s) => (
                <Group key={s.id} gap="xs" wrap="nowrap" justify="space-between">
                  <Checkbox size="xs" checked={visible[s.section_key] ?? true} disabled={solo !== null}
                    onChange={(e) => { setVisible((m) => ({ ...m, [s.section_key]: e.currentTarget.checked })); viewerRef.current?.setVisible(s.section_key, e.currentTarget.checked); }}
                    label={<Text size="sm">{s.label} <Text span c="dimmed" size="xs">{s.code} · {s.meshes}</Text></Text>} />
                  <Group gap={4} wrap="nowrap">
                    {load[s.section_key] === 'loading' && <Loader size={12} />}
                    {load[s.section_key] === 'error' && <Badge size="xs" color="red">로드 실패</Badge>}
                    <Badge size="xs" color={statusColor(s.status)}>{s.status}</Badge>
                    <Button size="compact-xs" variant={solo === s.section_key ? 'filled' : 'subtle'}
                      onClick={() => { const next = solo === s.section_key ? null : s.section_key; setSolo(next); viewerRef.current?.solo(next); }}>
                      단독
                    </Button>
                  </Group>
                </Group>
              ))}
            </Stack>
          </ScrollArea>
        </Stack>
      </Paper>
      <Box style={{ flex: 1, position: 'relative', minWidth: 0 }}>
        <canvas ref={canvasRef} style={{ width: '100%', height: '100%', display: 'block' }} />
        <Paper pos="absolute" top={8} left={8} p="xs" withBorder>
          <Text size="xs">{picked ? `${picked.node} · ${picked.section}` : '부재를 클릭하면 노드명이 표시됩니다'}</Text>
        </Paper>
      </Box>
      <Paper w={340} p="md" withBorder radius={0}>
        <Text size="sm" c="dimmed">검증·승인 패널 (Task 6)</Text>
      </Paper>
    </Group>
  );
}
```

`web/src/App.tsx`: `import { Model } from './routes/Model';` 와 `<Route path="p/:slug/model" element={<Model />} />` 를 questions 라우트 아래에 추가.
`web/src/routes/Projects.tsx`: 카드에 `<Anchor component={Link} to={`/p/${p.slug}/model`}>3D 검수 열기 →</Anchor>` 추가(질문 카드 링크 아래, `Group` 으로 나란히).

- [ ] **Step 8: 타입·테스트·브라우저 확인(시범 게이트)**

Run: `npm --prefix web run typecheck && npm --prefix web test` → 오류 0 / PASS
브라우저 패널: `preview_start {name: "web"}` → `/p/ab1-p4p5/model` 로 이동(로그인 세션은 브라우저에 남아 있음; 없으면 사용자에게 로그인 요청) → `read_console_messages` 오류 0 → 스크린샷: 섹션 10행·상태 배지·로더 → 캔버스에 결합본. `단독` 으로 `격벽` 만 보이는 스크린샷.
**STOP — 사용자 확인 게이트(D10)**: 스크린샷 2장을 전송하고 "이 화면으로 Task 6(클리핑·피킹·검증 패널·승인) 진행" 승인을 받는다.

- [ ] **Step 9: 커밋**

```bash
git add web/package.json web/package-lock.json web/src/lib/models.ts web/src/lib/models.test.ts web/src/lib/viewer/math.ts web/src/lib/viewer/math.test.ts web/src/lib/viewer/scene.ts web/src/routes/Model.tsx web/src/App.tsx web/src/routes/Projects.tsx
git commit -m "feat(web): 3D 검수 화면 최소판 — 섹션 GLB 서명 URL 로드·트리·단독 보기 (three.js 직접)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: 뷰어 기능 완성 — 클리핑·프리셋·피킹 + 검증·렌더·다운로드·승인 패널

**Files:**
- Modify: `web/src/routes/Model.tsx`(툴바·우 패널), `web/src/lib/models.ts`(변경 없음 — Task 5 함수 사용)
- Create: `web/src/components/VerifyPanel.tsx`

**Interfaces:**
- Consumes: `Viewer.setClip/preset/highlight/onPick`, `fetchApprovals`, `submitApproval`, `approvalPayload`, `latestApprovals`, `signedUrls`, `fetchJson`, `useSession()`.
- Produces: `VerifyPanel` props `{ project: ProjectRef; build: BuildRow; sections: SectionRow[]; selected: SectionRow | null; renderUrls: Map<string,string>; downloadUrls: Map<string,string>; approvals: ApprovalRow[]; onApproved(row: ApprovalRow): void }`.

- [ ] **Step 1: 툴바(프리셋·클리핑·선택 표시)**

`Model.tsx` 캔버스 위 `Paper` 를 툴바로 확장:
```tsx
const [clipZ, setClipZ] = useState({ enabled: false, d: 35, keep: 'below' as Keep });
const [clipX, setClipX] = useState({ enabled: false, x: 0, keep: 'below' as Keep });
const zP4 = -525;   // TODO 아님: build.stats 에 없으므로 modelspec.json(다운로드 URL)에서 coord.z_p4 를 읽어 세팅 — Step 3 에서 fetchJson 으로 채운다
useEffect(() => { viewerRef.current?.setClip('z', { enabled: clipZ.enabled, value: zFromDistance(zP4, clipZ.d), keep: clipZ.keep }); }, [clipZ, zP4]);
useEffect(() => { viewerRef.current?.setClip('x', { enabled: clipX.enabled, value: clipX.x, keep: clipX.keep }); }, [clipX]);
```
툴바 JSX: `SegmentedControl`(측면·정면·저면·아이소 → `viewerRef.current?.preset(...)`), `Switch` "z 단면" + `Slider min=0 max=70 step=0.1 label="P4+{d} m"` + `SegmentedControl` (`이전 유지`=below / `이후 유지`=above), `Switch` "x 절개" + `Slider min=-8 max=8 step=0.05` + keep, 선택 노드 텍스트(`picked.node · 섹션 라벨`) + "선택 해제" 버튼.
`Keep` 은 `import type { Keep } from '../lib/viewer/math'`.

- [ ] **Step 2: VerifyPanel 컴포넌트**

`web/src/components/VerifyPanel.tsx`:
```tsx
// 우측 패널 — 섹션 self-check 표, 결합본 집계, 렌더 썸네일(모달 확대), 다운로드, 승인/반려 기록·이력 (M4 설계서 §6)
import { useState } from 'react';
import { Anchor, Badge, Button, Group, Image, Modal, ScrollArea, SegmentedControl, Stack, Table, Text, Textarea, Title } from '@mantine/core';

import { approvalPayload, latestApprovals, submitApproval, targetKey, type ApprovalRow, type BuildRow, type SectionRow, type Verdict } from '../lib/models';
import type { ProjectRef } from '../lib/questions';
import { supabase } from '../lib/supabase';

export interface VerifyPanelProps {
  project: ProjectRef; build: BuildRow; sections: SectionRow[]; selected: SectionRow | null;
  renderUrls: Map<string, string>; downloadUrls: Map<string, string>; approvals: ApprovalRow[];
  onApproved(row: ApprovalRow): void;
}

export function VerifyPanel({ project, build, sections, selected, renderUrls, downloadUrls, approvals, onApproved }: VerifyPanelProps) {
  const [verdict, setVerdict] = useState<Verdict>('승인');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [zoom, setZoom] = useState<string | null>(null);
  const latest = latestApprovals(approvals);
  const target = selected ? selected.id : null;
  const history = approvals.filter((a) => targetKey(a.section_id) === targetKey(target));
  const st = build.stats;

  async function record() {
    if (supabase === null) return;
    setBusy(true); setErr(null);
    try {
      const row = await submitApproval(supabase, approvalPayload({ projectId: project.id, buildId: build.id, sectionId: target, verdict, note }));
      onApproved(row); setNote('');
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <Stack gap="sm" h="100%">
      <Title order={6}>{selected ? `${selected.label} (${selected.section_key})` : `결합본 b${build.version}`}</Title>
      <ScrollArea style={{ flex: 1 }}>
        <Stack gap="sm">
          <Text size="xs" fw={600}>self-check {selected ? `${selected.selfcheck.pass} PASS / ${selected.selfcheck.fail} FAIL` : `${st.selfcheck.pass} PASS / ${st.selfcheck.fail} FAIL / ${st.selfcheck.skipped} SKIP`}</Text>
          {selected && (
            <Table fz="xs" verticalSpacing={2}>
              <Table.Tbody>
                {selected.selfcheck.checks.map((c) => (
                  <Table.Tr key={c.label}>
                    <Table.Td><Badge size="xs" color={c.ok === true ? 'green' : c.ok === false ? 'red' : 'gray'}>{c.ok === true ? 'PASS' : c.ok === false ? 'FAIL' : 'SKIP'}</Badge></Table.Td>
                    <Table.Td>{c.label}</Table.Td><Table.Td c="dimmed">{c.detail}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
          <Text size="xs">결합본: 메시 {st.meshes} · 삼각형 {st.triangles}</Text>
          <Text size="xs">재실측: {st.measure ? `${st.measure.pass} PASS / ${st.measure.fail} FAIL / ${st.measure.info} INFO` : '없음(시범)'}</Text>
          <Text size="xs">참조 대조: {st.compare ? `${st.compare.match} match / ${st.compare.mismatch} mismatch / ${st.compare.na} na` : '없음(시범)'}</Text>
          <Text size="xs" fw={600}>렌더</Text>
          <Group gap={6}>
            {[...renderUrls].map(([key, url]) => (
              <Image key={key} src={url} w={150} radius="sm" style={{ cursor: 'zoom-in' }} onClick={() => setZoom(url)} alt={key} />
            ))}
          </Group>
          <Modal opened={zoom !== null} onClose={() => setZoom(null)} size="90%" title="렌더">{zoom && <Image src={zoom} alt="렌더" />}</Modal>
          <Text size="xs" fw={600}>다운로드</Text>
          {[...downloadUrls].map(([key, url]) => (<Anchor key={key} href={url} size="xs" target="_blank" rel="noreferrer">{key}</Anchor>))}
          <Text size="xs" fw={600}>승인 이력 ({history.length})</Text>
          {history.map((a) => (
            <Text key={a.id} size="xs"><Badge size="xs" color={a.verdict === '승인' ? 'green' : 'red'}>{a.verdict}</Badge> {a.created_at.slice(0, 16).replace('T', ' ')} {a.note}</Text>
          ))}
          <Text size="xs" c="dimmed">섹션 승인 {sections.filter((s) => latest.get(s.id)?.verdict === '승인').length}/{sections.length}</Text>
        </Stack>
      </ScrollArea>
      <SegmentedControl size="xs" value={verdict} onChange={(v) => setVerdict(v as Verdict)} data={['승인', '반려']} />
      <Textarea size="xs" placeholder="메모(선택, 500자)" value={note} onChange={(e) => setNote(e.currentTarget.value)} autosize minRows={2} />
      {err && <Text size="xs" c="red">{err}</Text>}
      <Button id="approve-button" size="xs" loading={busy} onClick={() => void record()}>{selected ? '이 섹션 ' : '결합본 '}{verdict} 기록</Button>
    </Stack>
  );
}
```

- [ ] **Step 3: Model.tsx 에 패널·URL·승인 상태 연결**

`Model.tsx` 추가 상태: `approvals`(fetchApprovals 로 로드), `renderUrls`·`downloadUrls`(signedUrls: `build.files.renders` → 렌더, `[build.glb_path, ...build.files.json, ...sections.map(s => s.glb_path)]` → 다운로드; 키 → 표시명은 경로의 마지막 두 조각), `selected: SectionRow | null`(피킹된 `picked.section` 또는 트리 행 클릭으로 선택; "결합본" 버튼으로 해제), `zP4`(다운로드 URL 중 `modelspec.json` 을 `fetchJson` 해 `spec.coord.z_p4`).
`onApproved(row)`: `setApprovals((a) => [row, ...a])`; `row.section_id` 가 있으면 `sections` 의 해당 status 를 `row.verdict` 로, 없으면 `builds` 의 해당 build status 를 갱신(트리거가 DB 를 바꾼 것과 동일하게 화면 반영).
우 패널: `{build && <VerifyPanel ... />}`.

- [ ] **Step 4: 타입·테스트·브라우저 실증**

Run: `npm --prefix web run typecheck && npm --prefix web test` → 오류 0 / PASS
브라우저 패널(로그인 상태): (1) 아이소 프리셋 + `격벽` 단독 + z 단면 P4+15 `이전 유지` → 격실 내부 스크린샷, (2) 부재 클릭 → 툴바에 `AB1_S5_DIA06 · P4P5/DIA`, 우 패널에 DIA self-check 표, (3) `이 섹션 승인 기록` → 이력 1건·배지 승인, (4) 결합본 `반려` 기록 → 빌드 배지 반려. `read_console_messages onlyErrors` → 0.
DB 확인: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli db check | grep -E "approvals"` → `approvals 2`.

- [ ] **Step 5: 커밋**

```bash
git add web/src/routes/Model.tsx web/src/components/VerifyPanel.tsx
git commit -m "feat(web): 3D 검수 — 단면 클리핑·프리셋·피킹 + self-check·렌더·다운로드·승인 패널" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: 실증·합격 판정·문서·통합

**Files:**
- Create: `data/derived/ab1-p4p5/model/acceptance-m4.md`(gitignore)
- Modify: `README.md`("3D 검수 (M4)" 절), 메모리 `m4-complete.md` + `MEMORY.md`

- [ ] **Step 1: 전 파이프라인 재실행(무과금) 후 판정 수치 확보**

```
PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli modelspec ab1-p4p5
PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli build ab1-p4p5 --pilot
PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli build ab1-p4p5
PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli measure ab1-p4p5
PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli render ab1-p4p5 --pilot
PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli render ab1-p4p5
PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli compare-model ab1-p4p5
PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli publish-model ab1-p4p5 --pilot
PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli publish-model ab1-p4p5
PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m m3d.cli db check | grep -E "builds|build_sections|approvals"
```
Expected: 섹션 10 section_fail=0 / measure 47/0/2 / compare 836/0/0 / publish 는 내용 불변이면 `skipped=true`(Task 4 에서 이미 올렸으면) — 판정서에는 실제 출력값을 적는다.

- [ ] **Step 2: 익명 접근 거부 (publishable 키만, 비밀값 출력 없음)**

heredoc 파이썬:
```python
import json, urllib.error, urllib.request
from m3d.config import load_config
cfg = load_config()
base, key = cfg.supabase_url.rstrip("/"), cfg.supabase_publishable_key
def req(method, path, data=None):
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    r = urllib.request.Request(base + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read()[:60]
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:60]
print("storage object:", req("GET", "/storage/v1/object/models/ab1-p4p5/b1/AB1_P4P5.glb"))
print("builds select:", req("GET", "/rest/v1/builds?select=id"))
z = "00000000-0000-0000-0000-000000000000"
print("approvals insert:", req("POST", "/rest/v1/approvals", json.dumps({"project_id": z, "build_id": z, "verdict": "승인"}).encode()))
```
Expected: storage 400 또는 403, builds `200 b'[]'`(RLS 필터), approvals 401.

- [ ] **Step 3: 브라우저 E2E 스크린샷(사용자 로그인 세션) — 판정 ④ 증적**

`preview_start {name: "web"}` → `/p/ab1-p4p5/model`: (a) 최신 빌드 섹션 10행 + 결합본, (b) `격벽` 단독 + z 단면 → 격실 내부, (c) 노드 클릭 표시 + DIA self-check 표, (d) 승인 기록 후 배지·이력, (e) 빌드 Select 로 시범(b1) 전환 → 섹션 2행. `read_console_messages onlyErrors` 0. 스크린샷은 세션 내 육안 확인 + 판정서에 소견 기록(파일 저장 안 함, M2b 관례).

- [ ] **Step 4: acceptance-m4.md**

`data/derived/ab1-p4p5/model/acceptance-m4.md` — 설계서 §1 ①~⑥ 표(결과·근거: 실제 출력 수치), 실증 소견(브라우저 5장), 익명 거부 결과, 테스트 수(pytest·vitest), LLM 호출 0 근거(`usage.jsonl` 과금 행 113 불변), 메모(판정 중 잡은 결함이 있으면 기재).

- [ ] **Step 5: README "3D 검수 (M4)" 절**

`README.md` 끝에:
```markdown

## 3D 검수 (M4)

모델을 섹션(구간/부재그룹) GLB 10개 + 결합본으로 산출해 비공개 버킷 `models` 에 올리고, 웹에서 섹션을 따로 띄워 내부까지 검수한 뒤 승인/반려를 기록한다. 모두 **LLM 호출 없음**.

```powershell
$env:PYTHONUTF8='1'
.\worker\.venv\Scripts\m3d.exe build ab1-p4p5            # model/sections/P4P5/<그룹>.glb ×10 + AB1_P4P5.glb(결합본) + selfcheck_sections.json + build.json
.\worker\.venv\Scripts\m3d.exe render ab1-p4p5           # renders/*.png + renders/views.json(뷰 계약)
.\worker\.venv\Scripts\m3d.exe publish-model ab1-p4p5    # Storage 업로드 + builds/build_sections (내용 같으면 skip · --force · --pilot)
cd web; npm run dev                                       # http://localhost:5173/p/ab1-p4p5/model
```

화면: 좌 섹션 트리(표시 체크·단독 보기·상태 배지·빌드 버전), 중앙 three.js 캔버스(프리셋 4·z/x 단면 클리핑·부재 클릭 → 노드명),
우 검증 패널(섹션 self-check·재실측·참조대조 집계·렌더·다운로드·승인/반려 기록). 승인은 `approvals` 에 이력으로 쌓이고 트리거가
`build_sections.status`/`builds.status` 를 갱신한다. 합격 판정: `data/derived/ab1-p4p5/model/acceptance-m4.md`.
```

- [ ] **Step 6: 최종 검증·커밋·통합**

Run: `PYTHONUTF8=1 ./worker/.venv/Scripts/python.exe -m pytest worker/tests -q && npm --prefix web run typecheck && npm --prefix web test` → 전건 PASS
```bash
git add README.md
git commit -m "docs: README 3D 검수 (M4) 절 + M4 합격 판정" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```
메모리 `C:\Users\parkj\.claude\projects\D--Projects-model3d-studio\memory\m4-complete.md` 작성 + `MEMORY.md` 한 줄. 그 다음 `superpowers:finishing-a-development-branch`(테스트 재확인 → 통합 옵션 3개를 사용자에게).

---

## 계획 자체 검토

- **스펙 커버리지**: §1 ①(T1 결합 동일성 테스트·compare_glb) ②(T1 섹션 self-check, T7 재실측·대조 재실행) ③(T4 publish-model + skip/--force, T7 db check) ④(T5·T6 웹 기능, T7 E2E) ⑤(T7 익명 거부) ⑥(각 태스크 테스트, LLM 0). §2 D1(T1 sections·Coord.segment) D2(T1 assemble + 웹 섹션별 로드) D3(T1 selfcheck group) D4(T1 model_dir pilot) D5(T3 3표) D6(T3 버킷 + T5 signedUrls) D7(T4 content_sha256) D8(T5 three 직접) D9(T2 views.json) D10(T5 Step 8 게이트). §3~§6 함수·명령·화면 요소 모두 태스크에 있음. §9 범위 밖 미포함.
- **플레이스홀더**: "TBD/TODO/나중에" 없음. Task 6 Step 1 의 `zP4` 주석은 Step 3 에서 modelspec.json 으로 채우는 절차를 명시했다. Task 4 Step 4 의 파일 수는 실행 출력으로 확정한다고 적었다(계산: 시범 6+2+2=10, 전체 6+10+4+2=22).
- **타입 일관성**: `sections.CODES` ↔ 웹 `CODES` 같은 리스트(양쪽 테스트); `object_key` ↔ `modelObjectKey` 같은 예시; `build.json` 필드명(`key/code/label/file/meshes/triangles/bytes/sha256/selfcheck`)을 T1 산출 → T4 소비 → T3 표 컬럼(`section_key/code/label/glb_path/bytes/sha256/meshes/triangles/selfcheck`) → T5 `SectionRow` 로 그대로 이었다; `selfcheck.run(..., section=)` 반환 키 `pass/fail/checks[].group`; `Viewer` 메서드명은 T5 정의를 T6 이 그대로 호출; `ApprovalRow.created_at` 정렬 규칙은 `latestApprovals` 와 `fetchApprovals(order desc)` 모두 최신 우선.
- **경로 정합**: DB 저장 경로는 버킷 접두 없는 키(T4 명시, 설계서 §4 표기 보정) — 웹 `signedUrls` 가 그대로 쓴다.
