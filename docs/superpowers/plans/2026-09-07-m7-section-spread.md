# M7 8섹션 확산 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 격벽 외 8섹션(SP04·HST·SLAB·BRG·FRM·RIB·CS·WG)을 LLM 모델링 에이전트가 만들 수 있게 인프라를 일반화하고, 웹 일괄 큐로 실증한 뒤, 본체만 정답인 결합 모델을 검증한다.

**Architecture:** 설계서 `docs/superpowers/specs/2026-09-07-m7-section-spread-design.md`. 섹션별로 흩어진 정보(근거 정규식·대표 노드·역할 라벨·스펙 키)를 `agent/sections_meta.py` 한 표로 모으고, 크롭·프롬프트·자기 렌더·채점 피드백·웹이 그 표를 읽게 바꾼다. `ctx` 는 본체 프로파일 전체로 확장하고(BOX 섹션은 범위 밖), `ModelSpec` 전 필드에 의미 설명을 단다. 실행은 웹에서 여러 섹션을 한 번에 큐에 넣고 `m3d worker --poll --drain` 이 순차 처리한다.

**Tech Stack:** Python 3.12 (`worker/.venv`), pydantic 2, trimesh, matplotlib(Agg), psycopg 3, typer, anthropic SDK(Sonnet 5), pytest; React 18 + Mantine 8 + vitest; Supabase(Postgres `jobs`·`builds`).

## Global Constraints

- 실증 API 지출: M7 증분 ≤ **$25** — `usage.jsonl` stage `model-agent` 누적 상한 **$28.17**(기존 $3.17 포함). 잡은 웹에서 예산 28.17 로 만든다. 섹션당 잡 ≤ 3, 잡당 시도 ≤ 4.
- 모델 `claude-sonnet-5`, thinking 비활성, `max_tokens` 16,000, `MAX_ATTEMPTS` 4 — 바꾸지 않는다(D12).
- 채점·합격 규칙은 M6 그대로: `score_section` + `within_bbox_tol`(5 mm + 0.1 mm 여유). 섹션별 예외 없음(D7).
- LLM 에 정답 렌더·정답 빌더 코드를 주지 않는다. 노드명 목록은 준다(D3).
- BOX(본체)는 에이전트 대상이 아니다 — `SECTIONS` 에 넣지 않는다.
- 비밀값(`.env`·키)은 출력·커밋 금지. 참조 원본 `D:\Projects\Inspection\...` 읽기 전용.
- 한국어 주석·문서. 새 파일 UTF-8. 워커·스크립트는 `export PYTHONUTF8=1` 뒤에 실행.
- **Bash heredoc 은 백슬래시를 소비한다** — 정규식·`\n` 이 든 파일은 Write/Edit 툴로 쓰거나 `chr(92)` 로 조립한다. 검증과 커밋을 한 명령에 묶을 때는 `set -o pipefail` 을 앞에 둔다. 항상 절대경로로 `cd /d/Projects/model3d-studio` 부터 시작한다.
- 테스트: 워커 `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest -q`, 웹 `cd /d/Projects/model3d-studio/web && npm test -- --run` 과 `npm run typecheck`.
- 브랜치 `feat/m7-section-spread`(main 0f9a56b 분기). 커밋 메시지 끝에 `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- 완료 주장 전 실제 실행 출력으로 검증(전역 규칙 2).

## 파일 구조

| 파일 | 책임 | 작업 |
|---|---|---|
| `worker/src/m3d/agent/sections_meta.py` (신규) | 섹션 메타 표 — 정규식·대표 노드·역할·스펙 키, 노드명 조회 | Task 1 |
| `worker/src/m3d/agent/crops.py` | 근거 크롭 — 메타의 pattern 사용, None 이면 크롭 없음 | Task 1 |
| `worker/src/m3d/agent/score.py` | 채점 — 역할 라벨을 메타에서 | Task 1 |
| `worker/src/m3d/agent/runner.py` | 샌드박스 ctx — `SectionContext` 로 확장 | Task 2 |
| `worker/src/m3d/agent/sandbox.py` | 러너 호출(변경 없음, 확인만) | Task 2 |
| `worker/src/m3d/model/spec.py` | 전 하위 모델 필드 `description` | Task 3 |
| `worker/src/m3d/agent/context.py` | 프롬프트 — ctx 문서·섹션별 노드명 블록·섹션별 스펙 발췌 | Task 4 |
| `worker/src/m3d/agent/critique.py` | 자기 렌더 — 메타에서 3뷰 생성(전체 아이소 포함) | Task 5 |
| `worker/src/m3d/agent/loop.py` | 루프 — 섹션 코드·ref_dir 를 메타 함수에 전달 | Task 4·5 |
| `worker/src/m3d/agent/worker.py`, `cli.py` | `--drain` | Task 6 |
| `web/src/lib/jobs.ts`, `routes/Model.tsx` | 다중 선택·일괄 잡 생성 | Task 6 |
| `worker/src/m3d/model/assemble_agent.py` (신규), `cli.py` | 전집 결합 빌드 + publish | Task 7 |
| `data/derived/.../acceptance-m7.md`, `README.md` | 실증·판정 | Task 8 |

---

### Task 1: 섹션 메타 표 + 크롭·채점 연결

**Files:**
- Create: `worker/src/m3d/agent/sections_meta.py`
- Modify: `worker/src/m3d/agent/crops.py:22` (`SECTION_PATTERNS`), `:33-45` (`fetch_evidence`)
- Modify: `worker/src/m3d/agent/score.py` (`node_role`)
- Test: `worker/tests/test_agent_sections_meta.py` (신규), `worker/tests/test_agent_score.py`

**Interfaces:**
- Produces: `SectionMeta(code, label, pattern, rep_nodes, roles, spec_keys)` (frozen dataclass);
  `SECTIONS: dict[str, SectionMeta]` (9개, BOX 없음); `meta(code) -> SectionMeta`;
  `role_of(code, node) -> str | None`; `node_names(ref_dir, segment, code) -> list[str]`.
- Consumes: `m3d.agent.score.load_named(glb) -> dict[str, Trimesh]`, `m3d.model.sections.LABELS`.

- [ ] **Step 1: 실패하는 테스트 작성**

`worker/tests/test_agent_sections_meta.py` (신규):

```python
"""섹션 메타 표 (M7 D2) — 크롭 정규식·대표 노드·역할 라벨·스펙 키를 한 곳에서."""

import pytest

from m3d.agent import sections_meta as M
from m3d.model import sections as X
from m3d.model.builder import Builder
from m3d.model.spec import ModelSpec


def test_nine_sections_without_box_match_group_labels():
    assert set(M.SECTIONS) == set(X.CODES) - {"BOX"}
    for code, m in M.SECTIONS.items():
        assert m.code == code and m.label == X.LABELS[code]
        assert m.rep_nodes and all(n.startswith("AB1_S5_") for n in m.rep_nodes)
        assert m.spec_keys and "coord" not in m.spec_keys and "box" not in m.spec_keys   # 공통은 별도로 붙는다


def test_hst_has_no_reading_pattern_others_do():
    assert M.SECTIONS["HST"].pattern is None
    assert all(M.SECTIONS[c].pattern for c in ("DIA", "SP04", "SLAB", "BRG", "FRM", "RIB", "CS", "WG"))


@pytest.mark.parametrize("code,node,label", [
    ("DIA", "AB1_S5_DIA01", "지점 격벽"),
    ("DIA", "AB1_S5_DIA13", "일반 격벽"),
    ("DIA", "AB1_S5_DIA26", "지점 격벽"),
    ("FRM", "AB1_S5_FRM07_TRW", "상부 웹"),
    ("FRM", "AB1_S5_FRM07_VSL", "수직보강재"),
    ("BRG", "AB1_S5_BRG_P4_1_SOLE", "솔플레이트"),
    ("BRG", "AB1_S5_BRG_P5_2_MORTAR", "무수축 모르타르"),
    ("SLAB", "AB1_S5_BARRIER_CTR", "중앙 방호벽"),
    ("SLAB", "AB1_S5_SLAB", "바닥판"),
    ("WG", "AB1_S5_WG096L_ST", "스트럿"),
    ("WG", "AB1_S5_WG096L", "가로보 본체"),
    ("CS", "AB1_S5_CS096L", "좌(보도측)"),
])
def test_role_of_labels_known_nodes(code, node, label):
    assert M.role_of(code, node) == label


def test_role_of_unknown_returns_none():
    assert M.role_of("SP04", "AB1_S5_SP04_ZZZ") is None
    assert M.role_of("NOPE", "AB1_S5_DIA01") is None


def test_node_names_reads_reference_section(tmp_path):
    spec = ModelSpec()
    b = Builder(spec)
    b.export_sections(X.split(b.build(pilot=False), spec.coord.segment), tmp_path)
    names = M.node_names(tmp_path, "P4P5", "SP04")
    assert names == ["AB1_S5_SP04_BF", "AB1_S5_SP04_TF", "AB1_S5_SP04_WEB_L", "AB1_S5_SP04_WEB_R"]
    assert len(M.node_names(tmp_path, "P4P5", "FRM")) == 150
    assert len(M.node_names(tmp_path, "P4P5", "WG")) == 156
```

- [ ] **Step 2: 실패 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_agent_sections_meta.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'm3d.agent.sections_meta'`

- [ ] **Step 3: 메타 모듈 작성**

`worker/src/m3d/agent/sections_meta.py` (Write 툴로 — 정규식에 백슬래시가 있다):

