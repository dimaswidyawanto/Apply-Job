@echo off
rem Tarik pembaruan dari repo pengembangan (akun dimasw1997) ke repo Anda.
rem Contoh: tarik.bat
rem Remote & cabang bisa diganti lewat variabel lingkungan ARENA_REMOTE
rem dan ARENA_CABANG. Bawaannya `main`: semua perbaikan digabungkan ke
rem sana lewat pull request. Bila ARENA_CABANG menunjuk cabang lama yang
rem sudah tidak ada, skrip ini tetap menarik `main` supaya Anda tidak
rem tertinggal di kode lama.
rem
rem Catatan: berkas ini sengaja memakai akhir baris CRLF dan TANPA label
rem goto. Batch berakhir LF + goto :label membuat cmd melompat ke tengah
rem baris dan memunculkan galat seperti "'gabungan' is not recognized".
setlocal
cd /d "%~dp0"

rem Jangan pernah membuka editor teks (Vim) di tengah skrip: tanpa ini,
rem penggabungan yang menghasilkan commit gabungan akan menggantung di Vim.
set "GIT_EDITOR=echo"
set "GIT_MERGE_AUTOEDIT=no"

if "%ARENA_REMOTE%"=="" set "ARENA_REMOTE=arena"
if "%ARENA_CABANG%"=="" set "ARENA_CABANG=main"
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

rem --- Jaring pengaman: bila cabang di atas sudah usang/dihapus, HEAD masih
rem     tertinggal dari main. Tarik main juga supaya perbaikan sampai.
set "SISA_MAIN=0"
for /f %%A in ('git rev-list --count "HEAD..%ARENA_REMOTE%/main" 2^>nul') do set "SISA_MAIN=%%A"
if not "%SISA_MAIN%"=="0" (
    echo [info] Masih tertinggal %SISA_MAIN% pembaruan di %ARENA_REMOTE%/main, menarik juga...
    git merge --no-edit %ARENA_REMOTE%/main
    if errorlevel 1 git merge --no-edit --allow-unrelated-histories %ARENA_REMOTE%/main
    if errorlevel 1 (
        echo.
        echo [GAGAL] Penggabungan %ARENA_REMOTE%/main bentrok. Selesaikan dengan:
        echo   git status
        echo   ... perbaiki file yang bertanda konflik ...
        echo   git add -A ^&^& git commit
        exit /b 1
    )
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
set "VERSI=?"
set "JUDUL=?"
for /f %%V in ('git rev-parse --short HEAD 2^>nul') do set "VERSI=%%V"
for /f "delims=" %%S in ('git log -1 --pretty^=%%s 2^>nul') do set "JUDUL=%%S"
echo Versi sekarang: %VERSI% - %JUDUL%
echo Selesai. Kode sudah yang terbaru. Kirim balik ke repo Anda dengan: simpan.bat
exit /b 0
