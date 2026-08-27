# M0 리포 부트스트랩 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** worker(Python)·web(React)·Supabase 스키마·샘플 112파일을 세우고, 각각이 실제로 동작함을 실행 출력으로 증명한다.

**Architecture:** 워크스페이스 도구 없는 2-루트 분리(`worker/` + `web/`). worker는 `m3d` typer CLI가 태스크 러너를 겸하고, psycopg로 Supabase에 직결해 마이그레이션을 적용한다. 샘플 원본은 읽기 전용으로 복사하고 SHA256 매니페스트만 커밋한다.

**Tech Stack:** Python 3.12 · typer · pydantic · psycopg[binary] · ezdxf · PyMuPDF · trimesh · numpy · matplotlib / React 18.3 · Vite 6 · TypeScript 5.6 · Mantine 8 · @supabase/supabase-js 2 / PostgreSQL(Supabase)

**정본:** [설계서](../specs/2026-08-27-m0-repo-bootstrap-design.md). 본 계획의 모든 §참조는 설계서 절 번호다.

## Global Constraints

모든 태스크의 요구사항에 아래가 암묵적으로 포함된다.

- **Python은 `py -3.12`** (3.12.6). venv는 `worker/.venv`. Anaconda 3.9(기본 `python`)를 쓰지 않는다.
- **`make`는 이 머신에 없다.** Makefile을 만들지 않는다. 진입점은 `m3d` CLI와 `scripts/*.ps1`.
- **Windows 콘솔은 cp949라 한국어가 깨진다.** 파이썬 실행 전 `PYTHONUTF8=1`을 설정한다.
- **필수 6종:** `ezdxf` `fitz` `trimesh` `numpy` `matplotlib` `psycopg` — 하나라도 import FAIL이면 M0 미완료.
  **선택:** `manifold3d` `claude_agent_sdk` — FAIL해도 M0는 통과, 표에 기록만 한다.
- **web 버전 고정** (web-app-v2와 일치): React `^18.3.1` · Vite `^6.0.5` · TypeScript `~5.6.3` · Mantine `^8.1.0` · `@supabase/supabase-js` `^2.110.7`. **three.js는 M0에 넣지 않는다.**
- **참조 원본은 읽기 전용.** `SAMPLE_SOURCE_DIR` / `REFERENCE_MODELS_DIR` 밑을 절대 쓰지 않는다. 경로는 코드에 하드코딩 금지 — 반드시 `.env` 경유.
- **샘플 고정 수량:** DXF 50 + PDF 1 + PNG 61 = **112파일**, sheets **50**, sheet_pages **61**. 이 숫자가 테스트의 기대값이다.
- **파일명 규칙(§1-4, 전수 검증됨):** DXF `{도면번호}.dxf` / PNG는 `page_count==1`이면 `{ord}_{name}.png`(접미사 없음), `>1`이면 `{ord}_{name}_p{i}.png`. `name`은 `_manifest.txt` 3번째 필드 전체.
- **`_manifest.txt`는 UTF-8·BOM 없음·탭 4필드.** 모든 파일 I/O에 `encoding="utf-8"`을 명시한다.
- **비밀키:** `SUPABASE_SERVICE_KEY`·`SUPABASE_DB_URL`은 worker 전용. `VITE_` 접두 2개만 web 번들에 들어간다. `.env`는 커밋 금지.
- **주석·CLI 출력은 한국어.**
- **커밋 메시지 말미에 반드시:** `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`

### 태스크 순서와 블로커

Task 1~6은 Supabase 키 없이 진행 가능하다. Task 7~8은 §12 선행 작업(프로젝트 생성·키 4개)이 끝나야 실행된다.

| Task | 산출물 | 키 필요 |
|---|---|---|
| 1 | worker 스캐폴드 + config + doctor | 아니오 |
| 2 | fixtures 커밋 + `_manifest.txt` 파서 | 아니오 |
| 3 | 매니페스트 생성·검증 로직 | 아니오 |
| 4 | collect 실행 — 112파일 복사·검증 | 아니오 |
| 5 | 마이그레이션 SQL + Pydantic + contracts 타입 | 아니오 |
| 6 | web 스켈레톤 | 아니오 |
| 7 | `db apply` / `db check` 실제 적용 | **예** |
| 8 | `seed` + §9 8항목 최종 검증 + 스크린샷 | **예** |

---

## Task 1: worker 스캐폴드 + config + doctor

**Files:**
- Modify: `.gitignore`
- Create: `.env.example`
- Create: `scripts/bootstrap.ps1`
- Create: `worker/pyproject.toml`
- Create: `worker/src/m3d/__init__.py`
- Create: `worker/src/m3d/config.py`
- Create: `worker/src/m3d/doctor.py`
- Create: `worker/src/m3d/cli.py`
- Test: `worker/tests/test_config.py`

**Interfaces:**
- Consumes: (없음 — 첫 태스크)
- Produces:
  - `m3d.config.REPO_ROOT: Path`
  - `m3d.config.ConfigError(RuntimeError)`
  - `m3d.config.Config` — frozen dataclass. 필드: `repo_root: Path`, `sample_source_dir: Path`, `reference_models_dir: Path | None`, `supabase_url: str | None`, `supabase_publishable_key: str | None`, `supabase_service_key: str | None`, `supabase_db_url: str | None`. 프로퍼티: `samples_dir`, `manifests_dir`, `fixtures_dir`, `migrations_dir`, `package_dir`, `dxf_dir`, `ref_dir`, `source_manifest_path` (모두 `Path`). 메서드: `require_db_url() -> str`, `require_reference_models_dir() -> Path`
  - `m3d.config.load_config(env_file: Path | None = None) -> Config`
  - `m3d.config.PACKAGE_SUBDIR: str`, `m3d.config.DXF_SUBDIR: str`
  - `m3d.doctor.PackageCheck` — frozen dataclass: `name: str`, `required: bool`, `ok: bool`, `version: str | None`, `error: str | None`
  - `m3d.doctor.run_doctor() -> list[PackageCheck]`, `m3d.doctor.required_failures(checks: list[PackageCheck]) -> list[PackageCheck]`
  - `m3d.cli.app: typer.Typer`

- [ ] **Step 1: `.gitignore` 갱신**

기존 5줄에 아래를 덧붙인다 (전체 내용):

```gitignore
.env
.env.local
node_modules/
__pycache__/
dist/
*.glb
.superpowers/
worker/.venv/
data/samples/
.pytest_cache/
*.egg-info/
```

**주의:** `.superpowers/` 줄을 빠뜨리면 SDD 워크스페이스가 리포에 커밋된다.
현재 `.gitignore` 에 이미 들어 있으니 지우지 말 것.

- [ ] **Step 2: `.env.example` 작성**

```dotenv
# ── 참조 원본 (읽기 전용 — 절대 쓰지 않는다) ──────────────────────────
# 도면 원본 루트. 이 밑에 _dxf/ · _정밀조사패키지_P4P5/ · _참고/ 가 있다.
SAMPLE_SOURCE_DIR=D:\Projects\Inspection\mbi_app_v2\assets\drawings_organized
# 정답지(SPEC_v2.md·재실측 JSON) 위치. fixtures 복사에만 쓴다.
REFERENCE_MODELS_DIR=D:\Projects\Inspection\mbi_app_v2\models_3d\ab1

# ── Supabase (설계서 §12 — 대시보드에서 발급 후 채운다) ────────────────
SUPABASE_URL=
SUPABASE_PUBLISHABLE_KEY=
# 아래 둘은 worker 전용. web 번들·커밋 금지.
SUPABASE_SERVICE_KEY=
SUPABASE_DB_URL=

# ── web 번들에 들어가는 값 (VITE_ 접두 2개만) ─────────────────────────
VITE_SUPABASE_URL=
VITE_SUPABASE_PUBLISHABLE_KEY=
```

- [ ] **Step 3: `worker/pyproject.toml` 작성**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "m3d-worker"
version = "0.1.0"
description = "model3d-studio 파이프라인 워커"
requires-python = ">=3.12,<3.13"
dependencies = [
    "typer>=0.12",
    "python-dotenv>=1.0",
    "pydantic>=2.7",
    "psycopg[binary]>=3.2",
    "ezdxf>=1.3",
    "PyMuPDF>=1.24",
    "trimesh>=4.4",
    "numpy>=1.26",
    "matplotlib>=3.9",
]

# 선택 의존성 — 설치 실패해도 M0 는 통과한다 (설계서 §6-1)
[project.optional-dependencies]
geom = ["manifold3d>=2.5"]
agents = ["claude-agent-sdk>=0.1"]
dev = ["pytest>=8.2"]

[project.scripts]
m3d = "m3d.cli:app"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 4: `worker/src/m3d/__init__.py` 작성**

```python
"""model3d-studio 파이프라인 워커."""

__version__ = "0.1.0"
```

- [ ] **Step 5: 실패하는 config 테스트 작성**

`worker/tests/test_config.py`:

```python
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
```

- [ ] **Step 6: venv 생성 후 테스트가 실패함을 확인**

PowerShell에서:

```powershell
$env:PYTHONUTF8='1'; py -3.12 -m venv worker\.venv; .\worker\.venv\Scripts\python.exe -m pip install -e "worker[dev]"; .\worker\.venv\Scripts\python.exe -m pytest worker\tests -v
```

Expected: `ModuleNotFoundError: No module named 'm3d.config'` 로 collection error (또는 설치 단계에서 `m3d` 패키지 없음 에러).

- [ ] **Step 7: `worker/src/m3d/config.py` 구현**

```python
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
```

- [ ] **Step 8: 테스트가 통과함을 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests -v
```

Expected: 8 passed.

- [ ] **Step 9: `worker/src/m3d/doctor.py` 구현**

```python
"""venv 스택 점검 — 무엇이 되고 무엇이 안 되는지 표로 보고한다 (설계서 §6-1).

전체 실패로 뭉개지 않는다. 필수 6종에 FAIL 이 하나라도 있으면 M0 는 미완료다.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass

REQUIRED = ("ezdxf", "fitz", "trimesh", "numpy", "matplotlib", "psycopg")
OPTIONAL = ("manifold3d", "claude_agent_sdk")


@dataclass(frozen=True)
class PackageCheck:
    name: str
    required: bool
    ok: bool
    version: str | None
    error: str | None


def _check(name: str, required: bool) -> PackageCheck:
    try:
        module = importlib.import_module(name)
    except Exception as exc:  # ImportError 외 DLL 로드 실패도 잡는다
        return PackageCheck(name, required, False, None, f"{type(exc).__name__}: {exc}")

    version = getattr(module, "__version__", None)
    if version is None:
        # PyMuPDF 는 __version__ 대신 VersionBind 를 노출한다
        version = getattr(module, "VersionBind", None)
    return PackageCheck(name, required, True, str(version) if version else "-", None)


def run_doctor() -> list[PackageCheck]:
    return [_check(n, True) for n in REQUIRED] + [_check(n, False) for n in OPTIONAL]


def required_failures(checks: list[PackageCheck]) -> list[PackageCheck]:
    return [c for c in checks if c.required and not c.ok]
```

- [ ] **Step 10: `worker/src/m3d/cli.py` 구현**

```python
"""m3d CLI 엔트리 (설계서 §6). make 가 없는 환경이라 이 CLI 가 태스크 러너를 겸한다."""

from __future__ import annotations

import sys

import typer

from m3d import doctor as doctor_mod

app = typer.Typer(help="model3d-studio 워커 CLI", no_args_is_help=True)


@app.command()
def doctor() -> None:
    """venv 스택 import 점검. 표로 보고하고 종료 코드는 0 을 유지한다."""
    checks = doctor_mod.run_doctor()
    typer.echo(f"{'패키지':<20} {'구분':<4} {'결과':<4} 상세")
    typer.echo("-" * 72)
    for check in checks:
        kind = "필수" if check.required else "선택"
        result = "PASS" if check.ok else "FAIL"
        detail = check.version if check.ok else (check.error or "")
        typer.echo(f"{check.name:<20} {kind:<4} {result:<4} {detail}")

    failures = doctor_mod.required_failures(checks)
    typer.echo("")
    if failures:
        names = ", ".join(f.name for f in failures)
        typer.echo(f"필수 {len(failures)}종 FAIL: {names} — M0 를 완료로 선언하지 마세요.")
    else:
        typer.echo(f"필수 {len(doctor_mod.REQUIRED)}종 PASS.")


if __name__ == "__main__":
    sys.exit(app())
```

- [ ] **Step 11: `scripts/bootstrap.ps1` 작성**

```powershell
# venv 생성·설치 — m3d CLI 를 쓸 수 있게 만드는 단계 (설계서 §1-3).
# make 가 없는 환경이므로 CLI 이전 단계만 여기서 처리한다.
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'

$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root 'worker\.venv'
$python = Join-Path $venv 'Scripts\python.exe'

if (-not (Test-Path $venv)) {
    Write-Host "venv 생성: $venv"
    py -3.12 -m venv $venv
}

& $python -m pip install --upgrade pip
& $python -m pip install -e "$root\worker[dev]"

# 선택 의존성은 실패해도 진행한다 — doctor 표에 FAIL 로 남는다 (설계서 §6-1)
foreach ($extra in @('geom', 'agents')) {
    Write-Host "선택 의존성 설치 시도: $extra"
    & $python -m pip install -e "$root\worker[$extra]"
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "선택 의존성 '$extra' 설치 실패 — doctor 표에 FAIL 로 기록됩니다."
    }
}

& (Join-Path $venv 'Scripts\m3d.exe') doctor
```

- [ ] **Step 12: 부트스트랩 실행 후 doctor 표 확인**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
```

Expected: 8행 표가 출력되고 마지막 줄이 `필수 6종 PASS.` — 필수 6종 중 FAIL이 있으면 **여기서 멈추고 사용자에게 보고**한다(Global Constraints).

- [ ] **Step 13: 커밋**

```bash
git add .gitignore .env.example scripts/bootstrap.ps1 worker/pyproject.toml worker/src worker/tests
git commit -m "$(cat <<'EOF'
feat(worker): m3d 스캐폴드 — config 로딩 + doctor 스택 점검

- config: 경로·비밀키를 .env 한 곳에서만 읽고, 누락·오경로를 ConfigError 로 잡음
- doctor: 필수 6종 / 선택 2종 import 결과를 표로 보고 (전체 실패로 뭉개지 않음)
- make 가 없는 환경이라 scripts/bootstrap.ps1 이 venv 생성만 담당

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: fixtures 커밋 + `_manifest.txt` 파서

**Files:**
- Create: `data/fixtures/ab1-p4p5/` — 원본에서 복사한 텍스트 5파일
- Create: `worker/src/m3d/samples/__init__.py`
- Create: `worker/src/m3d/samples/source_manifest.py`
- Create: `worker/tests/conftest.py`
- Test: `worker/tests/test_source_manifest.py`

**Interfaces:**
- Consumes: `m3d.config.REPO_ROOT`
- Produces:
  - `m3d.samples.source_manifest.SourceManifestError(ValueError)`
  - `m3d.samples.source_manifest.SourceSheet` — frozen dataclass: `ord: str`, `grade: str`, `drawing_no: str`, `title: str`, `page_count: int`
  - `m3d.samples.source_manifest.parse_source_manifest(path: Path) -> list[SourceSheet]`
  - `m3d.samples.source_manifest.png_filenames(sheet: SourceSheet) -> list[str]`
  - `m3d.samples.source_manifest.dxf_filename(sheet: SourceSheet) -> str`
  - pytest fixture `fixtures_dir -> Path` (in `conftest.py`)

- [ ] **Step 1: fixtures 5파일 복사 (원본은 읽기만)**

`data/fixtures/ab1-p4p5/` 아래로 복사한다. 원본 수정 금지(§6-2).

```powershell
$env:PYTHONUTF8='1'
$dst = 'data\fixtures\ab1-p4p5'
New-Item -ItemType Directory -Force $dst | Out-Null
$pkg = Join-Path $env:SAMPLE_SOURCE_DIR '_정밀조사패키지_P4P5'
$ref = Join-Path $env:SAMPLE_SOURCE_DIR '_참고'
Copy-Item (Join-Path $pkg '_manifest.txt')            $dst
Copy-Item (Join-Path $pkg 'README.md')                (Join-Path $dst '패키지_README.md')
Copy-Item (Join-Path $ref '접속1교_실측정리.md')       $dst
Copy-Item (Join-Path $env:REFERENCE_MODELS_DIR 'SPEC_v2.md')                $dst
Copy-Item (Join-Path $env:REFERENCE_MODELS_DIR 'measure_ab1_p4p5_v2.json')  $dst
Get-ChildItem $dst | Select-Object Name, Length
```

`.env`가 셸에 로드되어 있지 않으면 `$env:SAMPLE_SOURCE_DIR` 등을 먼저 설정한다.
`README.md`는 리포에 같은 이름이 흔하므로 `패키지_README.md`로 이름을 바꿔 넣는다.

Expected: 5파일, 합계 약 55KB.

- [ ] **Step 2: `worker/tests/conftest.py` 작성**

```python
"""테스트 공용 픽스처."""

from pathlib import Path

import pytest

from m3d.config import REPO_ROOT


@pytest.fixture
def fixtures_dir() -> Path:
    """커밋된 정답지·카탈로그 사본 (설계서 §1-2)."""
    return REPO_ROOT / "data" / "fixtures" / "ab1-p4p5"
```

- [ ] **Step 3: 실패하는 파서 테스트 작성**

`worker/tests/test_source_manifest.py`:

```python
"""_manifest.txt 파서 — 카탈로그 정답의 유일한 입구다.

