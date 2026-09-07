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
    z_p4: float = Field(-525.0, description="P4 받침선 전역 z(m) — 이 구간 체인의 시작")
    z_p5: float = Field(-455.0, description="P5 받침선 전역 z(m)")
    el0: float = Field(18.694, description="측점 z_sta3400 에서의 도로 계획고 EL(m)")
    grade: float = Field(0.0236, description="종단경사(무차원) — 계획고 = el0 + grade·(z − z_sta3400)")
    z_sta3400: float = Field(-790.0, description="계획고 기준 측점의 전역 z(m)")
    y_datum: float = Field(4.871, description="모델 y 원점 보정(m) — 모델 y = EL − y_datum")
    deck_drop: float = Field(0.398, description="계획고에서 강상판 상면까지 내림(m, y) [Q2] — 포장 + crown 슬래브 두께")
    t_slab_crown: float = Field(0.348, description="crown 위치 슬래브 두께(m, y) — 강상판 상면 + 이 값 = 슬래브 crown 상면")
    walk_side_sign: int = Field(-1, description="보도(캔틸레버가 넓은 쪽) x 부호 — −1 이면 −x 가 보도측(서측)")
    segment: str = Field("P4P5", description="구간 이름 — 섹션 키 '<구간>/<부재코드>' 와 섹션 GLB 폴더명")

    @property
    def span(self) -> float:
        return self.z_p5 - self.z_p4


class Box(BaseModel):
    """§1 강상자 본체(변단면)."""
    half_flange: float = Field(2.35, description="상·하 플랜지 반폭(m, x) — 웹 외면(x_web)보다 바깥으로 나온다")
    x_web: float = Field(2.25, description="웹 외면 x(m) [A21] — 웹은 ±x_web, 내면은 ±(x_web − t_web(z))")
    h_pier: float = Field(4.0, description="받침선 내공 높이 H(m, y) [Q1] — 받침선 ±l_flat 구간에서 일정")
    h_mid: float = Field(2.8, description="중앙부 내공 높이 H(m, y)")
    l_flat: float = Field(1.25, description="받침선에서 등고 구간 길이(m, z) — 이 안에서는 H = h_pier")
    l_para: float = Field(13.45, description="포물선 변단면 구간 길이(m, z) — 등고 끝에서 중앙 등고 시작까지")
    a_dwg: float = Field(0.00663, description="도면 표기 포물선 계수(1/m) — H(d) = h_mid + a·(l_flat+l_para−d)², 검산용")
    h_is_clear: bool = Field(True, description="형고 H 를 내공(강상판 하면~하판 상면)으로 본다는 표시 [Q1][A1]")
    top_t: list[Zone] = Field([(0.0, 6.3, 0.038), (6.3, 16.1, 0.026), (16.1, 53.9, 0.016),
                               (53.9, 63.7, 0.026), (63.7, 70.0, 0.038)],
                              description="상판 두께 존 [(d0, d1, t)] — d 는 P4 로부터 거리(m, z), t 는 두께(m, y)")
    bot_t: list[Zone] = Field([(0.0, 3.5, 0.038), (3.5, 13.3, 0.028), (13.3, 25.9, 0.018),
                               (25.9, 44.1, 0.014), (44.1, 56.7, 0.018), (56.7, 66.5, 0.028),
                               (66.5, 70.0, 0.038)],
                              description="하판 두께 존 [(d0, d1, t)] — d 는 P4 로부터 거리(m, z), t 는 두께(m, y)")
    web_t: list[Zone] = Field([(0.0, 11.9, 0.016), (11.9, 58.1, 0.012), (58.1, 70.0, 0.016)],
                              description="웹 두께 존 [(d0, d1, t)] — d 는 P4 로부터 거리(m, z), t 는 두께(m, x)")
    z_sp04_offset: float = Field(18.9, description="P4 에서 SP04 현장이음선까지 거리(m, z)")


