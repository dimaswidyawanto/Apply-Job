@echo off
rem Tarik pembaruan dari repo pengembangan (akun dimasw1997) ke repo Anda.
rem Contoh: tarik.bat
rem Remote & cabang bisa diganti lewat variabel lingkungan ARENA_REMOTE
rem dan ARENA_CABANG.
rem
rem Catatan: berkas ini sengaja memakai akhir baris CRLF dan TANPA label
rem goto. Batch berakhir LF + goto :label membuat cmd melompat ke tengah
rem baris dan memunculkan galat seperti "'gabungan' is not recognized".
setlocal
cd /d "%~dp0"

if "%ARENA_REMOTE%"=="" set "ARENA_REMOTE=arena"
if "%ARENA_CABANG%"=="" set "ARENA_CABANG=arena/4ab2b9fa-dimastes"
set "ARENA_URL=https://github.com/dimasw1997/dimastes.git"

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo [GAGAL] Folder ini bukan repo Git.
    exit /b 1
)

git remote get-url %ARENA_REMOTE% >nul 2>&1
if errorlevel 1 (
    echo Remote '%ARENA_REMOTE%' belum ada, menambahkan...
    git remote add %ARENA_REMOTE% %ARENA_URL%
)

echo [1/2] Mengambil pembaruan dari %ARENA_REMOTE% (%ARENA_URL%)...
git fetch %ARENA_REMOTE%
if errorlevel 1 (
    echo [GAGAL] Tidak bisa mengambil pembaruan. Periksa koneksi internet.
    exit /b 1
)

rem --- Bereskan sisa penggabungan yang gagal sebelumnya ---
if exist ".git\MERGE_HEAD" (
    echo [info] Membatalkan penggabungan sebelumnya yang belum selesai...
    git merge --abort
)

rem --- Simpan dulu perubahan lokal supaya penggabungan tidak ditolak
rem     dengan pesan "would be overwritten by merge".
set "STASH_SEBELUM=0"
for /f %%A in ('git stash list ^| find /c /v ""') do set "STASH_SEBELUM=%%A"
git stash push -m "tarik-otomatis" >nul 2>&1
set "STASH_SESUDAH=0"
for /f %%A in ('git stash list ^| find /c /v ""') do set "STASH_SESUDAH=%%A"
if %STASH_SESUDAH% GTR %STASH_SEBELUM% echo [info] Perubahan lokal disimpan sementara.

echo [2/2] Menggabungkan %ARENA_REMOTE%/%ARENA_CABANG% ke cabang ini...
git merge --no-edit %ARENA_REMOTE%/%ARENA_CABANG%
if errorlevel 1 (
    rem Riwayat berbeda, repo dibuat ulang: coba gabungkan tetap.
    git merge --no-edit --allow-unrelated-histories %ARENA_REMOTE%/%ARENA_CABANG%
)
if errorlevel 1 (
    echo.
    echo [GAGAL] Penggabungan bentrok. Selesaikan dengan:
    echo   git status
    echo   ... perbaiki file yang bertanda konflik ...
    echo   git add -A ^&^& git commit
    if %STASH_SESUDAH% GTR %STASH_SEBELUM% echo Perubahan lokal Anda tersimpan: git stash pop
    exit /b 1
)

if %STASH_SESUDAH% GTR %STASH_SEBELUM% (
    git stash pop >nul 2>&1
    if errorlevel 1 (
        echo [PERHATIAN] Perubahan lokal belum bisa dikembalikan otomatis.
        echo   Perubahan itu aman di git stash. Kembalikan dengan: git stash pop
    ) else (
        echo [info] Perubahan lokal dikembalikan.
    )
)

echo.
echo Selesai. Kode sudah yang terbaru. Kirim balik ke repo Anda dengan: simpan.bat
exit /b 0
