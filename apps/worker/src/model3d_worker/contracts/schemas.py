"""JSON Schema 정본 로더.

정본은 리포 루트의 ``packages/contracts/schemas/`` 다 — 워커와 웹이 **같은 파일**을 읽는다.
스키마가 사라지거나 경로가 어긋나면 조용히 넘어가지 않고 즉시 던진다.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

#: 이 파일: apps/worker/src/model3d_worker/contracts/schemas.py
#: 리포 루트까지 5단계 위.
_REPO_ROOT = Path(__file__).resolve().parents[5]

SCHEMA_FILES: tuple[str, ...] = (
    "ambiguity.schema.json",
    "coordinate_system.schema.json",
    "decision.schema.json",
    "member.schema.json",
    "sample_manifest.schema.json",
    "sample_set.schema.json",
    "sheet.schema.json",
    "ssot_item.schema.json",
    "verification_report.schema.json",
    "view_contract.schema.json",
)


def repo_root() -> Path:
    return _REPO_ROOT


def schema_dir() -> Path:
    d = _REPO_ROOT / "packages" / "contracts" / "schemas"
    if not d.is_dir():
        raise FileNotFoundError(
            f"계약 스키마 디렉터리를 찾을 수 없습니다: {d}. "
            "워커는 리포 안에서 실행되어야 합니다 (packages/contracts 가 정본)."
        )
    return d


def fixture_dir() -> Path:
    d = _REPO_ROOT / "packages" / "contracts" / "fixtures"
    if not d.is_dir():
        raise FileNotFoundError(f"계약 픽스처 디렉터리를 찾을 수 없습니다: {d}")
    return d


@cache
def load_schema(name: str) -> dict[str, Any]:
    """이름으로 스키마를 읽는다. 등록되지 않은 이름이면 던진다."""
    if name not in SCHEMA_FILES:
        raise KeyError(f"등록되지 않은 스키마: {name} (SCHEMA_FILES 에 추가하세요)")
    path = schema_dir() / name
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data