```python
"""섹션 메타 (M7 D2) — 섹션마다 다른 것만 한 표에: 판독 근거 정규식·대표 노드·역할 라벨·스펙 발췌 키.

크롭(crops)·프롬프트(context)·자기 렌더(critique)·채점 피드백(score)·웹이 모두 여기를 읽는다.
새 부재 그룹을 에이전트 대상으로 넣으려면 이 표에 한 줄을 더한다. BOX(본체)는 ctx 가 곧 그 기하라 대상이 아니다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from m3d.model import sections as X


@dataclass(frozen=True)
class SectionMeta:
    code: str
    label: str
    pattern: str | None                      # 판독 근거 정규식 (None = 크롭 없음)
    rep_nodes: tuple[str, ...]               # 자기 렌더 근접 뷰의 대표 노드
    roles: tuple[tuple[str, str], ...]       # (노드명 정규식, 역할 라벨) — 앞에서부터 첫 일치
    spec_keys: tuple[str, ...]               # 스펙 발췌에 넣을 하위 모델 (공통 coord·box 는 항상 추가)


SECTIONS: dict[str, SectionMeta] = {m.code: m for m in (
    SectionMeta("DIA", "격벽", r"다이아프램|격벽|DIAP|개구|문턱|잭업|수직보강",
                ("AB1_S5_DIA01",),
                ((r"DIA(01|26)$", "지점 격벽"), (r"DIA\d\d$", "일반 격벽")),
                ("diaphragm", "bearing")),
    SectionMeta("SP04", "이음판", r"이음판|SP-?04|현장이음|스플라이스",
                ("AB1_S5_SP04_TF",),
                ((r"_TF$", "상면판"), (r"_BF$", "하면판"), (r"_WEB_[LR]$", "복부판")),
                ("sp04",)),
    SectionMeta("HST", "수평보강재", None,
                ("AB1_S5_HST_UP_L",),
                ((r"_UP_[LR]$", "상단열"), (r"_LO1_[LR]$", "하단 1열"), (r"_LO2_[LR]$", "하단 2열")),
                ("hstiff", "diaphragm")),
    SectionMeta("SLAB", "슬래브·방호벽", r"슬래브|바닥판|방호벽|포장|콘크리트",
                ("AB1_S5_SLAB",),
                ((r"BARRIER_CTR$", "중앙 방호벽"), (r"BARRIER_[LR]$", "연단 방호벽"), (r"SLAB$", "바닥판")),
                ("slab",)),
    SectionMeta("BRG", "받침", r"받침|솔플레이트|무수축|모르타르|교좌",
                ("AB1_S5_BRG_P4_1_BODY",),
                ((r"_SOLE$", "솔플레이트"), (r"_BODY$", "받침 본체"), (r"_MORTAR$", "무수축 모르타르"),
                 (r"_BLOCK$", "받침 블록")),
                ("bearing",)),
    SectionMeta("FRM", "개방 프레임", r"프레임|개방|가로보|수직보강재|FRAME|브레이싱",
                ("AB1_S5_FRM01_TRW",),
                ((r"_TRW$", "상부 웹"), (r"_TRF$", "상부 플랜지"), (r"_BRW$", "하부 웹"),
                 (r"_BRF$", "하부 플랜지"), (r"_VS[LR]$", "수직보강재")),
                ("frame", "diaphragm")),
    SectionMeta("RIB", "종리브", r"종리브|리브|U-?리브|RIB",
                ("AB1_S5_RIB_TP4_1",),
                ((r"_RIB_T", "상판 리브"), (r"_RIB_B", "하판 리브")),
                ("rib",)),
    SectionMeta("CS", "외측빔", r"외측빔|연단|CS|가로보 선단",
                ("AB1_S5_CS096L",),
                ((r"CS\d+L$", "좌(보도측)"), (r"CS\d+R$", "우")),
                ("cs", "wg")),
    SectionMeta("WG", "외측가로보", r"외측가로보|가로보|캔틸레버|스트럿|니치|WG",
                ("AB1_S5_WG096L",),
                ((r"_ST$", "스트럿"), (r"_BR$", "브래킷"), (r"WG\d+[LR]$", "가로보 본체")),
                ("wg", "slab")),
)}


def meta(code: str) -> SectionMeta | None:
    return SECTIONS.get(code)


def role_of(code: str, node: str) -> str | None:
    """노드 → 역할 라벨(채점 피드백·렌더 캡션용). 표에 없으면 None."""
    m = SECTIONS.get(code)
    if m is None:
        return None
    for pat, label in m.roles:
        if re.search(pat, node):
            return label
    return None


def node_names(ref_dir, segment: str, code: str) -> list[str]:
    """정답 섹션 GLB 의 노드명(정렬) — 계약에 싣는 목록(D3)."""
    from m3d.agent.score import load_named
    return sorted(load_named(Path(ref_dir) / "sections" / segment / f"{code}.glb"))


assert set(SECTIONS) == set(X.CODES) - {"BOX"}, "섹션 메타와 부재 그룹 목록이 어긋난다"
```

- [ ] **Step 4: 통과 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_agent_sections_meta.py -q`
Expected: PASS (16개 안팎)

- [ ] **Step 5: 크롭·채점을 메타에 연결하는 테스트**

`worker/tests/test_agent_score.py` 의 `test_missing_and_shifted_nodes_fail_with_feedback` 은 이미 `role == "일반 격벽"` 을 본다(M6). 여기에 다른 섹션 라벨 확인을 더한다 — 파일 끝에 추가:

```python
def test_feedback_role_label_comes_from_section_meta():
    """역할 라벨은 섹션 메타에서 온다 — 격벽 전용 분기가 아니다(M7 D2)."""
    from m3d.agent import sections_meta as M
    assert S.node_role("FRM", "AB1_S5_FRM07_VSL", ModelSpec()) == M.role_of("FRM", "AB1_S5_FRM07_VSL") == "수직보강재"
    assert S.node_role("BRG", "AB1_S5_BRG_P4_1_SOLE", ModelSpec()) == "솔플레이트"
    assert S.node_role("SP04", "AB1_S5_SP04_TF", ModelSpec()) == "상면판"
```

`worker/tests/test_agent_context.py` 끝에 크롭 패턴 위임 테스트를 추가한다:

```python
def test_section_patterns_come_from_meta_and_hst_has_none():
    """크롭 정규식은 메타에서 온다; HST 는 판독 근거가 없어 패턴이 없다(M7 D9)."""
    from m3d.agent import crops as K2
    from m3d.agent import sections_meta as M
    assert K2.SECTION_PATTERNS["DIA"] == M.SECTIONS["DIA"].pattern
    assert set(K2.SECTION_PATTERNS) == {c for c, m in M.SECTIONS.items() if m.pattern}
    assert "HST" not in K2.SECTION_PATTERNS
```

- [ ] **Step 6: 실패 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_agent_score.py tests/test_agent_context.py -q`
Expected: FAIL — `node_role` 이 DIA 만 알고, `SECTION_PATTERNS` 는 DIA 만 있다.

- [ ] **Step 7: score.node_role·crops.SECTION_PATTERNS 위임**

`worker/src/m3d/agent/score.py` 의 `node_role` 을 교체(시그니처 유지 — `spec` 은 안 쓰지만 호출부 호환):

```python
def node_role(code: str, node: str, spec: ModelSpec) -> str | None:
    """노드 → 부재 역할 라벨(피드백용). 표는 sections_meta 에 있다(M7 D2)."""
    return sections_meta.role_of(code, node)
```

파일 상단 import 에 `from m3d.agent import sections_meta` 를 더한다.

`worker/src/m3d/agent/crops.py`: `SECTION_PATTERNS` 상수를 메타에서 만든다.

```python
from m3d.agent import sections_meta

SECTION_PATTERNS = {c: m.pattern for c, m in sections_meta.SECTIONS.items() if m.pattern}
```

- [ ] **Step 8: 지원 섹션 판단을 메타로 옮기는 테스트**

`loop.run_job` 은 지금 크롭 정규식이 없으면 `unsupported_section` 으로 튕긴다 — HST(근거 0건)가 그대로 막힌다(D9).
`worker/tests/test_agent_loop.py` 끝에 추가:

```python
def test_loop_supports_section_without_reading_pattern(cfg, ref_dir, monkeypatch):
    """HST 는 판독 근거가 없다 — 크롭 없이도 잡이 돌아야 한다(M7 D9)."""
    llm, calls = _fake_llm([GOOD])
    scorer, _ = _fake_scorer([True])
    monkeypatch.setattr(L, "spent_usd", lambda cfg, ds, stage=L.STAGE: 0.0)
    r = L.run_job(cfg, "ds", _job(section_key="P4P5/HST"), lambda lv, m: None, llm=llm, scorer=scorer,
                  publisher=_fake_publisher({}), crops=[], ref_dir=ref_dir, do_render=False)
    assert r.get("reason") != "unsupported_section" and len(calls) == 1
    assert calls[0]["n_images"] == 0


def test_loop_rejects_section_outside_meta(cfg, ref_dir, monkeypatch):
    """본체(BOX)는 에이전트 대상이 아니다."""
    llm, calls = _fake_llm([GOOD])
    monkeypatch.setattr(L, "spent_usd", lambda cfg, ds, stage=L.STAGE: 0.0)
    r = L.run_job(cfg, "ds", _job(section_key="P4P5/BOX"), lambda lv, m: None, llm=llm, evidence=[], crops=[],
                  ref_dir=ref_dir, do_render=False)
    assert r["reason"] == "unsupported_section" and calls == []
```

- [ ] **Step 9: 실패 확인 → loop.py 수정**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_agent_loop.py -q`
Expected: FAIL — HST 가 `unsupported_section` 으로 튕긴다.

`worker/src/m3d/agent/loop.py` 의 지원 판단을 메타로 바꾼다:

```python
    segment, code = job["section_key"].split("/")
    if agent_sections_meta.meta(code) is None:
        emit("error", f"지원하지 않는 섹션: {job['section_key']}")
        return {"pass": False, "reason": "unsupported_section", "attempts": 0, "cost_usd": 0.0, "assumptions": [], "questions": []}
    pattern = agent_crops.SECTION_PATTERNS.get(code)          # None 이면 크롭 없이 진행(HST)
```

그리고 근거 수집을 패턴이 있을 때만 한다:

```python
    if evidence is None:
        evidence = agent_crops.fetch_evidence(cfg, dataset, pattern) if pattern else []
```

import 에 `from m3d.agent import sections_meta as agent_sections_meta` 를 더한다(Task 4 에서도 쓴다).

- [ ] **Step 10: 통과 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_agent_sections_meta.py tests/test_agent_score.py tests/test_agent_context.py tests/test_agent_loop.py -q`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
cd /d/Projects/model3d-studio && git add worker/src/m3d/agent/sections_meta.py worker/src/m3d/agent/crops.py worker/src/m3d/agent/score.py worker/src/m3d/agent/loop.py worker/tests/test_agent_sections_meta.py worker/tests/test_agent_score.py worker/tests/test_agent_context.py worker/tests/test_agent_loop.py
git commit -m "feat(agent): 섹션 메타 표 — 근거 정규식·대표 노드·역할 라벨·스펙 키를 한 곳에; 지원 판단도 메타로(HST 크롭 없이 진행)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: ctx 확장 — SectionContext

