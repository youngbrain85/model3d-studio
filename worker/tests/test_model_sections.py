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
