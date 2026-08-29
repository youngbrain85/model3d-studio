"""시트 렌더 (설계서 §1-2의 2·3) — 원 파이프라인 이식.

계승한 실사고 해법 (원 _검증보고서.md):
  - ACI-7 가드: 배경 WHITE + set_colors("#FFFFFF") — 흑백 자동색이 검정으로 해석
  - HATCH/SOLID/WIPEOUT 선행 드로우 — 텍스트·선이 채움에 덮이지 않게
  - malgun.ttf 강제 + 깨진 style 참조 수리 — 한글 렌더
  - 드로우 실패 시 엔티티 개별 재시도 (PARTIAL — 하나 때문에 시트를 버리지 않음)

matplotlib 은 함수 내부에서만 import 한다 — 부모 프로세스 오염 방지 (멀티프로세싱).
"""

from __future__ import annotations

from pathlib import Path

from m3d.convert.frames import SheetFrame

SHEET_PX = 8000
DARKEN = {          # ACI → 흰 배경 가독 RGB (원 파이프라인 맵 그대로)
    2: (140, 115, 0),
    3: (0, 130, 0),
    4: (0, 120, 145),
    6: (170, 0, 170),
    8: (95, 95, 95),
    9: (110, 110, 110),
}
_FILL_FIRST = ("HATCH", "SOLID", "WIPEOUT")


def prepare_doc(doc) -> None:
    """폰트 강제·style 수리·밝은 색 어둡게 — 렌더 전 1회, 제자리 변형."""
    for style in doc.styles:
        try:
            style.dxf.font = "malgun.ttf"
            if style.dxf.hasattr("bigfont"):
                style.dxf.bigfont = ""
        except Exception:
            pass

    def _fix_styles(space):
        for e in space:
            try:
                if e.dxftype() in ("TEXT", "MTEXT", "ATTRIB", "ATTDEF"):
                    if e.dxf.hasattr("style") and e.dxf.style not in doc.styles:
                        e.dxf.style = "Standard"
            except Exception:
                pass

    def _darken(space):
        for e in space:
            try:
                c = e.dxf.color
                if c in DARKEN:
                    e.rgb = DARKEN[c]
            except Exception:
                pass

    msp = doc.modelspace()
    _fix_styles(msp)
    _darken(msp)
    for blk in doc.blocks:
        _fix_styles(blk)
        _darken(blk)
    for layer in doc.layers:
        if layer.color in DARKEN:
            layer.rgb = DARKEN[layer.color]


def render_frame(doc, frame: SheetFrame, out_png: Path,
                 sheet_px: int = SHEET_PX) -> tuple[int, int]:
    """프레임 하나를 PNG 로 렌더하고 실제 (W, H) 를 반환한다."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    try:
        font_manager.fontManager.addfont(r"C:\Windows\Fonts\malgun.ttf")
    except Exception:
        pass
    plt.rcParams["font.family"] = "Malgun Gothic"
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    from ezdxf import bbox as ezbbox
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing import matplotlib as ezmpl
    from ezdxf.addons.drawing.config import BackgroundPolicy, Configuration

    msp = doc.modelspace()
    w, h = frame.world_w, frame.world_h
    margin = 0.005 * max(w, h)

    # 프레임과 겹치는 엔티티만 선별 (원 로직 — bbox 사전 계산)
    sel = []
    for e in msp:
        try:
            bb = ezbbox.extents([e], fast=True)
            if not bb.has_data:
                continue
            if (bb.extmax.x < frame.x0 - margin or bb.extmin.x > frame.x1 + margin
                    or bb.extmax.y < frame.y0 - margin or bb.extmin.y > frame.y1 + margin):
                continue
            sel.append(e)
        except Exception:
            continue

    # 채움 선행 드로우 — 텍스트·선이 SOLID/HATCH 배너에 덮이지 않게 (원 실사고 해법)
    sel.sort(key=lambda e: 0 if e.dxftype() in _FILL_FIRST else 1)

    def _draw(entities):
        fig = plt.figure(dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_facecolor("#ffffff")
        cfg = Configuration(background_policy=BackgroundPolicy.WHITE)
        ctx = RenderContext(doc)
        backend = ezmpl.MatplotlibBackend(ax)
        fe = Frontend(ctx, backend, config=cfg)
        try:
            ctx.set_current_layout(msp)
        except Exception:
            pass
        try:
            # ACI-7 가드: 용지를 흰색으로 선언해 흑백 자동색이 검정으로 해석되게
            ctx.current_layout_properties.set_colors("#FFFFFF")
        except Exception:
            pass
        return fig, ax, backend, fe

    fig, ax, backend, fe = _draw(sel)
    skipped = 0
    try:
        fe.draw_entities(sel)
    except Exception:
        # 나쁜 엔티티 격리: 개별 재시도, 실패만 건너뜀 (원 PARTIAL 로직)
        plt.close(fig)
        fig, ax, backend, fe = _draw(sel)
        for e in sel:
            try:
                fe.draw_entities([e])
            except Exception:
                skipped += 1
    backend.finalize()

    ax.set_xlim(frame.x0, frame.x1)
    ax.set_ylim(frame.y0, frame.y1)
    ax.set_aspect("equal")
    if w >= h:
        fig.set_size_inches(sheet_px / 100.0, sheet_px / 100.0 * h / w)
    else:
        fig.set_size_inches(sheet_px / 100.0 * w / h, sheet_px / 100.0)

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=100, facecolor="white")
    plt.close(fig)

    with Image.open(out_png) as img:
        return img.width, img.height
