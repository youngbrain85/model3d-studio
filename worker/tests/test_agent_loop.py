"""잡 루프 — 가짜 LLM/채점/업로드로 시도·피드백·예산·산출 디렉터리를 검증한다 (M5 D7·D8·D9). 실호출 없음."""

import dataclasses
import json
import textwrap

import pytest

from m3d.agent import loop as L
from m3d.agent.schema import AgentOut
from m3d.config import load_config
from m3d.model import sections as X
from m3d.model.builder import Builder
from m3d.model.spec import ModelSpec

GOOD = textwrap.dedent('''
    from m3d.model.geom import box_prism, paint
    def build_section(spec, ctx):
        d = spec["diaphragm"]
        out = {}
        for k in range(d["n_cell"] + 1):
            zc = min(max(ctx.z_p4 + k * d["spacing"], ctx.z_p4 + 0.02), ctx.z_p5 - 0.02)
            out["AB1_S5_DIA%02d" % (k + 1)] = paint(box_prism(-2.0, 2.0, ctx.y_web_bot(zc), ctx.y_web_top(zc), zc - 0.005, zc + 0.005), ctx.COL_STEEL)
        return out
''')
BAD = "def build_section(spec, ctx):\n    return 1 / 0\n"


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


def _job(**over):
    return {"id": "job-1", "section_key": "P4P5/DIA", "request": "", "parent_job_id": None, "budget_usd": 5.0, **over}


def _fake_llm(codes):
    calls = []

    def llm(cfg, dataset, bundle, extra):
        calls.append({"attempt": extra["attempt"], "n_images": bundle["n_images"],
                      "text": "\n".join(p["text"] for p in bundle["messages"][0]["content"] if p["type"] == "text")})
        return AgentOut(code=codes[len(calls) - 1], assumptions=["가정1"], questions=["질문1"]), {"cost_usd": 0.1}
    return llm, calls


def _fake_scorer(passes):
    seen = []

    def scorer(code, glb, spec, ref, *, work_dir):
        seen.append(glb)
        ok = passes[len(seen) - 1]
        return {"pass": ok, "sanity": {"pass": 3, "fail": 0, "checks": []},
                "reference": {"only_ours": [], "only_ref": [] if ok else ["AB1_S5_DIA26"], "common": 25,
                              "bbox_dev_max_m": 0.0 if ok else 0.02, "bbox_dev_over_1mm": 0, "faces_equal": ok,
                              "worst": [], "worst_detail": []},
                "section_selfcheck": {"pass": 5, "fail": 0, "failed": []}, "assembled_selfcheck": {"pass": 24, "fail": 0, "failed": []},
                "measure": {"PASS": 47, "FAIL": 0, "INFO": 2, "section_fail": 0 if ok else 1,
                            "failed": [] if ok else ["격벽 판 z 위치 26 — 기대 x / 실측 y (허용 0.005)"]},
                "assembled_glb": str(work_dir / "assembled.glb")}
    return scorer, seen


def _fake_publisher(record):
    def publisher(cfg, dataset, *, out_dir, kind, force):
        record.update({"out_dir": out_dir, "kind": kind, "force": force})
        return {"version": 7, "build_id": "b-7", "files": 20, "uploaded": 20, "skipped": False, "failures": []}
    return publisher


def test_loop_retries_with_feedback_then_passes_and_builds_agent_dir(cfg, ref_dir, monkeypatch):
    llm, calls = _fake_llm([BAD, GOOD, GOOD])
    scorer, seen = _fake_scorer([False, True])
    pub = {}
    events = []
    monkeypatch.setattr(L, "spent_usd", lambda cfg, ds, stage=L.STAGE: 0.0)
    r = L.run_job(cfg, "ds", _job(), lambda lv, m: events.append((lv, m)), llm=llm, scorer=scorer, publisher=_fake_publisher(pub),
                  evidence=[], crops=[], ref_dir=ref_dir, do_render=False)
    assert r["pass"] is True and r["attempts"] == 3 and r["build_version"] == 7 and r["build_id"] == "b-7"
    assert abs(r["cost_usd"] - 0.3) < 1e-9 and r["assumptions"] == ["가정1"] and r["questions"] == ["질문1"]
    assert "AB1_S5_DIA26" in calls[0]["text"] and "정확히 이 이름들만" in calls[0]["text"]   # 노드명 목록이 첫 호출부터
    assert "실행 오류" in calls[1]["text"] and "ZeroDivisionError" in calls[1]["text"]          # 1차 실행 오류 → 2차 피드백
    assert "AB1_S5_DIA26" in calls[2]["text"] and "이전 시도 코드" in calls[2]["text"]           # 2차 채점 실패 → 3차 피드백
    # 실행 오류 뒤엔 렌더 없음. 채점 실패 뒤엔 자기 렌더 — 여기 가짜 코드의 격벽은 두께 10mm 민판이라
    # 측면 뷰가 400:1 로 납작해 생략된다(M7 _too_flat) → 대표 정면 + 섹션 전체 2장.
    assert calls[1]["n_images"] == 0 and calls[2]["n_images"] == 2
    assert "이전 시도 결과 렌더(자기검토용)" in calls[2]["text"] and "렌더: 이전 시도 격벽 섹션 전체" in calls[2]["text"]
    crit_dir = cfg.derived_dir / "ds" / "model" / "agent" / "job-1" / "agent" / "critique2"
    assert sorted(p.name for p in crit_dir.glob("*.png")) == ["rep_front.png", "section_all.png"]
    out_dir = pub["out_dir"]
    assert pub["kind"] == "agent" and pub["force"] is True
    assert sorted(p.name for p in (out_dir / "sections" / "P4P5").glob("*.glb")) == sorted(f"{c}.glb" for c in X.CODES)
    build = json.loads((out_dir / "build.json").read_text(encoding="utf-8"))
    assert build["kind"] == "agent" and {s["code"]: s["source"] for s in build["sections"]}["DIA"] == "agent"
    assert sum(1 for s in build["sections"] if s["source"] == "builder") == 9
    agent = out_dir / "agent"
    assert (agent / "code.py").read_text(encoding="utf-8") == GOOD and (agent / "prompt.md").is_file()
    attempts = json.loads((agent / "attempts.json").read_text(encoding="utf-8"))
    assert [a["ok"] for a in attempts] == [False, True, True] and [a.get("pass") for a in attempts] == [None, False, True]
    assert "critique" not in attempts[0] and attempts[1]["critique"] == ["rep_front.png", "section_all.png"] and "critique" not in attempts[2]
    assert json.loads((agent / "score.json").read_text(encoding="utf-8"))["summary"]["attempts"] == 3
    assert (out_dir / "AB1_P4P5.glb").is_file() and (out_dir / "selfcheck_sections.json").is_file() and (out_dir / "measure.json").is_file()
    assert [lv for lv, _ in events].count("warn") >= 1 and events[-1][0] == "info"


