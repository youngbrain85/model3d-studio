"""0001_init.sql 을 미러링하는 Pydantic 모델 (설계서 §3).

SQL 이 정본이다. 이 모듈은 DB 왕복 전에 같은 제약을 걸어 실패 원인을 앞당긴다.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

GRADES = ("핵심", "참고")
CATALOG_STATUSES = ("unverified", "match", "mismatch", "unreadable")
ASSET_KINDS = ("dxf", "pdf", "png", "photo")
ASSET_ROLES = ("source", "derived")


class ProjectRow(BaseModel):
    slug: str
    name: str
    structure: str | None = None
    coord_system: dict[str, Any]
    coord_assumptions: list[str] = Field(default_factory=list)


class SheetRow(BaseModel):
    ord: str
    drawing_no_from_filename: str
    title_from_filename: str
    grade: Literal["핵심", "참고"]
    page_count: int = Field(gt=0)
    # M0 는 내용 유래 값을 채우지 않는다 — M1 [3] 의 시험 문제다 (설계서 §6-3)
    catalog_status: Literal["unverified", "match", "mismatch", "unreadable"] = "unverified"


class SheetPageRow(BaseModel):
    ord: str                       # 부모 sheet 를 가리키는 키 (DB 컬럼 아님)
    page_no: int = Field(gt=0)


class AssetRow(BaseModel):
    kind: Literal["dxf", "pdf", "png", "photo"]
    role: Literal["source", "derived"]
    rel_path: str
    bytes: int = Field(gt=0)
    sha256: str = Field(min_length=64, max_length=64)
    # 아래 둘은 DB 컬럼이 아니라 시딩 시 sheet_id·sheet_page_id 를 찾는 키다
    ord: str | None = None
    page_no: int | None = None


READING_STATUSES = ("확정", "추정", "검토지적")
AMBIGUITY_STATUSES = ("대기", "결정", "잠정")

# 용지 mm 좌표 [x0, y0, x1, y1] — 크롭·근거 표시의 공통 형태 (설계서 §6)
MmBBox = Annotated[list[float], Field(min_length=4, max_length=4)]


class ReadingRow(BaseModel):
    """판독 결과 1건. 근거(시트·페이지·mm bbox) 없이는 만들 수 없다 (지식베이스 §8)."""

    region: str
    item: str
    value_raw: str = Field(min_length=1)      # 원문 표기 그대로 (§2)
    unit: str | None = None
    basis_ord: str                            # sheets.ord — id 는 삽입 시 해석
    basis_page_no: int = Field(gt=0)
    basis_mm_bbox: MmBBox
    crosscheck: dict[str, Any] | None = None  # {expr, result, ok}
    status: Literal["확정", "추정", "검토지적"]
    round: int = Field(default=1, ge=1, le=3)


class AmbiguityOption(BaseModel):
    """해석 선택지 — 라벨과 근거는 한 쌍이다 (§4)."""

    label: str = Field(min_length=1)
    basis: str = Field(min_length=1)


class AmbiguityRow(BaseModel):
    """애매성 1건 = 질문 카드 1장. 한 질문 = 한 요소 (§4)."""

    item: str = Field(min_length=1)
    basis_ord: str
    basis_page_no: int = Field(gt=0)
    mm_bbox: MmBBox
    options: list[AmbiguityOption] = Field(min_length=2, max_length=4)
    model_impact: str = Field(min_length=1)
    status: Literal["대기", "결정", "잠정"] = "대기"
