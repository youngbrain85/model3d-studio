"""섹션 메타 (M7 D2) — 섹션마다 다른 것만 한 표에: 판독 근거 정규식·대표 노드·역할 라벨·스펙 발췌 키.

크롭(crops)·프롬프트(context)·자기 렌더(critique)·채점 피드백(score)·잡 루프(loop)가 모두 여기를 읽는다.
새 부재 그룹을 에이전트 대상으로 넣으려면 이 표에 한 줄을 더한다.
BOX(본체)는 ctx 가 곧 그 기하라 대상이 아니다 — 표에 없으면 루프가 unsupported_section 으로 마감한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from m3d.model import sections as X


@dataclass(frozen=True)
class SectionMeta:
    code: str
    label: str
    pattern: str | None                      # 판독 근거 정규식 (None = 크롭 없음)
    rep_nodes: tuple[str, ...]               # 자기 렌더 근접 뷰의 대표 노드
    roles: tuple[tuple[str, str], ...]       # (노드명 정규식, 역할 라벨) — 앞에서부터 첫 일치
    spec_keys: tuple[str, ...]               # 스펙 발췌에 넣을 하위 모델 (공통 coord·box 는 항상 추가)


SECTIONS: dict[str, SectionMeta] = {m.code: m for m in (
    SectionMeta("DIA", "격벽", r"다이아프램|격벽|DIAP|개구|문턱|잭업|수직보강",
                ("AB1_S5_DIA01",),
                ((r"DIA(01|26)$", "지점 격벽"), (r"DIA\d\d$", "일반 격벽")),
                ("diaphragm", "bearing")),
    SectionMeta("SP04", "이음판", r"이음판|SP-?04|현장이음|스플라이스",
                ("AB1_S5_SP04_TF",),
                ((r"_TF$", "상면판"), (r"_BF$", "하면판"), (r"_WEB_[LR]$", "복부판")),
                ("sp04",)),
    SectionMeta("HST", "수평보강재", None,
                ("AB1_S5_HST_UP_L",),
                ((r"_UP_[LR]$", "상단열"), (r"_LO1_[LR]$", "하단 1열"), (r"_LO2_[LR]$", "하단 2열")),
                ("hstiff", "diaphragm")),
    SectionMeta("SLAB", "슬래브·방호벽", r"슬래브|바닥판|방호벽|포장|콘크리트",
                ("AB1_S5_SLAB",),
                ((r"BARRIER_CTR$", "중앙 방호벽"), (r"BARRIER_[LR]$", "연단 방호벽"), (r"SLAB$", "바닥판")),
                ("slab",)),
    SectionMeta("BRG", "받침", r"받침|솔플레이트|무수축|모르타르|교좌",
                ("AB1_S5_BRG_P4_1_BODY",),
                ((r"_SOLE$", "솔플레이트"), (r"_BODY$", "받침 본체"), (r"_MORTAR$", "무수축 모르타르"),
                 (r"_BLOCK$", "받침 블록")),
                ("bearing",)),
    SectionMeta("FRM", "개방 프레임", r"프레임|개방|가로보|수직보강재|FRAME|브레이싱",
                ("AB1_S5_FRM01_TRW",),
                ((r"_TRW$", "상부 웹"), (r"_TRF$", "상부 플랜지"), (r"_BRW$", "하부 웹"),
                 (r"_BRF$", "하부 플랜지"), (r"_VS[LR]$", "수직보강재")),
                ("frame", "diaphragm")),
    SectionMeta("RIB", "종리브", r"종리브|리브|U-?리브|RIB",
                ("AB1_S5_RIB_TP4_1",),
                ((r"_RIB_T", "상판 리브"), (r"_RIB_B", "하판 리브")),
                ("rib",)),
    SectionMeta("CS", "외측빔", r"외측빔|연단|CS|가로보 선단",
                ("AB1_S5_CS096L",),
                ((r"CS\d+L$", "좌(보도측)"), (r"CS\d+R$", "우")),
                ("cs", "wg")),
    SectionMeta("WG", "외측가로보", r"외측가로보|가로보|캔틸레버|스트럿|니치|WG",
                ("AB1_S5_WG096L",),
                ((r"_ST$", "스트럿"), (r"_BR$", "브래킷"), (r"WG\d+[LR]$", "가로보 본체")),
                ("wg", "slab")),
)}


def meta(code: str) -> SectionMeta | None:
    return SECTIONS.get(code)


def role_of(code: str, node: str) -> str | None:
    """노드 → 역할 라벨(채점 피드백·렌더 캡션용). 표에 없으면 None."""
    m = SECTIONS.get(code)
    if m is None:
        return None
    for pat, label in m.roles:
        if re.search(pat, node):
            return label
    return None


def node_names(ref_dir, segment: str, code: str) -> list[str]:
    """정답 섹션 GLB 의 노드명(정렬) — 계약에 싣는 목록(D3)."""
    from m3d.agent.score import load_named
    return sorted(load_named(Path(ref_dir) / "sections" / segment / f"{code}.glb"))


assert set(SECTIONS) == set(X.CODES) - {"BOX"}, "섹션 메타와 부재 그룹 목록이 어긋난다"
