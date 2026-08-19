import io
import re
import time
import threading
from pathlib import Path
from typing import Union
from google import genai
from google.genai import types
from config import (
    GEMINI_API_KEYS,
    GEMINI_MODEL,
    GEMINI_OCR_PROMPT,
    VLM_REFINE_PROMPT,
    VLM_TIMEOUT_SECONDS,
)

_client_lock = threading.Lock()
_current_key_idx = 0
_clients = {}

def _get_client_and_idx():
    global _current_key_idx
    if not GEMINI_API_KEYS:
        raise RuntimeError("Chưa cấu hình GEMINI_API_KEY trong file .env hoặc biến môi trường.")
        
    with _client_lock:
        idx = _current_key_idx
        key = GEMINI_API_KEYS[idx]
        
    if idx not in _clients:
        _clients[idx] = genai.Client(api_key=key)
        
    return _clients[idx], idx

def _rotate_key(failed_idx):
    global _current_key_idx
    with _client_lock:
        if _current_key_idx == failed_idx:
            _current_key_idx = (_current_key_idx + 1) % len(GEMINI_API_KEYS)
            return True
    return False

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
    mime_type = _MIME_MAP.get(input_path.suffix.lower())
    if mime_type is None:
        raise RuntimeError(f"Định dạng {input_path.suffix} chưa hỗ trợ qua Gemini backend.")

    file_bytes = input_path.read_bytes()
    last_err = None

    for attempt in range(1, max_retries + 1):
        client, client_idx = _get_client_and_idx()
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
                if len(GEMINI_API_KEYS) > 1:
                    print(f"[!] Key {client_idx+1} hết token hoặc bị giới hạn rate limit. Tự động luân chuyển để tiếp tục công việc...")
                    _rotate_key(client_idx)
                    time.sleep(2.0)
                else:
                    print("[!] Hết token, vui lòng thử lại sau (5 tiếng).")
                    raise RuntimeError("Hết token, vui lòng thử lại sau (5 tiếng).")
            else:
                wait = 2 ** attempt
                time.sleep(wait)

    raise RuntimeError(f"Gemini OCR thất bại sau {max_retries} lần thử: {last_err}")


def refine_with_gemini(
    image_input: Union[Path, bytes],
    draft_markdown: str,
    prompt: str = VLM_REFINE_PROMPT,
    max_retries: int = 5,
) -> str:
    """
    Stage 2 Refiner & Verifier bằng Gemini 3.5 Flash:
    Gửi ảnh trang tài liệu + Draft Markdown từ Stage 1 để đối chiếu, sửa lỗi nhận diện và tối ưu Markdown.
    """
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
        client, client_idx = _get_client_and_idx()
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
                if len(GEMINI_API_KEYS) > 1:
                    print(f"[!] Key {client_idx+1} hết token hoặc bị giới hạn rate limit. Tự động luân chuyển để tiếp tục công việc...")
                    _rotate_key(client_idx)
                    time.sleep(2.0)
                else:
                    print("[!] Hết token, vui lòng thử lại sau (5 tiếng).")
                    raise RuntimeError("Hết token, vui lòng thử lại sau (5 tiếng).")
            else:
                time.sleep(2 ** attempt)

    raise RuntimeError(f"Gemini Refiner thất bại sau {max_retries} lần thử: {last_err}")
