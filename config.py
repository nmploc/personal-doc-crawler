import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_ENV_FILE = Path(__file__).parent / ".env"

# --- API Keys & Models ---
# Tự động đọc tất cả các GEMINI_API_KEY từ file .env để hỗ trợ luân phiên (fallback)
def _load_gemini_keys():
    keys = []
    if _ENV_FILE.exists():
        with open(_ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("GEMINI_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val and val != "your_gemini_api_key_here":
                        keys.append(val)
    # Lấy thêm từ biến môi trường (nếu có)
    env_val = os.getenv("GEMINI_API_KEY", "").strip()
    if env_val and env_val != "your_gemini_api_key_here" and env_val not in keys:
        keys.append(env_val)
    # Trả về danh sách duy nhất, giữ nguyên thứ tự
    return list(dict.fromkeys(keys))

GEMINI_API_KEYS = _load_gemini_keys()
GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")  # gemini-3.5-flash / gemini-2.5-flash / gemini-3.5-pro


# --- PaddleOCR / PP-Structure Settings ---
PADDLE_USE_GPU = os.getenv("PADDLE_USE_GPU", "false").lower() in ("true", "1", "yes")
PADDLE_LANG = os.getenv("PADDLE_LANG", "vi")  # 'vi', 'en', 'ch', etc.

# --- VLM Verification Settings ---
VLM_TIMEOUT_SECONDS = int(os.getenv("VLM_TIMEOUT_SECONDS", "45"))
ENABLE_RAG_METADATA = os.getenv("ENABLE_RAG_METADATA", "true").lower() in ("true", "1", "yes")

# --- CLI paths (đổi nếu không nằm trong PATH) ---
MARKITDOWN_CMD = os.getenv("MARKITDOWN_CMD", "markitdown")
DOCLING_CMD = os.getenv("DOCLING_CMD", "docling")

# --- Output ---
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")
ATTACHMENT_SUBDIR = "images"  # ảnh trích xuất lưu trong output/{filename}/images

# --- Giới hạn song song ---
MAX_CONCURRENCY = {
    "markitdown": 4,  # local CLI, giới hạn theo CPU
    "docling": 2,     # nặng hơn markitdown
    "paddleocr": 2,   # OCR local GPU/CPU
    "gemini": 3,      # rate limit Gemini
    "hybrid": 2,      # pipeline 2-stage
}

# --- Prompts ---
GEMINI_OCR_PROMPT = (
    "Bạn là chuyên gia Document OCR & Parsing. Hãy trích xuất TOÀN BỘ nội dung văn bản trong ảnh/tài liệu này "
    "và trả về dưới dạng Markdown sạch, giữ đúng cấu trúc: tiêu đề dùng #/##/###, "
    "bảng biểu dùng cú pháp bảng Markdown chuẩn, công thức toán dùng LaTeX ($...$ hoặc $$...$$). "
    "Không thêm lời giải thích hay bình luận, chỉ trả về nội dung Markdown."
)


VLM_REFINE_PROMPT = (
    "Bạn là chuyên gia kiểm định và hiệu đính văn bản tài liệu (Document Verifier & Editor). "
    "Dưới đây là: (1) Ảnh gốc của tài liệu, và (2) Bản nháp Markdown được tạo từ công cụ OCR thô.\n\n"
    "NHIỆM VỤ CỦA BẠN:\n"
    "1. Đối chiếu kỹ lưỡng từng đoạn trong Bản nháp Markdown với Ảnh gốc.\n"
    "2. Sửa toàn bộ lỗi chính tả, nhận diện sai ký tự (đặc biệt là dấu tiếng Việt, số liệu, đơn vị đo).\n"
    "3. Khôi phục cấu trúc bảng biểu nếu bản nháp bị vỡ hàng/cột, đảm bảo cú pháp chuẩn Markdown Table (| col1 | col2 |).\n"
    "4. Chuẩn hóa công thức toán học/hóa học sang định dạng LaTeX ($...$ cho inline, $$...$$ cho block).\n"
    "5. Giữ nguyên toàn bộ nội dung trung thực với ảnh gốc, KHÔNG tự ý tóm tắt, cắt xén hoặc thêm nội dung không có trong ảnh.\n"
    "6. Chỉ trả về duy nhất nội dung Markdown hoàn chỉnh đã được hiệu đính (không kèm lời chào hay giải thích)."
)

