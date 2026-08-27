/**
 * 뷰 계약 → three.js 정사영 카메라.
 *
 * 규칙 §7 — 뷰 계약(origin + u·extent + u_axis + v·extent + v_axis)이 있으면
 * 시트·웹뷰어와 좌표가 호환된다. 이 모듈이 그 대응을 만든다.
 * 규칙 §6 — 검수 렌더는 **실척 정사영**이어야 하므로 원근 카메라를 쓰지 않는다.
 *
 * WebGL 없이 계산만 하므로 headless 로 단위 테스트할 수 있다.
 */
import { OrthographicCamera, Vector3 } from 'three';
import type { ViewContract } from '@model3d/contracts';
import { validateAxes } from '@model3d/contracts';

export interface OrthoCameraParams {
  position: Vector3;
  lookAt: Vector3;
  up: Vector3;
  left: number;
  right: number;
  top: number;
  bottom: number;
  near: number;
  far: number;
}

export interface CameraOptions {
  /** 뷰 평면에서 카메라를 얼마나 띄울지 (모델 단위 m). 정사영이라 배율에는 영향 없음. */
  standoff?: number;
  /** 화면 여백 비율 (0.05 = 5%) */
  padding?: number;
}

/**
 * 뷰 계약이 정의하는 사각형을 화면에 실척으로 담는 정사영 카메라 파라미터를 만든다.
 * 축이 정규직교가 아니면 던진다 — 잘못된 뷰로 검수 렌더를 만들면 안 된다.
 */
export function orthoParamsFromViewContract(
  vc: ViewContract,
  options: CameraOptions = {},
): OrthoCameraParams {
  const axes = validateAxes(vc, 1e-6);
  if (!axes.ok) {
    throw new Error(
      `뷰 계약의 축이 정규직교가 아닙니다 (|u|-1=${axes.uNormError}, |v|-1=${axes.vNormError}, ` +
        `u·v=${axes.orthogonalityError}) — 규칙 §7 왕복 검산을 통과하지 못한 뷰입니다.`,
    );
  }

  const standoff = options.standoff ?? Math.max(vc.u_extent, vc.v_extent) * 2 + 1;
  const padding = options.padding ?? 0.05;

  const u = new Vector3(...vc.u_axis);
  const v = new Vector3(...vc.v_axis);
  const origin = new Vector3(...vc.origin);
  const normal = new Vector3().crossVectors(u, v).normalize();

  // 뷰 사각형의 중심
  const center = origin
    .clone()
    .addScaledVector(u, vc.u_extent / 2)
    .addScaledVector(v, vc.v_extent / 2);

  const halfU = (vc.u_extent / 2) * (1 + padding);
  const halfV = (vc.v_extent / 2) * (1 + padding);

  return {
    position: center.clone().addScaledVector(normal, standoff),
    lookAt: center,
    up: v.clone(),
    left: -halfU,
    right: halfU,
    top: halfV,
    bottom: -halfV,
    near: 0.01,
    far: standoff * 2 + Math.max(vc.u_extent, vc.v_extent),
  };
}

/** 위 파라미터로 실제 three.js 카메라를 만든다. */
export function cameraFromViewContract(
  vc: ViewContract,
  options: CameraOptions = {},
): OrthographicCamera {
  const p = orthoParamsFromViewContract(vc, options);
  const cam = new OrthographicCamera(p.left, p.right, p.top, p.bottom, p.near, p.far);
  cam.position.copy(p.position);
  cam.up.copy(p.up);
  cam.lookAt(p.lookAt);
  cam.updateProjectionMatrix();
  cam.updateMatrixWorld(true);
  return cam;
}
