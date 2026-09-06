"""에이전트 입력 묶음 (M5 D3) — 규칙(KB §1·§2·§5)·툴킷 문서·ctx·코드 계약·스펙 발췌(출처)·크롭·판독값·피드백·요청."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

from m3d.config import REPO_ROOT
from m3d.model import geom
from m3d.reading.inputs import image_block
from m3d.samples.manifest import sha256_file

KB_PATH = REPO_ROOT / "docs" / "모델링규칙_지식베이스_v0.md"
KB_KEEP = ("## 1. ", "## 2. ", "## 5. ")
TOOLKIT_FUNCS = ("loft", "extrude", "rect", "box_prism", "mirror_poly", "mirror_mesh", "paint", "zone_loft")
SPEC_SECTIONS = ("coord", "box", "diaphragm")

ROLE = ("당신은 강상자형교 3D 모델링 에이전트다. 주어진 치수 정본(ModelSpec 발췌)·도면 크롭·규칙만으로 한 섹션(부재 그룹)의 "
        "파이썬 빌더 함수를 작성한다. 추정으로 확정하지 말고 가정은 assumptions 에, 확인이 필요한 것은 questions 에 낸다.")

CTX_DOC = """## ctx (본체 기하 — 주어진 조건)
- ctx.x_web: 웹 외면 x(m, +측). 웹은 x=±x_web 에 있고 두께 ctx.t_web(z) 만큼 안쪽으로 들어온다.
- ctx.z_p4, ctx.z_p5: P4·P5 받침선 z(m). 격벽·프레임 같은 반복 부재의 위치는 전역 체인 z = z_p4 + k·간격 에서 유도한다.
- ctx.y_web_top(z), ctx.y_web_bot(z): 상판 하면 y / 하판 상면 y (내공 경계, m). ctx.h_box(z) = 내공 높이.
- ctx.t_web(z): 웹 판두께(m). ctx.COL_STEEL: 강재 색 [r,g,b,a]. ctx.INS: 접합부 관통 삽입 5mm.
- ctx.geom: 아래 툴킷 모듈(직접 import 해도 된다: from m3d.model.geom import ...)."""

CODE_CONTRACT = """## 코드 계약
- 최상위에 `def build_section(spec, ctx) -> dict[str, trimesh.Trimesh]` 를 정의한다. spec 은 ModelSpec 전체 dict(m 단위), ctx 는 위 본체 기하.
- 노드명은 `AB1_S5_<그룹><번호>` 규칙(격벽: AB1_S5_DIA01 … AB1_S5_DIA26, 받침선 P4 쪽이 01). 노드명 = 객체 DB 연결 키.
- 모든 메시는 수밀(loft/extrude/box_prism 결과)이고 `geom.paint(mesh, ctx.COL_STEEL)` 로 색을 입힌다. 접합부는 ctx.INS 만큼 관통 삽입한다(공면 금지).
- 허용 import: math, numpy, trimesh, m3d.model.geom. 파일·네트워크·다른 모듈 접근 금지. 단위 m, Y-up, 좌표계는 §1 규약.
- 판두께 방향·개구·보강재 배치처럼 도면에서 확인한 값은 코드 주석에 근거(시트·값)를 적는다."""

OUTPUT_FORMAT = """## 출력
JSON: {"code": "<파이썬 코드 전체>", "assumptions": ["…"], "questions": ["…"]}. code 외 설명은 assumptions/questions 에만."""


def kb_excerpt(text: str) -> str:
    """'## n. ' 절 중 KB_KEEP 로 시작하는 절만 남긴다(다음 '## ' 까지)."""
    out, keep = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            keep = line.startswith(KB_KEEP)
        if keep:
            out.append(line)
    return "\n".join(out).strip()


def toolkit_doc() -> str:
    lines = ["## 툴킷 m3d.model.geom (Poly = [(x,y),...] CCW; z 로프트/압출은 Trimesh 솔리드를 돌려준다)"]
    for name in TOOLKIT_FUNCS:
        fn = getattr(geom, name)
        doc = inspect.getdoc(fn) or ""
        lines.append(f"- {name}{inspect.signature(fn)} — {doc.splitlines()[0] if doc else ''}")
    return "\n".join(lines)


def spec_excerpt(spec_dict: dict, sources: dict) -> dict:
    out = {}
    for sec in SPEC_SECTIONS:
        out[sec] = {k: {"value": v, "source": sources.get(f"{sec}.{k}", "default")} for k, v in spec_dict[sec].items()}
    out["bearing"] = {"x": {"value": spec_dict["bearing"]["x"], "source": sources.get("bearing.x", "default")}}
    return out


def section_bundle(section_key: str, *, spec_dict: dict, sources: dict, evidence: list[dict], crops: list[dict],
                   feedback: str | None = None, request: str = "", prev_code: str | None = None) -> dict:
    segment, code = section_key.split("/")
    kb = kb_excerpt(KB_PATH.read_text(encoding="utf-8")) if KB_PATH.is_file() else ""
    system = "\n\n".join([ROLE, "## 모델링 규칙(지식베이스 발췌)", kb, toolkit_doc(), CTX_DOC, CODE_CONTRACT, OUTPUT_FORMAT])
    ex = spec_excerpt(spec_dict, sources)
    parts: list[dict] = [
        {"type": "text", "text": f"섹션 {section_key} (구간 {segment}, 부재그룹 {code}). 이 섹션의 모든 노드를 만드는 build_section 을 작성하라."},
        {"type": "text", "text": "ModelSpec 발췌 (m 단위; source 가 ssot: 이면 판독 확정값, default 는 참조 차용 — 도면으로 확인할 것):\n"
                                 + json.dumps(ex, ensure_ascii=False)},
    ]
    if evidence:
        rows = [f"- [{e['ord']} p{e['page_no']}] {e['item']} = {e.get('value')} {e.get('unit') or ''} ({e.get('status')})" for e in evidence]
        parts.append({"type": "text", "text": "판독값(근거 시트·상태):\n" + "\n".join(rows)})
    for c in crops:
        cap = ", ".join(f"{it['item']} = {it.get('value')}" for it in c["items"][:6])
        parts.append({"type": "text", "text": f"도면 크롭 {c['ord']} p{c['page_no']} — {cap}"})
        parts.append(image_block(Path(c["path"])))
    if prev_code:
        parts.append({"type": "text", "text": "이전 시도 코드:\n```python\n" + prev_code[-12000:] + "\n```"})
    if feedback:
        parts.append({"type": "text", "text": "이전 시도의 실행 오류·채점(고쳐야 할 것):\n" + feedback[-6000:]})
    if request:
        parts.append({"type": "text", "text": "사용자 요청: " + request})
    h = hashlib.sha256(system.encode("utf-8"))
    for p in parts:
        h.update((p["text"] if p["type"] == "text" else "img").encode("utf-8"))
    for c in crops:
        h.update(sha256_file(Path(c["path"])).encode("ascii"))
    return {"system": system, "messages": [{"role": "user", "content": parts}], "digest": h.hexdigest(), "n_images": len(crops)}