def test_loop_stops_on_budget_before_calling_llm(cfg, ref_dir, monkeypatch):
    llm, calls = _fake_llm([GOOD])
    monkeypatch.setattr(L, "spent_usd", lambda cfg, ds, stage=L.STAGE: 4.9)
    r = L.run_job(cfg, "ds", _job(budget_usd=5.0), lambda lv, m: None, llm=llm, evidence=[], crops=[], ref_dir=ref_dir, do_render=False)
    assert r["reason"] == "budget" and r["pass"] is False and calls == []


def test_loop_reports_no_run_when_every_attempt_fails(cfg, ref_dir, monkeypatch):
    llm, calls = _fake_llm([BAD] * 4)
    monkeypatch.setattr(L, "spent_usd", lambda cfg, ds, stage=L.STAGE: 0.0)
    r = L.run_job(cfg, "ds", _job(), lambda lv, m: None, llm=llm, evidence=[], crops=[], ref_dir=ref_dir, do_render=False)
    assert r["reason"] == "no_run" and r["attempts"] == 4 and len(calls) == 4


def test_loop_uses_parent_code_for_revision(cfg, ref_dir, monkeypatch):
    parent = cfg.derived_dir / "ds" / "model" / "agent" / "job-0" / "agent"
    parent.mkdir(parents=True)
    (parent / "code.py").write_text(GOOD, encoding="utf-8")
    llm, calls = _fake_llm([GOOD])
    scorer, _ = _fake_scorer([True])
    monkeypatch.setattr(L, "spent_usd", lambda cfg, ds, stage=L.STAGE: 0.0)
    r = L.run_job(cfg, "ds", _job(id="job-1", parent_job_id="job-0", request="개구를 1.4×1.4 로"), lambda lv, m: None, llm=llm, scorer=scorer,
                  publisher=_fake_publisher({}), evidence=[], crops=[], ref_dir=ref_dir, do_render=False)
    assert r["pass"] is True and "이전 시도 코드" in calls[0]["text"] and "개구를 1.4×1.4 로" in calls[0]["text"]


def test_spent_usd_sums_only_stage_rows(cfg):
    p = cfg.derived_dir / "ds" / "usage.jsonl"
    p.write_text('{"stage": "read", "cost_usd": 1.0}\n{"stage": "model-agent", "cost_usd": 0.25}\n{"stage": "model-agent", "cost_usd": 0.5, "cached": true}\n', encoding="utf-8")
    assert abs(L.spent_usd(cfg, "ds") - 0.25) < 1e-9


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


def test_loop_treats_contract_violation_as_attempt_not_job_death(cfg, ref_dir, monkeypatch):
    """LLM 출력이 계약을 어기면 그 시도만 실패로 적고 피드백과 함께 다시 부른다(M7 배치 1 BRG)."""
    calls = []

    def llm(cfg, dataset, bundle, extra):
        calls.append("\n".join(p["text"] for p in bundle["messages"][0]["content"] if p["type"] == "text"))
        if len(calls) == 1:
            raise ValueError("코드 계약 위반: import 금지: m3d.model")
        return AgentOut(code=GOOD, assumptions=[], questions=[]), {"cost_usd": 0.1}

    scorer, _ = _fake_scorer([True])
    monkeypatch.setattr(L, "spent_usd", lambda cfg, ds, stage=L.STAGE: 0.0)
    r = L.run_job(cfg, "ds", _job(), lambda lv, m: None, llm=llm, scorer=scorer, publisher=_fake_publisher({}),
                  evidence=[], crops=[], ref_dir=ref_dir, do_render=False)
    assert r["pass"] is True and r["attempts"] == 2
    assert "코드 계약 위반" in calls[1] and "import 금지" in calls[1]
