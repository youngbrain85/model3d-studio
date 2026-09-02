"""LLM 입력 조립 (설계서 §4-1·§10 리스크).

원 교훈: 판독의 기준 소스는 sheet_text(무손실 텍스트)이고, 이미지는 배치·형상
확인용이다. 8000px 원본은 비전 한도를 넘으므로 리사이즈하되, 표제란은 별도 타일로
잘라 글자 크기를 지킨다.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from PIL import Image

Image.MAX_IMAGE_PIXELS = None

VISION_LONG_SIDE = 1568          # Anthropic 비전 권장 상한
TITLEBLOCK_FRAC = (0.62, 0.78)   # 우하단 표제란 대략 영역 (x, y 시작 비율)


def resize_for_vision(png: Path, out: Path, long_side: int = VISION_LONG_SIDE) -> tuple[int, int]:
    """긴 변을 long_side 로 축소. 이미 작으면 그대로 복사한다(업스케일 금지)."""
    with Image.open(png) as im:
        out.parent.mkdir(parents=True, exist_ok=True)   # 두 분기 공통 — 작은 이미지도 필요
        w, h = im.size
        if max(w, h) <= long_side:
            im.convert("RGB").save(out)
            return w, h
        scale = long_side / max(w, h)
        nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
        im.convert("RGB").resize((nw, nh), Image.LANCZOS).save(out)
        return nw, nh


def tile_titleblock(png: Path, out: Path) -> None:
    """우하단 표제란 타일 — 도면번호·제목·척도가 작게 적혀 있다.

    원본 픽셀 그대로 자른다. 긴 변이 API 비전 상한을 넘으면 서버 측에서 축소되지만,
    표제란 글자는 여백이 커서 축소 후에도 판독 가능하다. 좌표 정밀도가 필요한 값은
    이미지가 아니라 sheet_text 가 담당한다.
    """
    with Image.open(png) as im:
        w, h = im.size
        box = (int(w * TITLEBLOCK_FRAC[0]), int(h * TITLEBLOCK_FRAC[1]), w, h)
        out.parent.mkdir(parents=True, exist_ok=True)
        im.crop(box).convert("RGB").save(out)


def image_block(png: Path) -> dict:
    """Anthropic 비전 content block."""
    data = base64.b64encode(png.read_bytes()).decode("ascii")
    return {"type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": data}}


def sheet_text_excerpt(json_path: Path, max_rows: int = 1200) -> dict:
    """sheet_text 를 컨텍스트에 맞게 자른다.

    자를 때는 글자 높이 내림차순으로 남긴다 — 제목·치수 같은 큰 글자가 먼저 살고
    잔글씨가 먼저 버려진다. 자른 사실과 전체 개수를 함께 실어 LLM 이 알게 한다.
    """
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    texts = payload.get("texts", [])
    total = len(texts)
    truncated = total > max_rows
    if truncated:
        texts = sorted(texts, key=lambda t: -t.get("h_mm", 0.0))[:max_rows]
        texts = sorted(texts, key=lambda t: (-t["y_mm"], t["x_mm"]))
    return {
        "drawing_no": payload.get("drawing_no"),
        "page_no": payload.get("page_no"),
        "paper_mm": payload.get("paper_mm"),
        "scale": payload.get("scale"),
        "fallback": payload.get("fallback", False),
        "total_texts": total,
        "truncated": truncated,
        "texts": texts,
    }
