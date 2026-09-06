"""LLM 코드 샌드박스 (M5 D5) — AST 화이트리스트 검사 + 별도 프로세스(`python -I`) 실행.

완전한 격리(네트워크·파일)는 OS 샌드박스가 아니면 불가능하다. 여기서는 (1) AST 로 import·위험 이름을 거르고
(2) 러너가 제한된 builtins 와 가드된 __import__ 로 실행하며 (3) 타임아웃으로 무한 루프를 끊는다.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ALLOWED_IMPORTS = {"math", "numpy", "trimesh", "m3d.model.geom"}
FORBIDDEN_NAMES = {"open", "exec", "eval", "__import__", "compile", "input", "breakpoint", "globals", "locals",
                   "getattr", "setattr", "delattr", "vars", "__builtins__"}
FORBIDDEN_ATTRS = {"__subclasses__", "__globals__", "__code__", "__builtins__", "__dict__", "__class__", "__bases__",
                   "__mro__", "__getattribute__", "__reduce__"}


def _import_ok(name: str) -> bool:
    return name in ALLOWED_IMPORTS or name.split(".")[0] in {"math", "numpy", "trimesh"} or name.startswith("m3d.model.geom")


def check_code(code: str) -> list[str]:
    """계약 위반 목록(비면 통과). 문법 오류도 위반으로 돌려준다."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"문법 오류: {exc.msg} (line {exc.lineno})"]
    bad: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if not _import_ok(a.name):
                    bad.add(f"import 금지: {a.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if not _import_ok(mod):
                bad.add(f"import 금지: {mod}")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            bad.add(f"이름 금지: {node.id}")
        elif isinstance(node, ast.Attribute) and (node.attr in FORBIDDEN_ATTRS or node.attr.startswith("__")):
            bad.add(f"속성 금지: {node.attr}")
    if not any(isinstance(n, ast.FunctionDef) and n.name == "build_section" for n in tree.body):
        bad.add("최상위 def build_section(spec, ctx) 가 없다")
    return sorted(bad)


@dataclass
class RunResult:
    ok: bool
    glb: Path | None
    node_names: list[str] = field(default_factory=list)
    meshes: int = 0
    triangles: int = 0
    error: str = ""
    stdout: str = ""
    stderr: str = ""


def run_code(code: str, spec_dict: dict, out_glb: Path, *, timeout: float = 120.0) -> RunResult:
    """코드를 임시 디렉터리에 쓰고 `python -I -X utf8 -m m3d.agent.runner` 로 실행한다. 마지막 stdout JSON 줄이 결과."""
    work = Path(tempfile.mkdtemp(prefix="m3d-agent-"))
    code_path, spec_path = work / "code.py", work / "spec.json"
    code_path.write_text(code, encoding="utf-8")
    spec_path.write_text(json.dumps(spec_dict), encoding="utf-8")
    out_glb = Path(out_glb)
    out_glb.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-I", "-X", "utf8", "-m", "m3d.agent.runner", str(code_path), str(spec_path), str(out_glb)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, cwd=str(work))
    except subprocess.TimeoutExpired as exc:
        so = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", "replace")
        se = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", "replace")
        return RunResult(ok=False, glb=None, error=f"시간 초과 {timeout:.0f}s", stdout=so[-2000:], stderr=se[-2000:])
    last = next((ln for ln in reversed(proc.stdout.splitlines()) if ln.startswith("{")), None)
    if last is None:
        return RunResult(ok=False, glb=None, error="러너 결과 없음: " + proc.stderr[-1500:],
                         stdout=proc.stdout[-2000:], stderr=proc.stderr[-2000:])
    res = json.loads(last)
    if not res.get("ok"):
        err = res.get("error", "?") + ("\n" + res["traceback"] if res.get("traceback") else "")
        return RunResult(ok=False, glb=None, error=err, stdout=proc.stdout[-2000:], stderr=proc.stderr[-2000:])
    return RunResult(ok=True, glb=out_glb, node_names=res["nodes"], meshes=res["meshes"], triangles=res["triangles"],
                     stdout=proc.stdout[-2000:], stderr=proc.stderr[-2000:])
