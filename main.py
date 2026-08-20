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
import threading

_backend_semaphores = {
    b: threading.Semaphore(MAX_CONCURRENCY.get(b.value, 4))
    for b in Backend
}


def _exec_backend(
    b: Backend,
    path: Path,
    enable_rag: bool,
    skip_stage2: bool,
    obsidian_mode: str = 'table',
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
        return parse_with_markitdown(path, obsidian_mode=obsidian_mode)
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


def build_output_path(input_path: Path, base_dir: Optional[Path] = None) -> Path:
    """
    Tạo đường dẫn xuất file.
    - Nếu xử lý 1 file lẻ: output/{stem}/{stem}-{date}.md
    - Nếu xử lý theo lô từ thư mục: output/{tên_thư_mục_gốc}/{rel_path}.md
    """
    out_dir = Path(OUTPUT_DIR)
    
    if base_dir and base_dir.is_dir():
        # Lấy tên thư mục gốc làm subfolder
        batch_folder = out_dir / base_dir.name
        try:
            rel_path = input_path.relative_to(base_dir)
            # Thay đổi phần mở rộng thành .md
            out_file = batch_folder / rel_path.with_suffix(".md")
        except ValueError:
            out_file = batch_folder / f"{input_path.stem}.md"
            
        out_file.parent.mkdir(parents=True, exist_ok=True)
        return out_file
    else:
        stem = input_path.stem
        folder = out_dir / stem
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{stem}.md"


def process_file(
    input_path: Path,
    mode: str,
    force_backend: Optional[Backend],
    pdf_is_scanned: bool,
    enable_rag: bool,
    skip_stage2: bool,
    overwrite: bool = False,
    base_dir: Optional[Path] = None,
    obsidian_mode: str = 'table',
) -> tuple[Path, str]:
    out_path = build_output_path(input_path, base_dir)
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
            with _backend_semaphores[b]:
                content = _exec_backend(
                    b,
                    input_path,
                    enable_rag=enable_rag,
                    skip_stage2=skip_stage2,
                    obsidian_mode=obsidian_mode,
                )
            if len(content.strip()) < 20:
                raise RuntimeError(
                    f"Output quá ngắn ({len(content.strip())} ký tự) — "
                    f"backend {b.value} có thể không hỗ trợ định dạng này."
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
    base_dir: Optional[Path] = None,
    obsidian_mode: str = 'table',
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
                base_dir,
                obsidian_mode,
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
        action=argparse.BooleanOptionalAction,
        default=ENABLE_RAG_METADATA,
        help="Tự động sinh YAML Frontmatter chứa thông tin cấu trúc cho AI / RAG (hỗ trợ --no-rag-metadata)",
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
    parser.add_argument(
        "--obsidian-mode",
        choices=["table", "callout", "none"],
        default="table",
        help="Định dạng xuất bảng cho Obsidian (áp dụng MarkItDown với Excel/CSV). 'table' (Mặc định): Bảng chuẩn. 'callout': Thẻ ghi chú Q&A. 'none': Giữ nguyên gốc.",
    )
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"Lỗi: Đường dẫn '{args.path}' không tồn tại.")
        return
        
    base_dir = target if target.is_dir() else None

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
    if base_dir:
        print(f"- Xử lý theo lô (Batch Mode). Kết quả sẽ gom vào: output/{base_dir.name}/")

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
        base_dir=base_dir,
        obsidian_mode=args.obsidian_mode,
    )
    print(f"\nHoàn tất trong {time.time() - start:.2f}s")


if __name__ == "__main__":
    main()
