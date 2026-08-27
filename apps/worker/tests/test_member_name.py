"""부재 명명 규칙 — 규칙 §5. TS 구현과 **같은 픽스처**로 교차 검증한다."""

from __future__ import annotations

import json
from typing import Any

import pytest

from model3d_worker.contracts.member_name import (
    MEMBER_CODE_PATTERN,
    MemberNamingError,
    format_member_code,
    is_valid_member_code,
    parse_member_code,
)
from model3d_worker.contracts.schemas import fixture_dir, load_schema

_CASES: dict[str, Any] = json.loads(
    (fixture_dir() / "member_code.cases.json").read_text(encoding="utf-8")
)


def test_pattern_matches_fixture_and_schema() -> None:
    """정규식이 픽스처·스키마와 **문자열까지** 같아야 한다 — 셋이 갈라지면 조용히 어긋난다."""
    assert _CASES["pattern"] == MEMBER_CODE_PATTERN
    assert load_schema("member.schema.json")["properties"]["code"]["pattern"] == MEMBER_CODE_PATTERN


@pytest.mark.parametrize("case", _CASES["valid"], ids=lambda c: str(c["code"]))
def test_parse_valid(case: dict[str, Any]) -> None:
    assert is_valid_member_code(case["code"])
    parsed = parse_member_code(case["code"])
    assert parsed is not None
    assert parsed.structure == case["structure"]
    assert parsed.segment == case["segment"]
    assert parsed.member_type == case["member_type"]
    assert parsed.index == case["index"]
    assert parsed.side == case["side"]
    assert parsed.index_width == case["index_width"]


@pytest.mark.parametrize("case", _CASES["valid"], ids=lambda c: str(c["code"]))
def test_format_roundtrip(case: dict[str, Any]) -> None:
    assert (
        format_member_code(
            structure=case["structure"],
            segment=case["segment"],
            member_type=case["member_type"],
            index=case["index"],
            side=case["side"],
            index_width=case["index_width"],
        )
        == case["code"]
    )


@pytest.mark.parametrize("case", _CASES["invalid"], ids=lambda c: str(c["why"]))
def test_reject_invalid(case: dict[str, Any]) -> None:
    assert not is_valid_member_code(case["code"])
    assert parse_member_code(case["code"]) is None


def test_bad_format_raises() -> None:
    """잘못된 노드명이 조용히 퍼지면 안 된다."""
    with pytest.raises(MemberNamingError, match="부재 명명 규칙 위반"):
        format_member_code(structure="ab1", segment="S5", member_type="DIA", index=7)
