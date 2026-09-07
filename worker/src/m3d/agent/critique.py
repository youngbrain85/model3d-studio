"""자기 렌더 피드백 (M6 D4) — 채점에 실패한 시도의 섹션 GLB 만으로 몇 장 렌더해 다음 시도 프롬프트에 붙인다.

정답 렌더는 주지 않는다. LLM 은 자기 결과 그림을 도면 크롭·규칙과 비교해 방향·돌출·개구를 스스로 고친다.
그림 제목은 짧게(title), 프롬프트 캡션은 길게(caption) — 긴 제목은 tight bbox 로 그림 폭만 키운다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from m3d.agent import sections_meta
from m3d.model import render
from m3d.model.spec import ModelSpec

DPI = 100


def views_for(code: str) -> list[dict]:
    """섹션 메타 → 3뷰 (M7 D5): 대표 노드 정면 아이소·측면(체인선)·섹션 전체 아이소.

    세 번째(전체)가 개수·간격·좌우 배치 오류를 보여 준다 — 근접 뷰만으로는 안 보인다.
    """
    m = sections_meta.meta(code)
    if m is None:
        return []
    rep, label = m.rep_nodes, m.label
    short = rep[0].replace("AB1_S5_", "")
    return [
        {"name": "rep_front", "nodes": rep, "eye": (0.3, 0.2, 1.0), "size": (8, 6),
         "title": f"{short} 정면 아이소(+z 쪽에서, 좌=-x)",
         "caption": f"이전 시도 {label} 대표 부재 정면 — +z(경간 안쪽) 쪽에서 비스듬히 본 판면·개구·부속"
                    "(보강재는 판면 앞에 상자로 보여야 한다), 화면 좌 = -x"},
        {"name": "rep_side", "nodes": rep, "eye": (1, 0, 0), "size": (5, 10), "chain": "z_p4",
         "title": f"{short} 측면(+x 에서, 좌=+z)",
         "caption": f"이전 시도 {label} 대표 부재 측면 — +x 에서, 화면 좌 = +z(경간 안쪽), 점선 = 체인 z_p4;"
                    " 돌출은 판면에서 왼쪽으로 보여야 한다"},
        {"name": "section_all", "nodes": None, "eye": (0.7, 0.45, 0.85), "size": (10, 6),
         "title": f"{code} 섹션 전체(+x+y+z 에서)",
         "caption": f"이전 시도 {label} 섹션 전체 — +x+y+z 에서 본 배치·개수·좌우·간격."
                    " 빠진 부재나 엉뚱한 위치가 있는지 확인하라"},
    ]


MAX_ASPECT = 20.0        # 화면 비율이 이보다 납작하면(예: 44m 평강의 측면) 그림이 무의미하다 — 그 뷰는 건너뛴다


def _chain_marker(z_c: float, z_p4: float, y_lo: float, y_hi: float):
    """측면 뷰에 부재 z 위치 점선과 경간 안쪽 방향 표시 — render() 의 extra(ax, right, upv) 훅.

    점선은 부재 자신의 z 에 그린다. 멀리 있는 z_p4 에 그리면 화면이 그쪽까지 늘어나 부재가 실처럼 보인다(M7 육안 확인).
    """
    def extra(ax, right, upv):
        x = float(np.dot(np.array([0.0, 0.0, z_c]), right))
        ax.plot([x, x], [y_lo - 0.2, y_hi + 0.2], "--", color="#c0392b", linewidth=0.9)
        ax.text(x, y_lo - 0.35, "← 경간 안쪽(+z)   P4+%.1fm" % (z_c - z_p4), fontsize=8, color="#c0392b", ha="center")
    return extra


def _too_flat(V, eye) -> bool:
    """정사영 화면에서 가로:세로가 MAX_ASPECT 를 넘으면 알아볼 수 없다 — 그리지 않는다."""
    e = np.asarray(eye, float)
    e = e / np.linalg.norm(e)
    right = np.cross(render.Y_UP, e)
    right = right / np.linalg.norm(right)
    up = np.cross(e, right)
    xs, ys = V @ right, V @ up
    w, h = float(np.ptp(xs)), float(np.ptp(ys))
    lo = min(w, h)
    return lo <= 1e-9 or max(w, h) / lo > MAX_ASPECT


def render_views(agent_glb: Path, spec: ModelSpec, code: str, out_dir: Path) -> list[dict]:
    """섹션 코드의 뷰 표대로 PNG 를 만들고 [{"path", "caption"}] 를 돌려준다. 노드가 없는 뷰는 건너뛴다."""
    views = views_for(code)
    if not views:
        return []
    by_name = {n: (n, m, c) for n, m, c in render.load_nodes(Path(agent_glb))}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []
    for v in views:
        sel = list(by_name.values()) if v["nodes"] is None else [by_name[n] for n in v["nodes"] if n in by_name]
        if not sel:
            continue
        V, F, C = render.to_tris(sel)
        extra = None
        if v.get("chain") == "z_p4":
            extra = _chain_marker(float(V[:, 2].mean()), spec.coord.z_p4, float(V[:, 1].min()), float(V[:, 1].max()))
        if _too_flat(V, v["eye"]):
            continue
        path = render.render(V, F, C, v["eye"], render.Y_UP, out_dir / (v["name"] + ".png"), v["title"],
                             size=v["size"], dpi=DPI, extra=extra)
        out.append({"path": Path(path), "caption": v["caption"]})
    return out
