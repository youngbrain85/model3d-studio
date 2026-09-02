"""LLM 출력 스키마 (설계서 §4).

anthropic.transform_schema() 로 JSON Schema 가 되어 output_config 에 실리고,
응답 텍스트는 여기 모델로 직접 검증된다. 여기서 반려되는 응답이 곧 근거 없는
수치이며, 지식베이스 §8("근거 없는 수치는 반려")의 집행 지점이다.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from m3d.models import AmbiguityOption

MmBBox = Annotated[list[float], Field(min_length=4, max_length=4,
                                      description="[x0,y0,x1,y1] 용지 mm")]


class LlmReading(BaseModel):
    item: str = Field(min_length=1, description="항목명(한국어)")
    value_raw: str = Field(min_length=1, description="도면 원문 표기 그대로")
    unit: str | None = Field(default=None, description="mm, m, EL 등")
    page_no: int = Field(gt=0, description="근거 페이지 번호")
    mm_bbox: MmBBox
    crosscheck: str | None = Field(
        default=None, description="검산식과 결과. 예: '구간합 70,000 = 전장 70,000 ✓'")
    status: Literal["확정", "추정"] = Field(
        description="교차 확인된 값만 확정. 단일 소스·유추는 추정")


class LlmAmbiguity(BaseModel):
    item: str = Field(min_length=1, description="애매한 요소 하나")
    page_no: int = Field(gt=0)
    mm_bbox: MmBBox = Field(description="질문 카드 크롭이 될 영역")
    options: list[AmbiguityOption] = Field(
        min_length=2, max_length=4, description="권장안을 첫 번째로")
    model_impact: str = Field(min_length=1, description="선택에 따라 모델이 어떻게 달라지는가")


class SheetReadOut(BaseModel):
    readings: list[LlmReading]
    ambiguities: list[LlmAmbiguity]


class MergedReading(LlmReading):
    """계열 통합 후의 판독 1건 — 근거 시트(ord)를 반드시 달고 다닌다."""

    ord: str = Field(min_length=1, description="이 값이 적힌 시트의 ord (입력에 있던 것만)")


class MergedAmbiguity(LlmAmbiguity):
    ord: str = Field(min_length=1, description="이 애매성이 나온 시트의 ord (입력에 있던 것만)")


class FinalReading(MergedReading):
    """적대적 검토를 통과한 뒤의 판독 — 여기서만 '검토지적' 이 붙는다."""

    status: Literal["확정", "추정", "검토지적"]


class RegionMergeOut(BaseModel):
    readings: list[MergedReading]
    ambiguities: list[MergedAmbiguity]
    notes: list[str] = Field(default_factory=list, description="병합·교차확인 메모")


class ReviewFinding(BaseModel):
    target_item: str = Field(min_length=1)
    verdict: Literal["기각", "상태변경", "신규애매성"]
    reason: str = Field(min_length=1)
    # 검토는 낮추기만 한다 — '확정' 은 선택지에 없다 (§4-3)
    new_status: Literal["추정", "검토지적"] | None = None
    new_ambiguity: MergedAmbiguity | None = None

    @model_validator(mode="after")
    def _payload_matches_verdict(self):
        if self.verdict == "상태변경" and self.new_status is None:
            raise ValueError("상태변경 판정에는 new_status 가 필요하다")
        if self.verdict == "신규애매성" and self.new_ambiguity is None:
            raise ValueError("신규애매성 판정에는 new_ambiguity 가 필요하다")
        return self


class ReviewOut(BaseModel):
    findings: list[ReviewFinding]
