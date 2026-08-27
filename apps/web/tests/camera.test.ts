import { describe, expect, it } from 'vitest';
import { Vector3 } from 'three';
import type { ViewContract } from '@model3d/contracts';
import { cameraFromViewContract, orthoParamsFromViewContract } from '../src/viewer/camera.js';

const vc: ViewContract = {
  id: 'vc-1',
  name: 'AB1 측면도',
  origin: [10, 0, 5],
  u_axis: [0, 0, 1],
  v_axis: [0, 1, 0],
  u_extent: 30,
  v_extent: 8,
  unit: 'm',
};

describe('뷰 계약 → 정사영 카메라 (규칙 §6·§7)', () => {
  it('프러스텀이 뷰 사각형을 실척으로 담는다 (여백 제외)', () => {
    const p = orthoParamsFromViewContract(vc, { padding: 0 });
    expect(p.right - p.left).toBeCloseTo(vc.u_extent, 9);
    expect(p.top - p.bottom).toBeCloseTo(vc.v_extent, 9);
  });

  it('여백 비율이 프러스텀에 반영된다', () => {
    const p = orthoParamsFromViewContract(vc, { padding: 0.1 });
    expect(p.right - p.left).toBeCloseTo(vc.u_extent * 1.1, 9);
    expect(p.top - p.bottom).toBeCloseTo(vc.v_extent * 1.1, 9);
  });

  it('카메라가 뷰 사각형의 중심을 본다', () => {
    const p = orthoParamsFromViewContract(vc);
    // 중심 = origin + u_extent/2·u + v_extent/2·v = [10, 4, 20]
    expect(p.lookAt.toArray()).toEqual([10, 4, 20]);
  });

  it('시선이 뷰 평면의 법선과 평행하다', () => {
    const p = orthoParamsFromViewContract(vc);
    const dir = p.lookAt.clone().sub(p.position).normalize();
    const normal = new Vector3(...vc.u_axis).cross(new Vector3(...vc.v_axis)).normalize();
    // 카메라는 법선 방향으로 물러나 있으므로 시선은 −법선
    expect(dir.dot(normal)).toBeCloseTo(-1, 9);
  });

  it('up 벡터가 v_axis 다 — 시트의 위가 화면의 위', () => {
    const p = orthoParamsFromViewContract(vc);
    expect(p.up.toArray()).toEqual(vc.v_axis);
  });

  it('뷰 사각형이 near/far 사이에 온전히 들어간다', () => {
    const p = orthoParamsFromViewContract(vc);
    const dist = p.position.distanceTo(p.lookAt);
    expect(dist).toBeGreaterThan(p.near);
    expect(dist).toBeLessThan(p.far);
  });

  it('실제 three.js 정사영 카메라를 만든다', () => {
    const cam = cameraFromViewContract(vc, { padding: 0 });
    expect(cam.isOrthographicCamera).toBe(true);
    expect(cam.right - cam.left).toBeCloseTo(vc.u_extent, 9);
  });

  it('축이 정규직교가 아니면 던진다 — 잘못된 뷰로 검수 렌더를 만들지 않는다', () => {
    // u_axis 가 [0,0,1] 이므로, 비직교를 만들려면 v 에 z 성분이 있어야 한다.
    const bad: ViewContract = { ...vc, v_axis: [0, 0.7071067811865476, 0.7071067811865476] };
    expect(() => orthoParamsFromViewContract(bad)).toThrow(/정규직교/);
    const nonUnit: ViewContract = { ...vc, u_axis: [0, 0, 2] };
    expect(() => orthoParamsFromViewContract(nonUnit)).toThrow(/정규직교/);
  });
});