class Diaphragm(BaseModel):
    """§2 격벽 26면 — P4 + spacing·k. description 은 에이전트 프롬프트의 스펙 발췌 doc 이 된다(M6 D1)."""
    spacing: float = Field(2.8, description="격벽 간격(m) — 전역 체인 z = z_p4 + k·spacing")
    n_cell: int = Field(25, description="격실 수 — 격벽 수 = n_cell + 1 (01 = P4 받침선, 마지막 = P5 받침선)")
    support_t: float = Field(0.038, description="지점 격벽(01·마지막) 판 두께(m, z 방향) — 판면 한쪽이 받침선 z 에 놓이고 두께는 경간 안쪽으로")
    support_open: tuple[float, float] = Field((0.7, 0.7), description="(폭 x, 높이 y) 지점 격벽 개구(m), 개구는 x 중심")
    support_sill: float = Field(0.45, description="지점 격벽 개구 문턱 높이(m) — 하판 상면 y_web_bot(z) 기준")
    support_vstiff: tuple[float, float, int] = Field(
        (0.026, 0.24, 12),
        description="(t 두께[x 방향], w 돌출[판면에서 경간 안쪽 z], n 총 개수) 지점 격벽 수직보강재 — 내공 전 높이; "
                    "참조 단순화 [A4]: 경간 안쪽 면에만 받침 x·x±0.2 의 3열 × 좌우 = 6")
    support_jack: tuple[float, float, float] = Field(
        (0.022, 0.35, 1.15),
        description="(t 두께[x], w 돌출[판면에서 경간 안쪽 z], h 높이[y]) 지점 격벽 잭업보강재 — 받침 x 직상(상판 밑 h)·직하(하판 위 h) 각 1 × 좌우 = 4, "
                    "경간 안쪽 면에만")
    interior_t: float = Field(0.010, description="일반 격벽 판 두께(m, z) — 두께 중심을 체인 위치에")
    interior_open: tuple[float, float] = Field((1.4, 1.4), description="(폭 x, 높이 y) 일반 격벽 개구(m), x 중심")
    sill_cl: float = Field(0.45, description="CL 계열 일반 격벽 개구 문턱(m, y_web_bot 기준)")
    sill_cx: float = Field(0.40, description="CX 계열 일반 격벽 개구 문턱(m)")
    h_table: list[tuple[float, float]] = Field(
        [(2.8, 3.739), (5.6, 3.349), (8.4, 3.063), (11.2, 2.881), (14.0, 2.803)],
        description="(받침선으로부터 거리 d, 격벽 높이) 판독 대조값 — 판 높이는 ctx 내공(y_web_bot~y_web_top)에서 유도하고 이 표는 검산용")
    type_map: list[tuple[float, str]] = Field(
        [(2.8, "CL"), (5.6, "CL3"), (8.4, "CL6"), (11.2, "CL7"), (14.0, "CX"), (16.8, "CX1"), (19.6, "CX1"), (22.4, "CX1")],
        description="(받침선으로부터 거리 d, 타입명) — dmin = 양 받침선까지 최소 거리; CX 로 시작하는 타입의 d 범위(min−0.1 < dmin < max+0.1) 이면 sill_cx, "
                    "아니면 sill_cl")
    open_stiff: tuple[float, float, float, float] = Field(
        (0.010, 0.100, 0.090, 1.56),
        description="(t 두께[상·하변은 y, 좌·우변은 x], h_h 상·하변 돌출[z], h_v 좌·우변 돌출[z], l 길이) 일반 격벽 개구보강재 — 격벽 판면에 수직으로 선 판이라 "
                    "z 로는 두께 t 가 아니라 돌출 h 만큼 뻗는다; 개구 4변 바깥에 붙여 판의 +z 면에만 돌출(참조 단순화 [A5]); "
                    "개구 안으로 들어오지 않는다: 좌·우변은 x = ±폭/2 에서 바깥쪽으로 t(y 중심 길이 l), 상·하변은 문턱 y 아래·개구 상단 y 위로 t(x 중심 길이 l)")

class FrameRow(BaseModel):
    d_list: list[float] = Field(..., description="이 타입이 쓰이는 받침선 거리 dmin(m) 목록 — dmin = 양 받침선까지 최소 거리")
    name: str = Field(..., description="도면 타입명(F·F3·G1·D 등) — 형상에는 영향 없음")
    top_web: tuple[float, float] = Field(..., description="(t 두께[z], h 높이[y]) 상부 가로보 웹 — 강상판 하면에서 아래로 h")
    bot_web: tuple[float, float] = Field(..., description="(t 두께[z], h 높이[y]) 하부 가로보 웹 — 하판 상면에서 위로 h")
    vstiff: tuple[float, float, float] = Field(..., description="(t 두께[z], w 폭[x, 웹 내면에서 안쪽], l 길이[y]) 프레임 수직보강재 — l 은 내공 높이가 아니라 이 표의 값 그대로이고, 내공 중앙(상·하판 중점)에 ±l/2 로 놓는다 [A7]")
    top_flange_t: float | None = Field(None, description="상부 플랜지 두께(m, y) — None 이면 상부 웹 두께와 같게 본다 [A6]")


