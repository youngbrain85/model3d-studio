"""에이전트 입력 묶음 (M5 D3) — 규칙(KB §1·§2·§5)·툴킷 문서·ctx·코드 계약·스펙 발췌(출처)·크롭·판독값·피드백·요청."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

from m3d.agent import sections_meta
from m3d.config import REPO_ROOT
from m3d.model import geom
from m3d.model.spec import ModelSpec
from m3d.reading.inputs import image_block
from m3d.samples.manifest import sha256_file

KB_PATH = REPO_ROOT / "docs" / "모델링규칙_지식베이스_v0.md"
KB_KEEP = ("## 1. ", "## 2. ", "## 5. ")
TOOLKIT_FUNCS = ("loft", "extrude", "rect", "box_prism", "mirror_poly", "mirror_mesh", "paint", "zone_loft")
COMMON_SPEC_KEYS = ("coord", "box")
DEFAULT_SPEC_KEYS = ("diaphragm", "bearing")

ROLE = ("당신은 강상자형교 3D 모델링 에이전트다. 주어진 치수 정본(ModelSpec 발췌)·도면 크롭·규칙만으로 한 섹션(부재 그룹)의 "
        "파이썬 빌더 함수를 작성한다. 추정으로 확정하지 말고 가정은 assumptions 에, 확인이 필요한 것은 questions 에 낸다.")

CTX_DOC = """## ctx (본체 기하 — 주어진 조건, 전 섹션 공통)
- ctx.x_web: 웹 외면 x(m, +측). 웹은 x=±x_web 에 있고 두께 ctx.t_web(z) 만큼 안쪽으로 들어온다 → 웹 내면 x = ±(x_web − t_web(z)); 내공 판은 그 내면에 INS 만큼 물린다(반폭 = x_web − t_web(z) + INS).
- ctx.z_p4, ctx.z_p5, ctx.span: P4·P5 받침선 z(m)와 경간 길이. 격벽·프레임·가로보 같은 반복 부재의 위치는 전역 체인 z = z_p4 + k·간격 에서 유도한다.
- ctx.y_web_top(z), ctx.y_web_bot(z): 강상판 하면 y / 하판 상면 y (내공 경계, m). ctx.h_box(z) = 내공 높이.
- ctx.y_deck_top(z): 강상판 상면 y — 슬래브·상면 이음판이 여기에 얹힌다. ctx.y_bot_out(z): 하판 하면 y — 받침·하면 이음판이 여기에 붙는다.
- ctx.y_crown(z): 슬래브 crown 상면 y. ctx.el_road(z): 도로 계획고 EL(모델 y 가 아니다 — 모델 y = EL − y_datum).
- ctx.t_top(z), ctx.t_bot(z), ctx.t_web(z): 상판·하판·웹 판두께(m).
- ctx.zone_loft(z0, z1, poly_fn): 판두께 전이점에서 분절해 로프트한다(전이 계단면은 구간 캡). 종리브·수평보강재처럼 z 로 긴 부재는 loft 대신 이것을 쓴다. poly_fn(z) 는 그 z 의 단면 Poly 를 돌려준다.
- ctx.COL_STEEL / ctx.COL_CONC / ctx.COL_BRG / ctx.COL_SOLE: 강재·콘크리트·받침·솔플레이트 색 [r,g,b,a]. ctx.INS: 접합부 관통 삽입 5mm.
- ctx.geom: 아래 툴킷 모듈(직접 import 해도 된다: from m3d.model.geom import ...)."""

CODE_CONTRACT = """## 코드 계약
- 최상위에 `def build_section(spec, ctx) -> dict[str, trimesh.Trimesh]` 를 정의한다. spec 은 ModelSpec 전체 dict(m 단위), ctx 는 위 본체 기하.
- 노드명은 아래 '이 섹션의 노드' 목록과 **정확히** 같아야 한다(빠짐·추가 모두 채점 실패). 노드명 = 객체 DB 연결 키.
- 모든 메시는 수밀(loft/extrude/box_prism 결과)이고 `geom.paint(mesh, ctx.COL_STEEL)` 로 색을 입힌다. 접합부는 ctx.INS 만큼 관통 삽입한다(공면 금지).
- 허용 import: math, numpy, trimesh, m3d.model.geom. 파일·네트워크·다른 모듈 접근 금지. 단위 m, Y-up, 좌표계는 §1 규약.
- 코드 인자 spec 에는 **값만** 들어 있다: spec["diaphragm"]["spacing"] == 2.8 (float), spec["diaphragm"]["h_table"] == [[2.8, 3.739], ...].
  아래 'ModelSpec 발췌' 의 {"value", "source", "doc"} 포장은 출처·의미 표시용이며 코드에서는 ["value"] 로 접근하지 않는다. doc 의 [x]·[y]·[z] 는 그 성분이 뻗는 축이다.
- 반복 판(격벽 등)은 두께 중심을 전역 체인 위치 z = z_p4 + k·간격 에 두고 판면은 두께의 절반(±t/2)만 z 로 뻗는다.
  INS 관통 삽입은 상·하판·웹과 만나는 y·x 방향 접합에만 쓴다(z 로 판 두께를 키우지 않는다). 검증기는 체인 위치 ±10mm 안에 판면 정점이 있는지 본다.
