import os
import sys
import time
from pathlib import Path
from dotenv import set_key, load_dotenv

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def get_input_path(prompt="Nhập đường dẫn file hoặc thư mục (kéo thả file vào đây): "):
    path = input(prompt).strip()
    return path.strip('"').strip("'")

def check_gemini_key():
    load_dotenv(override=True)
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key or key == "your_gemini_api_key_here":
        print("\n[!] CẢNH BÁO: Bạn chưa cấu hình GEMINI_API_KEY!")
        print("    Vui lòng chọn chức năng (4) để nhập API Key trước khi chạy các tính năng AI.")
        input("    Nhấn Enter để quay lại menu...")
        return False
    return True

def run_main(mode_args):
    path = get_input_path()
    if not os.path.exists(path):
        print(f"\n[!] Lỗi: Không tìm thấy đường dẫn '{path}'")
        input("Nhấn Enter để tiếp tục...")
        return
        
    p = Path(path)
    if p.is_dir():
        print(f"\n[*] Đã phát hiện thư mục: Bắt đầu chế độ xử lý theo lô (Batch Mode).")
        print(f"[*] Kết quả sẽ tự động gom vào: output/{p.name}/")
        
    cmd = f'python main.py "{path}" {mode_args}'
    os.system(cmd)
    input("\nNhấn Enter để tiếp tục...")

def config_api_key():
    env_path = Path(".env")
    if not env_path.exists():
        if Path(".env.example").exists():
            env_path.write_text(Path(".env.example").read_text(encoding="utf-8"), encoding="utf-8")
        else:
            env_path.write_text("GEMINI_API_KEY=\n", encoding="utf-8")
    
    load_dotenv(override=True)
    current_key = os.getenv("GEMINI_API_KEY", "")
    masked_key = f"{current_key[:6]}...{current_key[-4:]}" if len(current_key) > 10 else "(Chưa cấu hình)"
    
    print("\n--- CẤU HÌNH GEMINI API KEY ---")
    print(f"Key hiện tại: {masked_key}")
    print("Lấy API Key miễn phí tại: https://aistudio.google.com/apikey")
    new_key = input("Nhập API Key mới (để trống nếu muốn giữ nguyên): ").strip()
    
    if new_key:
        set_key(str(env_path), "GEMINI_API_KEY", new_key)
        print("[+] Đã cập nhật GEMINI_API_KEY thành công!")
    else:
        print("Đã giữ nguyên cấu hình cũ.")
    input("\nNhấn Enter để quay lại menu...")

def open_output_dir():
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    if os.name == 'nt':
        os.startfile(str(out_dir))
    else:
        print(f"\nThư mục kết quả nằm tại: {out_dir.absolute()}")
    input("\nNhấn Enter để tiếp tục...")

def check_hardware():
    print("\n[Hardware Profiling] Đang kiểm tra cấu hình máy tính...")
    try:
        from hardware_checker import get_system_hardware
        hw = get_system_hardware()
        print("\n--- THÔNG TIN HỆ THỐNG ---")
        print(f"Số nhân CPU : {hw.cpu_count} Cores")
        print(f"RAM Tổng    : {hw.total_ram_gb} GB")
        print(f"RAM Khả dụng: {hw.available_ram_gb} GB")
        if hw.has_cuda:
            print(f"GPU / CUDA  : {hw.gpu_name} (VRAM: {hw.gpu_vram_gb} GB)")
        else:
            print("GPU / CUDA  : Không có hoặc chưa cài đặt driver CUDA.")
        print(f"\nKhuyến nghị : {hw.status_summary}")
    except Exception as e:
        print(f"[!] Lỗi khi kiểm tra phần cứng: {e}")
    input("\nNhấn Enter để tiếp tục...")

def show_info():
    print("\n===========================================")
    print("          PERSONAL DOC CRAWLER             ")
    print("===========================================")
    print("Bản quyền (c) 2026 nmploc - Giấy phép MIT")
    print("GitHub Repo: https://github.com/nmploc/personal-doc-crawler")
    print("Tính năng chính: Trích xuất và cấu trúc hóa tài liệu RAG")
    print("===========================================")
    input("\nNhấn Enter để tiếp tục...")

def main_menu():
    while True:
        clear_screen()
        print("=================================================================")
        print("       PERSONAL DOC CRAWLER - INTERACTIVE MENU                   ")
        print("=================================================================")
        print("Vui lòng chọn chức năng:\n")
        print(" [1] Quét OCR chất lượng cao (Hybrid: PaddleOCR + Gemini 3.5 Flash)")
        print(" [2] Chuyển đổi siêu tốc offline (Fast Mode - Không tốn API)")
        print(" [3] OCR trực tiếp bằng Gemini Vision (VLM Mode - Dành cho máy yếu)")
        print(" [4] Cấu hình GEMINI API KEY (Quản lý Key sinh text)")
        print(" [5] Mở thư mục kết quả (Output)")
        print(" [6] Kiểm tra cấu hình phần cứng (Hardware Profiling)")
        print(" [7] Thông tin dự án (License & GitHub)")
        print(" [0] Kết thúc phiên (Thoát)\n")
        
        choice = input("Lựa chọn của bạn: ").strip()
        
        if choice == '1':
            print("\n[Hybrid Mode] Chế độ tối ưu tốt nhất cho Layout & Bảng biểu")
            if check_gemini_key():
                run_main("--mode hybrid")
        elif choice == '2':
            print("\n[Fast Mode] Trích xuất siêu tốc bằng MarkItDown / Docling")
            run_main("--mode fast")
        elif choice == '3':
            print("\n[VLM Mode] Gửi trực tiếp ảnh/PDF để Gemini phân tích OCR")
            if check_gemini_key():
                run_main("--mode vlm")
        elif choice == '4':
            config_api_key()
        elif choice == '5':
            open_output_dir()
        elif choice == '6':
            check_hardware()
        elif choice == '7':
            show_info()
        elif choice == '0':
            print("\nĐã đóng chương trình. Hẹn gặp lại!")
            sys.exit(0)
        else:
            print("\n[!] Lựa chọn không hợp lệ, vui lòng thử lại.")
            time.sleep(1)

if __name__ == "__main__":
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    main_menu()
