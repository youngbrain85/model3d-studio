"""워커 설정.

CLAUDE.md §3: **비밀키(Supabase service key 등)는 로컬 `.env` 전용, 커밋·번들 금지.**
그래서 여기서는 비밀값을 ``SecretStr`` 로만 다루고, 어떤 표시 경로에도 원문을 싣지 않는다.

**샘플 원본 경로도 `.env` 전용이다** — 사용자마다 다르므로 커밋될 수 없다.
그런데 pydantic-settings 는 선언된 필드만 읽고 `.env` 값을 ``os.environ`` 에 넣지 않는다.
샘플 세트는 동적으로 늘어나므로 필드로 선언할 수 없다. 그래서 `.env` 를
:func:`dotenv_values` 로 **직접** 읽는다. (이 사실을 모르고 ``os.environ`` 만 보면
`.env` 에 적은 경로가 통째로 무시된다 — 실제로 그런 버그가 있었다.)

우선순위: **실제 환경변수 > `.env`**. CI·셸에서 준 값이 파일보다 세다.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from .contracts.schemas import repo_root

#: 샘플 세트 원본 경로를 주입하는 환경변수 접두사. 예: M3D_SAMPLE_SOURCE_AB1_P4P5
SAMPLE_SOURCE_PREFIX = "M3D_SAMPLE_SOURCE_"


def env_file_path() -> Path:
    """`.env` 는 **리포 루트** 하나뿐이다.

    상대 경로로 두면 실행 위치(cwd)에 따라 읽히기도 하고 안 읽히기도 한다 —
    "왜 내 .env 가 무시되지" 는 그렇게 생긴다.
    """
    return repo_root() / ".env"


class Settings(BaseSettings):
    """환경변수/`.env` 에서 읽는 워커 설정."""

    model_config = SettingsConfigDict(
        env_file=None,  # 아래 __init__ 에서 리포 루트 기준 절대경로로 지정한다
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Supabase (워커는 service key 를 쓴다 — 브라우저에는 절대 넣지 않는다) ──
    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_service_key: SecretStr | None = Field(default=None, alias="SUPABASE_SERVICE_KEY")

    # ── LLM ──
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    # ── 작업 디렉터리 (커밋하지 않는 산출물) ──
    work_dir: Path = Field(default=Path("work"), alias="M3D_WORK_DIR")

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("_env_file", env_file_path())
        super().__init__(**kwargs)  # type: ignore[arg-type]

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)

    @property
    def llm_configured(self) -> bool:
        return self.anthropic_api_key is not None

    def resolved_work_dir(self) -> Path:
        """작업 디렉터리를 리포 루트 기준 절대경로로 돌려준다."""
        return self.work_dir if self.work_dir.is_absolute() else (repo_root() / self.work_dir)


# ── 샘플 원본 경로 (동적 키라 pydantic 필드로 선언할 수 없다) ─────────────
@lru_cache(maxsize=1)
def _dotenv_map() -> dict[str, str]:
    path = env_file_path()
    if not path.is_file():
        return {}
    return {k: v for k, v in dotenv_values(path, encoding="utf-8").items() if v is not None}


def reload_env_cache() -> None:
    """`.env` 캐시를 비운다 (테스트·장기 실행 워커용)."""
    _dotenv_map.cache_clear()
    get_settings.cache_clear()


def sample_source_env_name(set_id: str) -> str:
    """샘플 세트 id → 원본 경로 환경변수 이름."""
    return SAMPLE_SOURCE_PREFIX + set_id.upper().replace("-", "_")


def _clean_raw(value: str) -> str:
    """따옴표로 감싼 값을 벗겨 낸다.

    ``.env`` 파서가 이미 벗기지만, 셸에서 ``VAR='"D:\\a"'`` 처럼 준 경우가 남는다.
    양쪽이 같은 따옴표일 때만 벗긴다 — 경로에 정상적으로 들어간 따옴표를 깎지 않기 위해.
    """
    v = value.strip()
    for q in ('"', "'"):
        if len(v) >= 2 and v[0] == q and v[-1] == q:
            return v[1:-1]
    return v


def raw_sample_source(set_id: str) -> str | None:
    """설정된 원본 경로 **원문**. 우선순위: 실제 환경변수 > `.env`."""
    name = sample_source_env_name(set_id)
    raw = os.environ.get(name)
    if raw is None:
        raw = _dotenv_map().get(name)
    if raw is None:
        return None
    cleaned = _clean_raw(raw)
    return cleaned or None


def sample_source_path(set_id: str) -> Path | None:
    """샘플 세트의 원본 경로. 설정되지 않았으면 None.

    사용자마다 경로가 다르므로 **커밋하지 않는다** — `.env` 로만 주입한다.
    Windows 경로(``D:\\Projects\\...``)와 POSIX 경로를 모두 원문 그대로 받는다.
    POSIX 에서 Windows 경로는 열리지 않는데, 그 사실은 :func:`samples.paths.
    explain_unusable_source` 가 사용자에게 설명한다 — 여기서 조용히 고치지 않는다.
    """
    raw = raw_sample_source(set_id)
    return Path(raw) if raw is not None else None


def known_sample_sources() -> dict[str, Path]:
    """환경(+`.env`)에 설정된 모든 샘플 원본 경로 (세트 id → 경로)."""
    merged: dict[str, str] = dict(_dotenv_map())
    merged.update(os.environ)
    out: dict[str, Path] = {}
    for key, value in merged.items():
        if not key.startswith(SAMPLE_SOURCE_PREFIX):
            continue
        cleaned = _clean_raw(value)
        if cleaned:
            out[key[len(SAMPLE_SOURCE_PREFIX) :].lower()] = Path(cleaned)
    return out


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
