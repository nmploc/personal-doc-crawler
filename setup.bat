@echo off
chcp 65001 >nul
color 0A
title Personal Doc Crawler - 1-Click Setup

echo =================================================================
echo       PERSONAL DOC CRAWLER - CÀI ĐẶT TỰ ĐỘNG (1-CLICK SETUP)     
echo =================================================================
echo.

:: 1. Kiểm tra Python
echo [*] Dang kiem tra Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    color 0C
    echo [!] LOI: Khong tim thay Python tren he thong!
    echo [!] Vui long tai va cai dat Python 3.10 toi 3.12 tai: https://www.python.org/downloads/
    echo [!] QUAN TRONG: Nho tich chon vao o "Add Python to PATH" khi cai dat.
    echo.
    pause
    exit /b 1
)

:: 2. Khởi tạo môi trường ảo (venv)
echo [*] Dang khoi tao moi truong ao (Virtual Environment)...
if not exist "venv" (
    python -m venv venv
    if %errorlevel% neq 0 (
        color 0C
        echo [!] LOI: Khong the tao moi truong ao.
        pause
        exit /b 1
    )
)

:: 3. Kích hoạt venv và cài đặt thư viện
echo [*] Kich hoat venv va cai dat thu vien phu thuoc (Co the mat vai phut)...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if %errorlevel% neq 0 (
    color 0C
    echo [!] LOI: Cai dat thu vien that bai. Vui long kiem tra lai mang hoac requirements.txt.
    pause
    exit /b 1
)

:: 4. Xử lý file .env
echo.
echo [*] Dang cau hinh moi truong...
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
    ) else (
        echo GEMINI_API_KEY= > .env
    )
)

:: 5. Cài đặt PaddleOCR (Optional)
echo.
echo =================================================================
echo Tùy chọn cài đặt OCR Cục bộ (PaddleOCR) để chạy Hybrid Mode.
echo Neu may tinh ban khong co card do hoa roi hoac ban chi muon 
echo dung API cua Gemini de tiet kiem tai nguyen, hay chon No.
echo =================================================================
choice /C YN /M "Ban co muon cai dat PaddleOCR (Khoang 1GB) khong? [Y = Yes, N = No]"
if errorlevel 2 goto SKIP_PADDLE
if errorlevel 1 goto INSTALL_PADDLE

:INSTALL_PADDLE
echo.
echo [*] Dang cai dat PaddleOCR (Phien ban CPU)...
pip install paddlepaddle paddleocr
echo [*] Hoan tat cai dat PaddleOCR.
goto END_SETUP

:SKIP_PADDLE
echo.
echo [*] Da bo qua buoc cai dat PaddleOCR.

:END_SETUP
echo.
color 0B
echo =================================================================
echo [+] HOAN TAT CAI DAT! 
echo [+] Ban da co the su dung chuong trinh.
echo =================================================================
echo.
echo Nhấn phím bất kỳ để khởi chạy Menu CLI...
pause >nul
call run.bat
