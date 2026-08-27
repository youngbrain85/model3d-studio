"""환경설정 로딩 — 경로와 비밀키를 .env 한 곳에서만 읽는다 (설계서 §8).

참조 원본 경로는 코드에 하드코딩하지 않는다. 반드시 이 모듈을 통과한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# worker/src/m3d/config.py → parents[3] 이 리포 루트
REPO_ROOT = Path(__file__).resolve().parents[3]

PACKAGE_SUBDIR = "_정밀조사패키지_P4P5"
DXF_SUBDIR = "_dxf"
REF_SUBDIR = "_참고"


class ConfigError(RuntimeError):
    """.env 값이 없거나 경로가 실재하지 않을 때."""


@dataclass(frozen=True)
class Config:
    repo_root: Path
    sample_source_dir: Path
    reference_models_dir: Path | None
    supabase_url: str | None
    supabase_publishable_key: str | None
    supabase_service_key: str | None
    supabase_db_url: str | None

    # ── 리포 내부 경로 ──────────────────────────────────────────────
    @property
    def samples_dir(self) -> Path:
        return self.repo_root / "data" / "samples"

    @property
    def manifests_dir(self) -> Path:
        return self.repo_root / "data" / "manifests"

    @property
    def fixtures_dir(self) -> Path:
        return self.repo_root / "data" / "fixtures"

    @property
    def migrations_dir(self) -> Path:
        return self.repo_root / "supabase" / "migrations"

    # ── 원본 경로 (읽기 전용) ───────────────────────────────────────
    @property
    def package_dir(self) -> Path:
        return self.sample_source_dir / PACKAGE_SUBDIR

    @property
    def dxf_dir(self) -> Path:
        return self.sample_source_dir / DXF_SUBDIR

    @property
    def ref_dir(self) -> Path:
        return self.sample_source_dir / REF_SUBDIR

    @property
    def source_manifest_path(self) -> Path:
        return self.package_dir / "_manifest.txt"

    # ── 필수값 요구 ────────────────────────────────────────────────
    def require_db_url(self) -> str:
        if not self.supabase_db_url:
            raise ConfigError(
                "SUPABASE_DB_URL 미설정 — 설계서 §12 선행 작업을 마친 뒤 .env 에 넣으세요."
            )
        return self.supabase_db_url

    def require_reference_models_dir(self) -> Path:
        if self.reference_models_dir is None:
            raise ConfigError("REFERENCE_MODELS_DIR 미설정 — .env 를 확인하세요.")
        return self.reference_models_dir


def _env(key: str) -> str | None:
    """빈 문자열·공백만 있는 값은 미설정으로 본다."""
    value = os.environ.get(key, "").strip()
    return value or None


def load_config(env_file: Path | None = None) -> Config:
    load_dotenv(env_file if env_file is not None else REPO_ROOT / ".env", override=False)

    raw_source = _env("SAMPLE_SOURCE_DIR")
    if not raw_source:
        raise ConfigError(
            "SAMPLE_SOURCE_DIR 미설정 — .env.example 을 복사해 .env 를 만드세요."
        )
    sample_source_dir = Path(raw_source)
    if not sample_source_dir.is_dir():
        raise ConfigError(f"SAMPLE_SOURCE_DIR 경로가 없습니다: {sample_source_dir}")

    raw_models = _env("REFERENCE_MODELS_DIR")
    reference_models_dir = Path(raw_models) if raw_models else None
    if reference_models_dir is not None and not reference_models_dir.is_dir():
        raise ConfigError(f"REFERENCE_MODELS_DIR 경로가 없습니다: {reference_models_dir}")

    return Config(
        repo_root=REPO_ROOT,
        sample_source_dir=sample_source_dir,
        reference_models_dir=reference_models_dir,
        supabase_url=_env("SUPABASE_URL"),
        supabase_publishable_key=_env("SUPABASE_PUBLISHABLE_KEY"),
        supabase_service_key=_env("SUPABASE_SERVICE_KEY"),
        supabase_db_url=_env("SUPABASE_DB_URL"),
    )
