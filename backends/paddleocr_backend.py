import io
import logging
from pathlib import Path
from typing import List, Tuple, Optional
from config import PADDLE_USE_GPU, PADDLE_LANG
from hardware_checker import get_system_hardware, HardwareProfile

logger = logging.getLogger(__name__)

_pp_structure_engine = None
_paddle_ocr_engine = None
_paddle_available = None


def is_paddle_available() -> bool:
    """Kiểm tra xem thư viện paddleocr và paddlepaddle đã cài đặt hay chưa."""
    global _paddle_available
    if _paddle_available is None:
        try:
            import paddleocr  # noqa: F401
            _paddle_available = True
        except ImportError:
            _paddle_available = False
    return _paddle_available


def _get_pp_structure_engine():
    """
    Khởi tạo engine PP-Structure (phân tích bố cục, bảng biểu, công thức) 
    dựa trên cấu hình phần cứng tự động phát hiện.
    """
    global _pp_structure_engine
    if _pp_structure_engine is None:
        if not is_paddle_available():
            raise RuntimeError(
                "Thư viện 'paddleocr' chưa được cài đặt. "
                "Cài đặt: pip install paddlepaddle paddleocr"
            )

        hw: HardwareProfile = get_system_hardware()
        use_gpu = PADDLE_USE_GPU or (hw.has_cuda and hw.recommended_mode == "gpu")
        
        try:
            from paddleocr import PPStructure
            _pp_structure_engine = PPStructure(
                table=True,
                ocr=True,
                show_log=False,
                lang=PADDLE_LANG,
                use_gpu=use_gpu,
                enable_mkldnn=hw.enable_mkldnn if not use_gpu else False,
                cpu_threads=hw.recommended_threads if not use_gpu else 1,
            )
            logger.info("PP-Structure đã khởi tạo thành công (GPU=%s, Threads=%s)", use_gpu, hw.recommended_threads)
        except Exception as e:
            logger.warning("Không thể khởi tạo PP-Structure, chuyển sang PaddleOCR tiêu chuẩn: %s", e)
            _pp_structure_engine = _get_standard_ocr_engine()

    return _pp_structure_engine


def _get_standard_ocr_engine():
    """Khởi tạo engine PaddleOCR tiêu chuẩn khi không cần phân tích sâu cấu trúc bảng."""
    global _paddle_ocr_engine
    if _paddle_ocr_engine is None:
        from paddleocr import PaddleOCR
        hw: HardwareProfile = get_system_hardware()
        use_gpu = PADDLE_USE_GPU or (hw.has_cuda and hw.recommended_mode == "gpu")

        _paddle_ocr_engine = PaddleOCR(
            use_angle_cls=True,
            lang=PADDLE_LANG,
            use_gpu=use_gpu,
            enable_mkldnn=hw.enable_mkldnn if not use_gpu else False,
            cpu_threads=hw.recommended_threads if not use_gpu else 1,
            show_log=False,
        )
    return _paddle_ocr_engine


