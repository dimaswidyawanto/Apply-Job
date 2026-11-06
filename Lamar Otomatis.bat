@echo off
rem ============================================================
rem  LAMAR OTOMATIS — satu klik untuk JobStreet, Glints, Indeed
rem ------------------------------------------------------------
rem  Cukup klik dua kali berkas ini. Yang terjadi:
rem    1. kode ditarik dari GitHub (selalu versi terbaru),
rem    2. dependensi hanya dipasang bila berubah,
rem    3. JobStreet -> Glints -> Indeed dijalankan berurutan,
rem    4. kuota harian tetap satu hitungan untuk ketiga situs.
rem
rem  Opsi (boleh dilewati):
rem    Lamar Otomatis.bat --situs jobstreet,indeed
rem    Lamar Otomatis.bat --limit 10
rem    Lamar Otomatis.bat --max-pages 2
rem
rem  Berkas ini memakai CRLF dan tanpa label goto (aman untuk cmd).
rem ============================================================
setlocal
cd /d "%~dp0"
title Lamar Otomatis - JobStreet, Glints, Indeed

call tarik.bat
if errorlevel 1 (
    echo.
    echo [PERHATIAN] Pembaruan kode gagal. Melanjutkan dengan kode yang ada.
)

echo.
call jalankan.bat lamar --tanpa-perbarui %*

echo.
echo ============================================================
echo  Selesai. Jendela ini bisa ditutup.
echo ============================================================
pause
exit /b 0
