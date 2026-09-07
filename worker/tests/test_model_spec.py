"""ModelSpec 추출 규칙 — 표기 파서·SSOT 필드 추출·출처 통계."""

from m3d.model import spec_rules as R
from m3d.model.spec import ModelSpec, leaf_paths


def test_parse_at_chain_and_number_and_pair():
    assert R.parse_at_chain("9@70,000=630,000") == (9, 70000.0, 630000.0)
    assert R.parse_at_chain("240@2,800=672,000") == (240, 2800.0, 672000.0)
    assert R.parse_at_chain("없음") is None
    assert R.parse_number("15,700") == 15700.0
    assert R.parse_number("4,000/2,800") == 4000.0
    assert R.parse_pair("450×330") == (450.0, 330.0)
    assert R.parse_pair("250 / 330") == (250.0, 330.0)


def test_parse_thickness_zones_symmetric_completion():
    zones = R.parse_thickness_zones("38(0~6,300) → 26(~16,100) → 16(~53,900) → 26 → 38", total=70000)
    assert zones == [(0.0, 6300.0, 38.0), (6300.0, 16100.0, 26.0), (16100.0, 53900.0, 16.0),
                     (53900.0, 63700.0, 26.0), (63700.0, 70000.0, 38.0)]
    assert R.parse_thickness_zones("38(0~6,300) → 26(~10,000)", total=70000) is None  # 사슬이 안 닫힘


def test_zones_from_class_totals_reconstructs_symmetric_chain():
    # SSOT C01 형태: 상판 38 총 12,600 / 26 편측 9,800 / 16 중앙 37,800
    zones = R.zones_from_class_totals({38.0: [12600.0], 26.0: [9800.0], 16.0: [35000.0, 2800.0]}, 70000.0)
    assert zones == [(0.0, 6300.0, 38.0), (6300.0, 16100.0, 26.0), (16100.0, 53900.0, 16.0),
                     (53900.0, 63700.0, 26.0), (63700.0, 70000.0, 38.0)]
    # 하판(SSOT C01): 18mm 가 총연장 12,600 과 소구간 5,600·7,000 으로 겹쳐 판독됨 → 최대값 후보로 닫힘
    bot = R.zones_from_class_totals({38.0: [7000.0], 28.0: [9800.0], 18.0: [12600.0, 5600.0, 7000.0],
                                     14.0: [18200.0]}, 70000.0)
    assert bot == [(0.0, 3500.0, 38.0), (3500.0, 13300.0, 28.0), (13300.0, 25900.0, 18.0),
                   (25900.0, 44100.0, 14.0), (44100.0, 56700.0, 18.0), (56700.0, 66500.0, 28.0),
                   (66500.0, 70000.0, 38.0)]
    assert R.zones_from_class_totals({38.0: [12600.0], 26.0: [4900.0], 16.0: [37800.0]}, 70000.0) is None


def _reading(region, ord_, item, value, status="확정"):
    return {"region": region, "ord": ord_, "page_no": 1, "item": item, "value_raw": value,
            "unit": "mm", "status": status, "mm_bbox": [1, 2, 3, 4], "crosscheck": None}


SSOT = {
    "project": {"coord_system": {"datums": {"P4_bearing_z": -525.0, "P5_bearing_z": -455.0}}},
    "readings": [
        _reading("B", "B01", "지간구성", "9@70,000=630,000"),
        _reading("C", "C01", "측면도 전체 형고 4,000", "4,000"),
        _reading("C", "C12", "CU 단면 전체 높이(형고) 2,800", "2,800"),
        _reading("C", "C01", "다이아프램 간격 240@2,800=672,000", "240@2,800=672,000"),
        _reading("C", "C13", "CL 다이아프램 규격 DIAP 10x4500x3739", "DIAP 10x4500x3739"),
        _reading("C", "C01", "상판 판두께 12,600(T=38mm HSB500)", "12,600(T=38mm HSB500)", "추정"),
        _reading("C", "C01", "상판 판두께 9,800(T=26mm HSB500)", "9,800(T=26mm HSB500)", "추정"),
        _reading("C", "C01", "상판 판두께 35,000(T=16mm HSB500) 중앙압축부", "35,000(T=16mm HSB500)", "추정"),
        _reading("C", "C01", "상판 판두께 2,800(T=16mm HSB500) 전이구간", "2,800(T=16mm HSB500)", "추정"),
        _reading("B", "B01", "전체 폭원", "15,700"),
        _reading("B", "B02", "슬래브 콘크리트 두께(단면 C-C/F-F, 300 표기)", "300"),
        _reading("B", "B02", "방호벽 하부 폭", "450"),
        _reading("B", "B01", "방호벽 높이 구간", "250 / 330"),
        _reading("A", "A04", "P1~P8 경간별 받침 간격(교각 상 받침 간 거리)", "3,100"),
    ],
    "decisions": [
        {"item": "측면도 형고 4,000mm가 내공고인지 전강고인지", "choice_label": "내공고(웹·격벽 높이)", "provisional": False},
        {"item": "슬래브 두께 표기 '113.2 / 127.7'의 의미(순 콘크리트 두께 vs 포장 포함)", "choice_label": "포장 포함 전체 두께", "provisional": False},
    ],
}


