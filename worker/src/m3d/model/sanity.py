"""기하 건전성 (M8 D3) — 스펙 해석 없이 큰 사고만 잡는다.

정답 빌더가 없는 교량에서도 쓰는 첫 관문이다. bbox 연산만 쓴다(메시 불리언은 느리다).
1) 외곽 이탈 — 노드가 교량 외곽 밖에 있다.  2) 부유 부재 — 어떤 부재와도 닿지 않는다.
3) 중복 배치 — 두 부재가 같은 자리를 절반 넘게 차지한다(한쪽이 다른 쪽을 감싸는 관계는 뺀다).
"""

from __future__ import annotations

import numpy as np
import trimesh

from m3d.model.spec import ModelSpec

MARGIN = 0.5          # 외곽 여유(m)
TOUCH = 0.05          # 이 거리 안에서 만나면 닿은 것으로 본다(m)
SAME_BOX = 0.02       # 두 노드의 bbox 모서리가 모두 이 거리 안이면 같은 자리에 겹쳐 놓은 것으로 본다(m)


def envelope(spec: ModelSpec) -> tuple[np.ndarray, np.ndarray]:
    """스펙에서 유도한 교량 외곽 — 여유 MARGIN."""
    c, sl, br = spec.coord, spec.slab, spec.bearing
    y_low = min(br.el_check.values()) - c.y_datum - br.mortar[0] - br.block[1]
    y_high = c.el0 + c.grade * (max(c.z_p4, c.z_p5) - c.z_sta3400) - c.y_datum + sl.barrier[1]
    z_out = max(br.sole[0], br.block[0]) / 2.0 + MARGIN      # 받침 부품이 받침선 밖으로 반 변만큼 나간다
    lo = np.array([-sl.half_width - MARGIN, y_low - MARGIN, min(c.z_p4, c.z_p5) - z_out])
    hi = np.array([sl.half_width + MARGIN, y_high + MARGIN, max(c.z_p4, c.z_p5) + z_out])
    return lo, hi


def _bounds(named: dict[str, trimesh.Trimesh]) -> dict[str, np.ndarray]:
    return {n: np.asarray(m.bounds, dtype=float) for n, m in named.items()}


def _overlap_volume(a: np.ndarray, b: np.ndarray) -> float:
    d = np.minimum(a[1], b[1]) - np.maximum(a[0], b[0])
    return float(np.prod(d)) if np.all(d > 0) else 0.0


def _box_volume(a: np.ndarray) -> float:
    return float(np.prod(np.maximum(a[1] - a[0], 1e-6)))


def run(named: dict[str, trimesh.Trimesh], spec: ModelSpec) -> dict:
    """세 가지 건전성 검사 — 결과는 self-check 와 같은 모양({pass, fail, checks})."""
    B = _bounds(named)
    lo, hi = envelope(spec)
    checks: list[dict] = []

    outside = sorted(n for n, b in B.items() if np.any(b[0] < lo - 1e-9) or np.any(b[1] > hi + 1e-9))
    checks.append({"label": "외곽 이탈", "ok": not outside, "nodes": outside[:10],
                   "detail": "외곽 x[%.1f,%.1f] y[%.1f,%.1f] z[%.1f,%.1f] 밖 %d개"
                             % (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2], len(outside))})

    keys = sorted(B)
    floating = []
    for n in keys:
        g = np.array([B[n][0] - TOUCH, B[n][1] + TOUCH])
        if not any(m != n and _overlap_volume(g, B[m]) > 0 for m in keys):
            floating.append(n)
    checks.append({"label": "부유 부재", "ok": not floating, "nodes": floating[:10],
                   "detail": "%dmm 안에서 다른 부재와 닿지 않는 노드 %d개" % (int(TOUCH * 1000), len(floating))})

    # 겹침 비율로 보면 슬래브가 방호벽을, 하판이 격벽을 품는 정상 관계까지 걸린다.
    # 정말 잡고 싶은 것은 '같은 부재를 두 번 놓은 경우' 이므로 bbox 가 거의 같은 쌍만 본다.
    dup = []
    for i, n in enumerate(keys):
        for m in keys[i + 1:]:
            if float(np.max(np.abs(B[n] - B[m]))) <= SAME_BOX:
                dup.append("%s↔%s" % (n, m))
    checks.append({"label": "중복 배치", "ok": not dup, "nodes": dup[:10],
                   "detail": "bbox 가 %dmm 안에서 같은 쌍 %d개" % (int(SAME_BOX * 1000), len(dup))})

    n_fail = sum(1 for c in checks if not c["ok"])
    return {"pass": len(checks) - n_fail, "fail": n_fail, "checks": checks}
