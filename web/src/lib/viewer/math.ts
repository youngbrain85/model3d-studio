// 뷰어 순수 계산 — three 에 의존하지 않아 vitest(node)에서 검증한다.
export type Axis = 'x' | 'z';
export type Keep = 'below' | 'above';
export type Preset = 'side' | 'front' | 'bottom' | 'iso';
export type Vec3 = [number, number, number];
export interface Box { min: Vec3; max: Vec3 }

/** 받침선(P4) 기준 거리 d(m) ↔ 월드 z */
export function zFromDistance(zP4: number, d: number): number { return zP4 + d; }
export function distanceFromZ(zP4: number, z: number): number { return z - zP4; }

/** three.Plane(normal, constant): normal·p + constant < 0 이면 잘린다. below = 값보다 작은 좌표만 남김. */
export function clipPlane(axis: Axis, value: number, keep: Keep): { normal: Vec3; constant: number } {
  const n: Vec3 = axis === 'x' ? [1, 0, 0] : [0, 0, 1];
  const s = keep === 'below' ? -1 : 1;
  return { normal: [n[0] * s, n[1] * s, n[2] * s], constant: -s * value };
}

const FOV_DEG = 45;

/** 프리셋 카메라 — bbox 중심을 보며 전체가 화면에 들어오는 거리. side=+x, front=+z, bottom=아래·앞·옆, iso=위·앞·옆 */
export function presetCamera(preset: Preset, box: Box): { position: Vec3; target: Vec3 } {
  const c: Vec3 = [(box.min[0] + box.max[0]) / 2, (box.min[1] + box.max[1]) / 2, (box.min[2] + box.max[2]) / 2];
  const size = Math.max(box.max[0] - box.min[0], box.max[1] - box.min[1], box.max[2] - box.min[2]);
  const dist = (size / 2) / Math.tan((FOV_DEG * Math.PI) / 360) * 1.15;
  const dir: Record<Preset, Vec3> = {
    side: [1, 0, 0], front: [0, 0, 1], bottom: [0.35, -1, 0.25], iso: [0.6, 0.45, 0.65],
  };
  const d = dir[preset];
  const len = Math.hypot(d[0], d[1], d[2]);
  return { position: [c[0] + (d[0] / len) * dist, c[1] + (d[1] / len) * dist, c[2] + (d[2] / len) * dist], target: c };
}