**Files:**
- Modify: `worker/src/m3d/agent/runner.py:41-51` (`BoxContext` → `SectionContext`), `:83`
- Test: `worker/tests/test_agent_sandbox.py`

**Interfaces:**
- Consumes: `m3d.model.builder.Builder` 의 `el_road·y_deck_top·y_crown·y_bot_out·t_top·t_bot·SPAN·_zone_loft`, 상수 `COL_CONC·COL_BRG·COL_SOLE`.
- Produces: `runner.SectionContext(b: Builder)` — 기존 항목 + `span·el_road·y_deck_top·y_crown·y_bot_out·t_top·t_bot·COL_CONC·COL_BRG·COL_SOLE·zone_loft(z0, z1, poly_fn)`.

- [ ] **Step 1: 실패하는 테스트 작성**

`worker/tests/test_agent_sandbox.py` 끝에 추가:

```python
def test_section_context_exposes_full_box_profile_and_zone_loft():
    """확산에 필요한 본체 프로파일·색·존 로프트를 ctx 가 준다(M7 D1)."""
    from m3d.agent.runner import SectionContext
    from m3d.model.builder import Builder
    from m3d.model.spec import ModelSpec
    spec = ModelSpec()
    ctx = SectionContext(Builder(spec))
    z = spec.coord.z_p4 + 10.0
    assert abs(ctx.span - (spec.coord.z_p5 - spec.coord.z_p4)) < 1e-9
    assert ctx.y_deck_top(z) > ctx.y_web_top(z) > ctx.y_web_bot(z) > ctx.y_bot_out(z)
    assert abs(ctx.y_crown(z) - (ctx.y_deck_top(z) + spec.coord.t_slab_crown)) < 1e-9
    assert ctx.t_top(z) > 0 and ctx.t_bot(z) > 0 and ctx.el_road(z) > 0
    assert ctx.COL_CONC != ctx.COL_STEEL and ctx.COL_BRG != ctx.COL_SOLE
    mesh = ctx.zone_loft(spec.coord.z_p4, spec.coord.z_p4 + 20.0,
                         lambda zz: ctx.geom.rect(-0.1, 0.1, ctx.y_web_bot(zz), ctx.y_web_bot(zz) + 0.2))
    assert mesh.is_watertight and len(mesh.faces) > 0


def test_section_context_hides_builder_internals():
    """빌더 자체는 계약에 없다 — 밑줄 속성만 남기고 공개 이름으로 새지 않는다."""
    from m3d.agent.runner import SectionContext
    from m3d.model.builder import Builder
    from m3d.model.spec import ModelSpec
    ctx = SectionContext(Builder(ModelSpec()))
    public = [n for n in vars(ctx) if not n.startswith("_")]
    assert "build" not in public and "s" not in public
    assert set(public) >= {"x_web", "z_p4", "z_p5", "span", "y_deck_top", "t_top", "COL_CONC"}
```

- [ ] **Step 2: 실패 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_agent_sandbox.py -q`
Expected: FAIL — `ImportError: cannot import name 'SectionContext'`

- [ ] **Step 3: runner.py 수정**

import 줄을 `from m3d.model.builder import COL_BRG, COL_CONC, COL_SOLE, COL_STEEL, INS, Builder` 로 바꾸고, `BoxContext` 를 교체:

```python
class SectionContext:
    """에이전트에 노출하는 본체 기하 (M5 D2 → M7 D1 확장) — Builder 의 프로파일 함수·상수만.

    본체(BOX)는 전 섹션의 주어진 조건이라 프로파일 전체를 준다. 격벽 전용 도우미(dia_z·dia_half_w)는 주지 않는다.
    """

    def __init__(self, b: Builder):
        self.x_web = b.s.box.x_web
        self.z_p4, self.z_p5 = b.Z_P4, b.Z_P5
        self.span = b.SPAN
        self.y_web_top, self.y_web_bot, self.h_box, self.t_web = b.y_web_top, b.y_web_bot, b.h_box, b.t_web
        self.el_road, self.y_deck_top, self.y_crown, self.y_bot_out = b.el_road, b.y_deck_top, b.y_crown, b.y_bot_out
        self.t_top, self.t_bot = b.t_top, b.t_bot
        self.COL_STEEL, self.COL_CONC = list(COL_STEEL), list(COL_CONC)
        self.COL_BRG, self.COL_SOLE = list(COL_BRG), list(COL_SOLE)
        self.INS = INS
        self.geom = geom
        self._b = b

    def zone_loft(self, z0, z1, poly_fn):
        """판두께 전이점에서 분절해 로프트한다(전이 계단면은 구간 캡). 종리브·수평보강재처럼 긴 부재에 쓴다."""
        return self._b._zone_loft(z0, z1, poly_fn)
```

`main()` 의 `ctx = BoxContext(b)` 를 `ctx = SectionContext(b)` 로 바꾼다.

- [ ] **Step 4: 통과 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_agent_sandbox.py tests/test_agent_loop.py -q`
Expected: PASS (루프 테스트의 가짜 코드가 `ctx.y_web_bot` 등을 쓰므로 함께 확인)

- [ ] **Step 5: Commit**

```bash
cd /d/Projects/model3d-studio && git add worker/src/m3d/agent/runner.py worker/tests/test_agent_sandbox.py
git commit -m "feat(agent): ctx 를 SectionContext 로 확장 — 강상판·크라운·하면·판두께·색 4종·존 로프트

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: ModelSpec 전 필드 설명

**Files:**
- Modify: `worker/src/m3d/model/spec.py` (coord·box·FrameRow·Frame·RibZone·Rib·HStiff·WG·CS·Slab·SP04·Bearing)
- Test: `worker/tests/test_model_spec.py`

**Interfaces:**
- Produces: 모든 하위 모델의 모든 필드에 `Field(..., description=...)`.

- [ ] **Step 1: 실패하는 테스트 작성**

`worker/tests/test_model_spec.py` 의 `test_diaphragm_and_bearing_fields_carry_descriptions` 뒤에 추가:

```python
def test_every_submodel_field_carries_a_description():
    """프롬프트 스펙 발췌의 doc 은 전 섹션에 필요하다(M7 D4)."""
    from m3d.model.spec import ModelSpec
    missing = []
    for key, f in ModelSpec.model_fields.items():
        sub = getattr(f.annotation, "model_fields", None)
        if not sub:
            continue
        missing += [f"{key}.{n}" for n, sf in sub.items() if not sf.description]
    assert missing == [], f"description 없는 필드: {missing}"


def test_tuple_fields_name_the_axis_each_component_extends():
    """튜플 필드는 성분마다 뻗는 축을 밝힌다 — M6 에서 '돌출 vs 두께' 오독의 해법."""
    from m3d.model.spec import Bearing, SP04, Slab, WG
    for model, field in ((SP04, "tf"), (SP04, "bf"), (SP04, "web"), (Bearing, "sole"),
                         (Bearing, "mortar"), (Bearing, "block"), (Slab, "barrier"), (WG, "knee")):
        d = model.model_fields[field].description
        assert any(ax in d for ax in ("[x]", "[y]", "[z]")), f"{model.__name__}.{field} 축 표기 없음: {d}"
```

- [ ] **Step 2: 실패 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_model_spec.py -q`
Expected: FAIL — `description 없는 필드: ['coord.z_p4', 'coord.z_p5', …]` 약 70개

- [ ] **Step 3: 설명 달기 (Edit 툴로 필드마다)**

기존 격벽 필드 형식을 그대로 따른다. 값은 바꾸지 않는다. 아래를 그대로 쓴다.

`Coord`:
```python
    z_p4: float = Field(-525.0, description="P4 받침선 전역 z(m) — 이 구간의 원점 체인 시작")
    z_p5: float = Field(-455.0, description="P5 받침선 전역 z(m)")
    el0: float = Field(18.694, description="측점 z_sta3400 에서의 도로 계획고 EL(m)")
    grade: float = Field(0.0236, description="종단경사(무차원) — 계획고 = el0 + grade·(z − z_sta3400)")
    z_sta3400: float = Field(-790.0, description="계획고 기준 측점의 전역 z(m)")
    y_datum: float = Field(4.871, description="모델 y 원점 보정(m) — 모델 y = EL − y_datum")
    deck_drop: float = Field(0.398, description="계획고에서 강상판 상면까지 내림(m, y) — 포장+슬래브 crown 두께")
    t_slab_crown: float = Field(0.348, description="crown 위치 슬래브 두께(m, y) — 강상판 상면 + 이 값 = 슬래브 상면")
    walk_side_sign: int = Field(-1, description="보도(캔틸레버 넓은 쪽) x 부호 — −1 이면 −x 가 보도측")
    segment: str = Field("P4P5", description="구간 이름 — 섹션 키 '<구간>/<부재코드>' 와 섹션 GLB 폴더명")
```

`Box`:
```python
    half_flange: float = Field(2.35, description="상·하 플랜지 반폭(m, x) — 웹 외면보다 바깥")
    x_web: float = Field(2.25, description="웹 외면 x(m) — 웹은 ±x_web, 내면은 ±(x_web − t_web(z))")
    h_pier: float = Field(4.0, description="받침선 내공 높이 H(m, y)")
    h_mid: float = Field(2.8, description="중앙부 내공 높이 H(m, y)")
    l_flat: float = Field(1.25, description="받침선에서 등고 구간 길이(m, z) — 이 안에서는 H = h_pier")
    l_para: float = Field(13.45, description="포물선 변단면 구간 길이(m, z) — 등고 끝에서 중앙 등고 시작까지")
    a_dwg: float = Field(0.00663, description="도면 표기 포물선 계수(1/m) — 검산용, 실제는 (h_pier−h_mid)/l_para²")
    h_is_clear: bool = Field(True, description="H 를 내공(강상판 하면~하판 상면)으로 본다는 표시 [A1]")
    top_t: list[Zone] = Field([...], description="상판 두께 존 [(d0, d1, t)] — d 는 P4 로부터 거리(m), t 는 두께(m, y)")
    bot_t: list[Zone] = Field([...], description="하판 두께 존 [(d0, d1, t)] — d 는 P4 로부터 거리(m), t 는 두께(m, y)")
    web_t: list[Zone] = Field([...], description="웹 두께 존 [(d0, d1, t)] — d 는 P4 로부터 거리(m), t 는 두께(m, x)")
    z_sp04_offset: float = Field(18.9, description="P4 에서 SP04 현장이음선까지 거리(m, z)")
```
(`[...]` 자리에는 기존 기본값 리스트를 그대로 둔다 — 값 변경 금지.)

