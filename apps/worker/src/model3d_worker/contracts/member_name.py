"""부재 명명 규칙 — 규칙 §5.

패턴: ``<구조물>_<세그먼트>_<부재종류><번호>[<측면>]``

    AB1_S5_DIA07   → structure=AB1, segment=S5, member_type=DIA, index=7,  side=None
    AB1_S5_WG097L  → structure=AB1, segment=S5, member_type=WG,  index=97, side=L

TS 쪽 대응: ``packages/contracts/src/memberName.ts``.
정규식 문자열은 ``member.schema.json`` 의 ``pattern`` 과 **문자열까지 같아야** 하며,
테스트가 이를 강제한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

MemberSide = Literal["L", "R", "C", "T", "B"]

#: member.schema.json 의 code 패턴과 문자열이 일치해야 한다.
MEMBER_CODE_PATTERN = r"^[A-Z][A-Z0-9]{0,7}_S[0-9]{1,3}_[A-Z]{2,4}[0-9]{1,4}[LRCTB]?$"

_MEMBER_CODE_RE = re.compile(
    r"^(?P<structure>[A-Z][A-Z0-9]{0,7})_(?P<segment>S[0-9]{1,3})_"
    r"(?P<member_type>[A-Z]{2,4})(?P<index>[0-9]{1,4})(?P<side>[LRCTB])?$"
)

_SIDES: frozenset[str] = frozenset({"L", "R", "C", "T", "B"})


@dataclass(frozen=True)
class ParsedMemberCode:
    structure: str
    segment: str
    member_type: str
    index: int
    side: MemberSide | None
    #: 원본 코드의 번호 자리수 (0 패딩 폭). 재조립 시 같은 폭을 유지한다.
    index_width: int


def is_valid_member_code(code: str) -> bool:
    return _MEMBER_CODE_RE.match(code) is not None


def parse_member_code(code: str) -> ParsedMemberCode | None:
    """부재 코드를 성분으로 분해한다. 규칙에 맞지 않으면 None."""
    m = _MEMBER_CODE_RE.match(code)
    if m is None:
        return None
    raw_index = m.group("index")
    side = m.group("side")
    return ParsedMemberCode(
        structure=m.group("structure"),
        segment=m.group("segment"),
        member_type=m.group("member_type"),
        index=int(raw_index),
        side=side if side in _SIDES else None,  # type: ignore[arg-type]
        index_width=len(raw_index),
    )


class MemberNamingError(ValueError):
    """부재 명명 규칙 위반."""


def format_member_code(
    *,
    structure: str,
    segment: str,
    member_type: str,
    index: int,
    side: MemberSide | None = None,
    index_width: int = 2,
) -> str:
    """성분에서 부재 코드를 조립한다.

    조립 결과가 명명 규칙에 맞지 않으면 던진다 — 잘못된 노드명이 조용히 퍼지면 안 된다.
    """
    code = f"{structure}_{segment}_{member_type}{index:0{index_width}d}{side or ''}"
    if not is_valid_member_code(code):
        raise MemberNamingError(f"부재 명명 규칙 위반: {code} (패턴 {MEMBER_CODE_PATTERN})")
    return code
