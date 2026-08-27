"""0001_init.sql 을 미러링하는 Pydantic 모델 (설계서 §3).

SQL 이 정본이다. 이 모듈은 DB 왕복 전에 같은 제약을 걸어 실패 원인을 앞당긴다.
"""

from __future__ import annotations

from typing import Any, Literal

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