class Frame(BaseModel):
    """§3 개방 프레임 25개 — 격벽 사이 offset 위치."""
    offset: float = Field(1.4, description="P4 에서 첫 프레임까지 거리(m, z) — 프레임 z = z_p4 + offset + k·격벽간격")
    rows: list[FrameRow] = Field([
        FrameRow(d_list=[1.4], name="F", top_web=(0.012, 0.25), bot_web=(0.040, 0.36), vstiff=(0.026, 0.32, 3.313)),
        FrameRow(d_list=[4.2], name="F3", top_web=(0.012, 0.25), bot_web=(0.036, 0.36), vstiff=(0.028, 0.28, 2.873)),
        FrameRow(d_list=[7.0], name="F6", top_web=(0.012, 0.25), bot_web=(0.036, 0.35), vstiff=(0.026, 0.26, 2.545)),
        FrameRow(d_list=[9.8], name="F9", top_web=(0.012, 0.25), bot_web=(0.036, 0.35), vstiff=(0.018, 0.20, 2.311)),
        FrameRow(d_list=[12.6], name="F10", top_web=(0.012, 0.25), bot_web=(0.030, 0.36), vstiff=(0.020, 0.18, 2.179)),
        FrameRow(d_list=[15.4, 18.2, 21.0, 23.8], name="G1", top_web=(0.020, 0.35), bot_web=(0.026, 0.35), vstiff=(0.014, 0.15, 2.054), top_flange_t=0.026),
        FrameRow(d_list=[26.6, 29.4, 32.2, 35.0], name="D", top_web=(0.026, 0.35), bot_web=(0.012, 0.25), vstiff=(0.014, 0.15, 2.162)),
    ], description="dmin 별 프레임 부재 규격 표 — 프레임마다 dmin 으로 행을 골라 6부재(TRW·TRF·BRW·BRF·VSL·VSR)를 만든다")


class RibZone(BaseModel):
    cols: int = Field(..., description="열 수(개) — x 방향으로 늘어선 리브 줄 수")
    pitch: float = Field(..., description="열 간격(m, x) — 열은 x=0 중심 대칭 배치")
    t: float = Field(..., description="리브 판 두께(m, x)")
    h: float = Field(..., description="리브 높이(m, y) — 붙는 판면에서 내공 쪽으로")
    from_web: float | None = Field(None, description="웹면에서 첫 열까지 거리(m, x) 표기값 — 참조 빌더는 형상에 쓰지 않는다: 모든 존의 열은 x=0 중심 대칭으로 (i − (cols−1)/2)·pitch (i=0..cols−1)")


class Rib(BaseModel):
    """§4 종리브 존 모델."""
    top_pier: RibZone = Field(RibZone(cols=3, pitch=1.124, t=0.014, h=0.150, from_web=1.126),
                              description="지점부 상판(강상판) 리브 존 — 받침선 쪽")
    top_mid: RibZone = Field(RibZone(cols=8, pitch=0.5, t=0.014, h=0.150), description="중앙부 상판 리브 존")
    top_switch: tuple[float, float] = Field((12.594, 15.753),
                                            description="(d0, d1) 상판 리브 존 전이 구간(m, P4 로부터 거리) — 그 사이 구간에는 두 존의 열을 함께 둔다")
    bot_pier: RibZone = Field(RibZone(cols=8, pitch=0.5, t=0.018, h=0.180), description="지점부 하판 리브 존")
    bot_mid: RibZone = Field(RibZone(cols=3, pitch=1.124, t=0.014, h=0.150, from_web=1.126), description="중앙부 하판 리브 존")
    bot_switch: tuple[float, float] = Field((22.118, 25.205),
                                            description="(d0, d1) 하판 리브 존 전이 구간(m, P4 로부터 거리)")


class HStiff(BaseModel):
    """§5 복부 수평보강재."""
    t: float = Field(0.012, description="평강 두께(m, y)")
    h: float = Field(0.150, description="웹 내면에서 내공 쪽으로 내민 길이(m, x)")
    upper_drop: float = Field(0.560, description="강상판 하면에서 상단열 중심까지(m, y)")
    upper_span: float = Field(12.6, description="상단열이 빠지는 받침선 쪽 구간(m, z) — 상단열은 P4+이 값 ~ P5−이 값에만 있다")
    lower_span: float = Field(25.2, description="하단열이 놓이는 받침선 쪽 구간 길이(m, z) — 각 받침선에서 안쪽으로")
    lower_factors: tuple[float, float] = Field((0.14, 0.36),
                                               description="하단 2열의 높이 비율 — y = 하판 상면 + 비율·H(z); 격벽 간격 절반마다 절선으로 H 를 따라간다 [A20]")


