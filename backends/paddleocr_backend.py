import io
import logging
from pathlib import Path
from typing import List, Tuple
from config import PADDLE_USE_GPU, PADDLE_LANG

logger = logging.getLogger(__name__)

_paddle_ocr_engine = None
_paddle_available = None


def is_paddle_available() -> bool:
    """Kiểm tra xem thư viện paddleocr đã được cài đặt trong môi trường hay chưa."""
    global _paddle_available
    if _paddle_available is None:
        try:
            import paddleocr  # noqa: F401
            _paddle_available = True
        except ImportError:
            _paddle_available = False
    return _paddle_available


def _get_paddle_engine():
    """Khởi tạo engine PaddleOCR (lazy singleton)."""
    global _paddle_ocr_engine
    if _paddle_ocr_engine is None:
        if not is_paddle_available():
            raise RuntimeError(
                "Thư viện 'paddleocr' chưa được cài đặt. "
                "Để sử dụng Stage 1 PaddleOCR, hãy cài: pip install paddlepaddle paddleocr"
            )
        from paddleocr import PaddleOCR
        _paddle_ocr_engine = PaddleOCR(
            use_angle_cls=True,
            lang=PADDLE_LANG,
            use_gpu=PADDLE_USE_GPU,
            show_log=False,
        )
    return _paddle_ocr_engine


def render_pdf_to_images(pdf_path: Path, dpi: int = 200) -> List[Tuple[int, bytes]]:
    """
    Chuyển đổi các trang PDF thành danh sách ảnh PNG dạng bytes.
    Sử dụng PyMuPDF (fitz) - nhanh, nhẹ và chất lượng cao.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("Cần cài đặt thư viện 'pymupdf' để trích xuất ảnh từ PDF: pip install pymupdf")

    images = []
    doc = fitz.open(str(pdf_path))
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    for page_index in range(len(doc)):
        page = doc.load_page(page_index)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        img_bytes = pix.tobytes(output="png")
        images.append((page_index + 1, img_bytes))

    doc.close()
    return images


def load_image_bytes(image_path: Path) -> List[Tuple[int, bytes]]:
    """Đọc ảnh đơn lẻ và đóng gói thành list dạng [(1, bytes)]."""
    return [(1, image_path.read_bytes())]


def ocr_single_image_bytes(image_bytes: bytes) -> str:
    """Thực hiện OCR trên 1 ảnh bytes bằng PaddleOCR."""
    from PIL import Image
    import numpy as np

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img_np = np.array(img)

    engine = _get_paddle_engine()
    result = engine.ocr(img_np, cls=True)

    if not result or not result[0]:
        return ""

    # Sắp xếp các đoạn text theo thứ tự đọc (y trước, x sau)
    lines = []
    page_data = result[0]
    # Sắp xếp theo trục Y (top) với độ lệch dung sai
    page_data_sorted = sorted(page_data, key=lambda item: (item[0][0][1], item[0][0][0]))

    for line in page_data_sorted:
        text, score = line[1]
        if score >= 0.4:  # Ngưỡng tin cậy cơ bản
            lines.append(text)

    return "\n\n".join(lines)


def parse_with_paddleocr(input_path: Path) -> Tuple[str, List[Tuple[int, bytes]]]:
    """
    Stage 1 Parser bằng PaddleOCR:
    1. Trích xuất danh sách ảnh trang (cho cả ảnh đơn và file PDF đa trang).
    2. Chạy OCR từng trang và tổng hợp thành Draft Markdown.
    3. Trả về tuple: (draft_markdown, list_of_page_images).
    """
    ext = input_path.suffix.lower()
    page_images: List[Tuple[int, bytes]] = []

    if ext == ".pdf":
        page_images = render_pdf_to_images(input_path)
    else:
        page_images = load_image_bytes(input_path)

    if not page_images:
        raise RuntimeError(f"Không thể trích xuất trang nào từ file: {input_path}")

    # Nếu có PaddleOCR -> OCR từng trang
    if is_paddle_available():
        draft_pages = []
        for page_num, img_bytes in page_images:
            page_text = ocr_single_image_bytes(img_bytes)
            if len(page_images) > 1:
                draft_pages.append(f"<!-- Page {page_num} -->\n{page_text}")
            else:
                draft_pages.append(page_text)
        draft_markdown = "\n\n---\n\n".join(draft_pages)
        return draft_markdown, page_images

    # Fallback nhẹ: nếu chưa có paddleocr nhưng là PDF, thử trích xuất text có sẵn qua PyMuPDF
    if ext == ".pdf":
        import fitz
        doc = fitz.open(str(input_path))
        extracted_pages = []
        for i, page in enumerate(doc):
            t = page.get_text()
            extracted_pages.append(f"<!-- Page {i+1} -->\n{t}" if len(doc) > 1 else t)
        doc.close()
        return "\n\n---\n\n".join(extracted_pages), page_images

    # Nếu là ảnh mà chưa cài paddleocr
    return "(Bản nháp OCR rỗng - Chưa cài đặt PaddleOCR local)", page_images