- 보강재·부속은 판 자체와 별도 솔리드로 만들어 같은 노드에 합친다(trimesh.util.concatenate). 두께 t 는 판면 안 방향, 돌출 w 는 판면 법선 방향이다.
- ctx 프로파일(y_deck_top·y_web_top·y_bot_out·y_crown·t_top…)은 **z 에 따라 변한다**(종단경사·변단면). z 로 뻗는 부재는 한 z 의 값을 상수로 쓰지 말고 양 끝 z 에서 각각 단면을 계산해 loft(또는 ctx.zone_loft)로 잇는다 — 그러지 않으면 노드 bbox 가 정답보다 납작해진다.
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


def _field_doc(sec: str, key: str) -> str | None:
    """ModelSpec 하위 모델의 Field description — 프롬프트 발췌의 doc(M6 D1)."""
    sub = ModelSpec.model_fields[sec].annotation
    f = getattr(sub, "model_fields", {}).get(key)
    return f.description if f is not None else None


def _entry(sec: str, key: str, value, sources: dict) -> dict:
    entry = {"value": value, "source": sources.get(f"{sec}.{key}", "default")}
    doc = _field_doc(sec, key)
    if doc:
        entry["doc"] = doc
    return entry


def spec_keys_for(code: str | None) -> tuple[str, ...]:
    """섹션이 볼 ModelSpec 하위 모델 — 공통(coord·box) + 메타의 spec_keys (M7 3.3)."""
    m = sections_meta.meta(code) if code else None
    return COMMON_SPEC_KEYS + (m.spec_keys if m else DEFAULT_SPEC_KEYS)


def spec_excerpt(spec_dict: dict, sources: dict, code: str | None = None) -> dict:
    return {sec: {k: _entry(sec, k, v, sources) for k, v in spec_dict[sec].items()} for sec in spec_keys_for(code)}


def section_block(code: str, names: list[str]) -> str:
    """계약에 싣는 섹션별 블록 — 노드명 전체와 역할 표(M7 D3). 채점이 노드 집합 일치를 요구한다."""
    m = sections_meta.meta(code)
    lines = [f"## 이 섹션의 노드 ({m.label if m else code}) — 정확히 이 이름들만, 빠짐없이 ({len(names)}개)",
             ", ".join(names)]
    if m and m.roles:
        lines.append("역할: " + " / ".join(f"{pat} → {lab}" for pat, lab in m.roles))
    return "\n".join(lines)

def section_bundle(section_key: str, *, spec_dict: dict, sources: dict, evidence: list[dict], crops: list[dict],
                   feedback: str | None = None, request: str = "", prev_code: str | None = None,
                   critique: list[dict] | None = None, node_list: list[str] | None = None) -> dict:
    segment, code = section_key.split("/")
    kb = kb_excerpt(KB_PATH.read_text(encoding="utf-8")) if KB_PATH.is_file() else ""
    system = "\n\n".join([ROLE, "## 모델링 규칙(지식베이스 발췌)", kb, toolkit_doc(), CTX_DOC, CODE_CONTRACT, OUTPUT_FORMAT])
    ex = spec_excerpt(spec_dict, sources, code)
    parts: list[dict] = [
        {"type": "text", "text": f"섹션 {section_key} (구간 {segment}, 부재그룹 {code}). 이 섹션의 모든 노드를 만드는 build_section 을 작성하라."},
    ]
    if node_list:
        parts.append({"type": "text", "text": section_block(code, node_list)})
    parts += [
        {"type": "text", "text": "ModelSpec 발췌 (m 단위; source 가 ssot: 이면 판독 확정값, default 는 참조 차용 — 도면으로 확인할 것; doc 은 필드 의미; 코드의 spec 인자에는 포장 없이 값만 들어온다: spec['diaphragm']['spacing'] == 2.8, ['value'] 접근 금지):\n"
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
    if critique:
        parts.append({"type": "text", "text": "이전 시도 결과 렌더(자기검토용): 도면 크롭·규칙과 비교해 판면 방향·보강재 돌출 방향과 크기·개구 위치를 "
                                              "스스로 확인하고 고쳐라. 정답 렌더가 아니라 방금 만든 결과다."})
        for c in critique:
            parts.append({"type": "text", "text": "렌더: " + c["caption"]})
            parts.append(image_block(Path(c["path"])))
    if request:
        parts.append({"type": "text", "text": "사용자 요청: " + request})
    h = hashlib.sha256(system.encode("utf-8"))
    for p in parts:
        h.update((p["text"] if p["type"] == "text" else "img").encode("utf-8"))
    for c in crops:
        h.update(sha256_file(Path(c["path"])).encode("ascii"))
    for c in (critique or []):
        h.update(sha256_file(Path(c["path"])).encode("ascii"))
    h.update(",".join(node_list or []).encode("utf-8"))
    return {"system": system, "messages": [{"role": "user", "content": parts}], "digest": h.hexdigest(), "n_images": len(crops) + len(critique or [])}
