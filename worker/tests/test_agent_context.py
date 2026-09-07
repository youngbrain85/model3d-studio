"""프롬프트 묶음 — 규칙·툴킷·ctx·계약·스펙 발췌(출처)·크롭·피드백·요청 (M5 D3). LLM 호출 없음."""

import json

from PIL import Image

from m3d.agent import context as C
from m3d.agent import crops as K
from m3d.model.spec import Bearing, Diaphragm, ModelSpec
from m3d.reading.sheet import PageRef

SOURCES = {"coord.z_p4": "ssot:project.coord_system.datums", "diaphragm.spacing": "ssot:C01/다이아프램 간격",
           "diaphragm.support_t": "default:SPEC_v2 §2", "box.h_pier": "ssot:C01/측면도 전체 형고 4,000"}


def _page(tmp_path, ord_, w=2000, h=1400):
    png = tmp_path / "png" / f"{ord_}_D-1_p1.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), "white").save(png)
    text = tmp_path / "text" / f"{ord_}_D-1_p1.json"
    text.parent.mkdir(parents=True, exist_ok=True)
    text.write_text(json.dumps({"paper_mm": [1189.0, 841.0], "rows": []}), encoding="utf-8")
    return PageRef(ord=ord_, drawing_no="D-1", page_no=1, region=ord_[0], png=png, text=text)


def test_section_crops_groups_by_page_and_limits(tmp_path):
    pages = {("C13", 1): _page(tmp_path, "C13"), ("C16", 1): _page(tmp_path, "C16")}
    ev = [{"ord": "C13", "page_no": 1, "item": "CL 다이아프램 규격", "value": "DIAP 10x4500x3739", "unit": "mm", "status": "확정", "mm_bbox": [100, 100, 160, 120]},
          {"ord": "C13", "page_no": 1, "item": "CU3 다이아프램 판 규격", "value": "DIAP 10x4500x2400", "unit": "mm", "status": "확정", "mm_bbox": [400, 300, 460, 320]},
          {"ord": "C16", "page_no": 1, "item": "CL7", "value": "DIAP 10x4500x2881", "unit": "mm", "status": "확정", "mm_bbox": [10, 10, 30, 20]},
          {"ord": "C99", "page_no": 1, "item": "없는 시트", "value": "x", "unit": None, "status": "추정", "mm_bbox": [0, 0, 1, 1]},
          {"ord": "C16", "page_no": 1, "item": "용지 밖", "value": "x", "unit": None, "status": "추정", "mm_bbox": [5000, 5000, 5001, 5001]}]
    out = K.section_crops(None, "ds", ev, tmp_path / "crops", pages=pages)
    assert [(c["ord"], c["page_no"]) for c in out] == [("C13", 1), ("C16", 1)]
    assert len(out[0]["items"]) == 2 and out[0]["path"].is_file()
    with Image.open(out[0]["path"]) as im:
        assert max(im.size) <= K.LONG_SIDE and min(im.size) >= 400          # 합집합 + 120mm 여백, 축소 상한
    many = [dict(ev[0], ord=f"C{10 + i}") for i in range(8)]
    pages8 = {(f"C{10 + i}", 1): _page(tmp_path, f"C{10 + i}") for i in range(8)}
    assert len(K.section_crops(None, "ds", many, tmp_path / "crops8", pages=pages8)) == K.MAX_IMAGES


def test_kb_excerpt_keeps_only_rule_sections():
    text = "# KB\n\n## 1. 좌표\n- a\n\n## 3. 판독\n- b\n\n## 5. 모델링 규칙\n- c\n\n## 6. 검증\n- d\n"
    ex = C.kb_excerpt(text)
    assert "## 1. 좌표" in ex and "## 5. 모델링 규칙" in ex and "- c" in ex
    assert "## 3. 판독" not in ex and "- d" not in ex


def test_toolkit_doc_lists_geom_functions_with_signatures():
    doc = C.toolkit_doc()
    for fn in ("loft(", "extrude(", "rect(", "box_prism(", "mirror_poly(", "mirror_mesh(", "paint(", "zone_loft("):
        assert fn in doc
    assert "ear_clip" not in doc                        # 내부 함수 제외


def test_spec_excerpt_marks_sources_docs_and_limits_fields():
    ex = C.spec_excerpt(ModelSpec().model_dump(), SOURCES)
    assert set(ex) == {"coord", "box", "diaphragm", "bearing"}
    assert ex["diaphragm"]["spacing"] == {"value": 2.8, "source": "ssot:C01/다이아프램 간격",
                                          "doc": Diaphragm.model_fields["spacing"].description}
    assert ex["diaphragm"]["support_t"]["source"].startswith("default:")
    assert ex["diaphragm"]["support_jack"]["doc"].startswith("(t 두께[x]")
    assert ex["bearing"]["x"] == {"value": 1.55, "source": "default", "doc": Bearing.model_fields["x"].description}
    assert "doc" not in ex["coord"]["z_p4"]                      # 설명 없는 필드는 키 생략


def test_section_bundle_composes_system_and_user_with_feedback(tmp_path):
    img = tmp_path / "c.png"
    Image.new("RGB", (600, 400), "white").save(img)
    crops = [{"ord": "C13", "page_no": 1, "path": img, "items": [{"item": "CL 다이아프램 규격", "value": "DIAP 10x4500x3739", "status": "확정"}]}]
    b = C.section_bundle("P4P5/DIA", spec_dict=ModelSpec().model_dump(), sources=SOURCES, evidence=[], crops=crops,
                         feedback="only_ref: AB1_S5_DIA26", request="개구를 1.4×1.4 로", prev_code="def build_section(spec, ctx):\n    return {}")
    assert "build_section(spec, ctx)" in b["system"] and "AB1_S5_DIA01" in b["system"] and "전역 체인" in b["system"]
    assert "geom.paint" in b["system"] and "y_web_top(z)" in b["system"]
    parts = b["messages"][0]["content"]
    kinds = [p["type"] for p in parts]
    assert kinds.count("image") == 1 and b["n_images"] == 1
    text = "\n".join(p["text"] for p in parts if p["type"] == "text")
    assert '"source": "ssot:C01/다이아프램 간격"' in text and "참조 차용" in text
    assert '"doc": "(t 두께[x]' in text and "출처·의미 표시용" in b["system"] and "doc 은 필드 의미" in text
    assert "이전 시도" in text and "only_ref: AB1_S5_DIA26" in text and "개구를 1.4×1.4 로" in text
    assert len(b["digest"]) == 64
    b2 = C.section_bundle("P4P5/DIA", spec_dict=ModelSpec().model_dump(), sources=SOURCES, evidence=[], crops=crops)
    assert b2["digest"] != b["digest"] and "이전 시도" not in "\n".join(p["text"] for p in b2["messages"][0]["content"] if p["type"] == "text")