`FrameRow`:
```python
    d_list: list[float] = Field(..., description="이 타입이 쓰이는 받침선 거리 dmin(m) 목록")
    name: str = Field(..., description="도면 타입명(F·F3·G1·D 등) — 형상에는 영향 없음")
    top_web: tuple[float, float] = Field(..., description="(t 두께[z], h 높이[y]) 상부 가로보 웹 — 강상판 하면에서 아래로 h")
    bot_web: tuple[float, float] = Field(..., description="(t 두께[z], h 높이[y]) 하부 가로보 웹 — 하판 상면에서 위로 h")
    top_flange_t: float | None = Field(None, description="상부 플랜지 두께(m, y) — None 이면 웹 두께와 같게 본다 [A6]")
    vstiff: tuple[float, float, float] = Field(..., description="(t 두께[z], w 폭[x, 웹 내면에서 안쪽], l 길이[y]) 프레임 수직보강재 — 내공 중앙 [A7]")
```

`Frame`:
```python
    offset: float = Field(1.4, description="P4 에서 첫 프레임까지 거리(m, z) — 프레임 z = z_p4 + offset + k·격벽간격")
    rows: list[FrameRow] = Field([...], description="dmin 별 프레임 부재 규격 표 — dmin 은 양 받침선까지 최소 거리")
```

`RibZone`:
```python
    cols: int = Field(..., description="열 수(개) — x 방향으로 늘어선 리브 줄 수")
    pitch: float = Field(..., description="열 간격(m, x) — 열은 x=0 중심 대칭 배치")
    t: float = Field(..., description="리브 판 두께(m, x)")
    h: float = Field(..., description="리브 높이(m, y) — 판면에서 내공 쪽으로")
    from_web: float | None = Field(None, description="웹에서 첫 열까지 거리(m, x) — None 이면 중심 대칭만 쓴다")
```

`Rib`:
```python
    top_pier: RibZone = Field(..., description="지점부 상판 리브 존")
    top_mid: RibZone = Field(..., description="중앙부 상판 리브 존")
    top_switch: tuple[float, float] = Field(..., description="(d0, d1) 상판 리브 존 전이 구간(m, P4 로부터 거리) — 그 사이는 두 존의 열을 겹쳐 둔다")
    bot_pier: RibZone = Field(..., description="지점부 하판 리브 존")
    bot_mid: RibZone = Field(..., description="중앙부 하판 리브 존")
    bot_switch: tuple[float, float] = Field(..., description="(d0, d1) 하판 리브 존 전이 구간(m, P4 로부터 거리)")
```

`HStiff`:
```python
    t: float = Field(0.012, description="평강 두께(m, y)")
    h: float = Field(0.15, description="웹 내면에서 안쪽으로 내민 길이(m, x)")
    upper_drop: float = Field(0.56, description="강상판 하면에서 상단열 중심까지(m, y)")
    upper_span: float = Field(12.6, description="상단열이 빠지는 받침선 쪽 구간(m, z) — 상단열은 P4+이 값 ~ P5−이 값")
    lower_span: float = Field(25.2, description="하단열이 놓이는 받침선 쪽 구간 길이(m, z)")
    lower_factors: list[float] = Field([0.14, 0.36], description="하단 2열의 높이 비율 — y = 하판 상면 + 비율·H(z), 격벽 간격 절반마다 절선 [A20]")
```

`WG`:
```python
    first_no: int = Field(96, description="첫 가로보 번호 — 노드명 WG096L 처럼 3자리로 붙는다")
    length: float = Field(4.45, description="웹 외면에서 선단까지 내민 길이(m, x)")
    flange_slope: float = Field(0.0195, description="상플랜지 기울기(무차원) — 바깥으로 갈수록 내려간다")
    flange_flat0: float = Field(0.1, description="웹면에서 기울기 시작까지 수평 구간(m, x)")
    flange_flat1: float = Field(4.3, description="웹면에서 기울기 끝까지(m, x)")
    depth0: float = Field(0.3, description="웹면에서의 가로보 춤(m, y)")
    web_t: float = Field(0.012, description="가로보 웹 두께(m, z)")
    fl_t: float = Field(0.012, description="가로보 플랜지 두께(m, y)")
    fl_w: float = Field(0.3, description="가로보 플랜지 폭(m, z)")
    niche_r: float = Field(0.3, description="니치(하부 곡선) 반지름(m) — 웹 부착부 하단 원호")
    knee: tuple[float, float] = Field((3.9, 0.482), description="(x 웹면 기준 거리[x], y crown 아래 깊이[y]) 하플랜지 절선점")
    tip_depth: float = Field(0.424, description="선단 블록 춤(m, y) — 외측빔 CS 춤과 같다")
    strut_size: float = Field(0.3, description="스트럿 단면 한 변(m)")
    strut_angle_deg: float = Field(28.222, description="스트럿 축 각도(도) — 수평에서 아래로")
    strut_lower: tuple[float, float] = Field((0.302, 2.413), description="(x 웹면 기준[x], y 강상판 하면 아래 깊이[y]) 스트럿 하단 부착점")
    bracket: tuple[float, float, float] = Field((0.35, 2.17, 2.7), description="(t 두께[z], h 높이[y], w 폭[x]) 웹 부착 브래킷")
```

`CS`:
```python
    depth: float = Field(0.424, description="외측빔 춤(m, y)")
    web_t: float = Field(0.012, description="외측빔 웹 두께(m, x)")
    fl_w: float = Field(0.3, description="외측빔 플랜지 폭(m, x)")
    fl_t: float = Field(0.012, description="외측빔 플랜지 두께(m, y)")
    seg: float = Field(2.8, description="세그먼트 길이(m, z) — 가로보 간격과 같아 가로보마다 1세그")
```

`Slab`:
```python
    half_width: float = Field(7.85, description="슬래브 반폭(m, x) — 전폭 15.7")
    slope: float = Field(0.02, description="횡단 경사(무차원) — crown 에서 바깥으로 내려간다")
    t_edge: float = Field(0.25, description="연단 슬래브 두께(m, y)")
    t_web: float = Field(0.3, description="웹 위 슬래브 두께(m, y)")
    t_crown: float = Field(0.348, description="crown 슬래브 두께(m, y)")
    thickness_is_net: bool = Field(True, description="두께가 포장 제외 순두께라는 표시")
    cant_drop: list[tuple[float, float]] = Field([...], description="[(x 거리, crown 에서 내림[y])] 캔틸레버 하면 절선 — x 는 중심에서 거리(m)")
    walk_width: float = Field(2.95, description="보도 폭(m, x)")
    center_barrier: float = Field(0.45, description="중앙 방호벽 하부 폭(m, x)")
    barrier: tuple[float, float, float] = Field((0.45, 0.33, 0.03), description="(w 하부 폭[x], h 높이[y], cap 상부 축소[x]) 방호벽 단면")
```

`SP04`:
```python
    tf: tuple[float, float, float] = Field((4.386, 0.58, 0.01), description="(w 폭[x], l 길이[z], t 두께[y]) 상면 이음판 — 강상판 위에 덧댄다")
    bf: tuple[float, float, float] = Field((4.7, 0.78, 0.012), description="(w 폭[x], l 길이[z], t 두께[y]) 하면 이음판 — 하판 아래에 덧댄다")
    web: tuple[float, float, float] = Field((2.68, 0.58, 0.01), description="(h 높이[y], l 길이[z], t 두께[x]) 복부 이음판 — 웹 외면 좌우에 덧댄다")
    setback: float = Field(0.157, description="이음선에서 판 중심까지 z 오프셋(m) [A17]")
```

`Bearing` (x 는 이미 있음):
```python
    kind: str = Field("isolation", description="받침 종류 — 형상에는 영향 없음 [Q4]")
    sole: tuple[float, float, float, float] = Field((1.37, 0.022, 0.054, 0.038), description="(a 한 변[x·z], t 판 두께[y], h1 리브 높이[y], t1 리브 두께) 솔플레이트 — 하판 아래 부착")
    body_h: float = Field(0.337, description="받침 본체 높이(m, y)")
    base: float = Field(0.825, description="받침 하부판 한 변(m, x·z)")
    body_d: float = Field(0.65, description="받침 본체 지름(m, x·z)")
    mortar: tuple[float, float] = Field((0.05, 0.9), description="(t 두께[y], a 한 변[x·z]) 무수축 모르타르")
    block: tuple[float, float] = Field((1.3, 0.105), description="(a 한 변[x·z], t 두께[y]) 받침 블록 — 모르타르 아래")
    el_check: dict[str, float] = Field(..., description="받침 하면 EL 검산값(m) — 교각별, 모델 y = EL − y_datum")
```

- [ ] **Step 4: 통과 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_model_spec.py tests/test_model_builder.py tests/test_model_compare.py -q`
Expected: PASS — 값은 안 바뀌었으므로 빌더 정답 대조도 그대로 통과한다.

- [ ] **Step 5: Commit**

```bash
cd /d/Projects/model3d-studio && git add worker/src/m3d/model/spec.py worker/tests/test_model_spec.py
git commit -m "feat(model): ModelSpec 전 하위 모델 필드에 description — 축·단위·배치 규칙(M7 D4)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: 프롬프트 일반화 — ctx 문서·노드명 블록·섹션별 스펙 발췌

**Files:**
- Modify: `worker/src/m3d/agent/context.py` (`CTX_DOC`, `CODE_CONTRACT`, `spec_excerpt`, `section_bundle`)
- Modify: `worker/src/m3d/agent/loop.py` (`section_bundle` 호출에 `ref_dir` 전달)
- Test: `worker/tests/test_agent_context.py`, `worker/tests/test_agent_loop.py`

**Interfaces:**
- Consumes: `sections_meta.meta(code)`, `sections_meta.node_names(ref_dir, segment, code)`, `sections_meta.role_of`.
- Produces: `context.spec_excerpt(spec_dict, sources, code=None) -> dict` (code 를 주면 공통 `coord`·`box` + 그 섹션 `spec_keys` 만);
  `context.section_block(code, names) -> str`;
  `context.section_bundle(section_key, *, spec_dict, sources, evidence, crops, feedback=None, request="", prev_code=None, critique=None, node_list=None) -> dict`.

- [ ] **Step 1: 실패하는 테스트 작성**

`worker/tests/test_agent_context.py` 끝에 추가:

