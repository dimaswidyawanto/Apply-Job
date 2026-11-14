@echo off
rem Simpan perubahan ke GitHub dengan satu klik (Windows).
rem Contoh: simpan.bat
rem          simpan.bat "Perbaiki filter judul"
rem Skrip ini: bersihkan sisa rebase -> git add -A -> commit -> tarik -> push.
rem Aman dipakai berkali-kali: kalau tidak ada perubahan, hanya mengirim saja.
setlocal enabledelayedexpansion

rem Jangan pernah membuka editor teks (Vim): semua commit memakai -m,
rem dan penggabungan memakai --no-edit. Tanpa ini skrip menggantung.
set "GIT_EDITOR=echo"
set "GIT_MERGE_AUTOEDIT=no"
cd /d "%~dp0"

set "PESAN=%~1"

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo [GAGAL] Folder ini bukan repo Git.
    exit /b 1
)

rem --- 0. Sisa rebase yang gagal sebelumnya bisa menghentikan git pull ---
if exist "%~dp0.git\rebase-merge" (
    echo [1/5] Membersihkan sisa rebase dari percobaan sebelumnya...
    git rebase --abort >nul 2>&1
    if exist "%~dp0.git\rebase-merge" rmdir /s /q "%~dp0.git\rebase-merge"
)
if exist "%~dp0.git\rebase-apply" (
    echo [1/5] Membersihkan sisa rebase dari percobaan sebelumnya...
    git rebase --abort >nul 2>&1
    if exist "%~dp0.git\rebase-apply" rmdir /s /q "%~dp0.git\rebase-apply"
)

for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "CABANG=%%b"
if "%CABANG%"=="" set "CABANG=main"
echo [2/5] Cabang: %CABANG%

rem --- 1. Kumpulkan perubahan (file .env, *.db, *.log, dan debug/ diabaikan) ---
git add -A

rem Berkas catatan pemantau tidak perlu ikut ke GitHub.
git ls-files --error-unmatch pantau.log >nul 2>&1
if not errorlevel 1 (
    git rm --cached -q pantau.log
    echo       pantau.log dikeluarkan dari daftar berkas Git.
)

git diff --cached --quiet
if errorlevel 1 (
    if "%PESAN%"=="" (
        for /f "tokens=1-3 delims=/-. " %%d in ("%DATE%") do set "TGL=%%f-%%e-%%d"
        set "PESAN=Update otomatis !TGL! %TIME:~0,5%"
    )
    echo [3/5] Commit: !PESAN!
    git commit -m "!PESAN!"
    if errorlevel 1 (
        echo [GAGAL] Commit ditolak. Periksa pesan di atas.
        exit /b 1
    )
) else (
    echo [3/5] Tidak ada perubahan baru yang perlu di-commit.
)

rem --- 2. Tarik perubahan terbaru supaya tidak bentrok ---
git ls-remote --exit-code --heads origin %CABANG% >nul 2>&1
if errorlevel 1 (
    echo [4/5] Cabang belum ada di GitHub, langsung dikirim.
) else (
    echo [4/5] Menarik perubahan terbaru dari GitHub...
    rem Gabung, bukan rebase: riwayat berisi commit gabungan dari tarik.bat,
    rem dan rebase pada commit gabungan sering gagal.
    git pull --no-rebase --autostash --no-edit origin %CABANG%
    if errorlevel 1 (
        echo.
        echo [GAGAL] Penggabungan bentrok.
        echo   1. Ketik:  git status   lalu periksa berkas yang bertanda konflik.
        echo   2. Perbaiki, lalu:  git add -A ^&^& git commit --no-edit
        echo   3. Jalankan lagi:  simpan.bat
        exit /b 1
    )
)

rem --- 3. Kirim ke GitHub ---
echo [5/5] Mengirim ke GitHub...
git push origin %CABANG%
if errorlevel 1 (
    echo.
    echo [GAGAL] Push ditolak. Kemungkinan besar karena login GitHub belum tersimpan.
    echo   Jalankan sekali:  git push origin %CABANG%
    echo   lalu ikuti jendela login yang muncul ^(browser/password^).
    echo   Setelah sekali berhasil, login tersimpan di Windows Credential Manager
    echo   sehingga simpan.bat berikutnya tidak akan bertanya lagi.
    exit /b 1
)

echo.
echo Selesai. Perubahan sudah ada di GitHub ^(cabang %CABANG%^).
exit /b 0
