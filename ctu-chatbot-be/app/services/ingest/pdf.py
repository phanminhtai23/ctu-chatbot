"""Đọc PDF và render trang thành ảnh JPEG (pypdfium2: có bản dựng sẵn cho Windows/Linux/ARM, không cần cài poppler)."""

import io
from pathlib import Path

VIEWER_DPI = 110  # ảnh hiện cho người dùng xem (nhẹ)
VIEWER_QUALITY = 70
OCR_DPI = 150  # ảnh đưa cho Gemini đọc chữ (rõ hơn)
OCR_QUALITY = 80


class PdfError(Exception):
    """File không phải PDF dùng được (hỏng, có mật khẩu, quá lớn...)."""


def check_pdf_bytes(data: bytes, max_mb: int) -> None:
    if not data.startswith(b"%PDF-"):
        raise PdfError("File không phải PDF (thiếu dấu hiệu %PDF)")
    if len(data) > max_mb * 1024 * 1024:
        raise PdfError(f"File lớn hơn {max_mb} MB")


def page_count(path: Path) -> int:
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(str(path))
    except Exception as exc:  # noqa: BLE001 - pypdfium2 ném PdfiumError (hỏng/có mật khẩu)
        raise PdfError(f"Không mở được PDF: {exc}") from exc
    try:
        return len(pdf)
    finally:
        pdf.close()


def render_pages(path: Path, pages: list[int], dpi: int, quality: int) -> dict[int, bytes]:
    """Render các trang (đánh số từ 1) ra JPEG. Trả về {số trang: bytes}."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    out: dict[int, bytes] = {}
    try:
        for number in pages:
            image = pdf[number - 1].render(scale=dpi / 72).to_pil().convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=quality)
            out[number] = buffer.getvalue()
    finally:
        pdf.close()
    return out


def jpeg_size(data: bytes) -> tuple[int, int]:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        return image.size
