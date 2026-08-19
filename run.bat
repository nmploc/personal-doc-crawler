@echo off
chcp 65001 >nul
title Personal Doc Crawler

if not exist "venv\Scripts\activate.bat" (
    color 0E
    echo [!] Moi truong ao chua duoc cai dat!
    echo [!] He thong se tu dong chay Setup...
    echo.
    pause
    call setup.bat
    exit /b
)

call venv\Scripts\activate.bat
python menu.py

pause
