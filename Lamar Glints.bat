@echo off
rem ============================================================
rem  LAMAR OTOMATIS — Glints
rem ------------------------------------------------------------
rem  Klik dua kali berkas ini untuk:
rem    1. menarik kode terbaru dari GitHub,
rem    2. memasang dependensi hanya bila requirements.txt berubah,
rem    3. melamar otomatis khusus di Glints.
rem
rem  Kuota harian tetap satu hitungan bersama situs lain, jadi bila jatah
rem  hari ini sudah habis, sesi ini akan berhenti dengan pesan kuota.
rem
rem  Opsi tambahan (boleh dilewati):
rem    "Lamar Glints.bat" --limit 10
rem    "Lamar Glints.bat" --max-pages 2
rem
rem  Berkas ini memakai CRLF dan tanpa label goto (aman untuk cmd).
rem ============================================================
setlocal
cd /d "%~dp0"
title Glints - Lamar Otomatis

call tarik.bat
if errorlevel 1 (
    echo.
    echo [PERHATIAN] Pembaruan kode gagal. Melanjutkan dengan kode yang ada.
)

echo.
call jalankan.bat lamar --situs glints --tanpa-perbarui %*

echo.
echo ============================================================
echo  Selesai melamar di Glints. Jendela ini bisa ditutup.
echo ============================================================
pause
exit /b 0
