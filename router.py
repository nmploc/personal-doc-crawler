import logging
import zipfile
from pathlib import Path
from enum import Enum
from typing import Optional, Tuple
from hardware_checker import get_system_hardware, HardwareProfile

logger = logging.getLogger(__name__)


class Backend(str, Enum):
    HYBRID = "hybrid"          # Pipeline 2-Stage: PP-Structure/PaddleOCR + Gemini
    PADDLEOCR = "paddleocr"    # Local PP-Structure / OCR & Layout parsing
    GEMINI = "gemini"          # Direct VLM OCR bằng Gemini 3.5 Flash
    DOCLING = "docling"        # Local Document layout parsing
    MARKITDOWN = "markitdown"  # Trích xuất nhanh Office & PDF text chuẩn


OFFICE_EXTS = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}
PDF_EXT = ".pdf"


def analyze_pdf_complexity(path: Path, max_check_pages: int = 5) -> Tuple[bool, bool]:
    """
    Phân tích độ phức tạp của PDF. Trả về (is_scanned, is_image_heavy).
    - is_scanned: Text layer cực mỏng (< 50 ký tự/trang)
    - is_image_heavy: Có quá nhiều hình ảnh nhúng, cần OCR
    """
    try:
        import fitz
        doc = fitz.open(str(path))
        total_text_len = 0
        total_images = 0
        pages_to_check = min(len(doc), max_check_pages)
        
        if pages_to_check == 0:
            doc.close()
            return False, False

        for i in range(pages_to_check):
            page = doc[i]
            total_text_len += len(page.get_text().strip())
            total_images += len(page.get_images(full=True))
            
        doc.close()

        avg_text = total_text_len / pages_to_check
        avg_images = total_images / pages_to_check
        
        is_scanned = avg_text < 50
        is_image_heavy = avg_images >= 2.0  # Trung bình từ 2 ảnh/trang trở lên
        
        return is_scanned, is_image_heavy
    except Exception as e:
        logger.debug("Lỗi khi kiểm tra PDF bằng fitz: %s", e)
        return False, False


def analyze_pptx_images(path: Path) -> bool:
    """
    Đếm số lượng file trong ppt/media/ (hình ảnh/video) để xem PPTX có nặng về hình ảnh không.
    Trả về True nếu chứa nhiều hơn 5 media files.
    """
    try:
        if not path.suffix.lower() == ".pptx":
            return False
            
        with zipfile.ZipFile(str(path), 'r') as z:
            media_files = [f for f in z.namelist() if f.startswith("ppt/media/")]
            return len(media_files) >= 5
    except Exception as e:
        logger.debug("Lỗi khi phân tích zip PPTX: %s", e)
        return False


def pick_backend(
    path: Path,
    mode: str = "hybrid",
    force: Optional[Backend] = None,
    pdf_is_scanned: bool = False,
) -> Backend:
    """
    Định tuyến backend thông minh dựa trên định dạng, đặc tính tài liệu, chế độ (mode)
    và cấu hình phần cứng.
    """
    if force:
        return force

    ext = path.suffix.lower()
    mode = (mode or "hybrid").lower()
    hw: HardwareProfile = get_system_hardware()

    # 1. HÌNH ẢNH -> Luôn dùng OCR
    if ext in IMAGE_EXTS:
        if not hw.is_capable_for_local_ocr or mode == "vlm":
            return Backend.GEMINI
        if mode == "fast":
            return Backend.PADDLEOCR
        return Backend.HYBRID

    # 2. VĂN BẢN ĐƠN GIẢN / EXCEL -> Ưu tiên MarkItDown/Docling, không dùng OCR
    if ext in {".doc", ".docx", ".xls", ".xlsx"}:
        return Backend.DOCLING if mode == "fast" else Backend.MARKITDOWN

    # 3. POWERPOINT -> Tự động kiểm tra mật độ hình ảnh
    if ext in {".ppt", ".pptx"}:
        # Nếu máy đủ mạnh và chế độ không phải fast/vlm, kiểm tra ảnh
        if hw.is_capable_for_local_ocr and mode in ("hybrid", "auto"):
            is_image_heavy = analyze_pptx_images(path)
            if is_image_heavy:
                return Backend.HYBRID
        return Backend.DOCLING if mode == "fast" else Backend.MARKITDOWN

    # 4. PDF -> Phân tích text layer và hình ảnh
    if ext == PDF_EXT:
        is_scanned, is_image_heavy = False, False
        if not pdf_is_scanned:
            is_scanned, is_image_heavy = analyze_pdf_complexity(path)
        else:
            is_scanned = True

        if not hw.is_capable_for_local_ocr:
            return Backend.GEMINI if is_scanned else Backend.MARKITDOWN

        if mode == "fast":
            return Backend.DOCLING if (is_scanned or is_image_heavy) else Backend.MARKITDOWN
            
        if mode == "vlm":
            return Backend.GEMINI

        if mode == "hybrid":
            return Backend.HYBRID

        # mode == "auto": Phân loại tự động thông minh nhất
        if is_scanned or is_image_heavy:
            return Backend.HYBRID
            
        return Backend.MARKITDOWN

    raise ValueError(f"Không có backend mặc định cho định dạng tệp: {ext}")
