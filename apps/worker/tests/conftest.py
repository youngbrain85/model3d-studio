"""테스트 격리 — 개발자의 실제 `.env` 가 테스트 결과를 바꾸지 못하게 한다.

리포 루트의 `.env` 에는 사용자마다 다른 샘플 원본 경로가 들어 있다. 그것을 읽는 채로
테스트를 돌리면 "내 머신에서는 통과하는데 CI 에서는 실패한다"(혹은 그 반대)가 된다.
그래서 모든 테스트는 기본적으로 **`.env` 가 없는 상태**에서 돈다. `.env` 를 실제로
읽는지 확인하는 테스트는 :func:`env_file` 픽스처로 명시적으로 옵트인한다.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from model3d_worker import config


@pytest.fixture(autouse=True)
def isolate_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """`.env` 와 M3D_SAMPLE_SOURCE_* 환경변수로부터 테스트를 격리한다."""
    missing = tmp_path_factory.mktemp("no-env") / ".env"  # 존재하지 않는 경로
    monkeypatch.setattr(config, "env_file_path", lambda: missing)
    for key in [k for k in os.environ if k.startswith(config.SAMPLE_SOURCE_PREFIX)]:
        monkeypatch.delenv(key, raising=False)
    config.reload_env_cache()


@pytest.fixture
def env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """실제 `.env` 파일을 쓰고 읽게 하는 픽스처 (옵트인)."""
    path = tmp_path / ".env"
    path.touch()
    monkeypatch.setattr(config, "env_file_path", lambda: path)
    config.reload_env_cache()
    yield path
    config.reload_env_cache()
