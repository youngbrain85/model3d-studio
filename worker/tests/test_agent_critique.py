"""자기 렌더 (M6 D4 → M7 D5) — 에이전트 섹션 GLB 만으로 뷰 표대로 PNG 를 만든다. 정답 렌더가 아니다."""

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
    assert [v["path"].name for v in out] == ["rep_front.png", "rep_side.png", "section_all.png"]
    for v in out:
        assert v["path"].is_file() and v["caption"].startswith("이전 시도")
        with Image.open(v["path"]) as im:
            assert max(im.size) <= 1100
    assert "경간 안쪽" in out[1]["caption"] and "격벽" in out[2]["caption"]


def test_section_all_view_covers_every_node(dia_glb, tmp_path, monkeypatch):
    seen = []
    real = K.render.to_tris
    monkeypatch.setattr(K.render, "to_tris", lambda sel, **kw: (seen.append(len(sel)), real(sel, **kw))[1])
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
