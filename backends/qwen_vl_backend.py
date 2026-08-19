import base64
import io
import re
import time
from pathlib import Path
from typing import Union
from openai import OpenAI
from config import (
    QWEN_VL_API_KEY,
    QWEN_VL_BASE_URL,
    QWEN_VL_MODEL,
    QWEN_OCR_PROMPT,
    VLM_REFINE_PROMPT,
    VLM_TIMEOUT_SECONDS,
)

_client = None


def _get_qwen_client() -> OpenAI:
    global _client
    if _client is None:
        if not QWEN_VL_API_KEY:
            raise RuntimeError(
                "Chưa cấu hình QWEN_VL_API_KEY trong file .env hoặc biến môi trường."
            )
        _client = OpenAI(
            api_key=QWEN_VL_API_KEY,
            base_url=QWEN_VL_BASE_URL,
            timeout=VLM_TIMEOUT_SECONDS,
        )
    return _client


def _strip_markdown_fences(text: str) -> str:
    """Loại bỏ ```markdown ... ``` hoặc ``` ... ``` bao ngoài nếu model tự bọc."""
    text = text.strip()
    match = re.match(r"^```(?:markdown)?\s*\n(.*)\n```$", text, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def _to_base64_data_uri(image_input: Union[Path, str, bytes], mime_type: str = "image/png") -> str:
    """Chuyển đổi Path hoặc bytes sang Base64 Data URI."""
    if isinstance(image_input, (str, Path)):
        p = Path(image_input)
        suffix = p.suffix.lower()
        if suffix in (".jpg", ".jpeg"):
            mime_type = "image/jpeg"
        elif suffix == ".webp":
            mime_type = "image/webp"
        raw_bytes = p.read_bytes()
    else:
        raw_bytes = image_input

    b64 = base64.b64encode(raw_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


def parse_with_qwen(
    input_path: Path,
    prompt: str = QWEN_OCR_PROMPT,
    max_retries: int = 3,
) -> str:
    """Gọi Qwen2.5-VL trực tiếp để OCR hình ảnh / tài liệu."""
    client = _get_qwen_client()
    data_uri = _to_base64_data_uri(input_path)

    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=QWEN_VL_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_uri}},
                        ],
                    }
                ],
                temperature=0.1,
            )
            content = response.choices[0].message.content
            if not content:
                raise RuntimeError("Qwen2.5-VL trả về nội dung rỗng.")
            return _strip_markdown_fences(content)
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)

    raise RuntimeError(f"Qwen2.5-VL OCR thất bại sau {max_retries} lần thử: {last_err}")


def refine_with_qwen(
    image_input: Union[Path, bytes],
    draft_markdown: str,
    prompt: str = VLM_REFINE_PROMPT,
    timeout: int = VLM_TIMEOUT_SECONDS,
) -> str:
    """
    Stage 2 Refiner & Verifier bằng Qwen2.5-VL:
    Đối chiếu hình ảnh gốc với bản nháp Markdown từ Stage 1 để sửa lỗi chính tả, bảng biểu và công thức.
    """
    client = _get_qwen_client()
    data_uri = _to_base64_data_uri(image_input)

    user_text = (
        f"{prompt}\n\n"
        f"--- BẢN NHÁP MARKDOWN TỪ STAGE 1 (CẦN KIỂM ĐỊNH & HIỆU ĐÍNH) ---\n"
        f"{draft_markdown}\n"
        f"--- HẾT BẢN NHÁP ---"
    )

    response = client.chat.completions.create(
        model=QWEN_VL_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        ],
        temperature=0.1,
        timeout=timeout,
    )

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("Qwen2.5-VL trả về nội dung rỗng khi verify.")
    return _strip_markdown_fences(content)
