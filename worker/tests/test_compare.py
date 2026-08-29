"""dHash 회귀 대조 — 신규 렌더가 기존 PNG 와 지각적으로 같은지 재는 자."""

from PIL import Image, ImageDraw

from m3d.compare import compare_files, dhash, hamming


def _blank(w=400, h=300):
    return Image.new("RGB", (w, h), "white")


def _with_rect(x0, y0, x1, y1, w=400, h=300):
    img = _blank(w, h)
    ImageDraw.Draw(img).rectangle([x0, y0, x1, y1], fill="black")
    return img


def test_identical_images_distance_zero():
    a = _with_rect(50, 50, 200, 150)
    assert hamming(dhash(a), dhash(a.copy())) == 0


def test_tiny_change_small_distance():
    """3px 점 하나 추가 — 지각적으로 같은 시트로 판정돼야 한다."""
    a = _with_rect(50, 50, 200, 150)
    b = a.copy()
    ImageDraw.Draw(b).rectangle([300, 250, 303, 253], fill="black")
    assert hamming(dhash(a), dhash(b)) <= 8


def test_different_layout_large_distance():
    """세로 줄무늬 vs 빈 화면 — 완전히 다른 시트."""
    a = _blank()
    b = _blank()
    d = ImageDraw.Draw(b)
    for x in range(0, 400, 20):
        d.rectangle([x, 0, x + 9, 300], fill="black")
    assert hamming(dhash(a), dhash(b)) >= 64


def test_resolution_invariance():
    """같은 그림의 2배 해상도 — dHash 는 리사이즈 기반이라 저거리여야 한다.

    경계 8 은 실측 기반: 2026-08-29 구현 시 LANCZOS 리샘플 앤티에일리어싱
    차이로 거리 6 이 측정됨 (당초 추정 4 는 과소). tiny_change 경계와 일관.
    """
    a = _with_rect(50, 50, 200, 150, 400, 300)
    b = _with_rect(100, 100, 400, 300, 800, 600)
    assert hamming(dhash(a), dhash(b)) <= 8


def test_compare_files_roundtrip(tmp_path):
    a = _with_rect(50, 50, 200, 150)
    pa = tmp_path / "a.png"
    pb = tmp_path / "b.png"
    a.save(pa)
    a.save(pb)
    assert compare_files(pa, pb) == 0
