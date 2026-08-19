import io
import re
import time
from pathlib import Path
from typing import Union
from google import genai
from google.genai import types
from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_OCR_PROMPT,
    VLM_REFINE_PROMPT,
    VLM_TIMEOUT_SECONDS,
)

_client = None


def _get_client():
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError("Chưa cấu hình GEMINI_API_KEY trong file .env hoặc biến môi trường.")
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


_MIME_MAP = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


def _strip_markdown_fences(text: str) -> str:
    """Loại bỏ ```markdown ... ``` hoặc ``` ... ``` bao ngoài nếu model tự bọc."""
    text = text.strip()
    match = re.match(r"^```(?:markdown)?\s*\n(.*)\n```$", text, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def parse_with_gemini(
    input_path: Path,
    prompt: str = GEMINI_OCR_PROMPT,
    max_retries: int = 5,
) -> str:
    """Gửi ảnh hoặc PDF cho Gemini 3.5 Flash, nhận về Markdown trực tiếp."""
    client = _get_client()
    mime_type = _MIME_MAP.get(input_path.suffix.lower())
    if mime_type is None:
        raise RuntimeError(f"Định dạng {input_path.suffix} chưa hỗ trợ qua Gemini backend.")

    file_bytes = input_path.read_bytes()
    last_err = None

    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                    prompt,
                ],
            )
            if not response.text:
                raise RuntimeError("Gemini trả về nội dung rỗng.")
            return _strip_markdown_fences(response.text)
        except Exception as e:
            last_err = e
            err_str = str(e)

            # Nếu gặp lỗi Rate Limit (429 / RESOURCE_EXHAUSTED)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                match = re.search(r"retry(?:\s*in\s*|Delay:\s*'?)([\d\.]+)", err_str, flags=re.IGNORECASE)
                if match:
                    wait = float(match.group(1)) + 2.0
                else:
                    wait = min(60.0, 15.0 * attempt)
                time.sleep(wait)
            else:
                wait = 2 ** attempt
                time.sleep(wait)

    raise RuntimeError(f"Gemini OCR thất bại sau {max_retries} lần thử: {last_err}")


def refine_with_gemini(
    image_input: Union[Path, bytes],
    draft_markdown: str,
    prompt: str = VLM_REFINE_PROMPT,
    max_retries: int = 3,
) -> str:
    """
    Stage 2 Refiner & Verifier bằng Gemini 3.5 Flash:
    Gửi ảnh trang tài liệu + Draft Markdown từ Stage 1 để đối chiếu, sửa lỗi nhận diện và tối ưu Markdown.
    """
    client = _get_client()

    if isinstance(image_input, (str, Path)):
        p = Path(image_input)
        mime_type = _MIME_MAP.get(p.suffix.lower(), "image/png")
        file_bytes = p.read_bytes()
    else:
        mime_type = "image/png"
        file_bytes = image_input

    refine_instruction = (
        f"{prompt}\n\n"
        f"--- BẢN NHÁP MARKDOWN TỪ STAGE 1 (CẦN KIỂM ĐỊNH & HIỆU ĐÍNH) ---\n"
        f"{draft_markdown}\n"
        f"--- HẾT BẢN NHÁP ---"
    )

    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                    refine_instruction,
                ],
            )
            if not response.text:
                raise RuntimeError("Gemini trả về nội dung rỗng khi verify.")
            return _strip_markdown_fences(response.text)
        except Exception as e:
            last_err = e
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                time.sleep(min(30.0, 10.0 * attempt))
            else:
                time.sleep(2 ** attempt)

    raise RuntimeError(f"Gemini Refiner thất bại sau {max_retries} lần thử: {last_err}")
