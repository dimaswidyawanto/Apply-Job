@echo off
rem Pantau folder ini: kirim perubahan ke GitHub DAN tarik pembaruan baru,
rem keduanya otomatis.
rem Contoh: pantau.bat        (periksa tiap 60 detik)
rem          pantau.bat 30   (periksa tiap 30 detik)
rem Hentikan dengan Ctrl+C. File .env, *.db, *.log, dan debug/ tidak ikut terkirim.
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "JEDA=%~1"
if "%JEDA%"=="" set "JEDA=60"

if "%ARENA_REMOTE%"=="" set "ARENA_REMOTE=arena"
if "%ARENA_CABANG%"=="" set "ARENA_CABANG=arena/4ab2b9fa-dimastes"
if "%ARENA_URL%"=="" set "ARENA_URL=https://github.com/dimasw1997/dimastes.git"

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo [GAGAL] Folder ini bukan repo Git.
    exit /b 1
)

for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "CABANG=%%b"

echo Memantau perubahan di %CD%
echo Cabang: %CABANG%
echo Selang pemeriksaan: %JEDA% detik. Tekan Ctrl+C untuk berhenti.
echo Kirim otomatis + tarik pembaruan otomatis (saat tidak ada perubahan lokal).
echo.

:pantau
set "ADA="
set "BELUM=0"
for /f "delims=" %%a in ('git status --porcelain 2^>nul') do set "ADA=1"

rem Commit yang belum terkirim (mis. push gagal karena internet putus).
for /f "delims=" %%c in ('git rev-list --count "@{u}..HEAD" 2^>nul') do set "BELUM=%%c"
if not "%BELUM%"=="0" set "ADA=1"

if defined ADA (
    echo [%DATE% %TIME%] Perubahan terdeteksi, mengirim ke GitHub...
    call "%~dp0simpan.bat"
    echo.
    goto :jeda
)

rem --- Tarik pembaruan: hanya saat tidak ada perubahan lokal, supaya berkas
rem     yang sedang Anda sunting tidak tertimpa. ---
git remote get-url %ARENA_REMOTE% >nul 2>&1
if errorlevel 1 git remote add %ARENA_REMOTE% %ARENA_URL% >nul 2>&1

git fetch --quiet origin >nul 2>&1
git fetch --quiet %ARENA_REMOTE% >nul 2>&1

set "BARU_ORIGIN=0"
set "BARU_ARENA=0"
for /f "delims=" %%d in ('git rev-list --count "HEAD..@{u}" 2^>nul') do set "BARU_ORIGIN=%%d"
for /f "delims=" %%e in ('git rev-list --count "HEAD..%ARENA_REMOTE%/%ARENA_CABANG%" 2^>nul') do set "BARU_ARENA=%%e"

if not "%BARU_ORIGIN%"=="0" (
    echo [%DATE% %TIME%] Ada %BARU_ORIGIN% commit baru di GitHub, menarik...
    call "%~dp0simpan.bat"
    echo.
)

if not "%BARU_ARENA%"=="0" (
    echo [%DATE% %TIME%] Ada %BARU_ARENA% pembaruan dari repo pengembangan, menarik...
    call "%~dp0tarik.bat"
    if errorlevel 1 (
        git merge --abort >nul 2>&1
        echo [peringatan] penggabungan bentrok - dilewati putaran ini.
    )
    echo.
)

:jeda
rem Jeda: ping dipakai karena 'timeout' gagal saat dijalankan tanpa jendela.
ping -n %JEDA% 127.0.0.1 >nul 2>&1
goto :pantau