```python
def test_spec_excerpt_picks_section_keys_plus_common():
    """섹션마다 필요한 하위 모델만 싣는다 — 프롬프트가 커지면 중요한 값이 묻힌다(M7 3.3)."""
    d = ModelSpec().model_dump()
    ex_sp04 = C.spec_excerpt(d, SOURCES, code="SP04")
    assert set(ex_sp04) == {"coord", "box", "sp04"}
    ex_cs = C.spec_excerpt(d, SOURCES, code="CS")
    assert set(ex_cs) == {"coord", "box", "cs", "wg"}          # 외측빔은 가로보 기하에서 위치를 잡는다
    assert set(C.spec_excerpt(d, SOURCES, code="DIA")) == {"coord", "box", "diaphragm", "bearing"}
    assert set(C.spec_excerpt(d, SOURCES)) == {"coord", "box", "diaphragm", "bearing"}   # 기본은 격벽(하위호환)
    assert ex_sp04["sp04"]["tf"]["doc"].startswith("(w 폭[x]")


def test_section_block_lists_every_node_and_roles():
    names = ["AB1_S5_SP04_BF", "AB1_S5_SP04_TF", "AB1_S5_SP04_WEB_L", "AB1_S5_SP04_WEB_R"]
    block = C.section_block("SP04", names)
    assert "정확히 이 이름들만" in block and "(4개)" in block
    for n in names:
        assert n in block
    assert "상면판" in block and "복부판" in block


def test_bundle_carries_section_nodes_and_new_ctx_doc(tmp_path):
    b = C.section_bundle("P4P5/SP04", spec_dict=ModelSpec().model_dump(), sources={}, evidence=[], crops=[],
                         node_list=["AB1_S5_SP04_BF", "AB1_S5_SP04_TF", "AB1_S5_SP04_WEB_L", "AB1_S5_SP04_WEB_R"])
    text = "\n".join(p["text"] for p in b["messages"][0]["content"] if p["type"] == "text")
    assert "AB1_S5_SP04_WEB_R" in text and "정확히 이 이름들만" in text
    assert "ctx.y_deck_top(z)" in b["system"] and "ctx.zone_loft(" in b["system"] and "ctx.COL_CONC" in b["system"]
    assert "AB1_S5_DIA01 … AB1_S5_DIA26" not in b["system"]        # 격벽 전용 문장이 계약에서 빠졌다
```

`worker/tests/test_agent_loop.py` 의 `test_loop_retries_with_feedback_then_passes_and_builds_agent_dir` 안, `assert "실행 오류" in calls[1]["text"]` 앞에 추가:

```python
    assert "AB1_S5_DIA26" in calls[0]["text"] and "정확히 이 이름들만" in calls[0]["text"]   # 노드명 목록이 첫 호출부터 들어간다
```

- [ ] **Step 2: 실패 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_agent_context.py tests/test_agent_loop.py -q`
Expected: FAIL — `spec_excerpt() got an unexpected keyword argument 'code'`, `section_block` 없음.

- [ ] **Step 3: context.py 수정**

`CTX_DOC` 를 교체:

```python
CTX_DOC = """## ctx (본체 기하 — 주어진 조건, 전 섹션 공통)
- ctx.x_web: 웹 외면 x(m, +측). 웹은 x=±x_web 에 있고 두께 ctx.t_web(z) 만큼 안쪽으로 들어온다 → 웹 내면 x = ±(x_web − t_web(z)); 내공 판은 그 내면에 INS 만큼 물린다(반폭 = x_web − t_web(z) + INS).
- ctx.z_p4, ctx.z_p5, ctx.span: P4·P5 받침선 z(m)와 경간 길이. 반복 부재의 위치는 전역 체인 z = z_p4 + k·간격 에서 유도한다.
- ctx.y_web_top(z), ctx.y_web_bot(z): 강상판 하면 y / 하판 상면 y (내공 경계, m). ctx.h_box(z) = 내공 높이.
- ctx.y_deck_top(z): 강상판 상면 y — 슬래브·이음판이 여기에 얹힌다. ctx.y_bot_out(z): 하판 하면 y — 받침·이음판이 여기에 붙는다.
- ctx.y_crown(z): 슬래브 crown 상면 y. ctx.el_road(z): 도로 계획고 EL(모델 y 가 아니다).
- ctx.t_top(z), ctx.t_bot(z), ctx.t_web(z): 상판·하판·웹 판두께(m).
- ctx.zone_loft(z0, z1, poly_fn): 판두께 전이점에서 분절해 로프트한다(전이 계단면 캡 포함). 종리브·수평보강재처럼 z 로 긴 부재는 loft 대신 이것을 쓴다.
- ctx.COL_STEEL / ctx.COL_CONC / ctx.COL_BRG / ctx.COL_SOLE: 강재·콘크리트·받침·솔플레이트 색 [r,g,b,a]. ctx.INS: 접합부 관통 삽입 5mm.
- ctx.geom: 아래 툴킷 모듈(직접 import 해도 된다: from m3d.model.geom import ...)."""
```

`CODE_CONTRACT` 에서 격벽 전용 문장 두 개를 일반 문장으로 바꾼다. 첫 줄의 노드명 문장을 다음으로 교체:

```
- 노드명은 아래 '이 섹션의 노드' 목록과 **정확히** 같아야 한다(빠짐·추가 모두 채점 실패). 노드명 = 객체 DB 연결 키.
```

그리고 지점 격벽 전용 문장(`- 지점 격벽(받침선 위, 01·26)은 …`)을 다음 일반 문장으로 교체:

```
- 보강재·부속은 판 자체와 별도 솔리드로 만들어 같은 노드에 합친다(trimesh.util.concatenate). 두께 t 는 판면 안 방향, 돌출 w 는 판면 법선 방향이다.
```

(반복 판 두께·체인 문장, spec 값 경고 문장은 그대로 둔다 — 프레임·리브에도 맞는다.)

`spec_excerpt` 와 새 헬퍼:

```python
COMMON_SPEC_KEYS = ("coord", "box")
DEFAULT_SPEC_KEYS = ("diaphragm", "bearing")


def spec_keys_for(code: str | None) -> tuple[str, ...]:
    m = sections_meta.meta(code) if code else None
    return COMMON_SPEC_KEYS + (m.spec_keys if m else DEFAULT_SPEC_KEYS)


def spec_excerpt(spec_dict: dict, sources: dict, code: str | None = None) -> dict:
    return {sec: {k: _entry(sec, k, v, sources) for k, v in spec_dict[sec].items()} for sec in spec_keys_for(code)}


def section_block(code: str, names: list[str]) -> str:
    """계약에 싣는 섹션별 블록 — 노드명 전체와 역할 표(M7 D3)."""
    m = sections_meta.meta(code)
    lines = [f"## 이 섹션의 노드 ({m.label if m else code}) — 정확히 이 이름들만, 빠짐없이 ({len(names)}개)",
             ", ".join(names)]
    roles = [(pat, lab) for pat, lab in (m.roles if m else ())]
    if roles:
        lines.append("역할: " + " / ".join(f"{pat} → {lab}" for pat, lab in roles))
    return "\n".join(lines)
```

`spec_excerpt(spec_dict, sources)` 를 쓰던 `section_bundle` 안의 호출을 `spec_excerpt(spec_dict, sources, code)` 로 바꾸고(`code` 는 `section_key.split("/")[1]`), `node_list` 인자를 더한다. 노드 블록은 스펙 발췌 **앞**에 넣는다(가장 중요한 제약):

```python
def section_bundle(section_key: str, *, spec_dict: dict, sources: dict, evidence: list[dict], crops: list[dict],
                   feedback: str | None = None, request: str = "", prev_code: str | None = None,
                   critique: list[dict] | None = None, node_list: list[str] | None = None) -> dict:
    segment, code = section_key.split("/")
    ...
    ex = spec_excerpt(spec_dict, sources, code)
    parts: list[dict] = [
        {"type": "text", "text": f"섹션 {section_key} (구간 {segment}, 부재그룹 {code}). 이 섹션의 모든 노드를 만드는 build_section 을 작성하라."},
    ]
    if node_list:
        parts.append({"type": "text", "text": section_block(code, node_list)})
    parts.append({"type": "text", "text": "ModelSpec 발췌 (…기존 문구…):\n" + json.dumps(ex, ensure_ascii=False)})
```

digest 에는 `node_list` 도 넣는다(`h.update(",".join(node_list or []).encode("utf-8"))`).

- [ ] **Step 4: loop.py 에서 노드명 전달**

`run_job` 의 `bundle = agent_context.section_bundle(...)` 호출에 `node_list=node_list` 를 더하고, 루프 시작 전에 한 번 구한다:

```python
    node_list = agent_sections_meta.node_names(ref_dir, segment, code)
```

(import: `from m3d.agent import sections_meta as agent_sections_meta`) — `ref_dir` 검증(`정답 섹션 GLB 없음`) 뒤에 놓는다.

- [ ] **Step 5: 통과 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_agent_context.py tests/test_agent_loop.py tests/test_agent_worker.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd /d/Projects/model3d-studio && git add worker/src/m3d/agent/context.py worker/src/m3d/agent/loop.py worker/tests/test_agent_context.py worker/tests/test_agent_loop.py
git commit -m "feat(agent): 프롬프트 일반화 — 확장 ctx 문서·섹션별 노드명 목록·섹션별 스펙 발췌

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: 자기 렌더 일반화 — 전체 아이소 포함 3뷰

**Files:**
- Modify: `worker/src/m3d/agent/critique.py` (`VIEWS` → `views_for`)
- Test: `worker/tests/test_agent_critique.py`

**Interfaces:**
- Consumes: `sections_meta.meta(code).rep_nodes`, `.label`.
- Produces: `critique.views_for(code) -> list[dict]`; `critique.render_views(agent_glb, spec, code, out_dir) -> list[dict]` (시그니처 유지).

- [ ] **Step 1: 실패하는 테스트 작성**

`worker/tests/test_agent_critique.py` 의 두 테스트를 교체하고 하나 더한다:

```python
def test_dia_views_render_three_pngs_with_captions(dia_glb, tmp_path):
    out = K.render_views(dia_glb, ModelSpec(), "DIA", tmp_path / "crit")
    assert [v["path"].name for v in out] == ["rep_front.png", "rep_side.png", "section_all.png"]
    for v in out:
        assert v["path"].is_file() and v["caption"].startswith("이전 시도")
        with Image.open(v["path"]) as im:
            assert max(im.size) <= 1100
    assert "경간 안쪽" in out[1]["caption"] and "격벽" in out[2]["caption"]


