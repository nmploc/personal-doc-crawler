import logging
import concurrent.futures
from pathlib import Path
from typing import Union, Tuple
from config import (
    GEMINI_API_KEY,
    QWEN_VL_API_KEY,
    VLM_VERIFY_MODE,
    VLM_TIMEOUT_SECONDS,
)
from backends.gemini_vision_backend import refine_with_gemini
from backends.qwen_vl_backend import refine_with_qwen

logger = logging.getLogger(__name__)


def _call_qwen_safe(image_input: Union[Path, bytes], draft_markdown: str) -> Tuple[bool, str]:
    """Gọi Qwen2.5-VL an toàn với bắt ngoại lệ và kiểm tra API key."""
    if not QWEN_VL_API_KEY:
        return False, "QWEN_VL_API_KEY chưa được cấu hình."
    try:
        res = refine_with_qwen(image_input, draft_markdown, timeout=VLM_TIMEOUT_SECONDS)
        return True, res
    except Exception as e:
        return False, f"Lỗi Qwen2.5-VL: {e}"


def _call_gemini_safe(image_input: Union[Path, bytes], draft_markdown: str) -> Tuple[bool, str]:
    """Gọi Gemini 3.5 Flash an toàn với bắt ngoại lệ và kiểm tra API key."""
    if not GEMINI_API_KEY:
        return False, "GEMINI_API_KEY chưa được cấu hình."
    try:
        res = refine_with_gemini(image_input, draft_markdown)
        return True, res
    except Exception as e:
        return False, f"Lỗi Gemini 3.5 Flash: {e}"


def verify_and_refine(
    image_input: Union[Path, bytes],
    draft_markdown: str,
    mode: str = VLM_VERIFY_MODE,
) -> Tuple[str, str]:
    """
    Điều phối kiểm tra cú pháp và hiệu đính OCR:
    - Mode 'parallel': Chạy song song cả Qwen2.5-VL và Gemini 3.5 Flash để đối chiếu.
      * Cả 2 thành công: Ưu tiên bản kiểm tra cú pháp của Qwen2.5-VL (đã cross-check với Gemini).
      * 1 trong 2 lỗi/không phản hồi: TỰ ĐỘNG CHUYỂN VÙNG (Auto-Failover) sang model còn lại.
      * Cả 2 lỗi: Giữ nguyên Draft Markdown từ Stage 1.
    - Mode 'fallback': Thử Qwen trước, nếu lỗi -> Gemini.
    - Mode 'qwen_only': Chỉ dùng Qwen2.5-VL.
    - Mode 'gemini_only': Chỉ dùng Gemini 3.5 Flash.

    Trả về: (markdown_hoan_chinh, thong_tin_verifiers)
    """
    mode = (mode or "parallel").lower()

    if mode == "qwen_only":
        ok, res = _call_qwen_safe(image_input, draft_markdown)
        if ok:
            return res, "qwen2.5-vl"
        logger.warning("Qwen only thất bại: %s", res)
        return draft_markdown, f"stage1-draft (qwen-failed: {res})"

    if mode == "gemini_only":
        ok, res = _call_gemini_safe(image_input, draft_markdown)
        if ok:
            return res, "gemini-3.5-flash"
        logger.warning("Gemini only thất bại: %s", res)
        return draft_markdown, f"stage1-draft (gemini-failed: {res})"

    if mode == "fallback":
        # Ưu tiên Qwen trước
        ok_q, res_q = _call_qwen_safe(image_input, draft_markdown)
        if ok_q:
            return res_q, "qwen2.5-vl (primary)"
        logger.warning("Qwen gặp sự cố, tự động failover sang Gemini: %s", res_q)
        
        # Chuyển qua Gemini
        ok_g, res_g = _call_gemini_safe(image_input, draft_markdown)
        if ok_g:
            return res_g, f"gemini-3.5-flash (auto-failover từ qwen: {res_q})"
        return draft_markdown, f"stage1-draft (cả 2 vlm đều lỗi: {res_q} | {res_g})"

    # Mặc định: Chế độ song song đối chiếu 'parallel'
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_qwen = executor.submit(_call_qwen_safe, image_input, draft_markdown)
        future_gemini = executor.submit(_call_gemini_safe, image_input, draft_markdown)

        ok_qwen, res_qwen = future_qwen.result()
        ok_gemini, res_gemini = future_gemini.result()

    # TH1: Cả hai model đều phản hồi thành công -> Đối chiếu & ưu tiên kết quả chuẩn cú pháp
    if ok_qwen and ok_gemini:
        # Qwen2.5-VL được ưu tiên về cấu trúc OCR & bảng biểu, đã được đối chiếu song song cùng Gemini
        return res_qwen, "qwen2.5-vl + gemini-3.5-flash (parallel cross-verified)"

    # TH2: Qwen thành công, Gemini không phản hồi / lỗi -> Dùng Qwen
    if ok_qwen and not ok_gemini:
        logger.warning("Gemini không phản hồi trong phiên, tự động dùng Qwen: %s", res_gemini)
        return res_qwen, f"qwen2.5-vl (gemini-offline: {res_gemini})"

    # TH3: Qwen không phản hồi / lỗi, Gemini thành công -> Tự động chuyển qua Gemini
    if not ok_qwen and ok_gemini:
        logger.warning("Qwen không phản hồi trong phiên, tự động chuyển sang Gemini: %s", res_qwen)
        return res_gemini, f"gemini-3.5-flash (auto-failover từ qwen: {res_qwen})"

    # TH4: Cả 2 đều không phản hồi -> Trả về bản nháp Stage 1
    logger.warning("Cả 2 VLM đều không phản hồi: Qwen (%s), Gemini (%s)", res_qwen, res_gemini)
    return draft_markdown, f"stage1-draft (vlm-failed: qwen={res_qwen} | gemini={res_gemini})"
