@echo off
rem Pantau folder ini dan kirim perubahan ke GitHub secara otomatis.
rem Contoh: pantau.bat        (periksa tiap 60 detik)
rem          pantau.bat 30   (periksa tiap 30 detik)
rem Hentikan dengan Ctrl+C. File .env, *.db, dan debug/ tidak ikut terkirim.
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "JEDA=%~1"
if "%JEDA%"=="" set "JEDA=60"

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo [GAGAL] Folder ini bukan repo Git.
    exit /b 1
)

for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "CABANG=%%b"

echo Memantau perubahan di %CD%
echo Cabang: %CABANG%
echo Selang pemeriksaan: %JEDA% detik. Tekan Ctrl+C untuk berhenti.
echo.

:pantau
set "ADA="
for /f "delims=" %%a in ('git status --porcelain 2^>nul') do set "ADA=1"

if defined ADA (
    echo [%DATE% %TIME%] Perubahan terdeteksi, mengirim ke GitHub...
    call "%~dp0simpan.bat"
    echo.
)

rem Jeda: ping dipakai karena 'timeout' gagal saat dijalankan tanpa jendela.
ping -n %JEDA% 127.0.0.1 >nul 2>&1
goto :pantau