def test_section_all_view_covers_every_node(dia_glb, tmp_path, monkeypatch):
    seen = []
    real = K.render.to_tris
    monkeypatch.setattr(K.render, "to_tris", lambda sel, **kw: seen.append(len(sel)) or real(sel, **kw))
    K.render_views(dia_glb, ModelSpec(), "DIA", tmp_path / "crit")
    assert seen == [1, 1, 26]                     # 대표 노드 2뷰 + 전체 26


def test_views_skip_missing_nodes_and_unknown_section(dia_glb, tmp_path):
    only13 = {"AB1_S5_DIA13": load_named(dia_glb)["AB1_S5_DIA13"]}
    glb = tmp_path / "one.glb"
    Builder(ModelSpec()).export(only13, glb)
    out = K.render_views(glb, ModelSpec(), "DIA", tmp_path / "crit1")
    assert [v["path"].name for v in out] == ["section_all.png"]        # 대표 노드가 없으면 전체 뷰만
    assert K.render_views(dia_glb, ModelSpec(), "BOX", tmp_path / "crit2") == []


def test_views_for_every_agent_section():
    from m3d.agent import sections_meta as M
    for code in M.SECTIONS:
        vs = K.views_for(code)
        assert [v["name"] for v in vs] == ["rep_front", "rep_side", "section_all"]
        assert vs[2]["nodes"] is None and M.SECTIONS[code].label in vs[2]["caption"]
```

- [ ] **Step 2: 실패 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_agent_critique.py -q`
Expected: FAIL — 파일명이 `dia01_front.png` 이고 `views_for` 가 없다.

- [ ] **Step 3: critique.py 수정**

`VIEWS` 상수를 지우고 생성 함수로 바꾼다:

```python
def views_for(code: str) -> list[dict]:
    """섹션 메타 → 3뷰: 대표 노드 정면 아이소·측면(체인선)·섹션 전체 아이소(M7 D5)."""
    m = sections_meta.meta(code)
    if m is None:
        return []
    rep, label = m.rep_nodes, m.label
    return [
        {"name": "rep_front", "nodes": rep, "eye": (0.3, 0.2, 1.0), "size": (8, 6),
         "title": f"{rep[0].replace('AB1_S5_', '')} 정면 아이소(+z 쪽에서, 좌=-x)",
         "caption": f"이전 시도 {label} 대표 부재 정면 — +z(경간 안쪽) 쪽에서 비스듬히 본 판면·개구·보강재(부속은 판면 앞에 상자로 보여야 한다), 화면 좌 = -x"},
        {"name": "rep_side", "nodes": rep, "eye": (1, 0, 0), "size": (5, 10), "chain": "z_p4",
         "title": f"{rep[0].replace('AB1_S5_', '')} 측면(+x 에서, 좌=+z)",
         "caption": f"이전 시도 {label} 대표 부재 측면 — +x 에서, 화면 좌 = +z(경간 안쪽), 점선 = 체인 z_p4; 돌출은 판면에서 왼쪽으로 보여야 한다"},
        {"name": "section_all", "nodes": None, "eye": (0.7, 0.45, 0.85), "size": (10, 6),
         "title": f"{code} 섹션 전체(+x+y+z 에서)",
         "caption": f"이전 시도 {label} 섹션 전체 — +x+y+z 에서 본 배치·개수·좌우·간격. 빠진 부재나 엉뚱한 위치가 있는지 확인하라"},
    ]
```

`render_views` 안에서 `views = VIEWS.get(code, [])` 를 `views = views_for(code)` 로, 노드 선택을 `nodes is None` 처리로 바꾼다:

```python
        sel = list(by_name.values()) if v["nodes"] is None else [by_name[n] for n in v["nodes"] if n in by_name]
```

import 에 `from m3d.agent import sections_meta` 를 더한다.

- [ ] **Step 4: 통과 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_agent_critique.py tests/test_agent_loop.py -q`
Expected: PASS

- [ ] **Step 5: 육안 확인**

정답 섹션 3개로 실제 그림을 만들어 본다(무과금):

```bash
cd /d/Projects/model3d-studio/worker && export PYTHONUTF8=1 && .venv/Scripts/python.exe -c "
from pathlib import Path
from m3d.agent.critique import render_views
from m3d.model.spec import ModelSpec
for c in ('SP04','FRM','WG'):
    out = render_views(Path(f'../data/derived/ab1-p4p5/model/sections/P4P5/{c}.glb'), ModelSpec(), c, Path(f'../data/derived/ab1-p4p5/model/agent/critique-preview/{c}'))
    print(c, [v['path'].name for v in out])"
```

Read 툴로 `critique-preview/FRM/section_all.png` 과 `WG/section_all.png` 을 열어 배치가 알아볼 만한지 확인한다. 알아보기 어려우면 `size` 나 `eye` 를 조정하고 다시 그린다.

- [ ] **Step 6: Commit**

```bash
cd /d/Projects/model3d-studio && git add worker/src/m3d/agent/critique.py worker/tests/test_agent_critique.py
git commit -m "feat(agent): 자기 렌더를 섹션 메타에서 생성 — 대표 부재 2뷰 + 섹션 전체 아이소

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: 일괄 큐 — 워커 `--drain` + 웹 다중 선택

**Files:**
- Modify: `worker/src/m3d/agent/worker.py:86-93` (`serve`), `worker/src/m3d/cli.py:659-666` (`worker`)
- Modify: `web/src/lib/jobs.ts`, `web/src/routes/Model.tsx`
- Test: `worker/tests/test_agent_worker.py`, `web/src/lib/jobs.test.ts`

**Interfaces:**
- Produces: `worker.serve(cfg, *, poll=2.0, once=False, drain=False) -> None`;
  `jobs.jobPayloads(p: { projectId, sectionKeys: string[], request, parentJobId, budgetUsd? }) -> JobInsert[]`;
  `jobs.createJobs(supabase, rows: JobInsert[]) -> Promise<JobRow[]>`.
- Consumes: 기존 `jobPayload`(단일), `createJob`.

- [ ] **Step 1: 실패하는 테스트 작성 (워커)**

`worker/tests/test_agent_worker.py` 끝에 추가:

```python
def test_serve_drain_processes_queue_then_returns(cfg, monkeypatch):
    """일괄 큐: --drain 이면 큐를 비우고 스스로 끝난다(M7 D6)."""
    db = FakeDb(queued=[ROW, ROW])
    monkeypatch.setattr(W.psycopg, "connect", lambda *a, **k: FakeConn(db))
    done = []

    def fake_run_job(cfg, dataset, job, emit):
        done.append(job["section_key"])
        return {"pass": True, "attempts": 1, "cost_usd": 0.1, "build_version": 1, "build_id": "b", "assumptions": [], "questions": []}
    W.serve(cfg, poll=0.0, drain=True, run_job_fn=fake_run_job)
    assert len(done) == 2


def test_serve_once_still_returns_after_one_job(cfg, monkeypatch):
    db = FakeDb(queued=[ROW, ROW])
    monkeypatch.setattr(W.psycopg, "connect", lambda *a, **k: FakeConn(db))
    n = []
    W.serve(cfg, poll=0.0, once=True,
            run_job_fn=lambda *a: n.append(1) or {"pass": True, "attempts": 1, "cost_usd": 0.0})
    assert len(n) == 1
```

- [ ] **Step 2: 실패 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_agent_worker.py -q`
Expected: FAIL — `serve() got an unexpected keyword argument 'drain'`

- [ ] **Step 3: worker.serve·CLI 수정**

`worker.py`:

```python
def serve(cfg: Config, *, poll: float = 2.0, once: bool = False, drain: bool = False, run_job_fn=None) -> None:
    mode = "한 건" if once else ("큐 소진" if drain else "상주")
    print(f"worker 시작 — {mode}, poll {poll}s, 기본 예산 상한 ${cfg.model_agent_budget_usd:.2f} (Ctrl+C 로 종료)")
    while True:
        did = run_once(cfg, run_job_fn=run_job_fn) if run_job_fn is not None else run_once(cfg)
        if did and once:
            return
        if not did:
            if drain or once:
                return
            time.sleep(poll)
```

`cli.py` 의 `worker` 명령에 옵션을 더한다:

```python
    drain: bool = typer.Option(False, "--drain", help="큐가 비면 종료(일괄 실행용)"),
...
    agent_worker.serve(cfg, poll=poll, once=once, drain=drain)
```

- [ ] **Step 4: 통과 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_agent_worker.py -q && .venv/Scripts/m3d.exe worker --help`
Expected: PASS, 도움말에 `--drain` 이 보인다.

- [ ] **Step 5: 실패하는 테스트 작성 (웹)**

`web/src/lib/jobs.test.ts` 의 `describe('jobPayload')` 뒤에 추가:

```ts
describe('jobPayloads (일괄)', () => {
  it('선택 수만큼 행을 만들고 요청·예산을 공통 적용', () => {
    const rows = jobPayloads({ projectId: 'p', sectionKeys: ['P4P5/SP04', 'P4P5/BRG'], request: ' 개구 ', parentJobId: null, budgetUsd: 28.17 });
    expect(rows).toHaveLength(2);
    expect(rows[0]).toEqual({ project_id: 'p', kind: 'model-section', section_key: 'P4P5/SP04', request: '개구', parent_job_id: null, budget_usd: 28.17 });
    expect(rows[1].section_key).toBe('P4P5/BRG');
  });
  it('빈 선택·잘못된 키는 RangeError', () => {
    expect(() => jobPayloads({ projectId: 'p', sectionKeys: [], request: '', parentJobId: null })).toThrow(RangeError);
    expect(() => jobPayloads({ projectId: 'p', sectionKeys: ['dia'], request: '', parentJobId: null })).toThrow(RangeError);
  });
});
```

그리고 `it('M5 는 격벽만', …)` 을 교체:

```ts
  it('M7 은 본체를 뺀 9섹션', () => {
    expect(AGENT_SECTIONS).toEqual(['DIA', 'SP04', 'HST', 'SLAB', 'BRG', 'FRM', 'RIB', 'CS', 'WG']);
    expect(AGENT_SECTIONS).not.toContain('BOX');
  });
```

import 줄에 `jobPayloads` 를 더한다.

