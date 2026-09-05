"""ModelSpec — P4~P5 정밀 모델의 파라미터 사양 (M3 설계서 §3).

참조 SPEC_v2 §0~§10 의 구조를 필드로 옮겼다. 값은 m 단위(내부), 기본값은 참조 사양(2026-08-17)
그대로다 — `spec_rules.build_modelspec` 이 SSOT·결정으로 덮어쓰고, 필드마다 출처를 남긴다.
빌더는 이 객체만 읽고 상수를 갖지 않는다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

Zone = tuple[float, float, float]          # (d0, d1, t) — P4 기점 거리 m, 두께 m


class Coord(BaseModel):
    """§0 좌표계·기준. x=교축직각, y=EL−y_datum, z=STA−4190 (m, Y-up)."""
    z_p4: float = -525.0
    z_p5: float = -455.0
    el0: float = 18.694
    grade: float = 0.0236
    z_sta3400: float = -790.0
    y_datum: float = 4.871
    deck_drop: float = 0.398            # [Q2] 강상판 상면 EL = 계획고 − 0.398
    t_slab_crown: float = 0.348
    walk_side_sign: int = -1            # 보도측 = −x (서측)

    @property
    def span(self) -> float:
        return self.z_p5 - self.z_p4


class Box(BaseModel):
    """§1 강상자 본체(변단면)."""
    half_flange: float = 2.35
    x_web: float = 2.25                 # [A21] 웹 외면
    h_pier: float = 4.0                 # [Q1] 내공(등고, 받침선 ±l_flat)
    h_mid: float = 2.8
    l_flat: float = 1.25
    l_para: float = 13.45
    a_dwg: float = 0.00663              # H(d)=h_mid+a·(l_flat+l_para−d)² (m⁻¹ 환산)
    h_is_clear: bool = True             # [Q1] 형고 = 내공
    top_t: list[Zone] = [(0.0, 6.3, 0.038), (6.3, 16.1, 0.026), (16.1, 53.9, 0.016),
                         (53.9, 63.7, 0.026), (63.7, 70.0, 0.038)]
    bot_t: list[Zone] = [(0.0, 3.5, 0.038), (3.5, 13.3, 0.028), (13.3, 25.9, 0.018),
                         (25.9, 44.1, 0.014), (44.1, 56.7, 0.018), (56.7, 66.5, 0.028),
                         (66.5, 70.0, 0.038)]
    web_t: list[Zone] = [(0.0, 11.9, 0.016), (11.9, 58.1, 0.012), (58.1, 70.0, 0.016)]
    z_sp04_offset: float = 18.9


class Diaphragm(BaseModel):
    """§2 격벽 26면 — P4 + spacing·k."""
    spacing: float = 2.8
    n_cell: int = 25
    support_t: float = 0.038
    support_open: tuple[float, float] = (0.7, 0.7)
    support_sill: float = 0.45
    support_vstiff: tuple[float, float, int] = (0.026, 0.24, 12)
    support_jack: tuple[float, float, float] = (0.022, 0.35, 1.15)
    interior_t: float = 0.010
    interior_open: tuple[float, float] = (1.4, 1.4)
    sill_cl: float = 0.45
    sill_cx: float = 0.40
    h_table: list[tuple[float, float]] = [(2.8, 3.739), (5.6, 3.349), (8.4, 3.063),
                                          (11.2, 2.881), (14.0, 2.803)]
    type_map: list[tuple[float, str]] = [(2.8, "CL"), (5.6, "CL3"), (8.4, "CL6"), (11.2, "CL7"),
                                         (14.0, "CX"), (16.8, "CX1"), (19.6, "CX1"), (22.4, "CX1")]
    open_stiff: tuple[float, float, float, float] = (0.010, 0.100, 0.090, 1.56)


class FrameRow(BaseModel):
    d_list: list[float]
    name: str
    top_web: tuple[float, float]        # (t, h)
    bot_web: tuple[float, float]
    vstiff: tuple[float, float, float]  # (t, w, h)
    top_flange_t: float | None = None   # None → 웹 두께와 동일 [A6]; G1 은 BOM 26t


class Frame(BaseModel):
    """§3 개방 프레임 25개 — 격벽 사이 offset 위치."""
    offset: float = 1.4
    rows: list[FrameRow] = [
        FrameRow(d_list=[1.4], name="F", top_web=(0.012, 0.25), bot_web=(0.040, 0.36), vstiff=(0.026, 0.32, 3.313)),
        FrameRow(d_list=[4.2], name="F3", top_web=(0.012, 0.25), bot_web=(0.036, 0.36), vstiff=(0.028, 0.28, 2.873)),
        FrameRow(d_list=[7.0], name="F6", top_web=(0.012, 0.25), bot_web=(0.036, 0.35), vstiff=(0.026, 0.26, 2.545)),
        FrameRow(d_list=[9.8], name="F9", top_web=(0.012, 0.25), bot_web=(0.036, 0.35), vstiff=(0.018, 0.20, 2.311)),
        FrameRow(d_list=[12.6], name="F10", top_web=(0.012, 0.25), bot_web=(0.030, 0.36), vstiff=(0.020, 0.18, 2.179)),
        FrameRow(d_list=[15.4, 18.2, 21.0, 23.8], name="G1", top_web=(0.020, 0.35), bot_web=(0.026, 0.35), vstiff=(0.014, 0.15, 2.054), top_flange_t=0.026),
        FrameRow(d_list=[26.6, 29.4, 32.2, 35.0], name="D", top_web=(0.026, 0.35), bot_web=(0.012, 0.25), vstiff=(0.014, 0.15, 2.162)),
    ]


class RibZone(BaseModel):
    cols: int
    pitch: float
    t: float
    h: float
    from_web: float | None = None       # 지점존 3열: 웹면에서 첫 열 거리


class Rib(BaseModel):
    """§4 종리브 존 모델."""
    top_pier: RibZone = RibZone(cols=3, pitch=1.124, t=0.014, h=0.150, from_web=1.126)
    top_mid: RibZone = RibZone(cols=8, pitch=0.5, t=0.014, h=0.150)
    top_switch: tuple[float, float] = (12.594, 15.753)
    bot_pier: RibZone = RibZone(cols=8, pitch=0.5, t=0.018, h=0.180)
    bot_mid: RibZone = RibZone(cols=3, pitch=1.124, t=0.014, h=0.150, from_web=1.126)
    bot_switch: tuple[float, float] = (22.118, 25.205)


class HStiff(BaseModel):
    """§5 복부 수평보강재."""
    t: float = 0.012
    h: float = 0.150
    upper_drop: float = 0.560
    upper_span: float = 12.6
    lower_span: float = 25.2
    lower_factors: tuple[float, float] = (0.14, 0.36)


class WG(BaseModel):
    """§6 외측가로보 26쌍 (WG096~121 L/R)."""
    first_no: int = 96
    length: float = 4.45
    flange_slope: float = 0.0195
    flange_flat0: float = 0.1
    flange_flat1: float = 4.3
    depth0: float = 0.3
    web_t: float = 0.012
    fl_t: float = 0.012
    fl_w: float = 0.3
    niche_r: float = 0.3
    knee: tuple[float, float] = (3.9, 0.482)
    tip_depth: float = 0.424
    strut_size: float = 0.3
    strut_angle_deg: float = 28.222
    strut_lower: tuple[float, float] = (0.302, 2.413)
    bracket: tuple[float, float, float] = (0.35, 2.17, 2.70)


class CS(BaseModel):
    """§7 외측빔 26세그 ×2."""
    depth: float = 0.424
    web_t: float = 0.012
    fl_w: float = 0.3
    fl_t: float = 0.012
    seg: float = 2.8


class Slab(BaseModel):
    """§8 슬래브 + 방호벽."""
    half_width: float = 7.85
    slope: float = 0.02
    t_edge: float = 0.25
    t_web: float = 0.30
    t_crown: float = 0.348
    thickness_is_net: bool = True       # [Q2]
    cant_drop: list[tuple[float, float]] = [(2.35, 0.330), (6.55, 0.418), (7.85, 0.398)]
    walk_width: float = 2.95            # [Q3]
    center_barrier: float = 0.45
    barrier: tuple[float, float, float] = (0.45, 0.33, 0.03)


class SP04(BaseModel):
    """§9 SP04 이음 외면판."""
    tf: tuple[float, float, float] = (4.386, 0.58, 0.010)
    bf: tuple[float, float, float] = (4.7, 0.78, 0.012)
    web: tuple[float, float, float] = (2.68, 0.58, 0.010)
    setback: float = 0.157


class Bearing(BaseModel):
    """§10 받침 4기."""
    x: float = 1.55
    kind: str = "isolation"             # [Q4] 면진(잠정)
    sole: tuple[float, float, float, float] = (1.37, 0.022, 0.054, 0.038)
    body_h: float = 0.337
    base: float = 0.825
    body_d: float = 0.65
    mortar: tuple[float, float] = (0.05, 0.9)
    block: tuple[float, float] = (1.3, 0.105)
    el_check: dict[str, float] = Field(default_factory=lambda: {"P4": 20.137, "P5": 21.789})


class ModelSpec(BaseModel):
    coord: Coord = Field(default_factory=Coord)
    box: Box = Field(default_factory=Box)
    diaphragm: Diaphragm = Field(default_factory=Diaphragm)
    frame: Frame = Field(default_factory=Frame)
    rib: Rib = Field(default_factory=Rib)
    hstiff: HStiff = Field(default_factory=HStiff)
    wg: WG = Field(default_factory=WG)
    cs: CS = Field(default_factory=CS)
    slab: Slab = Field(default_factory=Slab)
    sp04: SP04 = Field(default_factory=SP04)
    bearing: Bearing = Field(default_factory=Bearing)


def leaf_paths(model: BaseModel, prefix: str = "") -> list[str]:
    """출처 통계용 — 리프 필드 경로 목록 (표·리스트는 한 필드로 센다)."""
    out: list[str] = []
    for name in type(model).model_fields:
        value = getattr(model, name)
        path = f"{prefix}{name}"
        if isinstance(value, BaseModel):
            out.extend(leaf_paths(value, path + "."))
        else:
            out.append(path)
    return out
