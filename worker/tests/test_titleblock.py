"""표제란 ATTRIB 추출 — DI_DRWNO 보유 INSERT 가 곧 표제란이다."""

from pathlib import Path

import ezdxf
import pytest

from m3d.catalog.titleblock import TitleBlock, extract_titleblocks

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples" / "ab1-p4p5" / "dxf"


def _doc_with_titleblocks(*specs, block_name="CXBLKA1-구조"):
    """specs: (insert_xy, {tag: value}) — INSERT + ATTRIB 합성."""
    doc = ezdxf.new("R2018")
    doc.blocks.new(block_name)
    msp = doc.modelspace()
    for xy, tags in specs:
        ins = msp.add_blockref(block_name, xy)
        for tag, value in tags.items():
            ins.add_attrib(tag, value, insert=xy)
    return doc


def test_extracts_di_attribs():
    doc = _doc_with_titleblocks(
        ((0, 0), {"DI_DRWNO": "C0050304-030", "DI_TITLE": "강상형일반도(5)",
                  "DI_SUBTITLE": "(접속1교)", "DA_HSCALE": "H=1:100"}),
    )
    blocks = extract_titleblocks(doc)
    assert blocks == [TitleBlock("C0050304-030", "강상형일반도(5)", "(접속1교)", "H=1:100")]


def test_insert_without_di_drwno_ignored():
    doc = _doc_with_titleblocks(
        ((0, 0), {"NO": "P4"}),                       # 교각 번호 블록 — 표제란 아님
        ((10, 10), {"DI_DRWNO": "C0000000-001"}),
    )
    blocks = extract_titleblocks(doc)
    assert len(blocks) == 1
    assert blocks[0].drawing_no == "C0000000-001"
    assert blocks[0].title == ""                       # 태그 없으면 빈 문자열


def test_page_order_left_to_right():
    doc = _doc_with_titleblocks(
        ((500000, 0), {"DI_DRWNO": "P2"}),
        ((0, 0), {"DI_DRWNO": "P1"}),
    )
    assert [b.drawing_no for b in extract_titleblocks(doc)] == ["P1", "P2"]


@pytest.mark.skipif(not SAMPLES.is_dir(), reason="샘플 세트 없음")
def test_real_normal_sheet():
    doc = ezdxf.readfile(SAMPLES / "C0050304-030.dxf")
    blocks = extract_titleblocks(doc)
    assert len(blocks) == 1
    assert blocks[0].drawing_no == "C0050304-030"
    assert "강상형일반도" in blocks[0].title.replace(" ", "").replace("　", "")


@pytest.mark.skipif(not SAMPLES.is_dir(), reason="샘플 세트 없음")
def test_real_frameless_sheet_has_no_titleblock():
    doc = ezdxf.readfile(SAMPLES / "C0050302-001.dxf")
    assert extract_titleblocks(doc) == []
