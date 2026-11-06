@echo off
rem Skrip bantu Windows: siapkan .venv, pasang dependensi (sekali saja), lalu
rem jalankan CLI.
rem Contoh: jalankan.bat run
rem          jalankan.bat config
rem          jalankan.bat history --limit 10
rem          jalankan.bat indeed diagnosa --keyword "inventory staff"
rem
rem Variabel opsional:
rem   PAKSA_PASANG=1  -> pasang ulang dependensi walau sudah siap
rem   LEWATI_PASANG=1 -> jangan pernah memasang dependensi
setlocal
cd /d "%~dp0"

rem --- 0. Jalur cepat: .venv sudah siap -> jangan cari Python lagi ---
rem     Tanpa ini setiap perintah menunggu beberapa detik karena cmd
rem     menjalankan `py -3.13 --version`, `py -3.12`, ... satu per satu.
rem     Penanda .venv\.python-baik hanya dibuat bila versinya didukung.
if exist ".venv\Scripts\python.exe" if exist ".venv\.deps-terpasang" if exist ".venv\.python-baik" goto :venv_siap

rem --- 1. Pilih Python yang didukung (3.10 - 3.13) ---
set "PY="
for %%V in (3.13 3.12 3.11 3.10) do (
    if not defined PY py -%%V --version >nul 2>&1 && set "PY=py -%%V"
)
if not defined PY (
    python --version >nul 2>&1 && set "PY=python"
)
if not defined PY (
    py -3 --version >nul 2>&1 && set "PY=py -3"
)
if not defined PY goto :tanpapython

set "PYMINOR="
for /f %%A in ('%PY% -c "import sys;print(sys.version_info[1])" 2^>nul') do set "PYMINOR=%%A"
if not defined PYMINOR goto :tanpapython

set "PY_OK=0"
if %PYMINOR% LSS 14 set "PY_OK=1"
if "%PY_OK%"=="0" (
    echo [PERINGATAN] Python 3.%PYMINOR% terpilih, sedangkan paket yang dibutuhkan
    echo   belum tentu mendukungnya dan pip bisa macet.
    echo   Disarankan memasang Python 3.12 dari https://www.python.org/downloads/
    echo.
)

rem --- 2. .venv yang dibuat Python 3.14+ dibuat ulang bila ada pilihan lain ---
set "VENVMINOR="
if exist ".venv\Scripts\python.exe" for /f %%A in ('".venv\Scripts\python.exe" -c "import sys;print(sys.version_info[1])" 2^>nul') do set "VENVMINOR=%%A"
if not defined VENVMINOR goto :venv_siap
if %VENVMINOR% LSS 14 goto :venv_siap
if "%PY_OK%"=="0" goto :venv_siap

echo [info] .venv lama memakai Python 3.%VENVMINOR% ^(pip sering macet^).
echo [info] Membuat ulang dengan %PY% — folder lama disimpan sebagai .venv-lama
if exist ".venv-lama" rmdir /s /q ".venv-lama"
move ".venv" ".venv-lama" >nul

:venv_siap
if exist ".venv\.python-baik" goto :cek_deps
if not exist ".venv\Scripts\python.exe" goto :cek_deps
if not defined PYMINOR goto :cek_deps
if %PYMINOR% GEQ 14 goto :cek_deps
> ".venv\.python-baik" echo ok

:cek_deps
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Membuat virtual environment dengan %PY%...
    %PY% -m venv .venv
    if errorlevel 1 goto :gagal
)

if not exist ".venv\Scripts\python.exe" goto :gagal

rem --- 3. Pasang dependensi hanya bila belum pernah / requirements berubah ---
set "PERLU=0"
if /I "%PAKSA_PASANG%"=="1" set "PERLU=1"
if /I "%LEWATI_PASANG%"=="1" set "PERLU=0"
if "%PERLU%"=="0" (
    if not exist ".venv\.deps-terpasang" (
        set "PERLU=1"
    ) else (
        fc /b requirements.txt ".venv\.deps-terpasang" >nul 2>&1 || set "PERLU=1"
    )
)

if "%PERLU%"=="1" (
    echo [2/3] Memasang dependensi ^(sekali saja, mohon tunggu^)...
    ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
    ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
    if errorlevel 1 goto :gagal
    copy /y requirements.txt ".venv\.deps-terpasang" >nul
) else (
    echo [2/3] Dependensi sudah terpasang, dilewati.
)

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
echo Install Python 3.10 - 3.13 dari https://www.python.org/downloads/ dan centang
echo "Add python.exe to PATH" saat memasang, lalu buka terminal baru.
pause
exit /b 1

:gagal
echo.
echo GAGAL menyiapkan lingkungan Python.
echo - Pastikan versi Python didukung: 3.10 - 3.13 ^(bukan 3.14/3.15^).
echo   Cek versi terpasang dengan:  py -0p
echo - Hapus folder .venv lalu jalankan lagi bila pip macet atau rusak.
echo - Pastikan folder proyek TIDAK berada di C:\WINDOWS.
echo - Jalankan terminal sebagai pengguna biasa, bukan administrator.
echo - Tanpa internet? pasang manual:
echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
pause
exit /b 1
