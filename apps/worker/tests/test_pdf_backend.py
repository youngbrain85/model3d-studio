"""PDF 백엔드 스모크 — 파이프라인 [2] 의 전제가 실제로 동작하는지.

**왜 PyMuPDF 가 아닌 pypdfium2 인가**: PyMuPDF 는 AGPL-3.0 / Artifex 상용 듀얼
라이선스다. 도면 PDF 래스터화를 서버에서 수행하는 SaaS 는 AGPL 의 네트워크 배포
조항에 걸릴 수 있다. pypdfium2 는 BSD-3-Clause / Apache-2.0 이라 제약이 없고,
아키텍처 §3 의 "라이선스 프리 원칙"에도 맞는다.

임포트만 확인하는 것은 검증이 아니다 — 실제 PDF 를 래스터화하고 텍스트를 뽑는다.
"""

from __future__ import annotations

import pypdfium2 as pdfium

#: 텍스트 한 줄이 든 최소 PDF. 표제란 판독(파이프라인 [3])의 축소판이다.
_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 100]"
    b"/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>endobj\n"
    b"4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"5 0 obj<</Length 52>>stream\n"
    b"BT /F1 18 Tf 20 40 Td (AB1-S-021) Tj ET\n"
    b"endstream endobj\n"
    b"trailer<</Root 1 0 R>>\n"
)


def test_pdf_rasterizes_at_requested_scale() -> None:
    """시트별 고해상 PNG 생성(파이프라인 [2])의 전제."""
    page = pdfium.PdfDocument(_MINIMAL_PDF)[0]
    img = page.render(scale=2).to_pil()
    assert img.size == (400, 200), "MediaBox 200×100 을 scale=2 로 렌더하면 400×200"
    assert img.mode == "RGB"


def test_pdf_text_extraction() -> None:
    """sheet_text 추출(파이프라인 [2])과 표제란 대조(§3)의 전제."""
    page = pdfium.PdfDocument(_MINIMAL_PDF)[0]
    assert "AB1-S-021" in page.get_textpage().get_text_range()


def test_page_size_is_available_for_view_contract() -> None:
    """뷰 계약의 pixel_frame 은 페이지 크기를 알아야 만들 수 있다 (규칙 §7)."""
    page = pdfium.PdfDocument(_MINIMAL_PDF)[0]
    width, height = page.get_size()
    assert (round(width), round(height)) == (200, 100)
