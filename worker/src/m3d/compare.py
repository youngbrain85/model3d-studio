"""지각 해시 회귀 대조 (설계서 §8-2).

신규 렌더 61장이 원 프로젝트 산출 PNG 61장과 지각적으로 같은지 잰다.
dHash: 그레이스케일 → (size+1)×size 축소 → 인접 픽셀 밝기 비교 비트열.
해밍 거리 0 = 지각 동일. 임계값은 Task 6 에서 실측으로 확정한다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None  # 8000px 렌더 (원 파이프라인 계승)

HASH_SIZE = 16  # 16×16 = 256비트


def dhash(image: Image.Image, size: int = HASH_SIZE) -> int:
    gray = image.convert("L").resize((size + 1, size), Image.LANCZOS)
    arr = np.asarray(gray, dtype=np.int16)
    bits = arr[:, 1:] > arr[:, :-1]
    value = 0
    for bit in bits.flatten():
        value = (value << 1) | int(bit)
    return value


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def compare_files(path_a: Path, path_b: Path) -> int:
    with Image.open(path_a) as ia, Image.open(path_b) as ib:
        return hamming(dhash(ia), dhash(ib))
