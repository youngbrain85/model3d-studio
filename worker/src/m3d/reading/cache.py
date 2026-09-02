"""판독 캐시 (설계서 D5) — 요청 내용이 같으면 무호출.

개발 중 수십 회 재실행이 전제다. 키는 **실제로 보낼 요청의 내용 해시**여서
버전 상수를 올리는 사람 규율이 필요 없다: 프롬프트·스키마·모델·max_tokens·입력 중
무엇을 고치든 그것을 쓰는 호출만 미스가 된다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from m3d.config import Config


class CacheMissError(RuntimeError):
    """--cache-only 인데 캐시가 없다 — 실호출 대신 실패로 기록한다."""

    def __init__(self, stage: str, ref: str, key: str) -> None:
        super().__init__(f"캐시 없음: {stage} {ref} (key {key[:12]}…) — --cache-only")
        self.stage, self.ref, self.key = stage, ref, key


def cache_key(payload: dict) -> str:
    """dict 순서와 무관한 안정적 키."""
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def schema_fingerprint(model_cls) -> str:
    """출력 스키마의 지문 — 스키마가 바뀌면 캐시가 자연히 미스가 된다."""
    return cache_key(model_cls.model_json_schema())


def cache_path(cfg: Config, dataset: str, kind: str, key: str) -> Path:
    return cfg.derived_dir / dataset / "llm-cache" / kind / f"{key}.json"


def load_cached(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None  # 손상 캐시는 무시하고 재호출한다


def save_cached(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n",
    )
