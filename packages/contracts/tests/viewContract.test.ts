import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { fixtureDir } from '../src/node.js';
import type { ViewContract } from '../src/types.js';
import {
  pixelToView,
  roundtripCheck,
  validateAxes,
  viewToPixel,
  viewToWorld,
  worldToView,
} from '../src/viewContract.js';

interface ViewCases {
  tolerance: number;
  cases: {
    name: string;
    contract: ViewContract;
    forward: { u: number; v: number; world: [number, number, number] }[];
    inverse: {
      world: [number, number, number];
      u: number;
      v: number;
      off_plane: number;
      in_extent: boolean;
    }[];
    pixel?: { u: number; v: number; px: number; py: number }[];
    axes_ok: boolean;
    roundtrip_result: 'PASS' | 'FAIL';
  }[];
}

const fixture = JSON.parse(
  readFileSync(join(fixtureDir(), 'view_contract.cases.json'), 'utf8'),
) as ViewCases;

describe('뷰 계약 수학 (규칙 §7)', () => {
  for (const c of fixture.cases) {
    describe(c.name, () => {
      it('축 검사 결과가 기대와 같다', () => {
        expect(validateAxes(c.contract).ok).toBe(c.axes_ok);
      });

      it('정변환 (u,v) → 3D', () => {
        for (const f of c.forward) {
          const got = viewToWorld(c.contract, f.u, f.v);
          for (let i = 0; i < 3; i++) {
            expect(got[i]).toBeCloseTo(f.world[i]!, 9);
          }
        }
      });

      it('역변환 3D → (u,v) 및 평면 이탈 거리', () => {
        for (const inv of c.inverse) {
          const got = worldToView(c.contract, inv.world);
          expect(got.u).toBeCloseTo(inv.u, 9);
          expect(got.v).toBeCloseTo(inv.v, 9);
          expect(got.offPlane).toBeCloseTo(inv.off_plane, 9);
          expect(got.inExtent).toBe(inv.in_extent);
        }
      });

      it('왕복 검산 판정이 기대와 같다', () => {
        expect(roundtripCheck(c.contract).result).toBe(c.roundtrip_result);
      });

      if (c.pixel) {
        it('픽셀 대응이 왕복한다', () => {
          for (const p of c.pixel!) {
            const px = viewToPixel(c.contract, p.u, p.v);
            expect(px).not.toBeNull();
            expect(px!.px).toBeCloseTo(p.px, 9);
            expect(px!.py).toBeCloseTo(p.py, 9);

            const back = pixelToView(c.contract, p.px, p.py);
            expect(back!.u).toBeCloseTo(p.u, 9);
            expect(back!.v).toBeCloseTo(p.v, 9);
          }
        });
      }
    });
  }

  it('pixel_frame 이 없으면 픽셀 변환은 null 을 준다', () => {
    const vc = fixture.cases[0]!.contract;
    expect(viewToPixel(vc, 1, 1)).toBeNull();
    expect(pixelToView(vc, 1, 1)).toBeNull();
  });
});

describe('extent 경계 판정', () => {
  const rot = fixture.cases.find((c) => c.name.includes('45'))!.contract;

  it('회전 축에서도 경계 위의 점을 안쪽으로 본다 (부동소수점 오차 흡수)', () => {
    const corner = viewToWorld(rot, rot.u_extent, rot.v_extent);
    expect(worldToView(rot, corner).inExtent).toBe(true);
  });

  it('허용오차를 넘어서면 바깥으로 본다', () => {
    const outside = viewToWorld(rot, rot.u_extent + 1e-3, 0);
    expect(worldToView(rot, outside).inExtent).toBe(false);
  });
});
