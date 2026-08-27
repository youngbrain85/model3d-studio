"""테스트 공용 픽스처."""

from pathlib import Path

import pytest

from m3d.config import REPO_ROOT


@pytest.fixture
def fixtures_dir() -> Path:
    """커밋된 정답지·카탈로그 사본 (설계서 §1-2)."""
    return REPO_ROOT / "data" / "fixtures" / "ab1-p4p5"
