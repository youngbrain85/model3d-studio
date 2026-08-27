/**
 * 뷰 계약 수학 — 규칙 §7.
 *
 * 뷰는 3D 공간 안의 유한 직사각형 평면이다.
 *   n = u_axis × v_axis                                   (오른손 규칙, 좌표계 handedness=right 전제)
 *   정변환  W(u, v) = origin + u·u_axis + v·v_axis
 *   역변환  d = P − origin,  u = d·u_axis,  v = d·v_axis,  h = d·n
 *
 * 왕복 검산 조건 — 셋 다 성립해야 PASS:
 *   R1 시트 왕복  역변환(정변환(u,v)) = (u,v)
 *      ⇔ |u_axis| = 1, |v_axis| = 1, u_axis·v_axis = 0
 *      증명: u' = (u·u_axis + v·v_axis)·u_axis = u·|u_axis|² + v·(u_axis·v_axis).
 *            모든 u,v 에서 u' = u 이려면 |u_axis|² = 1 이고 u_axis·v_axis = 0. v 도 대칭.
 *   R2 모델 왕복  origin + u·u_axis + v·v_axis + h·n = P  (평면 밖 점까지 복원)
 *      ⇔ {u_axis, v_axis, n} 이 정규직교기저
 *   R3 픽셀 왕복  pixelToView(viewToPixel(u,v)) = (u,v)
 *
 * Python 쪽 대응: apps/worker/src/model3d_worker/contracts/view_contract.py
 * 두 구현은 packages/contracts/fixtures/view_contract.cases.json 으로 교차 검증된다.
 */
import type { RoundtripCheck, Vec3, ViewContract } from './types.js';

/** 축 단위길이·직교성 판정 허용오차 (무차원) */
export const DEFAULT_AXIS_TOLERANCE = 1e-9;

/** 왕복 검산 기본 허용오차 (m). 1 nm — 교량 규모(10²m)의 배정밀도 ULP(~10⁻¹⁴ m)보다 한참 크고 모델 정밀도보다 한참 작다. */
export const DEFAULT_ROUNDTRIP_TOLERANCE_M = 1e-9;

/**
 * 정의역 포함 판정 허용오차 (m).
 *
 * 없으면 안 된다: 뷰 모서리의 점은 u = u_extent 로 **정확히** 떨어지지 않는다.
 * 예) 45° 회전 뷰에서 u_extent=10 인 모서리는 내적 결과가 10.000000000000002 가 되어
 *     엄격 비교로는 정의역 밖으로 판정된다. 시트 모서리·크롭 경계가 늘 이 경우다.
 */
export const DEFAULT_EXTENT_EPSILON_M = 1e-9;

function dot(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}

function norm(a: Vec3): number {
  return Math.sqrt(dot(a, a));
}

export interface AxisValidation {
  /** | |u_axis| − 1 | */
  uNormError: number;
  /** | |v_axis| − 1 | */
  vNormError: number;
  /** |u_axis · v_axis| */
  orthogonalityError: number;
  ok: boolean;
}

/** R1·R2 의 성립 조건인 |u_axis| = |v_axis| = 1, u_axis ⟂ v_axis 를 검사한다. */
export function validateAxes(vc: ViewContract, tolerance = DEFAULT_AXIS_TOLERANCE): AxisValidation {
  const uNormError = Math.abs(norm(vc.u_axis) - 1);
  const vNormError = Math.abs(norm(vc.v_axis) - 1);
  const orthogonalityError = Math.abs(dot(vc.u_axis, vc.v_axis));
  return {
    uNormError,
    vNormError,
    orthogonalityError,
    ok: uNormError <= tolerance && vNormError <= tolerance && orthogonalityError <= tolerance,
  };
}

/** 뷰 평면의 법선 n = u_axis × v_axis. 축이 정규직교이면 단위벡터다. */
export function planeNormal(vc: ViewContract): Vec3 {
  return cross(vc.u_axis, vc.v_axis);
}

/** 정변환: 뷰 좌표 (u, v) → 3D 모델 좌표. 단위는 양쪽 모두 m. */
export function viewToWorld(vc: ViewContract, u: number, v: number): Vec3 {
  return [
    vc.origin[0] + u * vc.u_axis[0] + v * vc.v_axis[0],
    vc.origin[1] + u * vc.u_axis[1] + v * vc.v_axis[1],
    vc.origin[2] + u * vc.u_axis[2] + v * vc.v_axis[2],
  ];
}

/** 뷰 좌표 + 평면 이탈 거리 → 3D 모델 좌표 (R2 의 복원식). */
export function viewToWorldWithOffset(
  vc: ViewContract,
  u: number,
  v: number,
  offPlane: number,
): Vec3 {
  const n = planeNormal(vc);
  const base = viewToWorld(vc, u, v);
  return [base[0] + offPlane * n[0], base[1] + offPlane * n[1], base[2] + offPlane * n[2]];
}

export interface ViewCoord {
  u: number;
  v: number;
  /** 평면에서 벗어난 부호 있는 거리 h = d·n. 평면 위의 점이면 0. */
  offPlane: number;
  /** u ∈ [0, u_extent] 이고 v ∈ [0, v_extent] 인가 (경계 허용오차 포함) */
  inExtent: boolean;
}

