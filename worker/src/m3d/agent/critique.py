"""자기 렌더 피드백 (M6 D4) — 채점에 실패한 시도의 섹션 GLB 만으로 몇 장 렌더해 다음 시도 프롬프트에 붙인다.

정답 렌더는 주지 않는다. LLM 은 자기 결과 그림을 도면 크롭·규칙과 비교해 방향·돌출·개구를 스스로 고친다.
그림 제목은 짧게(title), 프롬프트 캡션은 길게(caption) — 긴 제목은 tight bbox 로 그림 폭만 키운다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from m3d.model import render
from m3d.model.spec import ModelSpec

DPI = 100
VIEWS: dict[str, list[dict]] = {
    "DIA": [
        {"name": "dia01_front", "nodes": ("AB1_S5_DIA01",), "eye": (0.3, 0.2, 1.0), "size": (8, 6),
         "title": "DIA01 정면 아이소(+z 쪽에서 비스듬히, 좌=-x)",
         "caption": "이전 시도 DIA01 정면 — +z(경간 안쪽) 쪽에서 비스듬히 본 판면·개구·보강재(보강재는 판면 앞에 상자로 보여야 한다), 화면 좌 = -x"},
        {"name": "dia01_side", "nodes": ("AB1_S5_DIA01",), "eye": (1, 0, 0), "size": (5, 10), "chain": "z_p4",
         "title": "DIA01 측면(+x 에서, 좌=+z)",
         "caption": "이전 시도 DIA01 측면 — +x 에서, 화면 좌 = +z(경간 안쪽), 점선 = 체인 z_p4; 보강재 돌출은 판면에서 왼쪽으로 보여야 한다"},
        {"name": "dia13_iso", "nodes": ("AB1_S5_DIA13",), "eye": (0.7, 0.45, 0.85), "size": (8, 6),
         "title": "DIA13 아이소(+x+y+z 에서)",
         "caption": "이전 시도 DIA13 아이소 — +x+y+z 에서, 개구보강재는 +z 면"},
    ],
}


def _chain_marker(z_chain: float, y_lo: float, y_hi: float):
    """측면 뷰에 체인 위치 점선과 경간 안쪽 방향 표시 — render() 의 extra(ax, right, upv) 훅."""
    def extra(ax, right, upv):
        x = float(np.dot(np.array([0.0, 0.0, z_chain]), right))
        ax.plot([x, x], [y_lo - 0.2, y_hi + 0.2], "--", color="#c0392b", linewidth=0.9)
        ax.text(x, y_lo - 0.35, "← 경간 안쪽(+z)   체인 z_p4", fontsize=8, color="#c0392b", ha="center")
    return extra


def render_views(agent_glb: Path, spec: ModelSpec, code: str, out_dir: Path) -> list[dict]:
    """섹션 코드의 뷰 표대로 PNG 를 만들고 [{"path", "caption"}] 를 돌려준다. 노드가 없는 뷰는 건너뛴다."""
    views = VIEWS.get(code, [])
    if not views:
        return []
    by_name = {n: (n, m, c) for n, m, c in render.load_nodes(Path(agent_glb))}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []
    for v in views:
        sel = [by_name[n] for n in v["nodes"] if n in by_name]
        if not sel:
            continue
        V, F, C = render.to_tris(sel)
        extra = None
        if v.get("chain") == "z_p4":
            extra = _chain_marker(spec.coord.z_p4, float(V[:, 1].min()), float(V[:, 1].max()))
        path = render.render(V, F, C, v["eye"], render.Y_UP, out_dir / (v["name"] + ".png"), v["title"],
                             size=v["size"], dpi=DPI, extra=extra)
        out.append({"path": Path(path), "caption": v["caption"]})
    return out
