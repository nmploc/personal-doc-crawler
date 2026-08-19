@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
color 0A
title Personal Doc Crawler - 1-Click Setup

echo =================================================================
echo       PERSONAL DOC CRAWLER - CAI DAT TU DONG 1-CLICK SETUP       
echo =================================================================
echo.

:: 1. Kiem tra Python
echo [*] Dang kiem tra Python tren may tinh...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    color 0C
    echo [!] LOI: Khong tim thay Python tren he thong!
    echo [!] Vui long tai va cai dat Python 3.10 den 3.12 tai: https://www.python.org/downloads/
    echo [!] LUU Y QUAN TRONG: Tich chon vao o "Add Python to PATH" khi cai dat.
    echo.
    pause
    exit /b 1
)

:: 2. Khoi tao moi truong ao venv
echo [*] Dang khoi tao moi truong ao Virtual Environment...
if not exist "venv" (
    python -m venv venv
    if %errorlevel% neq 0 (
        color 0C
        echo [!] LOI: Khong the tao moi truong ao venv.
        pause
        exit /b 1
    )
)

:: 3. Kich hoat venv va cai dat thu vien
echo [*] Dang kich hoat venv va cai dat thu vien phu thuoc...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if %errorlevel% neq 0 (
    color 0C
    echo [!] LOI: Cai dat thu vien that bai. Vui long kiem tra lai ket noi mang.
    pause
    exit /b 1
)

:: 4. Xu ly file .env
echo.
echo [*] Dang kiem tra file cau hinh .env...
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
    ) else (
        echo GEMINI_API_KEY= > .env
    )
)

:: 5. Cai dat PaddleOCR (Tuy chon)
echo.
echo =================================================================
echo Tuy chon cai dat OCR Cuc bo PaddleOCR de chay Hybrid Mode.
echo Neu may tinh khong co GPU hoac chi muon dung Online Gemini, chon N.
echo =================================================================
choice /C YN /M "Ban co muon cai dat PaddleOCR khoang 1GB khong? [Y = Co, N = Khong]"
if errorlevel 2 goto SKIP_PADDLE
if errorlevel 1 goto INSTALL_PADDLE

:INSTALL_PADDLE
echo.
echo [*] Dang cai dat PaddleOCR phien ban CPU...
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
echo [+] HOAN TAT CAI DAT! Ban da co the su dung chuong trinh.
echo =================================================================
echo.
echo Nhan phim bat ky de khoi chay Menu CLI...
pause >nul
call run.bat