실제 커밋된 fixture(50행)로 회귀를 걸고, 형식 오류는 합성 데이터로 검증한다.
"""

import re

import pytest

from m3d.samples.source_manifest import (
    SourceManifestError,
    SourceSheet,
    dxf_filename,
    parse_source_manifest,
    png_filenames,
)


@pytest.fixture
def sheets(fixtures_dir):
    return parse_source_manifest(fixtures_dir / "_manifest.txt")


def test_parses_50_rows(sheets):
    assert len(sheets) == 50


def test_page_count_sum_matches_png_total(sheets):
    """합계 61 = 실제 PNG 파일 수. 검산 없는 수치는 싣지 않는다 (지식베이스 §2)."""
    assert sum(s.page_count for s in sheets) == 61


def test_grade_split(sheets):
    assert {s.grade for s in sheets} == {"핵심", "참고"}
    assert sum(1 for s in sheets if s.grade == "핵심") == 43
    assert sum(1 for s in sheets if s.grade == "참고") == 7


def test_drawing_numbers_unique_and_well_formed(sheets):
    assert len({s.drawing_no for s in sheets}) == 50
    assert all(re.fullmatch(r"C\d{7}-\d{3}", s.drawing_no) for s in sheets)


def test_ords_unique(sheets):
    assert len({s.ord for s in sheets}) == 50


def test_titles_are_not_empty(sheets):
    assert all(s.title for s in sheets)


def test_png_filenames_single_page_has_no_suffix():
    """설계서 §1-4 — 1페이지 시트는 _p1 접미사가 붙지 않는다."""
    sheet = SourceSheet(
        ord="A02",
        grade="참고",
        drawing_no="C0050301-002",
        title="교량제원및특기사항(2)(접속1교)",
        page_count=1,
    )
    assert png_filenames(sheet) == ["A02_C0050301-002_교량제원및특기사항(2)(접속1교).png"]


def test_png_filenames_multi_page_uses_p_suffix():
    sheet = SourceSheet(
        ord="A01",
        grade="참고",
        drawing_no="C0050301-001",
        title="교량제원및특기사항(1)(접속1교)_(6차변경)",
        page_count=2,
    )
    assert png_filenames(sheet) == [
        "A01_C0050301-001_교량제원및특기사항(1)(접속1교)_(6차변경)_p1.png",
        "A01_C0050301-001_교량제원및특기사항(1)(접속1교)_(6차변경)_p2.png",
    ]


def test_png_filename_total_is_61(sheets):
    assert sum(len(png_filenames(s)) for s in sheets) == 61


def test_dxf_filename():
    sheet = SourceSheet(
        ord="C01",
        grade="핵심",
        drawing_no="C0050304-030",
        title="강상형일반도(5)(접속1교)",
        page_count=1,
    )
    assert dxf_filename(sheet) == "C0050304-030.dxf"


def _write(tmp_path, line):
    path = tmp_path / "_manifest.txt"
    path.write_text(line + "\n", encoding="utf-8")
    return path


def test_wrong_field_count_raises(tmp_path):
    path = _write(tmp_path, "A01\t참고\tC0050301-001_제목")
    with pytest.raises(SourceManifestError, match="탭 4필드"):
        parse_source_manifest(path)


def test_unknown_grade_raises(tmp_path):
    path = _write(tmp_path, "A01\t중요\tC0050301-001_제목\t1p")
    with pytest.raises(SourceManifestError, match="등급"):
        parse_source_manifest(path)


def test_bad_drawing_no_raises(tmp_path):
    path = _write(tmp_path, "A01\t참고\tX999_제목\t1p")
    with pytest.raises(SourceManifestError, match="도면번호"):
        parse_source_manifest(path)


def test_bad_page_format_raises(tmp_path):
    path = _write(tmp_path, "A01\t참고\tC0050301-001_제목\t2쪽")
    with pytest.raises(SourceManifestError, match="페이지수"):
        parse_source_manifest(path)


def test_blank_lines_are_skipped(tmp_path):
    path = tmp_path / "_manifest.txt"
    path.write_text("\nA01\t참고\tC0050301-001_제목\t1p\n\n", encoding="utf-8")
    assert len(parse_source_manifest(path)) == 1
```

- [ ] **Step 4: 테스트가 실패함을 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests\test_source_manifest.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'm3d.samples'`

- [ ] **Step 5: `worker/src/m3d/samples/__init__.py` 작성**

```python
"""샘플 도면 세트 수집·검증."""
```

- [ ] **Step 6: `worker/src/m3d/samples/source_manifest.py` 구현**

```python
"""원본 `_manifest.txt` 파서 (설계서 §1-4).

형식: 탭 4필드 — `접두 / 등급 / 도면번호_제목 / 페이지수`. UTF-8, BOM 없음.
파일명 유도 규칙도 여기 둔다 — 둘 다 이 한 행에서 나오므로 함께 산다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DRAWING_NO_RE = re.compile(r"^(C\d{7}-\d{3})_(.+)$")
PAGES_RE = re.compile(r"^(\d+)p$")
VALID_GRADES = ("핵심", "참고")


class SourceManifestError(ValueError):
    """`_manifest.txt` 형식 위반."""


@dataclass(frozen=True)
class SourceSheet:
    ord: str
    grade: str
    drawing_no: str
    title: str
    page_count: int


def parse_source_manifest(path: Path) -> list[SourceSheet]:
    sheets: list[SourceSheet] = []
    text = path.read_text(encoding="utf-8")

    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue

        fields = line.split("\t")
        if len(fields) != 4:
            raise SourceManifestError(
                f"{path}:{lineno} 탭 4필드가 아닙니다 ({len(fields)}개): {line!r}"
            )

        ord_, grade, name, pages = (f.strip() for f in fields)

        if grade not in VALID_GRADES:
            raise SourceManifestError(
                f"{path}:{lineno} 알 수 없는 등급 {grade!r} (허용: {VALID_GRADES})"
            )

        name_match = DRAWING_NO_RE.match(name)
        if name_match is None:
            raise SourceManifestError(f"{path}:{lineno} 도면번호 추출 실패: {name!r}")

        pages_match = PAGES_RE.match(pages)
        if pages_match is None:
            raise SourceManifestError(f"{path}:{lineno} 페이지수 형식 오류: {pages!r}")

        sheets.append(
            SourceSheet(
                ord=ord_,
                grade=grade,
                drawing_no=name_match.group(1),
                title=name_match.group(2),
                page_count=int(pages_match.group(1)),
            )
        )

    return sheets


def png_filenames(sheet: SourceSheet) -> list[str]:
    """설계서 §1-4 — 1페이지는 접미사 없음, 여러 페이지는 `_p{i}`."""
    stem = f"{sheet.ord}_{sheet.drawing_no}_{sheet.title}"
    if sheet.page_count == 1:
        return [f"{stem}.png"]
    return [f"{stem}_p{i}.png" for i in range(1, sheet.page_count + 1)]


def dxf_filename(sheet: SourceSheet) -> str:
    return f"{sheet.drawing_no}.dxf"
```

- [ ] **Step 7: 테스트가 통과함을 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests -v
```

Expected: 23 passed (config 8 + source_manifest 15).

- [ ] **Step 8: 커밋**

```bash
git add data/fixtures worker/src/m3d/samples worker/tests/conftest.py worker/tests/test_source_manifest.py
git commit -m "$(cat <<'EOF'
feat(worker): _manifest.txt 파서 + 정답지 fixtures 커밋

- fixtures 5파일(55KB) 커밋 — SPEC_v2·재실측 JSON·실측정리·패키지 README·_manifest.txt
- 파서: 탭 4필드·등급·도면번호·페이지수를 각각 명확한 에러로 검증
- 파일명 유도(png_filenames/dxf_filename)를 같은 모듈에 둠 — 한 행에서 나오는 값들
- 회귀 기대값: 50행 / page_count 합 61 / 핵심 43 · 참고 7

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 매니페스트 생성·검증 로직

**Files:**
- Create: `worker/src/m3d/samples/manifest.py`
- Test: `worker/tests/test_manifest.py`

**Interfaces:**
- Consumes: (없음 — 순수 로직)
- Produces:
  - `m3d.samples.manifest.SCHEMA_VERSION: int` (= 1)
  - `m3d.samples.manifest.ManifestEntry` — frozen dataclass: `rel_path: str`, `source_rel: str`, `kind: str`, `role: str`, `bytes: int`, `sha256: str`, `ord: str | None = None`, `drawing_no: str | None = None`, `page_no: int | None = None`
  - `m3d.samples.manifest.Manifest` — frozen dataclass: `dataset: str`, `entries: tuple[ManifestEntry, ...]`; 프로퍼티 `total_bytes: int`
  - `m3d.samples.manifest.VerifyReport` — frozen dataclass: `checked: int`, `missing: tuple[str, ...]`, `extra: tuple[str, ...]`, `mismatched: tuple[str, ...]`; 프로퍼티 `ok: bool`
  - `m3d.samples.manifest.sha256_file(path: Path) -> str`
  - `m3d.samples.manifest.write_manifest(manifest: Manifest, path: Path) -> None`
  - `m3d.samples.manifest.load_manifest(path: Path) -> Manifest`
  - `m3d.samples.manifest.verify_manifest(manifest: Manifest, repo_root: Path) -> VerifyReport`

**설계서와의 차이 1건(의도적):** §3은 매니페스트에 "출처경로"를 담는다고 했으나, 절대경로를 커밋하면 머신별 경로가 리포에 박힌다. `source_rel`(= `SAMPLE_SOURCE_DIR` 기준 상대경로, POSIX)로 담는다. 재현성은 같고 유출은 없다.

- [ ] **Step 1: 실패하는 매니페스트 테스트 작성**

`worker/tests/test_manifest.py`:

```python
"""매니페스트 — 413MB 를 커밋하지 않고도 무결성을 증명하는 유일한 수단."""

import hashlib
import json

import pytest

from m3d.samples.manifest import (
    Manifest,
    ManifestEntry,
    SCHEMA_VERSION,
    load_manifest,
    sha256_file,
    verify_manifest,
    write_manifest,
)

DATASET = "ab1-p4p5"


