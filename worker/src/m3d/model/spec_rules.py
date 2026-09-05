"""SSOT(ssot.json) → ModelSpec 추출 규칙 (M3 설계서 §3, D2·D3·D4).

규칙이 채운 필드는 `ssot:<ord>/<item>` 또는 `decision:<item>`, 계산값은 `derived:<식>`, 못 채운 필드는
`default:SPEC_v2 §n`(참조 사양 차용) 으로 출처를 남긴다. 은폐하지 않는다 — 출처 통계가 곧 성적표다.
"""

from __future__ import annotations

import re
from collections import defaultdict

from m3d.model.spec import ModelSpec, Zone, leaf_paths

DEFAULT_SECTION = {           # 필드 접두 → 참조 사양 절 (default 출처 표기용)
    "coord": "§0", "box": "§1", "diaphragm": "§2", "frame": "§3", "rib": "§4", "hstiff": "§5",
    "wg": "§6", "cs": "§7", "slab": "§8", "sp04": "§9", "bearing": "§10",
}

_NUM = r"[0-9][0-9,]*(?:\.[0-9]+)?"


def parse_number(text: str) -> float | None:
    """'15,700' → 15700.0, '4,000/2,800' → 첫 수. 숫자가 없으면 None."""
    m = re.search(_NUM, text or "")
    return float(m.group(0).replace(",", "")) if m else None


def parse_at_chain(text: str) -> tuple[int, float, float] | None:
    """'9@70,000=630,000' → (9, 70000.0, 630000.0)."""
    m = re.search(rf"(\d+)\s*@\s*({_NUM})\s*=\s*({_NUM})", text or "")
    if not m:
        return None
    return int(m.group(1)), float(m.group(2).replace(",", "")), float(m.group(3).replace(",", ""))


def parse_pair(text: str) -> tuple[float, float] | None:
    """'450×330' / '450x330' / '250 / 330' → (450.0, 330.0)."""
    m = re.search(rf"({_NUM})\s*[×x/]\s*({_NUM})", text or "")
    if not m:
        return None
    return float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))


def parse_thickness_zones(text: str, total: float) -> list[Zone] | None:
    """'38(0~6,300) → 26(~16,100) → 16(~53,900) → 26 → 38' → [(0,6300,38), …] (mm).

    뒤쪽에 경계가 없는 항은 앞쪽과 대칭으로 보완한다. 사슬이 total 로 닫히지 않으면 None.
    """
    items = [s.strip() for s in re.split(r"→|->", text or "") if s.strip()]
    if not items:
        return None
    parsed: list[tuple[float, float | None]] = []
    for it in items:
        m = re.match(rf"({_NUM})\s*(?:\(\s*(?:({_NUM}))?\s*~\s*({_NUM})\s*\))?", it)
        if not m:
            return None
        t = float(m.group(1).replace(",", ""))
        end = float(m.group(3).replace(",", "")) if m.group(3) else None
        parsed.append((t, end))
    n = len(parsed)
    ends: list[float | None] = [e for _, e in parsed]
    for i in range(n):                       # 대칭 보완: i 번째 끝 = total − (n−2−i) 번째 끝
        if ends[i] is None:
            j = n - 2 - i
            if 0 <= j < n and ends[j] is not None:
                ends[i] = total - ends[j]
    if ends[-1] is None:
        ends[-1] = total
    if any(e is None for e in ends):
        return None
    zones: list[Zone] = []
    d0 = 0.0
    for (t, _), e in zip(parsed, ends):
        zones.append((d0, float(e), t))
        d0 = float(e)
    if abs(zones[-1][1] - total) > 1e-6:
        return None
    return zones


