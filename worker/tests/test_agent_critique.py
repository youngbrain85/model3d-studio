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
