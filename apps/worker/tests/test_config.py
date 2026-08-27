"""설정 — 비밀키는 표시 경로에 원문이 노출되면 안 된다 (CLAUDE.md §3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from model3d_worker.config import (
    Settings,
    known_sample_sources,
    reload_env_cache,
    sample_source_path,
)
from model3d_worker.db import SupabaseNotConfiguredError, SupabaseRest


def test_secrets_are_not_reprd() -> None:
    s = Settings(
        SUPABASE_URL="https://x.supabase.co",
        SUPABASE_SERVICE_KEY="sb_secret_supersecretvalue",
        ANTHROPIC_API_KEY="sk-ant-supersecretvalue",
    )
    for text in (repr(s), str(s), s.model_dump_json()):
        assert "supersecretvalue" not in text
    assert s.supabase_service_key is not None
    assert s.supabase_service_key.get_secret_value() == "sb_secret_supersecretvalue"


def test_configured_flags() -> None:
    assert not Settings(_env_file=None).supabase_configured
    s = Settings(
        _env_file=None,
        SUPABASE_URL="https://x.supabase.co",
        SUPABASE_SERVICE_KEY="k",
    )
    assert s.supabase_configured


def test_db_refuses_without_config() -> None:
    """설정이 없으면 조용히 빈 클라이언트를 만들지 않고 던진다."""
    with pytest.raises(SupabaseNotConfiguredError, match="SUPABASE_URL"):
        SupabaseRest(Settings(_env_file=None))


def test_sample_source_path_strips_quotes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("M3D_SAMPLE_SOURCE_AB1_P4P5", '"D:\\Projects\\원본 폴더"')
    p = sample_source_path("ab1_p4p5")
    assert p is not None
    assert str(p) == "D:\\Projects\\원본 폴더"


def test_sample_source_path_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("M3D_SAMPLE_SOURCE_AB1_P4P5", raising=False)
    assert sample_source_path("ab1_p4p5") is None


def test_known_sample_sources(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("M3D_SAMPLE_SOURCE_FOO", str(tmp_path / "foo"))
    monkeypatch.setenv("M3D_SAMPLE_SOURCE_BAR", "")
    found = known_sample_sources()
    assert "foo" in found
    assert "bar" not in found, "빈 값은 미설정으로 본다"


# ── `.env` 를 실제로 읽는가 (회귀 방지) ───────────────────────────────────
# 이전 구현은 os.environ 만 봤다. pydantic-settings 는 선언된 필드만 읽고 `.env` 값을
# os.environ 에 넣지 않으므로, `.env` 에 적은 M3D_SAMPLE_SOURCE_* 가 **통째로 무시**됐다.
# 문서가 안내하는 워크플로가 전혀 동작하지 않았다. 이 테스트가 그 회귀를 막는다.
def test_sample_source_is_read_from_dotenv_file(env_file: Path, tmp_path: Path) -> None:
    src = tmp_path / "원본_P4P5"
    src.mkdir()
    env_file.write_text(f"M3D_SAMPLE_SOURCE_AB1_P4P5={src}\n", encoding="utf-8")
    reload_env_cache()
    assert sample_source_path("ab1_p4p5") == src


def test_real_env_var_beats_dotenv(
    env_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """셸/CI 가 준 값이 파일보다 세다."""
    env_file.write_text("M3D_SAMPLE_SOURCE_AB1_P4P5=/from/dotenv\n", encoding="utf-8")
    reload_env_cache()
    monkeypatch.setenv("M3D_SAMPLE_SOURCE_AB1_P4P5", "/from/shell")
    assert sample_source_path("ab1_p4p5") == Path("/from/shell")


def test_dotenv_double_quoted_windows_path_is_mangled(env_file: Path) -> None:
    """실측 고정 — 큰따옴표 안 백슬래시는 이스케이프로 해석된다.

    이것은 우리 코드의 버그가 아니라 dotenv 형식의 성질이다. 고칠 수 없으므로
    `.env.example` 과 오류 메시지가 이 사실을 **경고**한다.
    """
    env_file.write_text('M3D_SAMPLE_SOURCE_AB1_P4P5="D:\\Projects\\new\\test"\n', encoding="utf-8")
    reload_env_cache()
    got = sample_source_path("ab1_p4p5")
    assert got is not None
    assert "\n" in str(got), "큰따옴표 안의 \\n 이 개행으로 해석된다"

    env_file.write_text("M3D_SAMPLE_SOURCE_AB1_P4P5=D:\\Projects\\new\\test\n", encoding="utf-8")
    reload_env_cache()
    assert str(sample_source_path("ab1_p4p5")) == "D:\\Projects\\new\\test"
