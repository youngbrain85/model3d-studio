"""샌드박스 — AST 화이트리스트, 별도 프로세스 실행, 반환 검증 (M5 D5)."""

import textwrap

import pytest

from m3d.agent import sandbox, schema
from m3d.model.spec import ModelSpec

GOOD = textwrap.dedent('''
    import numpy as np
    from m3d.model.geom import box_prism, paint

    def build_section(spec, ctx):
        d = spec["diaphragm"]
        out = {}
        for k in range(d["n_cell"] + 1):
            zc = ctx.z_p4 + k * d["spacing"]
            zc = min(max(zc, ctx.z_p4 + 0.01), ctx.z_p5 - 0.01)
            m = box_prism(-2.0, 2.0, ctx.y_web_bot(zc), ctx.y_web_top(zc), zc - 0.005, zc + 0.005)
            out["AB1_S5_DIA%02d" % (k + 1)] = paint(m, ctx.COL_STEEL)
        return out
''')


def test_check_code_flags_forbidden_imports_and_names():
    bad = "import os\nfrom subprocess import run\ndef build_section(spec, ctx):\n    open('x')\n    return getattr(ctx, 'x') or ctx.__dict__"
    v = sandbox.check_code(bad)
    assert any("import 금지: os" in x for x in v) and any("subprocess" in x for x in v)
    assert any("이름 금지: open" in x for x in v) and any("이름 금지: getattr" in x for x in v)
    assert any("속성 금지: __dict__" in x for x in v)
    assert sandbox.check_code("x = 1") == ["최상위 def build_section(spec, ctx) 가 없다"]
    syntax = sandbox.check_code("def build_section(spec, ctx):\n  return {")
    assert syntax and "문법 오류" in syntax[0]
    assert sandbox.check_code(GOOD) == []


def test_validate_agent_out_rejects_bad_code():
    with pytest.raises(ValueError, match="import 금지"):
        schema.validate_agent_out(schema.AgentOut(code="import os\ndef build_section(spec, ctx):\n    return {}"))
    schema.validate_agent_out(schema.AgentOut(code=GOOD))


def test_run_code_executes_in_subprocess_and_exports_glb(tmp_path):
    r = sandbox.run_code(GOOD, ModelSpec().model_dump(), tmp_path / "out.glb")
    assert r.ok, r.error
    assert r.meshes == 26 and r.node_names[0] == "AB1_S5_DIA01" and r.node_names[-1] == "AB1_S5_DIA26"
    assert (tmp_path / "out.glb").stat().st_size > 1000 and r.triangles == 26 * 12


def test_run_code_reports_runtime_error_and_bad_return(tmp_path):
    r = sandbox.run_code("def build_section(spec, ctx):\n    return 1 / 0", ModelSpec().model_dump(), tmp_path / "a.glb")
    assert not r.ok and "ZeroDivisionError" in r.error
    r2 = sandbox.run_code("def build_section(spec, ctx):\n    return {'bad name': None}", ModelSpec().model_dump(), tmp_path / "b.glb")
    assert not r2.ok and "노드명 규칙 위반" in r2.error
    r3 = sandbox.run_code("from m3d.model.geom import box_prism\ndef build_section(spec, ctx):\n    return {'AB1_S5_DIA01': box_prism(0, 1, 0, 1, 0, 1)}",
                          ModelSpec().model_dump(), tmp_path / "c.glb")
    assert not r3.ok and "버텍스 컬러" in r3.error


def test_run_code_times_out(tmp_path):
    r = sandbox.run_code("def build_section(spec, ctx):\n    while True:\n        pass", ModelSpec().model_dump(), tmp_path / "t.glb", timeout=3.0)
    assert not r.ok and "시간 초과" in r.error


def test_guarded_import_blocks_at_runtime(tmp_path):
    """AST 를 우회하려 해도(문자열 조립) 러너의 __import__ 가 막는다."""
    code = "def build_section(spec, ctx):\n    m = __builtins__['__import__']('os')\n    return {}"
    assert sandbox.check_code(code)            # AST 단계에서도 걸린다(__builtins__·__import__ 이름 금지)
    r = sandbox.run_code("def build_section(spec, ctx):\n    import socket\n    return {}", ModelSpec().model_dump(), tmp_path / "s.glb")
    assert not r.ok and "import 금지" in r.error
