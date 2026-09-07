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


def test_section_context_exposes_full_box_profile_and_zone_loft():
    """확산에 필요한 본체 프로파일·색·존 로프트를 ctx 가 준다(M7 D1)."""
    from m3d.agent.runner import SectionContext
    from m3d.model.builder import Builder
    from m3d.model.spec import ModelSpec
    spec = ModelSpec()
    ctx = SectionContext(Builder(spec))
    z = spec.coord.z_p4 + 10.0
    assert abs(ctx.span - (spec.coord.z_p5 - spec.coord.z_p4)) < 1e-9
    assert ctx.y_deck_top(z) > ctx.y_web_top(z) > ctx.y_web_bot(z) > ctx.y_bot_out(z)
    assert abs(ctx.y_crown(z) - (ctx.y_deck_top(z) + spec.coord.t_slab_crown)) < 1e-9
    assert ctx.t_top(z) > 0 and ctx.t_bot(z) > 0 and ctx.el_road(z) > 0
    assert ctx.COL_CONC != ctx.COL_STEEL and ctx.COL_BRG != ctx.COL_SOLE
    mesh = ctx.zone_loft(spec.coord.z_p4, spec.coord.z_p4 + 20.0,
                         lambda zz: ctx.geom.rect(-0.1, 0.1, ctx.y_web_bot(zz), ctx.y_web_bot(zz) + 0.2))
    assert mesh.is_watertight and len(mesh.faces) > 0


def test_section_context_hides_builder_internals():
    """빌더 자체는 계약에 없다 — 밑줄 속성만 남기고 공개 이름으로 새지 않는다."""
    from m3d.agent.runner import SectionContext
    from m3d.model.builder import Builder
    from m3d.model.spec import ModelSpec
    ctx = SectionContext(Builder(ModelSpec()))
    public = [n for n in vars(ctx) if not n.startswith("_")]
    assert "build" not in public and "s" not in public
    assert set(public) >= {"x_web", "z_p4", "z_p5", "span", "y_deck_top", "t_top", "COL_CONC"}


def test_from_m3d_model_import_geom_is_allowed():
    """`from m3d.model import geom` 은 정상 사용법이다 — 이걸 막으면 잡이 통째로 죽는다(M7 배치 1 BRG)."""
    code = "from m3d.model import geom\ndef build_section(spec, ctx):\n    return {}\n"
    assert sandbox.check_code(code) == []


def test_import_of_other_m3d_modules_still_blocked():
    for line in ("from m3d.model import builder", "import m3d.model.builder", "from m3d import config"):
        code = line + "\ndef build_section(spec, ctx):\n    return {}\n"
        assert any("import 금지" in v for v in sandbox.check_code(code)), line


def test_watertight_error_says_how_the_mesh_is_broken():
    """'수밀 아님' 만으로는 못 고친다 — 경계 모서리·조각 수를 함께 준다(M7 배치 2 SLAB)."""
    import trimesh
    from m3d.agent.runner import _validate
    open_box = trimesh.creation.box(extents=(1, 1, 1))
    open_box.update_faces([True] * (len(open_box.faces) - 2) + [False, False])   # 면 2개 제거 → 구멍
    open_box.visual.face_colors = [0, 150, 168, 255]
    try:
        _validate({"AB1_S5_TEST": open_box})
    except RuntimeError as exc:
        msg = str(exc)
    else:
        raise AssertionError("수밀 아님을 잡지 못했다")
    assert "수밀 아님" in msg and "경계 모서리" in msg and "자기교차" in msg
