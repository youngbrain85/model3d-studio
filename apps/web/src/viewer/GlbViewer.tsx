import { useEffect, useRef, useState } from 'react';
import {
  AmbientLight,
  Box3,
  DirectionalLight,
  OrthographicCamera,
  Scene,
  Vector3,
  WebGLRenderer,
} from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import type { ViewContract } from '@model3d/contracts';
import { cameraFromViewContract } from './camera.js';
import { buildMemberIndex, type MemberIndex } from './memberIndex.js';

export interface GlbViewerProps {
  /** GLB 파일 URL. 없으면 빈 씬을 띄운다. */
  url?: string;
  /** 있으면 이 뷰 계약대로 실척 정사영 카메라를 건다 (규칙 §6·§7). */
  viewContract?: ViewContract;
  onMemberIndex?: (index: MemberIndex) => void;
}

/**
 * three.js 를 직접 다루는 얇은 React 래퍼.
 *
 * R3F 를 쓰지 않는 이유는 docs/M0_부트스트랩.md 「기술 선택」에 적어 두었다 —
 * 요약하면 정사영 카메라·뷰 계약 수학·GLB 노드 트리 순회가 전부 명령형이고,
 * R3F 9 는 react 를 `<19.3` 으로 고정한다.
 */
export function GlbViewer({ url, viewContract, onMemberIndex }: GlbViewerProps): React.JSX.Element {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let disposed = false;
    const scene = new Scene();
    scene.add(new AmbientLight(0xffffff, 0.8));
    const key = new DirectionalLight(0xffffff, 1.2);
    key.position.set(1, 2, 3);
    scene.add(key);

    const renderer = new WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    host.appendChild(renderer.domElement);

    // 뷰 계약이 없으면 임시 카메라로 시작하고, GLB 를 읽은 뒤 바운딩 박스로 맞춘다.
    let camera = viewContract
      ? cameraFromViewContract(viewContract)
      : new OrthographicCamera(-1, 1, 1, -1, 0.01, 1000);

    const resize = (): void => {
      const { clientWidth: w, clientHeight: h } = host;
      if (w === 0 || h === 0) return;
      renderer.setSize(w, h, false);
      // 실척을 유지하려면 가로세로비는 카메라 프러스텀으로 흡수한다.
      const aspect = w / h;
      const halfV = (camera.top - camera.bottom) / 2;
      const halfU = halfV * aspect;
      camera.left = -halfU;
      camera.right = halfU;
      camera.updateProjectionMatrix();
      renderer.render(scene, camera);
    };

    const observer = new ResizeObserver(resize);
    observer.observe(host);

    if (url) {
      new GLTFLoader().load(
        url,
        (gltf) => {
          if (disposed) return;
          scene.add(gltf.scene);
          onMemberIndex?.(buildMemberIndex(gltf.scene, ['Scene', 'RootNode']));
          if (!viewContract) {
            const box = new Box3().setFromObject(gltf.scene);
            const size = box.getSize(new Vector3());
            const center = box.getCenter(new Vector3());
            const half = Math.max(size.x, size.y, 1) / 2;
            camera = new OrthographicCamera(-half, half, half, -half, 0.01, size.length() * 4 + 10);
            camera.position.set(center.x, center.y, center.z + size.length() + 1);
            camera.lookAt(center);
          }
          resize();
        },
        undefined,
        (err: unknown) => {
          if (!disposed) setError(err instanceof Error ? err.message : 'GLB 로드 실패');
        },
      );
    } else {
      resize();
    }

    return () => {
      disposed = true;
      observer.disconnect();
      renderer.dispose();
      host.removeChild(renderer.domElement);
    };
  }, [url, viewContract, onMemberIndex]);

  return (
    <div className="viewer">
      <div ref={hostRef} className="viewer__canvas" />
      {error ? <p className="viewer__error">{error}</p> : null}
    </div>
  );
}