def zones_from_class_totals(classes: dict[float, list[float]], span: float) -> list[Zone] | None:
    """판독이 두께별 연장으로 흩어져 있을 때 대칭 사슬을 복원한다 (SSOT C01 형태).

    `classes` 는 두께 → 판독된 연장 목록. 판독은 같은 구간을 총연장과 소구간으로 겹쳐 적기도 하므로
    등급마다 후보 길이를 {합, 최대값} 두 가지로 두고, 규칙(가장 두꺼운 등급 = 양끝(길이/2 씩),
    가장 얇은 등급 = 중앙(길이), 중간 등급 = 편측 연장으로 두 번)으로 합이 span 에 닫히는 조합을
    고른다. 없으면 None(사양 차용).
    """
    from itertools import product

    if len(classes) < 2:
        return None
    order = sorted(classes.items(), key=lambda kv: -kv[0])   # 두께 내림차순
    cands = [sorted({sum(Ls), max(Ls)}) for _, Ls in order]
    for pick in product(*cands):
        t_end, L_end = order[0][0], pick[0]
        t_mid, L_mid = order[-1][0], pick[-1]
        per_side = [(t_end, L_end / 2.0)] + [(order[i][0], pick[i]) for i in range(1, len(order) - 1)]
        total = 2 * sum(L for _, L in per_side) + L_mid
        if abs(total - span) > 1e-6:
            continue
        zones: list[Zone] = []
        d = 0.0
        for t, L in per_side:
            zones.append((d, d + L, t)); d += L
        zones.append((d, d + L_mid, t_mid)); d += L_mid
        for t, L in reversed(per_side):
            zones.append((d, d + L, t)); d += L
        return zones
    return None


def _mm(v: float) -> float:
    return v / 1000.0


def _find(readings: list[dict], *needles: str, region: str | None = None, status: str | None = None):
    for r in readings:
        if region and r["region"] != region:
            continue
        if status and r["status"] != status:
            continue
        if all(n in r["item"] for n in needles):
            return r
    return None


def _src(r: dict) -> str:
    return f"ssot:{r['ord']}/{r['item']}"


