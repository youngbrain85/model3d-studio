"""샌드박스 진입점 (M5 D5) — 별도 프로세스에서 LLM 코드를 실행한다. 인자: code.py spec.json out.glb.

에이전트 코드에는 `ctx`(본체 기하 D2)·툴킷·제한된 builtins 만 보인다. Builder 는 ctx 를 만드는 데만 쓰고 노출하지 않는다.
결과는 stdout 마지막 줄 JSON({"ok": true, "nodes": [...], "meshes": n, "triangles": t} 또는 {"ok": false, "error": ..., "traceback": ...}).
"""

from __future__ import annotations

import builtins as _bi
import json
import re
import sys
import traceback
from pathlib import Path

import trimesh

from m3d.model import geom
from m3d.model.builder import COL_STEEL, INS, Builder
from m3d.model.spec import ModelSpec

NODE_RE = re.compile(r"^AB1_S5_[A-Z0-9_]+$")
_ALLOWED_ROOTS = {"math", "numpy", "trimesh"}
_real_import = _bi.__import__


def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name.split(".")[0] in _ALLOWED_ROOTS or name == "m3d.model.geom" or name.startswith("m3d.model.geom."):
        return _real_import(name, globals, locals, fromlist, level)
    raise ImportError(f"import 금지: {name}")


_SAFE_NAMES = ("abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter", "float", "int", "isinstance", "len",
               "list", "map", "max", "min", "pow", "print", "range", "reversed", "round", "set", "sorted", "str", "sum",
               "tuple", "zip", "Exception", "ValueError", "AssertionError", "KeyError", "IndexError", "True", "False", "None")
SAFE_BUILTINS = {k: getattr(_bi, k) for k in _SAFE_NAMES if hasattr(_bi, k)}
SAFE_BUILTINS["__import__"] = _guarded_import
SAFE_BUILTINS["__build_class__"] = _bi.__build_class__


class BoxContext:
    """에이전트에 노출하는 본체 기하 (D2) — Builder 의 프로파일 함수와 상수만."""

    def __init__(self, b: Builder):
        self.x_web = b.s.box.x_web
        self.z_p4, self.z_p5 = b.Z_P4, b.Z_P5
        self.y_web_top, self.y_web_bot, self.h_box, self.t_web = b.y_web_top, b.y_web_bot, b.h_box, b.t_web
        self.COL_STEEL = list(COL_STEEL)
        self.INS = INS
        self.geom = geom


def _has_colors(m: trimesh.Trimesh) -> bool:
    """paint() 를 거친 메시만 통과 — trimesh 는 색 없는 메시에도 기본 회색 face_colors 를 지어내므로 kind 로 본다."""
    return m.visual.kind in ("face", "vertex")


def _validate(named) -> None:
    if not isinstance(named, dict) or not named:
        raise RuntimeError("반환값은 비어 있지 않은 dict[str, Trimesh] 여야 한다")
    problems = []
    for name, m in named.items():
        if not isinstance(name, str) or not NODE_RE.match(name):
            problems.append(f"노드명 규칙 위반: {name!r} (^AB1_S5_[A-Z0-9_]+$)")
            continue
        if not isinstance(m, trimesh.Trimesh):
            problems.append(f"{name}: Trimesh 아님 ({type(m).__name__})")
            continue
        if len(m.faces) == 0:
            problems.append(f"{name}: 면 없음")
        elif not m.is_watertight:
            problems.append(f"{name}: 수밀 아님(loft/extrude/box_prism 으로 닫힌 솔리드를 만들 것)")
        if not _has_colors(m):
            problems.append(f"{name}: 버텍스 컬러 없음(geom.paint(mesh, ctx.COL_STEEL) 사용)")
    if problems:
        raise RuntimeError("; ".join(problems[:20]))


def main(argv: list[str]) -> None:
    code_path, spec_path, out_glb = (Path(a) for a in argv[1:4])
    spec = ModelSpec.model_validate(json.loads(spec_path.read_text(encoding="utf-8")))
    b = Builder(spec)
    ctx = BoxContext(b)
    g = {"__builtins__": SAFE_BUILTINS, "__name__": "agent_code"}
    exec(compile(code_path.read_text(encoding="utf-8"), "agent_code.py", "exec"), g)   # noqa: S102 — 샌드박스 진입점
    fn = g.get("build_section")
    if not callable(fn):
        raise RuntimeError("build_section 이 정의되지 않았다")
    named = fn(spec.model_dump(), ctx)
    _validate(named)
    b.export(named, out_glb)
    print(json.dumps({"ok": True, "nodes": sorted(named), "meshes": len(named),
                      "triangles": int(sum(len(m.faces) for m in named.values()))}))


if __name__ == "__main__":
    try:
        main(sys.argv)
    except BaseException as exc:      # noqa: BLE001 — 어떤 실패든 JSON 으로 보고
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()[-3000:]},
                         ensure_ascii=False))
        sys.exit(1)
