import { describe, expect, it } from 'vitest';
import { clipPlane, distanceFromZ, presetCamera, zFromDistance } from './math';

const BOX = { min: [-7.85, 15.1, -525.7] as [number, number, number], max: [7.85, 21.9, -454.3] as [number, number, number] };

describe('z ↔ 받침선 거리', () => {
  it('왕복', () => {
    expect(zFromDistance(-525, 10)).toBe(-515);
    expect(distanceFromZ(-525, -490)).toBe(35);
  });
});

describe('clipPlane', () => {
  // three.js: normal·p + constant < 0 인 조각은 잘린다
  const vis = (pl: { normal: number[]; constant: number }, p: number[]) =>
    pl.normal[0] * p[0] + pl.normal[1] * p[1] + pl.normal[2] * p[2] + pl.constant >= 0;
  it("z 'below' 는 값보다 작은 z 만 남긴다", () => {
    const pl = clipPlane('z', -500, 'below');
    expect(vis(pl, [0, 0, -510])).toBe(true);
    expect(vis(pl, [0, 0, -490])).toBe(false);
  });
  it("x 'above' 는 값보다 큰 x 만 남긴다", () => {
    const pl = clipPlane('x', 0, 'above');
    expect(vis(pl, [1, 0, 0])).toBe(true);
    expect(vis(pl, [-1, 0, 0])).toBe(false);
  });
});

describe('presetCamera', () => {
  it('측면은 +x 에서 중심을 보고, 아이소는 위·앞·옆 모두 양의 오프셋, 저면은 아래', () => {
    const c = [0, 18.5, -490];
    const side = presetCamera('side', BOX);
    expect(side.target).toEqual(c);
    expect(side.position[0]).toBeGreaterThan(BOX.max[0]);
    expect(side.position[1]).toBeCloseTo(c[1]);
    const iso = presetCamera('iso', BOX);
    expect(iso.position[0] > c[0] && iso.position[1] > c[1] && iso.position[2] > c[2]).toBe(true);
    const bottom = presetCamera('bottom', BOX);
    expect(bottom.position[1]).toBeLessThan(BOX.min[1]);
  });
});
