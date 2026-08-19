import base64
import io
import re
import time
import logging
from pathlib import Path
from typing import Union, List
from openai import OpenAI
from config import (
    QWEN_VL_API_KEY,
    QWEN_VL_BASE_URL,
    QWEN_VL_MODEL,
    QWEN_VL_FALLBACK_MODEL,
    QWEN_OCR_PROMPT,
    VLM_REFINE_PROMPT,
    VLM_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

_client = None


def _get_qwen_client() -> OpenAI:
    global _client
    if _client is None:
        if not QWEN_VL_API_KEY:
            raise RuntimeError(
                "Chưa cấu hình QWEN_VL_API_KEY trong file .env hoặc biến môi trường."
            )
        # Bổ sung headers khuyến nghị của OpenRouter
        headers = {
            "HTTP-Referer": "https://github.com/nmploc/personal-doc-crawler",
            "X-Title": "Personal Doc Crawler",
        }
        _client = OpenAI(
            api_key=QWEN_VL_API_KEY,
            base_url=QWEN_VL_BASE_URL,
            default_headers=headers,
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


def _get_candidate_models() -> List[str]:
    """Danh sách các model Qwen ưu tiên thử nghiệm (Model chính -> Model fallback)."""
    models = [QWEN_VL_MODEL]
    if QWEN_VL_FALLBACK_MODEL and QWEN_VL_FALLBACK_MODEL not in models:
        models.append(QWEN_VL_FALLBACK_MODEL)
    return models


def parse_with_qwen(
    input_path: Path,
    prompt: str = QWEN_OCR_PROMPT,
    max_retries: int = 2,
) -> str:
    """Gọi Qwen2.5-VL trực tiếp để OCR hình ảnh / tài liệu qua OpenRouter / OpenAI API."""
    client = _get_qwen_client()
    data_uri = _to_base64_data_uri(input_path)
    models = _get_candidate_models()

    last_err = None
    for model_name in models:
        for attempt in range(1, max_retries + 1):
            try:
                response = client.chat.completions.create(
                    model=model_name,
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
                    raise RuntimeError(f"Qwen ({model_name}) trả về nội dung rỗng.")
                return _strip_markdown_fences(content)
            except Exception as e:
                last_err = e
                logger.warning("Thử model %s (lần %s) thất bại: %s", model_name, attempt, e)
                time.sleep(2 ** attempt)

    raise RuntimeError(f"Qwen2.5-VL OCR thất bại trên tất cả models ({models}): {last_err}")


def refine_with_qwen(
    image_input: Union[Path, bytes],
    draft_markdown: str,
    prompt: str = VLM_REFINE_PROMPT,
    timeout: int = VLM_TIMEOUT_SECONDS,
) -> str:
    """
    Stage 2 Refiner & Verifier bằng Qwen2.5-VL:
    Đối chiếu hình ảnh gốc với bản nháp Markdown từ Stage 1 để sửa lỗi chính tả, bảng biểu và công thức.
    Tự động thử 72b trước, nếu bận/lỗi tự động thử sang 32b.
    """
    client = _get_qwen_client()
    data_uri = _to_base64_data_uri(image_input)
    models = _get_candidate_models()

    user_text = (
        f"{prompt}\n\n"
        f"--- BẢN NHÁP MARKDOWN TỪ STAGE 1 (CẦN KIỂM ĐỊNH & HIỆU ĐÍNH) ---\n"
        f"{draft_markdown}\n"
        f"--- HẾT BẢN NHÁP ---"
    )

    last_err = None
    for model_name in models:
        try:
            response = client.chat.completions.create(
                model=model_name,
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
                raise RuntimeError(f"Qwen ({model_name}) trả về nội dung rỗng.")
            return _strip_markdown_fences(content)
        except Exception as e:
            last_err = e
            logger.warning("Qwen refine trên model %s gặp sự cố: %s. Chuyển tiếp model kế tiếp...", model_name, e)
            continue

    raise RuntimeError(f"Qwen Refiner thất bại: {last_err}")