def build_modelspec(ssot: dict) -> tuple[ModelSpec, dict[str, str]]:
    """ssot.json(dict) → (ModelSpec, {필드경로: 출처})."""
    spec = ModelSpec()
    src: dict[str, str] = {}
    readings = ssot.get("readings", [])
    decisions = ssot.get("decisions", [])
    span_mm = spec.coord.span * 1000.0

    # §0 받침선 z — 프로젝트 좌표계 datums
    datums = (ssot.get("project", {}).get("coord_system") or {}).get("datums") or {}
    if "P4_bearing_z" in datums and "P5_bearing_z" in datums:
        spec.coord.z_p4 = float(datums["P4_bearing_z"]); spec.coord.z_p5 = float(datums["P5_bearing_z"])
        src["coord.z_p4"] = src["coord.z_p5"] = "ssot:project.coord_system.datums"
        span_mm = spec.coord.span * 1000.0

    # §0/§1 지간 — '9@70,000=630,000' 이 받침선 간격과 맞는지 검산(정보)
    r = _find(readings, "지간구성")
    if r and (chain := parse_at_chain(str(r["value_raw"]))):
        if abs(chain[1] - span_mm) < 1e-6:
            src["derived:span_check"] = f"{_src(r)} → 지간 {chain[1]:.0f} = 받침선 간격 ✓"

    # §1 형고(내공) — C 계열 '형고' 4,000 / 2,800
    for r in readings:
        if r["region"] == "C" and "형고" in r["item"]:
            v = parse_number(str(r["value_raw"]))
            if v == 4000.0 and "box.h_pier" not in src:
                spec.box.h_pier = 4.0; src["box.h_pier"] = _src(r)
            elif v == 2800.0 and "box.h_mid" not in src:
                spec.box.h_mid = 2.8; src["box.h_mid"] = _src(r)

    # §1 판두께 존 — '상판 판두께 12,600(T=38mm …)' 형태의 두께별 총연장 → 대칭 사슬 복원
    for key, needle in (("top_t", "상판 판두께"), ("bot_t", "하판 판두께"), ("web_t", "복부판 두께")):
        classes: dict[float, list[float]] = defaultdict(list)
        used: list[str] = []
        for r in readings:
            if r["region"] == "C" and needle in r["item"]:
                m = re.search(rf"({_NUM})\s*\(\s*T\s*=\s*({_NUM})", str(r["value_raw"]))
                if m:
                    classes[float(m.group(2).replace(",", ""))].append(float(m.group(1).replace(",", "")))
                    used.append(r["ord"])
        zones = zones_from_class_totals(dict(classes), span_mm) if classes else None
        if zones:
            setattr(spec.box, key, [(_mm(a), _mm(b), _mm(t)) for a, b, t in zones])
            src[f"box.{key}"] = f"ssot:{used[0]}/{needle} 두께별 총연장 {len(used)}건 → 대칭 사슬 복원(derived)"

    # §2 격벽 간격·개수
    r = _find(readings, "다이아프램 간격", status="확정") or _find(readings, "다이아프램 간격")
    if r and (chain := parse_at_chain(str(r["value_raw"]))):
        spec.diaphragm.spacing = _mm(chain[1]); src["diaphragm.spacing"] = _src(r)
        spec.diaphragm.n_cell = int(round(span_mm / chain[1]))
        src["diaphragm.n_cell"] = f"derived:지간 {span_mm:.0f} / 간격 {chain[1]:.0f}"
    # 격벽 규격 'DIAP 10x4500x3739' → 일반 격벽 판두께·타입별 높이표
    type_d = {name: d for d, name in spec.diaphragm.type_map}
    table = dict(spec.diaphragm.h_table)
    got_t = False
    for r in readings:
        m = re.search(r"\b(C[LXU]\d?)\b.*DIAP\s*(\d+)x(\d+)x(\d+)", r["item"] + " " + str(r["value_raw"]))
        if not m:
            continue
        name, t, _w, h = m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4))
        if not got_t:
            spec.diaphragm.interior_t = _mm(t); src["diaphragm.interior_t"] = _src(r); got_t = True
        if name in type_d:
            table[type_d[name]] = _mm(h); src.setdefault("diaphragm.h_table", _src(r))
    spec.diaphragm.h_table = sorted(table.items())

    # §8 슬래브·방호벽
    r = _find(readings, "전체 폭원", status="확정")
    if r and (v := parse_number(str(r["value_raw"]))):
        spec.slab.half_width = _mm(v) / 2.0; src["slab.half_width"] = _src(r)
    r = _find(readings, "슬래브 콘크리트 두께")
    if r and (v := parse_number(str(r["value_raw"]))):
        spec.slab.t_web = _mm(v); src["slab.t_web"] = _src(r)
    r_w = _find(readings, "방호벽 하부 폭"); r_h = _find(readings, "방호벽 높이 구간")
    if r_w and r_h:
        w = parse_number(str(r_w["value_raw"])); pair = parse_pair(str(r_h["value_raw"]))
        if w and pair:
            spec.slab.barrier = (_mm(w), _mm(max(pair)), spec.slab.barrier[2])
            src["slab.barrier"] = f"{_src(r_w)} + {_src(r_h)}"

    # §10 받침 간격
    r = _find(readings, "받침 간격")
    if r and (v := parse_number(str(r["value_raw"]))):
        spec.bearing.x = _mm(v) / 2.0; src["bearing.x"] = _src(r)

    # 결정(질문 카드) — Q1~Q4 [D4]
    for d in decisions:
        item, label = d["item"], d["choice_label"]
        if "형고" in item and ("내공" in item or "전강고" in item):
            spec.box.h_is_clear = "내공" in label; src["box.h_is_clear"] = f"decision:{item}"
        elif "슬래브 두께" in item:
            spec.slab.thickness_is_net = ("순" in label) or ("포장" not in label)
            src["slab.thickness_is_net"] = f"decision:{item}"
        elif "보도" in item and ("2,950" in label or "분할" in item or "명칭" in item):
            nums = [float(x.replace(",", "")) for x in re.findall(_NUM, label)]
            if 2950.0 in nums:
                spec.slab.walk_width = 2.95; src["slab.walk_width"] = f"decision:{item}"
            if 450.0 in nums:
                spec.slab.center_barrier = 0.45; src["slab.center_barrier"] = f"decision:{item}"
        elif "받침" in item and ("면진" in item or "방향" in item or "형식" in item):
            spec.bearing.kind = "isolation" if "면진" in label else ("fixed" if ("고정" in label or "가동" in label) else spec.bearing.kind)
            src["bearing.kind"] = f"decision:{item}"

    # 나머지: 참조 사양 차용 표기
    for path in leaf_paths(spec):
        if path not in src:
            src[path] = f"default:SPEC_v2 {DEFAULT_SECTION[path.split('.')[0]]}"
    return spec, src


def source_stats(sources: dict[str, str]) -> dict[str, int]:
    stats = {"ssot": 0, "decision": 0, "default": 0, "derived": 0}
    for path, s in sources.items():
        if path.startswith("derived:"):
            stats["derived"] += 1
        elif s.startswith("ssot:"):
            stats["ssot"] += 1
        elif s.startswith("decision:"):
            stats["decision"] += 1
        elif s.startswith("derived:"):
            stats["derived"] += 1
        else:
            stats["default"] += 1
    return stats
