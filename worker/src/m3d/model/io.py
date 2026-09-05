"""모델 산출물 경로·ModelSpec 파일 입출력 (data/derived/<dataset>/model/)."""

from __future__ import annotations

import json
from pathlib import Path

from m3d.config import Config
from m3d.model.spec import ModelSpec


def model_dir(cfg: Config, dataset: str) -> Path:
    d = cfg.derived_dir / dataset / "model"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_modelspec(cfg: Config, dataset: str, spec: ModelSpec, sources: dict, stats: dict) -> Path:
    path = model_dir(cfg, dataset) / "modelspec.json"
    path.write_text(json.dumps({"spec": spec.model_dump(), "sources": sources, "stats": stats},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_modelspec(cfg: Config, dataset: str) -> ModelSpec:
    path = model_dir(cfg, dataset) / "modelspec.json"
    if not path.is_file():
        raise RuntimeError(f"modelspec.json 없음 — `m3d modelspec {dataset}` 먼저")
    return ModelSpec.model_validate(json.loads(path.read_text(encoding="utf-8"))["spec"])