def render_pdf_to_images(pdf_path: Path, dpi: int = 200) -> List[Tuple[int, bytes]]:
    """
    Chuyển đổi các trang PDF thành danh sách ảnh PNG dạng bytes chất lượng cao bằng PyMuPDF.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("Cần cài đặt thư viện 'pymupdf' để trích xuất trang PDF: pip install pymupdf")

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
    """Đọc ảnh đơn lẻ và đóng gói thành [(1, bytes)]."""
    return [(1, image_path.read_bytes())]


def _html_table_to_markdown(html: str) -> str:
    """Chuyển đổi HTML Table từ PP-Structure sang Markdown Table."""
    try:
        import re
        # Loại bỏ các tag thừa
        html = html.replace("<html>", "").replace("</html>", "").replace("<body>", "").replace("</body>", "").strip()
        rows = re.findall(r"<tr>(.*?)</tr>", html, flags=re.DOTALL)
        if not rows:
            return html

        md_rows = []
        for r_idx, row in enumerate(rows):
            cols = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.DOTALL)
            clean_cols = [re.sub(r"<[^>]+>", "", c).strip() for c in cols]
            if clean_cols:
                md_rows.append("| " + " | ".join(clean_cols) + " |")
                if r_idx == 0:
                    md_rows.append("| " + " | ".join(["---"] * len(clean_cols)) + " |")

        return "\n".join(md_rows)
    except Exception:
        return html


def structure_single_image(image_bytes: bytes) -> str:
    """
    Phân tích bố cục, trích xuất bảng biểu và văn bản bằng PP-Structure / PaddleOCR.
    """
    from PIL import Image
    import numpy as np

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img_np = np.array(img)

    engine = _get_pp_structure_engine()

    # Kiểm tra nếu là PPStructure engine
    if hasattr(engine, "__call__") and type(engine).__name__ == "PPStructure":
        try:
            result = engine(img_np)
            markdown_blocks = []
            for region in result:
                r_type = region.get("type", "").lower()
                r_res = region.get("res", "")

                if r_type == "table":
                    # Bảng biểu
                    html_table = r_res.get("html", "") if isinstance(r_res, dict) else str(r_res)
                    md_table = _html_table_to_markdown(html_table)
                    markdown_blocks.append(f"\n{md_table}\n")
                elif r_type in ("title", "header"):
                    # Tiêu đề
                    text = " ".join([line["text"] for line in r_res]) if isinstance(r_res, list) else str(r_res)
                    markdown_blocks.append(f"\n## {text}\n")
                elif r_type in ("figure", "image"):
                    markdown_blocks.append("\n<!-- Figure / Image Block -->\n")
                else:
                    # Văn bản thông thường
                    if isinstance(r_res, list):
                        lines = [line.get("text", "") for line in r_res if isinstance(line, dict)]
                        if lines:
                            markdown_blocks.append("\n".join(lines))
                    elif isinstance(r_res, str):
                        markdown_blocks.append(r_res)

            return "\n\n".join(markdown_blocks).strip()
        except Exception as e:
            logger.warning("PPStructure phân tích thất bại, fallback sang PaddleOCR: %s", e)

    # Fallback sang PaddleOCR tiêu chuẩn
    std_engine = _get_standard_ocr_engine()
    result = std_engine.ocr(img_np, cls=True)
    if not result or not result[0]:
        return ""

    page_data = result[0]
    page_data_sorted = sorted(page_data, key=lambda item: (item[0][0][1], item[0][0][0]))
    lines = [line[1][0] for line in page_data_sorted if line[1][1] >= 0.4]
    return "\n\n".join(lines)


def parse_with_paddleocr(input_path: Path) -> Tuple[str, List[Tuple[int, bytes]]]:
    """
    Stage 1 Parser bằng PP-Structure / PaddleOCR:
    1. Tự động kiểm tra phần cứng. Nếu máy quá yếu -> bỏ qua OCR cục bộ, trả về draft rỗng để chuyển thẳng sang Online VLM.
    2. Nếu cấu hình đủ mạnh & có cài PaddleOCR -> Thực hiện bóc tách bố cục và bảng biểu.
    3. Trả về: (draft_markdown, list_of_page_images).
    """
    hw: HardwareProfile = get_system_hardware()
    ext = input_path.suffix.lower()
    page_images: List[Tuple[int, bytes]] = []

    # 1. Trích xuất danh sách ảnh trang tài liệu
    if ext == ".pdf":
        page_images = render_pdf_to_images(input_path)
    else:
        page_images = load_image_bytes(input_path)

    if not page_images:
        raise RuntimeError(f"Không thể trích xuất trang nào từ file: {input_path}")

    # 2. Kiểm tra năng lực phần cứng
    if not hw.is_capable_for_local_ocr:
        logger.warning(
            "[BỎ QUA STAGE 1 LOCAL] Cấu hình máy tính quá yếu: %s. Chuyển thẳng sang Online VLM.",
            hw.warning_reason,
        )
        return (
            f"<!-- [STAGE 1 SKIPPED] Cấu hình máy tính yếu: {hw.warning_reason}. Tự động định tuyến sang Online VLM -->",
            page_images,
        )

    # 3. Thực hiện bóc tách bằng PP-Structure / PaddleOCR nếu đã cài đặt
    if is_paddle_available():
        draft_pages = []
        for page_num, img_bytes in page_images:
            page_text = structure_single_image(img_bytes)
            if len(page_images) > 1:
                draft_pages.append(f"<!-- Page {page_num} -->\n{page_text}")
            else:
                draft_pages.append(page_text)
        draft_markdown = "\n\n---\n\n".join(draft_pages)
        return draft_markdown, page_images

    # 4. Fallback nếu là PDF và chưa cài PaddleOCR: dùng text layer trích xuất qua PyMuPDF
    if ext == ".pdf":
        import fitz
        doc = fitz.open(str(input_path))
        extracted_pages = []
        for i, page in enumerate(doc):
            t = page.get_text()
            extracted_pages.append(f"<!-- Page {i+1} -->\n{t}" if len(doc) > 1 else t)
        doc.close()
        return "\n\n---\n\n".join(extracted_pages), page_images

    return "<!-- (Stage 1 Draft: Chưa cài đặt PaddleOCR cục bộ - chuyển tiếp sang Stage 2 VLM) -->", page_images