class WG(BaseModel):
    """§6 외측가로보 26쌍 (WG096~121 L/R)."""
    first_no: int = Field(96, description="첫 가로보 번호 — 노드명에 3자리로 붙는다(WG096L … WG121R), 격벽 체인 순서와 같다")
    length: float = Field(4.45, description="웹 외면에서 선단까지 내민 길이(m, x)")
    flange_slope: float = Field(0.0195, description="상플랜지 기울기(무차원) — 바깥으로 갈수록 내려간다")
    flange_flat0: float = Field(0.1, description="웹면에서 기울기가 시작되는 지점까지(m, x) — 그 안쪽은 수평")
    flange_flat1: float = Field(4.3, description="웹면에서 기울기가 끝나는 지점까지(m, x) — 그 바깥은 다시 수평")
    depth0: float = Field(0.3, description="웹면 위치에서의 가로보 춤(m, y)")
    web_t: float = Field(0.012, description="가로보 웹 두께(m, z)")
    fl_t: float = Field(0.012, description="가로보 플랜지 두께(m, y)")
    fl_w: float = Field(0.3, description="가로보 플랜지 폭(m, z)")
    niche_r: float = Field(0.3, description="니치 원호 반지름(m) — 웹 부착부 하단 곡선")
    knee: tuple[float, float] = Field((3.9, 0.482),
                                      description="(x 웹 외면에서 거리[x], y 강상판 상면 ctx.y_deck_top 아래 깊이[y]) 하플랜지 절선점 겸 스트럿 상단 작업점")
    tip_depth: float = Field(0.424, description="선단 블록 춤(m, y) — 외측빔 CS 춤과 같다")
    strut_size: float = Field(0.3, description="스트럿 단면 한 변(m) — 정사각 단면")
    strut_angle_deg: float = Field(28.222, description="스트럿 축 각도(도) 검산값 — 참조 빌더는 형상에 쓰지 않는다(각도는 strut_lower 와 가로보 부착점에서 나온다)")
    strut_lower: tuple[float, float] = Field((0.302, 2.413),
                                             description="(x 웹 외면에서 거리[x], y 강상판 상면 ctx.y_deck_top 아래 깊이[y]) 스트럿 하단 작업점 — 스트럿은 이 점에서 knee 점까지 뻗는다(x 로 3.6m 넘게 눕는 긴 부재)")
    bracket: tuple[float, float, float] = Field((0.35, 2.17, 2.70),
                                                description="(d 돌출[x, 웹 외면에서 바깥], y0 상단 깊이, y1 하단 깊이 — 둘 다 ctx.y_deck_top 아래로 재는 값[y]) 웹 부착 정착대 [A11]: x 는 웹 외면−INS ~ 웹 외면+d, y 는 y_deck_top−y1 ~ y_deck_top−y0")


class CS(BaseModel):
    """§7 외측빔 26세그 ×2."""
    depth: float = Field(0.424, description="외측빔 춤(m, y) — 가로보 선단 블록 춤과 같다")
    web_t: float = Field(0.012, description="외측빔 웹 두께(m, x)")
    fl_w: float = Field(0.3, description="외측빔 플랜지 폭(m, x)")
    fl_t: float = Field(0.012, description="외측빔 플랜지 두께(m, y)")
    seg: float = Field(2.8, description="세그먼트 길이(m, z) — 가로보 간격과 같다. 각 세그는 그 가로보의 체인 위치를 **중심**으로 ±seg/2 이고 받침선 밖은 잘린다")


