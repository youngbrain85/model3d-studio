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