def _make_file(repo_root, rel_path, content: bytes) -> ManifestEntry:
    """repo_root 아래에 파일을 만들고 그에 대응하는 엔트리를 돌려준다."""
    target = repo_root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return ManifestEntry(
        rel_path=rel_path,
        source_rel=f"_dxf/{target.name}",
        kind="dxf",
        role="source",
        bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        ord="C01",
        drawing_no="C0050304-030",
    )


@pytest.fixture
def repo(tmp_path):
    return tmp_path


@pytest.fixture
def manifest(repo):
    entries = (
        _make_file(repo, f"data/samples/{DATASET}/dxf/a.dxf", b"alpha"),
        _make_file(repo, f"data/samples/{DATASET}/dxf/b.dxf", b"bravo"),
    )
    return Manifest(dataset=DATASET, entries=entries)


def test_sha256_file_matches_hashlib(repo):
    path = repo / "x.bin"
    path.write_bytes(b"hello world")
    assert sha256_file(path) == hashlib.sha256(b"hello world").hexdigest()


def test_total_bytes(manifest):
    assert manifest.total_bytes == len(b"alpha") + len(b"bravo")


def test_write_load_roundtrip(repo, manifest):
    path = repo / "data/manifests/ab1-p4p5.json"
    write_manifest(manifest, path)
    assert load_manifest(path) == manifest


