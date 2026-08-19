import logging
from pathlib import Path
from typing import Union, Tuple
from config import GEMINI_API_KEY
from backends.gemini_vision_backend import refine_with_gemini

logger = logging.getLogger(__name__)

def verify_and_refine(
    image_input: Union[Path, bytes],
    draft_markdown: str,
    *args,
    **kwargs
) -> Tuple[str, str]:
    """
    Sử dụng Gemini 3.5 Flash để đối chiếu, kiểm tra cú pháp và hiệu đính OCR.
    Trả về: (markdown_hoan_chinh, thong_tin_verifiers)
    """
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY chưa được cấu hình.")
        return draft_markdown, "stage1-draft (gemini-failed: NO_API_KEY)"

    try:
        res = refine_with_gemini(image_input, draft_markdown)
        return res, "gemini-3.5-flash"
    except Exception as e:
        logger.error("Gemini 3.5 Flash gặp sự cố: %s", e)
        return draft_markdown, f"stage1-draft (gemini-failed: {e})"
