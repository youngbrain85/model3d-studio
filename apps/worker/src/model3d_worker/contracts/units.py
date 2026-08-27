"""단위 변환 — 규칙 §1: "도면 치수는 mm 정본, 모델은 m — 변환은 한 곳(빌더 상수)에서만."

이 모듈이 그 "한 곳"이다. 다른 어디에서도 1000 을 곱하거나 나누지 않는다.
TS 쪽 대응: ``packages/contracts/src/units.ts``
"""

from __future__ import annotations

#: 모델 1 단위(m) 당 도면 단위(mm) 수. 이 상수는 이 파일에만 존재한다.
MM_PER_MODEL_UNIT = 1000.0


def mm_to_model(mm: float) -> float:
    """도면 mm → 모델 m."""
    return mm / MM_PER_MODEL_UNIT


def model_to_mm(m: float) -> float:
    """모델 m → 도면 mm."""
    return m * MM_PER_MODEL_UNIT


def mm_to_model_vec3(mm: tuple[float, float, float]) -> tuple[float, float, float]:
    """도면 mm 3성분 → 모델 m 3성분."""
    return (mm_to_model(mm[0]), mm_to_model(mm[1]), mm_to_model(mm[2]))