def test_build_modelspec_fills_from_ssot_and_decisions_with_sources():
    spec, src = R.build_modelspec(SSOT)
    assert spec.box.h_pier == 4.0 and src["box.h_pier"].startswith("ssot:C01/")
    assert spec.box.h_mid == 2.8 and src["box.h_mid"].startswith("ssot:C12/")
    assert spec.diaphragm.spacing == 2.8 and spec.diaphragm.n_cell == 25
    assert src["diaphragm.n_cell"].startswith("derived:")
    assert spec.diaphragm.interior_t == 0.010 and dict(spec.diaphragm.h_table)[2.8] == 3.739
    assert spec.box.top_t == [(0.0, 6.3, 0.038), (6.3, 16.1, 0.026), (16.1, 53.9, 0.016),
                              (53.9, 63.7, 0.026), (63.7, 70.0, 0.038)]
    assert src["box.top_t"].startswith("ssot:C01/")
    assert src["box.bot_t"].startswith("default:SPEC_v2 §1")      # 하판 판독 없음 → 차용 표기
    assert spec.slab.half_width == 7.85 and spec.slab.t_web == 0.30
    assert spec.slab.barrier == (0.45, 0.33, 0.03)
    assert spec.bearing.x == 1.55 and src["bearing.x"].startswith("ssot:A04/")
    assert spec.box.h_is_clear is True and src["box.h_is_clear"].startswith("decision:")
    assert spec.slab.thickness_is_net is False and src["slab.thickness_is_net"].startswith("decision:")
    assert spec.wg.length == 4.45 and src["wg.length"] == "default:SPEC_v2 §6"
    stats = R.source_stats(src)
    assert stats["ssot"] >= 9 and stats["decision"] == 2 and stats["default"] > 0
    assert sum(stats.values()) == len(src)
    assert set(leaf_paths(spec)) <= set(src)                      # 리프 필드 전건 출처 있음


def test_default_spec_roundtrips_json():
    spec = ModelSpec()
    again = ModelSpec.model_validate_json(spec.model_dump_json())
    assert again == spec and len(leaf_paths(spec)) > 60


def test_missing_paths_detects_schema_drift_in_nested_lists():
    from m3d.model.io import missing_paths
    cur = ModelSpec().model_dump()
    stored = ModelSpec().model_dump()
    del stored["frame"]["rows"][5]["top_flange_t"]
    del stored["wg"]["first_no"]
    assert missing_paths(cur, stored) == ["frame.rows[5].top_flange_t", "wg.first_no"]
    assert missing_paths(cur, ModelSpec().model_dump()) == []


from m3d.model.spec import Bearing, Diaphragm


def test_diaphragm_and_bearing_fields_carry_descriptions():
    """프롬프트 발췌가 튜플 필드의 의미(축·방향)를 보여줄 수 있어야 한다(M6 D1)."""
    for name, f in Diaphragm.model_fields.items():
        assert f.description, f"Diaphragm.{name} description 없음"
    assert Bearing.model_fields["x"].description
    vs, jk, os_ = (Diaphragm.model_fields[k].description for k in ("support_vstiff", "support_jack", "open_stiff"))
    assert "[x 방향]" in vs and "경간 안쪽 z" in vs and "[A4]" in vs
    assert "t 두께[x]" in jk and "h 높이[y]" in jk
    assert "+z 면에만" in os_ and "[A5]" in os_


def test_every_submodel_field_carries_a_description():
    """프롬프트 스펙 발췌의 doc 은 전 섹션에 필요하다(M7 D4)."""
    missing = []
    for key, f in ModelSpec.model_fields.items():
        sub = getattr(f.annotation, "model_fields", None)
        if not sub:
            continue
        missing += [f"{key}.{n}" for n, sf in sub.items() if not sf.description]
    assert missing == [], f"description 없는 필드: {missing}"


def test_tuple_fields_name_the_axis_each_component_extends():
    """튜플 필드는 성분마다 뻗는 축을 밝힌다 — M6 에서 '돌출 vs 두께' 오독의 해법."""
    from m3d.model.spec import SP04, Bearing, Slab, WG
    for model, field in ((SP04, "tf"), (SP04, "bf"), (SP04, "web"), (Bearing, "sole"),
                         (Bearing, "mortar"), (Bearing, "block"), (Slab, "barrier"), (WG, "knee")):
        d = model.model_fields[field].description
        assert any(ax in d for ax in ("[x]", "[y]", "[z]")), f"{model.__name__}.{field} 축 표기 없음: {d}"


def test_unused_fields_say_they_are_not_used_for_geometry():
    """참조 빌더가 형상에 쓰지 않는 값은 그렇다고 밝힌다 — 안 그러면 에이전트가 쓸 자리를 지어낸다(M7 배치 1 SP04·SLAB)."""
    from m3d.model.spec import SP04, Slab, WG
    for model, field in ((SP04, "setback"), (Slab, "t_edge"), (Slab, "t_web"), (Slab, "t_crown"),
                         (Slab, "thickness_is_net"), (WG, "strut_angle_deg")):
        d = model.model_fields[field].description
        assert "형상에 쓰지 않는다" in d, f"{model.__name__}.{field}: {d}"


def test_center_barrier_description_gives_its_position():
    """'중앙 방호벽' 은 x=0 이 아니라 보도 경계에 있다 — 이름만 보면 반드시 틀린다."""
    d = __import__("m3d.model.spec", fromlist=["Slab"]).Slab.model_fields["center_barrier"].description
    assert "보도" in d and "x=0" in d


def test_cs_seg_and_frame_vstiff_descriptions_carry_the_convention():
    """세그먼트는 체인 '중심', 수직보강재 길이는 내공 높이가 아니다(M7 배치 2 CS·FRM)."""
    from m3d.model.spec import CS, FrameRow
    assert "중심" in CS.model_fields["seg"].description
    assert "내공 높이가 아니라" in FrameRow.model_fields["vstiff"].description
