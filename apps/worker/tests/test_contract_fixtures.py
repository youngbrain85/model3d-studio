"""계약 정합성 — 같은 픽스처를 **JSON Schema 와 pydantic 양쪽**으로 통과시킨다.

이 테스트가 통과해야만 "TS 계약 = JSON Schema = pydantic 모델" 이 실제로 같은 것이 된다.
invalid 케이스는 **양쪽 모두** 거부해야 한다 — 한쪽만 거부하면 규칙이 새는 구멍이 있다는 뜻이다.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from model3d_worker.contracts import models as m
from model3d_worker.contracts.schemas import SCHEMA_FILES, fixture_dir, load_schema, schema_dir

_MODEL_BY_CASE: dict[str, type[m.BaseContract]] = {
    "ambiguity.cases.json": m.Ambiguity,
    "decision.cases.json": m.Decision,
    "ssot_item.cases.json": m.SsotItem,
    "verification_report.cases.json": m.VerificationReport,
}


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((fixture_dir() / name).read_text(encoding="utf-8"))
    return data


def test_schema_files_match_directory() -> None:
    on_disk = sorted(p.name for p in schema_dir().glob("*.schema.json"))
    assert on_disk == sorted(SCHEMA_FILES)


@pytest.mark.parametrize("name", SCHEMA_FILES)
def test_schema_is_valid_draft_2020_12(name: str) -> None:
    Draft202012Validator.check_schema(load_schema(name))


def _validator(case_file: str) -> tuple[Draft202012Validator, dict[str, Any]]:
    data = _load(case_file)
    return (
        Draft202012Validator(load_schema(data["schema"]), format_checker=FormatChecker()),
        data,
    )


@pytest.mark.parametrize("case_file", sorted(_MODEL_BY_CASE))
def test_valid_docs_accepted_by_both(case_file: str) -> None:
    validator, data = _validator(case_file)
    model = _MODEL_BY_CASE[case_file]
    for i, doc in enumerate(data["valid"]):
        errors = sorted(validator.iter_errors(doc), key=str)
        assert not errors, f"{case_file} valid[{i}] 스키마 거부: {errors[0].message}"
        model.model_validate(doc)  # pydantic 도 받아들여야 한다


@pytest.mark.parametrize("case_file", sorted(_MODEL_BY_CASE))
def test_invalid_docs_rejected_by_both(case_file: str) -> None:
    validator, data = _validator(case_file)
    model = _MODEL_BY_CASE[case_file]
    for i, case in enumerate(data["invalid"]):
        why = case["why"]
        assert list(validator.iter_errors(case["doc"])), (
            f"{case_file} invalid[{i}] 이 스키마를 통과했다 (거부되어야 함): {why}"
        )
        with pytest.raises(ValidationError):
            model.model_validate(case["doc"])


def test_extra_fields_are_rejected() -> None:
    """스키마에 없는 키가 조용히 무시되면 오타 난 근거가 흘러든다."""
    data = _load("decision.cases.json")
    doc = dict(data["valid"][0])
    doc["typo_field"] = "x"
    with pytest.raises(ValidationError):
        m.Decision.model_validate(doc)


def test_independent_remeasure_rejects_self_verification() -> None:
    """규칙 §8 — 빌더가 자기 산출물을 재실측하면 검증이 아니다.

    스키마로는 표현하기 어려운 제약이라 pydantic 이 맡는다.
    """
    data = _load("verification_report.cases.json")
    doc = dict(next(d for d in data["valid"] if d["stage"] == "independent_remeasure"))
    doc["performed_by"] = doc["builder_agent"]
    with pytest.raises(ValidationError, match="자기 검증"):
        m.VerificationReport.model_validate(doc)


def test_assumed_axis_requires_flip_test() -> None:
    """규칙 §1 — 방위가 미확정이면 뒤집기 검증 항목으로 등재해야 한다."""
    base: dict[str, Any] = {
        "project_id": "prj-ab1",
        "up_axis": "Y",
        "handedness": "right",
        "model_unit": "m",
        "drawing_unit": "mm",
        "mm_per_model_unit": 1000,
        "axes": {
            "x": {"meaning": "교축직각", "positive_direction": "+동측", "assumed": True},
            "y": {"meaning": "EL−오프셋", "positive_direction": "+상방", "assumed": False},
            "z": {"meaning": "STA−오프셋", "positive_direction": "+종점방향", "assumed": False},
        },
        "origin_reference": {
            "description": "P4 받침선과 교축중심선의 교점, 상부플랜지 상면",
            "source_sheets": ["AB1-S-003"],
        },
        "assumptions": [],
    }
    with pytest.raises(ValidationError, match="뒤집기"):
        m.CoordinateSystem.model_validate(base)

    base["assumptions"] = [
        {
            "item": "동측 방위",
            "assumed_value": "+x = 동측",
            "reason": "도면에 방위표 없음",
            "flip_test": "뒤집으면 배수구가 서측으로 간다 — 사진 P4-03 의 배수구 위치로 판정",
            "resolved": False,
        }
    ]
    m.CoordinateSystem.model_validate(base)


# ── 스키마 ↔ pydantic 구조 정합 ─────────────────────────────────────────
# JSON Schema 가 정본이므로, 모델이 스키마와 어긋나면 그것은 모델의 버그다.
# 필드가 한쪽에만 추가되는 드리프트를 **사람 눈이 아니라 테스트**가 잡는다.

_MODEL_BY_SCHEMA: dict[str, type[m.BaseContract]] = {
    "ambiguity.schema.json": m.Ambiguity,
    "coordinate_system.schema.json": m.CoordinateSystem,
    "decision.schema.json": m.Decision,
    "member.schema.json": m.Member,
    "sample_manifest.schema.json": m.SampleManifest,
    "sample_set.schema.json": m.SampleSetDef,
    "sheet.schema.json": m.Sheet,
    "ssot_item.schema.json": m.SsotItem,
    "verification_report.schema.json": m.VerificationReport,
    "view_contract.schema.json": m.ViewContract,
}


def test_every_schema_has_a_model() -> None:
    assert sorted(_MODEL_BY_SCHEMA) == sorted(SCHEMA_FILES)


@pytest.mark.parametrize("schema_name", sorted(_MODEL_BY_SCHEMA))
def test_model_fields_match_schema_properties(schema_name: str) -> None:
    schema = load_schema(schema_name)
    model = _MODEL_BY_SCHEMA[schema_name]
    schema_props = set(schema.get("properties", {}))
    model_fields = set(model.model_fields)

    assert model_fields == schema_props, (
        f"{schema_name}: 스키마에만 있는 필드 {sorted(schema_props - model_fields)}, "
        f"모델에만 있는 필드 {sorted(model_fields - schema_props)}"
    )


@pytest.mark.parametrize("schema_name", sorted(_MODEL_BY_SCHEMA))
def test_schema_required_fields_are_required_in_model(schema_name: str) -> None:
    """스키마가 필수라고 한 필드는 모델에서도 기본값 없이 필수여야 한다.

    예외: 스키마가 ``const`` 로 값을 고정한 필드(model_unit, handedness 등)는
    모델이 그 상수를 기본값으로 가져도 의미가 같다.
    """
    schema = load_schema(schema_name)
    model = _MODEL_BY_SCHEMA[schema_name]
    props = schema.get("properties", {})

    optional_in_model = [
        name
        for name in schema.get("required", [])
        if not model.model_fields[name].is_required() and "const" not in props.get(name, {})
    ]
    assert optional_in_model == [], (
        f"{schema_name}: 스키마 필수인데 모델에서 선택적인 필드 {optional_in_model}"
    )
