import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Optional
from tqdm import tqdm

# Đảm bảo Windows console in tiếng Việt không bị lỗi charmap/cp1252
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import (
    OUTPUT_DIR,
    MAX_CONCURRENCY,
    ENABLE_RAG_METADATA,
)
from hardware_checker import get_system_hardware, HardwareProfile
from router import pick_backend, Backend
from backends import (
    parse_with_markitdown,
    parse_with_docling,
    parse_with_gemini,
    parse_with_paddleocr,
    run_hybrid_pipeline,
)


def _exec_backend(
    b: Backend,
    path: Path,
    enable_rag: bool,
    skip_stage2: bool,
) -> str:
    """Gọi thực thi backend tương ứng với các tham số điều khiển."""
    if b == Backend.HYBRID:
        return run_hybrid_pipeline(
            path,
            enable_rag=enable_rag,
            skip_stage2=skip_stage2,
        )
    elif b == Backend.PADDLEOCR:
        md, _ = parse_with_paddleocr(path)
        return md

    elif b == Backend.GEMINI:
        return parse_with_gemini(path)
    elif b == Backend.DOCLING:
        return parse_with_docling(path)
    elif b == Backend.MARKITDOWN:
        return parse_with_markitdown(path)
    else:
        raise ValueError(f"Backend chưa được cấu hình hàm xử lý: {b}")


# Thứ tự fallback nếu backend chính gặp sự cố
FALLBACK_CHAIN = {
    Backend.HYBRID: [Backend.GEMINI, Backend.DOCLING],
    Backend.PADDLEOCR: [Backend.GEMINI, Backend.DOCLING],
    Backend.GEMINI: [Backend.MARKITDOWN],
    Backend.MARKITDOWN: [Backend.DOCLING, Backend.GEMINI],
    Backend.DOCLING: [Backend.GEMINI],
}


def build_output_path(input_path: Path) -> Path:
    """Template xuất file: output/{filename}/{filename}-{date}.md"""
    stem = input_path.stem
    today = date.today().isoformat()
    folder = Path(OUTPUT_DIR) / stem
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{stem}-{today}.md"


def process_file(
    input_path: Path,
    mode: str,
    force_backend: Optional[Backend],
    pdf_is_scanned: bool,

    enable_rag: bool,
    skip_stage2: bool,
    overwrite: bool = False,
) -> tuple[Path, str]:
    out_path = build_output_path(input_path)
    if not overwrite and out_path.exists() and out_path.stat().st_size > 0:
        return out_path, "ĐÃ CÓ (Bỏ qua)"

    backend = pick_backend(
        input_path,
        mode=mode,
        force=force_backend,
        pdf_is_scanned=pdf_is_scanned,
    )
    chain = [backend] + FALLBACK_CHAIN.get(backend, [])
    last_err = None

    for b in chain:
        try:
            content = _exec_backend(
                b,
                input_path,
                enable_rag=enable_rag,
                skip_stage2=skip_stage2,
            )
            out_path.write_text(content, encoding="utf-8")
            return out_path, f"OK ({b.value})"
        except Exception as e:
            last_err = e
            continue

    return input_path, f"THẤT BẠI: {last_err}"


def run_batch(
    files: list[Path],
    mode: str,
    force_backend: Optional[Backend],
    pdf_is_scanned: bool,

    enable_rag: bool,
    skip_stage2: bool,
    overwrite: bool = False,
):
    max_workers = max(MAX_CONCURRENCY.values())
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                process_file,
                f,
                mode,
                force_backend,
                pdf_is_scanned,

                enable_rag,
                skip_stage2,
                overwrite,
            ): f
            for f in files
        }
        for fut in tqdm(as_completed(futures), total=len(futures), desc="Đang xử lý"):
            f = futures[fut]
            out, status = fut.result()
            print(f"[{status}] {f.name} -> {out}")


def collect_files(target: Path) -> list[Path]:
    supported = {
        ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
        ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"
    }
    if target.is_file():
        return [target] if target.suffix.lower() in supported else []
    return [p for p in target.rglob("*") if p.suffix.lower() in supported]


def main():
    parser = argparse.ArgumentParser(
        description="Personal Doc Crawler – Hybrid OCR (PP-Structure/PaddleOCR) & VLM Verification (Gemini 3.5 Flash)"
    )
    parser.add_argument("path", help="File hoặc thư mục cần xử lý")
    parser.add_argument(
        "--mode",
        choices=["hybrid", "fast", "vlm", "auto"],
        default="hybrid",
        help="Chế độ xử lý: hybrid (mặc định: 2-stage), fast (offline local), vlm (direct VLM), auto (tự động)",
    )

    parser.add_argument(
        "--backend",
        choices=[b.value for b in Backend],
        help="Ép buộc dùng 1 backend cụ thể cho tất cả file",
    )
    parser.add_argument(
        "--scanned",
        action="store_true",
        help="Đánh dấu PDF là bản scan (ưu tiên chạy qua Hybrid / OCR pipeline)",
    )
    parser.add_argument(
        "--rag-metadata",
        action="store_true",
        default=ENABLE_RAG_METADATA,
        help="Tự động sinh YAML Frontmatter chứa thông tin cấu trúc cho AI / RAG",
    )
    parser.add_argument(
        "--no-refine",
        action="store_true",
        help="Chỉ chạy Stage 1 OCR, bỏ qua Stage 2 VLM verification (tiết kiệm API)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Ghi đè file markdown nếu đã tồn tại",
    )
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"Lỗi: Đường dẫn '{args.path}' không tồn tại.")
        return

    # 1. Quét phần cứng và tự động cấu hình
    hw: HardwareProfile = get_system_hardware()

    print("=================================================================")
    print("       PERSONAL DOC CRAWLER – HYBRID OCR & VLM SYSTEM       ")
    print("=================================================================")
    print(f"[*] PHẦN CỨNG: {hw.cpu_count} CPU Cores | RAM: {hw.total_ram_gb} GB (Khả dụng: {hw.available_ram_gb} GB)")
    if hw.has_cuda and hw.gpu_name:
        print(f"[*] GPU: {hw.gpu_name} ({hw.gpu_vram_gb} GB VRAM) – CUDA: Sẵn sàng")
    
    if not hw.is_capable_for_local_ocr:
        print(f"\n[!] CẢNH BÁO PHẦN CỨNG: {hw.warning_reason}")
        print(f"[!] Máy tính có cấu hình yếu -> ĐÃ BỎ QUA thiết lập Local PaddleOCR/PP-Structure.")
        print(f"[!] Hệ thống TỰ ĐỘNG CHUYỂN 100% SANG ONLINE VLM OCR (Gemini 3.5 Flash).\n")
    else:
        print(f"[*] CẤU HÌNH PP-STRUCTURE: {hw.status_summary}\n")

    force = Backend(args.backend) if args.backend else None
    files = collect_files(target)

    if not files:
        print("Không tìm thấy file hợp lệ.")
        return

    print(f"- Tìm thấy: {len(files)} file cần xử lý")
    print(f"- Chế độ (Mode): {args.mode}")

    print(f"- RAG Metadata: {args.rag_metadata}")
    print(f"- Bỏ qua Stage 2: {args.no_refine}")
    print("Bắt đầu xử lý...\n")

    start = time.time()
    run_batch(
        files=files,
        mode=args.mode,
        force_backend=force,
        pdf_is_scanned=args.scanned,
        enable_rag=args.rag_metadata,
        skip_stage2=args.no_refine,
        overwrite=args.overwrite,
    )
    print(f"\nHoàn tất trong {time.time() - start:.2f}s")


if __name__ == "__main__":
    main()
