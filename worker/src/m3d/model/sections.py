"""섹션 = 구간/부재그룹 (M4 설계 D1·D2) — 노드명 → 그룹, 분할, 결합. 순수 함수(빌더·DB 무관).

전 부재가 전역 체인 좌표(받침선 + n×간격)에 놓여 있어 결합은 좌표 변환 없는 합치기다(KB §2-18).
"""

from __future__ import annotations

import re

import trimesh

GROUPS: list[tuple[str, str]] = [
    ("BOX", "본체"), ("DIA", "격벽"), ("FRM", "개방 프레임"), ("RIB", "종리브"), ("HST", "수평보강재"),
    ("WG", "외측가로보"), ("CS", "외측빔"), ("SLAB", "슬래브·방호벽"), ("SP04", "이음판"), ("BRG", "받침"),
]
CODES = [c for c, _ in GROUPS]
LABELS = dict(GROUPS)
_NODE = re.compile(r"^[A-Z0-9]+_[A-Z0-9]+_(BOX|DIA|FRM|RIB|HST|WG|CS|SLAB|BARRIER|SP04|BRG)(?:_|\d|$)")


def group_of(name: str) -> str:
    """노드명 → 그룹 코드. BARRIER 는 슬래브 그룹."""
    m = _NODE.match(name)
    if m is None:
        raise ValueError("그룹을 알 수 없는 노드명: %s" % name)
    code = m.group(1)
    return "SLAB" if code == "BARRIER" else code


def section_key(segment: str, code: str) -> str:
    return f"{segment}/{code}"


def split(named: dict[str, trimesh.Trimesh], segment: str) -> dict[str, dict[str, trimesh.Trimesh]]:
    """노드 dict → {섹션 키: {노드명: 메시}} (CODES 순서, 빈 그룹 제외 — 시범은 BOX·DIA 만)."""
    out: dict[str, dict[str, trimesh.Trimesh]] = {section_key(segment, c): {} for c in CODES}
    for name, mesh in named.items():
        out[section_key(segment, group_of(name))][name] = mesh
    return {k: v for k, v in out.items() if v}


def assemble(sections: dict[str, dict[str, trimesh.Trimesh]]) -> dict[str, trimesh.Trimesh]:
    """레고식 결합 — 변환 없이 합친다. 노드명 중복은 결함(KB §2-15)."""
    named: dict[str, trimesh.Trimesh] = {}
    for key in sections:
        for name, mesh in sections[key].items():
            assert name not in named, "결합 중 노드명 중복: %s (%s)" % (name, key)
            named[name] = mesh
    return named
