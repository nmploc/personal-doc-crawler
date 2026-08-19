import logging
from pathlib import Path
from enum import Enum
from typing import Optional
from hardware_checker import get_system_hardware, HardwareProfile

logger = logging.getLogger(__name__)


class Backend(str, Enum):
    HYBRID = "hybrid"          # Pipeline 2-Stage: PP-Structure/PaddleOCR + Dual-VLM (Qwen + Gemini)
    PADDLEOCR = "paddleocr"    # Local PP-Structure / OCR & Layout parsing
    QWEN = "qwen"              # Direct VLM OCR bằng Qwen2.5-VL
    GEMINI = "gemini"          # Direct VLM OCR bằng Gemini 3.5 Flash
    DOCLING = "docling"        # Local Document layout parsing
    MARKITDOWN = "markitdown"  # Trích xuất nhanh Office & PDF text chuẩn


OFFICE_EXTS = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}
PDF_EXT = ".pdf"


def is_scanned_pdf(path: Path, max_check_pages: int = 3) -> bool:
    """
    Tự động phát hiện xem PDF có phải là bản scan/ảnh chụp không.
    Kiểm tra số lượng ký tự văn bản có thể trích xuất trực tiếp bằng PyMuPDF.
    """
    try:
        import fitz
        doc = fitz.open(str(path))
        total_text_len = 0
        pages_to_check = min(len(doc), max_check_pages)
        for i in range(pages_to_check):
            total_text_len += len(doc[i].get_text().strip())
        doc.close()

        # Nếu trung bình mỗi trang ít hơn 50 ký tự -> coi là PDF dạng scan/ảnh chụp
        return (total_text_len / max(1, pages_to_check)) < 50
    except Exception as e:
        logger.debug("Không thể kiểm tra text layer PDF qua fitz: %s", e)
        return False


def pick_backend(
    path: Path,
    mode: str = "hybrid",
    force: Optional[Backend] = None,
    pdf_is_scanned: bool = False,
) -> Backend:
    """
    Định tuyến backend thông minh dựa trên định dạng, đặc tính tài liệu, chế độ (mode)
    và cấu hình phần cứng thực tế của máy tính.
    """
    if force:
        return force

    ext = path.suffix.lower()
    mode = (mode or "hybrid").lower()
    hw: HardwareProfile = get_system_hardware()

    # Định dạng Office -> luôn tối ưu nhất qua MarkItDown
    if ext in OFFICE_EXTS:
        return Backend.MARKITDOWN

    # Định dạng Hình ảnh
    if ext in IMAGE_EXTS:
        # Nếu cấu hình máy tính quá yếu -> bắt buộc dùng Online VLM
        if not hw.is_capable_for_local_ocr or mode == "vlm":
            return Backend.GEMINI
        if mode == "fast":
            return Backend.PADDLEOCR
        return Backend.HYBRID

    # Định dạng PDF
    if ext == PDF_EXT:
        scanned = pdf_is_scanned or is_scanned_pdf(path)

        # Nếu máy yếu -> không chạy OCR cục bộ nặng
        if not hw.is_capable_for_local_ocr:
            return Backend.MARKITDOWN if not scanned else Backend.GEMINI

        if mode == "fast":
            return Backend.DOCLING if scanned else Backend.MARKITDOWN
        if mode == "vlm":
            return Backend.GEMINI
        if mode == "hybrid":
            return Backend.HYBRID

        # mode == "auto"
        if scanned:
            return Backend.HYBRID
        return Backend.MARKITDOWN

    raise ValueError(f"Không có backend mặc định cho định dạng tệp: {ext}")
