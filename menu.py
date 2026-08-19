import os
import sys
import time

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def main_menu():
    while True:
        clear_screen()
        print("=================================================================")
        print("       PERSONAL DOC CRAWLER - INTERACTIVE MENU                   ")
        print("=================================================================")
        print("Vui lòng nhập phím từ 1 đến 5 để chọn chức năng:\n")
        print(" 1 - Quét OCR & Verify chất lượng cao (Hybrid Mode)")
        print(" 2 - Chuyển đổi nhanh tài liệu thô (Fast Mode - Không tốn API)")
        print(" 3 - Kiểm tra cấu hình phần cứng (Hardware Check)")
        print(" 4 - Thông tin dự án (License & GitHub)")
        print(" 5 - Kết thúc phiên (Thoát chương trình)\n")
        
        choice = input("Lựa chọn của bạn: ").strip()
        
        if choice == '1':
            print("\n[Hybrid Mode] Kết hợp PaddleOCR và Gemini 3.5 Flash")
            path = input("Nhập đường dẫn file hoặc thư mục (kéo thả file vào đây): ").strip()
            path = path.strip('"').strip("'")
            if os.path.exists(path):
                os.system(f'python main.py "{path}" --mode hybrid')
            else:
                print(f"Lỗi: Không tìm thấy '{path}'")
            input("\nNhấn Enter để tiếp tục...")
            
        elif choice == '2':
            print("\n[Fast Mode] Trích xuất siêu tốc bằng MarkItDown / Docling")
            path = input("Nhập đường dẫn file hoặc thư mục (kéo thả file vào đây): ").strip()
            path = path.strip('"').strip("'")
            if os.path.exists(path):
                os.system(f'python main.py "{path}" --mode fast')
            else:
                print(f"Lỗi: Không tìm thấy '{path}'")
            input("\nNhấn Enter để tiếp tục...")
            
        elif choice == '3':
            print("\n[Hardware Profiling] Đang kiểm tra cấu hình máy tính...")
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
            
            print(f"\nKhuyến nghị  : {hw.status_summary}")
            input("\nNhấn Enter để tiếp tục...")
            
        elif choice == '4':
            print("\n===========================================")
            print("          PERSONAL DOC CRAWLER             ")
            print("===========================================")
            print("Bản quyền (c) 2026 nmploc - Giấy phép MIT")
            print("GitHub Repo: https://github.com/nmploc/personal-doc-crawler")
            print("Tính năng chính: Trích xuất và cấu trúc hóa tài liệu RAG")
            print("===========================================")
            input("\nNhấn Enter để tiếp tục...")
            
        elif choice == '5':
            print("\nĐã đóng chương trình. Hẹn gặp lại!")
            sys.exit(0)
            
        else:
            print("\nLựa chọn không hợp lệ, vui lòng nhập số từ 1 đến 5.")
            time.sleep(1.5)

if __name__ == "__main__":
    # Fix lỗi in tiếng Việt trên console Windows
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main_menu()