- [ ] **Step 6: 실패 확인**

Run: `cd /d/Projects/model3d-studio/web && npm test -- --run src/lib/jobs.test.ts`
Expected: FAIL — `jobPayloads is not a function`, `AGENT_SECTIONS` 가 `['DIA']`

- [ ] **Step 7: jobs.ts·Model.tsx 수정**

`jobs.ts`:

```ts
export const AGENT_SECTIONS = ['DIA', 'SP04', 'HST', 'SLAB', 'BRG', 'FRM', 'RIB', 'CS', 'WG'];   // M7: 본체(BOX) 제외

export function jobPayloads(p: { projectId: string; sectionKeys: string[]; request: string; parentJobId: string | null; budgetUsd?: number }): JobInsert[] {
  if (p.sectionKeys.length === 0) throw new RangeError('섹션을 하나 이상 고르세요');
  return p.sectionKeys.map((sectionKey) => jobPayload({ ...p, sectionKey }));
}

export async function createJobs(supabase: Client, rows: JobInsert[]): Promise<JobRow[]> {
  const { data, error } = await supabase.from('jobs').insert(rows).select();
  if (error) throw new Error(error.message);
  return (data ?? []) as JobRow[];
}
```

`Model.tsx`:
- 상태 `const [picked, setPicked] = useState<Set<string>>(new Set());`
- 섹션 행의 `LLM 으로 만들기` 버튼 옆(에이전트 대상 섹션만)에 선택 스위치를 둔다:

```tsx
                    {AGENT_SECTIONS.includes(s.code) && (
                      <Checkbox size="xs" color="violet" checked={picked.has(s.section_key)} aria-label={`${s.code} 일괄 선택`}
                        id={`pick-${s.code}`}
                        onChange={(e) => setPicked((prev) => {
                          const next = new Set(prev);
                          if (e.currentTarget.checked) next.add(s.section_key); else next.delete(s.section_key);
                          return next;
                        })} />
                    )}
```

- 섹션 목록 헤더에 버튼:

```tsx
              <Button size="compact-xs" color="violet" variant="light" id="create-jobs-button" disabled={picked.size === 0}
                onClick={() => { setAskSection(null); setAskRequest(''); setBatchOpen(true); }}>
                선택 {picked.size}개 LLM 모델링
              </Button>
```

- 모달을 단일/일괄 공용으로: `const modalOpen = askSection !== null || batchOpen;` 제목은 `askSection ? … : '선택 ' + picked.size + '개 — LLM 으로 만들기'`. 잡 생성 버튼:

```tsx
              onClick={() => {
                if (askSection) void submitJob(askSection, askRequest, null, askBudget);
                else void submitBatch([...picked], askRequest, askBudget);
                setAskSection(null); setBatchOpen(false);
              }}
```

- `submitBatch`:

```tsx
  async function submitBatch(sectionKeys: string[], request: string, budgetUsd: number) {
    if (supabase === null || !project) return;
    try {
      const rows = await createJobs(supabase, jobPayloads({ projectId: project.id, sectionKeys, request, parentJobId: null, budgetUsd }));
      setJobs((prev) => [...rows, ...prev]);
      setOpenJob(rows[0]?.id ?? null);
      setPicked(new Set());
    } catch (e) {
      setError((e as Error).message);
    }
  }
```

- [ ] **Step 8: 통과 확인**

Run: `cd /d/Projects/model3d-studio/web && npm test -- --run && npm run typecheck`
Expected: vitest 전건 PASS, tsc 오류 0

- [ ] **Step 9: Commit**

```bash
cd /d/Projects/model3d-studio && git add worker/src/m3d/agent/worker.py worker/src/m3d/cli.py worker/tests/test_agent_worker.py web/src/lib/jobs.ts web/src/lib/jobs.test.ts web/src/routes/Model.tsx
git commit -m "feat(web,worker): 섹션 다중 선택 일괄 잡 생성 + worker --drain 순차 처리

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: 전집 결합 빌드 `m3d agent-assemble`

**Files:**
- Create: `worker/src/m3d/model/assemble_agent.py`
- Modify: `worker/src/m3d/cli.py` (명령 추가)
- Test: `worker/tests/test_model_assemble_agent.py` (신규)

**Interfaces:**
- Consumes: `m3d.model.io.model_dir(cfg, dataset)`, `write_build_json`; `m3d.model.builder.Builder(spec).export/export_sections`; `m3d.model.selfcheck.run(named, b, pilot=False)`; `m3d.model.measure.run(glb, spec)`; `m3d.model.render.run_render(glb, out_dir, spec, pilot=False)`; `m3d.model.publish.run_publish_model(cfg, dataset, *, out_dir, kind, force)`; `m3d.agent.score.load_named`.
- Produces: `assemble_agent.pick_sources(cfg, dataset, *, ref_dir, segment) -> dict[str, dict]` (code → `{"glb": Path, "source": "agent"|"builder", "job_id": str|None, "pass": bool}`);
  `assemble_agent.run_assemble(cfg, dataset, *, out_dir=None, ref_dir=None, publish=True, do_render=True) -> dict`.

- [ ] **Step 1: 실패하는 테스트 작성**

`worker/tests/test_model_assemble_agent.py` (신규):

```python
"""전집 결합 (M7 D8) — 섹션마다 통과한 에이전트 산출을 골라 결합 빌드를 만든다. LLM·업로드 없음."""

import json

import pytest

from m3d.config import load_config
from m3d.model import assemble_agent as A
from m3d.model import sections as X
from m3d.model.builder import Builder
from m3d.model.spec import ModelSpec
import dataclasses


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


def _job(cfg, job_id, code, ref_dir, passed):
    """에이전트 잡 산출 흉내 — 그 섹션 GLB 와 score.json 만 있으면 된다."""
    d = cfg.derived_dir / "ds" / "model" / "agent" / job_id
    (d / "agent").mkdir(parents=True)
    (d / "sections" / "P4P5").mkdir(parents=True)
    src = ref_dir / "sections" / "P4P5" / f"{code}.glb"
    (d / "sections" / "P4P5" / f"{code}.glb").write_bytes(src.read_bytes())
    (d / "agent" / "score.json").write_text(json.dumps({"summary": {"pass": passed, "bbox_dev_max_m": 0.0}}), encoding="utf-8")
    (d / "build.json").write_text(json.dumps({"kind": "agent", "segment": "P4P5",
                                              "sections": [{"code": code, "source": "agent"}]}), encoding="utf-8")
    return d


def test_pick_sources_prefers_passing_agent_output(cfg, ref_dir):
    _job(cfg, "j-fail", "SP04", ref_dir, passed=False)
    _job(cfg, "j-pass", "SP04", ref_dir, passed=True)
    _job(cfg, "j-brg", "BRG", ref_dir, passed=False)
    picked = A.pick_sources(cfg, "ds", ref_dir=ref_dir, segment="P4P5")
    assert set(picked) == set(X.CODES)
    assert picked["SP04"]["source"] == "agent" and picked["SP04"]["job_id"] == "j-pass" and picked["SP04"]["pass"] is True
    assert picked["BRG"]["source"] == "builder"          # 통과분이 없으면 정답 빌더
    assert picked["BOX"]["source"] == "builder"


def test_run_assemble_writes_build_and_verification(cfg, ref_dir):
    _job(cfg, "j-pass", "SP04", ref_dir, passed=True)
    out = cfg.derived_dir / "ds" / "model" / "agent-all"
    r = A.run_assemble(cfg, "ds", out_dir=out, ref_dir=ref_dir, publish=False, do_render=False)
    assert r["sections"]["SP04"]["source"] == "agent" and r["selfcheck"]["fail"] == 0 and r["measure"]["FAIL"] == 0
    build = json.loads((out / "build.json").read_text(encoding="utf-8"))
    assert build["kind"] == "agent"
    assert {s["code"]: s["source"] for s in build["sections"]}["SP04"] == "agent"
    assert sum(1 for s in build["sections"] if s["source"] == "builder") == 9
    assert (out / "AB1_P4P5.glb").is_file() and (out / "selfcheck.json").is_file() and (out / "measure.json").is_file()
```

- [ ] **Step 2: 실패 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_model_assemble_agent.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'm3d.model.assemble_agent'`

- [ ] **Step 3: 모듈 작성**

`worker/src/m3d/model/assemble_agent.py`:

