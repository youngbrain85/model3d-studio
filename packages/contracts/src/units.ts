/**
 * 단위 변환 — 규칙 §1: "도면 치수는 mm 정본, 모델은 m — 변환은 한 곳(빌더 상수)에서만."
 *
 * 이 모듈이 그 "한 곳"이다. 다른 어디에서도 1000 을 곱하거나 나누지 않는다.
 * Python 쪽 대응: apps/worker/src/model3d_worker/contracts/units.py
 */

/** 모델 1 단위(m) 당 도면 단위(mm) 수. 이 상수는 이 파일에만 존재한다. */
export const MM_PER_MODEL_UNIT = 1000;

/** 도면 mm → 모델 m */
export function mmToModel(mm: number): number {
  return mm / MM_PER_MODEL_UNIT;
}

/** 모델 m → 도면 mm */
export function modelToMm(m: number): number {
  return m * MM_PER_MODEL_UNIT;
}

/** 도면 mm 3성분 → 모델 m 3성분 */
export function mmToModelVec3(mm: readonly [number, number, number]): [number, number, number] {
  return [mmToModel(mm[0]), mmToModel(mm[1]), mmToModel(mm[2])];
}
