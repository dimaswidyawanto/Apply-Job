@echo off
rem Skrip bantu Windows: siapkan .venv, pasang dependensi, lalu jalankan CLI.
rem Contoh: jalankan.bat run
rem          jalankan.bat config
rem          jalankan.bat history --limit 10
setlocal
cd /d "%~dp0"

rem Cari Python: utamakan "python", lalu jatuh ke launcher "py -3".
set "PY=python"
%PY% --version >nul 2>&1
if errorlevel 1 set "PY=py -3"
%PY% --version >nul 2>&1
if errorlevel 1 goto :tanpapython

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Membuat virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 goto :gagal
)

if not exist ".venv\Scripts\python.exe" goto :gagal

echo [2/3] Memasang dependensi...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
if errorlevel 1 goto :gagal

if not exist ".env" (
    if exist ".env.example" (
        copy /y ".env.example" ".env" >nul
        echo File .env dibuat dari .env.example. Sesuaikan dulu bila perlu.
    )
)

echo [3/3] Menjalankan program...
echo.
".venv\Scripts\python.exe" cli.py %*
exit /b %errorlevel%

:tanpapython
echo.
echo Python tidak ditemukan.
echo Install Python 3.10+ dari https://www.python.org/downloads/ dan centang
echo "Add python.exe to PATH" saat memasang, lalu buka terminal baru.
pause
exit /b 1

:gagal
echo.
echo GAGAL menyiapkan lingkungan Python.
echo - Pastikan Python 3.10+ terpasang:  python --version  atau  py --version
echo - Pastikan folder proyek TIDAK berada di C:\WINDOWS (pindahkan ke
echo   Documents, misalnya C:\Users\NamaAnda\Documents\dimastes)
echo - Jalankan terminal sebagai pengguna biasa, bukan administrator.
pause
exit /b 1
