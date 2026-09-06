"""config 로딩 — .env 누락·오경로를 명확한 에러로 잡는지 확인한다."""

import pytest

from m3d.config import ConfigError, load_config

ENV_KEYS = (
    "SAMPLE_SOURCE_DIR",
    "REFERENCE_MODELS_DIR",
    "SUPABASE_URL",
    "SUPABASE_PUBLISHABLE_KEY",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_DB_URL",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_WORKSPACE_ID",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """실제 .env 값이 테스트에 새어들지 않게 비운다."""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def absent_env(tmp_path):
    """존재하지 않는 .env 경로 — load_dotenv 가 아무것도 읽지 않게 한다."""
    return tmp_path / "absent.env"


def test_missing_sample_source_dir_raises(absent_env):
    with pytest.raises(ConfigError, match="SAMPLE_SOURCE_DIR"):
        load_config(env_file=absent_env)


def test_nonexistent_sample_source_dir_raises(tmp_path, absent_env, monkeypatch):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path / "없는폴더"))
    with pytest.raises(ConfigError, match="경로가 없습니다"):
        load_config(env_file=absent_env)


def test_derived_source_paths(tmp_path, absent_env, monkeypatch):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    cfg = load_config(env_file=absent_env)
    assert cfg.package_dir == tmp_path / "_정밀조사패키지_P4P5"
    assert cfg.dxf_dir == tmp_path / "_dxf"
    assert cfg.ref_dir == tmp_path / "_참고"
    assert cfg.source_manifest_path == cfg.package_dir / "_manifest.txt"


def test_repo_paths_are_under_repo_root(tmp_path, absent_env, monkeypatch):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    cfg = load_config(env_file=absent_env)
    assert cfg.samples_dir == cfg.repo_root / "data" / "samples"
    assert cfg.manifests_dir == cfg.repo_root / "data" / "manifests"
    assert cfg.fixtures_dir == cfg.repo_root / "data" / "fixtures"
    assert cfg.migrations_dir == cfg.repo_root / "supabase" / "migrations"


def test_derived_dir_is_under_repo_root(tmp_path, absent_env, monkeypatch):
    """M1 산출물 루트 — 재생성 가능물이라 gitignore 대상이다."""
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    cfg = load_config(env_file=absent_env)
    assert cfg.derived_dir == cfg.repo_root / "data" / "derived"


def test_repo_root_contains_claude_md(tmp_path, absent_env, monkeypatch):
    """REPO_ROOT 계산이 어긋나면 이후 모든 경로가 조용히 틀어진다."""
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    cfg = load_config(env_file=absent_env)
    assert (cfg.repo_root / "CLAUDE.md").is_file()


def test_require_db_url_raises_when_unset(tmp_path, absent_env, monkeypatch):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    cfg = load_config(env_file=absent_env)
    with pytest.raises(ConfigError, match="SUPABASE_DB_URL"):
        cfg.require_db_url()


def test_require_reference_models_dir_raises_when_unset(tmp_path, absent_env, monkeypatch):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    cfg = load_config(env_file=absent_env)
    with pytest.raises(ConfigError, match="REFERENCE_MODELS_DIR"):
        cfg.require_reference_models_dir()


def test_blank_env_value_is_treated_as_unset(tmp_path, absent_env, monkeypatch):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    monkeypatch.setenv("SUPABASE_DB_URL", "   ")
    cfg = load_config(env_file=absent_env)
    assert cfg.supabase_db_url is None


def test_model_agent_budget_default_and_env(tmp_path, absent_env, monkeypatch):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    monkeypatch.delenv("MODEL_AGENT_BUDGET_USD", raising=False)
    assert load_config(env_file=absent_env).model_agent_budget_usd == 5.0
    monkeypatch.setenv("MODEL_AGENT_BUDGET_USD", "2.5")
    assert load_config(env_file=absent_env).model_agent_budget_usd == 2.5
