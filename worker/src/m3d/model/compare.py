"""참조 대조 (M3 설계 D6·합격 기준 ④) — 우리 measure.json vs 참조 measure v2 JSON, GLB vs GLB.

같은 키 경로의 값을 재귀 대조한다. `대조`(항목 리스트)는 `항목` 이름으로, `내공_H_프로파일` 은 `위치`,
`격벽_상세` 는 `격벽` 으로 짝을 맞춘다(참조 D6: 한글 키 그대로). 짝이 없거나 형이 다르면 "na".
허용오차는 단위로 정한다: mm 5.0 / m 0.005 / 도 0.5 / 개수 0 / 문자열 동일.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

META_KEYS = {"대상", "치수정본", "월드전개"}          # 문구 — 대조 대상 아님
LIST_KEY = {"대조": "항목", "내공_H_프로파일": "위치", "격벽_상세": "격벽"}
COUNT_UNITS = {"개", "열", "기", "조", "면", "쌍"}


def _tol(path: str, unit: str | None, tol_len_mm: float) -> float:
    if unit in COUNT_UNITS:
        return 0.0
    if unit == "도":
        return 0.5
    if unit == "mm" or path.endswith("_mm") or "_mm" in path.rsplit("/", 1)[-1]:
        return tol_len_mm
    return tol_len_mm / 1000.0                      # m


def _leaf(path, a, b, tol, items, cause=""):
    if isinstance(a, bool) or isinstance(b, bool) or isinstance(a, str) or isinstance(b, str):
        v = "match" if a == b else "mismatch"
        items.append({"path": path, "ours": a, "ref": b, "diff": None, "verdict": v, "cause": cause})
        return
    if a is None or b is None:
        items.append({"path": path, "ours": a, "ref": b, "diff": None,
                      "verdict": "match" if a is None and b is None else "na", "cause": cause or "한쪽 값 없음"})
        return
    diff = float(a) - float(b)
    items.append({"path": path, "ours": a, "ref": b, "diff": round(diff, 6),
                  "verdict": "match" if abs(diff) <= tol + 1e-9 else "mismatch", "cause": cause})


def _walk(path, a, b, unit, tol_len_mm, items):
    if isinstance(a, dict) and isinstance(b, dict):
        u = a.get("단위") if isinstance(a.get("단위"), str) else unit
        for k in list(a) | b.keys() if False else list(dict.fromkeys(list(a) + list(b))):
            if k in META_KEYS or k == "단위":
                continue
            p = f"{path}/{k}" if path else k
            if k not in a or k not in b:
                items.append({"path": p, "ours": a.get(k), "ref": b.get(k), "diff": None, "verdict": "na",
                              "cause": "참조에 없음" if k not in b else "우리에 없음"})
                continue
            if k in LIST_KEY and isinstance(a[k], list) and isinstance(b[k], list):
                _walk_keyed(p, a[k], b[k], LIST_KEY[k], u, tol_len_mm, items)
            else:
                _walk(p, a[k], b[k], u, tol_len_mm, items)
        return
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            items.append({"path": path, "ours": a, "ref": b, "diff": None, "verdict": "na",
                          "cause": "길이 불일치 %d≠%d" % (len(a), len(b))})
            return
        for i, (x, y) in enumerate(zip(a, b)):
            _walk(f"{path}[{i}]", x, y, unit, tol_len_mm, items)
        return
    if isinstance(a, (dict, list)) or isinstance(b, (dict, list)):
        items.append({"path": path, "ours": a, "ref": b, "diff": None, "verdict": "na", "cause": "형 불일치"})
        return
    _leaf(path, a, b, _tol(path, unit, tol_len_mm), items)


def _walk_keyed(path, a_list, b_list, key, unit, tol_len_mm, items):
    a_map = {str(r.get(key)): r for r in a_list if isinstance(r, dict)}
    b_map = {str(r.get(key)): r for r in b_list if isinstance(r, dict)}
    for name in dict.fromkeys(list(a_map) + list(b_map)):
        p = f"{path}[{name}]"
        if name not in a_map or name not in b_map:
            items.append({"path": p, "ours": a_map.get(name), "ref": b_map.get(name), "diff": None, "verdict": "na",
                          "cause": "참조에 없음" if name not in b_map else "우리에 없음"})
            continue
        ra, rb = a_map[name], b_map[name]
        _walk(p, {k: v for k, v in ra.items() if k != key}, {k: v for k, v in rb.items() if k != key}, unit, tol_len_mm, items)


def compare(ours: dict, ref: dict, tol_len_mm: float = 5.0) -> dict:
    items: list[dict] = []
    _walk("", ours, ref, None, tol_len_mm, items)
    summary = {v: sum(1 for it in items if it["verdict"] == v) for v in ("match", "mismatch", "na")}
    return {"tol_len_mm": tol_len_mm, "items": items, "summary": summary}


def compare_glb(ours: Path, ref: Path) -> dict:
    """GLB 대 GLB — 노드 수·bbox·삼각형 수 + 동명 노드별 bbox 최대 편차."""
    def nodes(p):
        sc = trimesh.load(str(p))
        out = {}
        for node in sc.graph.nodes_geometry:
            T, g = sc.graph[node]
            m = sc.geometry[g].copy()
            m.apply_transform(T)
            out[str(g)] = m
        return out
    A, B = nodes(ours), nodes(ref)
    common = sorted(set(A) & set(B))
    devs = {n: float(np.abs(np.asarray(A[n].bounds) - np.asarray(B[n].bounds)).max()) for n in common}
    worst = sorted(devs.items(), key=lambda kv: -kv[1])[:10]

    def bbox(M):
        lo = np.min([m.bounds[0] for m in M.values()], axis=0)
        hi = np.max([m.bounds[1] for m in M.values()], axis=0)
        return [[round(float(v), 4) for v in lo], [round(float(v), 4) for v in hi]]
    return {
        "ours": {"path": str(ours), "nodes": len(A), "triangles": int(sum(len(m.faces) for m in A.values())), "bbox": bbox(A)},
        "ref": {"path": str(ref), "nodes": len(B), "triangles": int(sum(len(m.faces) for m in B.values())), "bbox": bbox(B)},
        "only_ours": sorted(set(A) - set(B)), "only_ref": sorted(set(B) - set(A)),
        "common": len(common),
        "bbox_dev_max_m": round(max(devs.values()), 6) if devs else None,
        "bbox_dev_over_1mm": sum(1 for v in devs.values() if v > 1e-3),
        "worst": [{"node": n, "dev_m": round(v, 6)} for n, v in worst],
        "faces_equal": all(len(A[n].faces) == len(B[n].faces) for n in common),
    }