class Slab(BaseModel):
    """§8 슬래브 + 방호벽."""
    half_width: float = Field(7.85, description="슬래브 반폭(m, x) — 전폭 15.7")
    slope: float = Field(0.02, description="횡단 경사(무차원) — crown(x=0)에서 바깥으로 내려간다")
    t_edge: float = Field(0.25, description="연단(선단) 슬래브 두께(m, y) — 참조 빌더는 형상에 쓰지 않는다(하면은 cant_drop 절선으로 만든다)")
    t_web: float = Field(0.30, description="웹 위 슬래브 두께(m, y) — 참조 빌더는 형상에 쓰지 않는다(하면은 cant_drop 절선으로 만든다)")
    t_crown: float = Field(0.348, description="crown 슬래브 두께(m, y) — 참조 빌더는 형상에 쓰지 않는다(같은 값인 coord.t_slab_crown 을 쓴다)")
    thickness_is_net: bool = Field(True, description="두께가 포장을 뺀 순두께라는 표시 [Q2] — 참조 빌더는 형상에 쓰지 않는다")
    cant_drop: list[tuple[float, float]] = Field([(2.35, 0.330), (6.55, 0.418), (7.85, 0.398)],
                                                 description="[(x 중심에서 거리[x], crown 상면에서 내림[y])] 캔틸레버 하면 절선 — 이 점들을 이어 하면을 만든다")
    walk_width: float = Field(2.95, description="보도 폭(m, x) [Q3] — 보도측은 coord.walk_side_sign 이 정한다")
    center_barrier: float = Field(0.45, description="보도-차도 경계 방호벽(노드 BARRIER_CTR)의 폭(m, x) — x=0 중앙이 아니다. 위치는 보도측(coord.walk_side_sign)의 연단 방호벽 안쪽 끝에서 walk_width 만큼 안쪽: 안쪽 끝 x = sign·(half_width − barrier[0] − walk_width), 거기서 차도 쪽으로 이 폭만큼")
    barrier: tuple[float, float, float] = Field((0.45, 0.33, 0.03),
                                                description="(w 폭[x], h 높이[y], ch 상단 모따기[x·y 같은 값]) 연단 방호벽 단면 — 슬래브 상면에서 위로 h, 상단 두 모서리를 ch 만큼 깎는다")


class SP04(BaseModel):
    """§9 SP04 이음 외면판."""
    tf: tuple[float, float, float] = Field((4.386, 0.58, 0.010),
                                           description="(w 폭[x], l 길이[z], t 두께[y]) 상면 이음판 — 강상판 상면(ctx.y_deck_top) 위에 덧댄다")
    bf: tuple[float, float, float] = Field((4.7, 0.78, 0.012),
                                           description="(w 폭[x], l 길이[z], t 두께[y]) 하면 이음판 — 하판 하면(ctx.y_bot_out) 아래에 덧댄다")
    web: tuple[float, float, float] = Field((2.68, 0.58, 0.010),
                                            description="(h 높이[y], l 길이[z], t 두께[x]) 복부 이음판 — 웹 외면(±ctx.x_web) 바깥에 좌·우 1매씩")
    setback: float = Field(0.157, description="도면 표기 뒷물림(m) [A17] — 참조 빌더는 형상에 쓰지 않는다: 네 판 모두 중심을 이음선 z = z_p4 + box.z_sp04_offset 에 둔다")


class Bearing(BaseModel):
    """§10 받침 4기."""
    x: float = Field(1.55, description="받침 중심 x(m) — 좌우 대칭 ±x")
    kind: str = Field("isolation", description="받침 종류(면진, 잠정) [Q4] — 형상에는 영향 없음")
    sole: tuple[float, float, float, float] = Field((1.37, 0.022, 0.054, 0.038),
                                                    description="(a 한 변[x·z], t0, t1, t 두께[y]) 솔플레이트 — 참조 빌더는 첫 값을 한 변으로, **네 번째 값을 판 두께**로 쓴다(둘째·셋째는 형상에 쓰지 않는다). 하판 하면 ctx.y_bot_out(받침선) 에서 아래로 그 두께만큼")
    body_h: float = Field(0.337, description="하판 하면에서 받침 하면까지 깊이(m, y) — 본체 자체 높이가 아니다. ctx.y_bot_out(받침선) − body_h 가 받침 하면이고 EL 검산(el_check) 기준면이다 [A18]. 본체는 그 면과 솔플레이트 밑면 사이를 채운다")
    base: float = Field(0.825, description="받침 하부판 한 변(m, x·z)")
    body_d: float = Field(0.65, description="받침 본체 지름(m, x·z) — 원형 단면")
    mortar: tuple[float, float] = Field((0.05, 0.9), description="(t 두께[y], a 한 변[x·z]) 무수축 모르타르 — 받침 하면에서 아래로 t")
    block: tuple[float, float] = Field((1.3, 0.105), description="(a 한 변[x·z], t 두께[y]) 받침 블록 — 모르타르 밑면에서 아래로 t. 모델 최하단")
    el_check: dict[str, float] = Field(default_factory=lambda: {"P4": 20.137, "P5": 21.789},
                                       description="교각별 받침 하면 EL 검산값(m) — 모델 y = EL − coord.y_datum")


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
