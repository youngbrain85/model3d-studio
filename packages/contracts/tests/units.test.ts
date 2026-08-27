import { describe, expect, it } from 'vitest';
import { MM_PER_MODEL_UNIT, mmToModel, mmToModelVec3, modelToMm } from '../src/units.js';

describe('단위 변환 (규칙 §1 — 변환은 한 곳에서만)', () => {
  it('mm ↔ m 이 서로의 역이다', () => {
    for (const mm of [0, 1, 2500, 32500, -1200.5]) {
      expect(modelToMm(mmToModel(mm))).toBeCloseTo(mm, 9);
    }
  });

  it('상수는 1000 이다', () => {
    expect(MM_PER_MODEL_UNIT).toBe(1000);
    expect(mmToModel(32500)).toBeCloseTo(32.5, 12);
    expect(modelToMm(32.5)).toBeCloseTo(32500, 9);
  });

  it('3성분 변환', () => {
    expect(mmToModelVec3([1000, 2500, -500])).toEqual([1, 2.5, -0.5]);
  });
});
