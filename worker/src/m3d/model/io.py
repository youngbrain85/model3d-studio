"""모델 산출물 경로·ModelSpec 파일 입출력 (data/derived/<dataset>/model/)."""

from __future__ import annotations

import json
from pathlib import Path

from m3d.config import Config
from m3d.model.spec import ModelSpec


def model_dir(cfg: Config, dataset: str, *, pilot: bool = False) -> Path:
    """산출 디렉터리 — 전체 model/, 시범 model/pilot/ (같은 파일명, M4 D4)."""
    d = cfg.derived_dir / dataset / "model"
    if pilot:
        d = d / "pilot"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_build_json(out_dir: Path, data: dict) -> Path:
    path = Path(out_dir) / "build.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


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


def missing_paths(current: dict, stored: dict, prefix: str = "") -> list[str]:
    """스키마 드리프트 — 현재 ModelSpec 에는 있는데 저장된 JSON 에 없는 경로(기본값이 조용히 적용됨)."""
    out: list[str] = []
    for k, v in current.items():
        path = f"{prefix}{k}"
        if k not in stored:
            out.append(path)
        elif isinstance(v, dict) and isinstance(stored[k], dict):
            out.extend(missing_paths(v, stored[k], path + "."))
        elif isinstance(v, list) and isinstance(stored[k], list) and v and isinstance(v[0], dict):
            for i, (cv, sv) in enumerate(zip(v, stored[k])):
                if isinstance(sv, dict):
                    out.extend(missing_paths(cv, sv, f"{path}[{i}]."))
    return out


def modelspec_drift(cfg: Config, dataset: str) -> list[str]:
    """저장된 modelspec.json 이 현재 스키마보다 오래됐으면 누락 필드 경로 목록(비면 정상)."""
    path = model_dir(cfg, dataset) / "modelspec.json"
    stored = json.loads(path.read_text(encoding="utf-8"))["spec"]
    return missing_paths(ModelSpec.model_validate(stored).model_dump(), stored)
