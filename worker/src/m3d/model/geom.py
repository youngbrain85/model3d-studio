"""메시 유틸 — 귀자르기 삼각화 + z-로프트 (참조 v2 빌더 §"메시 유틸" 포팅, 상수 의존 제거).

빌더(builder.py)는 이 함수들로 판·프리즘·로프트 솔리드를 만든다. 스테이션·존 분할이 필요한
전이점(BREAKS)·검산점(CHECKS)·포물선 구간(PARA)은 인자로 받는다 — 모듈 상수를 두지 않는다.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

Poly = list[tuple[float, float]]


def ear_clip(poly: Poly) -> list[tuple[int, int, int]]:
    """단순 다각형(CCW) 귀자르기 삼각화 → 정점 인덱스 삼각형 목록."""
    n = len(poly)
    idx = list(range(n))
    tris: list[tuple[int, int, int]] = []
    guard = 0
    while len(idx) > 3 and guard < 20000:
        guard += 1
        clipped = False
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            ax, ay = poly[i0]
            bx, by = poly[i1]
            cx, cy = poly[i2]
            cr = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
            if cr <= 1e-12:
                continue
            ear = True
            for j in idx:
                if j in (i0, i1, i2):
                    continue
                px, py = poly[j]
                d0 = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
                d1 = (cx - bx) * (py - by) - (cy - by) * (px - bx)
                d2 = (ax - cx) * (py - cy) - (ay - cy) * (px - cx)
                if d0 >= -1e-12 and d1 >= -1e-12 and d2 >= -1e-12:
                    ear = False
                    break
            if ear:
                tris.append((i0, i1, i2))
                idx.pop(k)
                clipped = True
                break
        if not clipped:
            break
    if len(idx) == 3:
        tris.append((idx[0], idx[1], idx[2]))
    return tris


def signed_area(poly: Poly) -> float:
    """폴리곤 부호 면적 — 양수면 CCW."""
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                     for i in range(len(poly)))


def normalize_poly(poly: Poly) -> Poly:
    """끝에 되풀이된 첫 점을 떼고 CCW 로 맞춘다.

    ear_clip 은 CCW 를 전제하므로 CW 입력은 캡이 뒤집혀 조용히 수밀이 깨졌다(M7 SLAB 3회 실패).
    올바른 입력에는 아무 영향이 없다(CCW 폴리곤을 CCW 로 두고, 중복 끝점이 없으면 그대로).
    """
    p = list(poly)
    while len(p) > 3 and abs(p[0][0] - p[-1][0]) < 1e-12 and abs(p[0][1] - p[-1][1]) < 1e-12:
        p.pop()
    return p if signed_area(p) >= 0 else list(reversed(p))


def loft(stations: list[tuple[float, Poly]]) -> trimesh.Trimesh:
    """stations = [(z, [(x,y),...]), ...] (동일 꼭짓점 수) → 닫힌 솔리드. 폴리곤 방향·중복 끝점은 알아서 맞춘다."""
    stations = [(z, normalize_poly(poly)) for z, poly in stations]
    ns = len(stations)
    n = len(stations[0][1])
    verts = []
    for z, poly in stations:
        assert len(poly) == n, "스테이션 꼭짓점 수 불일치"
        for x, y in poly:
            verts.append((x, y, z))
    faces = []
    for i in range(ns - 1):
        a, b = i * n, (i + 1) * n
        for j in range(n):
            j2 = (j + 1) % n
            faces.append((a + j, b + j2, b + j))
            faces.append((a + j, a + j2, b + j2))
    for (i0, i1, i2) in ear_clip(stations[0][1]):
        faces.append((i2, i1, i0))
    off = (ns - 1) * n
    for (i0, i1, i2) in ear_clip(stations[-1][1]):
        faces.append((off + i0, off + i1, off + i2))
    return trimesh.Trimesh(vertices=np.array(verts, dtype=np.float64),
                           faces=np.array(faces, dtype=np.int64), process=False)


def extrude(poly: Poly, z0: float, z1: float) -> trimesh.Trimesh:
    return loft([(z0, poly), (z1, poly)])


def rect(x0: float, x1: float, y0: float, y1: float) -> Poly:
    """CCW 사각 폴리곤."""
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def box_prism(x0, x1, y0, y1, z0, z1) -> trimesh.Trimesh:
    return extrude(rect(x0, x1, y0, y1), z0, z1)


def mirror_poly(poly: Poly) -> Poly:
    return [(-x, y) for (x, y) in reversed(poly)]


def mirror_mesh(m: trimesh.Trimesh) -> trimesh.Trimesh:
    """x 반전 — trimesh 는 반사 변환 시 와인딩을 자동 보정한다(참조 v1 검증)."""
    mm = m.copy()
    mm.apply_transform(np.diag([-1.0, 1.0, 1.0, 1.0]))
    return mm


def paint(mesh: trimesh.Trimesh, color) -> trimesh.Trimesh:
    """KB §2-14: 전 메시 버텍스 컬러."""
    mesh.visual.face_colors = color
    return mesh


def stations(z0: float, z1: float, *, para_ranges: list[tuple[float, float]],
             checks: list[float], step: float = 0.7) -> list[float]:
    """로프트 z 스테이션: 양끝 + 포물선 구간 세분(step) + 검산점(구간 내)."""
    zs = {z0, z1}
    for (a, b) in para_ranges:
        lo, hi = max(a, z0), min(b, z1)
        if lo < hi:
            n = max(2, int(math.ceil((hi - lo) / step)))
            for i in range(n + 1):
                zs.add(lo + (hi - lo) * i / n)
    for zc in checks:
        if z0 - 1e-9 <= zc <= z1 + 1e-9:
            zs.add(min(max(zc, z0), z1))
    return sorted(zs)


def zone_split(z0: float, z1: float, breaks: list[float]) -> list[tuple[float, float]]:
    """[z0,z1] 을 전이점(breaks)에서 분할 → 연속 구간 목록."""
    cuts = [z0] + [zb for zb in breaks if z0 + 1e-9 < zb < z1 - 1e-9] + [z1]
    return list(zip(cuts[:-1], cuts[1:]))


def zone_loft(z0: float, z1: float, poly_fn, *, breaks: list[float],
              para_ranges: list[tuple[float, float]], checks: list[float]) -> trimesh.Trimesh:
    """판두께 전이점 분할 로프트 — 전이점 계단면은 구간 캡으로 표현 [A1]."""
    parts = []
    for (a, b) in zone_split(z0, z1, breaks):
        eps = min(1e-6, (b - a) * 1e-3)
        parts.append(loft([(z, poly_fn(min(max(z, a + eps), b - eps)))
                           for z in stations(a, b, para_ranges=para_ranges, checks=checks)]))
    return trimesh.util.concatenate(parts)
