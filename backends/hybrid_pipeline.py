import datetime
from pathlib import Path
from typing import List, Tuple
from config import ENABLE_RAG_METADATA, VLM_VERIFY_MODE
from backends.paddleocr_backend import parse_with_paddleocr, render_pdf_to_images, load_image_bytes
from backends.vlm_verifier import verify_and_refine


def _generate_frontmatter(
    input_path: Path,
    stage1_name: str,
    verifier_info: str,
    total_pages: int,
    content: str,
) -> str:
    """Tạo YAML Frontmatter chuẩn cho các hệ thống AI / RAG."""
    now_iso = datetime.datetime.now().isoformat()
    word_count = len(content.split())
    
    frontmatter = [
        "---",
        f"source_file: {input_path.name}",
        f"converted_at: {now_iso}",
        f"pipeline: hybrid-2stage",
        f"stage1_engine: {stage1_name}",
        f"stage2_verifier: \"{verifier_info}\"",
        f"total_pages: {total_pages}",
        f"word_count: {word_count}",
        "---",
        "",
    ]
    return "\n".join(frontmatter)


def run_hybrid_pipeline(
    input_path: Path,
    verify_mode: str = VLM_VERIFY_MODE,
    enable_rag: bool = ENABLE_RAG_METADATA,
    skip_stage2: bool = False,
) -> str:
    """
    Quy trình Hybrid 2-Stage hoàn chỉnh:
    - Stage 1: Bóc tách OCR & bố cục bằng PaddleOCR-VL (sinh draft markdown + ảnh các trang).
    - Stage 2: Đối chiếu song song Qwen2.5-VL & Gemini 3.5 Flash (Auto-failover nếu 1 bên lỗi).
    - Xuất Markdown hoàn chỉnh chuẩn hóa cho AI/RAG.
    """
    ext = input_path.suffix.lower()

    # 1. Giai đoạn 1 (Stage 1): Trích xuất OCR & Danh sách ảnh trang
    draft_markdown, page_images = parse_with_paddleocr(input_path)
    stage1_name = "paddleocr-vl"

    # Nếu người dùng chọn bỏ qua Stage 2 (chế độ fast/local)
    if skip_stage2 or not page_images:
        final_md = draft_markdown
        verifier_summary = "none (stage 2 skipped)"
    else:
        # 2. Giai đoạn 2 (Stage 2): Dual-VLM Cross-Verification theo từng trang
        verified_pages = []
        verifier_statuses = []

        # Tách draft markdown theo trang nếu có nhiều trang
        raw_page_drafts = draft_markdown.split("\n\n---\n\n")

        for idx, (page_num, img_bytes) in enumerate(page_images):
            # Lấy bản nháp tương ứng của trang này nếu có
            page_draft = (
                raw_page_drafts[idx]
                if idx < len(raw_page_drafts)
                else draft_markdown
            )

            # Thực hiện kiểm tra chéo song song & auto-failover
            refined_page_md, verifier_info = verify_and_refine(
                image_input=img_bytes,
                draft_markdown=page_draft,
                mode=verify_mode,
            )

            verified_pages.append(refined_page_md)
            if verifier_info not in verifier_statuses:
                verifier_statuses.append(verifier_info)

        verifier_summary = "; ".join(verifier_statuses)
        if len(verified_pages) > 1:
            final_md = "\n\n---\n\n".join(
                f"<!-- Page {i+1} -->\n{p_md}" for i, p_md in enumerate(verified_pages)
            )
        else:
            final_md = verified_pages[0] if verified_pages else draft_markdown

    # 3. Đóng gói kết quả đầu ra kèm YAML Frontmatter cho RAG
    if enable_rag:
        frontmatter_str = _generate_frontmatter(
            input_path=input_path,
            stage1_name=stage1_name,
            verifier_info=verifier_summary,
            total_pages=len(page_images) if page_images else 1,
            content=final_md,
        )
        return f"{frontmatter_str}\n{final_md}"

    return final_md