def test_written_json_is_utf8_and_has_counts(repo, manifest):
    path = repo / "data/manifests/ab1-p4p5.json"
    write_manifest(manifest, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == SCHEMA_VERSION
    assert payload["dataset"] == DATASET
    assert payload["file_count"] == 2
    assert payload["total_bytes"] == manifest.total_bytes


def test_verify_ok(repo, manifest):
    report = verify_manifest(manifest, repo)
    assert report.ok
    assert report.checked == 2


def test_verify_detects_missing(repo, manifest):
    (repo / manifest.entries[0].rel_path).unlink()
    report = verify_manifest(manifest, repo)
    assert not report.ok
    assert report.missing == (manifest.entries[0].rel_path,)


def test_verify_detects_content_change(repo, manifest):
    (repo / manifest.entries[1].rel_path).write_bytes(b"CHANGED")
    report = verify_manifest(manifest, repo)
    assert not report.ok
    assert report.mismatched == (manifest.entries[1].rel_path,)


def test_verify_detects_same_size_content_change(repo, manifest):
    """크기가 같아도 내용이 바뀌면 잡아야 한다 — 크기만 보면 놓친다."""
    (repo / manifest.entries[0].rel_path).write_bytes(b"ALPHA")
    report = verify_manifest(manifest, repo)
    assert report.mismatched == (manifest.entries[0].rel_path,)


def test_verify_detects_extra_file(repo, manifest):
    stray = repo / f"data/samples/{DATASET}/dxf/stray.dxf"
    stray.write_bytes(b"unlisted")
    report = verify_manifest(manifest, repo)
    assert not report.ok
    assert report.extra == (f"data/samples/{DATASET}/dxf/stray.dxf",)


def test_load_rejects_wrong_schema(repo, manifest):
    path = repo / "m.json"
    write_manifest(manifest, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema"] = 99
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        load_manifest(path)


def test_load_rejects_count_mismatch(repo, manifest):
    path = repo / "m.json"
    write_manifest(manifest, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["file_count"] = 99
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="file_count"):
        load_manifest(path)
```

- [ ] **Step 2: 테스트가 실패함을 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests\test_manifest.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'm3d.samples.manifest'`

- [ ] **Step 3: `worker/src/m3d/samples/manifest.py` 구현**

```python
"""샘플 매니페스트 — 112파일 SHA256 정본 (설계서 §6-2·§9).

413MB 바이너리는 커밋하지 않는다. 리포에 남는 이 JSON 이 무결성의 유일한 증거다.
원본 절대경로는 담지 않는다(머신 종속·경로 유출) — SAMPLE_SOURCE_DIR 기준 상대경로만.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

SCHEMA_VERSION = 1
CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ManifestEntry:
    rel_path: str            # 리포 루트 기준 POSIX 상대경로
    source_rel: str          # SAMPLE_SOURCE_DIR 기준 POSIX 상대경로
    kind: str                # dxf | pdf | png
    role: str                # source | derived
    bytes: int
    sha256: str
    ord: str | None = None
    drawing_no: str | None = None
    page_no: int | None = None


@dataclass(frozen=True)
class Manifest:
    dataset: str
    entries: tuple[ManifestEntry, ...]

    @property
    def total_bytes(self) -> int:
        return sum(e.bytes for e in self.entries)


@dataclass(frozen=True)
class VerifyReport:
    checked: int
    missing: tuple[str, ...]
    extra: tuple[str, ...]
    mismatched: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not (self.missing or self.extra or self.mismatched)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(manifest: Manifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA_VERSION,
        "dataset": manifest.dataset,
        "file_count": len(manifest.entries),
        "total_bytes": manifest.total_bytes,
        "entries": [asdict(entry) for entry in manifest.entries],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_manifest(path: Path) -> Manifest:
    payload = json.loads(path.read_text(encoding="utf-8"))

    if payload.get("schema") != SCHEMA_VERSION:
        raise ValueError(
            f"매니페스트 schema 불일치: {payload.get('schema')!r} (기대 {SCHEMA_VERSION})"
        )

    entries = tuple(ManifestEntry(**entry) for entry in payload["entries"])
    if len(entries) != payload["file_count"]:
        raise ValueError(
            f"file_count({payload['file_count']}) 와 entries 길이({len(entries)}) 가 "
            "다릅니다 — 매니페스트가 손상되었습니다."
        )

    return Manifest(dataset=payload["dataset"], entries=entries)


def verify_manifest(manifest: Manifest, repo_root: Path) -> VerifyReport:
    """목록 대비 누락·변조·여분을 모두 본다.

    여분(목록에 없는 파일)까지 잡아야 '이 폴더가 매니페스트와 같다' 고 말할 수 있다.
    """
    missing: list[str] = []
    mismatched: list[str] = []

    for entry in manifest.entries:
        target = repo_root / entry.rel_path
        if not target.is_file():
            missing.append(entry.rel_path)
            continue
        if target.stat().st_size != entry.bytes or sha256_file(target) != entry.sha256:
            mismatched.append(entry.rel_path)

    listed = {entry.rel_path for entry in manifest.entries}
    dataset_root = repo_root / "data" / "samples" / manifest.dataset
    present: set[str] = set()
    if dataset_root.is_dir():
        present = {
            path.relative_to(repo_root).as_posix()
            for path in dataset_root.rglob("*")
            if path.is_file()
        }

    return VerifyReport(
        checked=len(manifest.entries),
        missing=tuple(missing),
        extra=tuple(sorted(present - listed)),
        mismatched=tuple(mismatched),
    )
```

- [ ] **Step 4: 테스트가 통과함을 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests -v
```

Expected: 34 passed (config 8 + source_manifest 15 + manifest 11).

- [ ] **Step 5: 커밋**

```bash
git add worker/src/m3d/samples/manifest.py worker/tests/test_manifest.py
git commit -m "feat(worker): 샘플 매니페스트 생성·검증

- SHA256 기반 무결성 검증 — 누락·변조·여분 3종을 모두 검출
- 크기가 같은 내용 변경도 잡는지 회귀 테스트로 고정
- 원본 절대경로 대신 SAMPLE_SOURCE_DIR 기준 상대경로만 기록 (머신 종속 제거)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: collect 실행 — 112파일 복사·검증

**Files:**
- Create: `worker/src/m3d/samples/collect.py`
- Modify: `worker/src/m3d/cli.py` (samples 서브앱 추가)
- Create: `data/manifests/ab1-p4p5.json` (생성물, 커밋)
- Test: `worker/tests/test_collect.py`

**Interfaces:**
- Consumes: `m3d.config.Config`, `m3d.samples.source_manifest.{SourceSheet, parse_source_manifest, png_filenames, dxf_filename}`, `m3d.samples.manifest.{Manifest, ManifestEntry, sha256_file, write_manifest, load_manifest, verify_manifest}`
- Produces:
  - `m3d.samples.collect.DATASET: str` (= `"ab1-p4p5"`)
  - `m3d.samples.collect.PDF_NAME: str` (= `"P4P5_정밀조사_도면집.pdf"`)
  - `m3d.samples.collect.CollectError(RuntimeError)`
  - `m3d.samples.collect.PlannedFile` — frozen dataclass: `source: Path`, `source_rel: str`, `rel_path: str`, `kind: str`, `role: str`, `ord: str | None`, `drawing_no: str | None`, `page_no: int | None`
  - `m3d.samples.collect.plan_files(cfg: Config, sheets: list[SourceSheet]) -> list[PlannedFile]` — 파일시스템을 건드리지 않는 순수 함수
  - `m3d.samples.collect.collect(cfg: Config) -> Manifest`
  - `m3d.samples.collect.manifest_path(cfg: Config) -> Path`

- [ ] **Step 1: 실패하는 plan 테스트 작성**

`worker/tests/test_collect.py`:

```python
"""collect 계획 — 실제 413MB 복사 없이 '무엇을 어디로' 만 검증한다."""

import pytest

from m3d.config import load_config
from m3d.samples.collect import DATASET, PDF_NAME, plan_files
from m3d.samples.source_manifest import parse_source_manifest


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    for key in ("SAMPLE_SOURCE_DIR", "REFERENCE_MODELS_DIR", "SUPABASE_DB_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    return load_config(env_file=tmp_path / "absent.env")


@pytest.fixture
def planned(cfg, fixtures_dir):
    sheets = parse_source_manifest(fixtures_dir / "_manifest.txt")
    return plan_files(cfg, sheets)


def test_plans_112_files(planned):
    assert len(planned) == 112


def test_kind_counts(planned):
    counts: dict[str, int] = {}
    for item in planned:
        counts[item.kind] = counts.get(item.kind, 0) + 1
    assert counts == {"dxf": 50, "png": 61, "pdf": 1}


def test_roles(planned):
    """DXF·PDF 는 [1] 업로드 입력(source), PNG 는 [2] 변환 산출물(derived)."""
    for item in planned:
        expected = "derived" if item.kind == "png" else "source"
        assert item.role == expected, item.rel_path


def test_rel_paths_unique(planned):
    assert len({item.rel_path for item in planned}) == 112


def test_rel_paths_are_under_dataset_dir(planned):
    prefix = f"data/samples/{DATASET}/"
    assert all(item.rel_path.startswith(prefix) for item in planned)
    assert all("\\" not in item.rel_path for item in planned)


def test_dxf_entries_have_no_page_no(planned):
    dxf = [i for i in planned if i.kind == "dxf"]
    assert len(dxf) == 50
    assert all(i.page_no is None and i.drawing_no is not None for i in dxf)


def test_png_page_numbers_start_at_one_per_sheet(planned):
    pages: dict[str, list[int]] = {}
    for item in planned:
        if item.kind == "png":
            pages.setdefault(item.ord, []).append(item.page_no)
    assert len(pages) == 50
    for ord_, page_nos in pages.items():
        assert page_nos == list(range(1, len(page_nos) + 1)), ord_


def test_pdf_entry_has_no_sheet_linkage(planned):
    pdf = [i for i in planned if i.kind == "pdf"]
    assert len(pdf) == 1
    assert pdf[0].ord is None and pdf[0].drawing_no is None and pdf[0].page_no is None
    assert pdf[0].rel_path == f"data/samples/{DATASET}/pdf/{PDF_NAME}"


def test_sources_point_into_configured_dirs(cfg, planned):
    for item in planned:
        if item.kind == "dxf":
            assert item.source.parent == cfg.dxf_dir
        else:
            assert item.source.parent == cfg.package_dir


def test_source_rel_is_posix_relative(planned):
    assert all(not item.source_rel.startswith("/") for item in planned)
    assert all("\\" not in item.source_rel for item in planned)
```

- [ ] **Step 2: 테스트가 실패함을 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests\test_collect.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'm3d.samples.collect'`

- [ ] **Step 3: `worker/src/m3d/samples/collect.py` 구현**

```python
"""원본 → data/samples 복사 (설계서 §6-2).

원본은 읽기만 한다. 복사 후 사본 해시를 원본 해시와 대조하고, 원본의 크기·mtime 이
그대로인지도 확인한다. 재실행은 멱등 — 이미 같은 파일이면 건너뛴다.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from m3d.config import DXF_SUBDIR, PACKAGE_SUBDIR, Config
from m3d.samples.manifest import Manifest, ManifestEntry, sha256_file
from m3d.samples.source_manifest import (
    SourceSheet,
    dxf_filename,
    parse_source_manifest,
    png_filenames,
)

DATASET = "ab1-p4p5"
PDF_NAME = "P4P5_정밀조사_도면집.pdf"


class CollectError(RuntimeError):
    """원본 누락·복사 실패·원본 변경."""


@dataclass(frozen=True)
class PlannedFile:
    source: Path
    source_rel: str
    rel_path: str
    kind: str
    role: str
    ord: str | None
    drawing_no: str | None
    page_no: int | None


def manifest_path(cfg: Config) -> Path:
    return cfg.manifests_dir / f"{DATASET}.json"


def plan_files(cfg: Config, sheets: list[SourceSheet]) -> list[PlannedFile]:
    """무엇을 어디로 복사할지 결정한다. 파일시스템을 건드리지 않는다."""
    base = f"data/samples/{DATASET}"
    planned: list[PlannedFile] = []

    for sheet in sheets:
        dxf = dxf_filename(sheet)
        planned.append(
            PlannedFile(
                source=cfg.dxf_dir / dxf,
                source_rel=f"{DXF_SUBDIR}/{dxf}",
                rel_path=f"{base}/dxf/{dxf}",
                kind="dxf",
                role="source",
                ord=sheet.ord,
                drawing_no=sheet.drawing_no,
                page_no=None,
            )
        )
        for page_no, png in enumerate(png_filenames(sheet), start=1):
            planned.append(
                PlannedFile(
                    source=cfg.package_dir / png,
                    source_rel=f"{PACKAGE_SUBDIR}/{png}",
                    rel_path=f"{base}/png/{png}",
                    kind="png",
                    role="derived",
                    ord=sheet.ord,
                    drawing_no=sheet.drawing_no,
                    page_no=page_no,
                )
            )

    planned.append(
        PlannedFile(
            source=cfg.package_dir / PDF_NAME,
            source_rel=f"{PACKAGE_SUBDIR}/{PDF_NAME}",
            rel_path=f"{base}/pdf/{PDF_NAME}",
            kind="pdf",
            role="source",
            ord=None,
            drawing_no=None,
            page_no=None,
        )
    )
    return planned


def _copy_one(item: PlannedFile, repo_root: Path) -> tuple[ManifestEntry, bool]:
    """한 파일을 복사(또는 건너뜀)하고 (엔트리, 복사했는지) 를 돌려준다."""
    if not item.source.is_file():
        raise CollectError(f"원본이 없습니다: {item.source}")

    before = item.source.stat()
    source_hash = sha256_file(item.source)

    dest = repo_root / item.rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)

    copied = False
    already_same = (
        dest.is_file()
        and dest.stat().st_size == before.st_size
        and sha256_file(dest) == source_hash
    )
    if not already_same:
        shutil.copy2(item.source, dest)
        if sha256_file(dest) != source_hash:
            raise CollectError(f"복사 후 해시가 다릅니다: {item.rel_path}")
        copied = True

    after = item.source.stat()
    if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
        raise CollectError(
            f"원본이 변경되었습니다 — 즉시 중단합니다: {item.source} "
            "(참조 원본은 읽기 전용이어야 합니다)"
        )

    entry = ManifestEntry(
        rel_path=item.rel_path,
        source_rel=item.source_rel,
        kind=item.kind,
        role=item.role,
        bytes=before.st_size,
        sha256=source_hash,
        ord=item.ord,
        drawing_no=item.drawing_no,
        page_no=item.page_no,
    )
    return entry, copied


def collect(cfg: Config) -> Manifest:
    sheets = parse_source_manifest(cfg.source_manifest_path)
    planned = plan_files(cfg, sheets)

    entries: list[ManifestEntry] = []
    copied_count = 0
    for item in planned:
        entry, copied = _copy_one(item, cfg.repo_root)
        entries.append(entry)
        copied_count += int(copied)

    print(f"복사 {copied_count}개 / 건너뜀 {len(planned) - copied_count}개")
    return Manifest(dataset=DATASET, entries=tuple(entries))
```

- [ ] **Step 4: 테스트가 통과함을 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests -v
```

Expected: 44 passed (config 8 + source_manifest 15 + manifest 11 + collect 10).

- [ ] **Step 5: CLI 에 samples 서브앱 추가**

`worker/src/m3d/cli.py` 의 import 블록을 아래로 교체한다:

```python
import typer

from m3d import doctor as doctor_mod
from m3d.config import load_config
from m3d.samples.collect import DATASET, collect, manifest_path
from m3d.samples.manifest import load_manifest, verify_manifest, write_manifest
```

`if __name__ == "__main__":` 앞에 아래를 추가한다:

```python
samples_app = typer.Typer(help="샘플 도면 세트 수집·검증", no_args_is_help=True)
app.add_typer(samples_app, name="samples")


@samples_app.command("collect")
def samples_collect() -> None:
    """원본을 data/samples 로 복사하고 매니페스트를 생성한다."""
    cfg = load_config()
    manifest = collect(cfg)
    path = manifest_path(cfg)
    write_manifest(manifest, path)
    size_mb = manifest.total_bytes / 1024 / 1024
    typer.echo(f"데이터셋 {DATASET}: {len(manifest.entries)}파일 / {size_mb:.1f} MB")
    typer.echo(f"매니페스트: {path}")


@samples_app.command("verify")
def samples_verify() -> None:
    """매니페스트와 실제 파일을 대조한다. 불일치가 있으면 종료 코드 1."""
    cfg = load_config()
    manifest = load_manifest(manifest_path(cfg))
    report = verify_manifest(manifest, cfg.repo_root)

    if report.ok:
        typer.echo(f"{report.checked}/{report.checked} SHA256 일치 — PASS")
        raise typer.Exit(code=0)

    typer.echo(f"검사 {report.checked}개 — FAIL")
    for label, items in (
        ("누락", report.missing),
        ("변조", report.mismatched),
        ("여분", report.extra),
    ):
        if not items:
            continue
        typer.echo(f"  {label} {len(items)}개:")
        for rel_path in items[:10]:
            typer.echo(f"    {rel_path}")
        if len(items) > 10:
            typer.echo(f"    … 외 {len(items) - 10}개")
    raise typer.Exit(code=1)
```

- [ ] **Step 6: 실제 112파일 복사 실행**

`.env` 에 `SAMPLE_SOURCE_DIR` 이 채워져 있어야 한다.

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\m3d.exe samples collect
```

Expected: `복사 112개 / 건너뜀 0개` → `데이터셋 ab1-p4p5: 112파일 / 413.1 MB`

- [ ] **Step 7: 검증 실행**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\m3d.exe samples verify; Write-Host "exit=$LASTEXITCODE"
```

Expected: `112/112 SHA256 일치 — PASS`, `exit=0`

- [ ] **Step 8: 멱등성 확인 (재실행)**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\m3d.exe samples collect
```

Expected: `복사 0개 / 건너뜀 112개` — 두 번째 실행은 아무것도 복사하지 않는다.

- [ ] **Step 9: `data/samples` 가 git 에 잡히지 않는지 확인**

```bash
git status --short | grep -q "data/samples" && echo "실패: 413MB 가 추적되고 있음" || echo "OK: gitignore 적용됨"
```

Expected: `OK: gitignore 적용됨`

- [ ] **Step 10: 커밋**

```bash
git add worker/src/m3d/samples/collect.py worker/src/m3d/cli.py worker/tests/test_collect.py data/manifests/ab1-p4p5.json
git commit -m "feat(worker): samples collect/verify — 112파일 복사·해시 검증

- plan_files 를 순수 함수로 분리해 413MB 복사 없이 계획을 테스트
- 복사 후 사본 해시 대조 + 원본 크기·mtime 불변 확인 (참조 원본 보호)
- 재실행 멱등: 이미 같은 파일이면 건너뜀
- 매니페스트 커밋 (112파일 SHA256), data/samples 자체는 gitignore

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: 마이그레이션 SQL + Pydantic 모델 + contracts 타입

**Files:**
- Create: `supabase/migrations/0001_init.sql`
- Create: `worker/src/m3d/models.py`
- Create: `contracts/db.types.ts`
- Create: `contracts/README.md`
- Test: `worker/tests/test_models.py`
- Test: `worker/tests/test_migration_sql.py`

**Interfaces:**
- Consumes: `m3d.config.REPO_ROOT`
- Produces:
  - `m3d.models.GRADES: tuple[str, ...]` (= `("핵심", "참고")`)
  - `m3d.models.CATALOG_STATUSES: tuple[str, ...]` (= `("unverified", "match", "mismatch", "unreadable")`)
  - `m3d.models.ASSET_KINDS: tuple[str, ...]` (= `("dxf", "pdf", "png", "photo")`)
  - `m3d.models.ASSET_ROLES: tuple[str, ...]` (= `("source", "derived")`)
  - `m3d.models.ProjectRow(BaseModel)` — `slug: str`, `name: str`, `structure: str | None`, `coord_system: dict[str, Any]`, `coord_assumptions: list[str]`
  - `m3d.models.SheetRow(BaseModel)` — `ord: str`, `drawing_no_from_filename: str`, `title_from_filename: str`, `grade: Literal`, `page_count: int`, `catalog_status: Literal = "unverified"`
  - `m3d.models.SheetPageRow(BaseModel)` — `ord: str`, `page_no: int`
  - `m3d.models.AssetRow(BaseModel)` — `kind: Literal`, `role: Literal`, `rel_path: str`, `bytes: int`, `sha256: str`, `ord: str | None`, `page_no: int | None`
  - `contracts/db.types.ts` — `export type Database` (Supabase 클라이언트 제네릭용)
- 이 태스크는 SQL을 **작성만** 한다. 적용은 Task 7.

- [ ] **Step 1: `supabase/migrations/0001_init.sql` 작성**

설계서 §4 전문을 그대로 옮기고 RLS 정책 4개를 모두 명시한다.

```sql
-- M0 초기 스키마 (설계서 §4).
-- 지식베이스 규칙을 주석이 아니라 컬럼·제약으로 강제하는 것이 설계 원칙이다.

create extension if not exists pgcrypto;

-- ── projects ────────────────────────────────────────────────────────────
-- §1 "프로젝트마다 전역 좌표계를 최우선 확정" → coord_system NOT NULL 로 강제
create table projects (
  id                 uuid primary key default gen_random_uuid(),
  slug               text not null unique,
  name               text not null,
  structure          text,
  coord_system       jsonb not null,
  coord_assumptions  text[] not null default '{}',   -- §1 미확정 가정·정정 메모
  created_at         timestamptz not null default now()
);

-- ── sheets ──────────────────────────────────────────────────────────────
-- §3 "파일명·폴더명은 내용을 보장하지 않는다" → 출처별 컬럼 분리
create table sheets (
  id                        uuid primary key default gen_random_uuid(),
  project_id                uuid not null references projects(id) on delete cascade,
  ord                       text not null,
  drawing_no_from_filename  text not null,
  drawing_no_from_content   text,
  title_from_filename       text not null,
  title_from_content        text,
  scale_from_content        text,
  grade                     text not null check (grade in ('핵심','참고')),
  catalog_status            text not null default 'unverified'
                              check (catalog_status in
                                ('unverified','match','mismatch','unreadable')),
  page_count                int  not null check (page_count > 0),
  created_at                timestamptz not null default now(),
  unique (project_id, ord),
  unique (project_id, drawing_no_from_filename)
);

-- ── sheet_pages ─────────────────────────────────────────────────────────
-- §4 질문 크롭은 원본 픽셀 좌표를 쓴다 → 페이지 픽셀 크기를 필수 보관
create table sheet_pages (
  id         uuid primary key default gen_random_uuid(),
  sheet_id   uuid not null references sheets(id) on delete cascade,
  page_no    int  not null check (page_no > 0),
  width_px   int,
  height_px  int,
  created_at timestamptz not null default now(),
  unique (sheet_id, page_no)
);

-- ── assets ──────────────────────────────────────────────────────────────
-- role: source = [1] 업로드 입력 / derived = [2] 변환 산출물(= 회귀 정답)
create table assets (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references projects(id) on delete cascade,
  sheet_id      uuid references sheets(id) on delete cascade,
  sheet_page_id uuid references sheet_pages(id) on delete cascade,
  kind          text not null check (kind in ('dxf','pdf','png','photo')),
  role          text not null check (role in ('source','derived')),
  rel_path      text not null,
  bytes         bigint not null check (bytes > 0),
  sha256        text not null check (char_length(sha256) = 64),
  storage_path  text,
  created_at    timestamptz not null default now(),
  unique (project_id, rel_path)
);

create index on sheets(project_id);
create index on sheets(project_id, catalog_status);
create index on sheet_pages(sheet_id);
create index on assets(project_id, kind);
create index on assets(sheet_id);

-- ── RLS ─────────────────────────────────────────────────────────────────
-- anon 은 0행을 본다. worker 는 service key / DB 직결이라 우회한다.
-- 이 비대칭이 §9 검증에서 RLS 작동의 증거가 된다.
alter table projects    enable row level security;
alter table sheets      enable row level security;
alter table sheet_pages enable row level security;
alter table assets      enable row level security;

create policy "authenticated read" on projects
  for select to authenticated using (true);
create policy "authenticated read" on sheets
  for select to authenticated using (true);
create policy "authenticated read" on sheet_pages
  for select to authenticated using (true);
create policy "authenticated read" on assets
  for select to authenticated using (true);
```

- [ ] **Step 2: 실패하는 SQL 구조 테스트 작성**

`worker/tests/test_migration_sql.py`:

```python
"""마이그레이션 SQL 구조 — 규칙을 구현한 제약이 실수로 빠지지 않게 고정한다.

DB 없이 텍스트만 본다. 실제 적용 검증은 Task 7 의 `m3d db apply` 가 담당한다.
"""

import re

import pytest

from m3d.config import REPO_ROOT

TABLES = ("projects", "sheets", "sheet_pages", "assets")


@pytest.fixture
def sql() -> str:
    path = REPO_ROOT / "supabase" / "migrations" / "0001_init.sql"
    return path.read_text(encoding="utf-8")


@pytest.fixture
def norm(sql) -> str:
    """공백을 하나로 접은 SQL.

    정렬용 공백은 언제든 바뀔 수 있다. 그때마다 테스트가 깨지면 테스트를 고치는
    습관이 들고, 그 습관이 진짜 제약이 사라진 것도 놓치게 만든다.
    """
    return re.sub(r"\s+", " ", sql)


def test_all_four_tables_created(norm):
    for table in TABLES:
        assert f"create table {table} (" in norm, table


def test_rls_enabled_on_every_table(norm):
    for table in TABLES:
        assert f"alter table {table} enable row level security" in norm, table


def test_one_select_policy_per_table(sql, norm):
    assert sql.count('create policy "authenticated read"') == len(TABLES)
    assert "to authenticated" in norm
    assert "to anon" not in norm, "anon 에게 정책을 주면 RLS 증명이 무너진다"


def test_coord_system_is_not_null(norm):
    """§1 — 전역 좌표계 확정을 스키마가 강제해야 한다."""
    assert "coord_system jsonb not null" in norm


def test_sheets_separates_filename_and_content_sources(norm):
    """§3 — 파일명 유래와 내용 유래를 섞으면 편철 오류를 검출할 수 없다."""
    assert "drawing_no_from_filename text not null" in norm
    assert "drawing_no_from_content text," in norm
    assert "title_from_filename text not null" in norm
    assert "title_from_content text," in norm


def test_catalog_status_defaults_to_unverified(norm):
    assert "catalog_status text not null default 'unverified'" in norm
    for status in ("unverified", "match", "mismatch", "unreadable"):
        assert f"'{status}'" in norm


def test_sheet_pages_keeps_pixel_size(norm):
    """§4 — 질문 크롭이 원본 픽셀 좌표를 쓰므로 필수."""
    assert "width_px int" in norm
    assert "height_px int" in norm


def test_asset_role_and_kind_constraints(norm):
    assert "check (kind in ('dxf','pdf','png','photo'))" in norm
    assert "check (role in ('source','derived'))" in norm


def test_sha256_length_constraint(norm):
    assert "char_length(sha256) = 64" in norm


def test_grade_constraint_uses_korean_values(norm):
    assert "check (grade in ('핵심','참고'))" in norm
```

- [ ] **Step 3: 실패하는 Pydantic 모델 테스트 작성**

`worker/tests/test_models.py`:

```python
"""Pydantic 모델 — 0001_init.sql 의 check 제약을 파이썬 쪽에서도 막는다.

DB 왕복 전에 잘못된 값을 걸러야 seed 실패 원인이 명확해진다.
"""

import pytest
from pydantic import ValidationError

from m3d.models import AssetRow, ProjectRow, SheetPageRow, SheetRow

VALID_SHA = "a" * 64


def test_project_requires_coord_system():
    with pytest.raises(ValidationError):
        ProjectRow(slug="x", name="X")


def test_project_accepts_minimal_valid():
    row = ProjectRow(slug="ab1-p4p5", name="접속1교 P4~P5", coord_system={"up": "Y"})
    assert row.coord_assumptions == []
    assert row.structure is None


def test_sheet_rejects_unknown_grade():
    with pytest.raises(ValidationError):
        SheetRow(
            ord="A01",
            drawing_no_from_filename="C0050301-001",
            title_from_filename="제목",
            grade="중요",
            page_count=1,
        )


def test_sheet_rejects_zero_page_count():
    with pytest.raises(ValidationError):
        SheetRow(
            ord="A01",
            drawing_no_from_filename="C0050301-001",
            title_from_filename="제목",
            grade="참고",
            page_count=0,
        )


def test_sheet_defaults_to_unverified():
    """M0 는 정답을 채우지 않는다 — 그게 M1 의 시험 문제다 (설계서 §6-3)."""
    row = SheetRow(
        ord="A01",
        drawing_no_from_filename="C0050301-001",
        title_from_filename="제목",
        grade="참고",
        page_count=1,
    )
    assert row.catalog_status == "unverified"


def test_sheet_page_rejects_zero_page_no():
    with pytest.raises(ValidationError):
        SheetPageRow(ord="A01", page_no=0)


def test_asset_rejects_bad_sha_length():
    with pytest.raises(ValidationError):
        AssetRow(
            kind="dxf", role="source", rel_path="a", bytes=1, sha256="abc",
        )


def test_asset_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        AssetRow(
            kind="dwg", role="source", rel_path="a", bytes=1, sha256=VALID_SHA,
        )


def test_asset_rejects_unknown_role():
    with pytest.raises(ValidationError):
        AssetRow(
            kind="png", role="golden", rel_path="a", bytes=1, sha256=VALID_SHA,
        )


def test_asset_rejects_zero_bytes():
    with pytest.raises(ValidationError):
        AssetRow(
            kind="png", role="derived", rel_path="a", bytes=0, sha256=VALID_SHA,
        )


def test_asset_accepts_valid():
    row = AssetRow(
        kind="png", role="derived", rel_path="data/samples/x.png",
        bytes=10, sha256=VALID_SHA, ord="A01", page_no=1,
    )
    assert row.ord == "A01" and row.page_no == 1
```

- [ ] **Step 4: 두 테스트가 실패함을 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests\test_models.py worker\tests\test_migration_sql.py -v
```

Expected: `test_models.py` 는 `ModuleNotFoundError: No module named 'm3d.models'`, `test_migration_sql.py` 는 `FileNotFoundError` (Step 1을 먼저 했다면 SQL 테스트는 통과할 수도 있다 — 그 경우 models 실패만 확인한다).

- [ ] **Step 5: `worker/src/m3d/models.py` 구현**

```python
"""0001_init.sql 을 미러링하는 Pydantic 모델 (설계서 §3).

SQL 이 정본이다. 이 모듈은 DB 왕복 전에 같은 제약을 걸어 실패 원인을 앞당긴다.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

GRADES = ("핵심", "참고")
CATALOG_STATUSES = ("unverified", "match", "mismatch", "unreadable")
ASSET_KINDS = ("dxf", "pdf", "png", "photo")
ASSET_ROLES = ("source", "derived")


class ProjectRow(BaseModel):
    slug: str
    name: str
    structure: str | None = None
    coord_system: dict[str, Any]
    coord_assumptions: list[str] = Field(default_factory=list)


class SheetRow(BaseModel):
    ord: str
    drawing_no_from_filename: str
    title_from_filename: str
    grade: Literal["핵심", "참고"]
    page_count: int = Field(gt=0)
    # M0 는 내용 유래 값을 채우지 않는다 — M1 [3] 의 시험 문제다 (설계서 §6-3)
    catalog_status: Literal["unverified", "match", "mismatch", "unreadable"] = "unverified"


class SheetPageRow(BaseModel):
    ord: str                       # 부모 sheet 를 가리키는 키 (DB 컬럼 아님)
    page_no: int = Field(gt=0)


class AssetRow(BaseModel):
    kind: Literal["dxf", "pdf", "png", "photo"]
    role: Literal["source", "derived"]
    rel_path: str
    bytes: int = Field(gt=0)
    sha256: str = Field(min_length=64, max_length=64)
    # 아래 둘은 DB 컬럼이 아니라 시딩 시 sheet_id·sheet_page_id 를 찾는 키다
    ord: str | None = None
    page_no: int | None = None
```

- [ ] **Step 6: 두 테스트가 통과함을 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests -v
```

Expected: 65 passed (기존 44 + models 11 + migration_sql 10).

- [ ] **Step 7: `contracts/db.types.ts` 생성 시도 후 수기 작성**

먼저 CLI 생성을 시도한다 (설계서 §3):

```powershell
npx --yes supabase@latest gen types typescript --db-url $env:SUPABASE_DB_URL
```

`SUPABASE_DB_URL`이 아직 없거나 Docker를 요구해 실패하면 아래를 수기로 작성한다. 어느 쪽이든 결과를 Step 8의 `contracts/README.md`에 기록한다.

```typescript
// Supabase DB 타입 — supabase/migrations/0001_init.sql 미러 (설계서 §3).
// SQL 이 정본이다. 스키마를 바꾸면 이 파일도 같이 고친다.

export type Json = string | number | boolean | null | { [key: string]: Json } | Json[];

export interface Database {
  public: {
    Tables: {
      projects: {
        Row: {
          id: string;
          slug: string;
          name: string;
          structure: string | null;
          coord_system: Json;
          coord_assumptions: string[];
          created_at: string;
        };
        Insert: {
          id?: string;
          slug: string;
          name: string;
          structure?: string | null;
          coord_system: Json;
          coord_assumptions?: string[];
          created_at?: string;
        };
        Update: Partial<Database['public']['Tables']['projects']['Insert']>;
      };
      sheets: {
        Row: {
          id: string;
          project_id: string;
          ord: string;
          drawing_no_from_filename: string;
          drawing_no_from_content: string | null;
          title_from_filename: string;
          title_from_content: string | null;
          scale_from_content: string | null;
          grade: '핵심' | '참고';
          catalog_status: 'unverified' | 'match' | 'mismatch' | 'unreadable';
          page_count: number;
          created_at: string;
        };
        Insert: {
          id?: string;
          project_id: string;
          ord: string;
          drawing_no_from_filename: string;
          drawing_no_from_content?: string | null;
          title_from_filename: string;
          title_from_content?: string | null;
          scale_from_content?: string | null;
          grade: '핵심' | '참고';
          catalog_status?: 'unverified' | 'match' | 'mismatch' | 'unreadable';
          page_count: number;
          created_at?: string;
        };
        Update: Partial<Database['public']['Tables']['sheets']['Insert']>;
      };
      sheet_pages: {
        Row: {
          id: string;
          sheet_id: string;
          page_no: number;
          width_px: number | null;
          height_px: number | null;
          created_at: string;
        };
        Insert: {
          id?: string;
          sheet_id: string;
          page_no: number;
          width_px?: number | null;
          height_px?: number | null;
          created_at?: string;
        };
        Update: Partial<Database['public']['Tables']['sheet_pages']['Insert']>;
      };
      assets: {
        Row: {
          id: string;
          project_id: string;
          sheet_id: string | null;
          sheet_page_id: string | null;
          kind: 'dxf' | 'pdf' | 'png' | 'photo';
          role: 'source' | 'derived';
          rel_path: string;
          bytes: number;
          sha256: string;
          storage_path: string | null;
          created_at: string;
        };
        Insert: {
          id?: string;
          project_id: string;
          sheet_id?: string | null;
          sheet_page_id?: string | null;
          kind: 'dxf' | 'pdf' | 'png' | 'photo';
          role: 'source' | 'derived';
          rel_path: string;
          bytes: number;
          sha256: string;
          storage_path?: string | null;
          created_at?: string;
        };
        Update: Partial<Database['public']['Tables']['assets']['Insert']>;
      };
    };
    Views: Record<string, never>;
    Functions: Record<string, never>;
    Enums: Record<string, never>;
  };
}
```

- [ ] **Step 8: `contracts/README.md` 작성**

Step 7에서 CLI 생성이 성공했는지 실패했는지를 **사실대로** 적는다.

```markdown
# contracts — web·worker 공유 계약

빌드 도구가 없는 순수 파일 디렉터리다. npm 패키지가 아니다.

## 정본

`supabase/migrations/*.sql` 이 정본이다. 아래 둘은 그 미러다.

| 파일 | 소비자 |
|---|---|
| `db.types.ts` | web (`@supabase/supabase-js` 제네릭) |
| `worker/src/m3d/models.py` | worker (Pydantic 검증) |

스키마를 바꾸면 **셋을 함께** 고친다. `worker/tests/test_migration_sql.py` 가
SQL 쪽 제약이 사라지는 것을 막아준다.

## 타입 생성 상태

`supabase gen types` 자동 생성을 시도한 결과를 여기에 기록한다.

- 시도한 명령: `npx --yes supabase@latest gen types typescript --db-url $SUPABASE_DB_URL`
- 결과: <성공 / 실패 — 실패 시 에러 요약을 그대로 적는다>
- 현재 `db.types.ts` 의 출처: <자동 생성 / 수기 작성>

자동 생성이 가능해지면 수기 파일을 생성물로 교체하고 이 절을 갱신한다.
```

- [ ] **Step 9: 커밋**

```bash
git add supabase/migrations/0001_init.sql worker/src/m3d/models.py contracts worker/tests/test_models.py worker/tests/test_migration_sql.py
git commit -m "feat(db): 0001_init 스키마 + Pydantic 미러 + contracts 타입

4테이블(projects/sheets/sheet_pages/assets) + RLS 4정책.
지식베이스 규칙을 제약으로 강제:
- §1 coord_system NOT NULL
- §3 drawing_no/title 의 from_filename · from_content 분리 + catalog_status
- §4 sheet_pages.width_px/height_px

SQL 구조 테스트로 제약 누락을 회귀 방지. 적용은 Task 7.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: web 스켈레톤

**Files:**
- Create: `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/tsconfig.app.json`, `web/tsconfig.node.json`, `web/index.html`
- Create: `web/src/main.tsx`, `web/src/App.tsx`, `web/src/vite-env.d.ts`
- Create: `web/src/lib/supabase.ts`
- Create: `web/src/routes/Health.tsx`

**Interfaces:**
- Consumes: `contracts/db.types.ts` (`Database` 타입)
- Produces:
  - `web/src/lib/supabase.ts` — `export const missingEnv: string[]`, `export const supabase: SupabaseClient<Database> | null`
  - `web/src/routes/Health.tsx` — `export function Health(): JSX.Element`

**주의:** three.js는 넣지 않는다. 화면은 헬스 1개뿐이다.

- [ ] **Step 1: `web/package.json` 작성**

버전은 web-app-v2와 일치시킨다(Global Constraints).

```json
{
  "name": "model3d-studio-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "typecheck": "tsc -b --noEmit"
  },
  "dependencies": {
    "@mantine/core": "^8.1.0",
    "@mantine/hooks": "^8.1.0",
    "@supabase/supabase-js": "^2.110.7",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "postcss": "^8.4.49",
    "postcss-preset-mantine": "^1.17.0",
    "postcss-simple-vars": "^7.0.1",
    "typescript": "~5.6.3",
    "vite": "^6.0.5"
  }
}
```

- [ ] **Step 2: `web/postcss.config.cjs` 작성**

Mantine 8이 요구한다.

```javascript
module.exports = {
  plugins: {
    'postcss-preset-mantine': {},
    'postcss-simple-vars': {
      variables: {
        'mantine-breakpoint-xs': '36em',
        'mantine-breakpoint-sm': '48em',
        'mantine-breakpoint-md': '62em',
        'mantine-breakpoint-lg': '75em',
        'mantine-breakpoint-xl': '88em',
      },
    },
  },
};
```

- [ ] **Step 3: `web/vite.config.ts` 작성**

`.env`를 리포 루트 한 곳에서만 관리하고, `contracts/`를 읽을 수 있게 fs 허용 범위를 넓힌다.

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

// 리포 루트 — .env 와 contracts/ 가 여기 있다 (설계서 §8)
const repoRoot = fileURLToPath(new URL('..', import.meta.url));

export default defineConfig({
  plugins: [react()],
  envDir: repoRoot,
  server: {
    fs: { allow: [repoRoot] },
  },
});
```

- [ ] **Step 4: tsconfig 3종 작성**

`web/tsconfig.json`:

```json
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ]
}
```

`web/tsconfig.app.json` — `contracts/`를 include에 넣어야 타입 import가 잡힌다:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noEmit": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "composite": true,
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.app.tsbuildinfo"
  },
  "include": ["src", "../contracts"]
}
```

`web/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "types": ["node"],
    "strict": true,
    "noEmit": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "composite": true,
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.node.tsbuildinfo"
  },
  "include": ["vite.config.ts"]
}
```

`tsconfig.node.json`이 `types: ["node"]`를 쓰므로 devDependencies에 `@types/node`를 추가한다:

```bash
npm --prefix web ci --save-dev @types/node@^22
```

**주의:** 인자 없는 `npm --prefix web install` 은 이 리포에서 실패한다. npm 은 `--prefix`
를 적용하기 전에 **현재 디렉터리**의 `package.json` 을 읽는데, 구조 A 는 워크스페이스가
없어 루트에 `package.json` 이 없다. `npm --prefix web ci` 또는 `cd web` 후 `npm install`
을 쓴다. `npm --prefix web run <script>` 는 정상 동작한다.

- [ ] **Step 5: `web/index.html` 작성**

```html
<!doctype html>
<html lang="ko">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>model3d-studio</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: `web/src/vite-env.d.ts` 작성**

```typescript
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SUPABASE_URL?: string;
  readonly VITE_SUPABASE_PUBLISHABLE_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
```

- [ ] **Step 7: `web/src/lib/supabase.ts` 작성**

```typescript
// Supabase 클라이언트. 번들에 들어가는 값은 VITE_ 접두 2개뿐이다 (설계서 §8).
// service key 와 DB URL 은 절대 여기에 오지 않는다 — worker 전용이다.
import { createClient, type SupabaseClient } from '@supabase/supabase-js';

import type { Database } from '../../../contracts/db.types';

const url = import.meta.env.VITE_SUPABASE_URL;
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

export const missingEnv: string[] = [
  url ? null : 'VITE_SUPABASE_URL',
  publishableKey ? null : 'VITE_SUPABASE_PUBLISHABLE_KEY',
].filter((name): name is string => name !== null);

export const supabase: SupabaseClient<Database> | null =
  missingEnv.length === 0 ? createClient<Database>(url!, publishableKey!) : null;
```

- [ ] **Step 8: `web/src/routes/Health.tsx` 작성**

익명 조회 결과가 **에러 없음 + 0행**이어야 RLS 작동이 증명된다(설계서 §7).

```tsx
// M0 헬스 화면 (설계서 §7·§9-8).
// 익명 키로 projects 를 조회해 "에러 없음 + 0행" 을 확인한다.
// 둘 중 하나만으로는 연결 실패와 구분되지 않는다.
import { useEffect, useState } from 'react';
import { Alert, Badge, Card, Code, Group, Stack, Text, Title } from '@mantine/core';

import { missingEnv, supabase } from '../lib/supabase';

type HealthState =
  | { kind: 'env-missing'; missing: string[] }
  | { kind: 'checking' }
  | { kind: 'error'; message: string }
  | { kind: 'ok'; rowCount: number };

export function Health() {
  const [state, setState] = useState<HealthState>(
    missingEnv.length > 0 ? { kind: 'env-missing', missing: missingEnv } : { kind: 'checking' },
  );

  useEffect(() => {
    if (supabase === null) return;

    let cancelled = false;
    void supabase
      .from('projects')
      .select('id')
      .then(({ data, error }) => {
        if (cancelled) return;
        if (error) {
          setState({ kind: 'error', message: error.message });
          return;
        }
        setState({ kind: 'ok', rowCount: data?.length ?? 0 });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Card withBorder padding="lg" maw={640} m="xl">
      <Stack gap="md">
        <Title order={3}>model3d-studio — 연결 상태</Title>

        {state.kind === 'env-missing' && (
          <Alert color="yellow" title="환경변수 미설정">
            <Text size="sm">
              .env 에 다음 값이 필요합니다: <Code>{state.missing.join(', ')}</Code>
            </Text>
            <Text size="sm" mt="xs">
              설계서 §12 선행 작업(Supabase 프로젝트 생성·키 발급)을 마친 뒤 채워주세요.
            </Text>
          </Alert>
        )}

        {state.kind === 'checking' && <Text size="sm">확인 중…</Text>}

        {state.kind === 'error' && (
          <Alert color="red" title="연결 실패">
            <Code>{state.message}</Code>
          </Alert>
        )}

        {state.kind === 'ok' && (
          <Stack gap="xs">
            <Group gap="xs">
              <Badge color="green">도달 OK</Badge>
              <Badge color={state.rowCount === 0 ? 'green' : 'red'}>
                익명 조회 {state.rowCount}행
              </Badge>
            </Group>
            {state.rowCount === 0 ? (
              <Text size="sm">
                에러 없이 0행 — RLS 가 익명 접근을 정상 차단하고 있습니다.
                worker 가 service key 로 보는 행 수와 대조하면 RLS 작동이 증명됩니다.
              </Text>
            ) : (
              <Text size="sm" c="red">
                익명 키로 {state.rowCount}행이 보입니다 — RLS 정책을 확인하세요.
              </Text>
            )}
          </Stack>
        )}
      </Stack>
    </Card>
  );
}
```

- [ ] **Step 9: `web/src/App.tsx` · `web/src/main.tsx` 작성**

`App.tsx`:

```tsx
import { Health } from './routes/Health';

export function App() {
  return <Health />;
}
```

`main.tsx`:

```tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { MantineProvider } from '@mantine/core';
import '@mantine/core/styles.css';

import { App } from './App';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MantineProvider defaultColorScheme="auto">
      <App />
    </MantineProvider>
  </StrictMode>,
);
```

- [ ] **Step 10: 설치 후 타입체크·빌드가 통과함을 확인**

```powershell
npm --prefix web ci
npm --prefix web run build
```

Expected: `tsc -b` 에러 0, `vite build` 성공. `contracts/db.types.ts` import 가 해결되지 않으면 `tsconfig.app.json` 의 `include` 를 다시 본다.

- [ ] **Step 11: dev 서버를 띄워 env 미설정 화면을 확인**

```powershell
npm --prefix web run dev
```

브라우저에서 `http://localhost:5173` 을 연다.
Expected: 노란 "환경변수 미설정" 경고와 `VITE_SUPABASE_URL, VITE_SUPABASE_PUBLISHABLE_KEY`.
(키가 이미 채워져 있다면 "도달 OK / 익명 조회 0행"이 보인다 — 그것도 정상이다.)

- [ ] **Step 12: 커밋**

```bash
git add web/package.json web/package-lock.json web/postcss.config.cjs web/vite.config.ts web/tsconfig*.json web/index.html web/src
git commit -m "feat(web): 헬스 화면 스켈레톤 — Supabase 도달·RLS 차단 확인

- web-app-v2 와 버전 일치 (React 18.3 / Vite 6 / TS 5.6 / Mantine 8), three.js 미포함
- envDir 을 리포 루트로 잡아 .env 를 한 곳에서만 관리
- 헬스 화면 4상태: env 미설정 / 확인 중 / 연결 실패 / 도달 OK + 익명 0행
- '에러 없음 + 0행' 을 함께 봐야 RLS 작동이 증명된다

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: `db apply` / `db check` — 실제 적용

> **블로커:** 설계서 §12 선행 작업이 끝나야 한다. `.env`에 `SUPABASE_DB_URL`이 없으면 이 태스크를 시작하지 말고 사용자에게 보고한다.

**Files:**
- Create: `worker/src/m3d/db.py`
- Modify: `worker/src/m3d/cli.py` (db 서브앱 추가)
- Test: `worker/tests/test_db_migrations.py`

**Interfaces:**
- Consumes: `m3d.config.Config`, `m3d.samples.manifest.sha256_file`
- Produces:
  - `m3d.db.TABLES: tuple[str, ...]` (= `("projects", "sheets", "sheet_pages", "assets")`)
  - `m3d.db.MigrationError(RuntimeError)`
  - `m3d.db.Migration` — frozen dataclass: `version: str`, `path: Path`, `sha256: str`
  - `m3d.db.discover_migrations(directory: Path) -> list[Migration]` — 순수
  - `m3d.db.pending_migrations(available: list[Migration], applied: dict[str, str]) -> list[Migration]` — 순수
  - `m3d.db.apply_migrations(cfg: Config) -> list[str]` — 적용된 version 목록
  - `m3d.db.check(cfg: Config) -> dict` — 키: `counts: dict[str, int]`, `rls: dict[str, bool]`, `projects: list[dict]`

- [ ] **Step 1: 실패하는 마이그레이션 로직 테스트 작성**

`worker/tests/test_db_migrations.py`:

```python
"""마이그레이션 러너의 순수 로직 — DB 없이 검증한다.

핵심 규칙: 이미 적용된 마이그레이션 파일이 나중에 수정되면 조용히 넘어가지 않는다.
"""

import pytest

from m3d.db import MigrationError, discover_migrations, pending_migrations


def _write(directory, name, body):
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def test_discover_sorts_by_version(tmp_path):
    _write(tmp_path, "0002_more.sql", "select 2;")
    _write(tmp_path, "0001_init.sql", "select 1;")
    versions = [m.version for m in discover_migrations(tmp_path)]
    assert versions == ["0001_init", "0002_more"]


def test_discover_raises_on_empty_dir(tmp_path):
    with pytest.raises(MigrationError, match="마이그레이션이 없습니다"):
        discover_migrations(tmp_path)


def test_discover_records_file_hash(tmp_path):
    _write(tmp_path, "0001_init.sql", "select 1;")
    migration = discover_migrations(tmp_path)[0]
    assert len(migration.sha256) == 64


def test_all_pending_when_nothing_applied(tmp_path):
    _write(tmp_path, "0001_init.sql", "select 1;")
    _write(tmp_path, "0002_more.sql", "select 2;")
    available = discover_migrations(tmp_path)
    assert [m.version for m in pending_migrations(available, {})] == ["0001_init", "0002_more"]


def test_applied_versions_are_skipped(tmp_path):
    _write(tmp_path, "0001_init.sql", "select 1;")
    _write(tmp_path, "0002_more.sql", "select 2;")
    available = discover_migrations(tmp_path)
    applied = {available[0].version: available[0].sha256}
    assert [m.version for m in pending_migrations(available, applied)] == ["0002_more"]


def test_modified_applied_migration_raises(tmp_path):
    """적용 후 수정된 마이그레이션을 조용히 무시하면 스키마가 코드와 어긋난다."""
    _write(tmp_path, "0001_init.sql", "select 1;")
    available = discover_migrations(tmp_path)
    applied = {"0001_init": "0" * 64}
    with pytest.raises(MigrationError, match="파일이 그 뒤 수정"):
        pending_migrations(available, applied)


def test_nothing_pending_when_all_applied(tmp_path):
    _write(tmp_path, "0001_init.sql", "select 1;")
    available = discover_migrations(tmp_path)
    applied = {m.version: m.sha256 for m in available}
    assert pending_migrations(available, applied) == []
```

- [ ] **Step 2: 테스트가 실패함을 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests\test_db_migrations.py -v
```

Expected: `ModuleNotFoundError: No module named 'm3d.db'`

- [ ] **Step 3: `worker/src/m3d/db.py` 구현**

```python
"""Supabase 직결 — 마이그레이션 적용과 상태 확인 (설계서 §5).

supabase CLI 도 Docker 도 없으므로 psycopg 로 Session pooler 에 직접 붙는다.
대시보드 수동 붙여넣기와 달리 재현 가능하고 이력이 schema_migrations 에 남는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import psycopg

from m3d.config import Config
from m3d.samples.manifest import sha256_file

TABLES = ("projects", "sheets", "sheet_pages", "assets")

SCHEMA_MIGRATIONS_DDL = """
create table if not exists schema_migrations (
  version    text primary key,
  sha256     text not null,
  applied_at timestamptz not null default now()
);
"""


class MigrationError(RuntimeError):
    """마이그레이션 파일 누락·사후 변조."""


@dataclass(frozen=True)
class Migration:
    version: str
    path: Path
    sha256: str


def discover_migrations(directory: Path) -> list[Migration]:
    files = sorted(directory.glob("*.sql"))
    if not files:
        raise MigrationError(f"마이그레이션이 없습니다: {directory}")
    return [Migration(f.stem, f, sha256_file(f)) for f in files]


def pending_migrations(
    available: list[Migration], applied: dict[str, str]
) -> list[Migration]:
    """아직 적용되지 않은 것만 돌려준다. 적용 후 수정된 파일은 에러로 정지시킨다."""
    pending: list[Migration] = []
    for migration in available:
        recorded = applied.get(migration.version)
        if recorded is None:
            pending.append(migration)
        elif recorded != migration.sha256:
            raise MigrationError(
                f"{migration.version} 은 이미 적용되었는데 파일이 그 뒤 수정되었습니다 "
                f"(기록 {recorded[:12]}… / 현재 {migration.sha256[:12]}…). "
                "적용된 마이그레이션을 고치지 말고 새 파일을 추가하세요."
            )
    return pending


def apply_migrations(cfg: Config) -> list[str]:
    available = discover_migrations(cfg.migrations_dir)

    with psycopg.connect(cfg.require_db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_MIGRATIONS_DDL)
            cur.execute("select version, sha256 from schema_migrations")
            applied = dict(cur.fetchall())
        conn.commit()

        todo = pending_migrations(available, applied)
        for migration in todo:
            with conn.cursor() as cur:
                # 파라미터 없는 execute 는 단순 질의 프로토콜을 써서 여러 문장을 허용한다
                cur.execute(migration.path.read_text(encoding="utf-8"))
                cur.execute(
                    "insert into schema_migrations (version, sha256) values (%s, %s)",
                    (migration.version, migration.sha256),
                )
            conn.commit()

    return [m.version for m in todo]


def check(cfg: Config) -> dict:
    """테이블 행 수·RLS 활성 여부·프로젝트 좌표계를 읽어온다."""
    with psycopg.connect(cfg.require_db_url()) as conn, conn.cursor() as cur:
        counts: dict[str, int] = {}
        for table in TABLES:  # 테이블명은 상수 튜플에서만 온다 — 외부 입력 아님
            cur.execute(f"select count(*) from {table}")
            counts[table] = cur.fetchone()[0]

        cur.execute(
            "select relname, relrowsecurity from pg_class where relname = any(%s)",
            (list(TABLES),),
        )
        rls = {name: enabled for name, enabled in cur.fetchall()}

        cur.execute(
            "select slug, name, coord_system, coord_assumptions "
            "from projects order by slug"
        )
        projects = [
            {
                "slug": slug,
                "name": name,
                "coord_system": coord_system,
                "coord_assumptions": coord_assumptions,
            }
            for slug, name, coord_system, coord_assumptions in cur.fetchall()
        ]

    return {"counts": counts, "rls": rls, "projects": projects}
```

- [ ] **Step 4: 테스트가 통과함을 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests -v
```

Expected: 72 passed (기존 65 + db_migrations 7).

- [ ] **Step 5: CLI에 db 서브앱 추가**

`worker/src/m3d/cli.py` import에 추가:

```python
from m3d import db as db_mod
```

`if __name__ == "__main__":` 앞에 추가:

```python
db_app = typer.Typer(help="Supabase 스키마 적용·확인", no_args_is_help=True)
app.add_typer(db_app, name="db")


@db_app.command("apply")
def db_apply() -> None:
    """supabase/migrations/*.sql 을 순서대로 적용한다."""
    cfg = load_config()
    applied = db_mod.apply_migrations(cfg)
    if applied:
        typer.echo(f"적용 {len(applied)}건: {', '.join(applied)}")
    else:
        typer.echo("적용할 마이그레이션이 없습니다 (모두 반영됨).")


@db_app.command("check")
def db_check() -> None:
    """테이블 행 수·RLS 상태·프로젝트 좌표계를 출력한다."""
    import json

    cfg = load_config()
    result = db_mod.check(cfg)

    typer.echo("테이블        행수   RLS")
    typer.echo("-" * 32)
    for table in db_mod.TABLES:
        rls = "on" if result["rls"].get(table) else "OFF"
        typer.echo(f"{table:<13} {result['counts'][table]:>5}   {rls}")

    for project in result["projects"]:
        typer.echo(f"\n프로젝트 {project['slug']} — {project['name']}")
        typer.echo("좌표계: " + json.dumps(project["coord_system"], ensure_ascii=False, indent=2))
        for note in project["coord_assumptions"]:
            typer.echo(f"가정·정정: {note}")
```

- [ ] **Step 6: `.env`에 Supabase 값이 채워졌는지 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -c "from m3d.config import load_config; c=load_config(); print('DB URL 설정됨:', c.supabase_db_url is not None); print('URL 설정됨:', c.supabase_url is not None)"
```

Expected: 둘 다 `True`. `False`면 **여기서 멈추고** 설계서 §12를 사용자에게 안내한다.

- [ ] **Step 7: 마이그레이션 적용**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\m3d.exe db apply
```

Expected: `적용 1건: 0001_init`

연결이 실패하면 설계서 §11대로 direct connection 문자열로 바꿔 재시도하고, 그래도 안 되면 대시보드 SQL Editor 수동 적용 후 **그 사실을 보고**한다(조용히 넘어가지 않는다).

- [ ] **Step 8: 재실행이 멱등인지 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\m3d.exe db apply
```

Expected: `적용할 마이그레이션이 없습니다 (모두 반영됨).`

- [ ] **Step 9: 스키마·RLS 상태 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\m3d.exe db check
```

Expected: 4테이블 모두 행수 `0`, RLS `on`. 하나라도 `OFF`면 마이그레이션을 다시 본다.

- [ ] **Step 10: 커밋**

```bash
git add worker/src/m3d/db.py worker/src/m3d/cli.py worker/tests/test_db_migrations.py
git commit -m "feat(worker): db apply/check — psycopg 직결 마이그레이션 러너

- supabase CLI·Docker 없이 Session pooler 직결로 적용, 이력은 schema_migrations
- 적용 후 수정된 마이그레이션은 조용히 넘기지 않고 에러로 정지
- check 가 행수와 함께 RLS 활성 여부를 출력 — RLS 증명의 절반

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 8: seed + M0 최종 검증

> **블로커:** Task 7과 동일. `.env`의 Supabase 값이 필요하다.

**Files:**
- Create: `worker/src/m3d/seed/__init__.py`
- Create: `worker/src/m3d/seed/ab1_p4p5.py`
- Modify: `worker/src/m3d/cli.py` (seed 명령 추가)
- Create: `scripts/verify-m0.ps1`
- Create: `README.md`
- Test: `worker/tests/test_seed_rows.py`

**Interfaces:**
- Consumes: `m3d.config.Config`, `m3d.models.{ProjectRow, SheetRow, SheetPageRow, AssetRow}`, `m3d.samples.manifest.{Manifest, load_manifest}`, `m3d.samples.collect.{DATASET, manifest_path}`, `m3d.samples.source_manifest.{SourceSheet, parse_source_manifest}`
- Produces:
  - `m3d.seed.ab1_p4p5.COORD_SYSTEM: dict`
  - `m3d.seed.ab1_p4p5.COORD_ASSUMPTIONS: list[str]`
  - `m3d.seed.ab1_p4p5.SeedPayload` — frozen dataclass: `project: ProjectRow`, `sheets: tuple[SheetRow, ...]`, `pages: tuple[SheetPageRow, ...]`, `assets: tuple[AssetRow, ...]`
  - `m3d.seed.ab1_p4p5.build_rows(manifest: Manifest, sheets: list[SourceSheet]) -> SeedPayload` — 순수
  - `m3d.seed.ab1_p4p5.seed(cfg: Config, *, reseed: bool = False) -> dict[str, int]`
  - `m3d.seed.ab1_p4p5.SeedError(RuntimeError)`

- [ ] **Step 1: 실패하는 seed 행 생성 테스트 작성**

`worker/tests/test_seed_rows.py`:

```python
"""seed 행 생성 — DB 없이 '무엇을 넣을지' 를 검증한다."""

import pytest

from m3d.samples.collect import DATASET, manifest_path
from m3d.samples.manifest import load_manifest
from m3d.samples.source_manifest import parse_source_manifest
from m3d.seed.ab1_p4p5 import COORD_SYSTEM, build_rows
from m3d.config import load_config


@pytest.fixture
def payload(fixtures_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    cfg = load_config(env_file=tmp_path / "absent.env")
    manifest = load_manifest(manifest_path(cfg))
    sheets = parse_source_manifest(fixtures_dir / "_manifest.txt")
    return build_rows(manifest, sheets)


def test_counts(payload):
    """설계서 §9-5 의 기대값 — projects 1 · sheets 50 · pages 61 · assets 112."""
    assert len(payload.sheets) == 50
    assert len(payload.pages) == 61
    assert len(payload.assets) == 112


def test_project_slug_and_coord_system(payload):
    assert payload.project.slug == DATASET
    assert payload.project.coord_system == COORD_SYSTEM
    assert payload.project.coord_system["unit"] == "m"
    assert payload.project.coord_system["up"] == "Y"


def test_project_records_known_correction(payload):
    """패키지 README 의 P4 STA 오기를 가정·정정 메모로 남긴다 (설계서 §6-4)."""
    assert len(payload.project.coord_assumptions) == 1
    assert "3+665.45" in payload.project.coord_assumptions[0]


def test_all_sheets_are_unverified(payload):
    """M0 는 내용 유래 값을 채우지 않는다 — M1 [3] 의 시험 문제 (설계서 §6-3)."""
    assert all(s.catalog_status == "unverified" for s in payload.sheets)


def test_sheet_grade_split(payload):
    assert sum(1 for s in payload.sheets if s.grade == "핵심") == 43
    assert sum(1 for s in payload.sheets if s.grade == "참고") == 7


def test_page_count_sum_matches_pages(payload):
    assert sum(s.page_count for s in payload.sheets) == len(payload.pages)


def test_pages_are_one_based_per_sheet(payload):
    by_ord: dict[str, list[int]] = {}
    for page in payload.pages:
        by_ord.setdefault(page.ord, []).append(page.page_no)
    assert len(by_ord) == 50
    for ord_, page_nos in by_ord.items():
        assert sorted(page_nos) == list(range(1, len(page_nos) + 1)), ord_


def test_asset_kind_counts(payload):
    counts: dict[str, int] = {}
    for asset in payload.assets:
        counts[asset.kind] = counts.get(asset.kind, 0) + 1
    assert counts == {"dxf": 50, "png": 61, "pdf": 1}


def test_dxf_assets_link_to_sheet_only(payload):
    dxf = [a for a in payload.assets if a.kind == "dxf"]
    assert all(a.ord is not None and a.page_no is None for a in dxf)


def test_png_assets_link_to_sheet_and_page(payload):
    png = [a for a in payload.assets if a.kind == "png"]
    assert all(a.ord is not None and a.page_no is not None for a in png)


def test_pdf_asset_links_to_project_only(payload):
    pdf = [a for a in payload.assets if a.kind == "pdf"]
    assert len(pdf) == 1
    assert pdf[0].ord is None and pdf[0].page_no is None


def test_asset_roles(payload):
    for asset in payload.assets:
        expected = "derived" if asset.kind == "png" else "source"
        assert asset.role == expected, asset.rel_path


def test_every_asset_ord_exists_in_sheets(payload):
    sheet_ords = {s.ord for s in payload.sheets}
    for asset in payload.assets:
        if asset.ord is not None:
            assert asset.ord in sheet_ords, asset.rel_path
```

- [ ] **Step 2: 테스트가 실패함을 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests\test_seed_rows.py -v
```

Expected: `ModuleNotFoundError: No module named 'm3d.seed'`

- [ ] **Step 3: `worker/src/m3d/seed/__init__.py` 작성**

```python
"""샘플 세트를 DB 에 등재한다."""
```

- [ ] **Step 4: `worker/src/m3d/seed/ab1_p4p5.py` 구현**

```python
"""접속1교 P4~P5 샘플 세트 시딩 (설계서 §6-3·§6-4).

M0 는 `*_from_filename` 만 채운다. `*_from_content` 는 M1 [3] 이 시트 내부 텍스트에서
독립적으로 판독해 채우고 대조한다 — 편철 오류 검출의 회귀 테스트가 여기서 성립한다.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from m3d.config import Config
from m3d.models import AssetRow, ProjectRow, SheetPageRow, SheetRow
from m3d.samples.collect import DATASET, manifest_path
from m3d.samples.manifest import Manifest, load_manifest
from m3d.samples.source_manifest import SourceSheet, parse_source_manifest

# 설계서 §6-4 — models_3d/ab1/SPEC_v2.md §0 에서 가져왔다
COORD_SYSTEM = {
    "up": "Y",
    "unit": "m",
    "axes": {
        "x": "교축직각 (상자 중심 x=0, 보도측 = x 음/서측)",
        "y": "EL − 4.871",
        "z": "STA − 4190",
    },
    "datums": {
        "P4_bearing_z": -525.0,
        "P4_sta": "3+665.000",
        "P5_bearing_z": -455.0,
        "P5_sta": "3+735.000",
    },
    "source": "models_3d/ab1/SPEC_v2.md §0",
}

COORD_ASSUMPTIONS = [
    "패키지 README 의 P4 STA '3+665.45' 는 오기 — SPEC_v2 §0 의 3+665.000 이 정본"
    " (상세도 M.L STA 역산)"
]

PROJECT_NAME = "접속1교 P4~P5"
PROJECT_STRUCTURE = "원산안면대교(솔빛대교) 접속1교"


class SeedError(RuntimeError):
    """이미 시딩된 프로젝트를 덮어쓰려 할 때."""


@dataclass(frozen=True)
class SeedPayload:
    project: ProjectRow
    sheets: tuple[SheetRow, ...]
    pages: tuple[SheetPageRow, ...]
    assets: tuple[AssetRow, ...]


def build_rows(manifest: Manifest, sheets: list[SourceSheet]) -> SeedPayload:
    """매니페스트 + 원본 카탈로그 → 삽입할 행 전부. 파일시스템·DB 를 건드리지 않는다."""
    project = ProjectRow(
        slug=DATASET,
        name=PROJECT_NAME,
        structure=PROJECT_STRUCTURE,
        coord_system=COORD_SYSTEM,
        coord_assumptions=list(COORD_ASSUMPTIONS),
    )

    sheet_rows = tuple(
        SheetRow(
            ord=sheet.ord,
            drawing_no_from_filename=sheet.drawing_no,
            title_from_filename=sheet.title,
            grade=sheet.grade,
            page_count=sheet.page_count,
        )
        for sheet in sheets
    )

    page_rows = tuple(
        SheetPageRow(ord=sheet.ord, page_no=page_no)
        for sheet in sheets
        for page_no in range(1, sheet.page_count + 1)
    )

    asset_rows = tuple(
        AssetRow(
            kind=entry.kind,
            role=entry.role,
            rel_path=entry.rel_path,
            bytes=entry.bytes,
            sha256=entry.sha256,
            ord=entry.ord,
            page_no=entry.page_no,
        )
        for entry in manifest.entries
    )

    return SeedPayload(
        project=project, sheets=sheet_rows, pages=page_rows, assets=asset_rows
    )


def seed(cfg: Config, *, reseed: bool = False) -> dict[str, int]:
    manifest = load_manifest(manifest_path(cfg))
    sheets = parse_source_manifest(cfg.source_manifest_path)
    payload = build_rows(manifest, sheets)

    with psycopg.connect(cfg.require_db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute("select id from projects where slug = %s", (payload.project.slug,))
            existing = cur.fetchone()
            if existing is not None:
                if not reseed:
                    raise SeedError(
                        f"프로젝트 '{payload.project.slug}' 가 이미 있습니다. "
                        "덮어쓰려면 --reseed 를 주세요 (자식 행이 모두 삭제됩니다)."
                    )
                cur.execute("delete from projects where slug = %s", (payload.project.slug,))

            cur.execute(
                "insert into projects (slug, name, structure, coord_system, coord_assumptions) "
                "values (%s, %s, %s, %s, %s) returning id",
                (
                    payload.project.slug,
                    payload.project.name,
                    payload.project.structure,
                    psycopg.types.json.Json(payload.project.coord_system),
                    payload.project.coord_assumptions,
                ),
            )
            project_id = cur.fetchone()[0]

            sheet_ids: dict[str, str] = {}
            for sheet in payload.sheets:
                cur.execute(
                    "insert into sheets (project_id, ord, drawing_no_from_filename, "
                    "title_from_filename, grade, catalog_status, page_count) "
                    "values (%s, %s, %s, %s, %s, %s, %s) returning id",
                    (
                        project_id,
                        sheet.ord,
                        sheet.drawing_no_from_filename,
                        sheet.title_from_filename,
                        sheet.grade,
                        sheet.catalog_status,
                        sheet.page_count,
                    ),
                )
                sheet_ids[sheet.ord] = cur.fetchone()[0]

            page_ids: dict[tuple[str, int], str] = {}
            for page in payload.pages:
                cur.execute(
                    "insert into sheet_pages (sheet_id, page_no) values (%s, %s) returning id",
                    (sheet_ids[page.ord], page.page_no),
                )
                page_ids[(page.ord, page.page_no)] = cur.fetchone()[0]

            for asset in payload.assets:
                sheet_id = sheet_ids[asset.ord] if asset.ord is not None else None
                page_id = (
                    page_ids[(asset.ord, asset.page_no)]
                    if asset.ord is not None and asset.page_no is not None
                    else None
                )
                cur.execute(
                    "insert into assets (project_id, sheet_id, sheet_page_id, kind, role, "
                    "rel_path, bytes, sha256) values (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        project_id,
                        sheet_id,
                        page_id,
                        asset.kind,
                        asset.role,
                        asset.rel_path,
                        asset.bytes,
                        asset.sha256,
                    ),
                )
        conn.commit()

    return {
        "projects": 1,
        "sheets": len(payload.sheets),
        "sheet_pages": len(payload.pages),
        "assets": len(payload.assets),
    }
```

- [ ] **Step 5: 테스트가 통과함을 확인**

`data/manifests/ab1-p4p5.json`이 있어야 한다(Task 4에서 생성).

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests -v
```

Expected: 85 passed (기존 72 + seed_rows 13).

- [ ] **Step 6: CLI에 seed 명령 추가**

`worker/src/m3d/cli.py` import에 추가:

```python
from m3d.seed import ab1_p4p5 as seed_mod
```

`if __name__ == "__main__":` 앞에 추가:

```python
@app.command()
def seed(
    dataset: str = typer.Argument(..., help="데이터셋 슬러그 (예: ab1-p4p5)"),
    reseed: bool = typer.Option(False, "--reseed", help="기존 프로젝트를 지우고 다시 넣는다"),
) -> None:
    """샘플 세트를 projects/sheets/sheet_pages/assets 에 등재한다."""
    if dataset != DATASET:
        typer.echo(f"알 수 없는 데이터셋: {dataset} (현재 지원: {DATASET})")
        raise typer.Exit(code=1)

    cfg = load_config()
    counts = seed_mod.seed(cfg, reseed=reseed)
    for table, count in counts.items():
        typer.echo(f"{table:<13} {count:>5}")
```

- [ ] **Step 7: 시딩 실행**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\m3d.exe seed ab1-p4p5
```

Expected:

```
projects          1
sheets           50
sheet_pages      61
assets          112
```

- [ ] **Step 8: DB 상태 재확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\m3d.exe db check
```

Expected: `projects 1 / sheets 50 / sheet_pages 61 / assets 112`, RLS 4개 모두 `on`, 좌표계 JSON과 가정·정정 메모 1건 출력.

- [ ] **Step 9: `scripts/verify-m0.ps1` 작성**

```powershell
# M0 완료 기준 §9 의 1~7 을 일괄 실행한다. 8(웹 스크린샷)은 수동이다.
$ErrorActionPreference = 'Continue'
$env:PYTHONUTF8 = '1'

$root = Split-Path -Parent $PSScriptRoot
$m3d = Join-Path $root 'worker\.venv\Scripts\m3d.exe'
$python = Join-Path $root 'worker\.venv\Scripts\python.exe'
$failed = @()

function Invoke-Step {
    param([string]$Label, [scriptblock]$Body)
    Write-Host "`n=== $Label ===" -ForegroundColor Cyan
    & $Body
    if ($LASTEXITCODE -ne 0) {
        $script:failed += $Label
        Write-Host "FAIL: $Label" -ForegroundColor Red
    }
}

Invoke-Step '1. doctor'         { & $m3d doctor }
Invoke-Step '2. samples collect' { & $m3d samples collect }
Invoke-Step '3. samples verify'  { & $m3d samples verify }
Invoke-Step '4. db apply'        { & $m3d db apply }
Invoke-Step '5-6. db check'      { & $m3d db check }
Invoke-Step '7. pytest'          { & $python -m pytest (Join-Path $root 'worker\tests') -q }

Write-Host "`n===== 요약 =====" -ForegroundColor Cyan
if ($failed.Count -eq 0) {
    Write-Host '1~7 전부 통과. 남은 것: 8(웹 헬스 화면 스크린샷).' -ForegroundColor Green
} else {
    Write-Host "실패 $($failed.Count)건: $($failed -join ', ')" -ForegroundColor Red
    Write-Host 'M0 를 완료로 선언하지 마세요.' -ForegroundColor Red
    exit 1
}
```

주의: `db check` 는 시딩 후 실행해야 5·6 기대값이 나온다. 이 스크립트는 `seed` 를 부르지 않는다 — 재시딩은 `--reseed` 가 필요한 파괴적 동작이라 자동화하지 않는다.

- [ ] **Step 10: 일괄 검증 실행**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-m0.ps1
```

Expected: `1~7 전부 통과. 남은 것: 8(웹 헬스 화면 스크린샷).`

- [ ] **Step 11: web 헬스 화면 확인 + 스크린샷**

`.env`의 `VITE_SUPABASE_URL`·`VITE_SUPABASE_PUBLISHABLE_KEY`가 채워진 상태에서:

```powershell
npm --prefix web run dev
```

브라우저로 `http://localhost:5173`을 열고 **스크린샷을 캡처**한다(전역 규칙 §2 — 검증 시 화면 캡처 대조).

Expected 화면:
- 초록 배지 `도달 OK`
- 초록 배지 `익명 조회 0행`
- 본문: "에러 없이 0행 — RLS 가 익명 접근을 정상 차단하고 있습니다."

**이 화면(익명 0행)과 Step 8의 `db check`(service key로 sheets 50 · assets 112)를 나란히 두는 것이 RLS 작동의 증거다.** 익명 조회에서 0행이 아니거나 에러가 나면 M0 미완료다.

- [ ] **Step 12: `README.md` 작성**

```markdown
# model3d-studio

도면(CAD·PDF)과 사진을 넣으면 AI 에이전트가 부재·섹션별로 병렬 판독·3D 모델링·
검수하고, 도면상 구분이 어려운 부분은 도면 크롭과 함께 사용자에게 질문하는 웹 서비스.

- 규칙 정본: [모델링규칙 지식베이스](docs/모델링규칙_지식베이스_v0.md)
- 아키텍처 정본: [아키텍처·MCP 구성](docs/아키텍처_MCP구성_v0.md)
- M0 설계서: [리포 부트스트랩](docs/superpowers/specs/2026-08-27-m0-repo-bootstrap-design.md)

## 구조

| 경로 | 내용 |
|---|---|
| `worker/` | Python 파이프라인 (`m3d` CLI). 판독·모델링·검증 |
| `web/` | React + Vite 프론트 |
| `contracts/` | web·worker 공유 DB 타입 (빌드 도구 없는 파일 디렉터리) |
| `supabase/migrations/` | 스키마 정본 |
| `data/manifests/` | 샘플 SHA256 매니페스트 (커밋) |
| `data/fixtures/` | 정답지·카탈로그 사본 (커밋) |
| `data/samples/` | 도면 원본 사본 413MB (**gitignore**) |

## 시작하기

1. `.env.example` 을 `.env` 로 복사하고 값을 채운다 (설계서 §12).
2. venv 생성·설치:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
   ```

3. 샘플 수집·DB 적용:

   ```powershell
   .\worker\.venv\Scripts\m3d.exe samples collect
   .\worker\.venv\Scripts\m3d.exe db apply
   .\worker\.venv\Scripts\m3d.exe seed ab1-p4p5
   ```

4. 웹:

   ```powershell
   npm --prefix web ci
   npm --prefix web run dev
   ```

## 검증

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-m0.ps1
```

`make` 는 이 환경에 없다. `m3d` CLI 가 태스크 러너를 겸한다.

## 주의

- `SAMPLE_SOURCE_DIR` · `REFERENCE_MODELS_DIR` 아래 참조 원본은 **읽기 전용**이다.
- `SUPABASE_SERVICE_KEY` · `SUPABASE_DB_URL` 은 worker 전용 — 웹 번들·커밋 금지.
- 검증 없이 완료를 주장하지 않는다. 실패는 출력과 함께 실패로 보고한다.
```

- [ ] **Step 13: 커밋**

```bash
git add worker/src/m3d/seed worker/src/m3d/cli.py worker/tests/test_seed_rows.py scripts/verify-m0.ps1 README.md
git commit -m "feat(worker): seed ab1-p4p5 + M0 일괄 검증 스크립트

- projects 1 / sheets 50 / sheet_pages 61 / assets 112 등재
- 모든 sheets 는 catalog_status=unverified — 내용 유래 값은 M1 [3] 이 채운다
- 좌표계는 SPEC_v2 §0 에서, README 의 P4 STA 오기는 가정·정정 메모로 기록
- 기존 프로젝트가 있으면 --reseed 없이는 거부 (파괴적 동작 보호)
- verify-m0.ps1 이 §9 의 1~7 을 일괄 실행

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## 계획 자체 검토 결과

작성 후 설계서와 대조해 확인한 것과 고친 것.

### 1. 스펙 커버리지

| 설계서 절 | 담당 태스크 |
|---|---|
| §3 디렉터리 구조 | 1(루트·worker·scripts) · 5(contracts·supabase) · 6(web) · 2·4(data) |
| §4 스키마 4테이블 + RLS | 5 작성 · 7 적용 |
| §5 마이그레이션 경로 | 7 |
| §6 CLI 6개 명령 | 1(doctor) · 4(samples×2) · 7(db×2) · 8(seed) |
| §6-1 doctor 필수/선택 분리 | 1 |
| §6-2 원본 보호 | 4 (`_copy_one` 의 mtime·size 불변 확인) |
| §6-3 편철 오류 회귀 | 5(스키마) · 8(전부 unverified 시딩) |
| §6-4 좌표계 시딩 | 8 |
| §7 web 헬스 3상태 | 6 (실제로는 4상태 — `checking` 추가) |
| §8 비밀키 분리 | 1(.env.example) · 6(VITE_ 2개만) |
| §9 완료 기준 1~8 | 1·4·7·8 + `verify-m0.ps1` |
| §9 테스트 대상 3종 | 1(config) · 2(파서) · 3(매니페스트) |
| §10 범위 밖 | 계획 어디에도 Storage·판독·뷰어·인증이 없음 — 확인함 |
| §11 리스크 대응 | 1(선택 의존성 개별 설치) · 7(연결 실패 폴백) · 5(타입 생성 폴백) · 4(멱등) |
| §12 선행 작업 | Task 7·8 상단 블로커 명시 |

**빠진 것 없음.** §7이 3상태라고 했으나 계획은 `checking`을 더해 4상태로 만들었다 — 비동기 조회에 로딩 상태가 없으면 화면이 거짓말을 한다.

### 2. 플레이스홀더 스캔

TBD·TODO·"적절히 처리"·"위와 유사" 없음. 모든 코드 스텝에 실제 코드가 들어 있다.

### 3. 타입 일관성 (교차 확인해 고친 것)

- `ManifestEntry`의 필드명이 Task 3 정의(`rel_path`·`source_rel`·`ord`·`drawing_no`·`page_no`)와 Task 4 생성부, Task 8 소비부에서 모두 일치함을 확인.
- `SheetPageRow`에 `ord` 필드를 추가했다. Task 5 초안에는 `page_no`만 있었으나 Task 8이 부모 시트를 찾으려면 키가 필요하다. `ord`·`page_no` 둘 다 DB 컬럼이 아니라 시딩용 키임을 주석으로 명시.
- `AssetRow`에도 같은 이유로 `ord`·`page_no`를 두고 DB 컬럼이 아님을 주석에 명시.
- `write_manifest`가 Task 4 CLI에서 쓰이므로 import 줄을 Task 4 Step 5에서 명시적으로 교체하도록 적었다.
- `DATASET` 상수의 출처를 `m3d.samples.collect` 하나로 통일(Task 8 CLI도 여기서 import).

### 4. 범위

M0 하나에 대한 단일 계획으로 적절하다. 8태스크 중 6개가 키 없이 진행 가능해 블로커 대기 중에도 일이 멈추지 않는다.
