"""모델링 에이전트 출력 (M5 D1) — 코드 + 가정 + 질문."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentOut(BaseModel):
    code: str = Field(description="build_section(spec, ctx) 를 정의하는 파이썬 코드 전체(허용 import: math, numpy, trimesh, m3d.model.geom)")
    assumptions: list[str] = Field(default_factory=list, description="도면·스펙에서 확정하지 못해 가정한 것(한 항목 = 한 가정)")
    questions: list[str] = Field(default_factory=list, description="사용자에게 확인이 필요한 질문(한 질문 = 한 요소)")


def validate_agent_out(out: AgentOut) -> None:
    """call_structured 의 post_validate — 계약·AST 위반은 ValueError 로 올려 1회 재시도를 유도한다."""
    from m3d.agent.sandbox import check_code
    violations = check_code(out.code)
    if violations:
        raise ValueError("코드 계약 위반: " + "; ".join(violations[:10]))
