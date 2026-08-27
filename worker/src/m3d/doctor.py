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
