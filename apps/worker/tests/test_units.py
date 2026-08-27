"""단위 변환 — 규칙 §1: 변환은 한 곳에서만."""

from __future__ import annotations

import pytest

from model3d_worker.contracts.units import (
    MM_PER_MODEL_UNIT,
    mm_to_model,
    mm_to_model_vec3,
    model_to_mm,
)


@pytest.mark.parametrize("mm", [0.0, 1.0, 2500.0, 32500.0, -1200.5])
def test_mm_m_roundtrip(mm: float) -> None:
    assert model_to_mm(mm_to_model(mm)) == pytest.approx(mm, abs=1e-9)


def test_constant() -> None:
    assert MM_PER_MODEL_UNIT == 1000.0
    assert mm_to_model(32500) == pytest.approx(32.5)
    assert model_to_mm(32.5) == pytest.approx(32500)


def test_vec3() -> None:
    assert mm_to_model_vec3((1000.0, 2500.0, -500.0)) == pytest.approx((1.0, 2.5, -0.5))


def test_constant_lives_in_exactly_one_place() -> None:
    """규칙 §1 — 1000 으로 곱하거나 나누는 식이 units.py 밖에 있으면 안 된다."""
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src" / "model3d_worker"
    pattern = re.compile(r"[*/]\s*1000(?![.\d])")
    offenders = [
        str(p.relative_to(src))
        for p in src.rglob("*.py")
        if p.name != "units.py" and pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"units.py 밖에서 1000 변환 발견: {offenders}"