/** 역변환: 3D 모델 좌표 → 뷰 좌표. 평면 밖의 점은 offPlane 으로 그 사실을 알린다. */
export function worldToView(
  vc: ViewContract,
  p: Vec3,
  extentEpsilonM = DEFAULT_EXTENT_EPSILON_M,
): ViewCoord {
  const d: Vec3 = [p[0] - vc.origin[0], p[1] - vc.origin[1], p[2] - vc.origin[2]];
  const u = dot(d, vc.u_axis);
  const v = dot(d, vc.v_axis);
  const n = planeNormal(vc);
  const nLen = norm(n);
  // 축이 평행하면 평면이 정의되지 않는다 — 거짓 0 대신 NaN 으로 드러낸다.
  const offPlane = nLen === 0 ? Number.NaN : dot(d, n) / nLen;
  return {
    u,
    v,
    offPlane,
    inExtent:
      u >= -extentEpsilonM &&
      u <= vc.u_extent + extentEpsilonM &&
      v >= -extentEpsilonM &&
      v <= vc.v_extent + extentEpsilonM,
  };
}

export interface PixelCoord {
  px: number;
  py: number;
}

/**
 * 뷰 좌표 → 시트 이미지 픽셀 좌표. pixel_frame 이 없으면 null.
 *
 * 뷰 직사각형은 이미지 **전체**가 아니라 view_bbox_px 영역에 대응한다
 * (스캔 시트는 여백·표제란을 포함하므로 전체 대응 가정은 틀린다).
 */
export function viewToPixel(vc: ViewContract, u: number, v: number): PixelCoord | null {
  const f = vc.pixel_frame;
  if (!f) return null;
  const b = f.view_bbox_px;
  const sx = b.width / vc.u_extent;
  const sy = b.height / vc.v_extent;
  const px = b.x + u * sx;
  const py = b.y + (f.v_down ? (vc.v_extent - v) * sy : v * sy);
  return { px, py };
}

/** 시트 이미지 픽셀 좌표 → 뷰 좌표. pixel_frame 이 없으면 null. */
export function pixelToView(
  vc: ViewContract,
  px: number,
  py: number,
): { u: number; v: number } | null {
  const f = vc.pixel_frame;
  if (!f) return null;
  const b = f.view_bbox_px;
  const sx = b.width / vc.u_extent;
  const sy = b.height / vc.v_extent;
  const u = (px - b.x) / sx;
  const dy = (py - b.y) / sy;
  const v = f.v_down ? vc.v_extent - dy : dy;
  return { u, v };
}

export interface RoundtripOptions {
  /** 한 변당 표본 수. 총 표본은 grid × grid 개. 최소 2 (총 4개). */
  grid?: number;
  toleranceM?: number;
  axisTolerance?: number;
  /** R2 표본이 평면에서 벗어나는 거리 (m). 평면 밖 복원까지 확인한다. */
  offPlaneProbeM?: number;
}

/**
 * 왕복 검산 R1·R2·R3 을 모두 재고 PASS/FAIL 을 낸다.
 * 축 검사(단위길이·직교)를 통과하지 못하면 오차와 무관하게 FAIL 이다 —
 * 비정규직교 축에서는 역변환 자체가 정의되지 않기 때문이다.
 */
export function roundtripCheck(vc: ViewContract, options: RoundtripOptions = {}): RoundtripCheck {
  const grid = Math.max(2, options.grid ?? 3);
  const toleranceM = options.toleranceM ?? DEFAULT_ROUNDTRIP_TOLERANCE_M;
  const offProbe = options.offPlaneProbeM ?? 0.5;
  const axes = validateAxes(vc, options.axisTolerance ?? DEFAULT_AXIS_TOLERANCE);

  let maxViewError = 0;
  let maxWorldError = 0;
  let maxPixelError: number | null = vc.pixel_frame ? 0 : null;
  let count = 0;

  for (let i = 0; i < grid; i++) {
    for (let j = 0; j < grid; j++) {
      const u = (vc.u_extent * i) / (grid - 1);
      const v = (vc.v_extent * j) / (grid - 1);

      // R1 — (u,v) → 3D → (u,v)
      const back = worldToView(vc, viewToWorld(vc, u, v));
      maxViewError = Math.max(maxViewError, Math.hypot(back.u - u, back.v - v));

      // R2 — 평면에서 offProbe 만큼 떨어진 점을 3D → (u,v,h) → 3D 로 복원
      const p = viewToWorldWithOffset(vc, u, v, offProbe);
      const inv = worldToView(vc, p);
      const rebuilt = viewToWorldWithOffset(vc, inv.u, inv.v, inv.offPlane);
      const worldErr = Math.hypot(rebuilt[0] - p[0], rebuilt[1] - p[1], rebuilt[2] - p[2]);
      maxWorldError = Math.max(maxWorldError, Number.isNaN(worldErr) ? Infinity : worldErr);

      // R3 — (u,v) → 픽셀 → (u,v)
      if (maxPixelError !== null) {
        const px = viewToPixel(vc, u, v);
        const pv = px ? pixelToView(vc, px.px, px.py) : null;
        if (pv) maxPixelError = Math.max(maxPixelError, Math.hypot(pv.u - u, pv.v - v));
      }

      count++;
    }
  }

  const pass =
    axes.ok &&
    maxViewError <= toleranceM &&
    maxWorldError <= toleranceM &&
    (maxPixelError === null || maxPixelError <= toleranceM);

  return {
    sample_count: count,
    tolerance_m: toleranceM,
    u_norm_error: axes.uNormError,
    v_norm_error: axes.vNormError,
    orthogonality_error: axes.orthogonalityError,
    max_view_roundtrip_error_m: maxViewError,
    max_world_roundtrip_error_m: maxWorldError,
    max_pixel_roundtrip_error_m: maxPixelError,
    result: pass ? 'PASS' : 'FAIL',
  };
}