```python
"""전집 결합 (M7 D8) — 섹션마다 가장 좋은 에이전트 산출을 골라 하나의 결합 빌드로 만든다.

LLM 호출이 없는 결정론 작업이다. 통과분이 없는 섹션은 정답 빌더 산출로 채우고 build.json 에 출처를 남긴다.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from m3d.agent import score as agent_score
from m3d.config import Config
from m3d.model import io as model_io
from m3d.model import measure, publish, render, sections, selfcheck
from m3d.model.builder import Builder
from m3d.model.spec import ModelSpec
from m3d.samples.manifest import sha256_file


def _agent_jobs(cfg: Config, dataset: str):
    """에이전트 잡 디렉터리 → (job_id, code, glb, pass) — 최신 순."""
    root = model_io.model_dir(cfg, dataset) / "agent"
    if not root.is_dir():
        return []
    out = []
    for d in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime):
        score = d / "agent" / "score.json"
        build = d / "build.json"
        if not score.is_file() or not build.is_file():
            continue
        try:
            summ = json.loads(score.read_text(encoding="utf-8")).get("summary", {})
            meta = json.loads(build.read_text(encoding="utf-8"))
        except ValueError:
            continue
        code = next((s["code"] for s in meta.get("sections", []) if s.get("source") == "agent"), None)
        if code is None:
            continue
        glb = d / "sections" / meta.get("segment", "P4P5") / f"{code}.glb"
        if glb.is_file():
            out.append({"job_id": d.name, "code": code, "glb": glb, "pass": bool(summ.get("pass"))})
    return out


def pick_sources(cfg: Config, dataset: str, *, ref_dir: Path, segment: str) -> dict[str, dict]:
    """섹션마다 쓸 GLB — 통과한 에이전트 산출 우선(최신), 없으면 정답 빌더."""
    ref_dir = Path(ref_dir)
    picked = {c: {"glb": ref_dir / "sections" / segment / f"{c}.glb", "source": "builder", "job_id": None, "pass": False}
              for c in sections.CODES}
    for job in _agent_jobs(cfg, dataset):
        if not job["pass"]:
            continue
        picked[job["code"]] = {"glb": job["glb"], "source": "agent", "job_id": job["job_id"], "pass": True}
    return picked


def run_assemble(cfg: Config, dataset: str, *, out_dir=None, ref_dir=None, publish: bool = True,
                 do_render: bool = True) -> dict:
    """결합 빌드 디렉터리를 만들고(선택) 업로드한다."""
    raw = model_io.load_modelspec_raw(cfg, dataset)
    spec = ModelSpec.model_validate(raw["spec"])
    segment = spec.coord.segment
    ref_dir = Path(ref_dir) if ref_dir else model_io.model_dir(cfg, dataset)
    out_dir = Path(out_dir) if out_dir else model_io.model_dir(cfg, dataset) / "agent-all"
    sec_dir = out_dir / "sections" / segment
    sec_dir.mkdir(parents=True, exist_ok=True)
    picked = pick_sources(cfg, dataset, ref_dir=ref_dir, segment=segment)
    b = Builder(spec)
    meta, named_all, sec_results = [], {}, {}
    for c in sections.CODES:
        dst = sec_dir / f"{c}.glb"
        shutil.copyfile(picked[c]["glb"], dst)
        named = agent_score.load_named(dst)
        named_all.update(named)
        rs = selfcheck.run(named, b, section=c)
        sec_results[f"{segment}/{c}"] = rs
        meta.append({"key": f"{segment}/{c}", "code": c, "label": sections.LABELS[c], "file": f"sections/{segment}/{c}.glb",
                     "meshes": len(named), "triangles": int(sum(len(m.faces) for m in named.values())),
                     "bytes": dst.stat().st_size, "sha256": sha256_file(dst), "source": picked[c]["source"],
                     "job_id": picked[c]["job_id"], "selfcheck": {"pass": rs["pass"], "fail": rs["fail"]}})
    glb = out_dir / "AB1_P4P5.glb"
    b.export(named_all, glb)
    r_all = selfcheck.run(named_all, b, pilot=False)
    meas = measure.run(glb, spec)
    (out_dir / "selfcheck.json").write_text(json.dumps(r_all, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "selfcheck_sections.json").write_text(json.dumps(sec_results, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "measure.json").write_text(json.dumps(meas, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.copyfile(model_io.model_dir(cfg, dataset) / "modelspec.json", out_dir / "modelspec.json")
    if do_render:
        render.run_render(glb, out_dir / "renders", spec, pilot=False)
    else:
        (out_dir / "renders").mkdir(exist_ok=True)
        (out_dir / "renders" / "views.json").write_text("{}", encoding="utf-8")
    model_io.write_build_json(out_dir, {
        "kind": "agent", "segment": segment,
        "assembled": {"file": "AB1_P4P5.glb", "meshes": r_all["meshes"], "triangles": r_all["triangles"],
                      "bytes": glb.stat().st_size, "sha256": sha256_file(glb)},
        "sections": meta, "selfcheck": {"pass": r_all["pass"], "fail": r_all["fail"], "skipped": r_all["skipped"]},
        "git_sha": None})
    result = {"out_dir": str(out_dir), "sections": {m["code"]: {"source": m["source"], "job_id": m["job_id"]} for m in meta},
              "agent_sections": sum(1 for m in meta if m["source"] == "agent"),
              "selfcheck": {"pass": r_all["pass"], "fail": r_all["fail"]},
              "measure": {"PASS": meas["집계"]["PASS"], "FAIL": meas["집계"]["FAIL"], "INFO": meas["집계"]["INFO"]}}
    if publish:
        result["publish"] = _publish(cfg, dataset, out_dir)
    return result


def _publish(cfg: Config, dataset: str, out_dir: Path) -> dict:
    return publish.run_publish_model(cfg, dataset, out_dir=out_dir, kind="agent", force=True)
```

- [ ] **Step 4: CLI 명령 추가**

`worker/src/m3d/cli.py` 의 `worker` 명령 앞에 추가:

```python
@app.command("agent-assemble")
def agent_assemble(
    dataset: str = typer.Option("ab1-p4p5", "--dataset"),
    no_publish: bool = typer.Option(False, "--no-publish", help="업로드 없이 로컬 산출만"),
) -> None:
    """[12] 전집 결합 — 섹션마다 통과한 에이전트 산출을 모아 결합 빌드 생성·업로드 (M7 §3.7). 무과금."""
    from m3d.model import assemble_agent
    cfg = load_config()
    r = assemble_agent.run_assemble(cfg, dataset, publish=not no_publish)
    typer.echo(f"에이전트 섹션 {r['agent_sections']}/10 · self-check {r['selfcheck']['pass']}/{r['selfcheck']['fail']} · "
               f"재실측 {r['measure']['PASS']}/{r['measure']['FAIL']}")
    for code, s in r["sections"].items():
        typer.echo(f"  {code:5s} {s['source']}{'' if s['job_id'] is None else ' ' + s['job_id'][:8]}")
    if "publish" in r:
        typer.echo(f"업로드 b{r['publish']['version']} ({r['publish']['uploaded']} 파일)")
    raise typer.Exit(code=1 if r["selfcheck"]["fail"] or r["measure"]["FAIL"] else 0)
```

- [ ] **Step 5: 통과 확인**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest tests/test_model_assemble_agent.py -q && .venv/Scripts/m3d.exe agent-assemble --help`
Expected: PASS, 도움말이 보인다.

- [ ] **Step 6: Commit**

```bash
cd /d/Projects/model3d-studio && git add worker/src/m3d/model/assemble_agent.py worker/src/m3d/cli.py worker/tests/test_model_assemble_agent.py
git commit -m "feat(model): m3d agent-assemble — 통과한 에이전트 섹션을 모은 전집 결합 빌드

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: 실증(≤ $25)·전집 결합·판정서·README·통합

**Files:**
- Create: `data/derived/ab1-p4p5/model/acceptance-m7.md` (gitignored)
- Modify: `README.md`, 메모리 `C:\Users\parkj\.claude\projects\D--Projects-model3d-studio\memory\`

- [ ] **Step 1: 전건 테스트**

Run: `cd /d/Projects/model3d-studio/worker && .venv/Scripts/python.exe -m pytest -q` 그리고 `cd /d/Projects/model3d-studio/web && npm test -- --run && npm run typecheck`
Expected: pytest 391 → 410 안팎 전건 PASS, vitest 21 → 24 안팎, tsc 0. 실패가 있으면 여기서 멈추고 고친다.

- [ ] **Step 2: 프롬프트 무과금 점검**

```bash
cd /d/Projects/model3d-studio/worker && export PYTHONUTF8=1 && .venv/Scripts/python.exe -c "
from m3d.agent import context as C, sections_meta as M
from m3d.model import io as model_io
from m3d.config import load_config
cfg = load_config(); raw = model_io.load_modelspec_raw(cfg, 'ab1-p4p5')
ref = model_io.model_dir(cfg, 'ab1-p4p5')
for code in ('SP04','HST','BRG','WG'):
    names = M.node_names(ref, 'P4P5', code)
    b = C.section_bundle(f'P4P5/{code}', spec_dict=raw['spec'], sources=raw.get('sources', {}), evidence=[], crops=[], node_list=names)
    text = chr(10).join(p['text'] for p in b['messages'][0]['content'] if p['type']=='text')
    print(code, 'nodes', len(names), 'system', len(b['system']), 'user', len(text))"
```

시스템 프롬프트에 새 ctx 항목이, 사용자 메시지에 노드명·doc 이 보이는지 눈으로 확인한다. 사용자 메시지가 30,000자를 넘으면(WG·FRM) 스펙 발췌가 과한지 살펴 `spec_keys` 를 줄인다.

- [ ] **Step 3: 배치 1 — SP04·HST·SLAB·BRG**

웹(`/p/ab1-p4p5/model`, 로그인 세션)에서 네 섹션을 선택하고 "선택 4개 LLM 모델링" → 예산 28.17 → 잡 생성. 워커:

```bash
cd /d/Projects/model3d-studio/worker && export PYTHONUTF8=1 && .venv/Scripts/m3d.exe worker --poll 2 --drain
```

잡마다 `model/agent/<job_id>/agent/{score.json, attempts.json, prompt.md, critique*/}` 를 읽고 결과를 표로 기록한다. 실패 원인이 정보 부족이면 그 섹션의 `description` 이나 계약 문구를 고치고(테스트·커밋) 재요청한다(섹션당 잡 ≤ 3).

- [ ] **Step 4: 배치 2 — FRM·RIB·CS·WG**

같은 방식. 누적 지출을 배치마다 확인한다:

```bash
cd /d/Projects/model3d-studio/worker && export PYTHONUTF8=1 && .venv/Scripts/python.exe -c "
from m3d.agent import loop as L
from m3d.config import load_config
print('stage spent $%.2f' % L.spent_usd(load_config(), 'ab1-p4p5'))"
```

- [ ] **Step 5: 전집 결합**

```bash
cd /d/Projects/model3d-studio/worker && export PYTHONUTF8=1 && .venv/Scripts/m3d.exe agent-assemble
```

self-check·재실측 fail 0 을 확인하고, 웹 뷰어에서 새 빌드를 열어 섹션 목록의 LLM 배지 수와 렌더를 확인한다(DOM 텍스트로 읽어도 된다).

- [ ] **Step 6: 판정서**

`data/derived/ab1-p4p5/model/acceptance-m7.md`: 기준 ①~⑤ 결과·근거, 섹션별 표(잡·시도·비용·최종 bbox·PASS 여부·실패 원인), 공개 정보 범위(노드명 목록·ctx 확장·필드 doc — 정답 렌더·코드는 아님), 비용 원장, 화면 확인, 교훈·다음 후보.

- [ ] **Step 7: README·메모리**

README "## LLM 모델링 (M5)" 절에 "### M7 — 8섹션 확산" 소절: 무엇을 바꿨나(메타 표·ctx·doc·전체 아이소·일괄 큐·전집 결합), 실증 결과 한 줄, 사용법(`선택 N개 LLM 모델링` → `m3d worker --poll --drain` → `m3d agent-assemble`). 메모리에 M7 파일을 쓰고 `MEMORY.md` 에 한 줄.

- [ ] **Step 8: 통합**

```bash
cd /d/Projects/model3d-studio && git add README.md && git commit -m "docs: README M7 8섹션 확산 절

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

그다음 superpowers:finishing-a-development-branch — 전건 테스트 → 병합 방식은 사용자 선택.
