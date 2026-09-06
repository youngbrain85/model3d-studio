// three.js 뷰어 — React 무관. 섹션 GLB 를 각각 로드해 한 씬에 얹는다(레고식 결합, 좌표 변환 없음).
// 버텍스 컬러 유지·양면·클리핑 평면. 피킹은 Raycaster(30k 삼각형이라 BVH 불요). (M4 설계서 §6, D8)
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

import { clipPlane, presetCamera, type Axis, type Keep, type Preset, type Vec3 } from './math';

export interface PickInfo { node: string; section: string; point: Vec3 }
export interface Viewer {
  loadSection(key: string, url: string): Promise<{ meshes: number }>;
  setVisible(key: string, on: boolean): void;
  solo(key: string | null): void;
  setClip(axis: Axis, opts: { enabled: boolean; value: number; keep: Keep }): void;
  preset(p: Preset): void;
  highlight(node: string | null): void;
  onPick(cb: (info: PickInfo | null) => void): void;
  bounds(): { min: Vec3; max: Vec3 } | null;
  dispose(): void;
}

export function createViewer(canvas: HTMLCanvasElement): Viewer {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.localClippingEnabled = true;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xf4f4f2);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8c8c86, 1.1));
  const sun = new THREE.DirectionalLight(0xffffff, 1.4);
  sun.position.set(30, 60, 40);
  scene.add(sun);
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
  const controls = new OrbitControls(camera, canvas);
  let dirty = true;
  controls.addEventListener('change', () => { dirty = true; });

  const sections = new Map<string, THREE.Group>();
  const visible = new Map<string, boolean>();
  let soloKey: string | null = null;
  const planes: Record<Axis, THREE.Plane | null> = { x: null, z: null };
  const materials: THREE.MeshStandardMaterial[] = [];
  let highlighted: THREE.Mesh | null = null;
  let pickCb: ((info: PickInfo | null) => void) | null = null;
  let disposed = false;

  const loader = new GLTFLoader();

  function activePlanes(): THREE.Plane[] {
    return [planes.x, planes.z].filter((p): p is THREE.Plane => p !== null);
  }
  function applyVisibility() {
    for (const [key, g] of sections) g.visible = soloKey ? key === soloKey : (visible.get(key) ?? true);
    dirty = true;
  }
  function applyPlanes() {
    const ps = activePlanes();
    for (const m of materials) { m.clippingPlanes = ps; m.needsUpdate = true; }
    dirty = true;
  }
  function bounds(): { min: Vec3; max: Vec3 } | null {
    const box = new THREE.Box3();
    let any = false;
    for (const g of sections.values()) { box.expandByObject(g); any = true; }
    return any ? { min: box.min.toArray() as Vec3, max: box.max.toArray() as Vec3 } : null;
  }
  function fit(p: Preset) {
    const b = bounds();
    if (!b) return;
    const { position, target } = presetCamera(p, b);
    camera.position.set(...position);
    controls.target.set(...target);
    camera.updateProjectionMatrix();
    controls.update();
    dirty = true;
  }
  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (w === 0 || h === 0) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    dirty = true;
  }
  const ro = new ResizeObserver(resize);
  ro.observe(canvas);
  resize();

  function frame() {
    if (disposed) return;
    requestAnimationFrame(frame);
    if (!dirty) return;
    dirty = false;
    renderer.render(scene, camera);
  }
  frame();

  // 피킹 — 드래그(회전)와 구분: pointerdown/up 거리 4px 이내만 클릭
  const ray = new THREE.Raycaster();
  let down: [number, number] | null = null;
  canvas.addEventListener('pointerdown', (e) => { down = [e.clientX, e.clientY]; });
  canvas.addEventListener('pointerup', (e) => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;
    const r = canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const targets: THREE.Object3D[] = [];
    for (const g of sections.values()) if (g.visible) targets.push(g);
    const ps = activePlanes();
    const hit = ray.intersectObjects(targets, true).find((h) => ps.every((pl) => pl.distanceToPoint(h.point) >= 0)); // 잘린 면 제외
    const mesh = hit?.object as THREE.Mesh | undefined;
    pickCb?.(mesh && hit
      ? { node: mesh.userData.node as string, section: mesh.userData.section as string, point: hit.point.toArray() as Vec3 }
      : null);
  });

  return {
    async loadSection(key, url) {
      const gltf = await loader.loadAsync(url);
      let n = 0;
      gltf.scene.traverse((o) => {
        const mesh = o as THREE.Mesh;
        if (!mesh.isMesh) return;
        n += 1;
        // GLTFLoader 는 기본 재질을 공유하므로 메시마다 새 재질(하이라이트·클리핑 개별 적용)
        const mat = new THREE.MeshStandardMaterial({ vertexColors: true, side: THREE.DoubleSide, metalness: 0.05, roughness: 0.85 });
        mat.clippingPlanes = activePlanes();
        mesh.material = mat;
        materials.push(mat);
        mesh.userData.node = mesh.name;
        mesh.userData.section = key;
      });
      const group = new THREE.Group();
      group.name = key;
      group.add(gltf.scene);
      const first = sections.size === 0;
      sections.set(key, group);
      if (!visible.has(key)) visible.set(key, true);
      scene.add(group);
      applyVisibility();
      if (first) fit('iso');
      return { meshes: n };
    },
    setVisible(key, on) { visible.set(key, on); applyVisibility(); },
    solo(key) { soloKey = key; applyVisibility(); },
    setClip(axis, { enabled, value, keep }) {
      if (!enabled) planes[axis] = null;
      else {
        const p = clipPlane(axis, value, keep);
        planes[axis] = new THREE.Plane(new THREE.Vector3(...p.normal), p.constant);
      }
      applyPlanes();
    },
    preset(p) { fit(p); },
    highlight(node) {
      if (highlighted) { (highlighted.material as THREE.MeshStandardMaterial).emissive.setHex(0x000000); highlighted = null; }
      if (node) {
        const found: THREE.Mesh[] = [];
        for (const g of sections.values()) {
          g.traverse((o) => { if ((o as THREE.Mesh).isMesh && o.name === node) found.push(o as THREE.Mesh); });
        }
        highlighted = found[0] ?? null;
        if (highlighted) (highlighted.material as THREE.MeshStandardMaterial).emissive.setHex(0x3355ff);
      }
      dirty = true;
    },
    onPick(cb) { pickCb = cb; },
    bounds,
    dispose() {
      disposed = true;
      ro.disconnect();
      controls.dispose();
      for (const m of materials) m.dispose();
      scene.traverse((o) => { (o as THREE.Mesh).geometry?.dispose?.(); });
      renderer.dispose();
    },
  };
}
