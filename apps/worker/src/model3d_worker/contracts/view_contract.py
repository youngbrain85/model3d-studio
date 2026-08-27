"""뷰 계약 수학 — 규칙 §7.

뷰는 3D 공간 안의 유한 직사각형 평면이다::

    n = u_axis × v_axis                                (오른손 규칙, handedness=right 전제)
    정변환  W(u, v) = origin + u·u_axis + v·v_axis
    역변환  d = P − origin,  u = d·u_axis,  v = d·v_axis,  h = d·n

왕복 검산 조건 — 셋 다 성립해야 PASS:

* **R1 시트 왕복** ``역변환(정변환(u,v)) = (u,v)``
  ⇔ ``|u_axis| = 1``, ``|v_axis| = 1``, ``u_axis·v_axis = 0``.
  증명: ``u' = (u·u_axis + v·v_axis)·u_axis = u·|u_axis|² + v·(u_axis·v_axis)``.
  모든 u,v 에서 ``u' = u`` 이려면 ``|u_axis|² = 1`` 이고 ``u_axis·v_axis = 0``. v 도 대칭.
* **R2 모델 왕복** ``origin + u·u_axis + v·v_axis + h·n = P`` (평면 밖 점까지 복원)
  ⇔ ``{u_axis, v_axis, n}`` 이 정규직교기저.
* **R3 픽셀 왕복** ``pixel_to_view(view_to_pixel(u,v)) = (u,v)``.

TS 쪽 대응: ``packages/contracts/src/viewContract.ts``.
두 구현은 ``packages/contracts/fixtures/view_contract.cases.json`` 으로 교차 검증된다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .models import PassFail, RoundtripCheck, ViewContract

Vec3 = tuple[float, float, float]

#: 축 단위길이·직교성 판정 허용오차 (무차원)
DEFAULT_AXIS_TOLERANCE = 1e-9

#: 왕복 검산 기본 허용오차 (m). 1 nm — 교량 규모(10²m)의 배정밀도 ULP(~10⁻¹⁴ m)보다
#: 한참 크고 모델 정밀도보다 한참 작다.
DEFAULT_ROUNDTRIP_TOLERANCE_M = 1e-9

#: 정의역 포함 판정 허용오차 (m).
#:
#: 없으면 안 된다: 뷰 모서리의 점은 u = u_extent 로 **정확히** 떨어지지 않는다.
#: 예) 45° 회전 뷰에서 u_extent=10 인 모서리는 내적 결과가 10.000000000000002 가 되어
#: 엄격 비교로는 정의역 밖으로 판정된다. 시트 모서리·크롭 경계가 늘 이 경우다.
DEFAULT_EXTENT_EPSILON_M = 1e-9


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(a: Vec3) -> float:
    return math.sqrt(_dot(a, a))


@dataclass(frozen=True)
class AxisValidation:
    #: | |u_axis| − 1 |
    u_norm_error: float
    #: | |v_axis| − 1 |
    v_norm_error: float
    #: |u_axis · v_axis|
    orthogonality_error: float
    ok: bool


def validate_axes(vc: ViewContract, tolerance: float = DEFAULT_AXIS_TOLERANCE) -> AxisValidation:
    """R1·R2 의 성립 조건인 |u_axis| = |v_axis| = 1, u_axis ⟂ v_axis 를 검사한다."""
    u = vc.u_axis
    v = vc.v_axis
    u_err = abs(_norm(u) - 1.0)
    v_err = abs(_norm(v) - 1.0)
    ortho = abs(_dot(u, v))
    return AxisValidation(
        u_norm_error=u_err,
        v_norm_error=v_err,
        orthogonality_error=ortho,
        ok=u_err <= tolerance and v_err <= tolerance and ortho <= tolerance,
    )


def plane_normal(vc: ViewContract) -> Vec3:
    """뷰 평면의 법선 n = u_axis × v_axis. 축이 정규직교이면 단위벡터다."""
    return _cross(vc.u_axis, vc.v_axis)


def view_to_world(vc: ViewContract, u: float, v: float) -> Vec3:
    """정변환: 뷰 좌표 (u, v) → 3D 모델 좌표. 단위는 양쪽 모두 m."""
    o = vc.origin
    ua = vc.u_axis
    va = vc.v_axis
    return (
        o[0] + u * ua[0] + v * va[0],
        o[1] + u * ua[1] + v * va[1],
        o[2] + u * ua[2] + v * va[2],
    )


def view_to_world_with_offset(vc: ViewContract, u: float, v: float, off_plane: float) -> Vec3:
    """뷰 좌표 + 평면 이탈 거리 → 3D 모델 좌표 (R2 의 복원식)."""
    n = plane_normal(vc)
    b = view_to_world(vc, u, v)
    return (b[0] + off_plane * n[0], b[1] + off_plane * n[1], b[2] + off_plane * n[2])


@dataclass(frozen=True)
class ViewCoord:
    u: float
    v: float
    #: 평면에서 벗어난 부호 있는 거리 h = d·n. 평면 위의 점이면 0.
    off_plane: float
    #: u ∈ [0, u_extent] 이고 v ∈ [0, v_extent] 인가 (경계 허용오차 포함)
    in_extent: bool


def world_to_view(
    vc: ViewContract,
    p: Vec3,
    extent_epsilon_m: float = DEFAULT_EXTENT_EPSILON_M,
) -> ViewCoord:
    """역변환: 3D 모델 좌표 → 뷰 좌표. 평면 밖의 점은 off_plane 으로 그 사실을 알린다."""
    o = vc.origin
    d: Vec3 = (p[0] - o[0], p[1] - o[1], p[2] - o[2])
    u = _dot(d, vc.u_axis)
    v = _dot(d, vc.v_axis)
    n = plane_normal(vc)
    n_len = _norm(n)
    # 축이 평행하면 평면이 정의되지 않는다 — 거짓 0 대신 NaN 으로 드러낸다.
    off_plane = math.nan if n_len == 0 else _dot(d, n) / n_len
    e = extent_epsilon_m
    return ViewCoord(
        u=u,
        v=v,
        off_plane=off_plane,
        in_extent=(-e <= u <= vc.u_extent + e) and (-e <= v <= vc.v_extent + e),
    )


def view_to_pixel(vc: ViewContract, u: float, v: float) -> tuple[float, float] | None:
    """뷰 좌표 → 시트 이미지 픽셀 좌표. pixel_frame 이 없으면 None.

    뷰 직사각형은 이미지 **전체**가 아니라 view_bbox_px 영역에 대응한다
    (스캔 시트는 여백·표제란을 포함하므로 전체 대응 가정은 틀린다).
    """
    f = vc.pixel_frame
    if f is None:
        return None
    b = f.view_bbox_px
    sx = b.width / vc.u_extent
    sy = b.height / vc.v_extent
    px = b.x + u * sx
    py = b.y + ((vc.v_extent - v) * sy if f.v_down else v * sy)
    return (px, py)


def pixel_to_view(vc: ViewContract, px: float, py: float) -> tuple[float, float] | None:
    """시트 이미지 픽셀 좌표 → 뷰 좌표. pixel_frame 이 없으면 None."""
    f = vc.pixel_frame
    if f is None:
        return None
    b = f.view_bbox_px
    sx = b.width / vc.u_extent
    sy = b.height / vc.v_extent
    u = (px - b.x) / sx
    dy = (py - b.y) / sy
    v = (vc.v_extent - dy) if f.v_down else dy
    return (u, v)


def roundtrip_check(
    vc: ViewContract,
    *,
    grid: int = 3,
    tolerance_m: float = DEFAULT_ROUNDTRIP_TOLERANCE_M,
    axis_tolerance: float = DEFAULT_AXIS_TOLERANCE,
    off_plane_probe_m: float = 0.5,
) -> RoundtripCheck:
    """왕복 검산 R1·R2·R3 을 모두 재고 PASS/FAIL 을 낸다.

    축 검사(단위길이·직교)를 통과하지 못하면 오차와 무관하게 FAIL 이다 —
    비정규직교 축에서는 역변환 자체가 정의되지 않기 때문이다.
    """
    grid = max(2, grid)
    axes = validate_axes(vc, axis_tolerance)

    max_view_error = 0.0
    max_world_error = 0.0
    max_pixel_error: float | None = 0.0 if vc.pixel_frame is not None else None
    count = 0

    for i in range(grid):
        for j in range(grid):
            u = vc.u_extent * i / (grid - 1)
            v = vc.v_extent * j / (grid - 1)

            # R1 — (u,v) → 3D → (u,v)
            back = world_to_view(vc, view_to_world(vc, u, v))
            max_view_error = max(max_view_error, math.hypot(back.u - u, back.v - v))

            # R2 — 평면에서 off_plane_probe_m 만큼 떨어진 점을 3D → (u,v,h) → 3D 로 복원
            p = view_to_world_with_offset(vc, u, v, off_plane_probe_m)
            inv = world_to_view(vc, p)
            rebuilt = view_to_world_with_offset(vc, inv.u, inv.v, inv.off_plane)
            world_err = math.dist(rebuilt, p)
            max_world_error = max(max_world_error, math.inf if math.isnan(world_err) else world_err)

            # R3 — (u,v) → 픽셀 → (u,v)
            if max_pixel_error is not None:
                px = view_to_pixel(vc, u, v)
                pv = pixel_to_view(vc, px[0], px[1]) if px is not None else None
                if pv is not None:
                    max_pixel_error = max(max_pixel_error, math.hypot(pv[0] - u, pv[1] - v))

            count += 1

    passed = (
        axes.ok
        and max_view_error <= tolerance_m
        and max_world_error <= tolerance_m
        and (max_pixel_error is None or max_pixel_error <= tolerance_m)
    )
    result: PassFail = "PASS" if passed else "FAIL"

    return RoundtripCheck(
        sample_count=count,
        tolerance_m=tolerance_m,
        u_norm_error=axes.u_norm_error,
        v_norm_error=axes.v_norm_error,
        orthogonality_error=axes.orthogonality_error,
        max_view_roundtrip_error_m=max_view_error,
        max_world_roundtrip_error_m=max_world_error,
        max_pixel_roundtrip_error_m=max_pixel_error,
        result=result,
    )
