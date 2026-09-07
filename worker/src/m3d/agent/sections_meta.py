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
    notes: str = ""                          # 이름만으로는 알 수 없는 섹션 규약(좌우 인덱스·존 이름·체인 중심 등)


SECTIONS: dict[str, SectionMeta] = {m.code: m for m in (
    SectionMeta("DIA", "격벽", r"다이아프램|격벽|DIAP|개구|문턱|잭업|수직보강",
                ("AB1_S5_DIA01",),
                ((r"DIA(01|26)$", "지점 격벽"), (r"DIA\d\d$", "일반 격벽")),
                ("diaphragm", "bearing")),
    SectionMeta("SP04", "이음판", r"이음판|SP-?04|현장이음|스플라이스",
                ("AB1_S5_SP04_WEB_L",),
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
                ("bearing",),
                "P4_1·P5_1 은 x = −bearing.x, P4_2·P5_2 는 +bearing.x (번호 1 이 −x 쪽이다). "
                "부품은 해당 받침선의 하판 하면(ctx.y_bot_out)에서 아래로 SOLE → BODY → MORTAR → BLOCK 순으로 쌓인다. 기준면은 받침 하면 = y_bot_out(받침선) − bearing.body_h 이고, SOLE 은 하판 하면 바로 아래 두께 sole[3], BODY 는 SOLE 밑면부터 받침 하면까지다."),
    SectionMeta("FRM", "개방 프레임", r"프레임|개방|가로보|수직보강재|FRAME|브레이싱",
                ("AB1_S5_FRM01_TRW",),
                ((r"_TRW$", "상부 웹"), (r"_TRF$", "상부 플랜지"), (r"_BRW$", "하부 웹"),
                 (r"_BRF$", "하부 플랜지"), (r"_VS[LR]$", "수직보강재")),
                ("frame", "diaphragm"),
                "FRM<k>(k=01..25) 의 z = z_p4 + frame.offset + (k−1)·diaphragm.spacing — 격벽 사이마다 하나. "
                "규격은 그 프레임의 dmin(양 받침선까지 최소 거리)이 d_list 에 든 frame.rows 행을 골라 쓴다. VSL 은 −x 쪽, VSR 은 +x 쪽 웹 내면. 참조 단순화 [A6]: 플랜지는 웹과 같은 z 중심에 두되 **플랜지의 z 폭은 그 웹의 h 값을 그대로 쓴다**(상부 플랜지 폭 = top_web[1], 하부 = bot_web[1]); 상부 플랜지 두께는 top_flange_t(None 이면 top_web[0]), 하부 플랜지 두께는 bot_web[0]."),
    SectionMeta("RIB", "종리브", r"종리브|리브|U-?리브|RIB",
                ("AB1_S5_RIB_TP4_1",),
                ((r"_RIB_T", "상판 리브"), (r"_RIB_B", "하판 리브")),
                ("rib",),
                "이름의 존 구분: T=상판(강상판 아래), B=하판(하판 위). P4/P5 = 그 받침선 쪽 지점존, "
                "X4/X5 = 전이 구간(지점존 열 + 중앙존 열을 함께 둔다), MA/MB·M = 중앙존. "
                "중앙존이 MA·MB 로 갈리는 것은 SP04 현장이음선 z = z_p4 + box.z_sp04_offset 에서 끊기 때문이다(MA 가 P4 쪽). "
                "하판 지점존이 BP4A·BP4B 로 갈리는 것도 같은 이음선 때문이다. 끝 숫자는 x 열 번호이고, 각 존의 열 x 는 (i − (cols−1)/2)·pitch (i=0..cols−1, x=0 중심 대칭). **X4/X5 전이 구간의 번호는 지점존 열 목록 뒤에 중앙존 열 목록을 그대로 이어붙인 순서다** — x 오름차순이 아니다."),
    SectionMeta("CS", "외측빔", r"외측빔|연단|CS|가로보 선단",
                ("AB1_S5_CS096L",),
                ((r"CS\d+L$", "좌(보도측)"), (r"CS\d+R$", "우")),
                ("cs", "wg"),
                "번호는 가로보와 같다(wg.first_no 부터 체인 순서). 각 세그는 그 체인 위치를 **중심**으로 ±cs.seg/2 이고 받침선 밖은 잘린다. "
                "x 는 가로보 선단 ctx.x_web + wg.length 를 **중심**으로 플랜지 ±wg.fl_w/2·웹 ±cs.web_t/2. 상면은 그 z 에서의 가로보 선단 상플랜지 상면(아래 WG 규약의 상플랜지 프로파일 u(x)+fl_t 를 x=wg.length 에서 구한 값), 거기서 아래로 cs.depth 가 춤이다. L 은 x<0, R 은 x>0."),
    SectionMeta("WG", "외측가로보", r"외측가로보|가로보|캔틸레버|스트럿|니치|WG",
                ("AB1_S5_WG096L",),
                ((r"_ST$", "스트럿"), (r"_BR$", "브래킷"), (r"WG\d+[LR]$", "가로보 본체")),
                ("wg", "slab"),
                "L 은 x<0(보도측), R 은 x>0 — 좌우 대칭이다. 번호는 wg.first_no 부터 격벽 체인 순서. "
                "_ST 스트럿은 아래 작업점 (x_web + strut_lower[0], y_deck_top − strut_lower[1]) 에서 "
                "위 작업점 (x_web + knee[0], y_deck_top − knee[1]) 까지 뻗는 I형 부재라 x 로 길게 눕는다. 상플랜지 프로파일(crown 기준 상대 y): u(x) = −(slab.cant_drop[0][1] + wg.fl_t) + 0.003 − wg.flange_slope·max(0, min(x, wg.flange_flat1) − wg.flange_flat0) — x 는 웹 외면에서 잰 거리, 0.003 은 공면 회피 상향 시프트 [A9]. _BR 정착대의 z 폭은 스펙에 없고 ±0.150 고정이다."),
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
